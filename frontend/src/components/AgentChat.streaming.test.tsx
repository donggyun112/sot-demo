import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import "../i18n";
import { AuthSession } from "../auth";
import { member } from "../test/server";
import { AgentChat } from "./AgentChat";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

async function harness(
  mode: "success" | "401" | "repeat401" | "refreshFailure" = "success",
) {
  const requests: Request[] = [];
  let stream: ReadableStreamDefaultController<Uint8Array>;
  let started: { threadId: string; runId: string };
  let runs = 0;
  const network = async (input: RequestInfo | URL, init?: RequestInit) => {
    const request = input instanceof Request ? input : new Request(input, init);
    requests.push(request.clone());
    if (request.url.endsWith("/google"))
      return Response.json({
        access_token: "expired-access",
        token_type: "bearer",
        user: member,
      });
    if (request.url.endsWith("/refresh"))
      return mode === "refreshFailure"
        ? Response.json({}, { status: 401 })
        : Response.json({
            access_token: "fresh-access",
            token_type: "bearer",
            user: member,
          });
    if (!request.url.endsWith("/agent"))
      throw new Error("Unexpected transcript write");
    runs++;
    if (
      mode === "repeat401" ||
      mode === "refreshFailure" ||
      (mode === "401" && runs === 1)
    )
      return Response.json({}, { status: 401 });
    const body = await request.json();
    started = { threadId: body.threadId, runId: body.runId };
    const bodyStream = new ReadableStream<Uint8Array>({
      start(controller) {
        stream = controller;
      },
    });
    return new Response(bodyStream, {
      headers: { "Content-Type": "text/event-stream" },
    });
  };
  vi.stubGlobal("fetch", network);
  // The SDK logs transport failures; suppress expected errors only in these tests.
  vi.spyOn(console, "error").mockImplementation(() => {});
  const auth = new AuthSession(
    (request) => network(request),
    "https://sot.test/api/v1",
  );
  await auth.loginWithGoogle("credential");
  const onSaved = vi.fn(async () => {});
  const props = {
    auth,
    apiBase: "https://sot.test/api/v1",
    workspaceId: "w1",
    branchId: "branch-1",
    sessionId: "session-1",
    turns: [],
    onSaved,
    youLabel: "You",
  };
  const rendered = render(<AgentChat {...props} />);
  await userEvent.type(screen.getByLabelText("Agent message"), "검토해줘");
  await userEvent.click(screen.getByRole("button", { name: "Send" }));
  const emit = async (...events: object[]) =>
    act(async () => {
      for (const event of events)
        stream.enqueue(
          new TextEncoder().encode(`data: ${JSON.stringify(event)}\n\n`),
        );
    });
  const start = async () => {
    await waitFor(() => expect(stream).toBeDefined());
    await emit(
      { type: "RUN_STARTED", ...started },
      {
        type: "TEXT_MESSAGE_START",
        messageId: "assistant-streamed",
        role: "assistant",
      },
      {
        type: "TEXT_MESSAGE_CONTENT",
        messageId: "assistant-streamed",
        delta: "부분 응답",
      },
    );
  };
  const finish = async () => {
    await emit(
      { type: "TEXT_MESSAGE_END", messageId: "assistant-streamed" },
      { type: "RUN_FINISHED", ...started },
    );
    await act(async () => stream.close());
  };
  return {
    requests,
    auth,
    onSaved,
    props,
    rendered,
    emit,
    start,
    finish,
    get stream() {
      return stream;
    },
  };
}

it("keeps a delayed native stream connected across rerenders and refetches only after RUN_FINISHED", async () => {
  const h = await harness();
  await h.start();
  h.rendered.rerender(<AgentChat {...h.props} turns={[]} />);
  expect(screen.getByText("부분 응답")).toBeVisible();
  expect(h.onSaved).not.toHaveBeenCalled();
  await h.finish();
  await waitFor(() => expect(h.onSaved).toHaveBeenCalledOnce());
  expect(
    h.requests.filter((request) => request.url.endsWith("/agent")),
  ).toHaveLength(1);
  const wire = h.requests.find((request) => request.url.endsWith("/agent"))!;
  expect(wire.url).toBe(
    "https://sot.test/api/v1/workspaces/w1/branches/branch-1/agent",
  );
  expect(wire.headers.get("Authorization")).toBe("Bearer expired-access");
  expect(wire.headers.has("X-SOT-User")).toBe(false);
});

it("refreshes and retries a pre-event HTTP 401 exactly once through supported SDK headers", async () => {
  const h = await harness("401");
  await h.start();
  await h.finish();
  await waitFor(() => expect(h.onSaved).toHaveBeenCalledOnce());
  expect(
    h.requests
      .filter((request) => request.url.endsWith("/agent"))
      .map((request) => request.headers.get("Authorization")),
  ).toEqual(["Bearer expired-access", "Bearer fresh-access"]);
  expect(
    h.requests.filter((request) => request.url.endsWith("/refresh")),
  ).toHaveLength(1);
});

it.each(["repeat401", "refreshFailure"] as const)(
  "stops after the single auth retry boundary: %s",
  async (mode) => {
    const h = await harness(mode);
    await waitFor(() =>
      expect(screen.getByLabelText("Agent message")).toBeEnabled(),
    );
    expect(
      h.requests.filter((request) => request.url.endsWith("/agent")),
    ).toHaveLength(mode === "repeat401" ? 2 : 1);
    expect(
      h.requests.filter((request) => request.url.endsWith("/refresh")),
    ).toHaveLength(1);
    expect(screen.getByLabelText("Agent message")).toHaveValue("검토해줘");
    expect(h.onSaved).not.toHaveBeenCalled();
    if (mode === "refreshFailure") expect(h.auth.accessToken).toBeNull();
  },
);

it.each(["model_error", undefined])(
  "retains input and partial output on RUN_ERROR without refetch or retry (%s)",
  async (code) => {
    const h = await harness();
    await h.start();
    await h.emit({
      type: "RUN_ERROR",
      message: "provider rejected",
      ...(code ? { code } : {}),
    });
    await act(async () => h.stream.close());
    expect(await screen.findByText(/provider rejected/)).toBeVisible();
    expect(screen.queryByText(/undefined/)).not.toBeInTheDocument();
    expect(screen.getByText("부분 응답")).toBeVisible();
    expect(screen.getByLabelText("Agent message")).toHaveValue("검토해줘");
    expect(h.onSaved).not.toHaveBeenCalled();
    expect(h.requests).toHaveLength(2);
  },
);

it.each([
  new DOMException("signal is aborted without reason", "AbortError"),
  Object.assign(new Error("late auth failure"), { status: 401 }),
])("preserves partial output after events without retry: %s", async (error) => {
  const h = await harness();
  await h.start();
  await act(async () => h.stream.error(error));
  expect(await screen.findByText(new RegExp(error.message))).toBeVisible();
  expect(screen.getByText("부분 응답")).toBeVisible();
  expect(screen.getByLabelText("Agent message")).toHaveValue("검토해줘");
  expect(h.onSaved).not.toHaveBeenCalled();
  expect(h.requests).toHaveLength(2);
});

it("stopping a stream retains partial text and input without canonical refetch", async () => {
  const h = await harness();
  await h.start();
  await userEvent.click(screen.getByRole("button", { name: "Stop" }));
  await waitFor(() =>
    expect(screen.getByLabelText("Agent message")).toBeEnabled(),
  );
  expect(screen.getByText("부분 응답")).toBeVisible();
  expect(screen.getByLabelText("Agent message")).toHaveValue("검토해줘");
  expect(h.onSaved).not.toHaveBeenCalled();
});

it("keeps submission disabled until committed resources finish refetching", async () => {
  const h = await harness();
  let finishRefetch: () => void = () => {};
  h.onSaved.mockImplementationOnce(
    () =>
      new Promise<void>((resolve) => {
        finishRefetch = resolve;
      }),
  );
  await h.start();
  await h.finish();
  await waitFor(() => expect(h.onSaved).toHaveBeenCalledOnce());
  expect(screen.getByLabelText("Agent message")).toBeDisabled();
  await act(async () => finishRefetch());
  expect(screen.getByLabelText("Agent message")).toBeEnabled();
});

it("retries only resource refetch after failure and keeps completed output visible", async () => {
  const h = await harness();
  h.onSaved.mockRejectedValueOnce(new Error("database unavailable"));
  await h.start();
  await h.finish();
  expect(
    await screen.findByRole("button", { name: "Retry sync" }),
  ).toBeVisible();
  expect(screen.getByText("부분 응답")).toBeVisible();
  expect(screen.getByLabelText("Agent message")).toBeDisabled();
  await userEvent.click(screen.getByRole("button", { name: "Retry sync" }));
  await waitFor(() =>
    expect(screen.getByLabelText("Agent message")).toBeEnabled(),
  );
  expect(h.onSaved).toHaveBeenCalledTimes(2);
  expect(
    h.requests.filter((request) => request.url.endsWith("/agent")),
  ).toHaveLength(1);
  expect(
    screen.queryByRole("button", { name: "Retry sync" }),
  ).not.toBeInTheDocument();
});
