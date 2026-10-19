import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { apiClient } from "../../lib/api-client";
import { Button, EmptyState, PageHeader, RunLabel, Spinner, StatusPill } from "../../components/ui";
import { MuscleShrug } from "../../components/mascot";

export function HistoryPage() {
  const runsQuery = useQuery({
    queryKey: ["runs"],
    queryFn: () => apiClient.listRuns()
  });

  if (runsQuery.isLoading) {
    return (
      <div className="flex items-center gap-2 text-sm text-ink-300">
        <Spinner /> Loading run history...
      </div>
    );
  }
  if (runsQuery.isError) {
    return <p className="text-sm text-danger-400">Failed to load runs.</p>;
  }

  const items = runsQuery.data?.items ?? [];
  // Baseline must come from the same cycle; comparing different cycles reports every test as removed.
  const latest = items[0];
  const baseline = latest?.cycle ? items.slice(1).find((run) => run.cycle === latest.cycle) : undefined;

  return (
    <section>
      <PageHeader
        title="Runs"
        subtitle="Every archived cycle run, newest first."
        actions={
          latest && baseline ? (
            <Link to={`/compare?current_run_id=${latest.run_id}&baseline_run_id=${baseline.run_id}`}>
              <Button variant="secondary" size="sm">
                Compare latest two
              </Button>
            </Link>
          ) : undefined
        }
      />
      {items.length === 0 ? (
        <EmptyState
          mascot={<MuscleShrug />}
          title="No runs yet"
          message="Run a cycle and its archived result will show up here."
          action={
            <Link to="/cycles">
              <Button size="sm">Browse cycles</Button>
            </Link>
          }
        />
      ) : (
        <ul className="divide-y divide-white/5 glass-card">
          {items.map((run) => (
            <li key={run.run_id} className="flex flex-wrap items-center justify-between gap-2 px-4 py-3 text-sm">
              <div className="flex min-w-0 items-center gap-3">
                <StatusPill status={run.status ?? "unknown"} returncode={run.returncode} />
                <RunLabel run={run} linked />
              </div>
              <span className="text-xs text-ink-400">
                {run.health_pct != null ? `health ${run.health_pct.toFixed(2)}%` : ""}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
