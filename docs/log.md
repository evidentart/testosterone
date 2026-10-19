---
type: log
status: current
created: 2026-10-07
updated: 2026-10-19
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
