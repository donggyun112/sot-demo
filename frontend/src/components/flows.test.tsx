import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { SOTApi } from "../api";
import type { SessionResponse, TossViewResponse } from "../types";
import { SessionWorkspace } from "./SessionWorkspace";
import { TossView } from "./TossView";

vi.mock("./AgentChat", () => ({ AgentChat: () => <div>Streaming agent chat</div> }));

const detail: SessionResponse = {
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
  turns: [
    {
      id: "turn-1",
      branch_id: "branch-1",
      ordinal: 1,
      role: "user",
      content: "B로 결정",
      created_at: "2026-09-06T00:00:00Z",
    },
  ],
  cites: [],
  proposals: [
    {
      id: "proposal-1",
      document_id: "doc-1",
      branch_id: "branch-1",
      created_by: "alice",
      content: "새 합의",
      status: "open",
      created_at: "2026-09-06T00:00:00Z",
    },
  ],
};

describe("SOT flows", () => {
  it("creates a cite and toss from selected turns", async () => {
    const api = {
      createCite: vi.fn().mockResolvedValue({
        cite: { id: "cite-1", summary: "B 선택" },
      }),
      createToss: vi.fn().mockResolvedValue({
        toss: { id: "toss-1", token: "share-me" },
      }),
    } as unknown as SOTApi;
    const onChanged = vi.fn();
    const onOpenToss = vi.fn();
    const user = userEvent.setup();

    render(
      <SessionWorkspace
        actor="alice"
        api={api}
        apiBase="/api/v1"
        detail={detail}
        onChanged={onChanged}
        onOpenToss={onOpenToss}
        onPublished={vi.fn()}
      />,
    );

    await user.click(screen.getByRole("checkbox", { name: /B로 결정/ }));
    await user.type(screen.getByLabelText("인용 요약"), "B 선택");
    await user.click(screen.getByRole("button", { name: "Cite 만들기" }));
    await user.click(await screen.findByRole("button", { name: "Toss 만들기" }));

    expect(api.createCite).toHaveBeenCalledWith("branch-1", ["turn-1"], "B 선택");
    expect(api.createToss).toHaveBeenCalledWith("cite-1");
    expect(onOpenToss).toHaveBeenCalledWith("share-me");
  });

  it("approves a proposal and announces publication", async () => {
    const api = {
      approveProposal: vi.fn().mockResolvedValue({
        proposal: { ...detail.proposals[0], status: "published" },
        approver_ids: ["alice", "bob"],
        revision: { id: "rev-2", number: 2, content: "새 합의" },
      }),
    } as unknown as SOTApi;
    const onPublished = vi.fn();

    render(
      <SessionWorkspace
        actor="alice"
        api={api}
        apiBase="/api/v1"
        detail={detail}
        onChanged={vi.fn()}
        onOpenToss={vi.fn()}
        onPublished={onPublished}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: "승인" }));

    await waitFor(() => expect(onPublished).toHaveBeenCalled());
    expect(screen.getByRole("status")).toHaveTextContent("revision 2가 main에 반영됐습니다");
  });

  it("opens a public toss and forks it as the selected actor", async () => {
    const toss: TossViewResponse = {
      toss: {
        id: "toss-1",
        cite_id: "cite-1",
        token: "share-me",
        created_by: "alice",
        created_at: "2026-09-06T00:00:00Z",
      },
      cite: {
        id: "cite-1",
        branch_id: "branch-1",
        created_by: "alice",
        turn_ids: ["turn-1"],
        summary: "B 선택",
        created_at: "2026-09-06T00:00:00Z",
      },
      turns: detail.turns,
    };
    const api = {
      forkToss: vi.fn().mockResolvedValue({
        branch: { id: "branch-bob", session_id: "session-1" },
      }),
    } as unknown as SOTApi;
    const onForked = vi.fn();

    render(<TossView actor="bob" api={api} view={toss} onForked={onForked} />);
    await userEvent.click(screen.getByRole("button", { name: "Bob으로 fork" }));

    expect(api.forkToss).toHaveBeenCalledWith("share-me");
    expect(onForked).toHaveBeenCalledWith("session-1");
  });
});
