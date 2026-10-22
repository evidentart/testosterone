"""Failing tests as GitHub Actions annotations, shown inline on the pull request diff.

``testo report annotations`` prints one ``::error`` workflow command per failing
test. GitHub turns each into an annotation on the check run, placed on the file
and line where the test failed, so a reviewer sees the failure next to the code
in "Files changed". Workflow commands need no token or permission, which is why
the GitHub Action emits them by default.

The location comes from the failure's stack trace in the run's Allure results
(pytest's ``path:line:`` and Python's ``File "path", line N`` frames): the first
frame that is a file inside the workspace. A failure with no such frame is
still annotated, just not on a line.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from testo_core import paths
from testo_core.history.views import CompletedRunView
from testo_core.services.report_archive_diff import _case_key

# GitHub shows at most 10 error annotations per step; the rest are dropped silently.
MAX_ANNOTATIONS = 10
_FAILED = frozenset({"failed", "broken"})
_MESSAGE_CHARS = 1000
_LOCATIONS = (
    re.compile(r"^(?P<file>[^\s:\"'][^:\n\"']*\.\w+):(?P<line>\d+):", re.MULTILINE),
    re.compile(r"File \"(?P<file>[^\"\n]+)\", line (?P<line>\d+)"),
)


@dataclass(frozen=True)
class Failure:
    name: str
    status: str
    message: str
    file: str | None = None
    line: int | None = None


def _frames(trace: str) -> list[tuple[str, int]]:
    """Every ``(path, line)`` in ``trace``, in the order they appear."""
    found = [
        (m.start(), m["file"], int(m["line"])) for rx in _LOCATIONS for m in rx.finditer(trace)
    ]
    return [(file, line) for _, file, line in sorted(found)]


def locate(trace: str, *, workspace: Path, roots: Sequence[Path]) -> tuple[str, int] | None:
    """First frame in ``trace`` that is a file under ``workspace``, as a workspace-relative path."""
    workspace = workspace.resolve()
    for file, line in _frames(trace):
        raw = Path(file)
        for candidate in [raw] if raw.is_absolute() else [root / raw for root in roots]:
            try:
                resolved = candidate.resolve()
                if resolved.is_file():
                    return resolved.relative_to(workspace).as_posix(), line
            except (OSError, ValueError):
                continue
    return None


def load_failures(
    run: CompletedRunView, *, workspace: Path, roots: Iterable[Path] = ()
) -> list[Failure]:
    """The run's failing and broken tests, sorted by name, located when the trace allows."""
    if not run.snapshot_dir:
        return []
    search = [workspace, *roots]
    if run.target_repo:
        search.append(Path(run.target_repo))
    seen: dict[str, Failure] = {}
    for path in sorted((paths.ORCHESTRATOR_ROOT / run.snapshot_dir).rglob("*-result.json")):
        try:
            data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        status = str(data.get("status") or "").lower()
        if status not in _FAILED:
            continue
        details = data.get("statusDetails") or {}
        where = locate(str(details.get("trace") or ""), workspace=workspace, roots=search)
        seen[_case_key(data)] = Failure(
            name=str(data.get("name") or data.get("fullName") or "test")[:200],
            status=status,
            message=str(details.get("message") or status).strip()[:_MESSAGE_CHARS],
            file=where[0] if where else None,
            line=where[1] if where else None,
        )
    return sorted(seen.values(), key=lambda f: f.name)


def _escape_data(text: str) -> str:
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _escape_property(text: str) -> str:
    return _escape_data(text).replace(":", "%3A").replace(",", "%2C")


def workflow_commands(
    failures: Sequence[Failure], *, cycle: str | None, limit: int = MAX_ANNOTATIONS
) -> list[str]:
    """``::error`` lines for the first ``limit`` failures, then a ``::notice`` for the rest."""
    lines = []
    for f in failures[:limit]:
        props = []
        if f.file:
            props.append(f"file={_escape_property(f.file)}")
            if f.line:
                props.append(f"line={f.line}")
        title = f"{f.name} {f.status}" + (f" ({cycle})" if cycle else "")
        props.append(f"title={_escape_property(title)}")
        lines.append(f"::error {','.join(props)}::{_escape_data(f.message)}")
    if len(failures) > limit:
        lines.append(
            f"::notice title=testo::{len(failures) - limit} more failing tests are not "
            "annotated; the job summary lists them all"
        )
    return lines
