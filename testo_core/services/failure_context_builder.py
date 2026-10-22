from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from testo_core.history.views import CompletedRunView
from testo_core.security.redaction import redact_text, redact_value


@dataclass(frozen=True)
class FailureContextBudget:
    max_total_chars: int = 16_000
    max_log_chars: int = 8_000
    max_trace_chars: int = 4_000
    max_metadata_chars: int = 4_000


@dataclass(frozen=True)
class FailureContext:
    prompt: str
    context_stats: dict[str, int]
    limitations: tuple[str, ...]


def _truncate(value: str, *, limit: int, label: str) -> tuple[str, bool]:
    if len(value) <= limit:
        return value, False
    suffix = f"\n...[truncated {label}]..."
    if limit <= len(suffix):
        return value[:limit], True
    keep = limit - len(suffix)
    return f"{value[:keep]}{suffix}", True


def _redacted_context_text(value: Any) -> str:
    if value is None:
        return ""
    redacted = redact_value(value)
    if isinstance(redacted, str):
        return redacted
    try:
        return json.dumps(redacted, sort_keys=True, default=str)
    except TypeError:
        return redact_text(str(redacted))


# The Run Details card shows the reply as plain text and bolds these three labels, so the
# reply has to be short, unformatted and in this exact shape.
_INSTRUCTIONS = """\
You explain a failed test run to the engineer who has to fix it.
Reply in plain text, in exactly this shape and nothing else:

What failed: one or two sentences naming the failing tests and the observed error, with the numbers from the evidence.
Likely cause: one sentence with the most probable cause. If the evidence does not show it, write "Not clear from the evidence" and name what is missing.
Next steps:
- up to three short, concrete actions, the most useful first

Rules: under 120 words in total. No Markdown: no asterisks, backticks, headings or numbered lists. Use only the evidence below; do not invent tests, endpoints or causes. No introduction, no extra sections."""


def build_failure_context(
    *,
    run: CompletedRunView,
    metadata: dict[str, Any],
    budget: FailureContextBudget,
) -> FailureContext:
    summary_block = (
        f"run_id={run.run_id}\n"
        f"test_kind={run.test_kind}\n"
        f"status={run.status.value if run.status else 'unknown'}\n"
        f"returncode={run.returncode}\n"
        f"failed={run.failed}\n"
        f"broken={run.broken}\n"
        f"health_pct={run.health_pct}\n"
    )
    raw_log = _redacted_context_text(metadata.get("error_message") or metadata.get("error"))
    raw_trace = _redacted_context_text(
        metadata.get("traceback") or metadata.get("stack_trace") or metadata.get("audit_json")
    )
    raw_meta = _redacted_context_text(metadata.get("sync"))

    log_section, log_truncated = _truncate(raw_log, limit=budget.max_log_chars, label="log")
    trace_section, trace_truncated = _truncate(
        raw_trace, limit=budget.max_trace_chars, label="trace"
    )
    meta_section, meta_truncated = _truncate(
        raw_meta, limit=budget.max_metadata_chars, label="metadata"
    )

    prompt = (
        f"{_INSTRUCTIONS}\n\n"
        f"[Run]\n{summary_block}\n"
        f"[FailureLog]\n{log_section}\n\n"
        f"[Trace]\n{trace_section}\n\n"
        f"[Metadata]\n{meta_section}\n"
    )
    prompt, prompt_truncated = _truncate(prompt, limit=budget.max_total_chars, label="prompt")
    limitations: list[str] = []
    if log_truncated:
        limitations.append("log_truncated")
    if trace_truncated:
        limitations.append("trace_truncated")
    if meta_truncated:
        limitations.append("metadata_truncated")
    if prompt_truncated:
        limitations.append("context_budget_truncated")
    return FailureContext(
        prompt=prompt,
        context_stats={
            "prompt_chars": len(prompt),
            "log_chars": len(log_section),
            "trace_chars": len(trace_section),
            "metadata_chars": len(meta_section),
        },
        limitations=tuple(limitations),
    )
