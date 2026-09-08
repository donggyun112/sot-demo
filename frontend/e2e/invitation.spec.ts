import { expect, test, type Page } from "@playwright/test";
import { openWorkspace } from "./workspace";

const api = "http://127.0.0.1:18001/api/v1";

async function login(page: Page, actor: "alice" | "bob") {
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
  return (await (await response).json()) as {
    access_token: string;
    user: { id: string; email: string };
  };
}

test("an invitation is not membership until it is accepted", async ({ browser }) => {
  const owner = await browser.newContext();
  const guest = await browser.newContext();
  try {
    const alice = await owner.newPage();
    const carol = await guest.newPage();
    const aliceLogin = await login(alice, "alice");
    await openWorkspace(alice, "Alice Workspace");
    const carolLogin = await login(carol, "bob");

    // A workspace the guest is not in, so the invitation is what lets them in.
    const made = await owner.request.post(`${api}/workspaces`, {
      headers: { Authorization: `Bearer ${aliceLogin.access_token}` },
      data: { name: `Invited ${Date.now()}` },
    });
    expect(made.status()).toBe(201);
    const workspaceId = (await made.json()).id as string;
    expect(
      (
        await guest.request.get(`${api}/workspaces/${workspaceId}/documents`, {
          headers: { Authorization: `Bearer ${carolLogin.access_token}` },
        })
      ).status(),
    ).toBe(403);

    await alice.goto(`/w/${workspaceId}/members`);
    await expect(alice.getByRole("heading", { name: "Members" })).toBeVisible();

    // Invite an address nobody has signed up with yet.
    const address = `newcomer-${Date.now()}@example.com`;
    const issued = alice.waitForResponse(
      (r) => r.request().method() === "POST" && r.url().endsWith("/invitations"),
    );
    await alice.getByLabel("Email").fill(address.toUpperCase());
    await alice.getByRole("button", { name: "Send invitation" }).click();
    const invitation = await (await issued).json();

    // Nothing carried it here, so the inviter is handed the code.
    expect(invitation.code).toMatch(/^[A-Z2-9]{10}$/);
    await expect(alice.getByText("Pass this code to them")).toBeVisible();
    // The address is stored in one spelling, and the invitation waits.
    await expect(alice.getByText(address)).toBeVisible();
    await expect(
      alice.getByRole("heading", { name: "Waiting to be accepted" }),
    ).toBeVisible();

    // A listing never carries the code: it is a credential, not a status.
    const listed = await (
      await owner.request.get(`${api}/workspaces/${workspaceId}/invitations`, {
        headers: { Authorization: `Bearer ${aliceLogin.access_token}` },
      })
    ).json();
    expect(listed).toHaveLength(1);
    expect(listed[0].code).toBeNull();

    // A wrong code is not a way in.
    const refused = await guest.request.post(`${api}/invitations/redeem`, {
      headers: { Authorization: `Bearer ${carolLogin.access_token}` },
      data: { code: "AAAAAAAAAA" },
    });
    expect(refused.status()).toBe(404);

    // The real code joins them, under whatever address they signed in with.
    const joined = await guest.request.post(`${api}/invitations/redeem`, {
      headers: { Authorization: `Bearer ${carolLogin.access_token}` },
      data: { code: invitation.code },
    });
    expect(joined.status()).toBe(201);
    expect(await joined.json()).toMatchObject({
      workspace_id: workspaceId,
      user_id: carolLogin.user.id,
      role: "member",
    });

    // Spent: the same code cannot be redeemed twice.
    expect(
      (
        await guest.request.post(`${api}/invitations/redeem`, {
          headers: { Authorization: `Bearer ${carolLogin.access_token}` },
          data: { code: invitation.code },
        })
      ).status(),
    ).toBe(404);

    // The workspace now lists them, and nothing is left waiting.
    await alice.reload();
    await expect(alice.getByRole("heading", { name: "Members" })).toBeVisible();
    await expect(alice.getByText("No invitations are waiting.")).toBeVisible();
    const roster = await (
      await owner.request.get(`${api}/workspaces/${workspaceId}/members`, {
        headers: { Authorization: `Bearer ${aliceLogin.access_token}` },
      })
    ).json();
    expect(
      roster.map((item: { user_id: string }) => item.user_id),
    ).toContain(carolLogin.user.id);
  } finally {
    await Promise.allSettled([owner.close(), guest.close()]);
  }
});
