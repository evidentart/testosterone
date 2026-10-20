import { afterEach, describe, expect, it, vi } from "vitest";

import { resolveStaticPath } from "./static-backend";

function resolve(url: string): string | null {
  const parsed = new URL(url, "https://example.gitlab.io/testosterone/");
  return resolveStaticPath(parsed.pathname, parsed.searchParams);
}

describe("resolveStaticPath", () => {
  it("maps the collection endpoints the pages load", () => {
    expect(resolve("/api/v1/runs")).toBe("runs.json");
    expect(resolve("/api/v1/runs?limit=30")).toBe("runs.json");
    expect(resolve("/api/v1/cycles")).toBe("cycles.json");
    expect(resolve("/api/v1/health/ready")).toBe("health.json");
    expect(resolve("/api/v1/ai/config/status")).toBe("ai-config.json");
    expect(resolve("/api/v1/dashboard/overview?recent_limit=6")).toBe("dashboard/overview.json");
    expect(resolve("/api/v1/dashboard/runs/recent?limit=8")).toBe("dashboard/recent-runs.json");
  });

  it("maps per-run endpoints", () => {
    expect(resolve("/api/v1/runs/abc-123")).toBe("runs/abc-123/detail.json");
    expect(resolve("/api/v1/runs/abc-123/reports")).toBe("runs/abc-123/reports.json");
    expect(resolve("/api/v1/runs/abc-123/pyramid")).toBe("runs/abc-123/pyramid.json");
    expect(resolve("/api/v1/runs/abc-123/ai-summary")).toBe("runs/abc-123/ai-summary.json");
    expect(resolve("/api/v1/cycles/sample-pytests")).toBe("cycles/sample-pytests.json");
  });

  it("turns delta query parameters into the exported pair folder", () => {
    expect(resolve("/api/v1/analytics/delta?current_run_id=aaa&baseline_run_id=bbb")).toBe(
      "delta/aaa__bbb/comparison.json"
    );
    expect(resolve("/api/v1/analytics/delta/cases?current_run_id=aaa&baseline_run_id=bbb")).toBe(
      "delta/aaa__bbb/cases.json"
    );
  });

  it("maps flaky tests to the cycle's exported file", () => {
    expect(resolve("/api/v1/analytics/flaky?cycle=fake-api")).toBe("flaky/fake-api.json");
    expect(resolve("/api/v1/analytics/flaky")).toBeNull();
  });

  it("works when the API base URL puts the site subpath in front of /api/v1", () => {
    expect(resolve("https://example.gitlab.io/testosterone/api/v1/runs")).toBe("runs.json");
  });

  it("has nothing to serve for streams, writes and incomplete comparisons", () => {
    expect(resolve("/api/v1/cycle-executions/xyz/events")).toBeNull();
    expect(resolve("/api/v1/cycles/sample-pytests/executions")).toBeNull();
    expect(resolve("/api/v1/analytics/delta?current_run_id=aaa")).toBeNull();
  });
});

describe("installStaticBackend", () => {
  async function installWith(files: Record<string, unknown>) {
    vi.resetModules();
    vi.stubEnv("VITE_STATIC_DATA_BASE", "/demo/data");
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const path = String(input);
        return Promise.resolve(
          path in files
            ? new Response(JSON.stringify(files[path]), { status: 200 })
            : new Response("missing", { status: 404 })
        );
      })
    );
    const backend = await import("./static-backend");
    backend.installStaticBackend();
    return backend;
  }

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  it("serves GETs from the exported files", async () => {
    const summary = { status: "available", summary_text: "The /broken route returns 500." };
    await installWith({ "/demo/data/runs/run-1/ai-summary.json": summary });

    const resp = await window.fetch("/api/v1/runs/run-1/ai-summary");

    expect(resp.status).toBe(200);
    expect(await resp.json()).toEqual(summary);
  });

  it("refuses writes with a host-neutral read-only message", async () => {
    const backend = await installWith({});

    const resp = await window.fetch("/api/v1/cycles/self-test/executions", { method: "POST" });

    expect(resp.status).toBe(405);
    const body = await resp.json();
    expect(body.error.code).toBe("read_only_build");
    expect(body.error.message).toBe(backend.READ_ONLY_MESSAGE);
    expect(backend.READ_ONLY_MESSAGE).not.toMatch(/GitLab|GitHub/);
  });
});
