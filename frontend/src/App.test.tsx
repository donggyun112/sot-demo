import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";

vi.mock("@copilotkitnext/react", () => ({
  CopilotKitProvider: ({ children }: { children: React.ReactNode }) => children,
  CopilotChat: () => <div>Agent chat</div>,
  useAgent: () => ({ agent: { subscribe: () => ({ unsubscribe: () => undefined }) } }),
  UseAgentUpdate: { OnRunStatusChanged: "OnRunStatusChanged" },
}));

vi.mock("@ag-ui/pydantic-ai", () => ({
  PydanticAIAgent: class {},
}));

const json = (body: unknown, status = 200) =>
  Promise.resolve(
    new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );

describe("App", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("shows a useful empty document state", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => json({ users: ["alice", "bob"], current_user: "alice", documents: [] })),
    );

    render(<App />);

    expect(await screen.findByText("아직 공유 문서가 없습니다")).toBeInTheDocument();
  });

  it("loads main revision and creates a session", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/bootstrap")) {
        return json({
          users: ["alice", "bob"],
          current_user: "alice",
          documents: [
            {
              id: "doc-1",
              title: "요청 제한 토큰",
              current_revision_id: "rev-1",
              created_by: "alice",
              created_at: "2026-09-06T00:00:00Z",
            },
          ],
        });
      }
      if (url.endsWith("/documents/doc-1/sessions") && init?.method === "POST") {
        return json(
          {
            session: {
              id: "session-1",
              document_id: "doc-1",
              owner_id: "alice",
              title: "격리 검토",
              created_at: "2026-09-06T00:00:00Z",
            },
            branch: {
              id: "branch-1",
              session_id: "session-1",
              owner_id: "alice",
              parent_branch_id: null,
              source_toss_id: null,
              created_at: "2026-09-06T00:00:00Z",
            },
          },
          201,
        );
      }
      if (url.endsWith("/sessions/session-1")) {
        return json({
          session: {
            id: "session-1",
            document_id: "doc-1",
            owner_id: "alice",
            title: "격리 검토",
            created_at: "2026-09-06T00:00:00Z",
          },
          branches: [
            {
              id: "branch-1",
              session_id: "session-1",
              owner_id: "alice",
              parent_branch_id: null,
              source_toss_id: null,
              created_at: "2026-09-06T00:00:00Z",
            },
          ],
          turns: [],
          cites: [],
          proposals: [],
        });
      }
      return json({
        document: {
          id: "doc-1",
          title: "요청 제한 토큰",
          current_revision_id: "rev-1",
          created_by: "alice",
          created_at: "2026-09-06T00:00:00Z",
        },
        current_revision: {
          id: "rev-1",
          document_id: "doc-1",
          number: 1,
          content: "초기 합의",
          proposal_id: null,
          created_by: "alice",
          created_at: "2026-09-06T00:00:00Z",
        },
        revisions: [],
        sessions: [],
      });
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();

    render(<App />);
    expect(await screen.findByText("초기 합의")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "새 세션" }));
    await user.type(screen.getByLabelText("세션 제목"), "격리 검토");
    await user.click(screen.getByRole("button", { name: "세션 만들기" }));

    expect(await screen.findByText("Agent chat")).toBeInTheDocument();
    expect(screen.getByText("격리 검토")).toBeInTheDocument();
  });
});
