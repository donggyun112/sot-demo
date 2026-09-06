import { beforeEach, expect, it, vi } from "vitest";
import { AuthSession } from "./auth";

const user = {
  id: "user-1",
  email: "member@example.com",
  display_name: "Member",
};
const token = (value: string) =>
  Response.json({ access_token: value, token_type: "bearer", user });
beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
});

it("sends only the Google credential and keeps tokens in memory while refreshing by cookie", async () => {
  const requests: Request[] = [];
  const network = vi.fn(async (request: Request) => {
    requests.push(request);
    return token(request.url.endsWith("/refresh") ? "access-2" : "access-1");
  });
  const auth = new AuthSession(network, "https://sot.test/api/v1");
  await auth.loginWithGoogle("google-credential");
  expect(await requests[0].json()).toEqual({ credential: "google-credential" });
  expect(auth.accessToken).toBe("access-1");
  await auth.refresh();
  expect(requests.map((request) => [request.url, request.credentials])).toEqual(
    [
      ["https://sot.test/api/v1/auth/google", "include"],
      ["https://sot.test/api/v1/auth/refresh", "include"],
    ],
  );
  expect(auth.accessToken).toBe("access-2");
  expect(localStorage.length).toBe(0);
  expect(sessionStorage.length).toBe(0);
});

it("refreshes and replays a protected request once with the real bearer and original body", async () => {
  const requests: Request[] = [];
  let protectedCalls = 0;
  const auth = new AuthSession(async (request) => {
    requests.push(request.clone());
    if (request.url.endsWith("/google")) return token("expired-access");
    if (request.url.endsWith("/refresh")) return token("fresh-access");
    protectedCalls++;
    return protectedCalls === 1
      ? Response.json({}, { status: 401 })
      : Response.json({ ok: true });
  }, "https://sot.test/api/v1");
  await auth.loginWithGoogle("credential");
  const response = await auth.fetch(
    new Request("https://sot.test/api/v1/workspaces/w/sessions/s", {
      method: "POST",
      body: JSON.stringify({ value: 1 }),
    }),
  );
  expect(response.ok).toBe(true);
  expect(
    requests
      .slice(1)
      .map((request) => [
        request.url.split("/").at(-1),
        request.headers.get("Authorization"),
      ]),
  ).toEqual([
    ["s", "Bearer expired-access"],
    ["refresh", null],
    ["s", "Bearer fresh-access"],
  ]);
  expect(await requests[1].json()).toEqual({ value: 1 });
  expect(await requests[3].json()).toEqual({ value: 1 });
});

it("does not refresh a second 401 and clears memory when refresh fails", async () => {
  let refreshes = 0;
  let refreshFails = false;
  const auth = new AuthSession(async (request) => {
    if (request.url.endsWith("/google")) return token("access");
    if (request.url.endsWith("/refresh")) {
      refreshes++;
      return refreshFails
        ? Response.json({}, { status: 401 })
        : token("renewed");
    }
    return Response.json({}, { status: 401 });
  }, "https://sot.test/api/v1");
  await auth.loginWithGoogle("credential");
  expect(
    (await auth.fetch(new Request("https://sot.test/api/v1/me"))).status,
  ).toBe(401);
  expect(refreshes).toBe(1);
  refreshFails = true;
  await expect(
    auth.fetch(new Request("https://sot.test/api/v1/me")),
  ).rejects.toThrow();
  expect(auth.accessToken).toBeNull();
  expect(auth.user).toBeNull();
  expect(refreshes).toBe(2);
});

it("allows independent concurrent Google logins", async () => {
  const sessions = [
    new AuthSession(async () => token("one")),
    new AuthSession(async () => token("two")),
  ];
  await Promise.all(sessions.map((auth) => auth.loginWithGoogle("credential")));
  expect(sessions.map((auth) => auth.accessToken)).toEqual(["one", "two"]);
});

it("does not let an older refresh failure erase a newer Google login", async () => {
  let rejectRefresh: (reason: unknown) => void = () => {};
  const auth = new AuthSession(async (request) =>
    request.url.endsWith("/refresh")
      ? new Promise<Response>((_resolve, reject) => {
          rejectRefresh = reject;
        })
      : token("new-login"),
  );
  const restoring = auth.refresh().catch(() => {});
  await auth.loginWithGoogle("credential");
  rejectRefresh(new TypeError("offline"));
  await restoring;
  expect(auth.accessToken).toBe("new-login");
});

it("does not replay a request aborted while its cookie refresh is pending", async () => {
  let finishRefresh: (response: Response) => void = () => {};
  const requests: Request[] = [];
  const auth = new AuthSession(async (request) => {
    requests.push(request);
    if (request.url.endsWith("/refresh"))
      return new Promise<Response>((resolve) => {
        finishRefresh = resolve;
      });
    return Response.json({}, { status: 401 });
  });
  const controller = new AbortController();
  const pending = auth.fetch(
    new Request("https://sot.test/api/v1/me", { signal: controller.signal }),
  );
  await vi.waitFor(() => expect(requests).toHaveLength(2));
  controller.abort();
  finishRefresh(token("renewed"));
  await expect(pending).rejects.toMatchObject({ name: "AbortError" });
  expect(requests).toHaveLength(2);
});
