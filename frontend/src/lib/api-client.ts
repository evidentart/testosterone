// Request/response types are generated from the FastAPI OpenAPI schema, so the
// backend's Pydantic models in testo_api/models.py are the single source of
// truth for the HTTP contract. To regenerate after changing a model:
//   python scripts/export_openapi.py && npm --prefix frontend run gen:api
// CI fails if either generated file is stale.
import type { components } from "./api-schema";

type Schemas = components["schemas"];

export type AdhocExecutionRequest = Schemas["AdhocExecutionRequest"];
export type AdhocFramework = AdhocExecutionRequest["framework"];

export type CycleExecutionRequest = Schemas["CycleExecutionRequest"];
export type CycleExecutionAccepted = Schemas["CycleExecutionAcceptedResponse"];
export type CycleExecutionStatus = Schemas["CycleExecutionStatusResponse"];
export type CycleSummary = Schemas["CycleSummary"];
export type CycleListResponse = Schemas["CycleListResponse"];
export type StageSummary = Schemas["StageSummary"];
export type CycleDetailResponse = Schemas["CycleDetailResponse"];

export type RunListItem = Schemas["RunListItem"];
export type RunListResponse = Schemas["RunListResponse"];
export type StageHealth = Schemas["StageHealth"];
export type RunDetailResponse = Schemas["RunDetailResponse"];
export type RunReportsResponse = Schemas["RunReportsResponse"];
export type RunPyramidResponse = Schemas["RunPyramidResponse"];
export type PyramidShape = RunPyramidResponse["shape"];

export type DeltaMetricNode = Schemas["DeltaMetricNode"];
export type DeltaClassification = DeltaMetricNode["classification"];
export type DeltaComparisonResponse = Schemas["DeltaComparisonResponse"];
export type DeltaStageDelta = Schemas["DeltaStageDelta"];
export type DeltaCaseChange = Schemas["DeltaCaseChange"];
export type CaseChangeKind = DeltaCaseChange["kind"];
export type DeltaCaseChangesResponse = Schemas["DeltaCaseChangesResponse"];
export type FlakyTestItem = Schemas["FlakyTestItem"];
export type FlakyTestsResponse = Schemas["FlakyTestsResponse"];

export type AiConfigStatus = Schemas["AiConfigStatusResponse"];
export type UpdateAiConfigRequest = Schemas["AiConfigUpdateRequest"];
export type AiSummaryResponse = Schemas["AiSummaryResponse"];

export type DashboardTrendIndicator = Schemas["DashboardTrendIndicator"];
export type DashboardOverviewResponse = Schemas["DashboardOverviewResponse"];
export type DashboardRecentRunsResponse = Schemas["DashboardRecentRunsResponse"];

export type HealthReadyResponse = Schemas["HealthReadyResponse"];

export const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

// Only needed when the API runs with TESTO_API_TOKEN (it then rejects writes without
// it). Set at build time, or at runtime with localStorage.setItem("testo.apiToken", …).
function apiToken(): string | null {
  if (import.meta.env.VITE_TESTO_API_TOKEN) return import.meta.env.VITE_TESTO_API_TOKEN;
  try {
    return localStorage.getItem("testo.apiToken");
  } catch {
    return null; // storage disabled (privacy mode, sandboxed iframe)
  }
}

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const token = apiToken();
  const resp = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers as Record<string, string> | undefined),
      ...(token ? { Authorization: `Bearer ${token}` } : {})
    }
  });
  if (!resp.ok) {
    // The API answers errors with {error: {code, message}}; surfacing that message
    // beats "API error 405" in the UI (and tells visitors of the read-only static
    // build why an action did nothing).
    const body = (await resp.json().catch(() => null)) as { error?: { message?: string } } | null;
    throw new Error(body?.error?.message ?? `API error ${resp.status}`);
  }
  return (await resp.json()) as T;
}

export const apiClient = {
  createCycleExecution(cycle: string, payload: CycleExecutionRequest): Promise<CycleExecutionAccepted> {
    return api<CycleExecutionAccepted>(`/api/v1/cycles/${encodeURIComponent(cycle)}/executions`, {
      method: "POST",
      body: JSON.stringify(payload)
    });
  },
  createAdhocExecution(payload: AdhocExecutionRequest): Promise<CycleExecutionAccepted> {
    return api<CycleExecutionAccepted>("/api/v1/adhoc-executions", {
      method: "POST",
      body: JSON.stringify(payload)
    });
  },
  getCycleExecutionStatus(executionId: string): Promise<CycleExecutionStatus> {
    return api<CycleExecutionStatus>(`/api/v1/cycle-executions/${executionId}`);
  },
  listCycles(): Promise<CycleListResponse> {
    return api<CycleListResponse>("/api/v1/cycles");
  },
  getCycle(name: string): Promise<CycleDetailResponse> {
    return api<CycleDetailResponse>(`/api/v1/cycles/${encodeURIComponent(name)}`);
  },
  async getHealthReady(): Promise<HealthReadyResponse> {
    // /health/ready responds 503 when degraded but still carries the check payload.
    const resp = await fetch(`${API_BASE}/api/v1/health/ready`, {
      headers: { "Content-Type": "application/json" }
    });
    return (await resp.json()) as HealthReadyResponse;
  },
  listRuns(): Promise<RunListResponse> {
    return api<RunListResponse>("/api/v1/runs");
  },
  getRun(runId: string): Promise<RunDetailResponse> {
    return api<RunDetailResponse>(`/api/v1/runs/${runId}`);
  },
  getRunReports(runId: string): Promise<RunReportsResponse> {
    return api<RunReportsResponse>(`/api/v1/runs/${runId}/reports`);
  },
  getRunPyramid(runId: string): Promise<RunPyramidResponse> {
    return api<RunPyramidResponse>(`/api/v1/runs/${runId}/pyramid`);
  },
  getDeltaComparison(currentRunId: string, baselineRunId: string): Promise<DeltaComparisonResponse> {
    const params = new URLSearchParams({
      current_run_id: currentRunId,
      baseline_run_id: baselineRunId
    });
    return api<DeltaComparisonResponse>(`/api/v1/analytics/delta?${params.toString()}`);
  },
  getDeltaCaseChanges(currentRunId: string, baselineRunId: string): Promise<DeltaCaseChangesResponse> {
    const params = new URLSearchParams({
      current_run_id: currentRunId,
      baseline_run_id: baselineRunId
    });
    return api<DeltaCaseChangesResponse>(`/api/v1/analytics/delta/cases?${params.toString()}`);
  },
  getFlakyTests(cycle: string): Promise<FlakyTestsResponse> {
    const params = new URLSearchParams({ cycle });
    return api<FlakyTestsResponse>(`/api/v1/analytics/flaky?${params.toString()}`);
  },
  getDashboardOverview(recentLimit = 5): Promise<DashboardOverviewResponse> {
    return api<DashboardOverviewResponse>(`/api/v1/dashboard/overview?recent_limit=${recentLimit}`);
  },
  getDashboardRecentRuns(limit = 10): Promise<DashboardRecentRunsResponse> {
    return api<DashboardRecentRunsResponse>(`/api/v1/dashboard/runs/recent?limit=${limit}`);
  },
  getAiConfigStatus(): Promise<AiConfigStatus> {
    return api<AiConfigStatus>("/api/v1/ai/config/status");
  },
  updateAiConfig(payload: UpdateAiConfigRequest): Promise<AiConfigStatus> {
    return api<AiConfigStatus>("/api/v1/ai/config", {
      method: "PUT",
      body: JSON.stringify(payload)
    });
  },
  getRunAiSummary(runId: string): Promise<AiSummaryResponse> {
    return api<AiSummaryResponse>(`/api/v1/runs/${runId}/ai-summary`);
  },
  generateRunAiSummary(runId: string, forceRefresh = false): Promise<AiSummaryResponse> {
    return api<AiSummaryResponse>(`/api/v1/runs/${runId}/ai-summary:generate`, {
      method: "POST",
      body: JSON.stringify({ force_refresh: forceRefresh })
    });
  }
};
