---
type: guide
status: current
created: 2026-10-19
updated: 2026-10-22
---

# Getting Started

Add Testosterone to a project you already have, in about five minutes: install it, describe your tests in one file, run them, see what changed, then run the same thing in GitHub Actions. Every command below was run against `testo-core` 1.1.1 from PyPI in a fresh virtualenv.

You need Python 3.11 or newer and a project with tests. The examples use pytest; other runners are at [step 6](#6-add-other-test-runners).

## 1. Install

```bash
python -m venv .venv && source .venv/bin/activate
pip install testo-core pytest
testo --version          # testo 1.1.1
```

`testo-core` is the `testo` CLI. It doesn't install your test runner, so keep installing pytest (or Behave, Jest...) the way your project already does.

## 2. Describe your tests

Create `testosterone.yaml` in the project root. A **cycle** is a named list of **stages**; each stage runs one test command.

```yaml
version: 1
cycles:
  unit:
    description: My unit tests.
    stages:
      - name: unit
        equipment: pytest
        args: [-q, tests]
```

Check it:

```bash
testo config validate    # ok — version=1 cycles=1 ...
testo doctor             # config, runners on PATH, database
```

For autocomplete in VS Code and other editors, put the [`$schema` line](CLI%20Commands/Command%20Reference.md#editor-autocomplete) at the top of the file.

`testo config init` writes a starter file with a `smoke-test` cycle that runs `pytest -q tests`, plus commented-out marker-based pytest and BehaveX examples. Edit its `args` if your tests live outside `tests/`.

## 3. Run it

```bash
testo run --cycle unit
```

You get a panel per stage, a summary table (total, passed, failed, skipped) and the exit code: `0` when everything passed, `1` when a test failed. All exit codes are in [Troubleshooting and Error Codes](CLI%20Commands/Troubleshooting%20and%20Error%20Codes.md).

Each run is recorded in `testo_history.db` (SQLite, next to the config) with its logs under `artifacts/` and a per-run copy of its reports under `.testo/` (set `TESTO_HOME` to put that elsewhere). Add all three to `.gitignore`.

## 4. See what changed

Break a test and run the cycle again, then ask for the difference between the last two runs:

```bash
testo run --cycle unit       # exit 1
testo summary --cycle unit
```

```text
Quality score (pass / total)
  Baseline 100.0%  →  50.0%  Δ -50.0 pp
Regressions & risk
  Kind         Test       Before   After
  regression   test_sub   passed   failed
```

Once a cycle has a few runs, `testo flaky --cycle unit` lists tests that keep flipping between pass and fail.

`testo report list` shows every recorded run and `testo diff <BASELINE_ID> <CURRENT_ID>` compares any two. How deltas are classified is in [Delta Comparison Policy](Specs%20&%20ADRs/Delta%20Comparison%20Policy.md).

## 5. Run it in GitHub Actions

```yaml
# .github/workflows/tests.yml
name: tests
on: [push, pull_request]
jobs:
  tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install pytest            # your project's test dependencies
      - uses: taltal-beep/testosterone/integrations/github-action@v1
        with:
          cycle: unit
          python-version: "3.11"         # same Python as above, so it sees your dependencies
```

The action installs `testo-core`, runs `testo run --ci` (one JSON event per line in the log), writes the results to the job summary and fails the job when the cycle fails. Add `comment-on-pr: "true"` (and `pull-requests: write` permission) to get the same summary as a comment on each pull request. Its inputs and outputs, and the GitLab CI template, are in [CI-CD Pipeline Setup](Processes%20&%20Guides/CI-CD%20Pipeline%20Setup.md).

## 6. Add other test runners

Add stages to the same cycle; they run in order.

```yaml
    stages:
      - name: unit
        equipment: pytest
        args: [-q, tests]
      - name: flows
        equipment: behave
        args: [features/smoke.feature]     # always name the feature files; needs testo-core[bdd]
      - name: web
        equipment: command                 # any runner that writes JUnit XML
        args: [npx, jest, --ci]
        junit_xml: ["reports/junit/*.xml"]
```

`behave` and `behavex` stages need the `bdd` extra: `pip install 'testo-core[bdd]'` (in the GitHub Action, `package: "testo-core[bdd]"`).

Every key (timeouts, workers, triggers on changed paths, reporters such as Allure) is in [Command Reference](CLI%20Commands/Command%20Reference.md). A runner or reporter that isn't built in can come from a [plugin](CLI%20Commands/Command%20Reference.md#plugins) package.

## Already have CI? Record its results instead

If your tests already run somewhere and write JUnit XML (Jest, Vitest, `go test`, JUnit5, pytest's `--junitxml`, ...), skip the YAML and add one step after them:

```bash
pip install testo-core
testo ingest 'reports/**/*.xml' --cycle web-unit
```

The run gets the same history, `testo summary`, `testo flaky` and Compare as a `testo run`. For one history across every CI job and teammate, run the [Team Server](Processes%20&%20Guides/Team%20Server.md) and add `--server https://your-server --token "$TESTO_API_TOKEN"`. Details: [Command Reference § testo ingest](CLI%20Commands/Command%20Reference.md#testo-ingest).

## Next

- **Web UI**: Dashboard, Runs, Compare and AI failure summaries. It runs from a checkout of the repository; see the README's [UI section](https://github.com/taltal-beep/testosterone#ui), or look at the [live demo](https://taltal-beep.github.io/testosterone/).
- **Using an AI coding assistant?** [Setup Prompts](Prompts%20&%20Snippets/Setup%20Prompts.md) are copy-paste prompts that do the steps above for you.
- **How it works**: [System Diagram](Architecture/System%20Diagram.md).
