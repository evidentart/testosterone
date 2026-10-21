---
type: tracker
status: current
created: 2026-06-25
updated: 2026-10-21
---

# Technical Debt Tracker

[Index](../Index.md)

Open backlog for the `testo-core` codebase. Items come from code reading and known contract gaps, not only inline `TODO` markers (there are none in `testo_core/`, `testo_api/` or `tests/`).

Related: [Deep Dive - Execution Logic](../Architecture/Deep%20Dive%20-%20Execution%20Logic.md), [Troubleshooting and Error Codes](../CLI%20Commands/Troubleshooting%20and%20Error%20Codes.md), [Architecture Overview](../Architecture/Architecture%20Overview.md).

---

## Open

### 1. Signal deaths classify as test failures

Timeouts normalize to return code **124** (exit **3**) and engine exceptions to exit **4**, but other signal deaths (e.g. SIGKILL, rc **137**) still classify as exit **1**. This is locked as a known misclassification in `tests/contract/testo_core/test_exit_code_contract.py` until a signal-aware classifier lands.

### 2. Reporter failures don't fail the run

`testo_core/reporting/reporters/factory.py` catches per-reporter exceptions, so a configured integration can be skipped silently after a green run. Fix: an opt-in `reporters_required: true` that maps a reporter failure to exit **3**, plus a `reporter_failed` NDJSON event.

### 3. Sequential-only orchestrator

Stages run one at a time (`engine/orchestrator.py`); parallelism today is framework-internal (e.g. BehaveX `--workers`). Opt-in parallel stages need isolated `artifacts/<cycle>/<stage>/` trees, aggregated exit classification and documented resource limits.

### 4. Log reader join timeout

`executor.py` calls `reader.join(timeout=2.0)` after the subprocess exits, so a very large final stdout burst could be cut short. Fix: drain until EOF; add an integration test with a large burst.

## Known and intentional

- **Per-stage Allure wipe**: `executor.py` removes the stage's `allure-results/` before each run to isolate stages. Retries must use separate stage names.
- **`LogBuffer.on_chunk` contains renderer errors** (`engine/log_buffer.py`) so a broken renderer cannot crash a run; the first failure per stage is logged as a warning.
- **Boundary catch-alls**: the `except Exception` sites left in `testo_core/` and `testo_api/` are deliberate boundaries (orchestrator, reporter factory, persistence backends, API routes, connection checks, third-party report generators). Each logs with `exc_info` and has a one-line comment saying why it is broad.
- **Orchestrator catch-all**: `run_plan()` turns an exception from `run_stage()` into an internal-failure stage result, which classifies the plan as exit **4** rather than crashing.

## Resolved

- Exit-code contract single-sourced in `engine/exit_codes.py`; timeouts → 124 → exit 3, engine errors → exit 4.
- The second, Docker-based execution stack (`HeadlessEngineService`, `runners.py`, pluggy plugins, `/api/v1/executions`, Streamlit UI) was removed in v1.1; every run goes through `CycleRunService` and the engine.
- `--ci` forces a synchronous report archive; a required archive failure exits **3**.
- `testo_core/persistence/` (`JsonBackend`, `DbBackend`, `composite_backend()`) replaced the persistence stub.
- MinIO, the pre-v1.1 snapshot reads and the Docker-stack record shape in `history/` were removed in v1.1.
- `mypy testo_core testo_api` reports 0 errors and blocks CI, as does `ruff format --check`.
- Silent-error audit: I/O paths (ReportPortal, Extent, metrics and Allure readers, doctor checks, persistence) catch specific exceptions (`OSError`, `ValueError`, `requests.RequestException`, `jinja2.TemplateError`, `SQLAlchemyError`) and log with `exc_info` instead of passing silently.
- BehaveX runs without `--formatter`, so it writes its own HTML report again; Allure results come from its `report.json` after the stage. Export and HTML failures are logged, appended to `run.log` and set `StageResult.error` (exit code unchanged), so the stage panel and `stage_finished` NDJSON show them.
- A failed Git trigger evaluation logs a warning and prefixes the snapshot fallback's `reason` with the Git error, so the trigger panel and `cycle_trigger` NDJSON event show it.

## Refreshing this note

On each release or large refactor, re-run `rg 'TODO|FIXME|HACK' testo_core testo_api tests`, look for new `except Exception` sites in `testo_core/engine/`, and move fixed items to **Resolved**.
