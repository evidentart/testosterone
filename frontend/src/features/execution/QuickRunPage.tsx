import { FormEvent, useState } from "react";
import { Link } from "react-router-dom";

import { apiClient, type AdhocFramework } from "../../lib/api-client";
import { Button, Card, PageHeader, Spinner } from "../../components/ui";
import { Toggle } from "../cycles/RunPanel";
import { ExecutionProgress } from "./ExecutionProgress";
import { useCycleExecution } from "./useCycleExecution";

const FRAMEWORKS: AdhocFramework[] = ["pytest", "behave", "behavex", "playwright", "command"];

const inputClass = "rounded-xl border border-ink-600 bg-ink-950/80 px-3 py-2 focus:border-brand-500 focus:outline-none text-sm text-ink-100";
const labelClass = "grid gap-1 text-xs font-medium text-ink-300";

/**
 * Run one framework directly, without defining a cycle first.
 *
 * The API wraps it in a one-stage `adhoc` cycle, so it goes through the same
 * engine, persistence and event stream as any cycle run.
 */
export function QuickRunPage() {
  const [framework, setFramework] = useState<AdhocFramework>("pytest");
  const [targetRepo, setTargetRepo] = useState(".");
  const [args, setArgs] = useState("-q");
  const [persist, setPersist] = useState(true);
  const execution = useCycleExecution();

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    await execution.start(() =>
      apiClient.createAdhocExecution({
        framework,
        target_repo: targetRepo,
        args: args.trim() ? args.trim().split(/\s+/) : [],
        persist
      })
    );
  }

  return (
    <section className="space-y-4">
      <PageHeader
        title="Quick Run"
        subtitle={
          <>
            Run one framework directly, without a cycle. For repeatable runs define a cycle in{" "}
            <code className="font-mono">testosterone.yaml</code> and use{" "}
            <Link to="/cycles" className="text-brand-300 hover:underline">
              Cycles
            </Link>
            .
          </>
        }
      />

      <Card title="Run a framework">
        <form onSubmit={onSubmit} className="grid gap-3 sm:grid-cols-2" data-testid="quick-run-form">
          <label className={labelClass}>
            Framework
            <select
              className={inputClass}
              value={framework}
              onChange={(e) => setFramework(e.target.value as AdhocFramework)}
              disabled={execution.busy}
            >
              {FRAMEWORKS.map((fw) => (
                <option key={fw} value={fw}>
                  {fw}
                </option>
              ))}
            </select>
          </label>
          <label className={labelClass}>
            Target repo
            <input
              className={`${inputClass} font-mono`}
              value={targetRepo}
              onChange={(e) => setTargetRepo(e.target.value)}
              disabled={execution.busy}
            />
          </label>
          <label className={`${labelClass} sm:col-span-2`}>
            {framework === "command" ? "Command (full argv)" : "Arguments"}
            <input
              className={`${inputClass} font-mono`}
              value={args}
              onChange={(e) => setArgs(e.target.value)}
              placeholder={framework === "command" ? "npx jest --ci" : "-q"}
              disabled={execution.busy}
            />
          </label>
          <div className="flex items-center gap-4 sm:col-span-2">
            <Button type="submit" disabled={execution.busy || !targetRepo.trim()}>
              {execution.busy ? (
                <>
                  <Spinner className="h-3.5 w-3.5 border-white/40 border-t-white" /> Running…
                </>
              ) : (
                "Run"
              )}
            </Button>
            <Toggle label="Persist run" checked={persist} onChange={setPersist} disabled={execution.busy} />
            {execution.executionId ? (
              <span className="font-mono text-xs text-ink-400">execution {execution.executionId}</span>
            ) : null}
          </div>
        </form>
      </Card>

      <ExecutionProgress execution={execution} noun="Run" persisted={persist} />
    </section>
  );
}
