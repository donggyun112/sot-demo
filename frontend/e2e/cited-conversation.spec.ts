import { expect, test, type Page } from "@playwright/test";

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
    user: { id: string };
  };
}

async function openWorkspace(page: Page, name: string) {
  await page.getByRole("button", { name: "Workspaces" }).click();
  await page.getByRole("menuitem", { name, exact: true }).click();
  await page.waitForURL(/\/w\/[^/]+$/);
  return new URL(page.url()).pathname.split("/")[2];
}

test("a merged passage leads back to the conversation that wrote it", async ({
  browser,
}) => {
  // This is what the record is for. Without it a citation is an ordinal:
  // "bundle 1, item 2", which tells a reader nothing and leads nowhere.
  const context = await browser.newContext();
  try {
    const alice = await context.newPage();
    const login1 = await login(alice, "alice");
    const auth = { Authorization: `Bearer ${login1.access_token}` };
    const aw = await openWorkspace(alice, "Alice Workspace");

    const made = await context.request.post(`${api}/workspaces/${aw}/documents`, {
      headers: auth,
      data: { title: `Cited ${Date.now()}`, content: "" },
    });
    const documentId = (await made.json()).document.id as string;

    // The conversation, held in a session.
    const created = await (
      await context.request.post(
        `${api}/workspaces/${aw}/documents/${documentId}/sessions`,
        { headers: auth, data: {} },
      )
    ).json();
    await alice.goto(`/w/${aw}/sessions/${created.session_id}`);
    const streamed = alice.waitForResponse((r) => r.url().endsWith("/agent"));
    const asked = "감사 로그를 남겨야 하나?";
    await alice.getByLabel("Agent message").fill(asked);
    await alice.getByLabel("Agent message").press("Enter");
    await (await streamed).text();

    // The update written by the agent's own tool call, so the passage can
    // point at the moment it was written rather than at the whole session.
    const wrote = alice.waitForResponse((r) => r.url().endsWith("/agent"));
    await alice.getByLabel("Agent message").fill("write the audit section");
    await alice.getByLabel("Agent message").press("Enter");
    await (await wrote).text();
    const proposals = (await (
      await context.request.get(
        `${api}/workspaces/${aw}/documents/${documentId}/proposals`,
        { headers: auth },
      )
    ).json()) as { id: string; status: string }[];
    const proposed = proposals.find((one) => one.status === "open")!;
    expect(proposed).toBeDefined();
    await context.request.post(
      `${api}/workspaces/${aw}/proposals/${proposed.id}/decisions`,
      { headers: auth, data: { expected_version: 1, decision: "approve" } },
    );
    expect(
      (
        await context.request.post(
          `${api}/workspaces/${aw}/proposals/${proposed.id}/merge`,
          { headers: auth, data: { expected_version: 1 } },
        )
      ).status(),
    ).toBe(200);

    // The passage in the document leads to the sot_update call that wrote it.
    await alice.goto(`/w/${aw}/documents/${documentId}`);
    const passage = alice
      .locator("[data-cited]")
      .filter({ hasText: "audit" });
    await expect(passage).toBeVisible();
    await passage
      .getByRole("link", { name: "The update that wrote this" })
      .click();
    await expect(alice).toHaveURL(new RegExp(`/sessions/${created.session_id}`));
    await expect(alice).toHaveURL(/call=/);
    // Landed on the call, opened and marked.
    const marked = alice.locator('details[data-marked="true"]');
    await expect(marked).toContainText("sot_update");
    await expect(
      alice.getByRole("paragraph").filter({ hasText: asked }),
    ).toBeVisible();

    // And the rail still shows what was actually said, not an ordinal.
    await alice.goto(`/w/${aw}/documents/${documentId}?panel=evidence`);
    const rail = alice.getByRole("region", { name: "Evidence" });
    await expect(rail.getByText(asked)).toBeVisible();
    await rail
      .getByRole("link", { name: "Open the session this came from" })
      .click();
    await expect(alice).toHaveURL(
      new RegExp(`/sessions/${created.session_id}`),
    );
  } finally {
    await context.close();
  }
});
