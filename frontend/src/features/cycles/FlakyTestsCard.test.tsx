import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { FlakyTestsCard } from "./FlakyTestsCard";

function renderCard(payload: unknown) {
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => payload });
  vi.stubGlobal("fetch", fetchMock);
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <FlakyTestsCard cycle="fake-api" />
    </QueryClientProvider>
  );
  return fetchMock;
}

const base = { cycle: "fake-api", window: 20, runs_analyzed: 4, tests_analyzed: 39 };

describe("FlakyTestsCard", () => {
  it("lists flaky tests with their flip count and history", async () => {
    const fetchMock = renderCard({
      ...base,
      items: [
        {
          key: "k",
          name: "test_flaky_route",
          group: "tests.api",
          runs: 4,
          passed: 2,
          failed: 2,
          flips: 3,
          flip_rate: 1,
          last_status: "failed",
          history: ["passed", "failed", "passed", "failed"]
        }
      ]
    });

    await waitFor(() => expect(screen.getByText("test_flaky_route")).toBeInTheDocument());
    expect(String(fetchMock.mock.calls[0][0])).toContain("/api/v1/analytics/flaky?cycle=fake-api");
    expect(screen.getByText("Flaky tests (1)")).toBeInTheDocument();
    expect(screen.getByText("3 flips in 4 runs")).toBeInTheDocument();
    expect(screen.getByLabelText("History, oldest first: passed, failed, passed, failed")).toBeInTheDocument();
  });

  it("says when nothing is flaky", async () => {
    renderCard({ ...base, items: [] });
    await waitFor(() => expect(screen.getByText("No flaky tests.")).toBeInTheDocument());
  });

  it("asks for more runs when there is too little history", async () => {
    renderCard({ ...base, runs_analyzed: 1, items: [] });
    await waitFor(() => expect(screen.getByText(/Run this cycle a few more times/)).toBeInTheDocument());
  });
});
