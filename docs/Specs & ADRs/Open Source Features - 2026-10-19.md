---
type: spec
status: current
created: 2026-10-19
updated: 2026-10-19
---

# Open Source Features - 2026-10-19

## Context

After the first PyPI release (1.1.1) and the [docs site](Docs%20Site%20-%202026-10-19.md), the owner chose to build "Tier 3" of the post-publish list: features that widen who can use Testosterone. Each lands as its own pull request; this note records the decisions behind them.

| Feature | State |
|---------|-------|
| Flaky test detection | This note, below |
| PR comment from the GitHub Action | [GitHub Action PR Comment - 2026-10-19](GitHub%20Action%20PR%20Comment%20-%202026-10-19.md) |
| Plugin API for framework adapters and reporters | Planned |
| More framework adapters | Planned |
| GitLab mirror and CI template | Needs the owner's GitLab account ([GitLab Pages Demo](../Processes%20&%20Guides/GitLab%20Pages%20Demo.md#what-you-have-to-do-on-gitlab)) |

## Flaky test detection

**Decision.** A test is flaky when, within the last `window` runs of one cycle (default 20), it both passed and failed and its outcome changed at least twice. Skipped and unknown runs neither pass nor fail. One change is a plain regression or fix, which Compare and `testo summary` already show; changing back and forth is what points at the test rather than the code. Results are ranked by flip rate (changes over observations minus one).

**Where the data comes from.** Each run record's own artifact snapshot (`static/history/<run_id>/artifacts/`, the Allure `*-result.json` files `DbBackend` copies per run), matched by `historyId` like the per-test diff. No schema change, and it works on every database backend.

**One implementation, three surfaces.** `testo_core/services/flaky_service.py` is called by `testo flaky` ([Command Reference](../CLI%20Commands/Command%20Reference.md#testo-flaky)), `GET /api/v1/analytics/flaky?cycle=` and the Flaky tests card on the cycle page. The static export writes `data/flaky/<cycle>.json`, so the Pages demo shows the fake-api app's `/api/flaky` route flipping across runs.

**Consequences.** Reading every snapshot in the window is linear in runs times tests; fine at the default window, and the API caps `window` at 200. `--fail-on-flaky` lets CI gate on it, but in CI the history only spans runs that share a database or a cached history directory, as in the Pages workflow.
