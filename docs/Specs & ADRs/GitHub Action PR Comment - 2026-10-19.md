---
type: spec
status: current
created: 2026-10-19
updated: 2026-10-19
---

# GitHub Action PR Comment - 2026-10-19

Part of the post-publish feature batch ([Specs & ADRs](README.md)).

## Context

The GitHub Action exposed the final `plan_finished` event as step outputs and nothing else. To see what failed, a reviewer had to open the job log and read NDJSON. Other test reporters for CI post a summary where reviewers already look: the job summary and the pull request.

## Decision

- **The text is a core feature, not action code.** `testo report markdown` (`testo_core/services/run_summary_markdown.py`) renders a stored run: counts, a per-stage table, failing tests, and per-test changes since the cycle's previous run, reusing the per-test diff Compare uses. Anything (GitLab, a script) can call it; the action is one caller.
- **Job summary on by default, PR comment opt in.** Writing `$GITHUB_STEP_SUMMARY` needs no permission. Commenting needs `pull-requests: write`, so it is `comment-on-pr: "true"`.
- **One comment per cycle, edited in place.** The Markdown starts with `<!-- testo-summary:<cycle> -->`; the action looks for a comment starting with it and edits that instead of posting a new one on every push. Two cycles in one workflow get two comments.
- **Never changes the result.** Rendering or commenting failures (a fork's read-only token, an API error) are `::warning::` lines; the step keeps `testo run`'s exit code. Standard library only (`urllib`), so the action adds no dependency.
- **`package` input.** The action pip-installs `testo-core` by default; `package: .` installs a checkout. This repository's `github_action` CI job uses that to run the action on its own code and comment on its own pull requests, while `getting_started` keeps testing the PyPI release.

## Consequences

- "Since the previous run" needs history from an earlier job. On a fresh runner the first summary says there is nothing to compare with; caching `testo_history.db` or a shared `database.url` fixes that. The CI job runs the cycle twice to exercise the comparison.
- The comment and the job summary describe the latest run of the cycle in the database the action sees, which is the run it just made.
