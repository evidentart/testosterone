import { FormEvent, useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { AiConfigStatus, apiClient, UpdateAiConfigRequest } from "../../lib/api-client";

const inputClass = "rounded-xl border border-ink-600 bg-ink-950/80 px-3 py-2 focus:border-brand-500 focus:outline-none text-sm text-ink-100";
const labelClass = "grid gap-1 text-xs font-medium text-ink-300";

type Provider = UpdateAiConfigRequest["provider"] & string;

// Mirrors the API's defaults (testo_core/services/ai/config.py).
const PROVIDER_DEFAULTS: Record<Provider, { model: string; envVar: string; timeoutS: number; maxOutputTokens: number }> = {
  openai: { model: "gpt-4o-mini", envVar: "OPENAI_API_KEY", timeoutS: 8, maxOutputTokens: 300 },
  anthropic: { model: "claude-haiku-4-5", envVar: "ANTHROPIC_API_KEY", timeoutS: 8, maxOutputTokens: 300 },
  // Free tiers and local models answer more slowly than the paid APIs, and reasoning models
  // (Gemini) spend output tokens on thinking, which cuts a 300-token summary short.
  openai_compatible: {
    model: "llama-3.3-70b-versatile",
    envVar: "OPENAI_COMPATIBLE_API_KEY",
    timeoutS: 60,
    maxOutputTokens: 2000
  }
};

// Services that speak OpenAI's chat-completions API. The first is the default.
const COMPATIBLE_PRESETS = [
  { id: "groq", label: "Groq (free key)", baseUrl: "https://api.groq.com/openai/v1", model: "llama-3.3-70b-versatile" },
  {
    id: "openrouter",
    label: "OpenRouter (free key, :free models)",
    baseUrl: "https://openrouter.ai/api/v1",
    model: "meta-llama/llama-3.3-70b-instruct:free"
  },
  {
    id: "gemini",
    label: "Google Gemini (free key)",
    baseUrl: "https://generativelanguage.googleapis.com/v1beta/openai",
    model: "gemini-flash-latest"
  },
  { id: "ollama", label: "Ollama (local, no key)", baseUrl: "http://localhost:11434/v1", model: "llama3.2" }
] as const;

function describeStatus(status: AiConfigStatus): string {
  if (status.provider === "openai_compatible") {
    if (!status.configured) {
      return "Not configured: an OpenAI-compatible provider needs a base URL.";
    }
    if (!status.enabled) {
      return "Base URL saved, but AI failure summaries are switched off.";
    }
    return status.key_present
      ? "Configured: failed runs can generate an AI summary."
      : "Configured without an API key. That works for a local server such as Ollama; hosted services need a key.";
  }
  if (!status.configured) {
    if (status.api_key_source === "env") {
      const envVar = status.api_key_env_var ?? PROVIDER_DEFAULTS[status.provider].envVar;
      return `Not configured: ${envVar} is not set in the API's environment. Set it and restart the API, or switch to Runtime input.`;
    }
    return "Not configured: no API token is stored. Enter one above and save. It is kept in memory only, so enter it again after the API restarts.";
  }
  if (!status.enabled) {
    return "API key found, but AI failure summaries are switched off.";
  }
  return "Configured: failed runs can generate an AI summary.";
}

export function AIIntegrationSettingsPage() {
  const [saveState, setSaveState] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [saveError, setSaveError] = useState<string | null>(null);
  const [apiKeyInput, setApiKeyInput] = useState("");

  const statusQuery = useQuery({
    queryKey: ["ai-config-status"],
    queryFn: () => apiClient.getAiConfigStatus()
  });

  const status = statusQuery.data;
  const [formState, setFormState] = useState<UpdateAiConfigRequest>({
    enabled: false,
    provider: "openai",
    model: "gpt-4o-mini",
    api_key_source: "env",
    api_key_env_var: null,
    timeout_s: 8,
    retry_count: 1,
    max_input_chars: 16000,
    max_output_tokens: 300,
    base_url: null
  });

  useEffect(() => {
    if (!status) {
      return;
    }
    setFormState({
      enabled: status.enabled,
      provider: status.provider,
      model: status.model,
      api_key_source: status.api_key_source,
      api_key_env_var: status.api_key_env_var,
      timeout_s: status.timeout_s,
      retry_count: status.retry_count,
      max_input_chars: status.max_input_chars,
      max_output_tokens: status.max_output_tokens,
      base_url: status.base_url
    });
  }, [status]);

  if (statusQuery.isLoading) {
    return <p className="text-sm text-ink-300">Loading AI settings...</p>;
  }
  if (statusQuery.isError || !status) {
    return <p className="text-sm text-danger-400">Failed to load AI settings.</p>;
  }

  const effectiveForm = formState;

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaveState("saving");
    setSaveError(null);
    try {
      await apiClient.updateAiConfig({
        ...effectiveForm,
        api_key_input: apiKeyInput || undefined
      });
      setApiKeyInput("");
      setSaveState("saved");
      await statusQuery.refetch();
    } catch (error) {
      setSaveState("error");
      setSaveError(error instanceof Error ? error.message : "Failed to save settings.");
    }
  }

  return (
    <section className="space-y-4">
      <header className="space-y-1">
        <h2 className="text-xl font-semibold">AI Integration Settings</h2>
        <p className="text-sm text-ink-300">Bring your own key. Tokens are masked and never returned by the API.</p>
      </header>

      <form onSubmit={onSubmit} className="grid max-w-lg gap-3 glass-card p-4">
        <label className="flex items-center gap-2 text-sm text-ink-300">
          <input
            type="checkbox"
            checked={effectiveForm.enabled}
            onChange={(event) => setFormState((prev) => ({ ...prev, enabled: event.target.checked }))}
          />
          Enable AI failure summaries
        </label>
        <label className={labelClass}>
          Provider
          <select
            className={inputClass}
            value={effectiveForm.provider}
            onChange={(event) => {
              // A model name belongs to one provider, so switching provider resets it.
              const provider = event.target.value as Provider;
              setFormState((prev) => ({
                ...prev,
                provider,
                model: PROVIDER_DEFAULTS[provider].model,
                timeout_s: PROVIDER_DEFAULTS[provider].timeoutS,
                max_output_tokens: PROVIDER_DEFAULTS[provider].maxOutputTokens,
                base_url: provider === "openai_compatible" ? COMPATIBLE_PRESETS[0].baseUrl : null
              }));
            }}
          >
            <option value="openai">OpenAI</option>
            <option value="anthropic">Anthropic</option>
            <option value="openai_compatible">OpenAI-compatible (Groq, OpenRouter, Gemini, Ollama)</option>
          </select>
        </label>
        {effectiveForm.provider === "openai_compatible" ? (
          <>
            <label className={labelClass}>
              Service
              <select
                className={inputClass}
                value={COMPATIBLE_PRESETS.find((preset) => preset.baseUrl === effectiveForm.base_url)?.id ?? "custom"}
                onChange={(event) => {
                  const preset = COMPATIBLE_PRESETS.find((item) => item.id === event.target.value);
                  if (preset) {
                    setFormState((prev) => ({ ...prev, base_url: preset.baseUrl, model: preset.model }));
                  }
                }}
              >
                {COMPATIBLE_PRESETS.map((preset) => (
                  <option key={preset.id} value={preset.id}>
                    {preset.label}
                  </option>
                ))}
                <option value="custom">Custom base URL</option>
              </select>
            </label>
            <label className={labelClass}>
              Base URL
              <input
                className={inputClass}
                value={effectiveForm.base_url ?? ""}
                placeholder="https://host/v1"
                onChange={(event) => setFormState((prev) => ({ ...prev, base_url: event.target.value || null }))}
              />
            </label>
          </>
        ) : null}
        <label className={labelClass}>
          Model
          <input
            className={inputClass}
            value={effectiveForm.model}
            onChange={(event) => setFormState((prev) => ({ ...prev, model: event.target.value }))}
          />
        </label>
        <label className={labelClass}>
          API key source
          <select
            className={inputClass}
            value={effectiveForm.api_key_source}
            onChange={(event) =>
              setFormState((prev) => ({ ...prev, api_key_source: event.target.value as "env" | "runtime_input" }))
            }
          >
            <option value="env">Environment variable</option>
            <option value="runtime_input">Runtime input</option>
          </select>
        </label>
        {effectiveForm.api_key_source === "env" ? (
          <label className={labelClass}>
            Name of the environment variable holding the key (not the key itself)
            <input
              className={inputClass}
              value={effectiveForm.api_key_env_var ?? ""}
              placeholder={PROVIDER_DEFAULTS[effectiveForm.provider ?? "openai"].envVar}
              onChange={(event) => setFormState((prev) => ({ ...prev, api_key_env_var: event.target.value || null }))}
            />
          </label>
        ) : (
          <label className={labelClass}>
            API token
            <input
              type="password"
              className={inputClass}
              value={apiKeyInput}
              placeholder="Enter token (not persisted to disk)"
              onChange={(event) => setApiKeyInput(event.target.value)}
            />
          </label>
        )}
        <div>
          <button
            type="submit"
            disabled={saveState === "saving"}
            className="rounded bg-brand-500 px-3 py-2 text-sm font-medium text-white hover:bg-brand-400 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {saveState === "saving" ? "Saving..." : "Save settings"}
          </button>
        </div>
      </form>

      <p role="status" className="text-sm text-ink-300">
        {describeStatus(status)}
      </p>
      <p className="text-xs text-ink-400">
        Saved provider: {status.provider} | Model: {status.model}
      </p>
      {saveState === "saved" ? <p className="text-sm text-success-400">Settings saved.</p> : null}
      {saveState === "error" ? <p className="text-sm text-danger-400">Save failed: {saveError}</p> : null}
    </section>
  );
}
