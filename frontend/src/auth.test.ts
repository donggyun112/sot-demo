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
  let rejectRefresh: ((reason: unknown) => void) | undefined;
  const auth = new AuthSession(async (request) =>
    request.url.endsWith("/refresh")
      ? new Promise<Response>((_resolve, reject) => {
          rejectRefresh = reject;
        })
      : token("new-login"),
  );
  const restoring = auth.refresh().catch(() => {});
  await vi.waitFor(() => expect(rejectRefresh).not.toBeUndefined());
  const login = auth.loginWithGoogle("credential");
  rejectRefresh!(new TypeError("offline"));
  await Promise.all([restoring, login]);
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

it.each(["response", "refresh"] as const)(
  "never replays an older mutation after a new Google login while awaiting %s",
  async (delay) => {
    const requests: Request[] = [];
    let release: (response: Response) => void = () => {};
    let logins = 0;
    let mutations = 0;
    const auth = new AuthSession(async (request) => {
      requests.push(request.clone());
      if (request.url.endsWith("/google")) {
        logins++;
        return Response.json({
          access_token: `access-${logins}`,
          token_type: "bearer",
          user: { ...user, id: `user-${logins}` },
        });
      }
      if (request.url.endsWith("/mutation")) mutations++;
      if (
        (delay === "response" &&
          request.url.endsWith("/mutation") &&
          mutations === 1) ||
        (delay === "refresh" && request.url.endsWith("/refresh"))
      )
        return new Promise<Response>((resolve) => {
          release = resolve;
        });
      if (request.url.endsWith("/refresh"))
        return token("incorrect-new-session-refresh");
      return mutations === 1
        ? Response.json({}, { status: 401 })
        : Response.json({ ok: true });
    });
    await auth.loginWithGoogle("first-credential");
    const pending = auth.fetch(
      new Request("https://sot.test/api/v1/mutation", {
        method: "POST",
        body: "first-user-mutation",
      }),
    );
    const rejected = expect(pending).rejects.toMatchObject({
      name: "AbortError",
    });
    await vi.waitFor(() =>
      expect(requests).toHaveLength(delay === "response" ? 2 : 3),
    );
    const login = auth.loginWithGoogle("second-credential");
    release(
      delay === "response"
        ? Response.json({}, { status: 401 })
        : token("obsolete-refresh"),
    );
    await login;
    await rejected;
    expect(
      requests.filter((request) => request.url.endsWith("/mutation")),
    ).toHaveLength(1);
    expect(
      requests.filter((request) => request.url.endsWith("/refresh")),
    ).toHaveLength(delay === "response" ? 0 : 1);
    expect(auth.accessToken).toBe("access-2");
    expect(auth.user?.id).toBe("user-2");
  },
);

it("does not clear a newer Google login when an older logout response arrives", async () => {
  let finishLogout: ((response: Response) => void) | undefined;
  const auth = new AuthSession(async (request) =>
    request.url.endsWith("/logout")
      ? new Promise<Response>((resolve) => {
          finishLogout = resolve;
        })
      : token("new-login"),
  );
  await auth.loginWithGoogle("first-credential");
  const logout = auth.logout();
  await vi.waitFor(() => expect(finishLogout).not.toBeUndefined());
  const login = auth.loginWithGoogle("second-credential");
  finishLogout!(new Response(null, { status: 204 }));
  await Promise.all([logout, login]);
  expect(auth.accessToken).toBe("new-login");
  expect(auth.user).toEqual(user);
});

it.each(["refresh", "logout", "recovery"] as const)(
  "orders delayed %s cookie headers before a newer login, including cookie-driven reload",
  async (operation) => {
    let cookie: string | null = null;
    let release: (() => void) | undefined;
    const calls: string[] = [];
    const network = async (request: Request) => {
      const path = request.url.split("/").at(-1)!;
      calls.push(path);
      if (path === "protected") return Response.json({}, { status: 401 });
      const owner = path === "google"
        ? (await request.json()).credential as string
        : path === "logout" ? null : cookie;
      if ((path === "logout" || path === "refresh") && !release) {
        await new Promise<void>((resolve) => { release = resolve; });
      }
      // Browsers apply response cookies even if AuthSession ignores the body.
      cookie = owner;
      if (path === "logout") return new Response(null, { status: 204 });
      if (!owner) return Response.json({}, { status: 401 });
      return Response.json({ access_token: owner, token_type: "bearer", user: { ...user, id: owner } });
    };
    const auth = new AuthSession(network);
    await auth.loginWithGoogle("alice");
    const older = operation === "logout" ? auth.logout()
      : operation === "refresh" ? auth.refresh()
      : auth.fetch(new Request("https://sot.test/protected")).catch((error: unknown) => {
        expect(error).toMatchObject({ name: "AbortError" });
      });
    await vi.waitFor(() => expect(release).toBeDefined());
    const newer = auth.loginWithGoogle("bob");
    await Promise.resolve();
    await Promise.resolve();
    const callsBeforeRelease = [...calls];
    release!();
    await Promise.all([older, newer]);
    const reloaded = new AuthSession(network);
    await reloaded.refresh();
    expect(reloaded.user?.id).toBe("bob");
    expect(callsBeforeRelease.filter((path) => path === "google")).toHaveLength(1);
  },
);

it("orders Google login, refresh, logout and another login by invocation, without coalescing across identities", async () => {
  let release: (() => void) | undefined;
  const calls: string[] = [];
  const auth = new AuthSession(async (request) => {
    const path = request.url.split("/").at(-1)!;
    calls.push(path);
    if (calls.length === 1) await new Promise<void>((resolve) => { release = resolve; });
    return path === "logout" ? new Response(null, { status: 204 }) : token(path);
  });
  const first = auth.loginWithGoogle("alice");
  await vi.waitFor(() => expect(release).toBeDefined());
  const operations = [first, auth.refresh(), auth.logout(), auth.loginWithGoogle("bob"), auth.refresh()];
  await Promise.resolve();
  const before = [...calls];
  release!();
  await Promise.all(operations);
  expect(before).toEqual(["google"]);
  expect(calls).toEqual(["google", "refresh", "logout", "google", "refresh"]);
  expect(auth.accessToken).toBe("refresh");
});
