import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, SOTApi } from "./api";

const ok = (body: unknown = {}) =>
  Promise.resolve(
    new Response(JSON.stringify(body), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }),
  );

describe("SOTApi", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("sends the selected actor on every mutation", async () => {
    const fetchMock = vi.fn<
      (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>
    >((_input, _init) => ok());
    vi.stubGlobal("fetch", fetchMock);
    const api = new SOTApi("/api/v1", "bob");

    await api.createSession("document", "검토");
    await api.appendTurns("branch", [{ role: "user", content: "질문" }]);
    await api.createCite("branch", ["turn"], "결정");
    await api.createToss("cite");
    await api.forkToss("token");
    await api.createProposal("branch", "새 합의");
    await api.approveProposal("proposal");

    expect(fetchMock).toHaveBeenCalledTimes(7);
    for (const [, init] of fetchMock.mock.calls) {
      expect(new Headers(init?.headers).get("X-SOT-User")).toBe("bob");
    }
  });

  it("omits identity for public toss reads", async () => {
    const fetchMock = vi.fn<
      (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>
    >((_input, _init) => ok());
    vi.stubGlobal("fetch", fetchMock);

    await new SOTApi("/api/v1", "alice").getToss("public-token");

    const [, init] = fetchMock.mock.calls[0];
    expect(new Headers(init?.headers).has("X-SOT-User")).toBe(false);
  });

  it("turns problem responses into typed ApiError values", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve(
          new Response(
            JSON.stringify({
              error: { code: "branch_forbidden", message: "Not your branch" },
            }),
            { status: 403, headers: { "Content-Type": "application/json" } },
          ),
        ),
      ),
    );

    const failure = new SOTApi("/api/v1", "bob").appendTurns("branch", [
      { role: "user", content: "침범" },
    ]);

    await expect(failure).rejects.toMatchObject({
      name: "ApiError",
      code: "branch_forbidden",
      status: 403,
    } satisfies Partial<ApiError>);
  });
});
