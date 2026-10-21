---
type: spec
status: current
created: 2026-10-21
updated: 2026-10-21
related: "Deep Dive - Execution Logic, Architecture Overview"
---

# BehaveX Reports - 2026-10-21

## Context

A BehaveX stage should leave two things: BehaveX's own HTML report (the stage's native report, `behave_reports/report.html`) and Allure results (`allure-results/behavex/`) for summaries, health and every reporter.

The adapter used to get the Allure results by passing BehaveX's `--formatter=...:AllureBehaveXFormatter`. BehaveX skips `report.html` whenever a formatter is set (`behavex.utils.generate_reports`), so BehaveX never wrote it. A post-stage hook re-rendered it from `report.json` inside Testo's process, but with the formatter on, BehaveX put scenario logs in the Allure folder, so the re-rendered report had no scenario logs.

## Decision

1. `BehaveXAdapter.build_argv` passes no formatter. BehaveX writes `report.html`, `report.json` and `outputs/logs/` to `behave_reports/` as it does on its own.
2. After the stage, the executor calls `export_behavex_allure_results` (`testo_core/reporting/behavex_allure.py`). It copies the scenario logs into `allure-results/behavex/` and runs BehaveX's own `AllureBehaveXFormatter` on `report.json`, with BehaveX's `logs` setting pointed there. The output is the same set of files a `--formatter` run writes, with `scenario.log` attachments that resolve.
3. A `--formatter` in a stage's `args` is passed through. The export then sees existing results and does nothing, and `ensure_behavex_report_html` still renders `report.html` from `report.json`, as before.
4. Both steps are best-effort: a failure goes to `run.log` and `StageResult.error`; the exit code still decides the stage.

## Options considered

- **Keep the formatter and only re-render the HTML afterwards** (the old behaviour). Rejected: the HTML loses scenario logs and the native report depends on Testo rebuilding it from BehaveX internals.
- **Run the formatter as a subprocess** (`python -m behavex.outputs.formatters.allure_behavex_formatter`). Rejected: its command line has no output directory option, so it writes to `./output/allure-results`.
- **Write our own `report.json` → Allure converter.** Rejected: BehaveX already ships one, and reusing it keeps attachments, labels and categories identical to a `--formatter` run.

## Consequences

- Allure results for a BehaveX stage appear when the stage ends, not while it runs. Reporters run after the whole cycle, so they still see every result.
- Scenario logs are stored twice (in `behave_reports/outputs/logs/` and in `allure-results/behavex/`). They are small text files.
- `tests/integration/testo_core/engine/test_behavex_reports.py` runs the real `behavex` binary and fails if either report is missing or the HTML is not BehaveX's own.
