import { expect, test, type BrowserContext, type Page } from "@playwright/test";
import type { components } from "../src/generated/api";

const api = "http://127.0.0.1:18001/api/v1";
type Login = components["schemas"]["AuthResponse"];
type Turn = components["schemas"]["TurnResponse"];
type Proposal = components["schemas"]["ProposalResponse"];

/** Credentials never reach web storage; two UI preferences are allowed there. */
async function credentialsInStorage(page: Page) {
  return page.evaluate(() => {
    const allowed = ["sot.locale", "sot.workspace"];
    return {
      session: Object.keys(sessionStorage),
      leaked: Object.entries({ ...localStorage })
        .filter(([key, value]) => !allowed.includes(key) || /token|bearer/i.test(value))
        .map(([key]) => key),
    };
  });
}

async function login(page: Page, actor: "alice" | "bob"): Promise<Login> {
  // Substitute only Google's external UI/credential boundary. SOT auth is real.
  await page.route("https://accounts.google.com/gsi/client", (route) => route.fulfill({
    contentType: "application/javascript", body: `
      let options;
      window.google = { accounts: { id: {
        initialize(value) { options = value; },
        renderButton(element) {
          const button = document.createElement('button');
          button.textContent = 'Sign in with Google';
          button.onclick = () => options.callback({ credential: 'google-test-${actor}' });
          element.replaceChildren(button);
        }
      } } };
    `,
  }));
  await page.goto("/");
  const response = page.waitForResponse((item) => item.url().endsWith("/auth/google"));
  await page.getByRole("button", { name: "Sign in with Google" }).click();
  const result = await response;
  expect(result.status()).toBe(200);
  expect(result.request().postDataJSON()).toEqual({ credential: `google-test-${actor}` });
  const body = await result.json() as Login;
  expect(body.access_token).not.toBe(`google-test-${actor}`);
  await expect(page.getByRole("link", { name: body.user.display_name, exact: true })).toBeVisible();
  const cookie = (await page.context().cookies()).find((item) => item.name === "sot_refresh");
  expect(cookie).toMatchObject({ httpOnly: true, secure: true, sameSite: "Lax", path: "/api/v1/auth" });
  expect(await credentialsInStorage(page)).toEqual({ session: [], leaked: [] });
  const refreshed = page.waitForResponse((item) => item.url().endsWith("/auth/refresh"));
  await page.reload();
  const refreshedResponse = await refreshed;
  expect(refreshedResponse.status()).toBe(200);
  const rotated = await refreshedResponse.json() as Login;
  expect(rotated.user).toEqual(body.user);
  await expect(page.getByRole("link", { name: body.user.display_name, exact: true })).toBeVisible();
  const rotatedCookie = (await page.context().cookies()).find((item) => item.name === "sot_refresh");
  expect(rotatedCookie?.value).not.toBe(cookie?.value);
  return rotated;
}

/** Open a workspace through the header menu and return the id the URL settles on. */
async function openWorkspace(page: Page, name: string) {
  await page.getByRole("button", { name: "Workspaces" }).click();
  await page.getByRole("menuitem", { name, exact: true }).click();
  await page.waitForURL(/\/w\/[^/]+$/);
  return new URL(page.url()).pathname.split("/")[2];
}

async function get(context: BrowserContext, path: string, auth?: Login) {
  return context.request.get(`${api}${path}`, {
    headers: auth ? { Authorization: `Bearer ${auth.access_token}` } : {},
  });
}

test("private draft, public detached fork and explicit consensus merge", async ({ browser }) => {
  const aliceContext = await browser.newContext();
  const bobContext = await browser.newContext();
  const publicContext = await browser.newContext();
  try {
    const alice = await aliceContext.newPage(), bob = await bobContext.newPage();
    const aliceLogin = await test.step("Alice Google login", () => login(alice, "alice"));
    const bobLogin = await test.step("Bob Google login", () => login(bob, "bob"));
    const aw = await openWorkspace(alice, "Alice Workspace");
    const bw = await openWorkspace(bob, "Bob Workspace");
    expect(aw).not.toBe(bw);
    expect((await get(aliceContext, `/workspaces/${bw}/documents`, aliceLogin)).status()).toBe(403);
    // The roster is what lets the UI show names instead of raw user ids.
    await alice.getByRole("link", { name: "Members" }).click();
    await expect(alice.getByRole("heading", { name: "Members" })).toBeVisible();
    await expect(alice.getByText("Owner", { exact: true })).toBeVisible();
    const roster = await (await get(aliceContext, `/workspaces/${aw}/members`, aliceLogin)).json();
    // Every member sees the roster; nobody outside the workspace does.
    expect(
      roster.map((item: { display_name: string }) => item.display_name).sort(),
    ).toEqual(["Alice", "Bob"]);
    expect((await get(bobContext, `/workspaces/${aw}/members`, bobLogin)).status()).toBe(200);
    expect((await get(publicContext, `/workspaces/${aw}/members`)).status()).toBe(401);
    // Return in-app: a reload would rotate the refresh cookie and invalidate
    // the access token this test still asserts on.
    await alice.getByRole("link", { name: "SOT", exact: true }).click();
    await expect(alice).toHaveURL(new RegExp(`/w/${aw}$`));

    const documents = await (await get(aliceContext, `/workspaces/${aw}/documents`, aliceLogin)).json();
    const documentPath = `/workspaces/${aw}/documents/${documents[0].id}`;
    const original = await (await get(aliceContext, documentPath, aliceLogin)).json();

    await alice.getByRole("link", { name: documents[0].title }).click();
    await alice.getByRole("link", { name: "Sessions", exact: true }).click();
    const createdResponse = alice.waitForResponse((res) => res.request().method() === "POST" && res.url().endsWith("/sessions"));
    await alice.getByRole("button", { name: "New session" }).click();
    const created = await (await createdResponse).json();
    const branchPath = `/workspaces/${aw}/branches/${created.branch_id}`;

    const privatePrompt = "Private draft: account detail must never appear in the public bundle";
    const posts: string[] = [];
    alice.on("request", (request) => { if (request.method() === "POST") posts.push(request.url()); });
    const streamed = alice.waitForResponse((res) => res.url().endsWith("/agent"));
    await alice.getByLabel("Agent message").fill(privatePrompt);
    await alice.getByLabel("Agent message").press("Enter");
    const stream = await streamed;
    expect(await stream.request().headerValue("authorization")).toBe(`Bearer ${aliceLogin.access_token}`);
    const events = (await stream.text()).split("\n").filter((line) => line.startsWith("data: ")).map((line) => JSON.parse(line.slice(6)));
    expect(events[0].type).toBe("RUN_STARTED");
    expect(events.at(-1).type).toBe("RUN_FINISHED");
    const stored = await (await get(aliceContext, `${branchPath}/turns`, aliceLogin)).json() as Turn[];
    expect(stored.map((turn) => [turn.role, turn.content])).toEqual([
      ["user", privatePrompt], ["assistant", "Public reasoning: isolate each user's work."],
    ]);
    expect(posts.every((url) => !url.endsWith("/turns"))).toBe(true);

    // Curate in the side panel: rewrite the assistant turn to the shareable
    // summary, then drop the private one. The chat transcript is not the bundle.
    const summary = "Publish only this curated rationale";
    const curation = alice.getByRole("complementary");
    await curation.getByRole("article").filter({ hasText: "Public reasoning" })
      .getByRole("button", { name: "Edit" }).click();
    await alice.getByLabel("Edit").fill(summary);
    await alice.getByRole("button", { name: "Save edit" }).click();
    const privateTurn = curation.getByRole("article").filter({ hasText: privatePrompt });
    await privateTurn.getByRole("button", { name: "Drop" }).click();
    // Curation ops are an append-only log, so the turn stays and is marked.
    await expect(privateTurn.getByText("Dropped")).toBeVisible();

    const preview = alice.getByRole("region", { name: "Bundle preview" });
    await expect(preview).toContainText(summary);
    await expect(preview).not.toContainText(privatePrompt);
    const publishedResponse = alice.waitForResponse((res) => res.request().method() === "POST" && res.url().endsWith("/bundles"));
    await alice.getByRole("button", { name: "Publish bundle" }).click();
    const bundle = await (await publishedResponse).json();
    // The published bundle lives in the URL, so a reload can still toss it.
    await expect(alice).toHaveURL(new RegExp(`bundle=${bundle.resource_id}`));
    const tossResponse = alice.waitForResponse((res) => res.request().method() === "POST" && res.url().endsWith("/tosses"));
    await alice.getByRole("button", { name: "Create toss link" }).click();
    const toss = await (await tossResponse).json();
    await alice.getByRole("link", { name: "Open toss link" }).click();
    await expect(alice.getByRole("heading", { name: "Shared evidence" })).toBeVisible();
    await expect(alice.getByText(summary)).toBeVisible();

    const publicRead = await get(publicContext, `/tosses/${toss.token}`);
    expect(publicRead.status()).toBe(200);
    expect(publicRead.headers()["cache-control"]).toContain("no-store");
    const shared = await publicRead.json();
    expect(shared.items).toEqual([{ source_ids: [stored[1].id], role: "assistant", content: summary, provenance: "edited" }]);
    for (const hidden of [privatePrompt, stored[0].id, created.session_id, aw]) expect(JSON.stringify(shared)).not.toContain(hidden);
    expect((await get(publicContext, `${branchPath}/turns`)).status()).toBe(401);
    expect((await get(bobContext, `${branchPath}/turns`, bobLogin)).status()).toBe(404);
    expect((await get(bobContext, `/workspaces/${bw}/branches/${created.branch_id}/turns`, bobLogin)).status()).toBe(404);
    expect(await (await get(bobContext, `${documentPath}/sessions`, bobLogin)).json()).toEqual([]);

    await bob.goto(`/s/${toss.token}`);
    await expect(bob.getByText(summary)).toBeVisible();
    await bob.getByRole("button", { name: "Fork into a workspace" }).click();
    await bob.getByLabel("Destination workspace").selectOption({ label: "Bob Workspace" });
    const forkResponse = bob.waitForResponse((res) => res.request().method() === "POST" && res.url().endsWith("/fork"));
    await bob.getByRole("button", { name: "Fork", exact: true }).click();
    const fork = await (await forkResponse).json();
    await expect(bob.getByLabel("Agent message")).toBeVisible();
    // A detached fork has no document, so nothing can be proposed from it.
    // The path stays on screen and says why rather than disappearing.
    await expect(
      bob.getByText("This session is not attached to a document."),
    ).toBeVisible();
    const forkSession = await (await get(bobContext, `/workspaces/${bw}/sessions/${fork.session_id}`, bobLogin)).json();
    expect(forkSession.document_id).toBeNull();
    const forkTurns = await (await get(bobContext, `/workspaces/${bw}/branches/${fork.branch_id}/turns`, bobLogin)).json() as Turn[];
    expect(forkTurns.map((turn) => ({ role: turn.role, content: turn.content }))).toEqual([{ role: "assistant", content: summary }]);
    expect((await get(aliceContext, `/workspaces/${bw}/sessions/${fork.session_id}`, aliceLogin)).status()).toBe(403);

    // Return from Toss to the source Session, retaining the immutable Bundle selection.
    await alice.goto(`/w/${aw}/sessions/${created.session_id}?bundle=${bundle.resource_id}`);
    // The agent writes document updates, so the proposal arrives as EDITS
    // through the same endpoint sot_update calls — never typed by a person.
    const content = "Each user's work runs in a separate process.";
    const created_proposal = await aliceContext.request.post(`${api}${documentPath}/proposals`, {
      headers: { Authorization: `Bearer ${aliceLogin.access_token}` },
      data: {
        source_session_id: created.session_id,
        edits: [{ find: "", replace: content }],
        bundle_ids: [bundle.resource_id],
        citations: [{ bundle_id: bundle.resource_id, bundle_item_position: 0, claim_anchor: content }],
        additional_approver_ids: [bobLogin.user.id],
      },
    });
    expect(created_proposal.status()).toBe(201);
    const proposal = await created_proposal.json();
    expect(proposal.source_session_id).toBe(created.session_id);
    expect(proposal.current_version.required_approver_ids.sort()).toEqual([aliceLogin.user.id, bobLogin.user.id].sort());
    expect(proposal.current_version.edits).toEqual([{ find: "", replace: content }]);
    expect(proposal.current_version.citations).toEqual([{ bundle_id: bundle.resource_id, bundle_item_position: 0, claim_anchor: content }]);
    await alice.goto(`/w/${aw}/proposals/${proposal.id}`);
    await expect(alice.getByRole("heading", { name: "Proposal" })).toBeVisible();

    // Raw approver ids never reach the canvas.
    await expect(alice.getByText(bobLogin.user.id)).toHaveCount(0);
    await expect(alice.getByText(created.session_id)).toHaveCount(0);

    const proposalPath = `/workspaces/${aw}/proposals/${proposal.id}`;
    await bob.goto(`/w/${aw}/proposals/${proposal.id}`);
    await expect(bob.getByText(content).first()).toBeVisible();
    await bob.getByRole("button", { name: "Approve" }).click();
    await expect.poll(async () => (await (await get(bobContext, proposalPath, bobLogin)).json()).approvals.length).toBe(1);
    expect((await get(bobContext, `${branchPath}/turns`, bobLogin)).status()).toBe(404);

    await alice.getByRole("button", { name: "Approve" }).click();
    await expect(alice.getByText("Approved", { exact: true })).toBeVisible();
    expect((await (await get(aliceContext, documentPath, aliceLogin)).json()).current_revision).toEqual(original.current_revision);
    await expect(bob.getByRole("button", { name: "Merge" })).toHaveCount(0);
    await alice.getByRole("button", { name: "Merge", exact: true }).click();
    await expect(alice.getByText("Merged", { exact: true })).toBeVisible();

    await alice.goto(`/w/${aw}/documents/${documents[0].id}`);
    await expect(alice.getByText(`Revision ${original.current_revision.number + 1}`)).toBeVisible();
    // The edit was an append, so the document it was written against is
    // still there: merging edits, not overwriting.
    await expect(alice.getByRole("article")).toContainText(content);
    await expect(alice.getByRole("article")).toContainText(original.current_revision.content);
    const current = (await (await get(aliceContext, documentPath, aliceLogin)).json()).current_revision;
    expect(current.proposal_id).toBe(proposal.id);
    expect(current.citations).toEqual(proposal.current_version.citations);
    expect((await (await get(aliceContext, proposalPath, aliceLogin)).json()).status).toBe("merged");

    // Native concurrent browser requests use real Agent tools and PostgreSQL.
    const raceSession = await aliceContext.request.post(`${api}${documentPath}/sessions`, { headers: { Authorization: `Bearer ${aliceLogin.access_token}` }, data: {} });
    const race = await raceSession.json();
    const results = await alice.evaluate(async ({ url, access }) => Promise.all(
      ["race winner", "race loser"].map(async (prompt) => {
        const response = await fetch(url, { method: "POST", headers: { Authorization: `Bearer ${access}`, "Content-Type": "application/json" }, body: JSON.stringify({ threadId: crypto.randomUUID(), runId: crypto.randomUUID(), state: {}, tools: [], context: [], forwardedProps: {}, messages: [{ id: crypto.randomUUID(), role: "user", content: prompt }] }) });
        return response.text();
      }),
    ), { url: `${api}/workspaces/${aw}/branches/${race.branch_id}/agent`, access: aliceLogin.access_token });
    expect(results[0]).toContain('"type":"RUN_FINISHED"');
    expect(results[1]).toContain('"code":"version_conflict"');
    expect(results[1]).not.toContain('"type":"RUN_FINISHED"');
    const proposals = await (await get(aliceContext, `${documentPath}/proposals`, aliceLogin)).json() as Proposal[];
    const proposed = (item: Proposal) => item.current_version.edits.map((edit) => edit.replace).join("");
    expect(proposals.filter((item) => proposed(item) === "race winner proposal")).toHaveLength(1);
    expect(proposals.some((item) => proposed(item) === "race loser proposal")).toBe(false);
    const raceTurns = await (await get(aliceContext, `/workspaces/${aw}/branches/${race.branch_id}/turns`, aliceLogin)).json() as Turn[];
    expect(raceTurns.map((turn) => turn.content)).toEqual(["race winner", "Winner committed"]);
  } finally {
    await Promise.allSettled([aliceContext.close(), bobContext.close(), publicContext.close()]);
  }
});
