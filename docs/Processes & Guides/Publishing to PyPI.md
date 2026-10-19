---
type: guide
status: current
created: 2026-07-01
updated: 2026-10-19
---

# Publishing to PyPI

[Index](../Index.md) · [Publishing Docker Images](Publishing%20Docker%20Images.md) · [Publishing to Artifactory](Publishing%20to%20Artifactory.md)

## Overview

`testo-core` is published to PyPI via GitHub Actions using trusted publishing (OIDC). No API tokens are stored in repository secrets.

## Prerequisites

1. **PyPI account**: register at https://pypi.org (2FA is required to publish). There is no Test PyPI step: the build, metadata and clean-install checks run before the upload instead.
2. **Pending trusted publisher** on PyPI, which reserves the name before the first upload: account menu → "Publishing" → "Add a new pending publisher" → GitHub, with
   - PyPI project name: `testo-core`
   - Owner: `taltal-beep`
   - Repository: `testosterone` (renamed from `unified-quality-orchestration-reporting-dashboard`; a publisher registered under the old name must be updated)
   - Workflow: `publish.yml`
   - Environment: `pypi`
3. **GitHub environment**: create `pypi` under the repository's Settings → Environments. Adding yourself as a required reviewer makes the upload wait for a click.

## Publishing flow

1. Create a GitHub Release with a semver tag matching `pyproject.toml` (e.g. `v1.1.1` for `version = "1.1.1"`).
2. The `publish.yml` workflow triggers automatically. Its one job waits for the `pypi` environment's reviewer, then checks out the tag, builds, checks the tag matches the package version, runs `twine check --strict`, installs the wheel with no extras and runs a cycle (`scripts/package_smoke.sh`), publishes with `pypa/gh-action-pypi-publish` over OIDC (no API token), and verifies `pip install`.
3. To publish an existing tag whose automatic run failed (for example after fixing the trusted publisher), run the workflow by hand from the Actions tab with that tag as input. PyPI refuses a version that was already uploaded.
4. The same Release also triggers `docker-publish.yml` (runner image to GHCR; the first push creates a private package, so set its visibility to public once) and `artifactory-publish.yml` (skipped while `ARTIFACTORY_URL` is unset).

The `package` job in `ci.yml` runs the build and clean-install check on every pull request, so a release should not be the first time they run.

## Current state

Version 1.1.1 is the first release meant for PyPI; 1.1.0 was never published and its wheel crashed on `testo run` without the `[db]` extra (see `CHANGELOG.md`). It is on PyPI since 2026-10-19 (https://pypi.org/project/testo-core/). The `v1.1.1` Release's automatic run stopped at the old Test PyPI step, so 1.1.1 was uploaded with a manual run of the workflow. The moving `v1` tag the GitHub Action docs refer to ([CI-CD Pipeline Setup § Versioning policy](CI-CD%20Pipeline%20Setup.md#versioning-policy)) is set separately.

## Version management

- Version is set in `pyproject.toml` under `[project] version`.
- Bump version before creating the release tag.
- The release tag should match the version (e.g. `v1.0.0` → `version = "1.0.0"`).

## Verifying a release

```bash
pip install testo-core==1.1.1
testo --version
testo run --help
```

## Troubleshooting

- **OIDC auth failure**: Verify trusted publisher configuration matches the workflow filename and GitHub environment name exactly.
- **Tag does not match**: the job stops when the tag (minus its `v`) differs from `[project] version`. Fix the version or the tag and create a new Release.
- **`twine check` failure**: Check `pyproject.toml` for missing metadata fields (`description`, `readme`, `requires-python`).
- **Version conflict**: PyPI does not allow re-uploading the same version. Bump the version and create a new release.

## Related

- [CI-CD Pipeline Setup](CI-CD%20Pipeline%20Setup.md) — CI workflow overview
- Workflow file: `.github/workflows/publish.yml`
