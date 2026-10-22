"""A run as GitHub-flavored Markdown: a job summary or a pull request comment.

``testo report markdown`` prints it; the GitHub Action writes it to the job
summary and, when asked, keeps one comment per cycle on the pull request up to
date (the first line is a hidden marker it finds that comment by).

Everything comes from stored run records and their artifact snapshots, so the
same text can be rebuilt for any past run.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from testo_core import paths
from testo_core.history.read_model import get_run, list_recent_runs
from testo_core.history.views import CompletedRunView
from testo_core.services.report_archive_diff import CaseChange, _load_cases, diff_case_maps

MAX_ROWS = 20
_SCAN_LIMIT = 500
_FAILED = frozenset({"failed", "broken"})
_CHANGE_ORDER = {"regression": 0, "added": 1, "fix": 2, "removed": 3, "status_change": 4}
_CHANGE_TALLY = {
    "regression": ("regression", "regressions"),
    "fix": ("fixed", "fixed"),
    "added": ("new test", "new tests"),
    "removed": ("removed", "removed"),
    "status_change": ("changed", "changed"),
}
_CHANGE_LABEL = {
    "regression": "🔴 regression",
    "fix": "🟢 fixed",
    "added": "🆕 new",
    "removed": "➖ removed",
    "status_change": "🔁 changed",
}


def comment_marker(cycle: str | None) -> str:
    """Hidden first line that identifies this cycle's comment on a pull request."""
    return f"<!-- testo-summary:{cycle or '-'} -->"


@dataclass(frozen=True)
class RunSummary:
    run: CompletedRunView
    previous: CompletedRunView | None
    failing: tuple[str, ...]
    changes: tuple[CaseChange, ...]


def _cases(run: CompletedRunView | None) -> dict[str, dict[str, Any]]:
    if run is None or not run.snapshot_dir:
        return {}
    return _load_cases(paths.ORCHESTRATOR_ROOT / run.snapshot_dir)


def _cycle_runs(cycle: str) -> list[CompletedRunView]:
    return [r for r in list_recent_runs(limit=_SCAN_LIMIT) if r.cycle == cycle]


def load_run_summary(*, cycle: str | None = None, run_id: str | None = None) -> RunSummary | None:
    """The given run (or ``cycle``'s latest) with its failures and changes since the run before."""
    if run_id:
        run = get_run(run_id=run_id)
        if run is None:
            return None
        older = (
            [r for r in _cycle_runs(run.cycle) if r.created_at < run.created_at]
            if run.cycle
            else []
        )
        previous = older[0] if older else None
    elif cycle:
        runs = _cycle_runs(cycle)
        if not runs:
            return None
        run, previous = runs[0], (runs[1] if len(runs) > 1 else None)
    else:
        recent = list_recent_runs(limit=1)
        if not recent:
            return None
        return load_run_summary(run_id=recent[0].run_id)

    current_cases = _cases(run)
    failing = tuple(
        sorted(str(c["name"]) for c in current_cases.values() if c["status"] in _FAILED)
    )
    changes: tuple[CaseChange, ...] = ()
    if previous is not None:
        previous_cases = _cases(previous)
        if previous_cases and current_cases:
            changes = tuple(
                sorted(
                    diff_case_maps(previous_cases, current_cases),
                    key=lambda c: (_CHANGE_ORDER.get(c.kind, 9), c.name),
                )
            )
    return RunSummary(run=run, previous=previous, failing=failing, changes=changes)


def _seconds(ms: float | None) -> str:
    if ms is None:
        return "—"
    return f"{ms / 1000:.1f}s"


def _count(value: Any) -> str:
    return "—" if value is None else str(value)


def _escape(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def render_markdown(summary: RunSummary, *, run_url: str | None = None) -> str:
    """Markdown for one run: headline, per-stage table, failing tests, changes since last run."""
    run = summary.run
    ok = run.returncode == 0
    name = run.cycle or "run"
    lines = [
        comment_marker(run.cycle),
        f"### {'✅' if ok else '❌'} Testosterone: `{name}` {'passed' if ok else 'failed'}",
        "",
    ]

    headline = f"Ran in {_seconds(run.wall_duration_ms)}"
    if run.total_tests is not None:
        failed = (run.failed or 0) + (run.broken or 0)
        headline = (
            f"**{run.passed or 0} passed · {failed} failed · {run.skipped or 0} skipped** "
            f"in {_seconds(run.wall_duration_ms)}"
        )
    if run.health_pct is not None:
        headline += f" · health {run.health_pct:.1f}%"
    lines += [headline, ""]

    if run.stage_health:
        lines += [
            "| Stage | Runner | Result | Tests | Passed | Failed | Skipped | Time |",
            "|---|---|---|---:|---:|---:|---:|---:|",
        ]
        for s in run.stage_health:
            failed = (s.get("failed") or 0) + (s.get("broken") or 0)
            result = "✅ pass" if s.get("returncode") == 0 else "❌ fail"
            if s.get("quarantined"):
                result += f" · {len(s['quarantined'])} quarantined"
            duration = s.get("duration_s")
            lines.append(
                f"| {_escape(str(s.get('name', '?')))} | {s.get('framework', '')} | {result} "
                f"| {_count(s.get('total_tests'))} | {_count(s.get('passed'))} | {failed} "
                f"| {_count(s.get('skipped'))} | {_seconds(duration * 1000 if duration is not None else None)} |"
            )
        lines.append("")

    if summary.failing:
        lines.append(f"<details{' open' if len(summary.failing) <= 5 else ''}>")
        lines.append(f"<summary><b>Failing tests ({len(summary.failing)})</b></summary>")
        lines.append("")
        quarantined = {str(n) for s in run.stage_health for n in (s.get("quarantined") or []) if n}
        lines += [
            f"- `{_escape(n)}`" + (" _(quarantined)_" if n in quarantined else "")
            for n in summary.failing[:MAX_ROWS]
        ]
        if len(summary.failing) > MAX_ROWS:
            lines.append(f"- … and {len(summary.failing) - MAX_ROWS} more")
        lines += ["", "</details>", ""]

    if summary.previous is None:
        lines.append("_First recorded run of this cycle, so there is nothing to compare with yet._")
    elif not summary.changes:
        lines.append("No test changed outcome since the previous run.")
    else:
        kinds: list[str] = [c.kind for c in summary.changes]
        tally = ", ".join(
            f"{n} {_CHANGE_TALLY[k][0 if n == 1 else 1]}"
            for k in _CHANGE_ORDER
            if (n := kinds.count(k))
        )
        lines += [
            f"**Since the previous run:** {tally}",
            "",
            "| Change | Test | Before | After |",
            "|---|---|---|---|",
        ]
        for c in summary.changes[:MAX_ROWS]:
            lines.append(
                f"| {_CHANGE_LABEL.get(c.kind, c.kind)} | `{_escape(c.name)}` "
                f"| {c.baseline_status or '—'} | {c.current_status or '—'} |"
            )
        if len(summary.changes) > MAX_ROWS:
            lines.append(f"| | … and {len(summary.changes) - MAX_ROWS} more | | |")
    lines.append("")

    footer = f"<sub>Run `{run.run_id}`"
    if run_url:
        footer += f" · [workflow run]({run_url})"
    footer += " · generated by [Testosterone](https://github.com/taltal-beep/testosterone)</sub>"
    lines.append(footer)
    return "\n".join(lines) + "\n"
