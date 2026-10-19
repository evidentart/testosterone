---
type: spec
status: current
created: 2026-10-07
updated: 2026-10-19
---

# Library Packaging

## Decision

Ship the orchestrator as an installable library (`testo-core` on PyPI, import `testo_core`) so the CLI, CI wrappers, the API and custom scripts share one engine instead of each needing an app checkout.

## Implementation

| Item | Location |
|------|----------|
| Package metadata | `pyproject.toml`: `name = "testo-core"` |
| Public API | `testo_core/__init__.py` |
| CLI entry | `testo` console script (`testo_core.cli.app:main`) |
| API entry | `testo-api` console script (`testo_api`) |
| Dev install | `pip install -e '.[dev]'` |

Run history is always saved (SQLite by default), so `sqlmodel` is a core dependency; the `[db]` extra only adds the Postgres driver and `tomli-w`. The `package` CI job installs the built wheel with no extras and runs a cycle to keep it that way.

FastAPI (`testo_api`) and the React frontend are **optional consumers**: `testo run` must not need them. See [Architecture Overview § Adjacent packages (same repo)](../Architecture/Architecture%20Overview.md#adjacent-packages-same-repo).

Publishing: [Publishing to PyPI](../Processes%20&%20Guides/Publishing%20to%20PyPI.md). Commands: [Command Reference](../CLI%20Commands/Command%20Reference.md).
