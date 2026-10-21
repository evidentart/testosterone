---
type: architecture
status: current
created: 2026-06-25
updated: 2026-10-21
---

# Deep Dive — Execution Logic

[Architecture Overview](Architecture%20Overview.md)

This note maps how **Testo** (`testo run`) initializes a test session, executes it stage-by-stage on the host, preserves state, and tears down. It is the implementation companion to [Architecture Overview](Architecture%20Overview.md) and [QA Strategies](../Testing%20Workflows/QA%20Strategies.md).

Every run uses **host subprocesses** — no Docker. The Docker-based execution stack (the project's original "UQO" design) that existed until v1.1 is summarized at the end.

---

## Executive summary

| Property | Behavior |
|----------|----------|
| Entry | `testo run` → Typer → `execute_plan_command` |
| Config | `testosterone.yaml` (or discovery chain) |
| Execution unit | **Cycle** (plan) → ordered **stages** |
| Stage runtime | One `subprocess.Popen` per stage |
| Stage ordering | **Strictly sequential** in `run_plan()` |
| Parallelism | Framework-internal only, via `workers` (BehaveX; pytest with pytest-xdist) — see [Framework level](#framework-level--optional) |
| Durability | `artifacts/<cycle>/` — logs, NDJSON events, Allure JSON |
| Exit codes | `EngineExitCode` 0–4 via `classify_exit_code()` |

---

## End-to-end lifecycle

```mermaid
sequenceDiagram
  participant CLI as testo_run
  participant Runner as cli_runner
  participant Svc as CycleRunService
  participant Config as config_loader
  participant Trig as triggers
  participant Orch as orchestrator
  participant Exec as executor
  participant FW as framework_adapter

  CLI->>Runner: execute_plan_command
  Runner->>Config: discover_and_load / resolve_plan
  Runner->>Svc: run(cfg, plan, renderer, options)
  Svc->>Config: resolve_stages_for_plan
  Svc->>Trig: evaluate_cycle_trigger optional
  Svc->>Orch: run_plan
  loop each stage
    Orch->>Exec: run_stage
    Exec->>FW: build_argv
    Exec->>Exec: Popen + LogBuffer + timeout
    Exec-->>Orch: StageResult
  end
  Orch->>Orch: plan_result.json + events.ndjson
  Svc->>Svc: reporters + optional DB archive + trigger snapshot
```

### Phase map

| Phase | Module | What happens |
|-------|--------|----------------|
| 1. CLI parse | `testo_core/cli/commands/run.py` | Validates flags; defers heavy imports |
| 2. Config load | `testo_core/config/loader.py` | `discover_and_load()` → `TestosteroneConfig` |
| 3. Plan resolve | `testo_core/config/resolver.py` | `resolve_plan()` / `resolve_stages_for_plan()` |
| 4. Trigger gate | `testo_core/services/cycle_run.py` → `config/triggers.py` | Optional skip (exit 0) unless `--force` |
| 5. Renderer pick | `testo_core/cli/runner.py` | Buffered / Stream / CI (NDJSON) |
| 6. Engine run | `testo_core/engine/orchestrator.py` | `run_plan()` — sequential stages |
| 7. Subprocess | `testo_core/engine/executor.py` | `run_stage()` per stage |
| 8. Post-run | `testo_core/services/cycle_run.py` | Reporters, native report snapshot, DB archive, trigger snapshot |

---

## Initialization

### CLI → runner bridge

`testo run` calls `execute_plan_command()` in `testo_core/cli/runner.py`:

- **`--cycle all`** — runs every cycle name (sorted); each trigger evaluated separately; `fail_fast` can stop after the first failing cycle.
- **Single cycle** — `resolve_plan(cfg, plan_name=...)`.
- **`--tag`** — filters cycles when using `all`, or validates tag membership for one cycle.
- **`--dry-run`** — prints resolved argv/cwd table (or NDJSON `dry_run_stage` events); no subprocesses.

Each resolved cycle is handed to `CycleRunService.run()` (`testo_core/services/cycle_run.py`), which owns the trigger gate, the engine call and every post-run step. The API's `testo_api/cycle_execution_manager.py` calls the same service (for named cycles and for ad-hoc one-stage runs built by `single_stage_plan()`), so a run started from the dashboard goes through exactly the same steps; the two callers differ only in the renderer and the listener that presents trigger/archive messages (Rich panels or NDJSON on stdout for the CLI, lines in `events.ndjson` for the API).

Config errors return exit code **2** (`EngineExitCode.INVALID_INPUT`). In `--ci` mode, errors emit:

```json
{"event":"error","code":"invalid_input","message":"..."}
```

### Config discovery order

From `testo_core/config/loader.py` (first match wins):

1. `--config PATH`
2. `./testosterone.yaml`
3. `./testosterone.yml`
4. `[tool.testosterone]` in `./pyproject.toml`

Legacy flat `runs:` schemas are wrapped into a single plan named `default`.

### Stage resolution

`resolve_stages_for_plan(plan)` applies:

- Default timeouts and paths from `defaults:` in YAML
- Per-stage `if_expr` gating (environment-based enable/disable)
- `${env:VAR}` interpolation in config strings

An empty resolved stage list is a hard error (exit **2**).

### Renderer selection

| Mode | Class | `wants_streaming` | Output |
|------|-------|-------------------|--------|
| Default | `BufferedRenderer` | `false` | Rich progress + post-mortem panels |
| `--stream` | `StreamRenderer` | `true` | Same panels + live stdout chunks |
| `--ci` | `CIRenderer` | `false` | NDJSON lines on stdout only |

Workers override: `_apply_workers_override()` clones the plan with `workers=` set on every stage (only frameworks that use `workers` act on it).

---

## Session execution (`run_plan`)

`testo_core/engine/orchestrator.py` owns the main loop.

### Setup (per cycle)

1. Resolve `artifacts_root` (from config `defaults.artifacts_root`, default `artifacts/`).
2. Create `artifacts/<cycle>/` and open `events.ndjson` (append-only NDJSON).
3. Copy `parent_env` (typically `os.environ`) for all stages.
4. Emit `PlanStarted` to the renderer.

### Per-stage loop

For each stage in order:

1. Emit `StageStarted` (renderer + NDJSON `stage_started`).
2. Call `run_stage()` inside a broad `try/except` — unexpected exceptions become `StageResult` with `returncode=4` and `error="internal error: ..."`.
3. Append `StageResult`; emit `StageFinished`.
4. Write NDJSON `stage_finished` (includes `returncode`, `timed_out`, `error`, `log_path`).
5. If `--fail-fast` and `returncode != 0`, write `plan_aborted` and break.

### Aggregation

- `aggregate_returncode = max(stage returncodes, default=0)`
- `exit_code = classify_exit_code(returncodes, infra_error=None)`
- Emit `PlanFinished`; write `plan_finished` NDJSON.
- Best-effort `plan_result.json` via `_try_persist()` (JSON snapshot; full DB persistence is not wired here yet).

### Health % computation

Both persistence backends (`testo_core/persistence/db_backend.py`,
`testo_core/persistence/json_backend.py`) call
`testo_core/persistence/health.py::compute_stage_health()` before writing the
run record. It re-parses each stage's Allure result JSON (via
`testo_core.reporting.allure_results.parse_collected_results`, the same
machinery the Extent/ReportPortal/TestBeats reporters use) to get real
per-test `passed`/`failed`/`broken`/`skipped`/`total` counts:

- **Per-stage `health_pct`** — `passed / total * 100` for that stage's own
  Allure results, stored on each entry in the persisted `stages` metadata.
- **Overall run `health_pct`** — a single weighted pass rate: sum of `passed`
  across every stage divided by the sum of `total` across every stage (not an
  average of the per-stage percentages). This is what the Run Detail page's
  Summary card and the Dashboard/Runs list health figures show.
- **Crashed stages** — a stage that exited non-zero without producing any
  results (e.g. it crashed at startup) has no pass rate, so the overall figure
  is scaled by the share of stages that did not crash: one stage at 100% plus
  one crashed stage gives 50%, not the 100% the other stage alone would show.
- **Fallback** — if no stage produced any parseable Allure results (empty
  `total` everywhere), the overall figure falls back to the older binary
  estimate (`passed_stages / len(stages) * 100`, i.e. did each stage
  subprocess exit `0`) so a run with no Allure output still gets an
  approximate health instead of a bare 0%. Runs persisted before this change
  only have that binary estimate — `stage_health` is empty for them, and the
  frontend shows "Per-stage breakdown not available for this run."

### Test time

The same parse gives each test's duration (Allure `stop - start`), so both
backends also store test time, summed by `run_test_totals()` in
`testo_core/persistence/health.py`:

- **`test_time_ms`** on each stage: the sum of that stage's test durations.
- **`metrics_duration_ms`** on the run: the sum over every test. It is not wall
  time (`duration_s`), which also counts collection, fixtures and process start.
- **`avg_case_ms`** on the run: `metrics_duration_ms / total_tests`, `null`
  when the run has no tests.

Compare shows these as "Test time (sum)" and "Avg per test". Runs persisted
before 2026-10-10 have neither key and show `n/a` there.
`tests/contract/testo_core/test_run_metadata_contract.py` fails when
`testo_core/history/views.py` reads a metadata key that persistence never writes.

---

## Subprocess execution (`run_stage`)

`testo_core/engine/executor.py` is a pure subprocess wrapper.

### Layout before spawn

```text
artifacts/<cycle>/<stage>/
  run.log
  allure-results/<framework>/   # wiped and recreated each stage
```

Steps:

1. `get_adapter(stage.framework)` → `PytestAdapter` | `BehaveAdapter` | `BehaveXAdapter` | `PlaywrightAdapter` | `CommandAdapter` (argv = `stage.args` verbatim), or a `testo.frameworks` plugin adapter
2. `adapter.build_argv(target_repo, results_dir, stage_args, workers)`
3. `merged_env(parent_env, stage.extra_env)` plus injected vars:
   - `TESTO_SHARED_ALLURE_RESULTS_DIR` → Allure output dir
   - `TESTO_ARTIFACTS_ROOT` → artifacts root
   - `TESTO_LAST_TEST_TYPE` → framework name

### Process model

```text
subprocess.Popen(argv, cwd=target_repo, stdout=PIPE, stderr=STDOUT)
    │
    ├── daemon thread: drain_stream_into_buffer → LogBuffer.feed
    └── main thread: proc.wait(timeout=stage.timeout_s)
```

- **LogBuffer** — tees all bytes to `run.log`; keeps a 64 KiB in-memory ring for `output_tail` (Rich panels).
- **Timeout** — `subprocess.TimeoutExpired` → SIGTERM → 5s grace → SIGKILL via `_terminate()`; sets `timed_out=True` and normalizes `returncode=124`.
- **Missing executable** — `FileNotFoundError` → `returncode=127`, `error` describes missing binary.

### Post-stage hook

For `behavex`, `_finish_behavex_reports` runs best-effort. The adapter starts BehaveX without `--formatter` (BehaveX skips `report.html` whenever one is set), so BehaveX writes its own HTML report and `report.json` to `behave_reports/`. The hook then converts `report.json` into Allure results in `allure-results/behavex/` with BehaveX's own Allure formatter (`testo_core/reporting/behavex_allure.py`), and calls `ensure_behavex_report_html`, which renders `report.html` only if a stage passed its own `--formatter`. A failure in either step is logged, appended to `run.log` and set as the stage's `error` (unless a timeout or launch error is already there). The exit code is unchanged. See [BehaveX Reports - 2026-10-21](../Specs%20&%20ADRs/BehaveX%20Reports%20-%202026-10-21.md).

For any stage with `junit_xml` globs (typically `equipment: command`), `_import_junit` converts the matching JUnit XML (only files inside `target_repo`, only files written since the stage started) into one Allure `*-result.json` per `<testcase>` in `allure-results/<framework>/`: `<failure>` → failed, `<error>` → broken, `<skipped>` → skipped, otherwise passed. It is best-effort, like the BehaveX hook. The process exit code still decides the stage result, and the import outcome (count, or malformed files skipped) is appended to `run.log` as `[testo] junit_xml: ...`.

---

## Runtime state preservation

### What survives across stages

| State | Mechanism |
|-------|-----------|
| Environment | `parent_env` dict passed unchanged between stages (plus per-stage `extra_env` overlay) |
| Cycle artifacts | Same `artifacts/<cycle>/` directory; `events.ndjson` appended |
| Trigger snapshot | After successful snapshot-mode run, `persist_trigger_snapshot()` writes JSON under artifacts |
| Allure per stage | **Isolated** — `results_dir` is `rmtree`'d before each stage |

### What does not carry over

- Subprocess stdout (only persisted in per-stage `run.log`)
- In-memory `LogBuffer` ring (recreated per stage)
- Framework process state (each stage is a fresh process)

### Event stream durability

Two consumers write the same logical events:

1. **Renderer** — human UI or CI stdout (`CIRenderer` → `emit_ndjson`)
2. **`_NdjsonRecorder`** — append-only `artifacts/<cycle>/events.ndjson`

`plan_result.json` is written after the loop completes (best-effort; `OSError` ignored).

---

## Concurrency and parallelism

### Orchestrator level — none

`orchestrator.py` states explicitly that stages run **sequentially**; the loop is the single place to change for future concurrent stage execution.

### Framework level — optional

`workers:` (stage, or `defaults:`, default `4`; CLI `--workers` overrides every stage) means something different per framework:

| Framework | What `workers: N` does |
|-----------|------------------------|
| `behavex` | `--parallel-processes N --parallel-scheme feature`, unless `args:` already set them. |
| `pytest` | `-n N` when N > 1 **and** pytest-xdist is importable by the `pytest` on PATH (the adapter reads its shebang and probes that interpreter). Without xdist it logs one warning and runs serially. A `-n`/`--numprocesses` or `-p no:xdist` in `args:` wins. |
| `playwright` | `--workers=N`, unless `args:` set `--workers`/`-j` (this replaces `workers` in `playwright.config`). |
| `behave` | Nothing — native behave is single-process. Setting `workers:` on the stage loads fine but logs a warning. |
| `command` | Nothing — the command owns its own flags (same warning). |

The API's `GET /api/v1/cycles/{cycle}` returns `workers: null` for `behave` and `command` stages, so the UI only shows *Workers* where it can apply (pytest's is labelled "with pytest-xdist").

### Threading in the engine

| Thread | Role | Daemon |
|--------|------|--------|
| `testo-log-reader-<stage>` | Read subprocess pipe → `LogBuffer` | Yes |
| `testo-report-archive` | `try_persist_cycle_report()` when `--async-report-db` (non-CI) | No (joined, 30s timeout) |

The log reader is **joined** with `timeout=2.0` after the process exits. If the reader is still draining, some tail bytes may be lost before the next stage starts.

### Multi-cycle (`--cycle all`)

Cycles run **one after another** in sorted name order. No thread pool across cycles.

---

## Teardown

### Per-stage subprocess

1. Process exits or is killed after timeout.
2. Log reader joined (2s cap).
3. `LogBuffer` closed (flushes `run.log`).
4. `StageResult` returned to orchestrator.

### Per-cycle

1. `plan_finished` event and JSON summary.
2. **Reporters** — `run_configured_reporters()` if YAML `reporters:` or `--reporter` set (Allure generate, Extent, ReportPortal, TestBeats).
3. **Report DB archive** — `try_persist_cycle_report()` unless `--no-report-db` or `--no-persist`:
   - **Sync** (default, and always under `--ci`) — blocks until archive completes; failure bumps exit to **3**.
   - **`--async-report-db`** (interactive only) — background thread joined up to 30s before process exit; failure bumps exit to **3**.
4. **Trigger snapshot** — if snapshot-mode trigger fired and run succeeded, persist catalog for next diff.

### Process exit

`testo run` raises `typer.Exit(code=exit_int)`. `testo_core/cli/app.py` `main()` returns that code to the shell.

---

## Architectural bottlenecks and race conditions

These are **current code behaviors** worth knowing for CI design and future refactors. See also [Technical Debt Tracker](../Testing%20Workflows/Technical%20Debt%20Tracker.md) and [Troubleshooting and Error Codes](../CLI%20Commands/Troubleshooting%20and%20Error%20Codes.md).

| Issue | Location | Impact |
|-------|----------|--------|
| Broad `except Exception` around `run_stage` | `orchestrator.py` | Surprises become synthetic stage failure instead of aborting the plan |
| Sequential multi-cycle | `execute_plan_command` with `plan_name == "all"` | Wall-clock time grows linearly with cycle count |
| Per-stage Allure wipe | `executor` `shutil.rmtree(results_dir)` | Correct isolation; cannot accumulate Allure results across retries within one stage without code changes |
| Log reader join timeout | `executor` `reader.join(timeout=2.0)` | Rare truncated tail in `output_tail` / last lines of `run.log` under heavy I/O |
| Reporter failures don't fail the run | `ReporterFactory` partial failures | A failed reporter is logged and returned as `ok=False`, but the exit code stays green |

### Exit classification reference

`testo_core/engine/exit_codes.py`:

```python
# internal_failure → INTERNAL_ERROR (4)
# 124, 127 → INFRA_FAILURE (3)
# any other non-zero → DOMAIN_FAILURE (1)
# empty returncodes list → INTERNAL_ERROR (4)
```

Stage timeouts emit **124** after `_terminate()`; orchestrator sets `internal_failure=True` for uncaught engine exceptions (plan exit **4**).

---

## Removed: the UQO headless / Docker path

Until v1.1 a second stack ran beside the engine: `uqo run --config` and the API's `/api/v1/executions` called `HeadlessEngineService`, which ran each framework in a one-off Docker container via `testo_core/runners.py` and wrote history through `run_history.record_completed_run`. It duplicated trigger-less execution, persistence and exit-code logic, so behaviour drifted between surfaces. It was removed; what only it provided now lives on the engine path:

| Former legacy-only feature | Now |
|----------------------------|-----|
| Run one framework without a cycle | `POST /api/v1/adhoc-executions` → `single_stage_plan()` → `CycleRunService` |
| CI provenance on run records | `DbBackend` + `services/ci_provenance.py` |
| Failed cases / traceback / log tail for AI summaries | `persistence/failure_context.py` via `DbBackend` |
| InfluxDB / Prometheus push | `integrations.push_run_metrics_if_configured()` after every cycle |

The compose stack (Postgres only) is described in repo `ARCHITECTURE.md` and is not required for `testo run`.

### Official documentation

| Topic | Reference |
|-------|-----------|
| Allure result format | https://docs.qameta.io/allure/ |
| Docker Compose | https://docs.docker.com/compose/ |
| Compose file spec | https://docs.docker.com/compose/compose-file/ |

---

## Related notes

- [Architecture Overview](Architecture%20Overview.md) — module map and artifact layout
- [QA Strategies](../Testing%20Workflows/QA%20Strategies.md) — triggers, CI output, typical flows
- [Command Reference](../CLI%20Commands/Command%20Reference.md) — flags and exit codes
- [Troubleshooting and Error Codes](../CLI%20Commands/Troubleshooting%20and%20Error%20Codes.md) — failure playbook
- [Technical Debt Tracker](../Testing%20Workflows/Technical%20Debt%20Tracker.md) — prioritized refactor backlog
