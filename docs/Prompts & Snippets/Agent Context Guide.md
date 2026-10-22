---
type: guide
status: current
created: 2026-06-25
updated: 2026-10-22
---

# Agent Context Guide

Map for AI coding agents working on Testosterone (`testo-core`, CLI `testo`): which note to read before touching what, so you don't have to scan the whole codebase. Adopting Testosterone in another project instead? Use the [Setup Prompts](Setup%20Prompts.md).

## Where to look

* **Architecture & flow:** [System Diagram](../Architecture/System%20Diagram.md) is the one-picture view. Before changing execution logic, runtime state or core modules, read [Architecture Overview](../Architecture/Architecture%20Overview.md) and [Deep Dive - Execution Logic](../Architecture/Deep%20Dive%20-%20Execution%20Logic.md). Don't guess the lifecycle phases.
* **CLI changes:** before adding or changing a command, flag or exit code, read [Command Reference](../CLI%20Commands/Command%20Reference.md) and [Troubleshooting and Error Codes](../CLI%20Commands/Troubleshooting%20and%20Error%20Codes.md). `tests/contract/testo_core/test_cli_docs_drift.py` fails if the reference documents a command that doesn't exist. A new `testosterone.yaml` key also goes in `testo_core/config/json_schema.py` (then run `python scripts/export_config_schema.py`).
* **CI and releases:** [CI-CD Pipeline Setup](../Processes%20&%20Guides/CI-CD%20Pipeline%20Setup.md), [QA Strategies § CI and streaming output](../Testing%20Workflows/QA%20Strategies.md#ci-and-streaming-output), and the publishing guides ([PyPI](../Processes%20&%20Guides/Publishing%20to%20PyPI.md), [Docker images](../Processes%20&%20Guides/Publishing%20Docker%20Images.md), [Artifactory](../Processes%20&%20Guides/Publishing%20to%20Artifactory.md)).
* **Team server and `testo ingest`:** [Team Server](../Processes%20&%20Guides/Team%20Server.md) and [Ingest and Team Server - 2026-10-22](../Specs%20&%20ADRs/Ingest%20and%20Team%20Server%20-%202026-10-22.md). `Dockerfile.testo-server`, `deploy/server/` and `scripts/team_server_smoke.sh` change together.
* **Pages demo:** [GitLab Pages Demo](../Processes%20&%20Guides/GitLab%20Pages%20Demo.md) (covers GitHub Pages too).
* **Reporting:** [QA Strategies § How results are logged and surfaced](../Testing%20Workflows/QA%20Strategies.md#how-results-are-logged-and-surfaced) and the reporter section of [Command Reference](../CLI%20Commands/Command%20Reference.md).
* **E2E harness:** [E2E Harness Operations Guide](../Processes%20&%20Guides/E2E%20Harness%20Operations%20Guide.md).
* **Docs vault, wiki and site:** [vault schema](../CLAUDE.md), [Docs Vault and Wiki Sync](../Specs%20&%20ADRs/Docs%20Vault%20and%20Wiki%20Sync%20-%202026-10-07.md) and [Docs Site](../Specs%20&%20ADRs/Docs%20Site%20-%202026-10-19.md). Images go under `docs/assets/` and must be embedded from a note to reach Obsidian and the wiki. A new note gets a `nav` entry in `mkdocs.yml` to show in the site's menu.
* **Getting started:** [Getting Started](../Getting%20Started.md) is tested by `examples/getting-started/` in CI. A change to the commands or config it shows updates both.
* **UI:** the React frontend in `frontend/` is the only UI; its API types are generated from FastAPI's OpenAPI schema.
* **Delta semantics:** [Delta Comparison Policy](../Specs%20&%20ADRs/Delta%20Comparison%20Policy.md).
* **Design decisions:** [Specs & ADRs](../Specs%20&%20ADRs/README.md).
* **Open debt and next steps:** [Technical Debt Tracker](../Testing%20Workflows/Technical%20Debt%20Tracker.md), [Product Roadmap](../Roadmap%20&%20Strategy/Product%20Roadmap.md).
* **History:** dated plans, audits and phase checklists are in [Archive](../Archive/README.md). They describe the code as it was, not as it is.

## Rules

The full conventions (frontmatter, ingest / query / lint, the log) are in the [vault schema](../CLAUDE.md); `python scripts/docs_vault.py lint` checks them.

1. **Read before writing.** Check the relevant note above before refactoring core architecture or changing a CLI argument.
2. **Keep docs in step.** If you change a CLI command, execution state logic or infrastructure setup, update the matching note under `docs/` in the same pull request. Bump the note's `updated` date.
3. **Point, don't paste.** If a note already explains something, link to it instead of repeating it.
4. **Links.** Use standard relative markdown links with spaces encoded as `%20` (e.g. `[Command Reference](../CLI%20Commands/Command%20Reference.md)`), so they work on GitHub and in Obsidian. When you move or rename a note, update the links to it and [Index](../Index.md) in the same change.
