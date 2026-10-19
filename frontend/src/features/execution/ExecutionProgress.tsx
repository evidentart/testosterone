import { Link } from "react-router-dom";

import { Badge, Card, StatusPill } from "../../components/ui";
import { MuscleDefeated, MuscleFlex } from "../../components/mascot";
import type { CycleExecution } from "./useCycleExecution";

/** Outcome banner, stage timeline and raw event stream for one execution. */
export function ExecutionProgress({
  execution,
  noun,
  persisted
}: {
  execution: CycleExecution;
  /** What ran, for the outcome line ("Cycle", "Run"). */
  noun: string;
  /** Whether the run was persisted, so the Runs page has it. */
  persisted: boolean;
}) {
  const { phase, exitCode, errorMessage, events, stageRows, finished } = execution;

  return (
    <>
      {finished ? (
        <Card>
          <div className="flex items-center gap-4" data-testid="run-outcome">
            {phase === "passed" ? <MuscleFlex size={72} animate /> : <MuscleDefeated size={72} animate />}
            <div>
              <p className="text-base font-semibold text-ink-100">
                {phase === "passed"
                  ? `${noun} passed. Gains secured. 💪`
                  : phase === "aborted"
                    ? `${noun} aborted (fail fast).`
                    : `${noun} failed.`}
              </p>
              <p className="mt-0.5 text-sm text-ink-300">
                {exitCode !== null ? `Exit code ${exitCode}. ` : ""}
                {errorMessage ?? ""}
                {persisted ? (
                  <>
                    See <Link to="/runs" className="text-brand-300 hover:underline">Runs</Link> for the archived
                    result.
                  </>
                ) : null}
              </p>
            </div>
          </div>
        </Card>
      ) : null}

      {(stageRows.length > 0 || events.length > 0) && (
        <div className="grid gap-4 lg:grid-cols-2">
          <Card title="Stage timeline">
            {stageRows.length === 0 ? (
              <p className="text-sm text-ink-400">Waiting for stage events…</p>
            ) : (
              <ul className="space-y-2">
                {stageRows.map((s) => (
                  <li key={s.stage} className="rounded-xl border border-white/5 bg-ink-950/70 p-2.5 text-sm">
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-mono text-ink-100">{s.stage}</span>
                      <StatusPill
                        status={s.status === "completed" ? (s.returncode === 0 ? "passed" : "failed") : s.status === "running" ? "running" : "queued"}
                      />
                    </div>
                    <div className="mt-1 flex items-center gap-2 text-xs text-ink-400">
                      {s.framework ? <Badge tone="brand">{s.framework}</Badge> : null}
                      {typeof s.duration_s === "number" ? <span>{s.duration_s.toFixed(1)}s</span> : null}
                      {typeof s.returncode === "number" ? <span>rc={s.returncode}</span> : null}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Card>
          <Card title="Event stream">
            <pre className="max-h-[420px] overflow-auto whitespace-pre-wrap break-words rounded-md bg-ink-950 p-3 font-mono text-xs leading-relaxed text-ink-200">
              {events.map((e) => JSON.stringify(e)).join("\n") || "(no events yet)"}
            </pre>
          </Card>
        </div>
      )}
    </>
  );
}
