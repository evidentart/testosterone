"""Raw artifact files captured for a run (``RunRecord.snapshot_dir``)."""

from __future__ import annotations

from testo_core import paths
from testo_core.history.views import CompletedRunView


def snapshot_files_for_download(*, record: CompletedRunView) -> list[tuple[str, bytes]]:
    """``(relative_path, bytes)`` for each file in the run's snapshot, sorted by path.

    ``snapshot_dir`` is relative to ``paths.ORCHESTRATOR_ROOT`` (the data root).
    """
    if not record.snapshot_dir:
        return []
    base = paths.ORCHESTRATOR_ROOT / record.snapshot_dir
    if not base.is_dir():
        return []
    return [
        (str(p.relative_to(base)), p.read_bytes()) for p in sorted(base.rglob("*")) if p.is_file()
    ]
