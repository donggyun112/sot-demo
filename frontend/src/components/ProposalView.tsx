import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import type { API } from "../api";
import type { CurrentMember } from "../types";

export function ProposalView({
  api,
  workspaceId,
  proposalId,
  member,
}: {
  api: API;
  workspaceId: string;
  proposalId: string;
  member?: CurrentMember;
}) {
  const cache = useQueryClient();
  const params = {
    params: { path: { workspace_id: workspaceId, proposal_id: proposalId } },
  };
  const detail = api.useQuery(
    "get",
    "/api/v1/workspaces/{workspace_id}/proposals/{proposal_id}",
    params,
  );
  const decision = api.useMutation(
    "post",
    "/api/v1/workspaces/{workspace_id}/proposals/{proposal_id}/decisions",
  );
  const merge = api.useMutation(
    "post",
    "/api/v1/workspaces/{workspace_id}/proposals/{proposal_id}/merge",
  );
  const [error, setError] = useState("");
  const proposal = detail.data;
  const refresh = async (published: boolean) => {
    if (!proposal) return;
    const documentParams = {
      params: {
        path: { workspace_id: workspaceId, document_id: proposal.document_id },
      },
    };
    await Promise.all([
      cache.invalidateQueries({
        queryKey: api.queryOptions(
          "get",
          "/api/v1/workspaces/{workspace_id}/proposals/{proposal_id}",
          params,
        ).queryKey,
        exact: true,
      }),
      cache.invalidateQueries({
        queryKey: api.queryOptions(
          "get",
          "/api/v1/workspaces/{workspace_id}/documents/{document_id}/proposals",
          documentParams,
        ).queryKey,
        exact: true,
      }),
      ...(published
        ? [
            cache.invalidateQueries({
              queryKey: api.queryOptions(
                "get",
                "/api/v1/workspaces/{workspace_id}/documents/{document_id}",
                documentParams,
              ).queryKey,
              exact: true,
            }),
            cache.invalidateQueries({
              queryKey: api.queryOptions(
                "get",
                "/api/v1/workspaces/{workspace_id}/documents",
                { params: { path: { workspace_id: workspaceId } } },
              ).queryKey,
              exact: true,
            }),
          ]
        : []),
    ]);
  };
  if (!proposal)
    return (
      <p role={detail.error ? "alert" : "status"}>
        {detail.error instanceof Error
          ? detail.error.message
          : "Proposal 동기화 중…"}
      </p>
    );
  const busy = decision.isPending || merge.isPending;
  const canDecide =
    member &&
    proposal.current_version.required_approver_ids.includes(member.user_id);
  const failed = (reason: unknown) =>
    setError(reason instanceof Error ? reason.message : "요청에 실패했습니다.");
  return (
    <article className="proposal-card">
      <div className="eyebrow">{proposal.status.toUpperCase()}</div>
      <p>{proposal.current_version.content}</p>
      <small>제안자 {proposal.created_by}</small>
      {proposal.status === "open" &&
        canDecide &&
        (["approve", "reject"] as const).map((value) => (
          <button
            className="button"
            key={value}
            disabled={busy}
            type="button"
            onClick={() => {
              void decision
                .mutateAsync({
                  ...params,
                  body: { expected_version: proposal.version, decision: value },
                })
                .then(() => refresh(false))
                .catch(failed);
            }}
          >
            {value === "approve" ? "승인" : "거절"}
          </button>
        ))}
      {proposal.status === "approved" &&
        member?.permissions.includes("document.publish") && (
          <button
            className="button"
            disabled={busy}
            type="button"
            onClick={() => {
              void merge
                .mutateAsync({
                  ...params,
                  body: { expected_version: proposal.version },
                })
                .then(() => refresh(true))
                .catch(failed);
            }}
          >
            Merge
          </button>
        )}
      {error && <p role="alert">{error}</p>}
    </article>
  );
}
