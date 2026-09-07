import { expect, test, type BrowserContext, type Page } from "@playwright/test";
import type { components } from "../src/generated/api";

const api = "http://127.0.0.1:18001/api/v1";
type Login = components["schemas"]["AuthResponse"];
type Turn = components["schemas"]["TurnResponse"];
type Proposal = components["schemas"]["ProposalResponse"];

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
  await expect(page.getByRole("combobox", { name: "Workspace", exact: true })).toBeVisible();
  const cookie = (await page.context().cookies()).find((item) => item.name === "sot_refresh");
  expect(cookie).toMatchObject({ httpOnly: true, secure: true, sameSite: "Lax", path: "/api/v1/auth" });
  expect(await page.evaluate(() => [localStorage.length, sessionStorage.length])).toEqual([0, 0]);
  const refreshed = page.waitForResponse((item) => item.url().endsWith("/auth/refresh"));
  await page.reload();
  const refreshedResponse = await refreshed;
  expect(refreshedResponse.status()).toBe(200);
  const rotated = await refreshedResponse.json() as Login;
  expect(rotated.user).toEqual(body.user);
  await expect(page.getByRole("combobox", { name: "Workspace", exact: true })).toBeVisible();
  const rotatedCookie = (await page.context().cookies()).find((item) => item.name === "sot_refresh");
  expect(rotatedCookie?.value).not.toBe(cookie?.value);
  return rotated;
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
    const aliceWorkspace = alice.getByRole("combobox", { name: "Workspace", exact: true });
    const bobWorkspace = bob.getByRole("combobox", { name: "Workspace", exact: true });
    await aliceWorkspace.selectOption({ label: "Alice Workspace" });
    await bobWorkspace.selectOption({ label: "Bob Workspace" });
    const aw = await aliceWorkspace.inputValue(), bw = await bobWorkspace.inputValue();
    expect(aw).not.toBe(bw);
    expect((await get(aliceContext, `/workspaces/${bw}/documents`, aliceLogin)).status()).toBe(403);
    const documents = await (await get(aliceContext, `/workspaces/${aw}/documents`, aliceLogin)).json();
    const documentPath = `/workspaces/${aw}/documents/${documents[0].id}`;
    const original = await (await get(aliceContext, documentPath, aliceLogin)).json();
    const createdResponse = alice.waitForResponse((res) => res.request().method() === "POST" && res.url().endsWith("/sessions"));
    await alice.getByRole("button", { name: "새 세션" }).click();
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
    await expect(alice.getByRole("checkbox")).toHaveCount(2);
    for (const checkbox of await alice.getByRole("checkbox").all()) await checkbox.check();
    const summary = "Publish only this curated rationale";
    await alice.getByLabel("인용 요약").fill(summary);
    await alice.getByRole("button", { name: "선별 적용" }).click();
    await expect(alice.getByRole("status")).toContainText("선별을 적용했습니다");
    await alice.getByRole("button", { name: "Bundle 미리보기" }).click();
    await expect(alice.getByLabel("Bundle preview")).toContainText(summary);
    await expect(alice.getByLabel("Bundle preview")).not.toContainText(privatePrompt);
    const publishedResponse = alice.waitForResponse((res) => res.request().method() === "POST" && res.url().endsWith("/bundles"));
    await alice.getByRole("button", { name: "Bundle 발행" }).click();
    const bundle = await (await publishedResponse).json();
    const tossResponse = alice.waitForResponse((res) => res.request().method() === "POST" && res.url().endsWith("/tosses"));
    await alice.getByRole("button", { name: "Toss 만들기" }).click();
    const toss = await (await tossResponse).json();
    await expect(alice.getByRole("heading", { name: summary })).toBeVisible();
    const publicRead = await get(publicContext, `/tosses/${toss.token}`);
    expect(publicRead.status()).toBe(200);
    expect(publicRead.headers()["cache-control"]).toContain("no-store");
    const shared = await publicRead.json();
    expect(shared.items).toEqual([{ source_ids: stored.map((turn) => turn.id), role: "user", content: summary, provenance: "edited" }]);
    for (const hidden of [privatePrompt, created.session_id, aw]) expect(JSON.stringify(shared)).not.toContain(hidden);
    expect((await get(publicContext, `${branchPath}/turns`)).status()).toBe(401);
    expect((await get(bobContext, `${branchPath}/turns`, bobLogin)).status()).toBe(404);
    expect((await get(bobContext, `/workspaces/${bw}/branches/${created.branch_id}/turns`, bobLogin)).status()).toBe(404);
    expect(await (await get(bobContext, `${documentPath}/sessions`, bobLogin)).json()).toEqual([]);
    await bob.getByLabel("Toss token").fill(toss.token);
    await bob.getByRole("button", { name: "열기", exact: true }).click();
    await bob.getByLabel("Destination Workspace").selectOption({ label: "Bob Workspace" });
    const forkResponse = bob.waitForResponse((res) => res.request().method() === "POST" && res.url().endsWith("/fork"));
    await bob.getByRole("button", { name: "Fork", exact: true }).click();
    const fork = await (await forkResponse).json();
    await expect(bob.getByLabel("Agent message")).toBeVisible();
    await expect(bob.getByRole("button", { name: "Proposal 만들기" })).toHaveCount(0);
    const forkSession = await (await get(bobContext, `/workspaces/${bw}/sessions/${fork.session_id}`, bobLogin)).json();
    expect(forkSession.document_id).toBeNull();
    const forkTurns = await (await get(bobContext, `/workspaces/${bw}/branches/${fork.branch_id}/turns`, bobLogin)).json() as Turn[];
    expect(forkTurns.map((turn) => ({ role: turn.role, content: turn.content }))).toEqual([{ role: "user", content: summary }]);
    expect((await get(aliceContext, `/workspaces/${bw}/sessions/${fork.session_id}`, aliceLogin)).status()).toBe(403);
    // Return from Toss to the source Session, retaining the immutable Bundle selection.
    await alice.getByRole("button", { name: `세션 ${String(created.session_id).slice(0, 8)}`, exact: true }).click();
    const content = "Each user's work runs in a separate process.";
    await alice.getByLabel("제안 본문").fill(content);
    await alice.getByLabel("추가 승인자 ID (쉼표로 구분)").fill(bobLogin.user.id);
    const proposalResponse = alice.waitForResponse((res) => res.request().method() === "POST" && res.url().endsWith("/proposals"));
    await alice.getByRole("button", { name: "Proposal 만들기" }).click();
    const proposal = await (await proposalResponse).json();
    expect(proposal.source_session_id).toBe(created.session_id);
    expect(proposal.current_version.required_approver_ids.sort()).toEqual([aliceLogin.user.id, bobLogin.user.id].sort());
    expect(proposal.current_version.citations).toEqual([{ bundle_id: bundle.resource_id, bundle_item_position: 0, claim_anchor: content }]);
    await bobWorkspace.selectOption({ label: "Alice Workspace" });
    const bobProposal = bob.getByRole("article").filter({ hasText: content });
    await expect(bobProposal).toBeVisible();
    await bobProposal.getByRole("button", { name: "승인", exact: true }).click();
    const proposalPath = `/workspaces/${aw}/proposals/${proposal.id}`;
    await expect.poll(async () => (await (await get(bobContext, proposalPath, bobLogin)).json()).approvals.length).toBe(1);
    expect((await get(bobContext, `${branchPath}/turns`, bobLogin)).status()).toBe(404);
    await alice.getByRole("button", { name: "Alice Policy", exact: true }).click();
    const aliceProposal = alice.getByRole("article").filter({ hasText: content });
    await aliceProposal.getByRole("button", { name: "승인", exact: true }).click();
    await expect(aliceProposal.getByText("APPROVED", { exact: true })).toBeVisible();
    expect((await (await get(aliceContext, documentPath, aliceLogin)).json()).current_revision).toEqual(original.current_revision);
    await expect(bobProposal.getByRole("button", { name: "Merge" })).toHaveCount(0);
    await aliceProposal.getByRole("button", { name: "Merge", exact: true }).click();
    await expect(alice.getByText(`MAIN · REVISION ${original.current_revision.number + 1}`)).toBeVisible();
    await expect(alice.getByLabel("Main revision provenance")).toContainText(content);
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
    expect(proposals.filter((item) => item.current_version.content === "race winner proposal")).toHaveLength(1);
    expect(proposals.some((item) => item.current_version.content === "race loser proposal")).toBe(false);
    const raceTurns = await (await get(aliceContext, `/workspaces/${aw}/branches/${race.branch_id}/turns`, aliceLogin)).json() as Turn[];
    expect(raceTurns.map((turn) => turn.content)).toEqual(["race winner", "Winner committed"]);
  } finally {
    await Promise.allSettled([aliceContext.close(), bobContext.close(), publicContext.close()]);
  }
});
