---
type: spec
status: current
created: 2026-10-22
updated: 2026-10-22
---

# Alerts Where Developers Look - 2026-10-22

Part of the mainstream-adoption work ([Specs & ADRs](README.md)).

## Context

A run's results reached people in two places: the dashboard, which someone has to remember to open, and the job summary / pull request comment from the [GitHub Action](GitHub%20Action%20PR%20Comment%20-%202026-10-19.md). Tools teams adopt also post to chat, mark failures on the diff, and file flaky tests as work. The `testbeats` reporter already posted to Slack and Teams, but only counts, on every run, with no failing test names and nothing about what changed.

## Decision

- **One message, built from run history.** `testo_core/services/run_alerts.py` builds the alert from the same `RunSummary` as `testo report markdown` (failing tests, per-test changes since the previous run) plus `newly_flaky_tests()`. It lists new regressions, newly flaky tests, failing tests and fixes, 10 names each. Any recorded run can be sent again.
- **Two entry points, same code.** `slack` and `teams` reporters send it right after `testo run` (reporters run after the run is recorded, so `context.run_id` is set). `testo notify --to slack|teams` sends it later, which is what the GitHub Action and any other CI call. `testbeats` stays as it was.
- **Quiet by default.** `when: failure` sends only for a red run or a newly flaky test; `change` sends when the result flipped or a test regressed, got fixed or became flaky; `always` sends every run.
- **"Newly flaky" means this run made it flaky:** flaky in the window ending at the run and not in the window ending at the run before. A flaky test is announced once, not on every run.
- **Webhook URLs are secrets.** They come from `TESTO_SLACK_WEBHOOK_URL` / `TESTO_TEAMS_WEBHOOK_URL` or a `${env:…}` reporter option, never a CLI flag, and errors never include them. The action takes them as `slack-webhook` / `teams-webhook` inputs fed from repository secrets.
- **Annotations use workflow commands, not the Checks API.** `testo report annotations` prints `::error file=…,line=…::` lines; GitHub attaches them to the job's check run and shows them on the diff. That needs no token or permission and works on fork pull requests, so the action does it by default. The line is the first stack-trace frame inside the workspace (pytest `path:line:` and Python `File "…", line N` frames), tried against each stage's `target_repo` because runners print paths relative to it. GitHub keeps 10 error annotations per step, so the rest are counted in one notice.
- **Flaky issues are opt-in action code.** `flaky-issues: "true"` reads `testo flaky --new --json` and opens one issue per test, titled `Flaky test: <name> (<cycle>)` and labelled `flaky-test`, skipping titles that already have an open issue. It needs `issues: write`, so it is off by default. Like the comment, it is standard library `urllib` and never changes the step's exit code.

## Consequences

- Alerts, "newly flaky" and "since the previous run" need history from earlier runs; in CI that means a cached or shared database, the same as the PR comment.
- Annotations only land on a line when the runner writes a stack trace into the Allure results (pytest, Behave). Others are still annotated, just without a file.
- Usage: [Command Reference § testo notify](../CLI%20Commands/Command%20Reference.md#testo-notify), [CI-CD Pipeline Setup](../Processes%20&%20Guides/CI-CD%20Pipeline%20Setup.md).
