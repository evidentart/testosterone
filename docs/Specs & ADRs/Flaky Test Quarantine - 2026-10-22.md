---
type: spec
status: current
created: 2026-10-22
updated: 2026-10-22
related: "Deep Dive - Execution Logic, QA Strategies, Command Reference"
---

# Flaky Test Quarantine - 2026-10-22

## Context

`testo flaky` finds tests whose outcome keeps flipping (see [Open Source Features - 2026-10-19](Open%20Source%20Features%20-%202026-10-19.md)), but finding them doesn't stop them from turning a pull request red. Tools teams adopt for flaky tests (Trunk, Datadog Test Optimization) let you quarantine a test: it keeps running and reporting, but it no longer fails the build while someone fixes it. This was gap 7 in the mainstream adoption review.

## Decision

1. **Config.** A `quarantine:` list in `testosterone.yaml`, at the top level (every cycle) and per cycle (added to the top-level list). An entry is a test name glob, or `{test, reason, owner}`. Unknown keys are rejected. Parsed into `QuarantineRule` on `Plan.quarantine` (`testo_core/config/`). See [QA Strategies](../Testing%20Workflows/QA%20Strategies.md#defining-work-in-testosteroneyaml) for the YAML.
2. **Matching.** `fnmatch` (case-sensitive) against the test's Allure `name` and `fullName`. So `test_checkout*` covers parametrized cases, and `tests.api#*` or `payout rules.*` (JUnit `classname.name`) covers a module or suite.
3. **Gate, in the executor.** After the post-stage hooks, when the plan has rules and the process exited `1`, `testo_core/engine/quarantine.py` reads the stage's `*-result.json` files. If there is at least one failed or broken test and all of them match, the stage's `returncode` becomes `0` and `waived_returncode` keeps the `1`. Exit codes, `--fail-fast` and every consumer then see a passed stage without any change to them.
4. **Still reported.** The result files aren't touched, so the failures count in health %, totals, Allure, Compare and flaky detection as before. `StageResult.quarantined` lists the matched tests and travels to `run.log`, the CLI summary (`PASS (1 quarantined)`), `--ci` NDJSON, `events.ndjson`, `plan_result.json`, the run record's stage metadata and `testo report markdown` (`✅ pass · 1 quarantined`, failing tests marked _(quarantined)_).
5. **`testo flaky`** reads the cycle's rules (auto-discovered config, or `--config`), marks quarantined tests, prints a `quarantine:` snippet for the others, and `--fail-on-flaky` only counts unquarantined ones.

## Options considered

- **Deselect quarantined tests** (`--deselect`, `-k "not ..."`). Rejected: the test stops running, so there's no signal for when it's fixed, and every runner needs its own syntax.
- **Waive any exit code when all failures are quarantined.** Rejected: pytest exits `2` for collection errors and `124`/`127` mean timeout and missing binary. Those failures have no per-test result to match, so only exit `1` ("tests ran, some failed") can be waived.
- **A separate `quarantine.yaml` or a database list edited from the UI.** Deferred: the list belongs in code review next to the cycle it affects. A UI or API to add entries can come later and write the same YAML.
- **Rewrite quarantined results to `skipped`.** Rejected: it would hide the failure from history, Compare and flaky detection.

## Consequences

- A quarantined test can fail forever without anyone noticing unless they read the reports. `reason` and `owner` exist so the list documents who is fixing what; an expiry date is a possible follow-up.
- A stage whose runner exits `1` without writing per-test results (no Allure output, no `junit_xml`) can't be waived: no failed tests are found, so the stage still fails.
- The API and UI don't show quarantine yet (the stage metadata has it, but `StageHealth` in the OpenAPI schema doesn't expose it).
- Tests: `tests/unit/testo_core/test_quarantine.py` (config, matching, the gate through a real `command` stage and `run_plan`), `test_cli_flaky.py` and `test_run_summary_markdown.py`.
