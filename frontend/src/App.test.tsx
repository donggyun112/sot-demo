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

it("keeps approval separate from merge and requires current-member publish permission", async () => {
  const server = createServer();
  server.state.sessions = [session];
  server.state.proposals = [proposal];
  await server.auth.loginWithGoogle("credential");
  render(<App auth={server.auth} apiBase="https://sot.test/api/v1" />);
  await userEvent.click(
    (await screen.findAllByRole("button", { name: /세션 session-/ }))[0],
  );
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
  await userEvent.click(
    (await screen.findAllByRole("button", { name: /세션 session-/ }))[0],
  );
  expect(await screen.findByText("APPROVED")).toBeVisible();
  expect(
    screen.queryByRole("button", { name: "Merge" }),
  ).not.toBeInTheDocument();
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
  await userEvent.type(screen.getByLabelText("제안 본문"), "새 합의");
  await userEvent.click(
    screen.getByRole("button", { name: "Proposal 만들기" }),
  );
  expect(await screen.findByText("OPEN")).toBeVisible();
  const writes = server.requests.filter(
    (request) => request.method === "POST" && !request.url.endsWith("/google"),
  );
  expect(writes.map((request) => new URL(request.url).pathname)).toEqual([
    "/api/v1/workspaces/w1/branches/branch-1/curation-ops",
    "/api/v1/workspaces/w1/branches/branch-1/bundles",
    "/api/v1/workspaces/w1/bundles/bundle-1/tosses",
    "/api/v1/workspaces/w2/tosses/share-me/fork",
    "/api/v1/workspaces/w2/documents/doc-1/proposals",
  ]);
  expect(await writes[0].json()).toEqual({
    expected_version: 2,
    operation: { kind: "join", turn_ids: ["turn-1"], content: "B 선택" },
  });
  expect(await writes[1].json()).toEqual({
    expected_version: 3,
    title: "B 선택",
  });
  expect(await writes[4].json()).toEqual({
    source_session_id: "session-1",
    content: "새 합의",
    bundle_ids: ["bundle-1"],
    citations: [
      {
        bundle_id: "bundle-1",
        bundle_item_position: 0,
        claim_anchor: "새 합의",
      },
    ],
  });
});
