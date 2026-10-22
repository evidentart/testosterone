---
type: guide
status: current
created: 2026-05-02
updated: 2026-10-22
---

# CI Integrations

Pre-packaged CI wrappers keep orchestration in `testo_core`: they install `testo-core`, run `testo run --ci`, and keep its machine output.

## Architecture boundary

- Execution is `testo run` → `CycleRunService` → `engine.run_plan()`, the same path as a local run and an API execution.
- CI wrappers are thin adapters that only prepare flags and consume the NDJSON stream.
- CI provenance is detected from the environment by `DbBackend` (`testo_core/services/ci_provenance.py`) and stored on the run record; repository adapters stay provider-agnostic.

## Output contract in CI

`testo run --ci` writes one JSON object per line on stdout (`plan_started`, `stage_started`, `stage_finished`, `plan_finished`, plus `cycle_trigger` / `error` when relevant). The last line is `plan_finished` with `exit_code` and per-stage results. Exit codes `0`–`4`: [Troubleshooting and Error Codes](../CLI%20Commands/Troubleshooting%20and%20Error%20Codes.md).

v1.0's "ghost mode" (`uqo run --config … --ghost/--json/--stream-json` and a summary JSON) was removed in v1.1 together with the Docker-based headless runner it drove.

## Canonical CI provenance fields

Run records written in CI include (when the provider exposes them):

- `ci_provider` (`github`, `gitlab`, `buildkite`, `circleci`, `jenkins`, `azure_pipelines`, `generic`)
- `ci_pipeline_id`
- `ci_job_id`
- `ci_commit_sha`
- `ci_ref_name`

## GitHub Action

Source lives under `integrations/github-action/` (inputs: `config-path`, `cycle`, `ci-mode`, `persist`, `python-version`, `package`, `job-summary`, `comment-on-pr`, `github-token`; outputs: `exit_code`, `status`, `summary_json`, `summary_path`).

```yaml
permissions:
  contents: read
  pull-requests: write        # only for comment-on-pr
steps:
  - uses: taltal-beep/testosterone/integrations/github-action@v1
    with:
      cycle: smoke
      comment-on-pr: "true"
```

After a persisted run the action renders it with `testo report markdown` and writes it to the job summary (`job-summary`, default on). With `comment-on-pr: "true"` on `pull_request` events it keeps one comment per cycle on the pull request, found by its hidden marker and edited on later pushes. Both are best-effort: an error, such as a fork's read-only token, is a workflow warning and never changes the exit code. `package` is what gets pip-installed (`testo-core` by default; `testo-core[bdd]` for cycles with `behave` or `behavex` stages; this repository's own CI passes `.`). The GitLab template's `TESTO_PACKAGE` variable does the same. Design: [GitHub Action PR Comment - 2026-10-19](../Specs%20&%20ADRs/GitHub%20Action%20PR%20Comment%20-%202026-10-19.md).

## GitLab include template

Template lives at `ci/gitlab/testo.gitlab-ci.yml`.

```yaml
include:
  - project: "taltal-beep/testosterone"
    file: "/ci/gitlab/testo.gitlab-ci.yml"

variables:
  TESTO_CYCLE: "smoke"
```

Variables: `TESTO_CONFIG_PATH` (empty = discovery), `TESTO_CYCLE` (empty = the only cycle), `TESTO_PERSIST` (`true` default). Artifacts: `testo-output.ndjson` and `testo-summary.json` (the `plan_finished` line).

## Runner image

`Dockerfile.testo-runner` builds an image whose entrypoint is `testo`. Use it as the CI job image when you want a pinned toolchain; stages run as subprocesses inside that job container. See [Publishing Docker Images](Publishing%20Docker%20Images.md).

## Tiered test harness commands

Tier selection is marker-driven and shared between local runs and GitHub Actions:

- Fast required gate:
  - `python -m pytest -q -m "tier_fast and not quarantined" --maxfail=1 --no-cov`
- Heavy optional gate:
  - `python -m pytest -q -m "tier_heavy and not tier_external" --maxfail=1 --durations=25`
- External nightly/release gate:
  - `python -m pytest -q -m "tier_external and cleanup_required" --maxfail=1 --durations=50`

Reference CI definitions:

- GitHub: `.github/workflows/ci.yml` (unified format → test → deploy pipeline; the fast-required gate lives in its `test` job), `.github/workflows/pr-heavy.yml`, `.github/workflows/nightly-external.yml`, `.github/workflows/release-gate.yml`. Code review runs via a local pre-push hook (`.claude/settings.json`), not in CI.

All tier jobs upload diagnostics artifacts (`logs`, summary JSON, API responses, screenshots when present) on failure, and external suites run with `external-e2e` concurrency isolation.

## This repository's workflows

What runs on Testosterone itself, as opposed to the wrappers above that run it in other projects. Every workflow is under `.github/workflows/`.

| Workflow | Runs on | What it does |
|----------|---------|--------------|
| `ci.yml` | pull request, push to `main`, release | Blocking gates: ruff lint and format, mypy on `testo_core` and `testo_api`; the fast pytest suite with the coverage gate; frontend typecheck, generated API types up to date, vitest and build; `CHANGELOG.md` touched; docs vault lint; the docs site with `mkdocs build --strict`; `examples/getting-started/` through the local GitHub Action, once with the PyPI release and once with this checkout (which also posts the PR comment); builds the sdist and wheel, runs `twine check --strict`, installs the wheel with no extras and runs a cycle (`scripts/package_smoke.sh`). Builds the wheel on a release |
| `commitlint.yml` | pull request | Conventional commit messages |
| `changelog-on-main.yml` | push to `main` | Drafts a `CHANGELOG.md` [Unreleased] entry from the pushed commits with Claude and commits it to `main`; skips when its bot secrets are missing |
| `pages-demo.yml` | push to `main`, nightly | Runs the self-test and fake-api cycles and publishes the read-only UI and the docs site to GitHub Pages ([GitLab Pages Demo](GitLab%20Pages%20Demo.md)) |
| `wiki-sync.yml` | push to `main` touching `docs/` | Regenerates the GitHub wiki from `docs/` ([Docs Vault and Wiki Sync](../Specs%20&%20ADRs/Docs%20Vault%20and%20Wiki%20Sync%20-%202026-10-07.md)) |
| `mirror-to-gitlab.yml` | push to `main` | Mirrors the repo to GitLab when `GITLAB_MIRROR_URL` / `GITLAB_MIRROR_TOKEN` are set |
| `pr-heavy.yml` | labeled pull request, manual | Heavy test tier |
| `nightly-external.yml` | nightly, manual | External test tier |
| `release-gate.yml` | manual | Release checks before publishing |
| `dependabot.yml` (config, not a workflow) | weekly | Grouped dependency update PRs for pip, npm (`/` and `frontend/`) and GitHub Actions, committed as `chore(deps)` with the `no-changelog` label so commitlint and `changelog_required` pass |
| `publish.yml`, `docker-publish.yml`, `artifactory-publish.yml` | GitHub Release published (`publish.yml` and `docker-publish.yml` can also be run by hand for an existing tag) | PyPI, GHCR runner image, JFrog Artifactory ([Publishing to PyPI](Publishing%20to%20PyPI.md), [Publishing Docker Images](Publishing%20Docker%20Images.md)) |
| `move-major-tag.yml` | GitHub Release published (not prereleases), manual | Force-moves the `v<major>` tag (e.g. `v1`) to the release's commit |

## Versioning policy

- GitHub action: publish immutable semver tags (`v1.0.0`, `v1.0.1`, ...), keep `v1` moving to latest stable `v1.x` (done by `move-major-tag.yml`), and recommend SHA pinning for strict supply-chain policies.
- GitLab template: pin `include` to immutable tag or commit SHA in production pipelines.
- Runner image tags:
  - immutable: `v1.x.y`, `sha-<commit>`
  - moving: `v1`, `latest`
- Compatibility rule: `testo-runner:v1.x.y` must embed a `testo-core` `1.x.y` compatible CLI contract (`testo run --ci` NDJSON and exit semantics).

## Official documentation

| Topic | Reference |
|-------|-----------|
| Docker Engine | https://docs.docker.com/engine/ |
| Docker Compose | https://docs.docker.com/compose/ |
| Compose file spec | https://docs.docker.com/compose/compose-file/ |

---
**Context & Links:**
- [QA Strategies § CI and streaming output](../Testing%20Workflows/QA%20Strategies.md#ci-and-streaming-output), [Command Reference](../CLI%20Commands/Command%20Reference.md), [Architecture Overview](../Architecture/Architecture%20Overview.md), [Deep Dive - Execution Logic](../Architecture/Deep%20Dive%20-%20Execution%20Logic.md)
- Gates (v1.0, historical): [Release Checklist - Phase 2 CI Integrations](../Archive/Release%20Checklist%20-%20Phase%202%20CI%20Integrations.md), [Release Checklist - Phase 2 Ghost Mode](../Archive/Release%20Checklist%20-%20Phase%202%20Ghost%20Mode.md)
