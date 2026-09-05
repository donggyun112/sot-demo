import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { SOTApi } from "../api";
import { AgentChat } from "./AgentChat";

const subscribe = vi.fn();

vi.mock("@copilotkitnext/react", () => ({
  CopilotKitProvider: ({ children }: { children: React.ReactNode }) => children,
  CopilotChat: () => <div>Streaming chat</div>,
  UseAgentUpdate: { OnRunStatusChanged: "OnRunStatusChanged" },
  useAgent: () => ({ agent: { subscribe } }),
}));

vi.mock("@ag-ui/pydantic-ai", () => ({
  PydanticAIAgent: class {},
}));

describe("AgentChat", () => {
  it("persists the completed user and assistant pair", async () => {
    const api = {
      appendTurns: vi.fn().mockResolvedValue({ turns: [] }),
    } as unknown as SOTApi;
    subscribe.mockImplementation((subscriber) => {
      void subscriber.onRunFinalized({
        messages: [
          { id: "user-1", role: "user", content: "검토해줘" },
          { id: "assistant-1", role: "assistant", content: "검토 결과" },
        ],
      });
      return { unsubscribe: () => undefined };
    });

    render(
      <AgentChat
        actor="alice"
        api={api}
        apiBase="/api/v1"
        branchId="branch-1"
        sessionId="session-1"
        turns={[]}
        onSaved={vi.fn()}
      />,
    );

    expect(screen.getByText("Streaming chat")).toBeInTheDocument();
    await waitFor(() =>
      expect(api.appendTurns).toHaveBeenCalledWith("branch-1", [
        { role: "user", content: "검토해줘" },
        { role: "assistant", content: "검토 결과" },
      ]),
    );
  });
});
