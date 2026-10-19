/**
 * Read-only backend for the static (GitHub / GitLab Pages) build of the UI.
 *
 * A static host serves files, not the FastAPI app, so when the build sets
 * `VITE_STATIC_DATA_BASE` this module installs a `fetch` shim that answers the
 * API requests the pages make from JSON files written by
 * `scripts/export_static_site.py`. The pages, the API client and the query
 * layer are untouched: they still issue the same requests and parse the same
 * payloads, which is why the demo shows real run data rather than fixtures.
 *
 * Writes (starting a cycle, saving AI settings) and the NDJSON event streams
 * have nothing to answer them, so they fail with a clear read-only message
 * instead of hanging.
 */

const DATA_BASE = (import.meta.env.VITE_STATIC_DATA_BASE ?? "").replace(/\/$/, "");

/** True when this build reads frozen run data instead of a live API. */
export const IS_STATIC_BUILD = DATA_BASE !== "";

export interface StaticManifest {
  mode: "static";
  generated_at: number;
  site_url: string | null;
  run_ids: string[];
  latest_run_id: string;
  delta_pairs: string[][];
  commit: string | null;
  commit_ref: string | null;
  pipeline_url: string | null;
  project_url: string | null;
}

export const READ_ONLY_MESSAGE =
  "This is a read-only demo snapshot: it shows the results of cycles CI already ran, so starting runs and saving settings are disabled.";

/**
 * Shown for a failed run that has no AI summary in the snapshot. The export
 * generates them only when it has an API key (scripts/export_static_site.py).
 */
export const AI_SUMMARY_SNAPSHOT_MESSAGE =
  "AI summaries are generated live when you run Testosterone locally; this snapshot was built without an API key.";

/** Map one API request onto the file the export wrote for it, or null if there is none. */
export function resolveStaticPath(pathname: string, search: URLSearchParams): string | null {
  const path = pathname.replace(/^.*\/api\/v1/, "");

  if (path === "/health/ready") return "health.json";
  if (path === "/ai/config/status") return "ai-config.json";
  if (path === "/cycles") return "cycles.json";
  if (path === "/runs") return "runs.json";
  if (path === "/dashboard/overview") return "dashboard/overview.json";
  if (path === "/dashboard/runs/recent") return "dashboard/recent-runs.json";

  const cycle = /^\/cycles\/([^/]+)$/.exec(path);
  if (cycle) return `cycles/${decodeURIComponent(cycle[1])}.json`;

  const run = /^\/runs\/([^/]+)$/.exec(path);
  if (run) return `runs/${run[1]}/detail.json`;

  const runSub = /^\/runs\/([^/]+)\/(reports|pyramid|ai-summary)$/.exec(path);
  if (runSub) return `runs/${runSub[1]}/${runSub[2]}.json`;

  if (path === "/analytics/flaky") {
    const name = search.get("cycle");
    return name ? `flaky/${name}.json` : null;
  }

  if (path === "/analytics/delta" || path === "/analytics/delta/cases") {
    const current = search.get("current_run_id");
    const baseline = search.get("baseline_run_id");
    if (!current || !baseline) return null;
    const file = path.endsWith("/cases") ? "cases.json" : "comparison.json";
    return `delta/${current}__${baseline}/${file}`;
  }

  return null;
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" }
  });
}

function readOnlyResponse(path: string): Response {
  return jsonResponse(
    {
      error: { code: "read_only_build", message: READ_ONLY_MESSAGE, details: { path } },
      request_id: "static-build"
    },
    405
  );
}

function notExportedResponse(path: string): Response {
  return jsonResponse(
    {
      error: {
        code: "not_exported",
        message: `This static build has no saved response for ${path}.`,
        details: { path }
      },
      request_id: "static-build"
    },
    404
  );
}

/** Replace `fetch` with one that answers `/api/v1/...` from the exported files. */
export function installStaticBackend(): void {
  if (!IS_STATIC_BUILD) return;

  const realFetch = window.fetch.bind(window);

  window.fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const rawUrl = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    const url = new URL(rawUrl, window.location.href);
    if (!url.pathname.includes("/api/v1")) {
      return realFetch(input as RequestInfo, init);
    }

    const method = (init?.method ?? (input instanceof Request ? input.method : "GET")).toUpperCase();
    if (method !== "GET") {
      return readOnlyResponse(url.pathname);
    }

    const file = resolveStaticPath(url.pathname, url.searchParams);
    if (!file) {
      return notExportedResponse(url.pathname);
    }

    const resp = await realFetch(`${DATA_BASE}/${file}`, { headers: { Accept: "application/json" } });
    if (!resp.ok) {
      return notExportedResponse(url.pathname);
    }
    // Served with whatever content type the host guessed; hand the app a clean JSON response.
    return jsonResponse(await resp.json());
  };
}

/** Provenance written by the export, for the demo banner. Null when unavailable. */
export async function loadManifest(): Promise<StaticManifest | null> {
  if (!IS_STATIC_BUILD) return null;
  try {
    const resp = await fetch(`${DATA_BASE}/manifest.json`, { headers: { Accept: "application/json" } });
    if (!resp.ok) return null;
    return (await resp.json()) as StaticManifest;
  } catch {
    return null;
  }
}
