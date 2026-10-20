---
type: spec
status: current
created: 2026-10-19
updated: 2026-10-19
---

# Playwright Adapter - 2026-10-19

## Context

Playwright already ran as a `command` stage, but only if the user knew to add `--reporter=junit`, point `PLAYWRIGHT_JUNIT_OUTPUT_FILE` (or the config) at a file and repeat that path in `junit_xml`. Its HTML report was lost between runs, and `workers` did nothing. Playwright is the most common browser test runner people ask about, so it gets its own equipment.

## Decision

- `equipment: playwright` maps to `PlaywrightAdapter` (`testo_core/frameworks/playwright_adapter.py`). It runs `npx playwright test <args>` and adds `--reporter=list,junit,html` and `--workers=N`, each only when `args` don't already set it.
- Two optional adapter hooks, read with `getattr` by the executor so other adapters are unaffected:
  - `stage_env(target_repo=, results_dir=)` returns env that depends on the stage's paths. Playwright uses it for `PLAYWRIGHT_JUNIT_OUTPUT_FILE`, `PLAYWRIGHT_HTML_OUTPUT_DIR` (the stage's artifacts dir) and `PLAYWRIGHT_HTML_OPEN=never`. The stage's own `extra_env` still wins.
  - `default_junit_xml` gives the JUnit globs to import when the stage sets no `junit_xml`. The import is the same one `command` stages use ([Command Adapter and JUnit Import](Command%20Adapter%20and%20JUnit%20Import%20-%202026-09-25.md)).
- `native_report()` returns the HTML report, so it is copied to `static/history/<run_id>/native_reports/playwright/` and linked from the run in the UI.
- Default tier `e2e`; `playwright` is in `PARALLEL_FRAMEWORKS`; `doctor` and `config validate --check-executables` look for `npx`.

## Consequences

- The target project installs `@playwright/test` and its browsers itself; Testosterone adds no Node dependency.
- `workers` (default 4) overrides `workers` in `playwright.config`. Put `--workers` in `args` to keep the config's value.
- The JUnit file is written to `test-results/testo-junit.xml` in the target repo, Playwright's own output folder, which projects usually ignore already.

Usage: [Architecture Overview § frameworks](../Architecture/Architecture%20Overview.md#testo_coreframeworks).
