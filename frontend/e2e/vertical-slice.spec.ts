import { expect, test, type BrowserContext, type Page } from "@playwright/test";
import type { components } from "../src/generated/api";
import { openWorkspace } from "./workspace";

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
  // Secure follows the environment — this harness is http, and a Secure cookie
  // would be dropped here the way it was in the local install. The rest of the
  // cookie's protection does not depend on the transport.
  expect(cookie).toMatchObject({ httpOnly: true, secure: false, sameSite: "Lax", path: "/api/v1/auth" });
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
async function get(context: BrowserContext, path: string, auth?: Login) {
  return context.request.get(`${api}${path}`, {
    headers: auth ? { Authorization: `Bearer ${auth.access_token}` } : {},
  });
}

test("private draft, hand-off to a teammate and explicit consensus merge", async ({ browser }) => {
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

    await alice.getByRole("main").getByRole("link", { name: documents[0].title }).click();
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

    // Before it is handed over, the session is Alice's alone: Bob is in this
    // workspace but holds nothing in it.
    expect((await get(bobContext, `${branchPath}/turns`, bobLogin)).status()).toBe(404);
    expect((await get(publicContext, `${branchPath}/turns`)).status()).toBe(401);
    expect(await (await get(bobContext, `${documentPath}/sessions`, bobLogin)).json()).toEqual([]);
    expect((await get(bobContext, `/workspaces/${bw}/branches/${created.branch_id}/turns`, bobLogin)).status()).toBe(404);

    // Choosing what to hand over belongs to the moment of handing it over, so
    // it is the last look before someone else reads the conversation. Send is
    // a list of people, not a picker, and you are never on it.
    const summary = "Publish only this curated rationale";
    const recipients = alice.getByRole("region", { name: "Send it to" });
    await expect(recipients.getByText(aliceLogin.user.display_name)).toHaveCount(0);
    await recipients.getByRole("button", { name: "Send session" }).first().click();

    const review = alice.getByRole("dialog");
    await expect(review).toBeVisible();
    await review.getByRole("article").filter({ hasText: "Public reasoning" })
      .getByRole("button", { name: "Edit" }).click();
    await alice.getByLabel("Edit").fill(summary);
    await review.getByRole("button", { name: "Save edit" }).click();
    const privateTurn = review.getByRole("article").filter({ hasText: privatePrompt });
    await privateTurn.getByRole("button", { name: "Drop" }).click();
    // Curation ops are an append-only log, so the turn stays and is marked.
    await expect(privateTurn.getByText("Dropped")).toBeVisible();

    // Handing it over is adding Bob to it: he continues the same session
    // rather than receiving a copy of the turns.
    const sendResponse = alice.waitForResponse((res) => res.request().method() === "POST" && res.url().endsWith("/members"));
    await review.getByRole("button", { name: "Send", exact: true }).click();
    expect((await sendResponse).status()).toBe(201);
    await expect(alice.getByText("Editor")).toBeVisible();

    // The curated conversation is what a proposal will freeze as its grounds.
    // Nobody publishes it: there is no button for that, and never was a reason
    // to make a person do it.
    const preview = alice.getByRole("region", { name: "Grounds this session carries" });
    await expect(preview).toContainText(summary);
    await expect(preview).not.toContainText(privatePrompt);
    await expect(alice.getByRole("button", { name: "Publish bundle" })).toHaveCount(0);

    await bob.goto(`/w/${aw}/sessions/${created.session_id}`);
    await expect(bob.getByLabel("Agent message")).toBeVisible();
    // He reads the WHOLE conversation, curation included: this is the session,
    // not a public projection of it.
    const bobTurns = await (await get(bobContext, `${branchPath}/turns`, bobLogin)).json() as Turn[];
    expect(bobTurns.map((turn) => turn.content)).toEqual(stored.map((turn) => turn.content));
    const bobSessions = await (await get(bobContext, `${documentPath}/sessions`, bobLogin)).json();
    expect(bobSessions.map((item: { id: string }) => item.id)).toEqual([created.session_id]);
    // Sharing never crosses a workspace boundary, so Bob's own stays untouched.
    expect(await (await get(bobContext, `/workspaces/${bw}/documents`, bobLogin)).json()).not.toEqual([]);
    expect((await get(publicContext, `${branchPath}/turns`)).status()).toBe(401);

    await alice.goto(`/w/${aw}/sessions/${created.session_id}`);
    // The agent writes document updates, so the proposal arrives as EDITS
    // through the same endpoint sot_update calls — never typed by a person.
    // It names the branch it was written in; the grounds follow from that.
    const content = "Each user's work runs in a separate process.";
    const created_proposal = await aliceContext.request.post(`${api}${documentPath}/proposals`, {
      headers: { Authorization: `Bearer ${aliceLogin.access_token}` },
      data: {
        source_session_id: created.session_id,
        branch_id: created.branch_id,
        edits: [{ find: "", replace: content }],
        additional_approver_ids: [bobLogin.user.id],
      },
    });
    expect(created_proposal.status()).toBe(201);
    const proposal = await created_proposal.json();
    expect(proposal.source_session_id).toBe(created.session_id);
    expect(proposal.current_version.required_approver_ids.sort()).toEqual([aliceLogin.user.id, bobLogin.user.id].sort());
    expect(proposal.current_version.edits).toEqual([{ find: "", replace: content }]);
    // The grounds were frozen from the curated conversation, not supplied:
    // one citation per edit, anchored on the line it adds.
    expect(proposal.current_version.citations.map((c: { claim_anchor: string }) => c.claim_anchor)).toEqual([content]);
    expect(proposal.current_version.bundle_ids).toHaveLength(1);
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
    // Bob reviews the diff AND can still open the session it came from: it was
    // handed to him, so the evidence is not something he has to take on trust.
    expect((await get(bobContext, `${branchPath}/turns`, bobLogin)).status()).toBe(200);

    await alice.getByRole("button", { name: "Approve" }).click();
    await expect(alice.getByText("Approved", { exact: true })).toBeVisible();
    expect((await (await get(aliceContext, documentPath, aliceLogin)).json()).current_revision).toEqual(original.current_revision);
    await expect(bob.getByRole("button", { name: "Merge" })).toHaveCount(0);
    await alice.getByRole("button", { name: "Merge", exact: true }).click();
    await expect(alice.getByText("Merged", { exact: true })).toBeVisible();

    await alice.goto(`/w/${aw}/documents/${documents[0].id}`);
    // The history lists revision numbers too, so say which one is the document.
    await expect(alice.getByRole("article").getByText(`Revision ${original.current_revision.number + 1}`)).toBeVisible();
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
    // The whole record is kept: the call, what it was called with, and what
    // it returned. An update you cannot see the agent make is one you have to
    // take on trust.
    expect(raceTurns.map((turn) => turn.content)).toEqual([
      "race winner",
      "sot_update",
      "sot_update",
      "Winner committed",
    ]);
    expect(raceTurns.map((turn) => turn.tool_kind)).toEqual([
      null,
      "call",
      "return",
      null,
    ]);
    expect(raceTurns[1].tool_payload).toEqual({
      edits: [{ find: "", replace: "race winner proposal" }],
    });
    expect(raceTurns[2].tool_payload).toMatchObject({ status: "open" });
    // Read out of the envelope, not passed through it.
    expect(JSON.stringify(raceTurns)).not.toContain("sot.tool-turn");
  } finally {
    await Promise.allSettled([aliceContext.close(), bobContext.close(), publicContext.close()]);
  }
});
