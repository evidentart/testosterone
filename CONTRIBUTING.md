# Contributing to Testosterone

## Setup

```bash
git clone https://github.com/taltal-beep/testosterone.git
cd testosterone
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pre-commit install   # one-time; runs ruff + changelog-format checks before each commit
```

See [README Quickstart](README.md#quickstart) for the full local infrastructure setup (optional Postgres, frontend).

Everyone taking part is expected to follow the [Code of Conduct](CODE_OF_CONDUCT.md). Found a security problem? Report it privately as described in [SECURITY.md](SECURITY.md), not in a public issue.

## Finding something to work on

Issues labelled [`good first issue`](https://github.com/taltal-beep/testosterone/labels/good%20first%20issue) are small and self-contained, with the files to touch named in the issue. Comment on one to claim it. For anything bigger, open an issue or a discussion first so the approach can be agreed before you write the code.

## Before opening a PR

- **Tests**: `pytest -q -m "tier_fast and not quarantined" --no-cov` — the fast local path for the required check in CI (`ci.yml`'s `test` job). CI runs the same selection with coverage on and fails below 65% line + branch coverage (gate set in `pytest.ini`); drop `--no-cov` to check that locally (~15 s slower).
- **Lint, format, types**: `ruff check .`, `ruff format --check .` and `mypy testo_core testo_api` — all three are blocking in CI (`ci.yml`'s `format` job). Run `ruff format .` to fix formatting.
- **Frontend**: `npm --prefix frontend run typecheck && npm --prefix frontend test` — both blocking in CI (`ci.yml`'s `frontend` job).
- **API contract**: the React app's request/response types are generated from FastAPI's OpenAPI schema. After changing a model in `testo_api/models.py` (or a route's `response_model`), run `python scripts/export_openapi.py && npm --prefix frontend run gen:api` and commit `frontend/openapi.json` and `frontend/src/lib/api-schema.ts`. CI fails if either is stale.
- **Commit messages**: [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, `test:`, `chore:`, `docs:`, ...) — enforced by `commitlint` in CI against `commitlint.config.js`.
- **Changelog**: add an entry under `## [Unreleased]` in `CHANGELOG.md` (Keep a Changelog format) for any non-doc change. CI's `changelog_required` job fails PRs that skip this — apply the `no-changelog` label if the change genuinely doesn't warrant an entry (pure test/CI/refactor with no user-facing effect).
- **Behave features**: always target explicitly (`behave features/smoke.feature`), never rely on cwd auto-discovery — see [Command Reference](docs/CLI%20Commands/Command%20Reference.md).

## Docs

If your change alters CLI arguments, exit codes, `testosterone.yaml` config parsing, or a workflow lifecycle, update the matching note under `docs/` (the Obsidian vault — start at [docs/Index.md](docs/Index.md)) in the same PR. Large or multi-step changes (migrations, refactors, new architecture) should also get an entry in `docs/Specs & ADRs/` or `docs/Testing Workflows/Technical Debt Tracker.md` as appropriate.

## Files for AI coding agents

`CLAUDE.md`, `docs/CLAUDE.md` and `.claude/` hold instructions and hooks for AI coding agents working in this repository (which notes to read first, the docs vault rules, the pre-push review hook). They describe the same conventions as this file; you don't need an AI agent to contribute, and you can ignore them.

## PR review

Code review runs as a local pre-push hook (`.claude/settings.json`), not in CI — see commit `990be121` for why the earlier CI-based review was dropped.
