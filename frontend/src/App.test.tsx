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
import { createServer, member, proposal } from "./test/server";
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
