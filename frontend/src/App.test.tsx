import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import { App } from "./App";
import { AuthSession } from "./auth";
import { StrictMode } from "react";
import { QueryClient } from "@tanstack/react-query";
import { createAPI } from "./api";
import {
  createServer,
  eventStream,
  member,
  proposal,
  session,
  turns,
} from "./test/server";

afterEach(() => vi.unstubAllGlobals());

it("uses GIS credential login and exposes no actor switcher", async () => {
  let callback:
    | ((value: google.accounts.id.CredentialResponse) => void)
    | undefined;
  const requests: Request[] = [];
  const auth = new AuthSession(async (request) => {
    requests.push(request.clone());
    if (request.url.endsWith("/refresh"))
      return Response.json({}, { status: 401 });
    if (request.url.endsWith("/google"))
      return Response.json({
        access_token: "real-access",
        token_type: "bearer",
        user: member,
      });
    if (request.url.endsWith("/me")) return Response.json(member);
    return Response.json([]);
  }, "https://sot.test/api/v1");
  vi.stubGlobal("google", {
    accounts: {
      id: {
        initialize: (options: google.accounts.id.IdConfiguration) => {
          callback = options.callback;
        },
        renderButton: (element: HTMLElement) => {
          element.textContent = "Sign in with Google";
        },
      },
    },
  });
  render(
    <App
      auth={auth}
      googleClientId="google-client-id"
      apiBase="https://sot.test/api/v1"
    />,
  );
  expect(await screen.findByText("Sign in with Google")).toBeVisible();
  await act(async () =>
    callback?.({ credential: "gis-credential", select_by: "btn" }),
  );
  expect(await screen.findByText("Member")).toBeVisible();
  const login = requests.find((request) => request.url.endsWith("/google"));
  expect(await login?.json()).toEqual({ credential: "gis-credential" });
  expect(screen.queryByLabelText("작업자")).not.toBeInTheDocument();
});

it("shows empty documents and resets document/session selection when workspace changes", async () => {
  const server = createServer();
  server.state.sessions = [session];
  await server.auth.loginWithGoogle("credential");
  render(<App auth={server.auth} apiBase="https://sot.test/api/v1" />);
  expect(await screen.findByText("초기 합의")).toBeVisible();
  await userEvent.click(
    screen.getAllByRole("button", { name: /세션 session-/ })[0],
  );
  expect(await screen.findByLabelText("Agent message")).toBeVisible();
  await userEvent.selectOptions(screen.getByLabelText("Workspace"), "w2");
  expect(await screen.findByText("목적지 합의")).toBeVisible();
  expect(screen.queryByLabelText("Agent message")).not.toBeInTheDocument();
  expect(
    server.requests.some((request) =>
      request.url.includes("/workspaces/w2/documents/doc-1"),
    ),
  ).toBe(true);
});

it("shows the existing empty document state", async () => {
  const server = createServer();
  server.state.emptyDocuments = true;
  await server.auth.loginWithGoogle("credential");
  render(<App auth={server.auth} apiBase="https://sot.test/api/v1" />);
  expect(await screen.findByText("아직 공유 문서가 없습니다")).toBeVisible();
});

it("loads canonical resources under the existing StrictMode root", async () => {
  const server = createServer();
  await server.auth.loginWithGoogle("credential");
  render(
    <StrictMode>
      <App auth={server.auth} apiBase="https://sot.test/api/v1" />
    </StrictMode>,
  );
  expect(await screen.findByText("초기 합의")).toBeVisible();
});

it("creates a canonical session without sending unsupported title fields", async () => {
  const server = createServer();
  await server.auth.loginWithGoogle("credential");
  render(<App auth={server.auth} apiBase="https://sot.test/api/v1" />);
  await userEvent.click(await screen.findByRole("button", { name: "새 세션" }));
  expect(await screen.findByLabelText("Agent message")).toBeVisible();
  const request = server.requests.find(
    (item) => item.method === "POST" && item.url.endsWith("/sessions"),
  );
  expect(request?.url).toBe(
    "https://sot.test/api/v1/workspaces/w1/documents/doc-1/sessions",
  );
  expect(await request?.json()).toEqual({});
});

it("RUN_FINISHED refetches only active branch Turns and branch metadata with the real QueryClient", async () => {
  const server = createServer();
  server.state.sessions = [session];
  const auth = new AuthSession(async (request) => {
    if (!request.url.endsWith("/agent")) return server.network(request);
    server.requests.push(request.clone());
    const run = await request.json();
    server.state.branchVersion = 3;
    server.state.turns = [
      ...turns,
      {
        ...turns[0],
        id: "canonical-answer",
        ordinal: 2,
        content: "서버에 확정된 답변",
      },
    ];
    return eventStream([
      { type: "RUN_STARTED", threadId: run.threadId, runId: run.runId },
      {
        type: "TEXT_MESSAGE_START",
        messageId: "draft-answer",
        role: "assistant",
      },
      {
        type: "TEXT_MESSAGE_CONTENT",
        messageId: "draft-answer",
        delta: "스트림 답변",
      },
      { type: "TEXT_MESSAGE_END", messageId: "draft-answer" },
      { type: "RUN_FINISHED", threadId: run.threadId, runId: run.runId },
    ]);
  }, "https://sot.test/api/v1");
  await auth.loginWithGoogle("credential");
  const cache = new QueryClient({
    defaultOptions: {
      queries: { staleTime: Infinity, retry: false },
      mutations: { retry: false },
    },
  });
  const api = createAPI(auth, "https://sot.test/api/v1");
  const inactiveKey = api.queryOptions(
    "get",
    "/api/v1/workspaces/{workspace_id}/branches/{branch_id}/turns",
    { params: { path: { workspace_id: "w2", branch_id: "branch-1" } } },
  ).queryKey;
  cache.setQueryData(inactiveKey, []);
  render(
    <App auth={auth} queryClient={cache} apiBase="https://sot.test/api/v1" />,
  );
  await userEvent.click(
    (await screen.findAllByRole("button", { name: /세션 session-/ }))[0],
  );
  await screen.findByRole("checkbox", { name: /B로 결정/ });
  server.requests.length = 0;
  await userEvent.type(screen.getByLabelText("Agent message"), "검토해줘");
  await userEvent.click(screen.getByRole("button", { name: "보내기" }));
  expect(
    await screen.findByRole("checkbox", { name: /서버에 확정된 답변/ }),
  ).toBeVisible();
  await waitFor(() =>
    expect(screen.getByText("SESSION · BRANCH V3")).toBeVisible(),
  );
  expect(
    server.requests
      .map((request) => `${request.method} ${new URL(request.url).pathname}`)
      .sort(),
  ).toEqual([
    "GET /api/v1/workspaces/w1/branches/branch-1/turns",
    "GET /api/v1/workspaces/w1/sessions/session-1/branches",
    "POST /api/v1/workspaces/w1/branches/branch-1/agent",
  ]);
  expect(cache.getQueryState(inactiveKey)?.isInvalidated).toBe(false);
  expect(screen.queryByText("스트림 답변")).not.toBeInTheDocument();
});

it("retains the completed native chat and retries resources after a real Branch-list refetch failure", async () => {
  const server = createServer();
  server.state.sessions = [session];
  let failMetadata = false;
  const auth = new AuthSession(async (request) => {
    if (request.url.endsWith("/branches") && failMetadata) {
      server.requests.push(request.clone());
      return Response.json(
        {
          error: {
            code: "unavailable",
            message: "Branch metadata unavailable",
          },
        },
        { status: 503 },
      );
    }
    if (!request.url.endsWith("/agent")) return server.network(request);
    server.requests.push(request.clone());
    const run = await request.json();
    failMetadata = true;
    server.state.branchVersion = 3;
    return eventStream([
      { type: "RUN_STARTED", threadId: run.threadId, runId: run.runId },
      {
        type: "TEXT_MESSAGE_START",
        messageId: "complete-answer",
        role: "assistant",
      },
      {
        type: "TEXT_MESSAGE_CONTENT",
        messageId: "complete-answer",
        delta: "완료된 응답을 유지합니다",
      },
      { type: "TEXT_MESSAGE_END", messageId: "complete-answer" },
      { type: "RUN_FINISHED", threadId: run.threadId, runId: run.runId },
    ]);
  }, "https://sot.test/api/v1");
  await auth.loginWithGoogle("credential");
  render(<App auth={auth} apiBase="https://sot.test/api/v1" />);
  await userEvent.click(
    (await screen.findAllByRole("button", { name: /세션 session-/ }))[0],
  );
  await userEvent.type(
    await screen.findByLabelText("Agent message"),
    "검토해줘",
  );
  await userEvent.click(screen.getByRole("button", { name: "보내기" }));
  expect(await screen.findByText("Branch metadata unavailable")).toBeVisible();
  expect(screen.getByText("완료된 응답을 유지합니다")).toBeVisible();
  expect(screen.getByLabelText("Agent message")).toBeDisabled();
  failMetadata = false;
  await userEvent.click(screen.getByRole("button", { name: "동기화 재시도" }));
  await waitFor(() =>
    expect(screen.getByLabelText("Agent message")).toBeEnabled(),
  );
  expect(screen.getByText("SESSION · BRANCH V3")).toBeVisible();
  expect(
    screen.queryByText("Branch metadata unavailable"),
  ).not.toBeInTheDocument();
  expect(
    server.requests.filter((request) => request.url.endsWith("/agent")),
  ).toHaveLength(1);
  expect(
    server.requests.filter(
      (request) =>
        request.method === "POST" &&
        !request.url.endsWith("/google") &&
        !request.url.endsWith("/agent"),
    ),
  ).toHaveLength(0);
});

it("keeps approval separate from merge and requires current-member publish permission", async () => {
  const server = createServer();
  server.state.sessions = [session];
  server.state.proposals = [proposal];
  await server.auth.loginWithGoogle("credential");
  render(<App auth={server.auth} apiBase="https://sot.test/api/v1" />);
  await userEvent.click(await screen.findByRole("button", { name: "승인" }));
  expect(await screen.findByText("APPROVED")).toBeVisible();
  expect(
    server.requests.filter((request) => request.url.endsWith("/merge")),
  ).toHaveLength(0);
  await userEvent.click(await screen.findByRole("button", { name: "Merge" }));
  expect(await screen.findByText("MERGED")).toBeVisible();
  expect(
    await server.requests
      .find((request) => request.url.endsWith("/merge"))
      ?.json(),
  ).toEqual({ expected_version: 1 });
});

it("does not offer Merge to an approved proposal without document.publish", async () => {
  const server = createServer();
  server.state.permissions = [
    "document.read",
    "session.read",
    "session.participate",
  ];
  server.state.sessions = [session];
  server.state.proposals = [{ ...proposal, status: "approved" }];
  await server.auth.loginWithGoogle("credential");
  render(<App auth={server.auth} apiBase="https://sot.test/api/v1" />);
  expect(await screen.findByText("APPROVED")).toBeVisible();
  expect(
    screen.queryByRole("button", { name: "Merge" }),
  ).not.toBeInTheDocument();
});

it("lets an invited approver discover and decide a document Proposal while the author's private Session is denied", async () => {
  const server = createServer();
  const approver = {
    id: "approver-2",
    email: "approver@example.com",
    display_name: "Approver",
  };
  server.state.user = approver;
  server.state.permissions = ["document.read", "session.read"];
  server.state.sessions = [session];
  server.state.proposals = [
    {
      ...proposal,
      current_version: {
        ...proposal.current_version,
        required_approver_ids: [member.id, approver.id],
      },
      approvals: [
        {
          proposal_id: proposal.id,
          version: 1,
          approver_user_id: member.id,
          decision: "approve",
          decided_at: session.created_at,
        },
      ],
    },
  ];
  await server.auth.loginWithGoogle("approver-credential");
  expect(server.auth.user?.id).not.toBe(proposal.created_by);
  expect(
    (
      await server.auth.fetch(
        new Request("https://sot.test/api/v1/workspaces/w1/sessions/session-1"),
      )
    ).status,
  ).toBe(404);
  server.requests.length = 0;
  render(<App auth={server.auth} apiBase="https://sot.test/api/v1" />);
  expect(await screen.findByText("새 합의")).toBeVisible();
  expect(screen.queryByLabelText("Agent message")).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "승인" }));
  expect(await screen.findByText("APPROVED")).toBeVisible();
  expect(
    screen.queryByRole("button", { name: "Merge" }),
  ).not.toBeInTheDocument();
  expect(
    server.state.proposals[0].approvals.some(
      (approval) =>
        approval.approver_user_id === approver.id &&
        approval.decision === "approve",
    ),
  ).toBe(true);
  expect(
    server.requests.filter((request) =>
      request.url.includes("/sessions/session-1"),
    ),
  ).toHaveLength(0);
});

it("curates, previews, publishes, shares, then forks into the chosen destination workspace", async () => {
  const server = createServer();
  server.state.sessions = [session];
  await server.auth.loginWithGoogle("credential");
  render(<App auth={server.auth} apiBase="https://sot.test/api/v1" />);
  await userEvent.click(
    (await screen.findAllByRole("button", { name: /세션 session-/ }))[0],
  );
  await userEvent.click(
    await screen.findByRole("checkbox", { name: /B로 결정/ }),
  );
  await userEvent.type(screen.getByLabelText("인용 요약"), "B 선택");
  await userEvent.click(screen.getByRole("button", { name: "선별 적용" }));
  await userEvent.click(
    await screen.findByRole("button", { name: "Bundle 미리보기" }),
  );
  expect(
    await screen.findByRole("region", { name: "Bundle preview" }),
  ).toHaveTextContent("B로 결정");
  await userEvent.click(screen.getByRole("button", { name: "Bundle 발행" }));
  await userEvent.click(
    await screen.findByRole("button", { name: "Toss 만들기" }),
  );
  expect(await screen.findByRole("heading", { name: "B 선택" })).toBeVisible();
  await userEvent.selectOptions(
    screen.getByLabelText("Destination Workspace"),
    "w2",
  );
  await userEvent.click(screen.getByRole("button", { name: "Fork" }));
  await waitFor(() =>
    expect(screen.getByLabelText("Workspace")).toHaveValue("w2"),
  );
  expect(await screen.findByLabelText("Agent message")).toBeVisible();
  expect(screen.queryByLabelText("제안 본문")).not.toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "Proposal 만들기" }),
  ).not.toBeInTheDocument();
  expect(server.state.forks[0].document_id).toBeNull();
  const writes = server.requests.filter(
    (request) => request.method === "POST" && !request.url.endsWith("/google"),
  );
  expect(writes.map((request) => new URL(request.url).pathname)).toEqual([
    "/api/v1/workspaces/w1/branches/branch-1/curation-ops",
    "/api/v1/workspaces/w1/branches/branch-1/bundles",
    "/api/v1/workspaces/w1/bundles/bundle-1/tosses",
    "/api/v1/workspaces/w2/tosses/share-me/fork",
  ]);
  expect(await writes[0].json()).toEqual({
    expected_version: 2,
    operation: { kind: "join", turn_ids: ["turn-1"], content: "B 선택" },
  });
  expect(await writes[1].json()).toEqual({
    expected_version: 3,
    title: "B 선택",
  });
});

it("creates a Proposal against the canonical Session document instead of the selected document fallback", async () => {
  const server = createServer();
  server.state.sessions = [session];
  const auth = new AuthSession(async (request) => {
    if (request.url.endsWith("/sessions/session-1"))
      return Response.json({ ...session, document_id: "canonical-doc" });
    if (request.url.endsWith("/documents/canonical-doc/proposals")) {
      server.requests.push(request.clone());
      return Response.json(
        request.method === "POST"
          ? { ...proposal, document_id: "canonical-doc" }
          : [],
      );
    }
    return server.network(request);
  }, "https://sot.test/api/v1");
  await auth.loginWithGoogle("credential");
  render(<App auth={auth} apiBase="https://sot.test/api/v1" />);
  await userEvent.click(
    (await screen.findAllByRole("button", { name: /세션 session-/ }))[0],
  );
  await userEvent.type(
    await screen.findByLabelText("제안 본문"),
    "연결된 문서에 제안",
  );
  await userEvent.click(
    screen.getByRole("button", { name: "Proposal 만들기" }),
  );
  await waitFor(() =>
    expect(
      server.requests.filter(
        (request) =>
          request.method === "POST" &&
          request.url.endsWith("/documents/canonical-doc/proposals"),
      ),
    ).toHaveLength(1),
  );
  expect(
    server.requests.filter(
      (request) =>
        request.method === "POST" &&
        request.url.endsWith("/documents/doc-1/proposals"),
    ),
  ).toHaveLength(0);
});

it("validates and normalizes additional approvers without granting Session access", async () => {
  const server = createServer();
  server.state.sessions = [session];
  await server.auth.loginWithGoogle("credential");
  render(<App auth={server.auth} apiBase="https://sot.test/api/v1" />);
  await userEvent.click((await screen.findAllByRole("button", { name: /세션 session-/ }))[0]);
  await userEvent.type(await screen.findByLabelText("제안 본문"), "review this proposal");
  const approvers = screen.getByLabelText("추가 승인자 ID (쉼표로 구분)");
  await userEvent.type(approvers, "invalid-id");
  await userEvent.click(screen.getByRole("button", { name: "Proposal 만들기" }));
  expect(screen.getByRole("status")).toHaveTextContent("승인자 ID는 UUID 형식이어야 합니다");
  expect(server.requests.filter((request) => request.method === "POST" && request.url.endsWith("/proposals"))).toHaveLength(0);
  await userEvent.clear(approvers);
  const bob = "a56bf7ae-0bda-4297-a934-9007f7f63521";
  await userEvent.type(approvers, ` ${bob.toUpperCase()}, ${bob}, `);
  await userEvent.click(screen.getByRole("button", { name: "Proposal 만들기" }));
  await waitFor(() => expect(server.state.proposals).toHaveLength(1));
  const request = server.requests.find((item) => item.method === "POST" && item.url.endsWith("/proposals"));
  expect(await request?.json()).toMatchObject({ additional_approver_ids: [bob] });
  expect(server.requests.some((item) => item.method === "POST" && item.url.endsWith("/members"))).toBe(false);
});

it("retains the published Bundle citation when returning from Toss to the source Session", async () => {
  const server = createServer();
  server.state.sessions = [session];
  await server.auth.loginWithGoogle("credential");
  render(<App auth={server.auth} apiBase="https://sot.test/api/v1" />);
  await userEvent.click((await screen.findAllByRole("button", { name: /세션 session-/ }))[0]);
  await userEvent.type(await screen.findByLabelText("인용 요약"), "Evidence");
  await userEvent.click(screen.getByRole("button", { name: "Bundle 미리보기" }));
  await userEvent.click(await screen.findByRole("button", { name: "Bundle 발행" }));
  await userEvent.click(await screen.findByRole("button", { name: "Toss 만들기" }));
  expect(await screen.findByRole("heading", { name: "B 선택" })).toBeVisible();
  await userEvent.click(screen.getByRole("button", { name: /세션 session-/ }));
  await userEvent.type(await screen.findByLabelText("제안 본문"), "Cited proposal");
  await userEvent.click(screen.getByRole("button", { name: "Proposal 만들기" }));
  await waitFor(() => expect(server.state.proposals).toHaveLength(1));
  const request = server.requests.find((item) => item.method === "POST" && item.url.endsWith("/proposals"));
  expect(await request?.json()).toMatchObject({ bundle_ids: ["bundle-1"], citations: [{ bundle_id: "bundle-1", bundle_item_position: 0, claim_anchor: "Cited proposal" }] });
});
