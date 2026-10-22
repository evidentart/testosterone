---
type: reference
status: current
created: 2026-06-25
updated: 2026-10-22
---

# Troubleshooting and Error Codes

[Command Reference](Command%20Reference.md)

Practical guide for debugging `testo` failures: exit codes, CI payloads, log locations, and step-by-step fixes. Implementation detail: [Deep Dive - Execution Logic](../Architecture/Deep%20Dive%20-%20Execution%20Logic.md).

---

## Exit code reference

Defined in `testo_core/engine/exit_codes.py` as `EngineExitCode`. The process exit code is propagated via `typer.Exit` in command handlers and `testo_core/cli/app.py` `main()`.

| Code | Enum | Meaning | Typical causes |
|------|------|---------|----------------|
| `0` | `SUCCESS` | Run completed; all stage return codes zero | Pass; or cycle **skipped by trigger** (resting) |
| `1` | `DOMAIN_FAILURE` | Tests or framework reported failure | Non-zero pytest/behave/behavex exit |
| `2` | `INVALID_INPUT` | Config or CLI validation failed | Missing YAML, bad schema, unknown cycle, tag mismatch |
| `3` | `INFRA_FAILURE` | Infrastructure / runtime dependency failure | Return code `127` (missing binary); `124` (stage timeout); report DB archive failure; Docker/Allure CLI failures |
| `4` | `INTERNAL_ERROR` | Unexpected engine error | Orchestrator `internal_failure` on uncaught engine exception; empty return-code list in classifier |

### Classification logic

`classify_exit_code(returncodes, infra_error=None, internal_failure=False)`:

- `infra_error` set → **3**
- `internal_failure` set → **4** (orchestrator caught an unexpected engine exception; not a framework subprocess exit)
- Empty `returncodes` → **4**
- Any stage return code in `(124, 127)` → **3**
- Any other non-zero return code → **1**
- Otherwise → **0**

Stage timeouts emit `returncode=124` and `timed_out=true`. Engine internal failures set `internal_failure=true` on the stage result (NDJSON `stage_finished` includes both fields).

### Commands that use exit codes

| Command | Uses `EngineExitCode` |
|---------|------------------------|
| `testo run` | Yes — engine result |
| `testo ingest` | Yes — engine result locally; with `--server`, the server's result, or **3** when the upload fails (unreachable, wrong token) |
| `testo report` | Yes — missing artifacts, Allure failure, I/O errors |
| `testo doctor` | **2** on hard FAIL; **0** on pass |
| `testo config validate` | **2** on failure (literal in some handlers) |
| `testo clean` | **2** / **3** |
| `testo config db` | **2** / **3** |

---

## Error output channels

### Interactive (default)

- Config errors: `[fail]error: <message>`
- Run failure: `Run exited with code <N>.`
- Success: `Run finished successfully.`
- Trigger skip: Rich panel titled **Resting**
- Stage failure: post-mortem panel with `output_tail` and log path

### CI (`--ci`)

All machine-readable lines go to **stdout** as NDJSON (one JSON object per line). No Rich markup.

**Config error:**

```json
{"event":"error","code":"invalid_input","message":"cycle 'foo' not found. Available: bar, baz."}
```

**Trigger evaluation:**

```json
{"event":"cycle_trigger","cycle":"sample-pytests","status":"resting","reason":"...","matched":[],"mode":"git"}
```

**Dry run skip** (roadmap — no `--dry-run` CLI flag exists yet, see [Command Reference](Command%20Reference.md)):

```json
{"event":"dry_run","cycle":"sample-pytests","status":"skipped","reason":"trigger"}
```

Stdout is reserved for NDJSON in CI mode — do not pipe other tools onto the same stream without filtering.

### Artifact mirror

`artifacts/<cycle>/events.ndjson` duplicates engine events (`plan_started`, `stage_started`, `stage_finished`, `plan_finished`, `plan_aborted`) even in interactive mode. Use this file when CI logs are truncated.

---

## NDJSON event schema (`testo run --ci`)

Emitted by `CIRenderer` and `_NdjsonRecorder`.

### `plan_started`

```json
{"event":"plan_started","plan":"sample-pytests","stage_count":1}
```

### `stage_started`

```json
{"event":"stage_started","stage":"pytest-sample","framework":"pytest","index":1,"count":1}
```

### `stage_finished`

```json
{
  "event":"stage_finished",
  "stage":"pytest-sample",
  "framework":"pytest",
  "returncode":1,
  "duration_s":12.4,
  "log_path":"/path/artifacts/sample-pytests/pytest-sample/run.log",
  "timed_out":false
}
```

When the executor sets an error string (timeout, missing binary):

- `error` may appear on the in-memory result; the NDJSON mirror in `orchestrator` includes `error` when present on `StageResult`. The mirror also carries `internal_failure` (true only for orchestrator-caught engine exceptions). `CIRenderer` stdout omits both keys.

### `plan_finished`

```json
{
  "event":"plan_finished",
  "plan":"sample-pytests",
  "aggregate_returncode":1,
  "exit_code":1,
  "duration_s":12.5,
  "stages":[...],
  "error":null
}
```

### `plan_aborted` (engine `fail_fast`)

Written to the artifact `events.ndjson` when `run_plan(fail_fast=True)` aborts after a failing stage. Reachable today via the API layer (`POST /api/v1/cycles/{cycle}/executions`); the `--fail-fast` CLI flag is a roadmap item.

```json
{"event":"plan_aborted","plan":"sample-pytests","reason":"fail_fast","completed_stages":1}
```

---

## Log and artifact map

```text
artifacts/<cycle>/
  events.ndjson              # Full event timeline
  plan_result.json           # Summary JSON (best-effort)
  <stage>/
    run.log                  # Complete subprocess stdout+stderr
    allure-results/
      pytest/ | behave/ | behavex/
        *-result.json
```

**Post-run reports** (when configured): often under `reports/allure/`, `reports/extent/`, etc. — see `testosterone.yaml` `reporters:`.

**Report DB archives:** require `testo-core[db]` and `database.url` or `DATABASE_URL`; UUID from `testo report list`.

---

## Failure-point playbook

### Config not found (exit 2)

**Symptoms**

```text
error: no testosterone.yaml / testosterone.yml / pyproject.toml [tool.testosterone] found under /your/cwd
```

**Debug**

1. Confirm working directory: `pwd`
2. Or pass explicit path: `testo run --cycle <name> --config /path/to/testosterone.yaml`
3. CI: parse NDJSON `{"event":"error","code":"invalid_input",...}`

**Fix**

- Add `testosterone.yaml` at repo root or set `--config`
- Use `testo config init` / `testo init` to scaffold

---

### Invalid YAML or schema (exit 2)

**Symptoms**

- `invalid YAML in ...`
- `unknown equipment 'foo'`
- Pydantic-style validation messages from loader

**Debug**

```bash
testo config validate
testo config validate --config path/to/testosterone.yaml
```

**Fix**

- Correct syntax and keys per [Architecture Overview § Configuration as the single source of truth](../Architecture/Architecture%20Overview.md#configuration-as-the-single-source-of-truth)
- Supported frameworks: `pytest`, `behave`, `behavex`

---

### Unknown cycle or no enabled stages (exit 2)

**Symptoms**

- `cycle 'x' not found. Available: ...`
- `plan 'x' has no stages enabled in this environment`

**Debug**

```bash
testo cycles list
testo cycles show <name>
```

**Fix**

- Use a defined cycle name from `cycles:` in YAML
- Check stage `if_expr` — stage may be disabled for current env vars

---

### Tag filter mismatch (exit 2)

**Symptoms**

- `cycle 'foo' does not include tag 'smoke'`
- `No cycles match --tag 'smoke'`

**Fix**

- Add tag to cycle in YAML, or run without `--tag`
- For `testo run --cycle all --tag smoke`, ensure at least one cycle lists `smoke` under `tags:`

---

### Trigger skip — resting (exit 0)

**Symptoms**

- Panel: `Cycle <name> skipped: No stimulus detected...`
- NDJSON: `"status":"resting"` on `cycle_trigger`
- No stages run; no new failures

**Debug**

- Inspect `trigger:` block on the cycle (paths, `since_ref`)
- Snapshot state under `artifacts/` for the cycle

**Fix**

- Expected behavior when no matching file changes
- Force run: `testo run --cycle <name> --force`

---

### Framework executable missing (exit 3 or 1)

**Symptoms**

- Stage `error`: `executable not found: ...`
- Stage `returncode`: **127** → should yield exit **3** at plan level
- `testo doctor` shows `CLI pytest FAIL — not found on PATH`

**Debug**

```bash
testo doctor
cat artifacts/<cycle>/<stage>/run.log
```

**Fix**

- Install framework in active venv: `pip install pytest`; for `behave` / `behavex` stages, `pip install 'testo-core[bdd]'` (since 1.2 a plain `pip install testo-core` leaves them out, and the stage error says so)
- Ensure CI image activates the same venv before `testo run`

---

### Stage timeout (exit 3)

**Symptoms**

- `timed_out: true` and `returncode: 124` in `stage_finished` NDJSON / `events.ndjson`
- `error`: `stage exceeded timeout_s=<N>`
- Truncated or abrupt end in `run.log`
- Process exit code **3** when timeout is the only failure

**Debug**

```bash
# Inspect event file
grep timed_out artifacts/<cycle>/events.ndjson
tail -100 artifacts/<cycle>/<stage>/run.log
```

**Fix**

- Increase `timeout_s` in `defaults:` or per-stage in YAML
- Fix hanging test; use `testo run --stream` locally to watch live output

---

### Test / assertion failures (exit 1)

**Symptoms**

- Non-zero stage `returncode` (often 1)
- Framework traceback in `run.log`
- Allure `*-result.json` with failed status

**Debug**

```bash
testo run --cycle <name> --stream    # live output
testo report --cycle <name>          # Allure dashboard
```

**Fix**

- Address failing tests in `target_repo`
- Use `--fail-fast` to stop after first failing stage

---

### Allure Report 3 CLI missing (exit 3 on report)

**Symptoms**

- `testo report` prints failure from `AllureReporter`
- `testo doctor` shows `Allure Report 3 CLI WARN`

**Debug**

```bash
node --version
testo doctor
ls node_modules/.bin/allure   # after npm install in repo root
```

**Fix**

- Install **Node.js 18+**, then in the Testo repo root: `npm install` (installs the `allure` npm package pinned in `package.json`)
- Or set `TESTO_ALLURE_BIN` to a custom Allure 3 executable
- Or use `testo report --format json` which does not need the Node CLI

**Command mapping (Allure 2 → 3)**

| Allure 2 (Java) | Allure 3 (Node) |
|-----------------|-----------------|
| `allure generate <dirs> -o <out> --clean` | `allure generate <dirs> -o <out> --config ./allurerc.mjs` |
| `allure generate … --single-file` | `allure awesome <dirs> -o <out> --single-file` |
| `allure serve <dirs>` | `allure open <dirs> --port <n>` (generate + serve) |
| `allure open <reportDir>` | `allure open <reportDir> --port <n>` |

Hosted reports: `{ALLURE_SERVER_URL}/reports/<run_id>/index.html` (any static file server).

See also: [Allure Report 3 docs](https://allurereport.org/docs/v3/), [Docker Engine](https://docs.docker.com/engine/).

---

### No artifacts for report (exit 2)

**Symptoms**

```text
no results found under artifacts — run testo run --cycle … first
```

**Debug**

```bash
ls -la artifacts/<cycle>/
find artifacts -name '*-result.json' | head
```

**Fix**

- Run the cycle first: `testo run --cycle <name>`
- Match `--artifacts` path if non-default
- Reporters skipped when no Allure JSON exists (see `run_configured_reporters`)

**Run Detail page shows "No artifacts recorded" / "No reports for this run" despite a passing cycle**: fixed 2026-07-06 — `DbBackend.persist()` never set `snapshot_dir` on the `RunRecord`, so `GET /api/v1/runs/{run_id}/reports` always returned `artifact_links: []`. See [Report Links and Artifacts Missing Fix - 2026-07-06](../Archive/Report%20Links%20and%20Artifacts%20Missing%20Fix%20-%202026-07-06.md). Native Allure/Behave HTML `static_links` still require a `reporters:` block in `testosterone.yaml` — that part is a config gap, not a bug.

---

### Report database / archive failures (exit 3)

**Symptoms**

- `testo report list` fails or doctor DB row FAIL
- No UUID printed after run when archive expected

**Debug**

```bash
testo doctor
echo "$DATABASE_URL"
testo config db show    # if configured
```

**Fix**

- Install extra: `pip install 'testo-core[db]'`
- Set `database.url` in YAML or `DATABASE_URL`
- In CI, archive always runs synchronously (`--ci` ignores `--async-report-db`)
- A failed required archive after a green run exits **3**
- Use `--no-report-db` to skip archive when DB not needed

---

### Reporter partial failure (exit 0)

**Symptoms**

- Tests passed but Slack/ReportPortal/Extent missing
- `[fail]` lines from reporter factory but run still exits 0

**Debug**

- Check reporter-specific env vars (`REPORTPORTAL_TOKEN`, webhooks in YAML)
- Inspect `reports/` output dirs

**Fix**

- Validate `reporters:` block in `testosterone.yaml`
- Run `testo report` separately to isolate Allure vs integrations

---

### Argparse / Typer help (non-engine)

**Symptoms**

- Typer prints help when required options missing (e.g. `testo run` without `--cycle`)
- May not use `EngineExitCode` — often exit **2** from Click/Typer

**Fix**

- Pass required flags per [Command Reference](Command%20Reference.md)

---

## Removed: `uqo run` headless contract

v1.0 shipped a second CLI contract, `uqo run --config <runs.yaml>` with `--ghost`, `--json` and `--stream-json`, backed by a Docker-based runner. It was removed in v1.1 together with the `uqo` command, and CI integrations use `testo run --cycle <name> --ci` (NDJSON events above, `plan_finished` last). Exit codes `0`–`4` mean the same thing in both.

---

## Quick diagnostic commands

```bash
testo doctor
testo config validate
testo cycles list
testo run --cycle <name> --dry-run
testo run --cycle <name> --ci 2>/dev/null | tee run.ndjson
testo run --cycle <name> --stream
```

---

## Related notes

- [Command Reference](Command%20Reference.md) — flags and subcommands
- [Deep Dive - Execution Logic](../Architecture/Deep%20Dive%20-%20Execution%20Logic.md) — session lifecycle and race conditions
- [Technical Debt Tracker](../Testing%20Workflows/Technical%20Debt%20Tracker.md) — known contract gaps and refactors
- [QA Strategies](../Testing%20Workflows/QA%20Strategies.md) — triggers and CI patterns
