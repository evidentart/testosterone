---
type: guide
status: current
created: 2026-10-19
updated: 2026-10-19
---

# Setup Prompts

Copy-paste prompts for adopting Testosterone in **your own** project with an AI coding assistant (Claude Code, Cursor, Copilot chat and the like). Paste one into the assistant while it has your repository open. Each prompt points the assistant at the note that owns the facts, so the prompts stay short and don't go stale when the docs change.

Working on Testosterone itself instead? Use the [Agent Context Guide](Agent%20Context%20Guide.md).

## Before you start

- **Install source.** The prompts install `testo-core` from PyPI (published since 1.1.1, [Publishing to PyPI](../Processes%20&%20Guides/Publishing%20to%20PyPI.md)).
- **The GitHub Action and GitLab template** in [CI-CD Pipeline Setup](../Processes%20&%20Guides/CI-CD%20Pipeline%20Setup.md) are referenced by the moving `v1` tag. Prompts 4 and 5 write a plain CI job that runs `pip install testo-core` instead, which is easier to adapt to the project's own toolchain.
- **Requirements:** Python 3.11+. Node.js only for HTML reports (`testo report`) and the web UI.

Run order for a new project: 1, 2, then whichever of 3 to 7 you need.

## 1. Install and smoke-check

```text
Install Testosterone (Python package testo-core, CLI `testo`) into this project's
development environment.

- Install it from PyPI into a virtualenv (create .venv with Python 3.11+ if the
  project has none):
    pip install testo-core
  Add the extras I need in brackets after testo-core: [api] for the web UI backend,
  [db] for Postgres/MySQL run history, [metrics] for InfluxDB.
- Pin it the same way the project pins other dev dependencies (requirements-dev.txt,
  pyproject optional deps, etc.). Don't add it to runtime dependencies.
- Verify with `testo --version` and `testo doctor`, and show me the doctor table.
  Explain any FAIL row; WARN and SKIP rows are fine.

Reference: https://github.com/taltal-beep/testosterone/blob/main/README.md
```

## 2. Write testosterone.yaml for this repository

```text
Add a testosterone.yaml at the root of this repository that runs our existing tests
as Testosterone cycles. Read the schema first:
https://github.com/taltal-beep/testosterone/blob/main/docs/CLI%20Commands/Command%20Reference.md
and the "Defining cycles" section of
https://github.com/taltal-beep/testosterone/blob/main/README.md

1. Find every test suite in the repo and how it is run today (pytest, behave,
   behavex, or anything else such as jest, playwright, go test, mvn). Check CI
   files, Makefile, package.json scripts, tox/nox and the README.
2. Propose the cycles before writing them: a fast `smoke` cycle for pull requests
   and a `full` cycle with everything. Each suite becomes one stage.
3. Stage rules:
   - equipment is pytest, behave, behavex or command.
   - Behave/BehaveX stages must name their feature files or directory explicitly in
     args (e.g. [features/smoke.feature]); never rely on cwd auto-discovery.
   - Anything that is not pytest/behave/behavex uses `equipment: command`, puts
     the whole command in args, and lists the JUnit XML it writes in `junit_xml`
     (globs allowed). If that runner doesn't write JUnit XML yet, add its JUnit
     reporter flag or config.
   - Set `tier:` (unit, integration, e2e) when the default from the equipment is
     wrong, so the test pyramid is correct.
   - Add a `trigger: paths:` list only if I ask for change-based skipping.
4. Add artifacts/ and testo_history.db to .gitignore.
5. Run `testo config validate`, then `testo run --cycle smoke` and show me the
   summary. Exit code 1 means tests failed (fine to report); 2 means the config or
   arguments are wrong, 3 an infrastructure problem: fix those and re-run.
```

## 3. Add a non-Python test runner

```text
Add our <runner, e.g. jest / playwright / go test> suite to testosterone.yaml as a
stage with `equipment: command`.

- args is the full argv, e.g. [npx, jest, --ci]. No shell features: if you need
  pipes or env setup, put it in a script and call the script.
- Make the runner write JUnit XML and list its path or glob under junit_xml;
  Testosterone reads results only from there. Configure the reporter in the
  runner's own config rather than in args where possible.
- Pick the right tier (unit, integration or e2e).
- Run the cycle and confirm the stage reports a non-zero test count. Zero tests
  means junit_xml didn't match a file: check the path relative to target_repo.

Background: https://github.com/taltal-beep/testosterone/blob/main/docs/Specs%20&%20ADRs/Command%20Adapter%20and%20JUnit%20Import%20-%202026-09-25.md
```

## 4. Run it in GitHub Actions

```text
Add a GitHub Actions workflow .github/workflows/testosterone.yml that runs the
`smoke` cycle from testosterone.yaml on pull requests and pushes to the default
branch.

- Set up Python 3.11 and whatever toolchains the stages need (Node, browsers, etc.)
  the same way our existing workflows do. Reuse their dependency install steps.
- Install Testosterone from PyPI:
    pip install testo-core
- Run: `set -o pipefail; testo run --ci --cycle smoke | tee testo-output.ndjson`.
  --ci prints one JSON event per line; the job's exit code is testo's (0 pass,
  1 tests failed, 2 bad config, 3 infrastructure, 4 internal error).
- Always (even on failure) save the last plan_finished line as testo-summary.json
  and upload testo-output.ndjson, testo-summary.json and artifacts/ with
  actions/upload-artifact.
- Leave a comment in the workflow: this can become
  `uses: taltal-beep/testosterone/integrations/github-action@v1` with `cycle: smoke`.

Reference: https://github.com/taltal-beep/testosterone/blob/main/docs/Processes%20&%20Guides/CI-CD%20Pipeline%20Setup.md
```

## 5. Run it in GitLab CI

```text
Add a GitLab CI job that runs the `smoke` cycle from testosterone.yaml, modelled on
https://github.com/taltal-beep/testosterone/blob/main/ci/gitlab/testo.gitlab-ci.yml
but adapted to this project.

- Use an image with Python 3.11+ plus whatever the stages need.
- Install it with `pip install testo-core`.
- Run `set -o pipefail; testo run --ci --cycle smoke | tee testo-output.ndjson`,
  write the last plan_finished line to testo-summary.json in after_script, and keep
  testo-output.ndjson, testo-summary.json and artifacts/ as artifacts with
  `when: always`.
- If .gitlab-ci.yml already has stages, add the job to the test stage instead of
  creating a new one.
```

## 6. Open the web UI on my runs

```text
Get the Testosterone web UI running against this project's testosterone.yaml and
run history.

1. Install the API extra into the project's venv:
     pip install "testo-core[api]"
2. Start the API from this repository's root (it finds testosterone.yaml in the
   current directory and reads the run history next to it): `testo-api`.
   Check http://127.0.0.1:8000/api/v1/cycles lists our cycles.
3. The React frontend is not in the Python package. Clone
   https://github.com/taltal-beep/testosterone somewhere outside this repo, then
   `npm --prefix frontend install` and `npm --prefix frontend run dev` in the
   clone. It talks to http://localhost:8000 by default.
4. Open http://localhost:5173, run the smoke cycle from the Cycles page, and
   confirm the run appears under Runs.

Keep the API on 127.0.0.1. If it must listen on another interface, set
TESTO_API_TOKEN first: anyone who can reach the API can run commands on this
machine. Reference: the "UI" section of
https://github.com/taltal-beep/testosterone/blob/main/README.md
```

## 7. Something is failing

```text
Testosterone is failing in this project. Diagnose it:

1. Run `testo doctor` and `testo config validate` and read the output.
2. Re-run the failing cycle with `testo run --cycle <name> --stream` to see each
   stage's output live. Each stage's log is also under artifacts/<cycle>/.
3. Map the exit code using
   https://github.com/taltal-beep/testosterone/blob/main/docs/CLI%20Commands/Troubleshooting%20and%20Error%20Codes.md
   1 means real test failures; 2, 3 and 4 mean the setup is wrong.
4. Tell me the cause and the smallest fix. Fix the setup (config, paths, missing
   tools) yourself; ask me before changing test code.
```

## Optional extras

Short add-ons to paste after any prompt above:

- **Shared run history:** "Store run history in Postgres: set `database.url` in testosterone.yaml with `testo config db --url postgresql+psycopg://…`, install the `[db]` extra, and read the URL from an environment variable in CI."
- **Metrics:** "Push run KPIs to InfluxDB or a Prometheus Pushgateway using the environment variables in the Command Reference's environment table; install the `[metrics]` extra."
- **Reporters:** "Add an `allure` reporter under `reporters:` and run `testo report --cycle smoke --generate-only` to build the HTML report (needs Node.js)."
- **AI failure summaries:** "Enable AI failure summaries in the UI's AI settings page. I'll paste the API key myself; don't write keys into files."
