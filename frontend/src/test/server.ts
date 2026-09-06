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
    content: "새 합의",
    bundle_ids: ["bundle-1"],
    citations: [
      {
        bundle_id: "bundle-1",
        bundle_item_position: 0,
        claim_anchor: "새 합의",
      },
    ],
    required_approver_ids: [member.id],
    additional_approver_ids: [],
    created_by: member.id,
    created_at: session.created_at,
  },
};
export const publicBundle: Schema["PublicBundleResponse"] = {
  bundle_id: "bundle-1",
  title: "B 선택",
  items: [
    {
      source_ids: ["turn-1"],
      role: "assistant",
      content: "B로 결정",
      provenance: "edited",
    },
  ],
  attribution: {
    title: "B 선택",
    author_display_name: "Member",
    published_at: session.created_at,
  },
};

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
    forks: [] as Schema["SessionResponse"][],
    proposals: [] as Schema["ProposalResponse"][],
    branchVersion: 2,
    turns: [...turns],
    emptyDocuments: false,
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
    if (path.endsWith("/members/me"))
      return Response.json({
        workspace_id,
        user_id: state.user.id,
        role: "member",
        permissions: state.permissions,
      });
    if (path === "/api/v1/workspaces")
      return Response.json([
        { id: "w1", name: "Source" },
        { id: "w2", name: "Destination" },
      ]);
    if (path.endsWith("/documents"))
      return Response.json(state.emptyDocuments ? [] : [document]);
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
      const found = [...state.forks, ...state.sessions].find(
        (item) => item.workspace_id === workspace_id && item.id === "session-1",
      );
      return found && found.created_by === state.user.id
        ? Response.json(found)
        : Response.json(
            { error: { code: "not_found", message: "Session not found" } },
            { status: 404 },
          );
    }
    if (path.endsWith("/sessions/session-1/branches"))
      return Response.json([
        { ...branch, workspace_id, version: state.branchVersion },
      ]);
    if (path.endsWith("/branches/branch-1/turns"))
      return Response.json(
        state.turns.map((turn) => ({ ...turn, workspace_id })),
      );
    if (path.endsWith("/curation-ops")) {
      state.branchVersion++;
      return Response.json({
        resource_id: "op-1",
        branch_version: state.branchVersion,
      });
    }
    if (path.endsWith("/bundle-preview"))
      return Response.json(publicBundle.items);
    if (path.endsWith("/bundles")) {
      state.branchVersion++;
      return Response.json({
        resource_id: "bundle-1",
        branch_version: state.branchVersion,
      });
    }
    if (path.endsWith("/bundles/bundle-1/tosses"))
      return Response.json({ id: "toss-1", token: "share-me" });
    if (path === "/api/v1/tosses/share-me") return Response.json(publicBundle);
    if (path.endsWith("/tosses/share-me/fork")) {
      state.forks.push({ ...session, workspace_id, document_id: null });
      return Response.json({ session_id: session.id, branch_id: branch.id });
    }
    if (path.endsWith("/documents/doc-1/proposals")) {
      if (request.method === "POST") {
        const body = (await request.json()) as Schema["CreateProposalRequest"];
        const source = [...state.forks, ...state.sessions].find(
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
            content: proposal.current_version.content,
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
