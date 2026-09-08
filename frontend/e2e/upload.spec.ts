import { expect, test, type Page } from "@playwright/test";
import type { components } from "../src/generated/api";
import { openWorkspace } from "./workspace";

const api = "http://127.0.0.1:18001/api/v1";
type Turn = components["schemas"]["TurnResponse"];

async function login(page: Page) {
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
          button.onclick = () => options.callback({ credential: 'google-test-alice' });
          element.replaceChildren(button);
        }
      } } };`,
    }),
  );
  const response = page.waitForResponse((r) => r.url().endsWith("/auth/google"));
  await page.goto("/");
  await page.getByRole("button", { name: "Sign in with Google" }).click();
  return (await (await response).json()) as { access_token: string };
}

test("a markdown file starts a document and joins a conversation", async ({
  browser,
}) => {
  const context = await browser.newContext();
  try {
    const alice = await context.newPage();
    const auth = { Authorization: `Bearer ${(await login(alice)).access_token}` };
    const aw = await openWorkspace(alice, "Alice Workspace");

    // A document that already exists as a file starts as that file, named by
    // its own first heading rather than by the filename.
    const body = "# 요청 제한 정책\n\n## 만료\n90일마다 회전한다.";
    const created = alice.waitForResponse(
      (r) => r.request().method() === "POST" && r.url().endsWith("/documents"),
    );
    await alice
      .getByLabel("Upload a Markdown file")
      .setInputFiles({
        name: "rate-limits.md",
        mimeType: "text/markdown",
        buffer: Buffer.from(body, "utf8"),
      });
    const document = await (await created).json();
    expect(document.document.title).toBe("요청 제한 정책");
    expect(document.current_revision.content).toBe(body);
    expect(document.current_revision.number).toBe(1);
    await alice.waitForURL(/\/documents\//);
    await expect(
      alice.getByRole("heading", { name: "요청 제한 정책", level: 1 }).first(),
    ).toBeVisible();

    // And a file brought into a session is something said in it.
    const session = await (
      await context.request.post(
        `${api}/workspaces/${aw}/documents/${document.document.id}/sessions`,
        { headers: auth, data: {} },
      )
    ).json();
    await alice.goto(`/w/${aw}/sessions/${session.session_id}`);
    const attached = alice.waitForResponse(
      (r) => r.request().method() === "POST" && r.url().endsWith("/attachments"),
    );
    await alice.getByLabel("Attach a file").setInputFiles({
      name: "rotation.md",
      mimeType: "text/markdown",
      buffer: Buffer.from("## 회전\n키는 90일마다 바꾼다.", "utf8"),
    });
    expect((await attached).status()).toBe(201);

    const turns = (await (
      await context.request.get(
        `${api}/workspaces/${aw}/branches/${session.branch_id}/turns`,
        { headers: auth },
      )
    ).json()) as Turn[];
    // Named, then quoted verbatim, as a turn the agent will read as history.
    expect(turns).toHaveLength(1);
    expect(turns[0].role).toBe("user");
    expect(turns[0].content).toBe("rotation.md\n\n## 회전\n키는 90일마다 바꾼다.");
    await expect(
      alice.getByRole("article").filter({ hasText: "rotation.md" }),
    ).toBeVisible();
  } finally {
    await context.close();
  }
});
