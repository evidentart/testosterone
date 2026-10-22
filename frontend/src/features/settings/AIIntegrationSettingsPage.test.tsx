import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AIIntegrationSettingsPage } from "./AIIntegrationSettingsPage";

describe("AIIntegrationSettingsPage", () => {
  it("renders config status and saves runtime token settings", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url.endsWith("/api/v1/ai/config/status")) {
          return Promise.resolve({
            ok: true,
            json: async () => ({
              enabled: false,
              configured: false,
              provider: "openai",
              model: "gpt-4o-mini",
              api_key_source: "runtime_input",
              api_key_env_var: null,
              key_present: false,
              timeout_s: 8,
              retry_count: 1,
              max_input_chars: 16000,
              max_output_tokens: 300
            })
          });
        }
        if (url.endsWith("/api/v1/ai/config") && init?.method === "PUT") {
          return Promise.resolve({
            ok: true,
            json: async () => ({
              enabled: true,
              configured: true,
              provider: "openai",
              model: "gpt-4o-mini",
              api_key_source: "runtime_input",
              api_key_env_var: null,
              key_present: true,
              timeout_s: 8,
              retry_count: 1,
              max_input_chars: 16000,
              max_output_tokens: 300
            })
          });
        }
        return Promise.resolve({ ok: false, status: 404, json: async () => ({}) });
      })
    );

    render(
      <QueryClientProvider client={new QueryClient()}>
        <AIIntegrationSettingsPage />
      </QueryClientProvider>
    );

    await waitFor(() => expect(screen.getByText("AI Integration Settings")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.change(screen.getByPlaceholderText("Enter token (not persisted to disk)"), { target: { value: "sk-temp" } });
    fireEvent.click(screen.getByRole("button", { name: "Save settings" }));
    await waitFor(() => expect(screen.getByText("Settings saved.")).toBeInTheDocument());
  });

  it("resets the model when the provider changes and names the missing env var", async () => {
    const put = vi.fn();
    const envStatus = {
      enabled: true,
      configured: false,
      provider: "openai",
      model: "gpt-4o-mini",
      api_key_source: "env",
      api_key_env_var: null,
      key_present: false,
      timeout_s: 8,
      retry_count: 1,
      max_input_chars: 16000,
      max_output_tokens: 300
    };
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
        if (init?.method === "PUT") {
          put(JSON.parse(String(init.body)));
        }
        return Promise.resolve({ ok: String(input).includes("/api/v1/ai/config"), json: async () => envStatus });
      })
    );

    render(
      <QueryClientProvider client={new QueryClient()}>
        <AIIntegrationSettingsPage />
      </QueryClientProvider>
    );

    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("OPENAI_API_KEY is not set"));
    fireEvent.change(screen.getByLabelText("Provider"), { target: { value: "anthropic" } });
    expect(screen.getByLabelText("Model")).toHaveValue("claude-haiku-4-5");
    fireEvent.click(screen.getByRole("button", { name: "Save settings" }));
    await waitFor(() => expect(put).toHaveBeenCalled());
    expect(put.mock.calls[0][0]).toMatchObject({ provider: "anthropic", model: "claude-haiku-4-5" });

    fireEvent.change(screen.getByLabelText("Provider"), { target: { value: "openai_compatible" } });
    expect(screen.getByLabelText("Base URL")).toHaveValue("https://api.groq.com/openai/v1");
    fireEvent.change(screen.getByLabelText("Service"), { target: { value: "ollama" } });
    expect(screen.getByLabelText("Base URL")).toHaveValue("http://localhost:11434/v1");
    expect(screen.getByLabelText("Model")).toHaveValue("llama3.2");
    fireEvent.click(screen.getByRole("button", { name: "Save settings" }));
    await waitFor(() => expect(put).toHaveBeenCalledTimes(2));
    expect(put.mock.calls[1][0]).toMatchObject({
      provider: "openai_compatible",
      base_url: "http://localhost:11434/v1",
      model: "llama3.2",
      timeout_s: 60,
      max_output_tokens: 2000
    });
  });
});
