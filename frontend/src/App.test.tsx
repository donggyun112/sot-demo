import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router";
import { afterEach, expect, it, vi } from "vitest";
import { App } from "./App";
import { AuthSession } from "./auth";
import { branch, createServer, member, proposal, session } from "./test/server";
import { PROPOSAL_CONTENT_LIMIT } from "./app/limits";

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
});

function renderApp(ui: Parameters<typeof render>[0]) {
  return render(<MemoryRouter>{ui}</MemoryRouter>);
}

/** The sidebar lists documents too, so pick the first matching link. */
async function openDocument(name: RegExp | string = /요청 제한 토큰/) {
  const links = await screen.findAllByRole("link", { name });
  await userEvent.click(links[0]);
}

function LocationProbe({ onChange }: { onChange: (value: string) => void }) {
  const location = useLocation();
  onChange(`${location.pathname}${location.search}`);
  return null;
}

it("lets a user continue without Google", async () => {
  const server = createServer();
  const requests: Request[] = [];
  const auth = new AuthSession(async (request) => {
    requests.push(request.clone());
    if (request.url.endsWith("/auth/refresh"))
      return Response.json({}, { status: 401 });
    if (request.url.endsWith("/auth/local"))
      return Response.json({
        access_token: "local-access",
        token_type: "bearer",
        user: member,
      });
    return server.network(request);
  }, "https://sot.test/api/v1");
  renderApp(<App auth={auth} apiBase="https://sot.test/api/v1" />);
  await userEvent.click(
    await screen.findByRole("button", { name: "Continue without Google" }),
  );
  expect(await screen.findByText("Member")).toBeVisible();
  expect(
    requests.some((request) => request.url.endsWith("/auth/local")),
  ).toBe(true);
});

it("introduces the workspace as an editorial record before sign in", async () => {
  const auth = new AuthSession(async (request) => {
    if (request.url.endsWith("/auth/refresh"))
      return Response.json({}, { status: 401 });
    return Response.json([]);
  }, "https://sot.test/api/v1");

  renderApp(<App auth={auth} apiBase="https://sot.test/api/v1" />);

  expect(
    await screen.findByRole("heading", {
      name: "Make decisions that can explain themselves.",
    }),
  ).toBeVisible();
  expect(
    screen.getByRole("heading", { name: "Enter the workspace" }),
  ).toBeVisible();
});

it("uses GIS credential login and exposes no actor switcher", async () => {
  let callback:
    | ((value: google.accounts.id.CredentialResponse) => void)
    | undefined;
  const requests: Request[] = [];
  const auth = new AuthSession(async (request) => {
    requests.push(request.clone());
    if (request.url.endsWith("/refresh"))
      return Response.json({}, { status: 401 });
    if (request.url.endsWith("/google"))
      return Response.json({
        access_token: "real-access",
        token_type: "bearer",
        user: member,
      });
    if (request.url.endsWith("/me")) return Response.json(member);
    return Response.json([]);
  }, "https://sot.test/api/v1");
  vi.stubGlobal("google", {
    accounts: {
      id: {
        initialize: (options: google.accounts.id.IdConfiguration) => {
          callback = options.callback;
        },
        renderButton: (element: HTMLElement) => {
          element.textContent = "Sign in with Google";
        },
      },
    },
  });
  renderApp(
    <App
      auth={auth}
      googleClientId="google-client-id"
      apiBase="https://sot.test/api/v1"
    />,
  );
  expect(await screen.findByText("Sign in with Google")).toBeVisible();
  await act(async () =>
    callback?.({ credential: "gis-credential", select_by: "btn" }),
  );
  expect(await screen.findByText("Member")).toBeVisible();
  const login = requests.find((request) => request.url.endsWith("/google"));
  expect(await login?.json()).toEqual({ credential: "gis-credential" });
  expect(screen.queryByLabelText("작업자")).not.toBeInTheDocument();
});

it("sends a user with no workspaces to create-workspace", async () => {
  const server = createServer();
  server.state.workspaces = [];
  const auth = new AuthSession(async (request) => {
    if (request.url.endsWith("/auth/refresh"))
      return Response.json({}, { status: 401 });
    if (request.url.endsWith("/auth/local"))
      return Response.json({
        access_token: "local-access",
        token_type: "bearer",
        user: member,
      });
    return server.network(request);
  }, "https://sot.test/api/v1");
  renderApp(<App auth={auth} apiBase="https://sot.test/api/v1" />);
  await userEvent.click(
    await screen.findByRole("button", { name: "Continue without Google" }),
  );
  expect(
    await screen.findByRole("heading", { name: "Create a workspace" }),
  ).toBeVisible();
});

it("opens the new workspace as soon as it is created", async () => {
  const server = createServer();
  server.state.workspaces = [];
  server.state.emptyDocuments = true;
  const auth = new AuthSession(async (request) => {
    if (request.url.endsWith("/auth/refresh"))
      return Response.json({}, { status: 401 });
    if (request.url.endsWith("/auth/local"))
      return Response.json({
        access_token: "local-access",
        token_type: "bearer",
        user: member,
      });
    return server.network(request);
  }, "https://sot.test/api/v1");
  renderApp(<App auth={auth} apiBase="https://sot.test/api/v1" />);
  await userEvent.click(
    await screen.findByRole("button", { name: "Continue without Google" }),
  );
  await userEvent.type(await screen.findByLabelText("Workspace name"), "Acme");
  await userEvent.click(screen.getByRole("button", { name: "Create workspace" }));
  expect(await screen.findByRole("heading", { name: "Documents" })).toBeVisible();
  expect(screen.getAllByText("Acme").length).toBeGreaterThan(0);
  expect(
    screen.queryByRole("heading", { name: "Create a workspace" }),
  ).not.toBeInTheDocument();
});

it("does not show New document when the workspace id is not in the list", async () => {
  const server = createServer();
  server.state.workspaces = [];
  const auth = new AuthSession(async (request) => {
    if (request.url.endsWith("/auth/refresh"))
      return Response.json({}, { status: 401 });
    if (request.url.endsWith("/auth/local"))
      return Response.json({
        access_token: "local-access",
        token_type: "bearer",
        user: member,
      });
    return server.network(request);
  }, "https://sot.test/api/v1");
  render(
    <MemoryRouter initialEntries={["/w/ghost"]}>
      <App auth={auth} apiBase="https://sot.test/api/v1" />
    </MemoryRouter>,
  );
  await userEvent.click(
    await screen.findByRole("button", { name: "Continue without Google" }),
  );
  expect(
    await screen.findByRole("heading", { name: "Create a workspace" }),
  ).toBeVisible();
  expect(
    screen.queryByRole("button", { name: "New document" }),
  ).not.toBeInTheDocument();
});

it("opens the document list after login when workspaces exist", async () => {
  const server = createServer();
  const auth = new AuthSession(async (request) => {
    if (request.url.endsWith("/auth/refresh"))
      return Response.json({}, { status: 401 });
    if (request.url.endsWith("/auth/local"))
      return Response.json({
        access_token: "local-access",
        token_type: "bearer",
        user: member,
      });
    return server.network(request);
  }, "https://sot.test/api/v1");
  renderApp(<App auth={auth} apiBase="https://sot.test/api/v1" />);
  await userEvent.click(
    await screen.findByRole("button", { name: "Continue without Google" }),
  );
  expect((await screen.findAllByText("요청 제한 토큰")).length).toBeGreaterThan(0);
});

it("drops the workspace menu and opens that workspace list", async () => {
  await signIn();
  await userEvent.click(screen.getByRole("button", { name: "Workspaces" }));
  await userEvent.click(screen.getByRole("menuitem", { name: "Destination" }));
  expect((await screen.findAllByText("Destination document")).length).toBeGreaterThan(0);
  expect(screen.queryAllByText("요청 제한 토큰")).toHaveLength(0);
});

it("leaves a document and opens the other workspace list", async () => {
  await signIn();
  await openDocument();
  expect(await screen.findByText("초기 합의")).toBeVisible();
  await userEvent.click(screen.getByRole("button", { name: "Workspaces" }));
  await userEvent.click(screen.getByRole("menuitem", { name: "Destination" }));
  expect((await screen.findAllByText("Destination document")).length).toBeGreaterThan(0);
  expect(screen.queryByText("초기 합의")).not.toBeInTheDocument();
});

async function signIn(server = createServer()) {
  const auth = new AuthSession(async (request) => {
    if (request.url.endsWith("/auth/refresh"))
      return Response.json({}, { status: 401 });
    if (request.url.endsWith("/auth/local"))
      return Response.json({
        access_token: "local-access",
        token_type: "bearer",
        user: member,
      });
    return server.network(request);
  }, "https://sot.test/api/v1");
  renderApp(<App auth={auth} apiBase="https://sot.test/api/v1" />);
  await userEvent.click(
    await screen.findByRole("button", { name: "Continue without Google" }),
  );
  await screen.findByRole("link", { name: "Member" });
  return server;
}

it("opens the signed-in profile from the header name", async () => {
  await signIn();
  await userEvent.click(await screen.findByRole("link", { name: "Member" }));
  expect(await screen.findByRole("heading", { name: "Profile" })).toBeVisible();
  expect(screen.getByText("member@example.com")).toBeVisible();
  expect(screen.getByRole("heading", { name: "Workspace role" })).toBeVisible();
  // Permission identifiers are internal; the role is what a person reads.
  expect(screen.queryByText("session.create")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Sign out everywhere" })).toBeVisible();
});

it("hides workspace members from a member without workspace.manage", async () => {
  await signIn();
  expect(screen.queryByRole("link", { name: "Members" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "New document" })).not.toBeInTheDocument();
});

it("invites a member by email instead of asking for their id", async () => {
  const server = createServer();
  server.state.permissions = [
    "workspace.manage",
    "document.create",
    "document.read",
    "document.publish",
    "session.create",
    "session.read",
    "session.participate",
  ];
  await signIn(server);
  await userEvent.click(await screen.findByRole("link", { name: "Members" }));
  expect(await screen.findByRole("heading", { name: "Members" })).toBeVisible();
  await userEvent.type(screen.getByLabelText("Email"), "Teammate@Example.com");
  await userEvent.click(screen.getByRole("button", { name: "Send invitation" }));
  // Nothing delivers it in this install, so the inviter is handed the code.
  expect(await screen.findByText("Pass this code to them")).toBeVisible();
  expect(
    screen.getByRole("button", { name: "Copy invitation code" }),
  ).toBeVisible();

  // An invitation is not membership: it waits, and can be taken back.
  expect(await screen.findByText("teammate@example.com")).toBeVisible();
  expect(
    screen.getByRole("heading", { name: "Waiting to be accepted" }),
  ).toBeVisible();
  await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
  await waitFor(() => expect(server.state.invitations).toEqual([]));
});

it("hides new-session when the actor cannot session.create", async () => {
  const server = createServer();
  server.state.permissions = ["document.read", "session.read"];
  await signIn(server);
  await openDocument();
  await userEvent.click(await screen.findByRole("link", { name: "Sessions" }));
  expect(await screen.findByRole("heading", { name: "Sessions" })).toBeVisible();
  expect(screen.queryByRole("button", { name: "New session" })).not.toBeInTheDocument();
});

it("lets an owner create an empty document from the list", async () => {
  const server = createServer();
  server.state.emptyDocuments = true;
  server.state.permissions = [
    "workspace.manage",
    "document.create",
    "document.read",
    "document.publish",
    "session.create",
    "session.read",
    "session.participate",
  ];
  await signIn(server);
  expect(await screen.findByRole("heading", { name: "No documents" })).toBeVisible();
  await userEvent.click(await screen.findByRole("button", { name: "New document" }));
  expect(
    await screen.findByText(/No evidence is linked/),
  ).toBeVisible();
});

it("shapes what a teammate gets at the moment of handing it over", async () => {
  const server = createServer();
  await signIn(server);
  await openDocument();
  await userEvent.click(await screen.findByRole("link", { name: "Sessions" }));
  await userEvent.click(await screen.findByRole("button", { name: "New session" }));

  // Curation is not a permanent instrument in the rail: it is the last look
  // before someone else reads the conversation.
  expect(screen.queryByRole("button", { name: "Drop" })).not.toBeInTheDocument();
  const recipients = await screen.findByRole("region", { name: "Send it to" });
  await userEvent.click(
    within(recipients).getByRole("button", { name: "Send session" }),
  );

  expect(
    await screen.findByRole("heading", { name: "Before sending to Reviewer" }),
  ).toBeVisible();
  await userEvent.click(
    within(screen.getByRole("dialog")).getByRole("button", { name: "Drop" }),
  );
  expect(screen.queryByRole("button", { name: "Drop" })).not.toBeInTheDocument();

  await userEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Send" }));
  await waitFor(() =>
    expect(
      server.state.sessionMembers.some((item) => item.user_id === "user-2"),
    ).toBe(true),
  );
});

async function openProposal() {
  await openDocument();
  await userEvent.click(
    (await screen.findAllByRole("link", { name: /새 합의/ }))[0],
  );
  expect(await screen.findByRole("heading", { name: "Proposal" })).toBeVisible();
}

it("reviews the edits an agent proposed and records an approval", async () => {
  const server = createServer();
  // The agent opens proposals through sot_update; a person only decides.
  server.state.proposals = [proposal];
  await signIn(server);
  await openProposal();
  await userEvent.click(await screen.findByRole("button", { name: "Approve" }));
  expect(await screen.findByText("approve")).toBeVisible();
  // The diff is the edit itself, not two whole documents compared.
  expect(document.querySelector("[data-kind='del']")?.textContent).toBe(
    "-초기 합의",
  );
  expect(document.querySelector("[data-kind='add']")?.textContent).toBe(
    "+새 합의",
  );
});

it("shows no raw session or user id in the session list", async () => {
  await signIn();
  await openDocument();
  await userEvent.click(await screen.findByRole("link", { name: "Sessions" }));
  await userEvent.click(await screen.findByRole("button", { name: "New session" }));
  await userEvent.click(await screen.findByRole("link", { name: "Sessions" }));
  expect(await screen.findByRole("heading", { name: "Sessions" })).toBeVisible();
  expect(screen.getByText("You")).toBeVisible();
  expect(screen.queryByText("session-1")).not.toBeInTheDocument();
  expect(screen.queryByText("user-1")).not.toBeInTheDocument();
});

it("says the session list is empty instead of the standing blurb", async () => {
  await signIn();
  await openDocument();
  await userEvent.click(await screen.findByRole("link", { name: "Sessions" }));
  expect(
    await screen.findByText("No sessions on this document yet."),
  ).toBeVisible();
});

it("titles a session from its first user turn, not its id", async () => {
  const server = createServer();
  server.state.turns = [
    {
      id: "turn-0",
      workspace_id: "w1",
      branch_id: "branch-1",
      ordinal: 0,
      role: "user",
      content: "인증 흐름 정리\n두 번째 줄",
      created_at: "2026-09-06T00:00:00Z",
      created_by: member.id,
    },
  ];
  await signIn(server);
  await openDocument();
  await userEvent.click(await screen.findByRole("link", { name: "Sessions" }));
  await userEvent.click(await screen.findByRole("button", { name: "New session" }));
  expect((await screen.findAllByText("인증 흐름 정리")).length).toBeGreaterThan(0);
  expect(screen.queryByText("session-1")).not.toBeInTheDocument();
});

it("switches branches from the session side panel", async () => {
  const server = createServer();
  server.state.extraBranches = [
    {
      id: "branch-2",
      workspace_id: "w1",
      session_id: "session-1",
      created_by: member.id,
      created_at: "2026-09-06T00:00:00Z",
      version: 1,
    },
  ];
  await signIn(server);
  await openDocument();
  await userEvent.click(await screen.findByRole("link", { name: "Sessions" }));
  await userEvent.click(await screen.findByRole("button", { name: "New session" }));
  await userEvent.selectOptions(
    await screen.findByRole("combobox", { name: "Branch" }),
    "branch-2",
  );
  expect((await screen.findAllByText("다른 전제")).length).toBeGreaterThan(0);
});

it("names a required approver from the workspace roster instead of their id", async () => {
  const server = createServer();
  server.state.proposals = [proposal];
  await signIn(server);
  await openProposal();
  expect(screen.getByText("Reviewer")).toBeVisible();
  expect(screen.queryByText("user-2")).not.toBeInTheDocument();
  expect(screen.queryByText("Another member")).not.toBeInTheDocument();
});

it("lists the workspace roster on the members screen", async () => {
  const server = createServer();
  server.state.permissions = ["workspace.manage", "document.read", "session.read"];
  await signIn(server);
  await userEvent.click(await screen.findByRole("link", { name: "Members" }));
  expect(await screen.findByRole("heading", { name: "Members" })).toBeVisible();
  expect(screen.getByText("Reviewer")).toBeVisible();
  // "Viewer" is both a roster role and an option in the invite picker.
  expect((await screen.findAllByText("Viewer")).length).toBeGreaterThan(0);
  expect(screen.queryByText("user-2")).not.toBeInTheDocument();
});

it("shows the whole path to the document with reasons, not hidden actions", async () => {
  await signIn();
  await openDocument();
  await userEvent.click(await screen.findByRole("link", { name: "Sessions" }));
  await userEvent.click(await screen.findByRole("button", { name: "New session" }));

  // Document updates are the agent's to write, so the path says so here.
  expect(
    await screen.findByText(
      "The agent writes document updates. Ask for one in the session.",
    ),
  ).toBeVisible();
  // Handing the session over is the one thing a person does here. Publishing
  // evidence is not on the screen at all: a proposal freezes the conversation
  // it was written from.
  expect(
    await screen.findByRole("heading", { name: "Who holds this session" }),
  ).toBeVisible();
  expect(screen.queryByRole("button", { name: "Publish bundle" })).toBeNull();
});

it("says a viewer may not act instead of hiding the actions", async () => {
  const server = createServer();
  server.state.permissions = ["document.read", "session.read", "session.create"];
  await signIn(server);
  await openDocument();
  await userEvent.click(await screen.findByRole("link", { name: "Sessions" }));
  await userEvent.click(await screen.findByRole("button", { name: "New session" }));
  expect(
    (await screen.findAllByText("You have read-only access to this workspace."))
      .length,
  ).toBeGreaterThan(0);
});

it("navigates from the sidebar and counts what is waiting on me", async () => {
  const server = createServer();
  server.state.proposals = [proposal];
  await signIn(server);
  // The shell owns navigation: workspace, inbox and every document.
  expect(screen.getByRole("navigation", { name: "Workspace navigation" }))
    .toBeVisible();
  expect(screen.getByRole("button", { name: "Workspaces" })).toBeVisible();

  await openDocument();

  // The open proposal waits on me, so the sidebar says so and Inbox lists it.
  const inbox = await screen.findByRole("link", { name: /Inbox/ });
  await waitFor(() => expect(inbox).toHaveTextContent("1"));
  await userEvent.click(inbox);
  expect(await screen.findByText("Waiting on you")).toBeVisible();
  // Listed in the inbox and nested under its document in the sidebar.
  expect(screen.getAllByText("새 합의").length).toBeGreaterThan(1);
});

it("lists no outline entries for a document without headings", async () => {
  await signIn();
  await openDocument();
  expect(await screen.findByRole("heading", { name: "요청 제한 토큰" })).toBeVisible();
  // The outline lives in the shell now; a heading-less document adds nothing,
  // rather than a blank row.
  const nav = screen.getByRole("navigation", { name: "Workspace navigation" });
  expect(
    within(nav)
      .queryAllByRole("button")
      .filter((button) => button.textContent?.trim() === ""),
  ).toHaveLength(0);
});

it("sends a session to a workspace member instead of minting a link", async () => {
  const server = createServer();
  await signIn(server);
  await openDocument();
  await userEvent.click(await screen.findByRole("link", { name: "Sessions" }));
  await userEvent.click(await screen.findByRole("button", { name: "New session" }));

  // Whoever already holds it is listed; the others are the ones you can send
  // it to, each with the one action that applies. Never yourself.
  expect(await screen.findByRole("heading", { name: "Who holds this session" }))
    .toBeVisible();
  const recipients = await screen.findByRole("region", { name: "Send it to" });
  expect(within(recipients).getByText("Reviewer")).toBeVisible();
  expect(within(recipients).queryByText("Member")).not.toBeInTheDocument();

  await userEvent.click(within(recipients).getByRole("button", { name: "Send session" }));
  // Sending opens the last look rather than firing straight away.
  expect(
    await screen.findByRole("heading", { name: "Before sending to Reviewer" }),
  ).toBeVisible();
  await userEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Send" }));

  await waitFor(() =>
    expect(
      server.state.sessionMembers.some((item) => item.user_id === "user-2"),
    ).toBe(true),
  );
  // They hold it as an editor: the point is to continue it together.
  expect(await screen.findByText("Editor")).toBeVisible();
});


it("renames a document without writing a revision", async () => {
  // A name is picked before anyone knows what the document will say, so it
  // has to stay changeable — and changing it is not a change to the text.
  const server = createServer();
  // Naming the canonical document is the same right as creating one.
  server.state.permissions = [...server.state.permissions, "document.create"];
  await signIn(server);
  await openDocument();
  await userEvent.click(await screen.findByRole("button", { name: "Rename" }));
  const field = await screen.findByLabelText("Document title");
  await userEvent.clear(field);
  await userEvent.type(field, "레이트리밋 정책");
  await userEvent.click(screen.getByRole("button", { name: "Save" }));

  expect(
    await screen.findByRole("heading", { name: "레이트리밋 정책", level: 1 }),
  ).toBeVisible();
  const patch = server.requests.find((item) => item.method === "PATCH");
  expect(patch).toBeDefined();
  expect(await patch!.json()).toEqual({ title: "레이트리밋 정책" });
  // The history is untouched: renaming is not a revision.
  expect(server.state.revisions).toHaveLength(2);
});

it("reads an earlier revision and says it is not the current text", async () => {
  const server = createServer();
  await signIn(server);
  await openDocument();
  await userEvent.click(
    await screen.findByRole("button", { name: "Evidence" }),
  );
  const history = await screen.findByRole("region", { name: "History" });
  await userEvent.click(
    within(history).getByRole("button", { name: /Revision 1/ }),
  );

  expect(await screen.findByText(/처음 쓴 합의/)).toBeVisible();
  expect(
    screen.getByText(/Reading revision 1\. This is not the current text\./),
  ).toBeVisible();
  await userEvent.click(screen.getByRole("button", { name: "Back to current" }));
  expect(await screen.findByText(/초기 합의/)).toBeVisible();
});

it("a viewer forks the conversation instead of asking for write access", async () => {
  const server = createServer();
  // Sent this session read-only: they can follow it and not answer in it.
  server.state.sessionMembers = [
    {
      workspace_id: "w1",
      session_id: "session-1",
      user_id: member.id,
      role: "viewer",
    },
  ];
  await signIn(server);
  await openDocument();
  await userEvent.click(await screen.findByRole("link", { name: "Sessions" }));
  await userEvent.click(await screen.findByRole("button", { name: "New session" }));

  const fork = await screen.findByRole("button", {
    name: "Continue in a session of your own",
  });
  await userEvent.click(fork);

  // They land in their own session, which says where it came from.
  expect(
    await screen.findByText("Forked from a session"),
  ).toBeVisible();
  expect(
    screen.getByRole("link", { name: "Open the session it came from" }),
  ).toBeVisible();
  const forked = server.requests.find((item) => item.url.endsWith("/forks"));
  expect(forked).toBeDefined();
  expect(await forked!.json()).toEqual({ branch_id: "branch-1" });
});

it("offers no fork in a session you can already write in", async () => {
  await signIn();
  await openDocument();
  await userEvent.click(await screen.findByRole("link", { name: "Sessions" }));
  await userEvent.click(await screen.findByRole("button", { name: "New session" }));
  expect(await screen.findByLabelText("Agent message")).toBeVisible();
  expect(
    screen.queryByRole("button", { name: "Continue in a session of your own" }),
  ).toBeNull();
});


it("puts a teammate's name on a teammate's words", async () => {
  // The transcript used to sign every line with the reader's own name, so a
  // session someone handed you read as if you had written all of it.
  await signIn();
  await openDocument();
  await userEvent.click(await screen.findByRole("link", { name: "Sessions" }));
  await userEvent.click(await screen.findByRole("button", { name: "New session" }));

  const turnFor = async (content: string) => {
    const matches = await screen.findAllByText(content);
    const article = matches
      .map((node) => node.closest("article"))
      .find((node): node is HTMLElement => node !== null);
    expect(article).toBeDefined();
    return article!;
  };

  expect(
    within(await turnFor("그럼 A는 왜 뺐죠?")).getByText("Reviewer"),
  ).toBeVisible();
  // And the agent is still the agent, not a person.
  expect(within(await turnFor("B로 결정")).getByText("SOT Agent")).toBeVisible();
});


it("shows the grounds for the section you are reading", async () => {
  // The anchor is a markdown heading and the outline strips the hashes, so a
  // verbatim comparison reported every section as unsupported.
  await signIn();
  await openDocument();
  await userEvent.click(await screen.findByRole("button", { name: "Evidence" }));
  const rail = await screen.findByRole("region", { name: "Evidence" });
  // The passage selector lives with the grounds it chooses, not in the
  // workspace sidebar where sections read as more documents.
  await userEvent.selectOptions(
    within(rail).getByLabelText("Passage"),
    within(rail).getByRole("option", { name: "감사·모니터링" }),
  );

  expect(
    within(rail).queryByText("No evidence is linked to this passage."),
  ).toBeNull();
  // The grounds are the conversation, not an ordinal: what was said, and the
  // way back into the session that said it.
  expect(
    await within(rail).findByText("남겨야 합니다. 유출 시 추적이 안 됩니다."),
  ).toBeVisible();
  expect(within(rail).getByText("감사 로그 남겨야 하나?")).toBeVisible();
  expect(
    within(rail).getByRole("link", { name: "Open the session this came from" }),
  ).toHaveAttribute("href", "/w/w1/sessions/session-1");
});

it("walks from a revision back to the conversation behind it", async () => {
  // A canonical document is only trustworthy if you can reach the argument
  // that produced it.
  const server = createServer();
  server.state.proposals = [proposal];
  await signIn(server);
  await openDocument();
  await userEvent.click(await screen.findByRole("button", { name: "Evidence" }));
  const history = await screen.findByRole("region", { name: "History" });

  const session = within(history).getByRole("link", {
    name: "Session it came from",
  });
  expect(session).toHaveAttribute("href", "/w/w1/sessions/session-1");
  expect(
    within(history).getByRole("link", { name: "Proposal" }),
  ).toHaveAttribute("href", "/w/w1/proposals/proposal-1");
});


it("opens the session from the passage the update landed on", async () => {
  // The question "where did this come from" is asked at the passage, so it is
  // answered there — in the document, not in a panel somewhere else.
  await signIn();
  await openDocument();

  const passage = (await screen.findByRole("heading", { name: "감사·모니터링" }))
    .closest("[data-cited]");
  expect(passage).not.toBeNull();
  const link = within(passage as HTMLElement).getByRole("link", {
    name: "The update that wrote this",
  });
  // Not just the session: the sot_update call inside it that wrote this.
  expect(link).toHaveAttribute(
    "href",
    "/w/w1/sessions/session-1?call=call-abc123",
  );

  // A passage no update wrote carries no such claim.
  const untouched = (await screen.findByRole("heading", { name: "문제 정의" }))
    .closest("[data-cited]");
  expect(untouched).toBeNull();
});


it("marks and opens the call that wrote the passage you came from", async () => {
  // Landing in the session is not the answer on its own — the conversation is
  // long. The reader arrives at the moment the update was written.
  const server = createServer();
  server.state.sessions = [session];
  await signIn(server);
  await openDocument();
  const passage = (await screen.findByRole("heading", { name: "감사·모니터링" }))
    .closest("[data-cited]");
  await userEvent.click(
    within(passage as HTMLElement).getByRole("link", {
      name: "The update that wrote this",
    }),
  );

  const call = await screen.findByText("sot_update");
  const fold = call.closest("details");
  expect(fold).not.toBeNull();
  expect(fold!.dataset.marked).toBe("true");
  expect(fold!.open).toBe(true);
});


it("keeps what a tool was called with and what it returned, after a reload", async () => {
  // A run streams all of this to whoever watched it. Dropping it from the
  // stored transcript made the same session read differently on reload — and
  // an update you cannot see the agent make is one you take on trust.
  const server = createServer();
  server.state.sessions = [session];
  await signIn(server);
  await openDocument();
  await userEvent.click(await screen.findByRole("link", { name: "Sessions" }));
  await userEvent.click(await screen.findByRole("button", { name: "New session" }));

  const fold = (await screen.findByText("sot_update")).closest("details");
  expect(fold).not.toBeNull();
  await userEvent.click(screen.getByText("sot_update"));

  // One record, not two: the call and its return read as one thing.
  expect(screen.getAllByText("sot_update")).toHaveLength(1);
  expect(within(fold!).getByText(/감사·모니터링/)).toBeVisible();
  expect(within(fold!).getByText(/proposal-1/)).toBeVisible();
});


it("starts a document from the file it already exists as", async () => {
  // Otherwise a design document that exists has to be dictated to the agent
  // a few hundred characters at a time.
  const server = createServer();
  server.state.permissions = [...server.state.permissions, "document.create"];
  await signIn(server);
  expect(await screen.findByRole("heading", { name: "Documents" })).toBeVisible();

  const file = new File(
    ["# 요청 제한 정책\n\n계정당 초당 10회로 한다."],
    "rate-limits.md",
    { type: "text/markdown" },
  );
  await userEvent.upload(
    screen.getByLabelText("Upload a Markdown file"),
    file,
  );

  const posted = server.requests.find(
    (item) => item.method === "POST" && item.url.endsWith("/documents"),
  );
  expect(posted).toBeDefined();
  // Named by its own first heading, and the body is the file verbatim.
  expect(await posted!.json()).toEqual({
    title: "요청 제한 정책",
    content: "# 요청 제한 정책\n\n계정당 초당 10회로 한다.",
  });
});

it("holds a picked file in the composer until the message is sent", async () => {
  // Attaching on pick published someone's file the moment they clicked it,
  // with no way back and nothing said about it.
  const server = createServer();
  server.state.sessions = [session];
  await signIn(server);
  await openDocument();
  await userEvent.click(await screen.findByRole("link", { name: "Sessions" }));
  await userEvent.click(await screen.findByRole("button", { name: "New session" }));

  await userEvent.upload(
    await screen.findByLabelText("Attach files"),
    new File(["## 만료\n90일마다 회전한다."], "rotation.md", {
      type: "text/markdown",
    }),
  );

  // Staged, not sent: the file is on screen and nothing has left the browser.
  expect(await screen.findByText("rotation.md")).toBeVisible();
  expect(
    await screen.findByRole("button", { name: "Remove rotation.md" }),
  ).toBeVisible();
  expect(
    server.requests.find((item) => item.url.endsWith("/attachments")),
  ).toBeUndefined();

  await userEvent.click(screen.getByRole("button", { name: "Send" }));

  const posted = server.requests.find((item) =>
    item.url.endsWith("/attachments"),
  );
  expect(posted).toBeDefined();
  expect(await posted!.json()).toEqual({
    expected_version: branch.version,
    files: [
      { filename: "rotation.md", content: "## 만료\n90일마다 회전한다." },
    ],
  });
});

it("takes a picked file back out of the composer", async () => {
  const server = createServer();
  server.state.sessions = [session];
  await signIn(server);
  await openDocument();
  await userEvent.click(await screen.findByRole("link", { name: "Sessions" }));
  await userEvent.click(await screen.findByRole("button", { name: "New session" }));

  await userEvent.upload(
    await screen.findByLabelText("Attach files"),
    new File(["본문"], "wrong.md", { type: "text/markdown" }),
  );
  await userEvent.click(
    await screen.findByRole("button", { name: "Remove wrong.md" }),
  );

  expect(screen.queryByText("wrong.md")).toBeNull();
  expect(
    server.requests.find((item) => item.url.endsWith("/attachments")),
  ).toBeUndefined();
});

it("shows a file in the transcript as a file, not as its contents", async () => {
  // A hundred lines of someone's YAML in the middle of a conversation is
  // not something anyone reads.
  const server = createServer();
  server.state.sessions = [session];
  server.state.turns = [
    {
      id: "turn-file",
      workspace_id: "w1",
      branch_id: branch.id,
      ordinal: 1,
      role: "attachment",
      content: "rotation.md\n\n## 회전\n키는 90일마다 바꾼다.\n끝.",
      created_at: session.created_at,
      created_by: member.id,
    },
  ];
  await signIn(server);
  await openDocument();
  await userEvent.click(await screen.findByRole("link", { name: "Sessions" }));
  await userEvent.click(await screen.findByRole("button", { name: "New session" }));

  expect(await screen.findByText("rotation.md")).toBeVisible();
  expect(await screen.findByText("3 lines")).toBeVisible();
  expect(screen.queryByText(/키는 90일마다 바꾼다/)).toBeNull();
});


it("names an uploaded file after the file when it has no top-level heading", async () => {
  // A file that opens with front matter, or whose first heading is a section,
  // is not called after that section. This project's own DESIGN.md begins
  // with YAML and its first heading is "## Overview".
  const server = createServer();
  server.state.permissions = [...server.state.permissions, "document.create"];
  await signIn(server);
  expect(await screen.findByRole("heading", { name: "Documents" })).toBeVisible();

  await userEvent.upload(
    screen.getByLabelText("Upload a Markdown file"),
    new File(
      ["---\nname: SOT\n---\n\n## Overview\n\n본문."],
      "DESIGN.md",
      { type: "text/markdown" },
    ),
  );

  const posted = server.requests.find(
    (item) => item.method === "POST" && item.url.endsWith("/documents"),
  );
  const body = (await posted!.json()) as { title: string; content: string };
  expect(body.title).toBe("DESIGN");
  // The body is still the file, verbatim: front matter included.
  expect(body.content).toContain("name: SOT");
});
