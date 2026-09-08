import { useQueries } from "@tanstack/react-query";
import { useParams } from "react-router";
import { useSot } from "./sot";
import type { Proposal } from "../types";

/**
 * Everything unresolved across the workspace, split by whether it is my move.
 *
 * ponytail: one proposals request per document. The API has no workspace-wide
 * proposal list; add one if a workspace ever holds enough documents to notice.
 */
export function useOpenProposals() {
  const { workspaceId = "" } = useParams();
  const { api, user } = useSot();
  const documents = api.useQuery(
    "get",
    "/api/v1/workspaces/{workspace_id}/documents",
    { params: { path: { workspace_id: workspaceId } } },
    { enabled: Boolean(workspaceId) },
  );
  const list = documents.data ?? [];
  const results = useQueries({
    queries: list.map((doc) =>
      api.queryOptions(
        "get",
        "/api/v1/workspaces/{workspace_id}/documents/{document_id}/proposals",
        { params: { path: { workspace_id: workspaceId, document_id: doc.id } } },
      ),
    ),
  });

  const titleOf = new Map(list.map((doc) => [doc.id, doc.title]));
  const open: { proposal: Proposal; documentTitle: string }[] = [];
  results.forEach((result) => {
    for (const proposal of (result.data as Proposal[] | undefined) ?? []) {
      if (proposal.status !== "open" && proposal.status !== "approved") continue;
      open.push({
        proposal,
        documentTitle: titleOf.get(proposal.document_id) ?? "",
      });
    }
  });

  const decided = (proposal: Proposal) =>
    proposal.approvals.some(
      (approval) =>
        approval.approver_user_id === user?.id &&
        approval.version === proposal.version,
    );
  const required = (proposal: Proposal) =>
    Boolean(user) &&
    proposal.current_version.required_approver_ids.includes(user!.id);

  return {
    loading: documents.isLoading || results.some((result) => result.isLoading),
    all: open,
    waitingOnMe: open.filter(
      (item) =>
        item.proposal.status === "open" &&
        required(item.proposal) &&
        !decided(item.proposal),
    ),
    mine: open.filter((item) => item.proposal.created_by === user?.id),
  };
}
