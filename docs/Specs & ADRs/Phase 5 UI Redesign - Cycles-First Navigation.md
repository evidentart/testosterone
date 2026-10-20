---
type: spec
status: current
created: 2026-07-04
updated: 2026-10-19
---

# Phase 5 UI Redesign — Cycles-First Navigation

**Status:** Shipped 2026-07-04
**Scope:** React frontend + two new API endpoints. Engine/CLI behavior unchanged.

## Why

Post-Phase-3 feedback: the React UI read as an unpolished AI-generated beta — generic slate styling, no design tokens or shared components, the brand logo unused, two overlapping execution pages, and **no way to discover cycles** (users had to type cycle names from memory into a free-text field). The CLI delivered the product promise (straightforward, time-saving); the UI didn't.

## Decisions

### 1. Cycle discovery becomes an API + UI feature
- **`GET /api/v1/cycles`** — list summaries (name, description, stage_count, equipment) via `discover_and_load()`; parity with `testo cycles list`.
- **`GET /api/v1/cycles/{cycle}`** — resolved stage detail (equipment, target repo, args, timeout, workers, trigger); parity with `testo cycles show`. 404 lists valid names; missing config → 503 `infra_failure`.
- Models in `testo_api/models.py` (`CycleSummary`, `CycleListResponse`, `StageSummary`, `CycleDetailResponse`); routes in `testo_api/routes/cycles.py`; contract tests in `tests/contract/api/test_cycles_contract.py`.

### 2. Cycles-first information architecture
- Nav: **Dashboard · Cycles · Runs · Compare**, plus health indicator (`GET /api/v1/health/ready`, polled 30s) and an **Advanced ▾** menu (Legacy Execution, AI Settings). Since [UI Restyle - 2026-10-19](UI%20Restyle%20-%202026-10-19.md) these sit in a desktop sidebar.
- New pages: `frontend/src/features/cycles/CyclesPage.tsx` (card grid, Run buttons), `CycleDetailPage.tsx` (stage breakdown + run panel).
- **RunPanel** (`frontend/src/features/cycles/RunPanel.tsx`) replaces the free-text `LiveExecutionConsole` (deleted): cycle dropdown fed by the new endpoint, core toggles (stream/persist/fail-fast/force), and a progressive-disclosure Advanced accordion covering every `CycleExecutionRequest` field (workers, reporters, report DB, config path, artifacts root). SSE consumption unchanged (locked NDJSON event contract).
- Dashboard shows a **3-step first-run guide** when no runs exist instead of "n/a" KPI walls.
- Route renames with redirects: `/history`→`/runs`, `/runner`→`/cycles`, `/execution`→`/advanced/execution`.

### 3. Design system
- Tailwind tokens in `frontend/tailwind.config.ts`: `ink` neutral scale (near-black until 2026-10-19, now navy; see [UI Restyle - 2026-10-19](UI%20Restyle%20-%202026-10-19.md)), single `brand` blue accent (from the logo), semantic `success`/`danger`/`warn`.
- Shared components in `frontend/src/components/ui/`: Button, Card, Badge, StatusPill, PageHeader, EmptyState, Spinner, KeyValue.
- **Pixel arm-muscle mascot** in `frontend/src/components/mascot/` (crisp-edge SVG grids): logo mark in nav, `MuscleFlex` on run success, `MuscleDefeated` on failure, `MuscleShrug` for empty states. Animations via `muscle-flex`/`muscle-droop` keyframes.

### 4. Doc drift fixed
`docs/CLI Commands/Command Reference.md` documented `testo run --tag/--fail-fast/--dry-run/--reporter` and `testo doctor/clean/watch/init` which are **not implemented** in `testo_core/cli/`. Marked as roadmap callouts; the API layer already accepts `fail_fast`/`reporter_override` so the UI surfaces them.

## Verification (performed at ship time)

- 17 API contract tests + 352 backend unit/contract tests pass.
- 14 Vitest tests pass, incl. RunPanel submit-via-click regression (the old "Run cycle" button bug) and advanced-options→payload mapping.
- Real-browser walkthrough: cycles list renders all 5 sample cycles; `sample-pytests` run streamed stage events over SSE and finished green with the flex mascot; mobile (375px) layout verified.

## Follow-ups

- Implement the roadmap CLI flags (`--fail-fast`, `--reporter`, `--tag`, `--dry-run`) to close the CLI↔API gap in the other direction.
- Historical runs stuck in `RUNNING` status render as "Running" pills on Runs/Dashboard — data hygiene, not a UI defect.
- Consider surfacing `GET /api/v1/cycles?config_path=` in the UI for multi-config workflows.
