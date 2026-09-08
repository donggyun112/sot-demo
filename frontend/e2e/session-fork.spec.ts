import { expect, test, type BrowserContext, type Page } from "@playwright/test";
import type { components } from "../src/generated/api";

const api = "http://127.0.0.1:18001/api/v1";
type Login = components["schemas"]["AuthResponse"];
type Turn = components["schemas"]["TurnResponse"];

async function login(page: Page, actor: "alice" | "bob"): Promise<Login> {
  await page.route("https://accounts.google.com/gsi/client", (route) =>
    route.fulfill({
      contentType: "application/javascript",
      body: `
      let options;
      window.google = { accounts: { id: {
        initialize(value) { options = value; },
        renderButton(element) {
          const button = document.createElement('button');
          button.textContent = 'Sign in with Google';
          button.onclick = () => options.callback({ credential: 'google-test-${actor}' });
          element.replaceChildren(button);
        }
      } } };`,
    }),
  );
  const response = page.waitForResponse((r) => r.url().endsWith("/auth/google"));
  await page.goto("/");
  await page.getByRole("button", { name: "Sign in with Google" }).click();
  return (await (await response).json()) as Login;
}

async function openWorkspace(page: Page, name: string) {
  await page.getByRole("button", { name: "Workspaces" }).click();
  await page.getByRole("menuitem", { name, exact: true }).click();
  await page.waitForURL(/\/w\/[^/]+$/);
  return new URL(page.url()).pathname.split("/")[2];
}

async function get(context: BrowserContext, path: string, auth: Login) {
  return context.request.get(`${api}${path}`, {
    headers: { Authorization: `Bearer ${auth.access_token}` },
  });
}

test("a viewer continues the conversation in a session of their own", async ({
  browser,
}) => {
  const ownerContext = await browser.newContext();
  const readerContext = await browser.newContext();
  try {
    const alice = await ownerContext.newPage();
    const bob = await readerContext.newPage();
    const aliceLogin = await login(alice, "alice");
    const bobLogin = await login(bob, "bob");
    const aw = await openWorkspace(alice, "Alice Workspace");
    await openWorkspace(bob, "Bob Workspace");

    // Its own document: these sessions must not show up in another test's
    // assertions about who holds what.
    const made = await ownerContext.request.post(
      `${api}/workspaces/${aw}/documents`,
      {
        headers: { Authorization: `Bearer ${aliceLogin.access_token}` },
        data: { title: `Fork ${Date.now()}`, content: "초기 합의" },
      },
    );
    expect(made.status()).toBe(201);
    const documentId = (await made.json()).document.id as string;

    // Alice holds a conversation in her own session.
    await alice.goto(`/w/${aw}/documents/${documentId}/sessions`);
    const createdResponse = alice.waitForResponse(
      (res) => res.request().method() === "POST" && res.url().endsWith("/sessions"),
    );
    await alice.getByRole("button", { name: "New session" }).click();
    const created = await (await createdResponse).json();
    const branchPath = `/workspaces/${aw}/branches/${created.branch_id}`;
    const prompt = "Should the limit be per account or per token?";
    const streamed = alice.waitForResponse((res) => res.url().endsWith("/agent"));
    await alice.getByLabel("Agent message").fill(prompt);
    await alice.getByLabel("Agent message").press("Enter");
    // The turns are stored as the run finishes, so read the stream out first.
    await (await streamed).text();
    const stored = (await (
      await get(ownerContext, `${branchPath}/turns`, aliceLogin)
    ).json()) as Turn[];
    expect(stored).toHaveLength(2);

    // She sends it to Bob to READ. He can follow it and not answer in it.
    const sent = await ownerContext.request.post(
      `${api}/workspaces/${aw}/sessions/${created.session_id}/members`,
      {
        headers: { Authorization: `Bearer ${aliceLogin.access_token}` },
        data: { user_id: bobLogin.user.id, role: "viewer" },
      },
    );
    expect(sent.status()).toBe(201);

    await bob.goto(`/w/${aw}/sessions/${created.session_id}`);
    await expect(bob.getByRole("paragraph").filter({ hasText: prompt })).toBeVisible();

    // The way out of a read-only session is a session of his own.
    const forked = bob.waitForResponse(
      (res) => res.request().method() === "POST" && res.url().endsWith("/forks"),
    );
    await bob
      .getByRole("button", { name: "Continue in a session of your own" })
      .click();
    const fork = await (await forked).json();
    expect(fork.session_id).not.toBe(created.session_id);
    await expect(bob).toHaveURL(new RegExp(`/sessions/${fork.session_id}`));
    await expect(bob.getByText("Forked from a session")).toBeVisible();

    // The conversation came across word for word, and it is his to write in.
    const copied = (await (
      await get(
        readerContext,
        `/workspaces/${aw}/branches/${fork.branch_id}/turns`,
        bobLogin,
      )
    ).json()) as Turn[];
    expect(copied.map((turn) => [turn.role, turn.content])).toEqual(
      stored.map((turn) => [turn.role, turn.content]),
    );
    expect(copied.map((turn) => turn.id)).not.toEqual(stored.map((turn) => turn.id));
    // Copying what someone said does not make the copier its author, so the
    // transcript reads under Alice's name even in Bob's session.
    expect(new Set(copied.map((turn) => turn.created_by))).toEqual(
      new Set([aliceLogin.user.id]),
    );
    await expect(
      bob.getByRole("article").filter({ hasText: prompt }).getByText("Alice"),
    ).toBeVisible();

    const answered = bob.waitForResponse((res) => res.url().endsWith("/agent"));
    await bob.getByLabel("Agent message").fill("Per account.");
    await bob.getByLabel("Agent message").press("Enter");
    await (await answered).text();
    const afterBob = (await (
      await get(
        readerContext,
        `/workspaces/${aw}/branches/${fork.branch_id}/turns`,
        bobLogin,
      )
    ).json()) as Turn[];
    expect(afterBob.at(-1)?.created_by).toBe(bobLogin.user.id);
    expect(
      (
        (await (
          await get(
            readerContext,
            `/workspaces/${aw}/branches/${fork.branch_id}/turns`,
            bobLogin,
          )
        ).json()) as Turn[]
      ).length,
    ).toBeGreaterThan(copied.length);

    // Alice's session is untouched: a fork is a copy, not a shared desk.
    const untouched = (await (
      await get(ownerContext, `${branchPath}/turns`, aliceLogin)
    ).json()) as Turn[];
    expect(untouched.map((turn) => turn.id)).toEqual(stored.map((turn) => turn.id));

    // And the fork is Bob's: Alice was never added to it.
    expect(
      (
        await get(
          ownerContext,
          `/workspaces/${aw}/sessions/${fork.session_id}`,
          aliceLogin,
        )
      ).status(),
    ).toBe(404);
  } finally {
    await Promise.allSettled([ownerContext.close(), readerContext.close()]);
  }
});
