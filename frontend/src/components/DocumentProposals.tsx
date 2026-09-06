import type { API } from "../api";
import type { CurrentMember } from "../types";
import { ProposalView } from "./ProposalView";

export function DocumentProposals({
  api,
  workspaceId,
  documentId,
  member,
}: {
  api: API;
  workspaceId: string;
  documentId: string;
  member?: CurrentMember;
}) {
  const proposals = api.useQuery(
    "get",
    "/api/v1/workspaces/{workspace_id}/documents/{document_id}/proposals",
    {
      params: { path: { workspace_id: workspaceId, document_id: documentId } },
    },
  );

  return (
    <section aria-label="Document proposals">
      <h2>Main 변경 제안</h2>
      {proposals.error && (
        <p role="alert">
          {proposals.error instanceof Error
            ? proposals.error.message
            : "Proposal을 불러오지 못했습니다."}
        </p>
      )}
      {proposals.isLoading && <p role="status">Proposal 동기화 중…</p>}
      {proposals.data?.length === 0 && (
        <p className="muted">아직 변경 제안이 없습니다.</p>
      )}
      <div className="proposal-list">
        {proposals.data?.map((proposal) => (
          <ProposalView
            key={proposal.id}
            api={api}
            workspaceId={workspaceId}
            proposalId={proposal.id}
            member={member}
          />
        ))}
      </div>
    </section>
  );
}
