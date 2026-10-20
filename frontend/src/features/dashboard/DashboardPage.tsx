import type { ComponentType } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { DashboardOverviewResponse, DashboardTrendIndicator, apiClient } from "../../lib/api-client";
import { Badge, Card, HealthBar, Icons, PageHeader, RunLabel, Spinner, StatusPill } from "../../components/ui";
import { MuscleShrug } from "../../components/mascot";
import { countLabel } from "../../lib/format";

const RECENT_RUNS_REFRESH_MS = 15_000;

export function DashboardPage() {
  const overviewQuery = useQuery({
    queryKey: ["dashboard-overview"],
    queryFn: () => apiClient.getDashboardOverview(6)
  });
  // Polled on its own, lighter-weight cadence so recent activity stays fresh
  // without recomputing the full overview (rollups/trends) on every tick.
  const recentRunsQuery = useQuery({
    queryKey: ["dashboard-recent-runs"],
    queryFn: () => apiClient.getDashboardRecentRuns(8),
    refetchInterval: RECENT_RUNS_REFRESH_MS
  });

  if (overviewQuery.isLoading) {
    return (
      <div className="flex items-center gap-2 text-sm text-ink-300">
        <Spinner /> Loading dashboard overview...
      </div>
    );
  }
  if (overviewQuery.isError) {
    return <p className="text-sm text-danger-400">Failed to load dashboard overview.</p>;
  }

  const data = overviewQuery.data;
  if (!data) {
    return <p className="text-sm text-ink-300">No dashboard data available.</p>;
  }
  const recentRuns = recentRunsQuery.data?.items ?? data.recent_runs ?? [];
  const latestRunId = data.headline_kpis?.latest_run_id;

  // First-run experience: nothing has ever executed, so guide instead of showing n/a walls.
  if (!latestRunId && recentRuns.length === 0) {
    return <FirstRunGuide />;
  }

  return (
    <section className="space-y-5">
      <PageHeader
        title="Dashboard"
        subtitle="Health, reliability, and performance at a glance."
      />
      {data.data_freshness?.degraded ? (
        <p role="status" className="rounded-md border border-warn-500/40 bg-warn-500/10 px-3 py-2 text-sm text-warn-300">
          Some metrics are degraded: {data.data_freshness.notes?.join(", ") || "unknown source issue"}.
        </p>
      ) : null}

      <TrendBaseline kpis={data.headline_kpis} />

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <KpiCard label="Health" icon={Icons.HeartIcon} value={formatPct(data.headline_kpis.health_pct)} trend={data.trend_indicators.health} />
        <KpiCard
          label="Failed"
          icon={Icons.CrossIcon}
          value={formatInt(data.headline_kpis.fail_count)}
          trend={data.trend_indicators.failed_count}
          lowerIsBetter
        />
        <KpiCard
          label="Pass Count"
          icon={Icons.CheckIcon}
          value={formatInt(data.headline_kpis.pass_count)}
          trend={{ direction: "unknown", delta_abs: null, delta_pct: null }}
        />
        <KpiCard
          label="Duration"
          icon={Icons.ClockIcon}
          value={formatMs(data.headline_kpis.duration_ms)}
          trend={data.trend_indicators.duration}
          lowerIsBetter
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Rollups">
          <ul className="space-y-2 text-sm text-ink-300">
            <li className="flex flex-wrap items-center gap-2">
              <strong className="text-ink-100">Reliability</strong>
              <RollupBadges summary={data.reliability_rollup.status_summary} />
            </li>
            <li className="flex flex-wrap items-center gap-2">
              <strong className="text-ink-100">Performance</strong>
              <RollupBadges summary={data.performance_rollup.status_summary} />
            </li>
          </ul>
        </Card>

        <Card title="Quick Links">
          <ul className="space-y-1.5 text-sm">
            {latestRunId ? (
              <li>
                <Link to={`/runs/${latestRunId}`} className="text-brand-300 hover:text-brand-400 hover:underline">
                  Latest run details
                </Link>
              </li>
            ) : (
              <li className="text-ink-400">Latest run details unavailable</li>
            )}
            {recentRuns[0]?.compare_url ? (
              <li>
                <Link to={recentRuns[0].compare_url} className="text-brand-300 hover:text-brand-400 hover:underline">
                  Compare latest two runs
                </Link>
              </li>
            ) : (
              <li className="text-ink-400">Compare view unavailable</li>
            )}
            <li className="text-ink-300">{reportLink("Allure report", data.report_links?.allure ?? { url: null, state: "unknown" })}</li>
            <li className="text-ink-300">{reportLink("Behave report", data.report_links?.behave ?? { url: null, state: "unknown" })}</li>
          </ul>
        </Card>
      </div>

      <Card title="Recent Runs">
        {recentRuns.length === 0 ? (
          <p className="text-sm text-ink-400">No recent runs available.</p>
        ) : (
          <ul className="divide-y divide-white/5">
            {recentRuns.map((run) => (
              <li key={run.run_id} className="space-y-1.5 py-2.5 text-sm">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex min-w-0 items-center gap-3">
                    <StatusPill status={run.status ?? "unknown"} returncode={run.returncode} />
                    <RunLabel run={run} linked href={run.run_detail_url} />
                  </div>
                  <div className="flex items-center gap-3 text-xs text-ink-400">
                    <span>health {formatPct(run.health_pct)}</span>
                    {run.compare_url ? (
                      <Link to={run.compare_url} className="text-brand-300 hover:underline">
                        compare
                      </Link>
                    ) : null}
                  </div>
                </div>
                <HealthBar healthPct={run.health_pct} className="max-w-xs" />
              </li>
            ))}
          </ul>
        )}
      </Card>
    </section>
  );
}

function FirstRunGuide() {
  return (
    <section className="space-y-6">
      <PageHeader title="Welcome to Testo" subtitle="Three steps to your first quality cycle." />
      <div className="flex flex-col items-center gap-2 py-4">
        <MuscleShrug size={112} />
        <p className="text-sm text-ink-300">No runs yet — let&apos;s change that.</p>
      </div>
      <ol className="grid gap-4 md:grid-cols-3" data-testid="first-run-guide">
        <GuideStep
          step={1}
          title="Check system health"
          body="The dot in the top-right corner shows engine readiness. Green means go."
        />
        <GuideStep
          step={2}
          title="Pick a cycle"
          body={
            <>
              Browse the cycles defined in your config —{" "}
              <Link to="/cycles" className="text-brand-300 hover:underline">
                see what you have
              </Link>
              .
            </>
          }
        />
        <GuideStep
          step={3}
          title="Run it"
          body="Hit Run on any cycle card and watch stages stream live. Results land here."
        />
      </ol>
    </section>
  );
}

function GuideStep({ step, title, body }: { step: number; title: string; body: React.ReactNode }) {
  return (
    <li>
      <Card className="h-full">
        <span className="inline-flex h-7 w-7 items-center justify-center rounded-full bg-brand-600/20 font-mono text-sm font-bold text-brand-300">
          {step}
        </span>
        <h3 className="mt-2 text-sm font-semibold text-ink-100">{title}</h3>
        <p className="mt-1 text-sm text-ink-300">{body}</p>
      </Card>
    </li>
  );
}

// Trends are only meaningful within one cycle, so say which cycle and which run they compare against.
function TrendBaseline({ kpis }: { kpis: DashboardOverviewResponse["headline_kpis"] }) {
  if (!kpis.latest_run_id) {
    return null;
  }
  const cycle = kpis.cycle ?? "unnamed cycle";
  return (
    <p data-testid="trend-baseline" className="text-sm text-ink-300">
      Latest run: <strong className="text-ink-100">{cycle}</strong>.{" "}
      {kpis.baseline_run_id ? (
        <>
          Trends compare it with the{" "}
          <Link
            to={`/compare?current_run_id=${kpis.latest_run_id}&baseline_run_id=${kpis.baseline_run_id}`}
            className="text-brand-300 hover:text-brand-400 hover:underline"
          >
            previous {cycle} run
          </Link>
          .
        </>
      ) : (
        "No earlier run of this cycle in recent history, so there is no trend."
      )}
    </p>
  );
}

function RollupBadges({
  summary
}: {
  summary: { regressions: number; improvements: number; unchanged: number; unknown: number };
}) {
  return (
    <span className="flex flex-wrap gap-1.5">
      <Badge tone={summary.regressions > 0 ? "danger" : "neutral"}>{countLabel(summary.regressions, "regression")}</Badge>
      <Badge tone={summary.improvements > 0 ? "success" : "neutral"}>{countLabel(summary.improvements, "improvement")}</Badge>
      <Badge>{summary.unchanged} unchanged</Badge>
      <Badge>{summary.unknown} unknown</Badge>
    </span>
  );
}

function KpiCard({
  label,
  icon: Icon,
  value,
  trend,
  lowerIsBetter = false
}: {
  label: string;
  icon: ComponentType;
  value: string;
  trend: DashboardTrendIndicator;
  lowerIsBetter?: boolean;
}) {
  const semantic = trendSemantic(trend, lowerIsBetter);
  const trendColor =
    semantic.label === "improved"
      ? "text-success-400"
      : semantic.label === "regressed"
        ? "text-danger-400"
        : "text-ink-400";
  return (
    <article className="glass-card flex items-center justify-between gap-3 p-4">
      <div className="min-w-0">
        <strong className="text-xs font-medium text-ink-300">{label}</strong>
        <p className="my-0.5 text-lg font-bold text-white">{value}</p>
        <p data-testid={`${label.toLowerCase().replace(/\s+/g, "-")}-trend`} className={`text-xs font-semibold ${trendColor}`}>
          Trend: {semantic.label}
        </p>
      </div>
      <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-brand-500 text-white shadow-lg shadow-brand-500/30">
        <Icon />
      </span>
    </article>
  );
}

export function trendSemantic(
  trend: DashboardTrendIndicator,
  lowerIsBetter: boolean
): { label: "improved" | "regressed" | "flat" | "unknown" } {
  if (trend.direction === "unknown") {
    return { label: "unknown" };
  }
  if (trend.direction === "flat") {
    return { label: "flat" };
  }
  if (lowerIsBetter) {
    return { label: trend.direction === "down" ? "improved" : "regressed" };
  }
  return { label: trend.direction === "up" ? "improved" : "regressed" };
}

function reportLink(
  label: string,
  report: { url: string | null; state: "available" | "missing" | "unknown" }
) {
  if (report.state === "available" && report.url) {
    return (
      <a href={report.url} target="_blank" rel="noreferrer" className="text-brand-300 hover:text-brand-400 hover:underline">
        {label}
      </a>
    );
  }
  if (report.state === "unknown") {
    return `${label} (state unknown)`;
  }
  return `${label} (not available)`;
}

function formatPct(value: number | null): string {
  if (value == null) {
    return "n/a";
  }
  return `${value.toFixed(2)}%`;
}

function formatMs(value: number | null): string {
  if (value == null) {
    return "n/a";
  }
  return `${value.toFixed(0)} ms`;
}

function formatInt(value: number | null): string {
  if (value == null) {
    return "n/a";
  }
  return `${Math.round(value)}`;
}
