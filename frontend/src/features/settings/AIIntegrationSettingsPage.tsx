import { FormEvent, useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { apiClient, UpdateAiConfigRequest } from "../../lib/api-client";

const inputClass = "rounded-xl border border-ink-600 bg-ink-950/80 px-3 py-2 focus:border-brand-500 focus:outline-none text-sm text-ink-100";
const labelClass = "grid gap-1 text-xs font-medium text-ink-300";

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
    max_output_tokens: 300
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
      max_output_tokens: status.max_output_tokens
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
            onChange={(event) =>
              setFormState((prev) => ({ ...prev, provider: event.target.value as "openai" | "anthropic" }))
            }
          >
            <option value="openai">OpenAI</option>
            <option value="anthropic">Anthropic</option>
          </select>
        </label>
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
            API key env var
            <input
              className={inputClass}
              value={effectiveForm.api_key_env_var ?? ""}
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
        Status: {status.configured ? "configured" : "not configured"} | Provider: {status.provider} | Model:{" "}
        {status.model}
      </p>
      {saveState === "saved" ? <p className="text-sm text-success-400">Settings saved.</p> : null}
      {saveState === "error" ? <p className="text-sm text-danger-400">Save failed: {saveError}</p> : null}
    </section>
  );
}
