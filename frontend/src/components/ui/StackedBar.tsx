export interface StackedBarSegment {
  label: string;
  value: number;
  colorClass: string;
}

export interface StackedBarProps {
  segments: StackedBarSegment[];
  className?: string;
}

/** Horizontal proportional bar, e.g. passed/failed/broken/skipped composition. */
export function StackedBar({ segments, className }: StackedBarProps) {
  const total = segments.reduce((sum, s) => sum + Math.max(0, s.value), 0);

  return (
    <div className={className}>
      <div
        className="flex h-2.5 w-full overflow-hidden rounded-full bg-ink-800/80"
        role="img"
        aria-label={segments.map((s) => `${s.label}: ${s.value}`).join(", ")}
      >
        {total > 0
          ? segments
              .filter((s) => s.value > 0)
              .map((s) => (
                <span
                  key={s.label}
                  className={s.colorClass}
                  style={{ width: `${(s.value / total) * 100}%` }}
                  title={`${s.label}: ${s.value}`}
                />
              ))
          : null}
      </div>
      <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-ink-400">
        {segments.map((s) => (
          <span key={s.label} className="inline-flex items-center gap-1">
            <span className={`h-1.5 w-1.5 rounded-full ${s.colorClass}`} aria-hidden />
            {s.label} {s.value}
          </span>
        ))}
      </div>
    </div>
  );
}

/** Simple two-segment bar for a single health percentage (0-100). */
export function HealthBar({ healthPct, className }: { healthPct: number | null; className?: string }) {
  const pct = healthPct == null ? null : Math.max(0, Math.min(100, healthPct));
  return (
    <div
      className={`h-1.5 w-full overflow-hidden rounded-full bg-ink-800 ${className ?? ""}`}
      role="img"
      aria-label={pct == null ? "health unknown" : `health ${pct.toFixed(1)}%`}
    >
      {pct != null ? (
        <span
          className={`block h-full ${pct >= 90 ? "bg-success-400" : pct >= 60 ? "bg-warn-400" : "bg-danger-400"}`}
          style={{ width: `${pct}%` }}
        />
      ) : null}
    </div>
  );
}
