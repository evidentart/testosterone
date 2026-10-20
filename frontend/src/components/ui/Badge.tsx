import type { HTMLAttributes } from "react";

type Tone = "neutral" | "brand" | "success" | "danger" | "warn";

const TONE_CLASSES: Record<Tone, string> = {
  neutral: "border-white/10 bg-ink-800/70 text-ink-200",
  brand: "border-brand-600/50 bg-brand-600/15 text-brand-300",
  success: "border-success-600/50 bg-success-600/15 text-success-300",
  danger: "border-danger-600/50 bg-danger-600/15 text-danger-300",
  warn: "border-warn-500/50 bg-warn-500/15 text-warn-300"
};

export interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  tone?: Tone;
}

export function Badge({ tone = "neutral", className, ...props }: BadgeProps) {
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium ${TONE_CLASSES[tone]} ${className ?? ""}`}
      {...props}
    />
  );
}
