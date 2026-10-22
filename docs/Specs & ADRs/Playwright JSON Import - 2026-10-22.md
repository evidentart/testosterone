---
type: spec
status: current
created: 2026-10-22
updated: 2026-10-22
---

# Playwright JSON Import - 2026-10-22

## Context

Most end-to-end testing today is Playwright in JavaScript and TypeScript repos. `testo ingest` and `equipment: playwright` both read Playwright through its JUnit reporter, which keeps only each test's last attempt. A test that failed and then passed on retry looks like a plain pass, the earlier error is gone, and the traces, screenshots and videos Playwright saved are not linked to anything. Retries and traces are exactly what people debugging a red Playwright run need, and the JSON reporter has all of them.

## Decision

- `testo_core/reporting/playwright_import.py` converts a Playwright JSON report (`--reporter=json`) into Allure results. The JUnit importer hands it every matched file that ends in `.json`, so `junit_xml` globs, `testo ingest` and the post-stage hook all accept Playwright JSON with no new option. Everything after that point (summaries, history, Compare, `testo flaky`, reporters) is unchanged.
- **One result per test, attempts as steps.** Totals count tests, not attempts. Each attempt is an Allure step with its own status, duration, error and attachments, so the Allure report shows what happened on every try.
- **Status.** Playwright's `expected` → passed (skipped when skipped), `flaky` → passed with `statusDetails.flaky` set and the first failure's message, `skipped` → skipped, `unexpected` → failed (broken when interrupted). A timeout is a failure, as Playwright reports it.
- **Identity.** `fullName` is `file › describe › title [project]`, so the same test in two Playwright projects is two tests. The project and the attempt count are Allure parameters, `@tags` become Allure tags.
- **Attachments.** Traces, screenshots, videos, `error-context.md` and `testInfo.attach()` bodies are copied next to the result as Allure attachments. Files are read only from inside the stage's `target_repo` (for `testo ingest`, `--repo`). Playwright writes absolute paths, so a report made on another machine is matched by the tail of each path under the repo, which makes a CI artifact downloaded to a laptop work. Missing, outside or oversized (over 50 MB) files are skipped and logged, never fatal.
- **`equipment: playwright`** now adds `--reporter=list,json,html` and writes the JSON report to `test-results/testo-results.json`. Its default reports are alternatives: the executor imports the first one that was written (JSON, else `test-results/testo-junit.xml` for a stage that sets its own `--reporter=junit`), so the same tests are never counted twice.
- **Server uploads.** `testo ingest --server` uploads `.json` files as they are, and `POST /api/v1/ingest` keeps the suffix so the server reads them the same way. Attachment files are not uploaded.

## Consequences

- Flaky Playwright tests count as passed, like Playwright itself counts them; the flaky flag and the failed attempt are visible in the Allure report. `testo flaky` still works from history across runs.
- Testosterone's own UI does not show attachments yet. They are in the Allure results, so `testo report allure` shows them, and Playwright's HTML report stays the run's native report for `equipment: playwright`.
- Traces for uploaded runs stay on the CI runner. Uploading them would need a size budget on the server; left for later.
- The JSON report can be large for big suites (it includes stdout). It is read once per run.

Builds on [Command Adapter and JUnit Import](Command%20Adapter%20and%20JUnit%20Import%20-%202026-09-25.md) and [Playwright Adapter](Playwright%20Adapter%20-%202026-10-19.md).
