---
type: reference
status: current
created: 2026-06-25
updated: 2026-10-22
---

# Command Reference

Entry point: **`testo`** (`pyproject.toml` → `testo_core.cli.app:main`).

Parent index: [Index](../Index.md). Architecture: [Architecture Overview](../Architecture/Architecture%20Overview.md). Run lifecycle: [QA Strategies](../Testing%20Workflows/QA%20Strategies.md).

```bash
testo --help
```

Help is grouped into panels: **Run and report**, **Config**, **Diagnostics**, **Maintenance**, **About**.

Extras: `pip install testo-core` is the CLI with pytest, Playwright, `command` and `junit` stages. Add `[bdd]` for `behave` and `behavex` stages (Behave, BehaveX and Allure-Behave), `[api]` for the REST API and UI backend, `[db]` for Postgres or MySQL, `[metrics]` for InfluxDB. A `behave` stage without the extra fails with exit `3` and `executable not found: behave (... pip install 'testo-core[bdd]')`.

---

## `testo run`

Execute one cycle or all cycles from `testosterone.yaml`.

```bash
testo run --cycle sample-pytests
testo run --cycle sample-pytests --ci
testo run --cycle sample-pytests --stream
testo run --cycle sample-pytests --workers 8 --force
```

### Options

| Flag | Short | Description |
|------|-------|-------------|
| `--cycle` | | Cycle name from `cycles:`; use `all` for every cycle (sorted), each trigger evaluated separately |
| `--plan` | `-p` | Deprecated alias for `--cycle` (hidden) |
| `--config` | `-c` | Path to `testosterone.yaml` (default: discovery) |
| `--stream` | | Tail each stage stdout live (vs post-mortem Rich panel) |
| `--ci` | | NDJSON events on stdout instead of Rich UI |
| `--no-persist` | | Skip optional run-history DB writes |
| `--no-report-db` | | Skip archiving cycle artifacts to report DB after run |
| `--async-report-db` | | Archive in background thread with join timeout; **ignored when `--ci` is set** |
| `--workers` | `-w` | Override parallel workers (e.g. BehaveX) |
| `--force` | `-f` | Run even when trigger would skip the cycle |

> [!warning] Roadmap flags — not implemented yet
> `--tag`, `--fail-fast`, `--dry-run` and `--reporter` were previously listed here but are **not present in `testo_core/cli/commands/run.py`**. The API layer already accepts `fail_fast` and `reporter_override` on `POST /api/v1/cycles/{cycle}/executions` (surfaced in the React Run panel); the CLI flags remain roadmap items. (Doc corrected 2026-07-04 during the Phase 5 UI redesign.)

### Expected terminal output

**Interactive (default):** Rich panels for plan start, each stage, and finish. On success:

```text
Run finished successfully.
```

On failure:

```text
Run exited with code 1.
```

**`--ci`:** One NDJSON object per line (`plan_started`, `stage_started`, `stage_finished`, `plan_finished`, etc.), no Rich styling.

### Exit codes

See [Architecture Overview § Exit code contract](../Architecture/Architecture%20Overview.md#exit-code-contract). `testo run` returns the engine exit code directly.

---

## `testo ingest`

Record JUnit XML that another step already wrote (any runner, any language) as a run of a cycle. Nothing is executed: the files are parsed into the same run history as `testo run`, so Compare, trends, `testo flaky`, reporters and the PR comment work on them.

```bash
testo ingest 'reports/**/*.xml' --cycle web-unit          # record locally
testo ingest junit.xml --cycle api --tier integration --ci
testo ingest test-results/results.json --cycle web-e2e --stage e2e --tier e2e   # Playwright JSON
testo ingest 'reports/*.xml' --cycle web-unit \
  --server https://testo.example.com --token "$TESTO_API_TOKEN"   # team server
```

| Flag | Default | Meaning |
|------|---------|---------|
| `REPORTS...` | required | Files or quoted globs, relative to `--repo` (absolute paths must be inside it). A `.json` file is read as a Playwright JSON report (`--reporter=json`), keeping retries, flaky tests and attachments |
| `--cycle` | required | Cycle name the run is recorded under: letters, digits, `.`, `_`, `-`. Reuse it so runs build a history |
| `--stage` | `junit` | Stage name the tests are grouped under |
| `--tier` | `unit` | Test-pyramid tier: `unit`, `integration`, `e2e` |
| `--repo` | `.` | Directory the report paths are relative to |
| `--config` / `-c` | discovered | `testosterone.yaml` for `reporters:` and paths; not required |
| `--ci` | off | NDJSON events on stdout, as `testo run --ci` (with `--server`: one `ingest_uploaded` event) |
| `--no-persist` | off | Parse only, record nothing |
| `--server` | `$TESTO_SERVER_URL` | Upload to a [team server](../Processes%20&%20Guides/Team%20Server.md) instead of recording locally |
| `--token` | `$TESTO_API_TOKEN` | The server's API token |

Exit codes follow `testo run`: **0** every test passed or was skipped, **1** a test failed or broke, **2** bad arguments or no file matched, **3** the server could not be reached or refused the upload (wrong token). With `--server`, the job's CI provenance (provider, pipeline, job, commit, branch, repository) is sent with the files. Under the hood this is a one-stage cycle with `equipment: junit` run through `CycleRunService`; see [Ingest and Team Server - 2026-10-22](../Specs%20&%20ADRs/Ingest%20and%20Team%20Server%20-%202026-10-22.md). For Playwright JSON (each retry as a step, flaky tests flagged, traces and screenshots copied from inside `--repo` as Allure attachments) see [Playwright JSON Import - 2026-10-22](../Specs%20&%20ADRs/Playwright%20JSON%20Import%20-%202026-10-22.md).

---

## `testo report`

Build unified Allure reports from artifacts; subcommands for archives and native framework HTML.

```bash
# Default: generate + local Allure dashboard (opens browser unless --no-open)
testo report --cycle sample-pytests

testo report --generate-only --out artifacts/report
testo report --format json --summary-out summary.json
testo report list
testo report open --id <uuid>
testo report compare
testo report native
testo report native flow-tests --no-open
testo report pyramid <run-id>
```

### Default callback options

| Flag | Short | Default | Description |
|------|-------|---------|-------------|
| `--artifacts` | `-a` | `artifacts` | Artifacts root |
| `--cycle` | | latest | Restrict to one cycle |
| `--generate-only` | | false | Write HTML only; no HTTP server |
| `--host` | | `127.0.0.1` | Allure dashboard host |
| `--port` | | `8080` | Port (auto-picks free port if busy; `0` = always free) |
| `--out` | `-o` | `artifacts/report` | Generated HTML output dir |
| `--format` | `-f` | `html` | `html`, `json`, or `junit` |
| `--summary-out` | | | Path for json/junit summary file |
| `--no-history` | | false | Skip injecting prior Allure history |
| `--open` / `--no-open` | | open | Start dashboard after generate |
| `--trend` | | `1` | Merge history from N prior archived runs |

**Typical success output:** messages about collecting results, running `allure generate`, and a local URL such as `http://127.0.0.1:8080/...`.

### Subcommands

| Command | Purpose |
|---------|---------|
| `testo report list` | Table of archived runs (needs DB); columns: id, cycle, created, exit, tests, pass, fail |
| `testo report open --id <uuid>` | Extract archive and regenerate/serve Allure |
| `testo report compare` | Rich diff + Allure comparison (optional baseline/current UUIDs) |
| `testo report native [ROUTINE]` | List or open BehaveX/pytest native HTML under stage dirs |
| `testo report markdown [--cycle NAME \| --run-id ID] [--out FILE] [--run-url URL]` | The cycle's latest run (or one run) as GitHub-flavored Markdown: headline counts, per-stage table, failing tests, and per-test changes since the cycle's previous run. The first line is a hidden `<!-- testo-summary:<cycle> -->` marker. Exit `2` when no run is recorded. The GitHub Action uses it for the job summary and the PR comment |
| `testo report annotations [--cycle NAME \| --run-id ID] [--workspace DIR] [--limit N] [-c CONFIG]` | The run's failing tests as GitHub Actions `::error file=…,line=…` workflow commands, so each failure shows on its line in the pull request's "Files changed". The location is the first stack-trace frame inside `--workspace` (default `.`), tried relative to the workspace, each stage's `target_repo` from the config, and the run's target repo. At most `--limit` (default `10`, GitHub's per-step cap) lines, then a `::notice` with the rest. Exit `2` when no run is recorded. The GitHub Action prints it by default. See [Alerts Where Developers Look - 2026-10-22](../Specs%20&%20ADRs/Alerts%20Where%20Developers%20Look%20-%202026-10-22.md) |
| `testo report pyramid RUN_ID [-c CONFIG]` | ASCII unit/integration/e2e test pyramid for a completed run (`run_id`, not the archive UUID); stage→tier is the stage's `tier:` (default inferred from `equipment`: pytest→unit, behave→integration, behavex→e2e, playwright→e2e) as recorded in the run when it executed; `-c` is only read for older runs that predate recorded tiers. See [Architecture Overview § Test pyramid](../Architecture/Architecture%20Overview.md#test-pyramid). |

---

## `testo cycles` (alias: `testo plans`)

Inspect cycles in config (hidden alias `plans` for backward compatibility).

```bash
testo cycles list
testo cycles show sample-pytests
testo cycles show sample-pytests -c ./testosterone.yaml
```

**`list`:** Rich table — Name, Description, stage count.

**`show`:** Cycle title plus table of stages (equipment, target repo, args, timeout).

Config errors print `[fail]config error: …` and exit **2**.

---

## `testo config`

| Subcommand | Description |
|------------|-------------|
| `testo config validate` | Load YAML; optional `--check-executables` for pytest/behave/behavex (and `npx` for playwright) on PATH |
| `testo config init` | Write starter `testosterone.yaml` (`--path`, `--force`) |
| `testo config db` | Set `database.url` (PostgreSQL prompts or `--url`) |

```bash
testo config validate
testo config validate --no-check-executables
testo config init --path testosterone.yaml --force
testo config db --url sqlite:////tmp/testo-reports.db
```

**Validate success:**

```text
ok — version=1 cycles=6 reporters=4 defaults_target=.
```

**Deprecated:** `testo config-db` → use `testo config db`.

### Editor autocomplete

`schema/testosterone.schema.json` is a JSON Schema for `testosterone.yaml`. Editors with a YAML language server (VS Code with the Red Hat YAML extension, JetBrains IDEs, Neovim) then suggest keys and built-in equipment, and underline typos as you type. `testo config init` and `testo init` add this line at the top of the file; add it yourself to an existing config:

```yaml
# yaml-language-server: $schema=https://raw.githubusercontent.com/taltal-beep/testosterone/main/schema/testosterone.schema.json
```

`testo config validate` is still the final word. The schema describes the `cycles:` layout only, and accepts plugin equipment and reporter names. Why and how it is generated: [Config JSON Schema](../Specs%20&%20ADRs/Config%20JSON%20Schema%20-%202026-10-22.md).

---

## `testo diff` / `testo summary`

Compare two archived report runs by UUID (from `testo report list`).

```bash
testo diff <BASELINE_ID> <CURRENT_ID>
testo summary   # same family; see help for metrics-only variants
```

Rich terminal diff of metrics and (for full diff) extracted Allure deltas. Reads the run history database (SQLite by default; `testo-core[db]` for Postgres).

Prefer **`testo report compare`** for Rich diff plus Allure visual comparison pipeline.

Note: this operates on `ReportArchive` UUIDs (`testo report list`), a separate id space from run-history `run_id`s — see [Architecture Overview § Persistence](../Architecture/Architecture%20Overview.md#persistence). The React Compare page (`GET /api/v1/analytics/delta` + `/analytics/delta/cases`) reaches equivalent per-stage and per-test detail by `run_id` instead, per [Delta Comparison Policy](../Specs%20&%20ADRs/Delta%20Comparison%20Policy.md).

---

## `testo flaky`

Tests whose outcome keeps flipping across a cycle's recent runs.

```bash
testo flaky --cycle fake-api               # last 20 runs
testo flaky --cycle fake-api --window 50 --json
testo flaky --cycle nightly --fail-on-flaky  # exit 1 when any test is flaky and not quarantined (CI gate)
testo flaky --cycle nightly --new --json     # only tests the latest run made flaky
```

| Flag | Default | Meaning |
|------|---------|---------|
| `--cycle` | required | Cycle whose run history to read |
| `--window` | `20` | How many of the cycle's most recent runs to look at (min 2) |
| `--new` | off | Only tests the cycle's latest run made flaky: flaky in the window ending at that run, not in the window ending at the run before. Used for alerts and the action's `flaky-issues` |
| `--json` | off | Print the report as JSON |
| `--fail-on-flaky` | off | Exit `1` when any flaky test that isn't quarantined is found |
| `--config` | discovery | `testosterone.yaml` whose `quarantine:` rules mark tests; without a config found, nothing is marked. Exit `2` if the given file is missing or invalid |

A test is flaky when, within the window, it both passed and failed and its outcome changed at least twice (skipped runs are ignored). One change is a regression or a fix, which `testo summary` shows. Exit `2` when fewer than two runs with per-test results exist. Reads run-history records (`run_id`s) and each run's artifact snapshot, the same data as `GET /api/v1/analytics/flaky?cycle=<name>` and the Flaky tests card on the cycle page. See [Open Source Features - 2026-10-19](../Specs%20&%20ADRs/Open%20Source%20Features%20-%202026-10-19.md).

The table's Quarantined column (and `"quarantined"` in `--json`) shows which flaky tests match the cycle's [`quarantine:` rules](../Testing%20Workflows/QA%20Strategies.md#defining-work-in-testosteroneyaml); for the others it prints a `quarantine:` snippet to paste. A quarantined test's failures don't fail `testo run`; see [Flaky Test Quarantine - 2026-10-22](../Specs%20&%20ADRs/Flaky%20Test%20Quarantine%20-%202026-10-22.md).

---

## `testo notify`

Send a recorded run to Slack and/or Microsoft Teams: pass/fail counts, then new regressions, newly flaky tests, failing tests and fixed tests (10 names per list).

```bash
export TESTO_SLACK_WEBHOOK_URL=...         # from a secret, never on the command line
testo notify --to slack --cycle nightly                      # only when it needs attention
testo notify --to slack --to teams --cycle nightly --when change --run-url "$CI_JOB_URL"
testo notify --to teams --cycle nightly --dry-run            # print the payload, send nothing
```

| Flag | Default | Meaning |
|------|---------|---------|
| `--to` | required | `slack` or `teams`; repeat for both. URLs come from `TESTO_SLACK_WEBHOOK_URL` and `TESTO_TEAMS_WEBHOOK_URL` |
| `--cycle` / `--run-id` | latest run | Which recorded run to send |
| `--when` | `failure` | `failure`: the run failed or made a test flaky. `change`: the run's result flipped, or a test regressed, got fixed or became flaky. `always`: every run |
| `--title` | cycle name | Name in the message |
| `--run-url` | none | "View run" link |
| `--dry-run` | off | Print the JSON payloads instead of posting |

Exit `0` when sent or when there is nothing to report, `2` for a bad flag, a missing webhook variable or no recorded run, `3` when a webhook rejects the message or can't be reached (the error never includes the URL). The `slack` and `teams` [reporters](#reporter-types-reporters----reporter) send the same message right after `testo run`. See [Alerts Where Developers Look - 2026-10-22](../Specs%20&%20ADRs/Alerts%20Where%20Developers%20Look%20-%202026-10-22.md).

---

## `testo doctor`

Health check: config load, framework CLIs on PATH, Node.js + Allure Report 3 CLI, optional Docker warnings, DB probe if `DATABASE_URL` or config URL is set.

```bash
testo doctor
testo doctor -c testosterone.yaml
```

**Output:** Rich table with Check / Status / Detail rows (`PASS`, `FAIL`, `WARN`, `SKIP`).

Exits **2** on hard failures (config or missing required executables) — see [Troubleshooting and Error Codes § Commands that use exit codes](Troubleshooting%20and%20Error%20Codes.md#commands-that-use-exit-codes).

---

## `testo plugins`

Lists the built-in frameworks and reporters, then every installed [plugin](#plugins) with the package that registered it.

```bash
testo plugins            # table
testo plugins --check    # also import each plugin and verify its interface
testo plugins --json
```

Exits **1** when `--check` finds a plugin that fails to import or does not implement its interface; otherwise **0**.

---

## `testo clean`

Remove `artifacts/` (from config or `./artifacts`) and `./temp`; optional Docker prune.

```bash
testo clean --yes
testo clean -y --docker
```

Without `--yes` / `-y`: refuses with exit **2**.

---

## `testo watch`

Filesystem watcher (watchdog) re-runs a cycle after debounced changes.

```bash
testo watch --cycle sample-pytests
testo watch --cycle sample-pytests --path sample_target_repo --debounce-ms 750
```

Ignores `.git`, `artifacts`, `venv`, `__pycache__`, etc. Each batch invokes `testo run` with the same cycle.

---

## `testo init`

Interactive wizard for `testosterone.yaml` (non-interactive alternative: `testo config init`).

```bash
testo init
```

---

## `testo version`

```bash
testo version
# testo 0.1.0

# Equivalent top-level eager flag (works before/instead of a subcommand):
testo --version
testo -v
```

---

## Other entry points (not `testo` Typer tree)

| Command | Package | Role |
|---------|---------|------|
| `testo-api` | `testo_api` | FastAPI server (React UI backend) |

The v1.0 `uqo` command (including its `uqo run --config` headless format with `--ghost`, `--json`, `--stream-json`) and the `testo-ui` Streamlit app were removed in v1.1; use `testo run --cycle … --ci` and the React frontend.

---

## Environment variables (common)

| Variable | Effect |
|----------|--------|
| `DATABASE_URL` | Overrides `database.url` in YAML for archives / list |
| `TESTO_HOME` | Where per-run report copies (`static/`, `static_reports/`) are written. Default: `./.testo` for a `pip install`, the repository root for a source checkout ([Architecture Overview § Artifact layout](../Architecture/Architecture%20Overview.md#artifact-layout)) |
| `INFLUXDB_URL`, `INFLUXDB_TOKEN`, `INFLUXDB_ORG`, `INFLUXDB_BUCKET` | Push run KPIs to InfluxDB after each run |
| `PROMETHEUS_PUSHGATEWAY_URL`, `PROMETHEUS_JOB_NAME` | Push run KPIs to a Prometheus Pushgateway after each run |
| `TESTO_SLACK_WEBHOOK_URL`, `TESTO_TEAMS_WEBHOOK_URL` | Webhooks for `testo notify` and the `slack` / `teams` reporters |
| Reporter tokens | e.g. `REPORTPORTAL_TOKEN`, `SLACK_WEBHOOK` via `${env:…}` in YAML |

---

## Reporter types (`reporters:` / `--reporter`)

Supported: `allure`, `extent`, `reportportal`, `slack`, `teams`, `testbeats`, plus any installed [reporter plugin](#plugins). Configured in root `testosterone.yaml`; outputs often under `reports/` (see repo `testosterone.yaml` for examples).

`slack` and `teams` post the [`testo notify`](#testo-notify) message for the run that just finished. They need a recorded run (not `--no-persist`):

```yaml
reporters:
  - type: slack
    webhook: ${env:SLACK_WEBHOOK_URL}   # default: $TESTO_SLACK_WEBHOOK_URL
    when: failure                        # failure | change | always
    title: Nightly API tests             # default: the cycle name
    report_url: ${env:CI_JOB_URL}        # optional "View run" link
```

`testbeats` posts counts only, to the `slack_webhook` / `teams_webhook` options.

After `testo run`, terminal hints may point to `./reports/allure`, `./reports/extent`, etc.

### Official documentation

| Reporter | Reference |
|----------|-----------|
| Allure Report 3 | https://allurereport.org/docs/v3/ |
| ReportPortal | https://reportportal.io/docs/api-development/ |
| ReportPortal agents | https://reportportal.io/docs/log-data-in-reportportal/test-framework-integration/ |

## Plugins

A Python package can add a test runner (`equipment:`) or a reporter (`reporters:`) without changing Testosterone, through two entry point groups:

```toml
# the plugin's pyproject.toml
[project.entry-points."testo.frameworks"]
unittest = "testo_example_plugin:UnittestAdapter"

[project.entry-points."testo.reporters"]
json-summary = "testo_example_plugin:JsonSummaryReporter"
```

After `pip install`, the names work in `testosterone.yaml` and `--reporter`, and `testo plugins` lists them.

| Group | Value | Interface |
|-------|-------|-----------|
| `testo.frameworks` | A class or factory returning an adapter | `FrameworkAdapter` in [`testo_core/frameworks/base.py`](../../testo_core/frameworks/base.py): `name`, `results_subdir()`, `build_argv(target_repo, results_dir, stage_args, workers)` and `native_report(stage_dir)` |
| `testo.reporters` | A `BaseReporter` subclass | [`testo_core/reporting/reporters/base.py`](../../testo_core/reporting/reporters/base.py): `reporter_type` and `publish(results, context, console)`; YAML keys other than `type` arrive as `self._options` |

- The stage process runs `build_argv`'s command in `target_repo`. Tests are counted from Allure `*-result.json` files written to `results_dir` (also exported as `TESTO_SHARED_ALLURE_RESULTS_DIR`), or from the stage's `junit_xml` globs.
- A plugin stage defaults to `tier: unit` and gets `workers` passed through unchanged.
- Built-in names always win; a plugin that reuses one, or a second plugin with the same name, is ignored with a warning.
- Plugins are imported only when a stage or reporter uses them, or by `testo plugins --check`.
- The API's ad-hoc run endpoint (`POST /api/v1/adhoc-executions`) accepts built-in frameworks only.

[`examples/plugin`](../../examples/plugin/README.md) is a complete plugin with one of each. Design: [Plugin API](../Specs%20&%20ADRs/Plugin%20API%20-%202026-10-19.md).

## Related operational docs

- [CI-CD Pipeline Setup](../Processes%20&%20Guides/CI-CD%20Pipeline%20Setup.md) — `testo run --ci` in CI wrappers
- [Delta Comparison Policy](../Specs%20&%20ADRs/Delta%20Comparison%20Policy.md) — semantics for `testo diff` / `testo summary`
