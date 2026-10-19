---
type: roadmap
status: current
created: 2026-06-25
updated: 2026-10-19
---

# Product Roadmap

Where Testosterone (`testo-core`, CLI `testo`) stands today and what comes next. Open engineering debt lives in [Technical Debt Tracker](../Testing%20Workflows/Technical%20Debt%20Tracker.md); the per-phase release checklists from the original plan are in the [Archive](../Archive/README.md).

## Where it is now

**One engine behind every surface.** `testosterone.yaml` → `CycleRunService` → `engine.run_plan()` → framework adapters → reporting and persistence. The CLI, the FastAPI backend and the CI wrappers all start runs this way; the Docker-based second execution stack and its `uqo run --config` contract were removed after 1.0.0. See [Architecture Overview](../Architecture/Architecture%20Overview.md).

| Area | State |
|------|-------|
| Frameworks | `pytest`, `behave`, `behavex`, plus `command` for any other runner with JUnit XML import ([Command Adapter and JUnit Import](../Specs%20&%20ADRs/Command%20Adapter%20and%20JUnit%20Import%20-%202026-09-25.md)) |
| CLI | `testo run` (Rich, `--stream`, `--ci` NDJSON), reports, diff/summary, config, doctor/clean/watch/init; exit codes `0`–`4` ([Command Reference](../CLI%20Commands/Command%20Reference.md)) |
| Storage | SQLite by default, PostgreSQL/MySQL through the repository layer ([Repository Pattern](../Specs%20&%20ADRs/Repository%20Pattern%20-%20Database-Agnostic%20Refactor.md)). Docker and MinIO are not required |
| UI | React + Vite + Tailwind frontend on the FastAPI `/api/v1` API; frontend types generated from the OpenAPI schema ([Phase 5 UI Redesign](../Specs%20&%20ADRs/Phase%205%20UI%20Redesign%20-%20Cycles-First%20Navigation.md)). The Streamlit prototype was removed |
| Analytics | Dashboard, run-to-run delta with per-stage and per-test changes ([Delta Comparison Policy](../Specs%20&%20ADRs/Delta%20Comparison%20Policy.md)), test pyramid, flaky test detection ([Open Source Features](../Specs%20&%20ADRs/Open%20Source%20Features%20-%202026-10-19.md)) |
| AI | Bring-your-own-key failure summaries ([Phase 4 BYOK and Failure Analysis](../Specs%20&%20ADRs/Phase%204%20BYOK%20and%20Failure%20Analysis.md)) |
| CI | GitHub Action and GitLab template wrapping `testo run --ci` ([CI-CD Pipeline Setup](../Processes%20&%20Guides/CI-CD%20Pipeline%20Setup.md)) |
| Demo | A Pages pipeline runs testosterone on itself and on the deliberately broken fake-api app, then publishes the React UI as a read-only snapshot ([GitLab Pages Demo](../Processes%20&%20Guides/GitLab%20Pages%20Demo.md)) |
| Distribution | Version 1.1.0 is cut (`pyproject.toml`, `CHANGELOG.md`) but not yet tagged or published; a GitHub Release publishes to PyPI (`testo-core`), GHCR (`testo-runner`) and, when configured, JFrog Artifactory ([Publishing to PyPI § Current state](../Processes%20&%20Guides/Publishing%20to%20PyPI.md#current-state)) |

## Next

- **Release v1.1.0.** Tag `v1.0.0` and `v1.1.0`, move `v1`, and create the GitHub Release.
- **Repo allow-list for the API.** `testo-api` binds `127.0.0.1` and can require `TESTO_API_TOKEN` on mutating requests; before it runs anywhere shared it also needs an allow-list of target repos.
- **Parallel stages.** Stages run sequentially; only BehaveX parallelizes internally. Opt-in parallel stages need isolated per-stage artifact trees and aggregated exit classification.
- **Concurrent run guard.** Today the only guard is the API's in-memory check that rejects a second run of the same cycle with 409 (`testo_api/cycle_execution_manager.py`). Two CLI runs of one cycle on one machine share `artifacts/<cycle>/` and overwrite each other, and nothing stops a CI run and a local run from hitting the same deployment at once. Every run enters through `CycleRunService.run()`, so a guard goes there, before `run_plan`, without a refactor. Three levels, smallest first:
  1. A lock file per cycle under `artifacts/<cycle>/`: a second run on the same machine exits `3` with a clear message.
  2. A per-environment lease in the database (an `environment:` key on the cycle, a row with an expiry): a second run against the same environment waits or fails. Only works across machines that share one database (e.g. Postgres), not per-machine SQLite.
  3. A real run queue. That is a central service and not worth it yet.
- **Smaller items** (signal-aware exit codes, reporter failure policy): see [Technical Debt Tracker](../Testing%20Workflows/Technical%20Debt%20Tracker.md).

## How it got here

The project started as "UQO", a Docker-and-Streamlit platform, and was delivered in four phases: packaging and a database-agnostic repository layer; drop-in CI wrappers; the React UI, delta engine and unified dashboard; then BYOK AI failure analysis. Each phase had a release checklist; those checklists and the dated plans and audits behind them are kept in the [Archive](../Archive/README.md).
