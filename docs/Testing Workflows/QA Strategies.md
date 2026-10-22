---
type: guide
status: current
created: 2026-06-25
updated: 2026-10-22
---

# QA Strategies

How Testo **triggers**, **executes**, and **logs** test suites today — from YAML cycles through artifacts, reporters, and optional database archives.

Related: [Architecture Overview](../Architecture/Architecture%20Overview.md), [Command Reference](../CLI%20Commands/Command%20Reference.md), [Index](../Index.md).

---

## Mental model

A **cycle** (plan) is an ordered list of **stages**. Each stage names an **equipment** framework (`pytest`, `behave`, `behavex`, `playwright`, `command`, `junit`; `behave` and `behavex` come with the `bdd` extra), a **target_repo**, and CLI **args**. The engine runs stages **one after another** on the host unless a trigger skips the whole cycle.

```mermaid
flowchart LR
  YAML[testosterone.yaml] --> Load[discover_and_load]
  Load --> Trigger{trigger + force?}
  Trigger -->|skip| Rest[exit 0 resting]
  Trigger -->|run| Engine[run_plan]
  Engine --> S1[stage 1 subprocess]
  S1 --> S2[stage 2 subprocess]
  S2 --> Rep[reporters]
  Rep --> Arc[optional DB archive]
```

---

## Defining work in `testosterone.yaml`

Example cycle (from repo `testosterone.yaml`):

```yaml
cycles:
  sample-pytests:
    description: Pytest suite for the sample target repo
    tags: [smoke]
    stages:
      - name: pytest-sample
        equipment: pytest
        target_repo: sample_target_repo
        args: ["-q", "tests"]
```

**Multi-framework cycle:** `sample-all-frameworks` chains pytest → native Behave → BehaveX on `sample_target_repo`.

**Any other runner (`equipment: command`):** `args` is the whole command. Point `junit_xml` at the JUnit report it writes, and the results show up like a pytest stage's:

```yaml
      - name: app-unit
        equipment: command
        target_repo: ClientApp
        args: ["npx", "jest", "--ci", "--reporters=default", "--reporters=jest-junit"]
        junit_xml: junit.xml            # string or list of globs, relative to target_repo
        tier: unit
      - name: app-e2e
        equipment: command
        target_repo: ClientApp
        args: ["npx", "playwright", "test"]
        junit_xml: ["test-results/*.xml"]
        tier: e2e
```

Validation: a `command` stage needs `args`, and `junit_xml` patterns must be relative and stay inside `target_repo`. `junit_xml` also works on pytest/Behave stages.

**Quarantine** (top-level and/or per cycle): failures of the listed tests don't fail their stage. The tests still run and still show as failed in results, reports, Compare and the PR comment.

```yaml
quarantine:                       # every cycle
  - test_upload_retries           # fnmatch glob on the test's name or full name
cycles:
  fake-api:
    quarantine:                   # added to the top-level list for this cycle
      - test: "test_flaky_route*"
        reason: races the slow endpoint
        owner: "@taltal"
```

A stage that exits `1` passes when every failed test matches a rule; one unquarantined failure, or any other exit code (timeout, crash, collection error), still fails it. The same goes for `equipment: junit` stages, whose exit code comes from the recorded results. `testo flaky` marks quarantined tests and prints a snippet for the rest. See [Flaky Test Quarantine - 2026-10-22](../Specs%20&%20ADRs/Flaky%20Test%20Quarantine%20-%202026-10-22.md).

**Results an earlier step wrote (`equipment: junit`):** no command runs; the stage records the JUnit XML its `junit_xml` globs match (files of any age) and fails when a test failed or nothing matched. `testo ingest` builds exactly this stage on the fly ([Command Reference § testo ingest](../CLI%20Commands/Command%20Reference.md#testo-ingest)).

```yaml
      - name: go-tests
        equipment: junit
        junit_xml: ["reports/go-*.xml"]   # required for junit
```

**Post-run reporters** (global `reporters:` block) run after all stages complete — Allure HTML, Extent dashboard, ReportPortal upload, TestBeats Slack/Teams preview.

Validate before running:

```bash
testo config validate
testo cycles show sample-pytests
```

---

## How runs are triggered

### 1. Manual CLI

Primary path:

```bash
testo run --cycle sample-pytests
```

Run every cycle (respecting each cycle’s trigger unless `--force`):

```bash
testo run --cycle all
testo run --cycle all --tag smoke
```

### 2. Selective triggers

Cycles may define a `trigger:` with glob `paths` (and optional Git `since_ref`). Evaluation lives in `testo_core/config/triggers.py`:

| Mode | Behavior |
|------|----------|
| **Git** | If config anchor is inside a Git repo, diff against `since_ref` or default ref; match changed files to patterns |
| **Snapshot** | Fallback: compare file mtimes/sizes to `.testo-trigger-snapshots/` under artifacts |

If no stimulus and not `--force`:

- Interactive: message that cycle is **resting** (skipped).
- Exit code **0** (not a failure).
- `--dry-run` shows `would be skipped (no trigger stimulus)`.

After a successful snapshot-triggered run, state is persisted via `persist_trigger_snapshot()`.

### 3. Watch mode (local TDD)

```bash
testo watch --cycle sample-pytests --path sample_target_repo
```

Debounced filesystem events call `testo run` repeatedly; useful for fast feedback loops.

### 4. CI/automation

| Mechanism | Notes |
|-----------|--------|
| `testo run --ci` | NDJSON on stdout for parsers |
| `testo run --no-persist` / `--no-report-db` | Lighter CI without DB |
| GitHub Action / GitLab template | `integrations/github-action/`, `ci/gitlab/testo.gitlab-ci.yml` — both wrap `testo run --ci` |
| `testo-api` | `POST /cycles/{cycle}/executions` or `POST /adhoc-executions` + SSE event stream |

---

## How suites are executed

1. **Resolve config** — `discover_and_load`, `resolve_stages_for_plan` (env-specific stage filtering if configured).
2. **Pick renderer** — `BufferedRenderer` (default), `StreamRenderer` (`--stream`), or `CIRenderer` (`--ci`).
3. **`run_plan()`** (`testo_core/engine/orchestrator.py`):
   - Creates `artifacts/<cycle>/`.
   - Opens `events.ndjson` recorder.
   - For each stage: `run_stage()` in `executor.py`.
4. **`run_stage()`**:
   - Framework adapter builds `argv` (e.g. `pytest` with Allure plugin paths).
   - `subprocess.Popen` in `target_repo` cwd.
   - Merges `extra_env`; sets `TESTO_SHARED_ALLURE_RESULTS_DIR`, `TESTO_ARTIFACTS_ROOT`.
   - Streams stdout/stderr into `run.log` via `LogBuffer`.
   - Enforces `timeout_s` (SIGTERM → SIGKILL).
5. **`--fail-fast`** — aborts remaining stages (and `run --cycle all` aborts remaining cycles).
6. **Exit classification** — `classify_exit_code()` maps stage return codes to `EngineExitCode`.

There is no other execution path: the API (cycle and ad-hoc executions) and the CI wrappers all reach `run_plan()` through `CycleRunService`. The Docker-based `runners.py` stack was removed in v1.1.

---

## How results are logged and surfaced

### On disk (always)

| Artifact | Location | Purpose |
|----------|----------|---------|
| Stage log | `artifacts/<cycle>/<stage>/run.log` | Full subprocess output |
| Allure raw | `…/allure-results/<framework>/` | `*-result.json` per test |
| Plan events | `artifacts/<cycle>/events.ndjson` | Machine-readable timeline |
| Plan summary | `artifacts/<cycle>/plan_result.json` | Aggregated outcome |

The collector (`testo_core/reporting/collector.py`) scans this tree; `testo report` uses the latest cycle when `--cycle` is omitted.

### Reporters (after run)

If `reporters:` is set or `--reporter` is passed, `run_configured_reporters()` runs:

- **allure** → `./reports/allure` (typical)
- **extent** → HTML dashboard under configured `output_dir`
- **reportportal** → REST launch import
- **testbeats** → webhook or preview JSON under `artifacts/reports/testbeats/`

### Official documentation

| Technology | Reference |
|------------|-----------|
| Allure Report | https://docs.qameta.io/allure/ |
| Allure Report (project site) | https://allurereport.org/docs/ |
| ReportPortal | https://reportportal.io/docs/ |
| ReportPortal agents | https://reportportal.io/docs/log-data-in-reportportal/test-framework-integration/ |

### Database archive (optional)

With `testo-core[db]` and `database.url` (or `DATABASE_URL`):

- Post-run zip of cycle artifacts + metrics row.
- `testo report list` / `testo report open --id …` / `testo diff` / `testo report compare`.

Use `--no-report-db` to skip; `--async-report-db` for background archive with join timeout (ignored under `--ci`).

### Unified Allure dashboard

```bash
testo report --cycle sample-pytests
```

Runs `allure generate` (with optional **trend** history from prior archives), serves local HTTP, opens browser by default.

**Native framework reports** (BehaveX HTML, etc.):

```bash
testo report native
```

---

## CI and streaming output

**`--ci` on `testo run`:**

- No Rich panels; NDJSON lines suitable for log aggregators.
- Same exit code contract as interactive mode.

**`--stream`:**

- Live stdout chunks per stage while subprocess runs.

**Dry-run in CI:**

```bash
testo run --cycle sample-pytests --dry-run --ci
```

Emits `dry_run_stage` objects with `argv`, `cwd`, `framework` without executing.

**CI:** use `testo run --ci` so the CLI stays non-interactive (NDJSON on stdout, `plan_finished` last). Run records written in CI carry `ci_provider`, `ci_pipeline_id`, `ci_job_id`, `ci_commit_sha` and `ci_ref_name` (detected from the CI environment by `DbBackend`). Wrappers: [CI-CD Pipeline Setup](../Processes%20&%20Guides/CI-CD%20Pipeline%20Setup.md).

---

## Recommended workflows

### Local smoke before commit

```bash
testo doctor
testo run --cycle sample-pytests
testo report --cycle sample-pytests --no-open
```

### PR gate (tagged cycles only)

```bash
testo run --cycle all --tag smoke --fail-fast --ci
```

Parse final `plan_finished` NDJSON line; fail pipeline on `exit_code != 0`.

### Nightly full matrix

```bash
testo run --cycle sample-all-frameworks
```

Or split cycles in CI jobs per `cycles:` key.

### Investigate regressions

```bash
testo report list
testo report compare --cycle sample-pytests
# or
testo diff <older-uuid> <newer-uuid>
```

### Clean slate

```bash
testo clean --yes
```

---

## Sample target repo

`sample_target_repo/` is the bundled **sandbox** under test:

- `tests/` — pytest + Allure
- `features/` — Behave / BehaveX BDD

Cycles in `testosterone.yaml` point `target_repo: sample_target_repo` for demos and docs. Replace with your application repo path in real projects.

---

## Testing the orchestrator itself

The repo’s own QA lives under `tests/`. The **modern `testo run` execution path** (CLI → runner → orchestrator → executor) has a dedicated suite aligned with [Deep Dive - Execution Logic](../Architecture/Deep%20Dive%20-%20Execution%20Logic.md) and [Troubleshooting and Error Codes](../CLI%20Commands/Troubleshooting%20and%20Error%20Codes.md).

### Layout

| Path | Focus |
|------|--------|
| `tests/fixtures/engine/` | YAML builders (`write_minimal_config`, `write_multi_stage_config`, `write_cycles_config`), adapters (`EchoAdapter`, `HangAdapter`, `MissingBinaryAdapter`), `NoopRenderer`, `parse_ndjson`, `assert_ndjson_events`, `read_artifact_events`, `scripts/echo.py` + `scripts/hang.py` |
| `tests/unit/testo_core/engine/` | `classify_exit_code` (`test_exit_codes.py`), `LogBuffer` (`test_log_buffer.py`), `run_stage` (`test_executor.py`), `run_plan` fail-fast (`test_orchestrator.py`) + lifecycle/state (`test_orchestrator_lifecycle.py`) |
| `tests/unit/testo_core/cli/` | Exit codes (`test_run_exit_codes.py`), archive (`test_run_archive.py`), flags (`test_run_flags.py`), CI NDJSON (`test_run_ci_ndjson.py`), config discovery (`test_config_discovery.py`), smokes (`test_cli_commands_smoke.py`) |
| `tests/integration/testo_core/engine/` | Real subprocess smoke via `echo.py` (no Docker) — `test_subprocess_smoke.py` |
| `tests/contract/testo_core/` | Formal `EngineExitCode` 0–4 contract (`test_exit_code_contract.py`) |
| `tests/unit/testo_core/` | Cycle-run service, persistence (incl. failure context), reporters, triggers, archives |
| `tests/unit/test_cycle_execution_manager.py`, `tests/contract/api/` | API executions (cycle + ad-hoc) through the engine |
| `tests/integration/` | Sandbox API, fuller paths |
| `tests/contract/` | Packaging, CI wrapper contracts |

### Coverage matrix (engine suite)

#### A. Exit-code contract (`EngineExitCode`)

| ID | Scenario | Expected | Test location |
|----|----------|----------|---------------|
| EC-00 | All stages pass | 0 | `test_exit_codes.py`, `test_run_exit_codes.py` |
| EC-01 | Framework failure (rc≠0, not 124/127) | 1 | `test_run_exit_codes.py` |
| EC-02 | Config/CLI validation | 2 | `test_run_exit_codes.py`, `test_config_discovery.py` |
| EC-03a | Missing binary (127) | 3 | `test_executor.py`, `test_run_exit_codes.py` |
| EC-03b | Stage timeout (124, `timed_out`) | 3 | `test_executor.py`, `test_run_exit_codes.py`, `test_orchestrator_lifecycle.py`, `test_run_ci_ndjson.py` |
| EC-03c–e | Sync/async archive failure escalates exit | 3 | **Gap (roadmap)** — archiving is best-effort today; the current no-escalation behavior is locked in `test_run_archive.py` |
| EC-04 | `internal_failure` / empty returncodes | 4 | `test_orchestrator_lifecycle.py`, `test_run_exit_codes.py`, `test_exit_code_contract.py` |
| EC-05 | Trigger resting (no stages) | 0 | `test_run_exit_codes.py` |
| EC-06 | `max(plan_exit, archive_exit)` | 3 | **Gap (roadmap)** — see EC-03c–e |
| EC-07 | Raw rc=4 without `internal_failure` → domain | 1 | `test_exit_code_contract.py`, `test_exit_codes.py` |

#### B. CLI flags

> [!note] Roadmap flags
> `--tag`, `--fail-fast`, `--dry-run` and `--reporter` are **not implemented CLI flags** (see the correction note in [Command Reference](../CLI%20Commands/Command%20Reference.md)). The engine already supports `fail_fast` (exposed via the API layer); the CLI flags remain roadmap items. Rows below marked *Gap* become testable once the flags land.

| ID | Scenario | Test location |
|----|----------|---------------|
| CLI-01 | Missing `--cycle` (multi-cycle config → 2; single cycle → runs it) | `test_run_exit_codes.py` |
| CLI-02 | `--dry-run` | **Gap (roadmap flag)** |
| CLI-03 | `--cycle all --fail-fast` | **Gap (roadmap flag)** — engine `fail_fast` covered by `test_orchestrator.py` |
| CLI-04 | `--cycle all --tag` filtering | **Gap (roadmap flag)** — rejection as usage error locked in `test_run_flags.py` |
| CLI-05–06 | `--workers`, `--stream` (+ renderer selection) | `test_run_flags.py` |
| CLI-07 | `--reporter` override | **Gap (roadmap flag)** |
| CLI-08–09 | `--no-report-db`, `--async-report-db` | `test_run_archive.py` |
| CLI-10 | `--ci` forces sync archive | **Gap (roadmap)** — `--ci --async-report-db` still archives on a background thread today |
| CLI-11 | `--cycle all` sorted order + worst exit code, `--force`, `--no-persist` | `test_run_flags.py`, `test_run_exit_codes.py` |

#### C. Lifecycle & state

| ID | Scenario | Test location |
|----|----------|---------------|
| LC-01–06 | Artifacts, NDJSON, fail-fast, `plan_result.json` | Fail-fast + `plan_aborted`: `test_orchestrator.py`. Full event order, field contract, persistence hand-off, `plan_result.json` schema: `test_orchestrator_lifecycle.py` |
| LC-07–08 | Report archive post-run, trigger snapshot | `test_run_archive.py` (archive), `test_run_flags.py` (snapshot only after a green triggered run) |
| ST-01–08 | Logs, env carry-over, Allure wipe, NDJSON fields | `test_executor.py`, `test_log_buffer.py`, `test_orchestrator_lifecycle.py` |

#### D. CI NDJSON (`--ci`)

| Event | Test location |
|-------|---------------|
| `error`, `cycle_trigger`, `plan_started`, `stage_started`, `stage_finished`, `plan_finished` | `test_run_ci_ndjson.py` |
| `dry_run` / `dry_run_stage` | **Gap** — no `--dry-run` flag yet (see section B) |
| `plan_aborted` (artifact `events.ndjson`) | Engine-level: `test_orchestrator.py` — no CLI surface until `--fail-fast` lands |
| `error` on timeout (artifact mirror; stdout has `timed_out` + rc 124, no `error` key) | `test_run_ci_ndjson.py` |

#### E. Integration smoke

| ID | Scenario | Test location |
|----|----------|---------------|
| INT-01 | `run_plan` + real `echo.py` subprocess (2 stages) | `test_subprocess_smoke.py` |
| INT-02 | Full `testo run --ci` with echo adapter | `test_subprocess_smoke.py` |

### Run locally

Dev install (matches CI):

```bash
pip install -e ".[dev]"
```

**Engine + CLI slice** (fast, ~2s; PR gate):

```bash
pytest tests/unit/testo_core/engine \
       tests/unit/testo_core/cli/test_run_exit_codes.py \
       tests/unit/testo_core/cli/test_run_ci_ndjson.py \
       tests/unit/testo_core/cli/test_run_flags.py \
       tests/unit/testo_core/cli/test_run_archive.py \
       tests/unit/testo_core/cli/test_config_discovery.py \
       tests/unit/testo_core/cli/test_cli_commands_smoke.py \
       tests/contract/testo_core/test_exit_code_contract.py -q --no-cov
```

**With integration smoke** (`tier_heavy`):

```bash
pytest tests/unit/testo_core/engine tests/unit/testo_core/cli/test_run_*.py \
       tests/unit/testo_core/cli/test_config_discovery.py \
       tests/unit/testo_core/cli/test_cli_commands_smoke.py \
       tests/integration/testo_core/engine \
       tests/contract/testo_core/test_exit_code_contract.py -q --no-cov
```

**Full unit surface:**

```bash
pytest tests/unit/testo_core -q
```

**With coverage** (default `pytest.ini` adds `--cov=testo_core --cov=testo_api --cov-branch --cov-fail-under=65`; the gate is sized for the fast suite or a full run, so narrower selections like this one report coverage but fail the gate):

```bash
pytest tests/unit/testo_core/engine tests/unit/testo_core/cli -q
```

### CI/CD

| Workflow | Command | When |
|----------|---------|------|
| [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml) (`test` job) | `pytest -m "tier_fast and not quarantined" --cov-report=xml` | Every PR and push to main; engine unit + contract tests auto-marked `tier_fast` (folds in the old pr-fast workflow). Enforces the 65% line + branch coverage gate from `pytest.ini` and uploads `coverage.xml` as an artifact |
| [`.github/workflows/pr-heavy.yml`](../../.github/workflows/pr-heavy.yml) | `pytest -m "tier_heavy and not tier_external" --no-cov` | Optional PR deep suite; `test_subprocess_smoke.py` is marked `tier_heavy` explicitly (it also runs in the fast tier — it is deterministic and ~1s) |
| [`.github/workflows/nightly-external.yml`](../../.github/workflows/nightly-external.yml) | `pytest -m "tier_external and cleanup_required" --no-cov` | Nightly (and `release-gate.yml`, manual). Needs `TESTO_E2E_GITHUB_*` or `TESTO_E2E_GITLAB_*` repository secrets; the nightly job skips with a notice when neither pair is set |

Install step in CI: `pip install -e ".[dev]"`.

### Notes

- Tests **lock current exit-code behavior**, including known misclassifications documented in [Troubleshooting and Error Codes § Classification logic](../CLI%20Commands/Troubleshooting%20and%20Error%20Codes.md#classification-logic) (e.g. SIGKILL rc=137 → exit **1**); fixing those is a separate refactor.
- 2026-07-04: the suite was rebuilt after the original files were lost uncommitted, and two documented contract pieces were restored in the engine at the same time: stage timeouts now normalise to `returncode=124` (previously the raw signal code leaked through, classifying timeouts as exit 1), and `classify_exit_code` gained the `internal_failure` flag so orchestrator-caught exceptions exit **4** instead of **1**. See [Engine Test Suite Rebuild - 2026-07-04](../Archive/Engine%20Test%20Suite%20Rebuild%20-%202026-07-04.md).
- `CIRenderer` stdout omits `error` on `stage_finished`; the artifact `events.ndjson` mirror includes it — tests assert both surfaces where relevant.
- Use [Command Reference](../CLI%20Commands/Command%20Reference.md) for operator-facing commands; this section is for contributors validating engine changes.

## Related operational docs

- [E2E Harness Operations Guide](../Processes%20&%20Guides/E2E%20Harness%20Operations%20Guide.md) — tiered E2E harness for this repo
- [CI-CD Pipeline Setup](../Processes%20&%20Guides/CI-CD%20Pipeline%20Setup.md) — GitHub Action / GitLab template
- [Product Roadmap](../Roadmap%20&%20Strategy/Product%20Roadmap.md) — current state and next steps
