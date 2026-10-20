import type { ReactNode } from "react";

export interface EmptyStateProps {
  mascot?: ReactNode;
  title: ReactNode;
  message?: ReactNode;
  action?: ReactNode;
}

export function EmptyState({ mascot, title, message, action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-ink-600 bg-ink-900/40 backdrop-blur px-6 py-12 text-center">
      {mascot}
      <h2 className="text-base font-semibold text-ink-100">{title}</h2>
      {message ? <div className="max-w-md text-sm text-ink-300">{message}</div> : null}
      {action ? <div className="mt-2">{action}</div> : null}
    </div>
  );
}
