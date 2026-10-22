"""Record uploaded JUnit XML (or Playwright JSON) as a run: the server side of ``testo ingest --server``.

CI jobs anywhere upload their JUnit XML to one Testosterone server
(``POST /api/v1/ingest``), so the whole team's runs land in one history. The
upload is written to a scratch directory and recorded through
:class:`~testo_core.services.cycle_run.CycleRunService` with a one-stage
``junit`` cycle, exactly like a local ``testo ingest``: same engine, same run
record, same reporters. Nothing in an upload is ever executed.

The client's CI provenance (provider, commit, branch, ...) travels in the
request, because the server's own environment says nothing about it.
"""

from __future__ import annotations

import json
import re
import tempfile
import threading
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from testo_core.config.errors import ConfigValidationError
from testo_core.config.schema import TestosteroneConfig

# Upload limits: plenty for real suites, small enough that one request can't fill a disk.
MAX_FILES = 200
MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_TOTAL_BYTES = 100 * 1024 * 1024

# Run-record keys an upload may set. Everything else is computed by the server.
RUN_METADATA_KEYS: tuple[str, ...] = (
    "ci_provider",
    "ci_pipeline_id",
    "ci_job_id",
    "ci_commit_sha",
    "ci_ref_name",
    "repository",
)
_MAX_METADATA_CHARS = 256
_UNSAFE_FILENAME = re.compile(r"[^A-Za-z0-9._-]+")

# One ingest at a time: they take milliseconds, and the run history (often
# SQLite) and report archive are shared by every request.
_INGEST_LOCK = threading.Lock()


@dataclass(frozen=True)
class IngestOutcome:
    run_id: str | None
    cycle: str
    exit_code: int
    tests: int
    passed: int
    failed: int
    skipped: int


def clean_run_metadata(raw: Mapping[str, str | None]) -> dict[str, str]:
    """Keep the allowed, non-empty provenance keys, trimmed to a sane length."""
    out: dict[str, str] = {}
    for key in RUN_METADATA_KEYS:
        value = (raw.get(key) or "").strip()
        if value:
            out[key] = value[:_MAX_METADATA_CHARS]
    return out


def ingest_uploaded_reports(
    *,
    cfg: TestosteroneConfig,
    cycle: str,
    reports: Sequence[tuple[str, bytes]],
    stage: str = "junit",
    tier: str = "unit",
    run_metadata: Mapping[str, str] | None = None,
) -> IngestOutcome:
    """Record *reports* (``(filename, content)`` pairs) as one run of *cycle*.

    Raises :class:`ConfigValidationError` for an empty or oversized upload, or
    an unsafe cycle or stage name.
    """
    from testo_core.services.cycle_run import (
        CycleRunOptions,
        CycleRunService,
        junit_ingest_plan,
    )

    if not reports:
        raise ConfigValidationError("no JUnit XML files in the upload.")
    if len(reports) > MAX_FILES:
        raise ConfigValidationError(f"too many files ({len(reports)}; the limit is {MAX_FILES}).")
    total = 0
    for name, content in reports:
        if len(content) > MAX_FILE_BYTES:
            raise ConfigValidationError(
                f"{name!r} is larger than {MAX_FILE_BYTES // (1024 * 1024)} MB."
            )
        total += len(content)
    if total > MAX_TOTAL_BYTES:
        raise ConfigValidationError(
            f"upload is larger than {MAX_TOTAL_BYTES // (1024 * 1024)} MB in total."
        )

    with _INGEST_LOCK, tempfile.TemporaryDirectory(prefix="testo-ingest-") as scratch:
        root = Path(scratch)
        reports_dir = root / "reports"
        reports_dir.mkdir()
        for index, (name, content) in enumerate(reports):
            # Client file names are only a label; the index keeps them unique.
            label = _UNSAFE_FILENAME.sub("_", Path(name or "report").stem)[:80] or "report"
            # .json is a Playwright JSON report, anything else JUnit XML (junit_import decides by suffix).
            suffix = ".json" if (name or "").lower().endswith(".json") else ".xml"
            (reports_dir / f"{index:03d}-{label}{suffix}").write_bytes(content)

        plan = junit_ingest_plan(
            cycle=cycle,
            reports=["reports/*.xml", "reports/*.json"],
            target_repo=root,
            stage_name=stage,
            tier=tier,
        )
        # The scratch path means nothing after this call; record the client's repository instead.
        metadata: dict[str, str | None] = {**(run_metadata or {})}
        metadata["target_repo"] = metadata.get("repository")
        outcome = CycleRunService().run(
            cfg=cfg,
            plan=plan,
            renderer=_SilentRenderer(),
            options=CycleRunOptions(
                artifacts_root=root / "artifacts",
                run_metadata=metadata,
                force=True,
            ),
        )
        # The DB backend copied the artifacts to static/history/<run_id>/; the
        # scratch directory goes when this block ends.
        counts = _status_counts(root / "artifacts" / plan.name / stage / "allure-results" / "junit")

    return IngestOutcome(
        run_id=outcome.run_id,
        cycle=plan.name,
        exit_code=outcome.exit_code,
        tests=sum(counts.values()),
        passed=counts.get("passed", 0),
        failed=counts.get("failed", 0) + counts.get("broken", 0),
        skipped=counts.get("skipped", 0),
    )


def _status_counts(results_dir: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    for path in results_dir.glob("*-result.json"):
        try:
            status = str(json.loads(path.read_text(encoding="utf-8")).get("status") or "unknown")
        except (OSError, ValueError):
            continue
        counts[status] = counts.get(status, 0) + 1
    return counts


class _SilentRenderer:
    wants_streaming = False

    def handle(self, event: object) -> None:
        return
