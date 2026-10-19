---
type: index
status: current
created: 2026-06-25
updated: 2026-10-19
---

# Testosterone docs

Design notes for Testosterone (`testo-core`, CLI `testo`).
New here? Start with [ARCHITECTURE.md](../ARCHITECTURE.md) and [README.md](../README.md).

The notes are plain markdown and also open as an Obsidian vault. Dated plans, audits and phase checklists from earlier development are in the [Archive](Archive/README.md).

## Architecture

- [System Diagram](Architecture/System%20Diagram.md): the architecture picture, what each part does, and where every other diagram lives
- [Architecture Overview](Architecture/Architecture%20Overview.md): component flowchart, modules, engine, adapters, artifact layout, persistence
- [Deep Dive - Execution Logic](Architecture/Deep%20Dive%20-%20Execution%20Logic.md): session init, the subprocess loop, teardown

## Using the CLI

- [Setup Prompts](Prompts%20&%20Snippets/Setup%20Prompts.md): copy-paste prompts for an AI assistant to install Testosterone in your project, write `testosterone.yaml`, add CI and open the UI
- [Command Reference](CLI%20Commands/Command%20Reference.md): every `testo` command, flag and exit code, and the `testosterone.yaml` schema
- [Troubleshooting and Error Codes](CLI%20Commands/Troubleshooting%20and%20Error%20Codes.md): exit codes, NDJSON errors, debugging playbook

## Testing and CI

- [QA Strategies](Testing%20Workflows/QA%20Strategies.md): how runs are defined, triggered, logged, and how the orchestrator tests itself
- [CI-CD Pipeline Setup](Processes%20&%20Guides/CI-CD%20Pipeline%20Setup.md): GitHub Action, GitLab template, runner image, test tiers
- [E2E Harness Operations Guide](Processes%20&%20Guides/E2E%20Harness%20Operations%20Guide.md): the external E2E harness
- [GitLab Pages Demo](Processes%20&%20Guides/GitLab%20Pages%20Demo.md): the GitHub and GitLab Pages demo pipeline

## Releasing

- [Publishing to PyPI](Processes%20&%20Guides/Publishing%20to%20PyPI.md) · [Publishing Docker Images](Processes%20&%20Guides/Publishing%20Docker%20Images.md) · [Publishing to Artifactory](Processes%20&%20Guides/Publishing%20to%20Artifactory.md)
- [Changelog policy](changelog_automation_policy.md)

## Decisions and direction

- [Specs & ADRs](Specs%20&%20ADRs/README.md): design decisions that still describe the code
- [Product Roadmap](Roadmap%20&%20Strategy/Product%20Roadmap.md): current state and next steps
- [Technical Debt Tracker](Testing%20Workflows/Technical%20Debt%20Tracker.md): open backlog
- [Agent Context Guide](Prompts%20&%20Snippets/Agent%20Context%20Guide.md): which note to read before changing what (for AI coding agents)

## The vault itself

- [Vault schema](CLAUDE.md): frontmatter, linking and the ingest / query / lint rules for these notes
- [Vault log](log.md): record of changes to the vault's structure
