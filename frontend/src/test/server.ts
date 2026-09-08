import type { components } from "../generated/api";
import { AuthSession } from "../auth";

type Schema = components["schemas"];
export const member: Schema["UserResponse"] = {
  id: "user-1",
  email: "member@example.com",
  display_name: "Member",
};
export const session: Schema["SessionResponse"] = {
  id: "session-1",
  workspace_id: "w1",
  document_id: "doc-1",
  created_by: member.id,
  created_at: "2026-09-06T00:00:00Z",
  status: "open",
};
export const branch: Schema["BranchResponse"] = {
  id: "branch-1",
  workspace_id: "w1",
  session_id: session.id,
  created_by: member.id,
  created_at: session.created_at,
  version: 2,
};
export const turns: Schema["TurnResponse"][] = [
  {
    id: "turn-1",
    workspace_id: "w1",
    branch_id: branch.id,
    ordinal: 1,
    role: "assistant",
    content: "B로 결정",
    created_at: session.created_at,
  },
];
export const proposal: Schema["ProposalResponse"] = {
  id: "proposal-1",
  workspace_id: "w1",
  document_id: "doc-1",
  source_session_id: session.id,
  created_by: member.id,
  created_at: session.created_at,
  version: 1,
  status: "open",
  approvals: [],
  current_version: {
    proposal_id: "proposal-1",
    version: 1,
    base_revision_id: "rev-1",
    edits: [{ find: "초기 합의", replace: "새 합의" }],
    bundle_ids: ["bundle-1"],
    citations: [
      {
        bundle_id: "bundle-1",
        bundle_item_position: 0,
        claim_anchor: "새 합의",
      },
    ],
    required_approver_ids: [member.id, "user-2"],
    additional_approver_ids: [],
    created_by: member.id,
    created_at: session.created_at,
  },
};
/** What curation keeps: the bundle preview reads these. */
export const bundleItems: Schema["BundleItemResponse"][] = [
  {
    source_ids: ["turn-1"],
    role: "assistant",
    content: "B로 결정",
    provenance: "edited",
  },
];

export function createServer() {
  const requests: Request[] = [];
  const state = {
    user: member,
    permissions: [
      "document.read",
      "document.publish",
      "session.create",
      "session.read",
      "session.participate",
    ] as Schema["Permission"][],
    sessions: [] as Schema["SessionResponse"][],
    proposals: [] as Schema["ProposalResponse"][],
    invitations: [] as {
      id: string;
      workspace_id: string;
      invitee_email: string;
      role: string;
      created_at: string;
      expires_at: string;
      code?: string;
    }[],
    sessionMembers: [
      { workspace_id: "w1", session_id: "session-1", user_id: member.id, role: "owner" },
    ] as { workspace_id: string; session_id: string; user_id: string; role: string }[],
    members: [
      { user_id: member.id, role: "owner", display_name: member.display_name },
      { user_id: "user-2", role: "viewer", display_name: "Reviewer" },
    ] as { user_id: string; role: string; display_name: string }[],
    branchVersion: 2,
    turns: [...turns],
    /* Curation is append-only: a dropped turn is still recoverable. */
    dropped: [] as Schema["TurnResponse"][],
    extraBranches: [] as Schema["BranchResponse"][],
    createdDocument: null as Schema["DocumentSummaryResponse"] | null,
    emptyDocuments: false,
    workspaces: [
      { id: "w1", name: "Source" },
      { id: "w2", name: "Destination" },
    ] as Schema["WorkspaceResponse"][],
  };
  const network = async (input: RequestInfo | URL, init?: RequestInit) => {
    const request = input instanceof Request ? input : new Request(input, init);
    requests.push(request.clone());
    const path = new URL(request.url).pathname;
    const workspace_id = path.split("/")[4];
    const document: Schema["DocumentSummaryResponse"] = {
      id: "doc-1",
      workspace_id,
      title: workspace_id === "w2" ? "Destination document" : "요청 제한 토큰",
      current_revision_id: "rev-1",
      version: 1,
    };
    if (path.endsWith("/auth/refresh") || path.endsWith("/auth/google"))
      return Response.json({
        access_token: "test-access",
        token_type: "bearer",
        user: state.user,
      });
    if (path === "/api/v1/me") return Response.json(state.user);
    if (path.endsWith("/auth/logout-all") && request.method === "POST")
      return Response.json({ ok: true });
    if (path.endsWith("/members/me"))
      return Response.json({
        workspace_id,
        user_id: state.user.id,
        role: state.permissions.includes("workspace.manage") ? "owner" : "member",
        permissions: state.permissions,
      });
    // `/sessions/{id}/members` also ends with "/members": keep the workspace
    // roster from answering for it.
    if (
      path.endsWith("/members") &&
      !path.includes("/sessions/") &&
      request.method === "GET"
    )
      return Response.json(
        state.members.map((item) => ({ workspace_id, ...item })),
      );
    if (path.endsWith("/invitations")) {
      if (request.method === "POST") {
        const body = (await request.json()) as { email: string; role: string };
        const invitation = {
          id: "invitation-1",
          workspace_id,
          invitee_email: body.email.toLowerCase(),
          role: body.role,
          created_at: session.created_at,
          expires_at: "2026-09-15T00:00:00Z",
          // Nothing delivers it here, so the code comes back to the inviter.
          code: "ABCD234XYZ",
        };
        state.invitations = [...state.invitations, invitation];
        return Response.json(invitation, { status: 201 });
      }
      return Response.json(state.invitations);
    }
    if (path.includes("/invitations/") && request.method === "DELETE") {
      const id = path.split("/").pop();
      state.invitations = state.invitations.filter((item) => item.id !== id);
      return new Response(null, { status: 204 });
    }
    if (
      path.endsWith("/members") &&
      !path.includes("/sessions/") &&
      request.method === "POST"
    ) {
      const body = (await request.json()) as Schema["AddWorkspaceMemberRequest"];
      return Response.json(
        { workspace_id, user_id: body.user_id, role: body.role },
        { status: 201 },
      );
    }
    if (path === "/api/v1/workspaces") {
      if (request.method === "POST") {
        const body = (await request.json()) as Schema["CreateWorkspaceRequest"];
        const created = { id: "w-new", name: body.name };
        state.workspaces = [...state.workspaces, created];
        return Response.json(created, { status: 201 });
      }
      return Response.json(state.workspaces);
    }
    if (path.endsWith("/documents")) {
      if (request.method === "POST") {
        const body = (await request.json()) as Schema["CreateDocumentRequest"];
        const created = {
          id: "doc-new",
          workspace_id,
          title: body.title,
          current_revision_id: "rev-new",
          version: 1,
        };
        state.emptyDocuments = false;
        state.createdDocument = created;
        return Response.json(
          {
            document: created,
            current_revision: {
              id: "rev-new",
              workspace_id,
              document_id: created.id,
              number: 1,
              content: body.content,
              proposal_id: null,
              created_by: member.id,
              created_at: session.created_at,
              citations: [],
            },
          } satisfies Schema["DocumentResponse"],
          { status: 201 },
        );
      }
      return Response.json(state.emptyDocuments ? [] : [document]);
    }
    if (path.endsWith("/documents/doc-new") && state.createdDocument)
      return Response.json({
        document: state.createdDocument,
        current_revision: {
          id: "rev-new",
          workspace_id,
          document_id: "doc-new",
          number: 1,
          content: "",
          proposal_id: null,
          created_by: member.id,
          created_at: session.created_at,
          citations: [],
        },
      } satisfies Schema["DocumentResponse"]);
    if (path.endsWith("/documents/doc-1"))
      return Response.json({
        document,
        current_revision: {
          id: "rev-1",
          workspace_id,
          document_id: document.id,
          number: 1,
          content: workspace_id === "w2" ? "목적지 합의" : "초기 합의",
          proposal_id: null,
          created_by: member.id,
          created_at: session.created_at,
          citations: [],
        },
      } satisfies Schema["DocumentResponse"]);
    if (path.endsWith("/documents/doc-1/sessions")) {
      if (request.method === "POST") {
        state.sessions = [{ ...session, workspace_id }];
        return Response.json(
          { session_id: session.id, branch_id: branch.id },
          { status: 201 },
        );
      }
      return Response.json(
        state.sessions.filter(
          (item) =>
            item.workspace_id === workspace_id &&
            item.document_id === "doc-1" &&
            item.created_by === state.user.id,
        ),
      );
    }
    if (path.endsWith("/sessions/session-1")) {
      const found = state.sessions.find(
        (item) => item.workspace_id === workspace_id && item.id === "session-1",
      );
      return found && found.created_by === state.user.id
        ? Response.json(found)
        : Response.json(
            { error: { code: "not_found", message: "Session not found" } },
            { status: 404 },
          );
    }
    if (path.endsWith("/sessions/session-1/branches")) {
      if (request.method === "POST") {
        const created = {
          ...branch,
          id: "branch-2",
          workspace_id,
          version: 1,
        };
        state.extraBranches = [...state.extraBranches, created];
        return Response.json(created, { status: 201 });
      }
      return Response.json([
        { ...branch, workspace_id, version: state.branchVersion },
        ...state.extraBranches,
      ]);
    }
    if (path.endsWith("/branches/branch-2/turns"))
      return Response.json([
        {
          id: "turn-other",
          workspace_id,
          branch_id: "branch-2",
          ordinal: 1,
          role: "user",
          content: "다른 전제",
          created_at: session.created_at,
        },
      ]);
    if (path.endsWith("/branches/branch-1/turns"))
      return Response.json(
        state.turns.map((turn) => ({ ...turn, workspace_id })),
      );
    if (path.endsWith("/curation-ops")) {
      const body = (await request.json()) as Schema["CurationRequest"];
      const op = body.operation;
      if (op.kind === "drop") {
        const gone = state.turns.find((turn) => turn.id === op.turn_id);
        if (gone) state.dropped = [...state.dropped, gone];
        state.turns = state.turns.filter((turn) => turn.id !== op.turn_id);
      } else if (op.kind === "edit") {
        state.turns = state.turns.map((turn) =>
          turn.id === op.turn_id ? { ...turn, content: op.content } : turn,
        );
      } else if (op.kind === "restore") {
        // The real projection puts the turn back where it was; the fixture
        // only needs it back in the list for the UI under test.
        const gone = state.dropped.find((turn) => turn.id === op.turn_id);
        if (gone) {
          state.dropped = state.dropped.filter((turn) => turn.id !== op.turn_id);
          state.turns = [...state.turns, gone].sort(
            (a, b) => a.ordinal - b.ordinal,
          );
        }
      } else {
        const keep = op.turn_ids[0];
        const drop = new Set(op.turn_ids.slice(1));
        state.turns = state.turns
          .filter((turn) => !drop.has(turn.id))
          .map((turn) =>
            turn.id === keep ? { ...turn, content: op.content } : turn,
          );
      }
      state.branchVersion++;
      return Response.json({
        resource_id: "op-1",
        branch_version: state.branchVersion,
      });
    }
    if (path.endsWith("/bundle-preview"))
      return Response.json(bundleItems);
    if (path.endsWith("/sessions/session-1/members")) {
      if (request.method === "POST") {
        const body = (await request.json()) as { user_id: string; role: string };
        const member = {
          workspace_id,
          session_id: session.id,
          user_id: body.user_id,
          role: body.role,
        };
        state.sessionMembers = [...state.sessionMembers, member];
        return Response.json(member, { status: 201 });
      }
      return Response.json(
        state.sessionMembers.map((item) => ({ ...item, workspace_id })),
      );
    }
    if (path.endsWith("/documents/doc-1/proposals")) {
      if (request.method === "POST") {
        const body = (await request.json()) as Schema["CreateProposalRequest"];
        const source = state.sessions.find(
          (item) =>
            item.workspace_id === workspace_id &&
            item.id === body.source_session_id,
        );
        if (!source || source.document_id !== "doc-1")
          return Response.json(
            {
              error: {
                code: "invalid_source_session",
                message: "Proposal requires a document-linked source session",
              },
            },
            { status: 422 },
          );
        state.proposals = [{ ...proposal, workspace_id }];
        return Response.json(state.proposals[0], { status: 201 });
      }
      return Response.json(state.proposals);
    }
    if (path.endsWith("/proposals/proposal-1/decisions")) {
      const body = (await request.json()) as Schema["DecideProposalRequest"];
      const current = state.proposals[0];
      state.proposals = [
        {
          ...current,
          status: body.decision === "approve" ? "approved" : "rejected",
          approvals: [
            ...current.approvals,
            {
              proposal_id: proposal.id,
              version: 1,
              approver_user_id: state.user.id,
              decision: body.decision,
              decided_at: session.created_at,
            },
          ],
        },
      ];
      return Response.json(state.proposals[0]);
    }
    if (path.endsWith("/proposals/proposal-1/merge")) {
      state.proposals = [{ ...proposal, status: "merged" }];
      return Response.json({
        proposal_id: proposal.id,
        status: "merged",
        version: 1,
        publication: {
          document: { ...document, current_revision_id: "rev-2", version: 2 },
          revision: {
            id: "rev-2",
            workspace_id,
            document_id: document.id,
            number: 2,
            content: proposal.current_version.edits[0].replace,
            proposal_id: proposal.id,
            created_by: member.id,
            created_at: session.created_at,
            citations: proposal.current_version.citations,
          },
        },
      } satisfies Schema["MergeProposalResponse"]);
    }
    if (path.endsWith("/proposals/proposal-1"))
      return Response.json(state.proposals[0]);
    throw new Error(`Unexpected request: ${request.method} ${path}`);
  };
  const auth = new AuthSession(network, "https://sot.test/api/v1");
  return { auth, network, requests, state };
}

export function eventStream(events: object[]) {
  return new Response(
    events.map((event) => `data: ${JSON.stringify(event)}\n\n`).join(""),
    { headers: { "Content-Type": "text/event-stream" } },
  );
}
