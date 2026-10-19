# Changelog

All notable changes to `testo-core` will be documented in this file.

This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added
- Flaky test detection: `testo flaky --cycle <name>` (`--window`, `--json`, `--fail-on-flaky`), `GET /api/v1/analytics/flaky` and a Flaky tests card on the cycle page (also in the Pages demo). A test is flaky when it both passed and failed and flipped at least twice in the cycle's last runs (`testo_core/services/flaky_service.py`)
- Docs site: the `docs/` vault built with MkDocs Material (`mkdocs.yml`, `scripts/mkdocs_hooks.py`, `[docs]` extra) and published at <https://taltal-beep.github.io/testosterone/docs/> by the Pages demo workflow. A new `docs_site` CI job builds it with `--strict`
- `docs/Getting Started.md`: from `pip install testo-core` to a regression in `testo summary` and the GitHub Action, with the same project in `examples/getting-started/`. A new `getting_started` CI job runs that example through the GitHub Action

### Changed
- `publish.yml` publishes straight to PyPI (the Test PyPI step is gone; the build, metadata and clean-install checks still run before the upload) and can be run by hand for an existing release tag
- Runner image: `Dockerfile.testo-runner` uses the floating `python:3.11-slim-bookworm` base (the `3.11.9` pin carried 9 fixable CRITICAL Debian CVEs that failed the v1.1.1 image scan), and `docker-publish.yml` scans and smoke-runs the image before pushing it and can be run by hand for an existing release tag
- Setup prompts install `testo-core` from PyPI instead of the GitHub zip
- `move-major-tag.yml` keeps the moving `v1` tag on the latest stable release (and can be run by hand for an existing tag)

## [1.1.1] - 2026-10-19

First release meant for PyPI (`pip install testo-core`).

### Added
- Open-source community files: `SECURITY.md` (private vulnerability reporting), `CODE_OF_CONDUCT.md` (Contributor Covenant 2.1), `CITATION.cff`, issue forms (`.github/ISSUE_TEMPLATE/*.yml`, blank issues off, links to Discussions and the security form) and `.github/dependabot.yml` (weekly grouped updates for pip, npm and GitHub Actions, `chore(deps)` commits with the `no-changelog` label; `commitlint.config.js` skips Dependabot's long commit bodies). `CONTRIBUTING.md` gains "Finding something to work on" and a note on the AI-agent files, and its Quickstart link is fixed
- README: animated walkthroughs of the web UI and of the CLI (`docs/assets/demo/`)
- `docs/Prompts & Snippets/Setup Prompts.md`: copy-paste prompts for an AI coding assistant to install Testosterone in another project, write its `testosterone.yaml`, run it in GitHub Actions or GitLab CI, open the web UI and troubleshoot. They install from GitHub until `testo-core` is on PyPI. Command Reference no longer calls `doctor`, `clean`, `watch` and `init` unimplemented

### Fixed
- `pip install testo-core` followed by `testo run` crashed with `ModuleNotFoundError: No module named 'sqlalchemy'`: run history is always saved (SQLite by default) but `sqlmodel` was only in the `[db]` extra. It is now a core dependency; `[db]` keeps the Postgres driver and `tomli-w`. A new `package` CI job (`scripts/package_smoke.sh`) installs the built wheel with no extras and runs a cycle, and the publish workflow runs the same check before uploading
- Compare showed "n/a" / "Unknown" for "Test time (sum)" and "Avg per test" on every run because nothing stored them. Both persistence backends now write `metrics_duration_ms` (sum of per-test Allure durations) and `avg_case_ms` (that sum over the test count, `null` with no tests), plus `test_time_ms` per stage. Runs saved earlier still show "n/a". A new contract test fails when `history/views.py` reads a run metadata key that persistence never writes

### Changed
- Package metadata for PyPI: description, MIT license expression, author, keywords, classifiers and project links (homepage, docs, demo, issues, changelog). The README shown on PyPI has its relative images and links rewritten to GitHub URLs at build time (`hatch-fancy-pypi-readme`), and the sdist now carries only the Python package, its tests and the top-level docs (about 260 KB instead of 3.5 MB)
- `publish.yml` fails before uploading when the release tag does not match `pyproject.toml`'s version, and runs `twine check --strict`
- README: PyPI badge and a `pip install testo-core` quickstart
- Pages demo: the read-only notice is now a dismissible alert with a × button, remembered across reloads, and a "Read-only demo" badge in the header reopens it
- Detailed architecture diagram (`docs/assets/testosterone-architecture-detailed-{dark,light}.png`, drawn by `scripts/render_architecture_diagram.js`) showing `CycleRunService`, the `history/` read side and the repository; it replaces the six-box picture in the README and leads `docs/Architecture/System Diagram.md`
- Docs vault: the architecture diagram now has its own note (`docs/Architecture/System Diagram.md`) so it shows in Obsidian and the GitHub wiki, not only the README; Architecture Overview's text sketch is a Mermaid flowchart. New decision note for the vault and wiki sync, the second wave of the 2026-10-07 interview fixes, and this repo's workflows in CI-CD Pipeline Setup. `scripts/docs_vault.py lint --base` accepts a second edit to a note already dated today

## [1.1.0] - 2026-10-07

One engine behind every surface. The Docker-based second execution stack, the Streamlit UI, MinIO and the `uqo` command are gone; the CLI, the API and CI all run cycles through `CycleRunService`. The release also adds an API security model, a type-checked API, same-cycle run comparison and a read-only demo on GitHub Pages. Upgrading from 1.0: see "Migrating from v1.0" in the README.

### Added
- Docs vault rules: `docs/CLAUDE.md` (schema), `docs/log.md`, frontmatter on every note, and `scripts/docs_vault.py lint` (frontmatter, broken links, wikilinks, orphans, `updated` date on edited notes) as a `docs_vault` CI job and a contract test. `.github/workflows/wiki-sync.yml` regenerates the GitHub wiki from `docs/` on every push to `main` that touches the vault. The root `CLAUDE.md` gains the six second-brain rules, and `docs/Specs & ADRs/` gains decision notes for the 2026-10-06 architecture consolidation and the 2026-10-07 interview fixes
- Pages demo on GitHub and GitLab: `.github/workflows/pages-demo.yml` (GitHub Pages, `https://<owner>.github.io/<repo>/`) and `.gitlab-ci.yml` (GitLab Pages) each run testosterone's own suite (`self-test` cycle) and the deliberately broken [fake-api](https://github.com/taltal-beep/fake-api) app (`fake-api` cycle), then publishes the React UI as a read-only snapshot of those runs (`scripts/export_static_site.py` freezes the API's own responses; `frontend/src/lib/static-backend.ts` serves them to the unchanged pages). Run history is cached between pipelines. `.github/workflows/mirror-to-gitlab.yml` mirrors `main` to GitLab, inert until configured
- `frontend` CI job in `ci.yml`: runs the React dashboard's typecheck, vitest suite and production build on every PR (the frontend had no CI coverage)
- `POST /api/v1/adhoc-executions`: run one framework (`pytest`, `behave`, `behavex`, `command`) against a repo without defining a cycle. It runs as a one-stage `adhoc` cycle through `CycleRunService`, with status and SSE events under `/api/v1/cycle-executions/{id}`
- Quick Run page in the React frontend (`/quick-run`, under Advanced) built on that endpoint; it replaces the Legacy Execution page
- Engine run records now store failure evidence for failed runs (failing cases, first traceback, log tail, timeout flag; all redacted) for the AI failure summary, and CI provenance (`ci_provider`, `ci_pipeline_id`, `ci_job_id`, `ci_commit_sha`, `ci_ref_name`) when run in CI
- After every cycle run, test KPIs are pushed to InfluxDB and/or a Prometheus Pushgateway when `INFLUXDB_*` / `PROMETHEUS_PUSHGATEWAY_URL` are set

### Changed
- Loose `testo_core` root modules moved into their subpackages (no compatibility shims): `db.py` → `repository/db.py`, `db_config.py` → `repository/db_config.py`, `report_generator.py` / `metrics.py` / `metrics_extractor.py` / `integrations.py` → `reporting/`, `triggers.py` → `config/triggers.py`. Only the cross-cutting `paths.py` stays at the root
- CI type-checks `testo_api` as well as `testo_core` (`mypy testo_core testo_api`, blocking). The AI config routes validate their status payload through Pydantic, and report diffs type the change kind as a `Literal`
- Pages demo explains itself: the banner says it shows testosterone's self-test and fake-api (whose red is deliberate), only cycles that ran are exported and their Run buttons are disabled with the local `testo run` command, the read-only message no longer names GitLab, and with an optional `ANTHROPIC_API_KEY` the export freezes an AI failure summary per failed run (otherwise the card says summaries are generated live)
- API access control: CORS now allows only the Vite dev/preview servers by default (`TESTO_CORS_ORIGINS`; credentials only for an explicit origin list, never with `*`) and mutating requests from other browser origins get `403`, optional `TESTO_API_TOKEN` requires a bearer token on mutating requests (the frontend sends `VITE_TESTO_API_TOKEN`), and `testo-api` warns when bound beyond loopback without a token. `ARCHITECTURE.md` gains "Security model" and "Trade-offs and known limits" sections
- Running a cycle (trigger gate, engine, reporters, native report snapshot, report archive, trigger snapshot) now lives in one application service, `testo_core/services/cycle_run.py` (`CycleRunService`). `testo run` and `POST /api/v1/cycles/{cycle}/executions` both call it, so the API no longer imports private helpers from `testo_core/cli/runner.py`
- API cycle executions now save the trigger snapshot after a successful triggered run, as `testo run` already did; before, a cycle with `trigger:` started from the dashboard never advanced its snapshot
- Frontend API types are now generated from FastAPI's OpenAPI schema (`frontend/openapi.json` → `frontend/src/lib/api-schema.ts`) instead of being hand-written; CI's `frontend` job runs `tsc` and fails on a stale schema or generated file
- `ARCHITECTURE.md` and `README.md` now describe the single execution engine (config → `CycleRunService` → engine → framework adapters → reporting/persistence) with a system diagram, layer table and the typed Pydantic-to-React contract
- `testo_core/run_history.py` is replaced by the `testo_core/history/` package: `views` (typed run views), `read_model` (queries), `report_links`, `snapshots` and `maintenance`. All of it goes through the run repository, which gains `merge_run_metadata()`; `STATIC_HISTORY_ROOT` moves to `testo_core.paths`
- GitHub Action and GitLab template now run `testo run --ci` (they called `uqo run --config … --ghost`, which v1.0's `uqo` alias no longer accepted). Action inputs are `config-path`, `cycle`, `ci-mode`, `persist`, `python-version`; `ghost-mode`, `stream-json`, `runner-image`, `runner-prebuilt` and the `run_id` output are gone. GitLab variables are now `TESTO_CONFIG_PATH`, `TESTO_CYCLE`, `TESTO_PERSIST`
- The React UI names runs by cycle and start time (`fake-api · Oct 7 03:21`) with the short run id as secondary text, on the Dashboard, Runs, Run detail and Compare pages; `GET /api/v1/dashboard/runs/recent` items now include `cycle`. Compare shows Reliability/Performance as tables with coloured deltas and state badges instead of raw `key=value` strings, and its run pickers are grouped and filterable by cycle
- CI's `format` job now blocks on `mypy testo_core` and `ruff format --check` (both were advisory); the codebase was reformatted once with `ruff format`, and a `ruff-format` pre-commit hook was added
- A stage's `workers` now does what it says, or says it doesn't: pytest stages get `-n <workers>` when pytest-xdist is installed for the `pytest` on PATH (otherwise one warning and a serial run), `workers:` on a behave or command stage logs a warning, and the API/UI only show workers for frameworks that use them
- CI's `test` job now enforces coverage (it ran `--no-cov`): `pytest.ini` measures `testo_core` and `testo_api` with branch coverage and fails below 65% (was 50%, `testo_core` only), and `coverage.xml` is uploaded as an artifact. `nightly-external`, `release-gate` and `pr-heavy` pass `--no-cov`: their few marker-selected tests could never meet that project-wide gate, which is why `nightly-external` failed every night. `nightly-external` also reads `TESTO_E2E_*` secrets instead of `UQO_E2E_*` and skips with a notice when none are set
- Renamed the remaining UQO names in code and UI to Testosterone: tab title, OpenAPI title (`Testosterone API`), and env vars `UQO_*` → `TESTO_*` (`TESTO_SHARED_ALLURE_RESULTS_DIR`, `TESTO_ARTIFACTS_ROOT`, `TESTO_LAST_TEST_TYPE`, `TESTO_RUN_ID`, `TESTO_E2E_*`, runner image build args) with no aliases for the old names. Defaults changed too: `PROMETHEUS_JOB_NAME` is `testo`, metrics are `testo_*` / `testo_test_run`, the default SQLite history file is `testo_history.db`, and the compose Postgres is `testo-postgres` / `testo_admin` / `testo_history`

### Removed
- MinIO support: the `s3` readiness check (`/api/v1/health/ready` reported "degraded" without MinIO credentials), `testo_core/s3_client.py`, `history/s3_snapshots.py` (pre-v1.1 snapshot reads), the pre-v1.1 record shape in `history/views.py`, the `boto3` dependency, and the `minio`, `minio-init`, `allure-sync` and `allure` compose services. `docker-compose.yml` now only provides Postgres
- The second, Docker-based execution stack: `HeadlessEngineService`, `testo_core/runners.py`, `command_builders.py`, `multi_run.py`, `event_drain.py`, `config_loader.py`, `audit_service.py`, `ghost_policy.py`, `result_management.py`, and the pluggy `orchestrator.py` / `specs.py` / `plugins_builtin.py`. Every run now goes through the cycle engine
- The v1.0 `uqo run --config <runs.yaml>` contract (`--ghost`, `--no-ghost`, `--json`, `--stream-json`, summary JSON); use `testo run --cycle <name> --ci`
- The `uqo` console script (`testo_core/cli/deprecated.py`) and the frontend's legacy route redirects (`/history`, `/runner`, `/execution`, `/advanced/execution`); use `testo` and the current routes. Unknown frontend paths now show a not-found page
- `POST /api/v1/executions`, `GET /api/v1/executions/{id}` and `GET /api/v1/executions/{id}/events`; use `POST /api/v1/adhoc-executions` or `POST /api/v1/cycles/{cycle}/executions`
- The Streamlit UI (`testo_ui/`, `testo-ui` script, `ui` extra), as scheduled in 1.0.0
- The `docker` extra and the `pluggy` runtime dependency
- Run-history writer functions in `run_history.py` (`create_run`, `record_completed_run`, MinIO uploads), the unused `compare_latest_two()` and the `db_path` arguments on history queries
- Generated run output that was committed by mistake (`artifacts/allure-report*`, `artifacts/allure-results-archive/`, `artifacts/metrics.json`); these paths are now ignored
- `testo_core/reporting/allure_delta_transform.py`, `allure_history_serve.py` and `allure_summary_widgets.py`: unreferenced modules that could not be imported (they depended on functions no longer in `services/report_archive_diff.py`)
- Dead code and test-failure injection: `.streamlit/`, `drop_in_hooks/`, `requirements.txt`, `deploy/nginx/`, `examples/gitlab/`, the unused GitLab tier templates, `sample_target_repo/random_fail.py` and the `sample-all-frameworks-stochastic` cycle, and the `UQO_FLAKY_DEMO` / `SANDBOX_API_FLAKY_P` switches in testosterone's own suite. `testo_core/sandbox_api.py` (a uvicorn launcher for the sample mock API, used only by one black-box test on a fixed port) is gone with that test, so it no longer ships in the wheel

### Fixed
- Dashboard and Compare badges say "1 improvement" / "1 regression" instead of "1 improvements"
- `release-gate.yml` reads the `TESTO_E2E_*` repository secrets, matching the nightly job, instead of the old `UQO_E2E_*` names
- Errors in I/O and reporting paths are no longer swallowed silently: `except Exception: pass` sites in `testo_core/` and `testo_api/` now catch the specific exceptions they expect and log with the module logger, and the deliberate catch-alls (orchestrator, reporter factory, API routes) log with a traceback. A failed BehaveX HTML report now sets the stage's `error` and is written to `run.log`, and a failed Git trigger evaluation logs a warning and says so in the trigger `reason` (exit codes unchanged)
- The frontend's top nav overflowed the page at phone width. Below 640px the nav links and the Advanced menu now collapse into a menu button (`aria-expanded`, closes on navigation and Escape), and page gutters shrink to 16px; no page of the demo scrolls sideways at 390px any more
- Dashboard trends and "Compare latest two" (dashboard and Runs page) compared the latest run with whatever ran before it, even another cycle; the baseline is now the previous run of the same cycle, and the dashboard names it. A cycle whose stage crashed without producing results no longer reports the other stages' pass rate (often 100%) as its health
- The API's execution registry kept every execution in memory forever and each SSE viewer held a worker thread while polling `events.ndjson` every 0.2 s. Finished executions beyond `TESTO_MAX_FINISHED_EXECUTIONS` (default 200) are now evicted (their status/events endpoints return 404 pointing to `/api/v1/runs`); the SSE tail is an async generator with poll backoff (0.1 s to 2 s) that closes right after the run's own last event (not the next run's, which shares `events.ndjson`) or when the client disconnects, and no longer drops a line caught mid-write
- The test pyramid (`testo report pyramid`, `/api/v1/runs/{id}/pyramid`) bucketed a run by the tiers in the *current* `testosterone.yaml`, so renaming a stage re-counted old runs as "unit". Run records now store each stage's `tier`; only older records without one fall back to the YAML
- A `command` stage's `junit_xml:` reports were never imported by `testo run` or the API, so the stage showed 0 tests and PASS. Cycle resolution and the `--workers` override rebuilt each stage without its `junit_xml` and `tier`; they now copy the stage with `dataclasses.replace`
- Pytest stages ignored the target repo's own pytest config (`pythonpath`, markers) when the target sat inside another pytest project, such as a repo cloned into the testosterone checkout in CI, so tests failed to import the target's code. The adapter passed `--alluredir <path>` as two tokens, and pytest counted the results path when choosing its rootdir; it now passes `--alluredir=<path>`
- Compare's test-level changes were always empty for two runs of the same cycle, and a run's artifact download returned whichever run of that cycle came last. Run records pointed `snapshot_dir` at the shared `artifacts/<cycle>/` tree, which every run overwrites; each run now keeps its own copy at `static/history/<run_id>/artifacts/`
- Frontend typecheck errors surfaced by the generated types: `/health/ready` is typed `"ready" | "degraded"` as the API returns, and `StatusPill` handles a `null` status
- `mypy testo_core` reports 0 errors, down from 59: reporters take a typed Rich `Console`, `testo report` narrows its optional open path before use, and the persistence, repository and CLI UI code is fully annotated
- `equipment: behavex`: every BehaveX stage failed at startup with `OSError: AF_UNIX path too long`, because BehaveX points `TEMP` at its output folder and the multiprocessing socket landed there; the adapter now pins `TMPDIR` to the system temp dir
- API errors surfaced in the UI as `API error <status>`; the client now shows the message the API returned, and the Run detail page reports a failed AI-summary request instead of swallowing it
- Run detail, dashboard and compare showed a wall duration of 0 ms for every cycle run; engine-sourced records store `duration_s`, which the history view now falls back to

---

## [1.0.0] - 2026-09-27

First public release. Published to PyPI (`testo-core`), GHCR (`testo-runner`), and JFrog Artifactory.

### Deprecated
- `testo-ui` / Streamlit interface: prints a deprecation notice on stderr and is scheduled for removal in v1.1. The React frontend (`frontend/`) is the official UI.
- `uqo` CLI alias: continues to forward to `testo`; removal in a future release.

### Added
- `.pre-commit-config.yaml`: local `ruff`, changelog-format, and whitespace/YAML/TOML hooks (`pre-commit install` to enable)
- `mypy` type-check tooling: `[tool.mypy]` config in `pyproject.toml`, advisory step in `ci.yml`'s `format` job
- Extended `[tool.ruff.lint]` selection (added `UP`, `B`) and made `ruff check` blocking in `ci.yml` now that the tree is clean
- `changelog_required` CI gate in `ci.yml`: fails PRs with non-doc changes that don't touch `CHANGELOG.md` (escape hatch: `no-changelog` label)
- `commitlint` CI check (`.github/workflows/commitlint.yml`, `commitlint.config.js`) enforcing Conventional Commits on PR commit messages
- `changelog-on-main.yml`: AI-drafted `CHANGELOG.md [Unreleased]` entries on push to `main`, gated by `scripts/check_changelog_format.py` — see `docs/changelog_automation_policy.md` for the review-step tradeoff and required secrets/branch-protection setup
- `CONTRIBUTING.md`, `.github/PULL_REQUEST_TEMPLATE.md`, `.github/ISSUE_TEMPLATE/` (bug report, feature request), and `CODEOWNERS`
- Root-level `CLAUDE.md` pointing any directly-invoked AI agent at `docs/Index.md` and the Agent Context Guide
- Persistence module with `PersistenceBackend` protocol, JSON and DB backends
- Single-sourced `EngineExitCode` across modern and legacy execution stacks
- Contract tests asserting exit code consistency between stacks
- Execution stack boundary documentation in Architecture Overview
- `_SENSITIVE_KEY_PATTERN` in `redaction.py` to detect sensitive mapping keys (#35)
- `_redacted_context_text()` in `failure_context_builder.py` for structured metadata redaction (#35)
- Allure failure context wiring in `record_completed_run()` for run recording (#35)
- `equipment: command`: run any test runner (Jest, Playwright, Maestro, `go test`, ...) as a stage. `args` is the full argv
- Stage key `junit_xml` (glob or list, relative to `target_repo`): JUnit XML written by the stage is converted into Allure results after it exits, so non-Allure runners count in summaries, health % and every reporter (`testo_core/reporting/junit_import.py`)
- `artifactory-publish.yml`: mirrors the release to JFrog Artifactory (PyPI + Docker repos), inert until `ARTIFACTORY_URL` is set — see `docs/Processes & Guides/Publishing to Artifactory.md`

### Changed
- `--no-persist` / `--persist` CLI flags with clarified semantics
- `classify_exit_code` consolidated into `engine/exit_codes.py`
- Literal exit code constants in CLI replaced with `EngineExitCode` enum

### Fixed
- Sprint 2 release gate execution across all 4 phases
- Contract test assertion mismatch (`--plan` vs `--cycle`)
- Allure CLI unit test mock for `resolve_allure_command`
- `publish.yml`: post-publish verification installed `testo-core==v1.0.0` from the raw git tag, which is not a valid version specifier; the leading `v` is now stripped
- `docker-publish.yml`: Trivy scan and verify steps referenced an image tag that never existed (`docker/metadata-action` strips the `v`); both now use the resolved metadata version
- `docker-publish.yml`: the `latest` tag was gated on `is_default_branch`, which is never true for a release event, so `latest` would never have been published
- `.gitattributes`: GitHub reported the repository as HTML because the generated 3.2 MB `artifacts/allure-report/index.html` outweighed all authored Python and TypeScript; generated and vendored paths are now excluded from language statistics
- `Dockerfile.testo-runner`: the image ran as root, which fails the release workflow's blocking Trivy config scan (DS002, HIGH); it now runs as an unprivileged `testo` user, and the entrypoint is `testo` instead of the deprecated `uqo` alias

---

## [0.1.0] — Phase 1–4 Feature Complete

### Phase 4: BYOK AI Failure Summaries

*AI-powered test failure analysis with bring-your-own-key provider support.*

#### Added
- `testo_core/services/failure_analysis_service.py` — context-aware AI failure summary generation
- `PUT /api/v1/ai/config` — runtime AI provider/model configuration (memory-only key storage)
- `GET /api/v1/runs/{run_id}/ai-summary` — cached AI summary retrieval
- `POST /api/v1/runs/{run_id}/ai-summary:generate` — on-demand summary generation for failed runs
- `GET /api/v1/ai/config/status` — non-secret AI configuration status endpoint
- React AI Settings page (`/settings/ai`) — provider config, key management, model selection
- AI summary display on Run Detail page (`/runs/:runId`)
- AI summary caching — generate once, retrieve cached on refresh
- AI failure context capture tests
- Passing-run AI summary skip regression test

#### Security
- Raw API keys never returned by backend responses
- Runtime key input memory-only by default (not persisted to DB/files)
- Token-like values redacted from internal error surfaces before transport
- AI integration explicit opt-in (`enabled=false` by default)

#### Fixed
- AI summary refresh data loss on forced refresh failure (#32)
- AI failure summary and context builder regression coverage (#33, #34)

---

### Phase 3: Unified Dashboard, Delta Engine, Frontend Migration

*React frontend, run comparison analytics, and unified dashboard.*

#### Added
- FastAPI backend (`testo_api/`) — thin adapter over `HeadlessEngineService`
- React frontend (`frontend/`) — Vite + React + Tailwind dashboard
- Dashboard overview page (`/`) — KPI cards, trend badges, drill-down links
- Delta comparison engine (`testo_core/services/delta_service.py`) — regression/improvement classification
- Compare page (`/compare`) — run selection and delta visualization
- SSE client (`frontend/src/lib/sse-client.ts`) — real-time execution log streaming
- `GET /api/v1/dashboard/overview` — unified dashboard payload endpoint
- `GET /api/v1/analytics/delta` — core-owned run delta comparison endpoint
- `POST /api/v1/executions` — create run execution job endpoint
- `GET /api/v1/executions/{id}/events` — SSE stream for log/result/summary events
- Health probes: `GET /api/v1/health/live`, `GET /api/v1/health/ready`
- Degraded-data behavior (n/a display, degraded banner, missing report links)
- Report DB archives, diff CLI, Allure history, hybrid cycles
- Report archive extraction path hardening (#28, #30)
- Report archive diff regression tests (#27, #29)
- Execution accepted-status regression test (#26)
- Frontend unit tests (Vitest) and E2E test harness

#### Fixed
- Race condition in 202 Accepted response status for `/executions`

---

### Phase 2: CI Integrations, Ghost Mode, Runner Image

*CI wrappers, headless ghost execution, and prebuilt Docker runner.*

#### Added
- GitHub Action wrapper (`ariel-evn/uqo-action@v1`) with typed inputs/outputs
- GitLab CI template (`ci/gitlab/testo.gitlab-ci.yml`)
- Ghost mode — CI auto-detection for GitHub, GitLab, Buildkite, CircleCI, Jenkins, Azure Pipelines
- `--ghost` / `--no-ghost` / `--ci` CLI flags with precedence rules
- `Dockerfile.testo-runner` — prebuilt runner image for CI execution
- Configurable runner image path (`UQO_RUNNER_IMAGE`)
- NDJSON event streaming (`--stream-json`) for CI log consumption
- Ghost summary and NDJSON contract tests
- CI provenance unit tests
- GitHub Action and GitLab wrapper contract tests

#### Changed
- Renamed `uqo`-prefixed CI files to `testo`-prefixed

---

### Phase 1: Foundation

*Core engine, CLI, packaging, database adapters, Allure reporting.*

#### Added
- `testo_core/` — config-driven orchestration engine reading `testosterone.yaml`
- `testo` CLI entrypoint (via Typer) with `run`, `report`, `cycles`, `config` subcommands
- `uqo` legacy CLI alias (deprecated)
- Framework adapters: `PytestAdapter`, `BehaveAdapter`, `BehaveXAdapter`
- Repository pattern (`testo_core/repository/`) — SQLite default, Postgres/MySQL optional
- Allure reporting pipeline with per-framework isolation and unified reports
- MinIO S3 artifact storage (`testo_core/s3_client.py`)
- Docker-based ephemeral test execution (`testo_core/runners.py`)
- Dockerless local fallback when Docker is unavailable
- Streamlit UI (`testo_ui/`) for interactive execution and history
- Pluggy-based plugin system for drop-in runner extensions
- Shared headless engine service (`testo_core/services/headless_engine.py`)
- Hatchling-based packaging (`pyproject.toml`) with extras: `ui`, `api`, `db`, `docker`, `metrics`, `dev`
- Stable exit codes: 0 (success), 1 (test failure), 2 (invalid input), 3 (infra failure), 4 (internal error)
- Crash recovery: orphaned `RUNNING` rows auto-marked `FAILED` on startup
- Container timeout safety net (`UQO_CONTAINER_TIMEOUT_S`)
- Docker Compose infrastructure: Postgres, MinIO, Allure static host, Allure sync

#### Fixed
- Docker runner path mapping
- Mock API and built-in Pluggy hooks restoration
- Multi-run batch locking until complete
- Multi-run polling active until batch ends

---

[Unreleased]: https://github.com/taltal-beep/testosterone/compare/v1.1.0...HEAD
[1.1.0]: https://github.com/taltal-beep/testosterone/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/taltal-beep/testosterone/compare/v0.1.0...v1.0.0
[0.1.0]: https://github.com/taltal-beep/testosterone/releases/tag/v0.1.0
