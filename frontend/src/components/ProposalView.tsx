import type { Proposal } from "../types";

interface ProposalViewProps {
  proposal: Proposal;
  busy: boolean;
  onApprove: (proposalId: string) => void;
}

export function ProposalView({ proposal, busy, onApprove }: ProposalViewProps) {
  return (
    <article className="proposal-card">
      <div className="eyebrow">{proposal.status === "open" ? "OPEN PROPOSAL" : "PUBLISHED"}</div>
      <p>{proposal.content}</p>
      <small>제안자 {proposal.created_by}</small>
      {proposal.status === "open" && (
        <button
          className="button"
          disabled={busy}
          type="button"
          onClick={() => onApprove(proposal.id)}
        >
          승인
        </button>
      )}
    </article>
  );
}
