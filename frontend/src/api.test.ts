import { QueryClient } from "@tanstack/react-query";
import { expect, it } from "vitest";
import { AuthSession } from "./auth";
import { createAPI } from "./api";

it("isolates same-id resources by workspace using generated query keys and real bearer requests", async () => {
  const requests: Request[] = [];
  const auth = new AuthSession(async (request) => {
    requests.push(request.clone());
    return request.url.endsWith("/google")
      ? Response.json({
          access_token: "real-access",
          token_type: "bearer",
          user: { id: "u", email: "u@example.com", display_name: "U" },
        })
      : Response.json({
          id: "s",
          workspace_id: request.url.includes("/w1/") ? "w1" : "w2",
          document_id: null,
          created_by: "u",
          created_at: "2026-09-06T00:00:00Z",
        status: "open",
        });
  }, "https://sot.test/api/v1");
  await auth.loginWithGoogle("credential");
  const api = createAPI(auth, "https://sot.test/api/v1");
  const cache = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  for (const workspace_id of ["w1", "w2"]) {
    const data = await cache.fetchQuery(
      api.queryOptions(
        "get",
        "/api/v1/workspaces/{workspace_id}/sessions/{session_id}",
        { params: { path: { workspace_id, session_id: "s" } } },
      ),
    );
    expect(data.workspace_id).toBe(workspace_id);
  }
  expect(requests.slice(1).map((request) => request.url)).toEqual([
    "https://sot.test/api/v1/workspaces/w1/sessions/s",
    "https://sot.test/api/v1/workspaces/w2/sessions/s",
  ]);
  expect(
    requests
      .slice(1)
      .every(
        (request) =>
          request.headers.get("Authorization") === "Bearer real-access" &&
          !request.headers.has("X-SOT-User"),
      ),
  ).toBe(true);
  cache.clear();
});

it("decodes stable error envelopes and falls back safely for malformed upstream errors", async () => {
  for (const [body, code, message] of [
    [
      {
        error: {
          code: "version_conflict",
          message: "Branch changed",
          details: {},
        },
      },
      "version_conflict",
      "Branch changed",
    ],
    [
      { error: { code: 1, message: {} } },
      "request_failed",
      "Request failed with 409",
    ],
  ] as const) {
    const auth = new AuthSession(async () =>
      Response.json(body, { status: 409 }),
    );
    const api = createAPI(auth);
    const cache = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    await expect(
      cache.fetchQuery(api.queryOptions("get", "/api/v1/me")),
    ).rejects.toMatchObject({ status: 409, code, message });
    cache.clear();
  }
});
