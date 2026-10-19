---
type: guide
status: current
created: 2026-10-07
updated: 2026-10-19
title: GitLab Pages Demo
tags: [ci, gitlab, pages, frontend, demo]
---

# GitLab Pages Demo

A public, link-shareable demo of Testo: a CI pipeline runs **real** `testo run`
cycles, then publishes the React UI to a static Pages site showing the results of
those runs. The same pipeline exists twice:

- **GitHub Pages** (`.github/workflows/pages-demo.yml`) at
  `https://taltal-beep.github.io/testosterone/`. This is the main demo link; see
  [GitHub Pages](#github-pages).
- **GitLab Pages** (`.gitlab-ci.yml`), for showing the same thing on GitLab; see
  [What you have to do on GitLab](#what-you-have-to-do-on-gitlab).

It runs two things:

- **Testosterone testing itself**: its own fast Python suite, split into a unit
  and an integration/contract stage so the dashboard's pyramid is real.
- **[fake-api](https://github.com/taltal-beep/fake-api)**, a deliberately silly
  app ("Fake Doing Bullshit") with a flaky route, a broken route and a slow route.
  Its tests describe how the app *should* behave, so the broken parts fail them
  honestly. Nothing in the tests is rigged.

Green-only data proves little about a test tool, which is why the second target
exists: it guarantees failures, flakiness and slowness to look at, and every one
of them traces back to a line of app code.

> Live site: `https://<namespace>.gitlab.io/<project>/` (see [What you have to do on GitLab](#what-you-have-to-do-on-gitlab)).

Related: [CI-CD Pipeline Setup](CI-CD%20Pipeline%20Setup.md) (the reusable template for running Testo in
*your* pipeline), [Architecture Overview](../Architecture/Architecture%20Overview.md).

## Why it is built this way

GitLab Pages serves static files only, so it cannot host `testo_api` (FastAPI).
Publishing the UI therefore needs run data frozen into files.

What it does *not* do is reimplement the UI against fixtures. Instead:

1. `scripts/export_static_site.py` calls every read-only endpoint the UI uses —
   in-process, through `TestClient` against the same `create_app()` the real
   server runs — and writes each response body to a JSON file.
2. `frontend/src/lib/static-backend.ts` installs a `fetch` shim in builds made
   with `VITE_STATIC_DATA_BASE`, mapping each API request onto the file the
   export wrote for it.

The pages, the API client and the query layer are unchanged, so the published
dashboard renders the same payloads the live API produces. The cost of the trick
is a layout contract between those two files, pinned by
`tests/unit/ci/test_gitlab_pages_demo_contract.py`.

```
testo run (self-test, fake-api)
  └─ history DB + static/history/<run_id>/ (Allure HTML)
       └─ export_static_site.py ──► public/data/**.json  +  public/history/**
                                        └─ vite build ──► public/  ──► GitLab Pages
                                             (static-backend.ts reads data/)
```

## What the pipeline runs

`.gitlab-ci.yml` at the repo root (the reusable customer-facing template stays in
`ci/gitlab/testo.gitlab-ci.yml`):

| Job | Stage | What it does |
|-----|-------|--------------|
| `run_demo_cycles` | `demo` | Installs the package and Playwright's Chromium, clones fake-api into `.demo/fake-api`, runs `self-test` and `fake-api` once each, exports the site into `public/`. |
| `pages` | `deploy` | Builds the frontend in static mode and copies it over `public/`, then copies `index.html` to `404.html` so deep links survive a refresh. |

Both cycles live in the root `testosterone.yaml`:

| Cycle | Stages (tier) | Expected result |
|-------|---------------|-----------------|
| `self-test` | `core-unit` (unit), `core-integration` (integration) | Green. A red self-test fails the pipeline and nothing is published. |
| `fake-api` | `unit` (unit), `api` (integration), `buttons` Behave (integration), `ui` Playwright (e2e) | Red by design: `broken` and `slow` always fail, `flaky` fails about a third of the time. |

Each pipeline runs `fake-api` once. The cached history (below) holds the
previous pipelines' runs, so Compare puts this run next to the last one and
shows which tests changed, such as the flaky route passing in one pipeline and
failing in the next. The very first pipeline has nothing to compare against
yet.

Run history goes to file-backed SQLite inside the job workspace
(`DATABASE_URL=sqlite:///$CI_PROJECT_DIR/.ci-history/testo.db`), so the demo
needs no database service and no credentials. The DB and the Allure
HTML under `static/history/` are kept in a GitLab cache between pipelines (the
20 newest report trees are kept), so the trend grows with every pipeline. The
cache is best-effort: if GitLab drops it, the next pipeline starts a fresh
history.

The self-test's nested pytest gets `DATABASE_URL=sqlite:////tmp/testo-self-test.db`
through `extra_env`, so testosterone's own tests never write into the history of
the run that is executing them.

### Build-time variables the `pages` job sets

| Variable | Value | Why |
|----------|-------|-----|
| `VITE_BASE` | Pages subpath, e.g. `/testosterone/` | Vite asset URLs and the router `basename`. |
| `VITE_STATIC_DATA_BASE` | `<subpath>/data` | Where the shim reads the exported JSON. |
| `VITE_API_BASE_URL` | `$CI_PAGES_URL` | Report links render as `<API base>/history/…`, which on Pages is the published copy of `static/history/`. |

All three are derived from `CI_PAGES_URL`; nothing is hardcoded, so the same
pipeline works for project, user and group Pages.

## Running it locally

```bash
pip install -e ".[dev]"
npm install                       # Allure 3 CLI, for the HTML reports
git clone https://github.com/taltal-beep/fake-api.git .demo/fake-api
pip install -r .demo/fake-api/requirements.txt
python -m playwright install chromium

testo run --cycle self-test --ci
testo run --cycle fake-api --ci || true
testo run --cycle fake-api --ci || true   # a second run gives Compare a pair locally
python scripts/export_static_site.py --out public --site-url http://localhost:8090/testo

cd frontend
VITE_BASE=/testo/ VITE_STATIC_DATA_BASE=/testo/data \
  VITE_API_BASE_URL=http://localhost:8090/testo npm run build
cd .. && cp -r frontend/dist/. public/ && cp public/index.html public/404.html
```

Serve `public/` under a `/testo/` path (any static server) and the demo behaves
as it does on Pages, except for the 404 fallback, which is Pages-specific.

## What visitors see

A dismissible notice above the header marks the build read-only, says what the
two cycles are (testosterone testing itself, and fake-api, whose red is
deliberate) and links to the pipeline that produced it. Its × button closes it
and the choice is remembered in `localStorage` (`testo.demoNotice.dismissed`);
a "Read-only demo" badge in the header stays visible and toggles the notice
(`frontend/src/components/StaticBuildBanner.tsx`). Writes have nothing behind them, so the shim answers them with
`405 read_only_build` ("This is a read-only demo snapshot…"). The NDJSON event
stream is likewise absent: a static host cannot stream a run that is not running.

- **Cycles page**: only cycles with a run in the snapshot are exported, so every
  card leads to real history. Run buttons (on the cards and the cycle page) are
  disabled and show the local command instead (`testo run --cycle <name>`).
- **AI Failure Summary**: a visitor's click cannot reach an AI provider, so the
  export generates the summary for each failed run beforehand, through the same
  `POST /runs/{id}/ai-summary:generate` the button calls, and the Run detail page
  shows that frozen summary (the button itself is disabled). This needs `ANTHROPIC_API_KEY` in the export
  step's environment (see [Optional: AI summaries](#optional-ai-summaries)); without it the card says
  summaries are generated live when you run Testosterone locally.

Report links work: `static/history/<run_id>/` is copied into the published site,
so the Allure reports for each framework open from the Run detail page.

## Optional: AI summaries

`scripts/export_static_site.py` freezes one AI failure summary per failed run
when `ANTHROPIC_API_KEY` is set. The model defaults to `claude-haiku-4-5`
(override with `TESTO_DEMO_AI_MODEL`). A generated summary is stored with the
run in the cached history DB, so later pipelines reuse it; a failed attempt is
retried on the next pipeline. Each request gets one 30-second attempt, and an
error only skips that summary, never the deploy. The key is only read from the
environment; it is never written to the site.

- GitHub: add a repository secret named `ANTHROPIC_API_KEY`; the export step
  passes `${{ secrets.ANTHROPIC_API_KEY }}` through. Unset, it is empty and the
  export skips the summaries.
- GitLab: add a masked CI/CD variable named `ANTHROPIC_API_KEY`.

## GitHub Pages

`.github/workflows/pages-demo.yml` has the same steps as the GitLab job, in one
`build` job and a `deploy` job:

| Trigger | What happens |
|---------|--------------|
| Push to `main`, nightly schedule, manual run | Build, then deploy to Pages. |
| Pull request touching the demo files | Build only, so a broken demo fails the PR instead of the site. |

The same site also carries the docs: the `build` job runs `mkdocs build --strict --site-dir public/docs`, so the vault is at `https://taltal-beep.github.io/testosterone/docs/` ([Docs Site](../Specs%20&%20ADRs/Docs%20Site%20-%202026-10-19.md)). Pull requests that touch `mkdocs.yml` or `scripts/mkdocs_hooks.py` build it too.

Run history is restored from and saved to the Actions cache under a fresh key
per run (`testo-demo-history-<run_id>`, restored by prefix), because Actions
caches cannot be overwritten. Only the `deploy` job gets `pages: write`.

One-time setup: **Settings → Pages → Source → GitHub Actions**. The first
deployment happens on the next push to `main` (or Actions → Pages demo → Run
workflow); the URL then also shows on the workflow run and under
Settings → Pages.

## What you have to do on GitLab

Everything above is in the repository; these steps need a human and a GitLab
account.

1. **Create the GitLab project**, e.g. `gitlab.com/<user>/testosterone`, public
   (Pages sites on GitLab.com are public unless Pages Access Control is enabled;
   a private project's site is visible only to members).
2. **Get the code there.** GitLab's *pull* mirroring (GitLab fetches from GitHub)
   is a Premium feature, so on Free use one of:
   - the included `.github/workflows/mirror-to-gitlab.yml`, which pushes `main`
     to GitLab on every push. Set repository variable `GITLAB_MIRROR_URL` and
     secret `GITLAB_MIRROR_TOKEN` (a GitLab project access token with
     `write_repository`) on GitHub; the workflow is inert until both exist;
   - or a one-off `git push` to a second remote.
3. **Check runners.** GitLab.com shared runners need an account with CI/CD
   minutes available; GitLab.com asks free-tier accounts to complete identity
   verification (a payment method on file) before shared runners pick up jobs.
   A self-hosted runner works too.
4. **Run the pipeline** — it runs on pushes to the default branch, and can be
   started from CI/CD → Pipelines → Run pipeline.
5. **Open the site** at Deploy → Pages, which shows the URL
   (`https://<namespace>.gitlab.io/<project>/`). The first deployment can take a
   few minutes to become reachable.

Nothing in the pipeline needs secrets; the only credentials anywhere are the
mirror token in step 2, if you choose that route, and the optional AI key
(see [Optional: AI summaries](#optional-ai-summaries)).

## Maintenance notes

- `FAKE_API_REPO` / `FAKE_API_REF` in `.gitlab-ci.yml` choose what is cloned;
  pin `FAKE_API_REF` to a tag to freeze the demo.
- `tests/unit/ci/test_gitlab_pages_demo_contract.py` asserts the cycles exist,
  that the fake-api cycle points where the pipeline clones it, and that only
  fake-api is allowed to fail.
- Compare's **Test-Level Changes** needs each run's own copy of its per-test
  results under `static/history/<run_id>/artifacts/` (PR #68). That folder is
  in the history cache, and the prune step trims it with the reports.
- Adding a UI page that calls a new endpoint means exporting it in
  `scripts/export_static_site.py` *and* mapping it in `static-backend.ts`,
  otherwise the demo shows that panel's error state.
- The export scrubs checkout-absolute paths out of the payloads before they are
  published.
