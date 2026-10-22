import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { API_BASE, apiClient } from "../../lib/api-client";
import { Badge, Button, Card, KeyValue, PageHeader, Spinner, StatusPill, TestPyramid } from "../../components/ui";
import { formatRunLabel } from "../../lib/format";
import { AI_SUMMARY_SNAPSHOT_MESSAGE, IS_STATIC_BUILD } from "../../lib/static-backend";

// Error codes that the user fixes on the AI settings page.
const AI_SETTINGS_ERROR_CODES = new Set(["ai_feature_disabled", "provider_misconfigured", "unsupported_provider_model"]);

const AI_SUMMARY_ERROR_MESSAGES: Record<string, string> = {
  summary_not_available: "No summary has been generated for this run yet.",
  ai_feature_disabled: "AI failure summaries are switched off.",
  provider_misconfigured: "No summary generated: the AI provider has no API key, or rejected it.",
  unsupported_provider_model: "No summary generated: the configured model is not available for this API key.",
  provider_timeout: "No summary generated: the AI provider timed out. Try again.",
  provider_rate_limited: "No summary generated: the AI provider rate-limited the request. Try again shortly."
};

function describeAiSummaryError(code: string | null | undefined, limitations: string[] = []): string {
  // Limitation codes are snake_case; a provider failure is recorded as a sentence.
  const providerError = limitations.find((item) => item.includes(" "));
  if (code === "summary_not_available" && providerError) {
    return `No summary generated: ${providerError}`;
  }
  return AI_SUMMARY_ERROR_MESSAGES[code ?? ""] ?? `No summary generated (${code ?? "not_available"}).`;
}

// The labels the summary prompt asks for (testo_core/services/failure_context_builder.py).
const AI_SUMMARY_LABEL = /^(What failed|Likely cause|Next steps):\s*(.*)$/;

function AiSummaryText({ text }: { text: string }) {
  return (
    <div className="space-y-1 text-sm text-ink-100">
      {text
        .split("\n")
        .filter((line) => line.trim())
        .map((line, index) => {
          const labelled = AI_SUMMARY_LABEL.exec(line);
          return labelled ? (
            <p key={index} className="pt-1">
              <span className="font-semibold text-ink-50">{labelled[1]}:</span> {labelled[2]}
            </p>
          ) : (
            <p key={index} className="whitespace-pre-wrap">
              {line}
            </p>
          );
        })}
    </div>
  );
}

export function RunDetailPage() {
  const params = useParams();
  const runId = params.runId ?? "";
  const [artifactsExpanded, setArtifactsExpanded] = useState(false);
  const [aiError, setAiError] = useState<string | null>(null);
  const runQuery = useQuery({
    queryKey: ["run", runId],
    queryFn: () => apiClient.getRun(runId),
    enabled: Boolean(runId)
  });
  const reportsQuery = useQuery({
    queryKey: ["reports", runId],
    queryFn: () => apiClient.getRunReports(runId),
    enabled: Boolean(runId)
  });
  const aiSummaryQuery = useQuery({
    queryKey: ["run-ai-summary", runId],
    queryFn: () => apiClient.getRunAiSummary(runId),
    enabled: Boolean(runId)
  });
  const pyramidQuery = useQuery({
    queryKey: ["run-pyramid", runId],
    queryFn: () => apiClient.getRunPyramid(runId),
    enabled: Boolean(runId)
  });

  if (!runId) {
    return <p className="text-sm text-danger-400">Missing run id.</p>;
  }
  if (runQuery.isLoading || reportsQuery.isLoading) {
    return (
      <div className="flex items-center gap-2 text-sm text-ink-300">
        <Spinner /> Loading run details...
      </div>
    );
  }
  if (runQuery.isError || reportsQuery.isError || !runQuery.data || !reportsQuery.data) {
    return <p className="text-sm text-danger-400">Failed to load run details.</p>;
  }

  const run = runQuery.data.run;
  const reports = reportsQuery.data;

  return (
    <section className="space-y-4">
      <PageHeader
        title={
          <span className="flex items-center gap-3">
            <span>{formatRunLabel(run)}</span>
            <StatusPill status={run.status} returncode={run.returncode} />
          </span>
        }
        subtitle="Run Details"
        actions={
          <Link to="/runs">
            <Button variant="secondary" size="sm">
              Back to runs
            </Button>
          </Link>
        }
      />

      <Card title="Summary">
        <KeyValue
          items={[
            { label: "Run ID", value: <span className="font-mono text-xs">{run.run_id}</span> },
            { label: "Type", value: run.test_kind },
            { label: "Return code", value: <span className="font-mono">{run.returncode}</span> },
            { label: "Health", value: run.health_pct != null ? `${run.health_pct.toFixed(2)}%` : "n/a" },
            { label: "Wall duration", value: `${run.wall_duration_ms.toFixed(0)} ms` }
          ]}
        />
      </Card>

      <Card title="Report Links">
        {Object.keys(reports.static_links).length === 0 ? (
          <p className="text-sm text-ink-400">No reports for this run.</p>
        ) : (
          <ul className="space-y-1 text-sm">
            {Object.entries(reports.static_links).map(([name, url]) => (
              <li key={name}>
                <a href={`${API_BASE}/${url}`} target="_blank" rel="noreferrer" className="text-brand-300 hover:text-brand-400 hover:underline">
                  {name}
                </a>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card title="Test Pyramid">
        {pyramidQuery.isLoading ? (
          <p className="text-sm text-ink-300">Loading test pyramid...</p>
        ) : pyramidQuery.isError || !pyramidQuery.data ? (
          <p className="text-sm text-danger-400">Failed to load test pyramid.</p>
        ) : (
          <TestPyramid {...pyramidQuery.data} />
        )}
      </Card>

      <Card title="Stage Health">
        {(run.stage_health ?? []).length === 0 ? (
          <p className="text-sm text-ink-400">Per-stage breakdown not available for this run.</p>
        ) : (
          <ul className="space-y-2 text-sm">
            {(run.stage_health ?? []).map((stage) => (
              <li key={stage.name} className="flex items-center justify-between gap-2">
                <span className="text-ink-100">
                  {stage.name}
                  {stage.framework ? <span className="ml-2 text-xs text-ink-400">{stage.framework}</span> : null}
                </span>
                <span className="flex items-center gap-2">
                  {stage.total_tests != null && (
                    <span className="text-xs text-ink-400">
                      {stage.passed ?? 0}/{stage.total_tests}
                    </span>
                  )}
                  <Badge tone={stage.health_pct == null ? "neutral" : stage.health_pct >= 100 ? "success" : stage.health_pct > 0 ? "warn" : "danger"}>
                    {stage.health_pct != null ? `${stage.health_pct.toFixed(2)}%` : "n/a"}
                  </Badge>
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card
        title={
          <button
            type="button"
            onClick={() => setArtifactsExpanded((expanded) => !expanded)}
            className="flex items-center gap-2 text-sm font-semibold text-ink-100"
          >
            <span className={`transition-transform ${artifactsExpanded ? "rotate-90" : ""}`}>
              &#9656;
            </span>
            Artifacts
          </button>
        }
      >
        {artifactsExpanded &&
          (reports.artifact_links.length === 0 ? (
            <p className="text-sm text-ink-400">No artifacts recorded.</p>
          ) : (
            <ul className="space-y-1 text-sm text-ink-300">
              {reports.artifact_links.map((artifact) => (
                <li key={artifact} className="font-mono text-xs">
                  {artifact}
                </li>
              ))}
            </ul>
          ))}
      </Card>

      <Card title="AI Failure Summary">
        {run.returncode === 0 ? (
          <p className="text-sm text-ink-400">Summary only applies to failed runs.</p>
        ) : aiSummaryQuery.isLoading ? (
          <p className="text-sm text-ink-300">Loading AI summary...</p>
        ) : aiSummaryQuery.isError || !aiSummaryQuery.data ? (
          <p className="text-sm text-danger-400">Failed to load AI summary.</p>
        ) : aiSummaryQuery.data.status === "available" ? (
          <article className="space-y-1">
            <AiSummaryText text={aiSummaryQuery.data.summary_text ?? ""} />
            <p className="text-xs text-ink-400">
              Confidence: {aiSummaryQuery.data.confidence ?? "unknown"} | Model: {aiSummaryQuery.data.model ?? "unknown"}
              {IS_STATIC_BUILD ? " | Generated when this snapshot was built" : ""}
            </p>
          </article>
        ) : IS_STATIC_BUILD ? (
          <p className="text-sm text-ink-300">
            {aiSummaryQuery.data.limitations.includes("summary_not_generated")
              ? AI_SUMMARY_SNAPSHOT_MESSAGE
              : `The AI summary could not be generated when this snapshot was built (${aiSummaryQuery.data.error_code ?? "not_available"}).`}
          </p>
        ) : (
          <p className="text-sm text-ink-400">
            {describeAiSummaryError(aiSummaryQuery.data.error_code, aiSummaryQuery.data.limitations)}
            {AI_SETTINGS_ERROR_CODES.has(aiSummaryQuery.data.error_code ?? "") ? (
              <>
                {" "}
                <Link className="text-brand-300 underline" to="/settings/ai">
                  Open AI settings
                </Link>
              </>
            ) : null}
          </p>
        )}
        <Button
          className="mt-3"
          // A snapshot has nothing to generate with; the export already did it, or explains why not above.
          disabled={IS_STATIC_BUILD}
          title={IS_STATIC_BUILD ? "Read-only demo: summaries are generated when the snapshot is built." : undefined}
          onClick={async () => {
            setAiError(null);
            try {
              await apiClient.generateRunAiSummary(runId, true);
              await aiSummaryQuery.refetch();
            } catch (err) {
              setAiError(err instanceof Error ? err.message : String(err));
            }
          }}
        >
          Generate AI Summary
        </Button>
        {aiError ? <p className="mt-2 text-sm text-danger-400">{aiError}</p> : null}
      </Card>
    </section>
  );
}
