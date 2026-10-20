import { Link, useParams, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { apiClient } from "../../lib/api-client";
import { Badge, Card, EmptyState, KeyValue, PageHeader, Spinner } from "../../components/ui";
import { MuscleShrug } from "../../components/mascot";
import { FlakyTestsCard } from "./FlakyTestsCard";
import { RunPanel } from "./RunPanel";

export function CycleDetailPage() {
  const { name = "" } = useParams();
  const [searchParams] = useSearchParams();
  const query = useQuery({
    queryKey: ["cycle", name],
    queryFn: () => apiClient.getCycle(name),
    enabled: Boolean(name)
  });

  if (query.isLoading) {
    return (
      <div className="flex items-center gap-2 text-sm text-ink-300">
        <Spinner /> Loading cycle…
      </div>
    );
  }

  if (query.isError || !query.data) {
    return (
      <EmptyState
        mascot={<MuscleShrug />}
        title={`Cycle "${name}" not found`}
        message={
          <>
            It may have been renamed or removed from the config.{" "}
            <Link to="/cycles" className="text-brand-300 hover:underline">
              Browse available cycles
            </Link>
            .
          </>
        }
      />
    );
  }

  const cycle = query.data;

  return (
    <section className="space-y-6">
      <PageHeader
        title={<span className="font-mono">{cycle.name}</span>}
        subtitle={cycle.description ?? "No description."}
      />

      <RunPanel initialCycle={cycle.name} lockCycle autoFocusRun={searchParams.get("run") === "1"} />

      <FlakyTestsCard cycle={cycle.name} />

      <Card title={`Stages (${cycle.stages.length})`}>
        <ol className="space-y-3">
          {cycle.stages.map((stage, idx) => (
            <li key={stage.name} className="rounded-2xl border border-white/5 bg-ink-950/70 p-3">
              <div className="flex items-center gap-2">
                <span className="font-mono text-xs text-ink-500">#{idx + 1}</span>
                <span className="font-mono text-sm font-semibold text-ink-100">{stage.name}</span>
                <Badge tone="brand">{stage.equipment}</Badge>
              </div>
              <KeyValue
                className="mt-2"
                items={[
                  { label: "Target repo", value: <span className="font-mono text-xs">{stage.target_repo}</span> },
                  {
                    label: "Args",
                    value: (
                      <span className="font-mono text-xs">
                        {stage.args.length > 0 ? stage.args.join(" ") : "—"}
                      </span>
                    )
                  },
                  { label: "Timeout", value: stage.timeout_s !== null ? `${stage.timeout_s}s` : "none" },
                  // The API leaves workers null for single-process frameworks (behave, command).
                  ...(stage.workers !== null
                    ? [
                        {
                          label: "Workers",
                          value:
                            stage.equipment === "pytest" ? `${stage.workers} (with pytest-xdist)` : stage.workers
                        }
                      ]
                    : [])
                ]}
              />
            </li>
          ))}
        </ol>
      </Card>

      {cycle.trigger ? (
        <Card title="Trigger (selective execution)">
          <KeyValue
            items={[
              { label: "Paths", value: <span className="font-mono text-xs">{cycle.trigger.paths.join(", ")}</span> },
              { label: "Since ref", value: cycle.trigger.since_ref ?? "working tree" }
            ]}
          />
        </Card>
      ) : null}
    </section>
  );
}
