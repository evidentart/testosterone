---
type: log
status: current
created: 2026-10-07
updated: 2026-10-22
---

# Vault log

Append-only record of changes to the vault's shape. Rules are in the [vault schema](CLAUDE.md#log).

## 2026-06-25: vault created

Notes moved into `docs/` as an Obsidian vault, and copied once by hand to the GitHub wiki.

## 2026-10-07: restructure for GitHub

Wikilinks converted to relative markdown links, dated plans and checklists moved to `Archive/`, Index, Product Roadmap and Technical Debt Tracker rewritten (pull request 74).

## 2026-10-07: schema, lint and wiki sync

Added the [vault schema](CLAUDE.md), frontmatter on every note, `scripts/docs_vault.py lint` in CI, and a workflow that regenerates the GitHub wiki from `docs/`. The lint found four leftover wikilinks in Architecture Overview, Deep Dive - Execution Logic and GitLab Pages Demo; fixed. The wiki had not changed since 2026-06-24.

## 2026-10-07: decision notes and wiki-only page

Added [Architecture Consolidation - 2026-10-06](Specs%20&%20ADRs/Architecture%20Consolidation%20-%202026-10-06.md) and [Interview Readiness Fixes - 2026-10-07](Specs%20&%20ADRs/Interview%20Readiness%20Fixes%20-%202026-10-07.md). Moved the wiki-only page [GitHub Actions CI and AI Code Review](Archive/GitHub%20Actions%20CI%20and%20AI%20Code%20Review.md) into `Archive/` so the first wiki sync doesn't lose it.

## 2026-10-08: diagrams and gap fill

Added [System Diagram](Architecture/System%20Diagram.md): the architecture image was only embedded in the root README, so it never showed in Obsidian or the wiki. Architecture Overview's text sketch became a Mermaid flowchart. Added [Docs Vault and Wiki Sync - 2026-10-07](Specs%20&%20ADRs/Docs%20Vault%20and%20Wiki%20Sync%20-%202026-10-07.md), the second wave of the interview fixes, and this repo's workflows in CI-CD Pipeline Setup. Fixed two stale claims: 1.0.0 was never published to PyPI, and the PyPI trusted publisher named the old repository.

## 2026-10-19: setup prompts

Added [Setup Prompts](Prompts%20&%20Snippets/Setup%20Prompts.md), copy-paste prompts for adopting Testosterone in another project, linked from Index. Fixed a stale claim in Command Reference: `doctor`, `clean`, `watch` and `init` are registered commands, not roadmap items.

## 2026-10-19: getting started and docs site

Added [Getting Started](Getting%20Started.md), linked from Index, and [Docs Site - 2026-10-19](Specs%20&%20ADRs/Docs%20Site%20-%202026-10-19.md). The vault is now also built as a MkDocs site under `/docs/` of the Pages demo; the notes themselves did not change shape.

## 2026-10-19: post-publish features note

Added [Open Source Features - 2026-10-19](Specs%20&%20ADRs/Open%20Source%20Features%20-%202026-10-19.md), the decision record for the Tier 3 feature pull requests (flaky test detection first).

## 2026-10-19: GitHub Action PR comment note

Added [GitHub Action PR Comment - 2026-10-19](Specs%20&%20ADRs/GitHub%20Action%20PR%20Comment%20-%202026-10-19.md), linked from the Specs & ADRs README.

## 2026-10-19: plugin API

Added [Plugin API - 2026-10-19](Specs%20&%20ADRs/Plugin%20API%20-%202026-10-19.md) and a Plugins section in [Command Reference](CLI%20Commands/Command%20Reference.md#plugins).

## 2026-10-19: Playwright adapter

Added [Playwright Adapter - 2026-10-19](Specs%20&%20ADRs/Playwright%20Adapter%20-%202026-10-19.md).

## 2026-10-19: UI restyle

Added [UI Restyle - 2026-10-19](Specs%20&%20ADRs/UI%20Restyle%20-%202026-10-19.md) to Specs & ADRs and pointed the Phase 5 note at it for the sidebar and the navy tokens.

## 2026-10-21: BehaveX reports

Added [BehaveX Reports - 2026-10-21](Specs%20&%20ADRs/BehaveX%20Reports%20-%202026-10-21.md) to Specs & ADRs.

## 2026-10-22: Ingest and team server

Added [Team Server](Processes%20&%20Guides/Team%20Server.md) to Processes & Guides and [Ingest and Team Server - 2026-10-22](Specs%20&%20ADRs/Ingest%20and%20Team%20Server%20-%202026-10-22.md) to Specs & ADRs, both linked from Index or their hub.

## 2026-10-22: Playwright JSON import

Added [Playwright JSON Import - 2026-10-22](Specs%20&%20ADRs/Playwright%20JSON%20Import%20-%202026-10-22.md) to Specs & ADRs.
