import { useQuery } from "@tanstack/react-query";

import { apiClient, type FlakyTestItem } from "../../lib/api-client";
import { Badge, Card, Spinner } from "../../components/ui";

const DOT: Record<string, string> = {
  passed: "bg-success-500",
  failed: "bg-danger-500",
  broken: "bg-danger-500"
};

function History({ item }: { item: FlakyTestItem }) {
  return (
    <span className="flex flex-wrap gap-0.5" aria-label={`History, oldest first: ${item.history.join(", ")}`}>
      {item.history.map((status, idx) => (
        <span
          // History is positional; the index is the identity.
          key={idx}
          title={status}
          className={`h-2.5 w-2.5 rounded-sm ${DOT[status] ?? "bg-ink-600"}`}
        />
      ))}
    </span>
  );
}

/** Tests that keep flipping between pass and fail across this cycle's recent runs. */
export function FlakyTestsCard({ cycle }: { cycle: string }) {
  const query = useQuery({
    queryKey: ["flaky", cycle],
    queryFn: () => apiClient.getFlakyTests(cycle)
  });

  if (query.isLoading) {
    return (
      <Card title="Flaky tests">
        <div className="flex items-center gap-2 text-sm text-ink-300">
          <Spinner /> Checking run history…
        </div>
      </Card>
    );
  }
  if (query.isError || !query.data) {
    return null;
  }

  const report = query.data;
  const summary = `${report.tests_analyzed} tests across the last ${report.runs_analyzed} runs. Flaky means it both passed and failed and flipped at least twice.`;

  return (
    <Card title={`Flaky tests (${report.items.length})`}>
      <p className="mb-3 text-xs text-ink-400">{summary}</p>
      {report.runs_analyzed < 2 ? (
        <p className="text-sm text-ink-300">Run this cycle a few more times to see which tests are flaky.</p>
      ) : report.items.length === 0 ? (
        <p className="text-sm text-ink-300">No flaky tests.</p>
      ) : (
        <ul className="space-y-2">
          {report.items.map((item) => (
            <li key={item.key} className="rounded-2xl border border-white/5 bg-ink-950/70 p-3">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-mono text-sm text-ink-100">{item.name}</span>
                <Badge tone="warn">
                  {item.flips} flips in {item.runs} runs
                </Badge>
                <Badge tone={item.last_status === "passed" ? "success" : "danger"}>last: {item.last_status}</Badge>
              </div>
              <div className="mt-1 text-xs text-ink-400">{item.group}</div>
              <div className="mt-2">
                <History item={item} />
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
