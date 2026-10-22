---
type: guide
status: current
created: 2026-10-22
updated: 2026-10-22
---

# Team Server

[Index](../Index.md) · [Command Reference § testo ingest](../CLI%20Commands/Command%20Reference.md#testo-ingest) · [Ingest and Team Server - 2026-10-22](../Specs%20&%20ADRs/Ingest%20and%20Team%20Server%20-%202026-10-22.md)

One Testosterone server that every CI job uploads its test results to, so the whole team sees one history: the dashboard, run details, Compare, trends and flaky tests across every branch and pipeline. CI keeps running its tests the way it does today; one extra step uploads the JUnit XML (or Playwright's JSON report, which keeps retries and flaky tests).

## Start it

From a checkout of the repository (`deploy/server/docker-compose.yml`: the `testo-server` image, which is the API with the web UI built in, plus Postgres):

```bash
export TESTO_API_TOKEN="$(openssl rand -hex 32)"   # keep it: CI needs it to upload
cd deploy/server
docker compose up -d          # pulls ghcr.io/taltal-beep/testo-server; add --build to build from the checkout
```

Open <http://localhost:8000>. Reading needs no token. Every write (uploads, starting runs, AI settings) needs `Authorization: Bearer $TESTO_API_TOKEN`; in the UI, set it once with `localStorage.setItem("testo.apiToken", "<token>")` in the browser console.

| Variable | Default | Meaning |
|----------|---------|---------|
| `TESTO_API_TOKEN` | required | Bearer token for every write |
| `POSTGRES_PASSWORD` | `testo` | Database password (internal to the compose network) |
| `TESTO_SERVER_PORT` | `8000` | Port on the host |
| `TESTO_SERVER_TAG` | `1` | Image tag to pull |

Run history lives in Postgres (`postgres_data` volume); per-run artifacts and reports in `testo_data` (`/data` in the container). Put the server behind HTTPS (any reverse proxy) before exposing it beyond your network.

## Upload from CI

After the tests, in any CI system:

```bash
pip install testo-core
testo ingest 'reports/**/*.xml' --cycle web-unit --server "$TESTO_SERVER_URL" --token "$TESTO_API_TOKEN"
```

GitHub Actions:

```yaml
      - run: npx jest --ci --reporters=default --reporters=jest-junit   # your tests, unchanged
      - if: always()            # record failing runs too
        run: |
          pip install testo-core
          testo ingest 'junit*.xml' --cycle web-unit
        env:
          TESTO_SERVER_URL: https://testo.example.com
          TESTO_API_TOKEN: ${{ secrets.TESTO_API_TOKEN }}
```

The upload carries the job's CI provenance (provider, pipeline, job, commit, branch and repository for GitHub Actions, GitLab CI, Buildkite, CircleCI, Jenkins and Azure Pipelines). The step exits `1` when a test failed, like the test step itself, and `3` when the server can't be reached or refuses the token. Use the same `--cycle` name for the same suite every time; that name is what Compare, trends and `testo flaky` group by.

## How it works

`POST /api/v1/ingest` (multipart: `files`, `cycle`, optional `stage`, `tier` and provenance fields) writes the files to a scratch directory and records them through `CycleRunService` as a one-stage `junit` cycle, the same path as a local `testo ingest` and `testo run`. Nothing in an upload is executed. Limits: 200 files, 20 MB per file, 100 MB per upload. The response has the `run_id`, the counts, the exit code and a link to the run page.

The image sets `TESTO_UI_DIR=/app/ui`, which makes the API serve the built React UI at `/` (unknown paths fall back to `index.html`, so `/runs/<id>` loads directly). With a token set, the UI may write to its own origin; without one, only the `TESTO_CORS_ORIGINS` allow-list may.

## Limits today

- Cycles that exist only as uploads are not in `testosterone.yaml`, so the Cycles page doesn't list them; their runs show on the Dashboard, Runs and Compare, and `testo flaky --cycle` / `GET /api/v1/analytics/flaky` work.
- One token for the whole server; no per-user accounts or projects.
- Starting runs from the server's UI runs commands inside the server container, which only makes sense for cycles defined there. The team server is meant for uploads.

CI checks all of this end to end: the `team_server` job in `ci.yml` builds the image, starts the compose file and uploads with `testo ingest --server` (`scripts/team_server_smoke.sh`).
