---
type: spec
status: current
created: 2026-06-25
updated: 2026-10-10
---

# Phase 4 BYOK and Failure Analysis

<!-- source: notion https://www.notion.so/354d95cd0312800aafc1e117a94f6fca + https://www.notion.so/354d95cd03128001b96df447ecb59f2a -->

## Strategy (WHY)

- **BYOK:** Users supply their own LLM API keys (OpenAI, Anthropic, etc.) — no bundled provider billing.
- **No paid key required:** a third provider, `openai_compatible`, talks to any server that implements OpenAI's chat-completions API at a configurable base URL, so a free tier (Groq, OpenRouter, Gemini) or a local Ollama works too.
- **Failure summaries:** Failed runs should surface a short, actionable explanation on Run Details without reading full logs.

## Architecture

- `testo_core` builds bounded, redacted failure context from artifacts (`failure_context_builder.py`, `failure_analysis_service.py`).
- `testo_api` orchestrates AI calls and settings (`/api/v1/ai/*`, run `ai-summary` endpoints).
- React: settings page + summary card on Run Details.

### Providers

| `provider` | Endpoint | Key |
| --- | --- | --- |
| `openai` | `https://api.openai.com/v1` | required (`OPENAI_API_KEY`) |
| `anthropic` | `https://api.anthropic.com/v1` | required (`ANTHROPIC_API_KEY`) |
| `openai_compatible` | `base_url` from the settings, required, `http(s)` only | optional (`OPENAI_COMPATIBLE_API_KEY`); sent as a bearer token when present |

`openai_compatible` reuses the OpenAI provider with a different base URL (`OpenAiCompatibleProvider` in `testo_core/services/ai/providers/openai_provider.py`) and counts as configured once it has a base URL, because a local server needs no key. The settings page offers presets for Groq, OpenRouter, Gemini and Ollama and, for this provider, raises the timeout to 60 seconds and `max_output_tokens` to 2000: reasoning models such as Gemini spend output tokens on thinking, and 300 cut the summary off mid-sentence. An HTTP error from the provider carries the provider's own message (redacted, truncated) into the summary's `limitations`, so a wrong model name is visible on the card. A rejected key (HTTP 401 or 403) is reported as `provider_misconfigured`. `api_key_env_var` must look like a variable name, so a key pasted there by mistake is refused instead of being stored and shown back.

### Settings storage

The API keeps the AI settings (enabled, provider, model, key source, env var name, limits) in `artifacts/ai_settings.json`, so they survive a restart (`FileBackedAiSettingsStore` in `testo_core/services/ai/integration_settings.py`). `TESTO_AI_SETTINGS_PATH` moves the file; an empty value keeps settings in memory only, which is what the test suite and the static export use. A key typed into the settings page (`runtime_input`) is never written to disk and has to be entered again after a restart; a key from an environment variable is read on each call.

The settings page resets the model to the provider's default when the provider changes, and names the missing environment variable when no key is found. The Run Details card turns each `error_code` into a sentence and links to the settings page when the fix is there.

Security: opt-in default, redaction pipeline, keys never returned on read. See [Technical Debt Tracker](../Testing%20Workflows/Technical%20Debt%20Tracker.md) for ongoing contract gaps.

## Context-aware failure analysis

On run failure, extract failing Allure cases + log tail → `failure_context_v1` metadata → optional auto-generate summary → display via `GET /api/v1/runs/{run_id}/ai-summary`. Implementation: `testo_core/services/failure_context_builder.py`, `testo_api/execution_manager.py`.

## Release gate

[Release Checklist - Phase 4 AI and Failure Analysis](../Archive/Release%20Checklist%20-%20Phase%204%20AI%20and%20Failure%20Analysis.md)

---
**Context & Links:** [Architecture Overview](../Architecture/Architecture%20Overview.md), [Command Reference](../CLI%20Commands/Command%20Reference.md), [Product Roadmap § Phase 4: Next-Gen Capabilities](../Roadmap%20&%20Strategy/Product%20Roadmap.md#how-it-got-here)
