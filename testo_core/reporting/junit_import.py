"""Convert JUnit XML reports into Allure ``*-result.json`` files.

Runners that don't speak Allure (Jest via ``jest-junit``, Playwright's
``junit`` reporter, Maestro, ``go test`` via go-junit-report, ...) all emit
JUnit XML. A stage lists those files with ``junit_xml`` globs; after the stage
the executor calls :func:`import_junit_reports`, which writes one Allure result
per ``<testcase>`` into the stage's results dir. From there the stage is
counted by :mod:`testo_core.reporting.allure_results` (summaries, health %,
the dashboard) and rendered by every reporter like a pytest/Behave stage.

Status mapping (JUnit has no "broken" of its own):

    <failure>            -> failed
    <error>              -> broken
    <skipped>            -> skipped
    none of the above    -> passed

A ``.json`` file among the matches is read as a Playwright JSON report by
:mod:`testo_core.reporting.playwright_import` instead, which keeps retries,
flakiness and attachments (traces, screenshots) that JUnit loses.

A ``junit`` stage (``testo ingest``) runs no command at all: the executor calls
this without ``not_before`` and derives the stage's returncode from ``failed``.

Only the files a stage's own command wrote are parsed (paths come from the
stage config and stay inside ``target_repo``); expat does not resolve external
entities, so no file or network access happens during parsing.
"""

from __future__ import annotations

import hashlib
import json
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

_MAX_TRACE_CHARS = 20_000


@dataclass(frozen=True)
class JunitImportResult:
    files: tuple[Path, ...]
    tests: int
    errors: tuple[str, ...]
    # Cases that ended ``failed`` or ``broken``; what a ``junit`` (ingest) stage's
    # returncode is derived from, since no process exit code exists there.
    failed: int = 0
    # Sum of the per-case ``time`` attributes, in seconds.
    duration_s: float = 0.0
    # Playwright JSON only: tests that passed on a retry, and attachments copied.
    flaky: int = 0
    attachments: int = 0


def _suite_start_ms(suite: ET.Element, fallback_ms: int) -> int:
    stamp = suite.get("timestamp")
    if stamp:
        try:
            parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
            return int(parsed.timestamp() * 1000)
        except ValueError:
            pass
    return fallback_ms


def _seconds_ms(value: str | None) -> int:
    try:
        return max(0, int(round(float(value or 0) * 1000)))
    except ValueError:
        return 0


def _status(case: ET.Element) -> tuple[str, str | None, str | None]:
    for tag, status in (("failure", "failed"), ("error", "broken"), ("skipped", "skipped")):
        node = case.find(tag)
        if node is None:
            continue
        text = (node.text or "").strip()
        message = node.get("message") or (text.splitlines()[0] if text else None)
        trace = text or None
        if trace and len(trace) > _MAX_TRACE_CHARS:
            trace = trace[:_MAX_TRACE_CHARS] + "\n… (truncated)"
        return status, message, trace
    return "passed", None, None


def _suites(root: ET.Element) -> list[ET.Element]:
    if root.tag == "testsuite":
        return [root]
    # <testsuites> or any wrapper: every nested <testsuite>, depth-first.
    return list(root.iter("testsuite"))


def _results_for_file(path: Path, *, tool: str, fallback_ms: int) -> list[dict]:
    root = ET.parse(path).getroot()  # noqa: S314 — stage-owned file, expat ignores external entities
    results: list[dict] = []
    for suite in _suites(root):
        suite_name = suite.get("name") or path.stem
        clock = _suite_start_ms(suite, fallback_ms)
        for case in suite.findall("testcase"):
            name = case.get("name") or "(unnamed)"
            classname = case.get("classname") or suite_name
            full_name = f"{classname}.{name}" if classname else name
            duration = _seconds_ms(case.get("time"))
            status, message, trace = _status(case)
            result: dict = {
                "uuid": str(uuid.uuid4()),
                "historyId": hashlib.sha256(f"{tool}:{full_name}".encode()).hexdigest(),
                "name": name,
                "fullName": full_name,
                "status": status,
                "stage": "finished",
                "start": clock,
                "stop": clock + duration,
                "labels": [
                    {"name": "suite", "value": suite_name},
                    {"name": "testClass", "value": classname},
                    {"name": "framework", "value": tool},
                    {"name": "language", "value": "junit"},
                ],
            }
            if message or trace:
                result["statusDetails"] = {
                    k: v for k, v in (("message", message), ("trace", trace)) if v
                }
            results.append(result)
            clock += duration
    return results


def import_junit_reports(
    *,
    target_repo: Path,
    patterns: tuple[str, ...],
    results_dir: Path,
    tool: str = "command",
    not_before: float | None = None,
    first_match_only: bool = False,
) -> JunitImportResult:
    """Convert every JUnit XML (or Playwright JSON) matching ``patterns`` into Allure results.

    ``first_match_only`` reads only the files of the first pattern that
    matches anything, for adapters that list one report in several formats
    (Playwright: its JSON report, else its JUnit report) and must not count
    the same tests twice. Attachments a Playwright report points to are copied
    only from inside ``target_repo``.

    ``not_before`` (epoch seconds, the stage start) skips files older than the
    stage, so a stale report left by an earlier run is never counted as this
    run's result. A malformed file is reported in ``errors`` and skipped; it
    never fails the stage on its own (the process exit code already does).
    """
    repo = target_repo.expanduser().resolve()
    results_dir.mkdir(parents=True, exist_ok=True)
    files: list[Path] = []
    for pattern in patterns:
        for match in sorted(repo.glob(pattern)):
            resolved = match.resolve()
            if not resolved.is_file() or repo not in resolved.parents:
                continue
            if not_before is not None and resolved.stat().st_mtime < not_before - 1:
                continue
            if resolved not in files:
                files.append(resolved)
        if first_match_only and files:
            break

    tests = 0
    failed = 0
    duration_ms = 0
    flaky = 0
    attachments = 0
    errors: list[str] = []
    for path in files:
        try:
            if path.suffix.lower() == ".json":
                from testo_core.reporting.playwright_import import playwright_results_for_file

                parsed = playwright_results_for_file(
                    path, tool=tool, results_dir=results_dir, attachments_root=repo
                )
                results = parsed.results
                flaky += parsed.flaky
                attachments += parsed.attachments
                errors += [f"{path.name}: {note}" for note in parsed.notes]
            else:
                results = _results_for_file(
                    path, tool=tool, fallback_ms=int(path.stat().st_mtime * 1000)
                )
        except (ET.ParseError, OSError, ValueError) as exc:
            errors.append(f"{path.name}: {exc}")
            continue
        for result in results:
            out = results_dir / f"{result['uuid']}-result.json"
            out.write_text(json.dumps(result), encoding="utf-8")
            if result["status"] in ("failed", "broken"):
                failed += 1
            duration_ms += result["stop"] - result["start"]
        tests += len(results)
    return JunitImportResult(
        files=tuple(files),
        tests=tests,
        errors=tuple(errors),
        failed=failed,
        duration_s=duration_ms / 1000,
        flaky=flaky,
        attachments=attachments,
    )
