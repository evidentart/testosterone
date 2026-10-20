---
type: spec
status: current
created: 2026-10-19
updated: 2026-10-20
---

# UI Restyle - 2026-10-19

## Context

The web UI used the near-black, Vercel-like look from [Phase 5 UI Redesign - Cycles-First Navigation](Phase%205%20UI%20Redesign%20-%20Cycles-First%20Navigation.md): flat grey cards and a top nav bar. Taltal asked for the look of a reference image in the style of the "Vision UI" dashboard template: deep navy, glass cards over a blue glow, a floating sidebar with icon tiles, and electric-blue accents.

## Decision

- **Tokens, not per-page rewrites.** `frontend/tailwind.config.ts` remaps the `ink` scale to navy and `brand` to `#0075ff`, so every page that already used the tokens changed with no edits. The font is Plus Jakarta Sans from Google Fonts (`frontend/index.html`), falling back to the system sans.
- **Two surface utilities** in `frontend/src/styles.css`: `glass-card` (cards, KPI tiles, page panels) and `glass-panel` (sidebar). The page background is a fixed navy gradient with a blue radial glow.
- **Sidebar shell.** From the `lg` breakpoint `AppShell.tsx` shows a fixed glass sidebar: the four primary links and an Advanced section (Quick Run, AI Settings), each with an icon tile that turns blue when active, and a "Need help?" card linking to the docs site. A breadcrumb with the demo badge and health dot sits above the page. Below `lg` the old top bar and disclosure menu stay, so the mobile tests and behaviour are unchanged. The desktop Advanced dropdown is gone; its links live in the sidebar.
- **Background art** (added 2026-10-20, Taltal's ask): `frontend/src/components/BackgroundArt.tsx` draws original line art of the testosterone molecule and two vials with a syringe in the brand blue, fixed behind the page at 12 to 16% opacity with a soft glow. It sits under the glass cards, whose blur hides it behind text, so it shows only in the gaps. It is `aria-hidden` and ignores the pointer.
- **Icons** are inline SVGs in `frontend/src/components/ui/icons.tsx` (no icon library). Dashboard KPI cards show one in a blue tile, as the reference does.

Styling only: no route, API or behaviour change.

## Consequences

- New pages get the look by using `Card`, `glass-card` and the `ink`/`brand` tokens; a hard-coded colour will stand out.
- The font loads from Google Fonts at runtime; offline it falls back to the system font.
