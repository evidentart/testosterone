---
type: guide
status: current
created: 2026-07-01
updated: 2026-10-19
---

# Publishing Docker Images

[Index](../Index.md) · [Publishing to PyPI](Publishing%20to%20PyPI.md) · [Publishing to Artifactory](Publishing%20to%20Artifactory.md)

## Overview

The `testo-runner` Docker image is published to GitHub Container Registry (GHCR) via GitHub Actions. Images are built for `linux/amd64` and `linux/arm64` on the floating `python:3.11-slim-bookworm` base, so each build picks up current Debian security fixes, and are scanned with Trivy before they are pushed.

## Registry

- **Registry**: `ghcr.io`
- **Image**: `ghcr.io/taltal-beep/testo-runner`
- **Auth**: Uses `GITHUB_TOKEN` (automatic for public repos, no additional secrets needed)

## Publishing flow

1. Create a GitHub Release with a semver tag (e.g. `v1.0.0`).
2. The `docker-publish.yml` workflow triggers automatically:
   - Checks the tag matches the `pyproject.toml` version.
   - Scans `Dockerfile.testo-runner` with Trivy for configuration issues.
   - Builds the `linux/amd64` image locally, scans it with Trivy for fixable critical vulnerabilities and checks it runs `testo run --help`. Nothing is pushed if either fails.
   - Builds the multi-arch image (`linux/amd64`, `linux/arm64`) via Docker Buildx and pushes it to GHCR, tagged with semver (`1.0.0`), major.minor (`1.0`), major (`1`), commit SHA, and `latest`.
3. To rebuild the image for an existing release (for example after a base-image fix), run the workflow by hand from the Actions tab with the tag as input. It builds the selected branch, so use it only when that branch carries the same package version.
4. The first push creates a private package. Make it public once under the package's settings (Package settings → Danger Zone → Change visibility).

## Tagging strategy

| Tag pattern | Example | When applied |
|-------------|---------|--------------|
| Full semver | `1.0.0` | Every release |
| Major.minor | `1.0` | Every release (floating) |
| Major | `1` | Every release (floating) |
| Commit SHA | `03043a2b` | Every release |
| `latest` | `latest` | Default branch releases only |

## Pulling the image

```bash
docker pull ghcr.io/taltal-beep/testo-runner:latest
docker run --rm ghcr.io/taltal-beep/testo-runner:latest run --help
```

## Using in CI

```yaml
# GitHub Actions
- name: Run tests
  run: |
    docker run --rm \
      -v ${{ github.workspace }}:/workspace \
      ghcr.io/taltal-beep/testo-runner:1.0.0 \
      run --cycle smoke --ci

# docker-compose.yml (override)
services:
  runner:
    image: ghcr.io/taltal-beep/testo-runner:1.0.0
```

## Troubleshooting

- **Trivy blocks the build**: Fix the reported vulnerabilities or update the base image. Critical and high severity issues block the Dockerfile scan; fixable critical issues block the image scan. The v1.1.1 release run failed this way on 2026-10-19 because the base was pinned to `python:3.11.9-slim-bookworm`, after the vulnerable image had already been pushed; the scan now runs before the push.
- **Multi-arch build fails**: Ensure QEMU is set up correctly (the workflow handles this with `docker/setup-qemu-action`).
- **Image pull fails**: For private repos, authenticate with `docker login ghcr.io -u <username> --password-stdin` using a PAT with `read:packages` scope.

## Related

- [Publishing to PyPI](Publishing%20to%20PyPI.md) — Python package publishing
- [CI-CD Pipeline Setup](CI-CD%20Pipeline%20Setup.md) — CI workflow overview
- Workflow file: `.github/workflows/docker-publish.yml`
- Dockerfile: `Dockerfile.testo-runner`
