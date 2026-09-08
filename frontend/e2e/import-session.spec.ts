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

test("a conversation had elsewhere becomes a session of your own", async ({
  browser,
}) => {
  const context = await browser.newContext();
  try {
    const alice = await context.newPage();
    const auth = { Authorization: `Bearer ${(await login(alice)).access_token}` };
    const aw = await openWorkspace(alice, "Alice Workspace");

    const made = await (
      await context.request.post(`${api}/workspaces/${aw}/documents`, {
        headers: auth,
        data: { title: `Imported ${Date.now()}`, content: "# 정책\n\n초안." },
      })
    ).json();
    await alice.goto(`/w/${aw}/documents/${made.document.id}/sessions`);

    // What a person actually copies out of another tool: a title, then the
    // exchange, marked however that tool marks it.
    const transcript = [
      "토큰 회전 논의",
      "",
      "You said:",
      "회전 주기를 며칠로 할까?",
      "",
      "ChatGPT said:",
      "90일. 유출 대응 창을 한 분기로 묶는 게 낫다.",
      "",
      "You said:",
      "그럼 90일로 간다.",
      "",
    ].join("\n");
    const created = alice.waitForResponse(
      (r) =>
        r.request().method() === "POST" && r.url().endsWith("/imported-sessions"),
    );
    await alice.getByLabel("Import a conversation").setInputFiles({
      name: "rotation-chat.md",
      mimeType: "text/markdown",
      buffer: Buffer.from(transcript, "utf8"),
    });
    const session = await (await created).json();
    await alice.waitForURL(/\/sessions\//);

    // Turn by turn, in the roles the file said, so each one is citable.
    const branches = (await (
      await context.request.get(
        `${api}/workspaces/${aw}/sessions/${session.session_id}/branches`,
        { headers: auth },
      )
    ).json()) as { id: string }[];
    const turns = (await (
      await context.request.get(
        `${api}/workspaces/${aw}/branches/${branches[0].id}/turns`,
        { headers: auth },
      )
    ).json()) as Turn[];
    expect(turns.map((turn) => turn.role)).toEqual([
      "user",
      "assistant",
      "user",
    ]);
    // The file's own title belongs to whoever spoke first, not to a turn
    // nobody took.
    expect(turns[0].content).toBe("토큰 회전 논의\n\n회전 주기를 며칠로 할까?");
    expect(turns[1].content).toContain("90일");

    // And it says so: this exchange was not run here.
    await expect(
      alice.getByText("Imported from rotation-chat.md", { exact: false }),
    ).toBeVisible();
    await expect(
      alice.getByRole("article").filter({ hasText: "90일. 유출 대응 창을" }),
    ).toBeVisible();

    // The list names it by its file rather than by the minute it was made.
    await alice.goto(`/w/${aw}/documents/${made.document.id}/sessions`);
    await expect(alice.getByText("rotation-chat.md")).toBeVisible();
  } finally {
    await context.close();
  }
});
