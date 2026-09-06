import { lazy, Suspense, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import type { API } from "../api";
import type { AuthSession } from "../auth";
import type { Branch, CurrentMember } from "../types";
import { ProposalView } from "./ProposalView";

const AgentChat = lazy(() =>
  import("./AgentChat").then((module) => ({ default: module.AgentChat })),
);

interface SessionWorkspaceProps {
  auth: AuthSession;
  api: API;
  apiBase: string;
  workspaceId: string;
  sessionId: string;
  documentId: string;
  sourceBundleId?: string | null;
  member?: CurrentMember;
  onOpenToss: (token: string) => void;
}

export function SessionWorkspace(props: SessionWorkspaceProps) {
  const { api, workspaceId, sessionId } = props;
  const params = {
    params: { path: { workspace_id: workspaceId, session_id: sessionId } },
  };
  const session = api.useQuery(
    "get",
    "/api/v1/workspaces/{workspace_id}/sessions/{session_id}",
    params,
  );
  const branches = api.useQuery(
    "get",
    "/api/v1/workspaces/{workspace_id}/sessions/{session_id}/branches",
    params,
  );
  const [selectedBranchId, setBranchId] = useState<string | null>(null);
  const branch =
    branches.data?.find((item) => item.id === selectedBranchId) ??
    branches.data?.find((item) => item.created_by === props.member?.user_id) ??
    branches.data?.[0];
  const error = session.error || branches.error;
  if (error)
    return (
      <p role="alert">
        {error instanceof Error ? error.message : "세션을 불러오지 못했습니다."}
      </p>
    );
  if (!session.data || !branches.data)
    return <p role="status">세션 동기화 중…</p>;
  if (!branch)
    return (
      <main className="empty-state">이 세션에는 아직 branch가 없습니다.</main>
    );
  return (
    <main className="workspace" tabIndex={-1}>
      <header className="workspace-header">
        <div>
          <div className="eyebrow">SESSION · BRANCH V{branch.version}</div>
          <h1>세션 · {session.data.id.slice(0, 8)}</h1>
        </div>
        <label>
          Branch
          <select
            value={branch.id}
            onChange={(event) => setBranchId(event.target.value)}
          >
            {branches.data.map((item) => (
              <option key={item.id} value={item.id}>
                {item.created_by} · {item.id.slice(0, 8)}
              </option>
            ))}
          </select>
        </label>
      </header>
      <BranchWorkspace key={branch.id} {...props} branch={branch} />
    </main>
  );
}

function BranchWorkspace({
  api,
  auth,
  apiBase,
  workspaceId,
  sessionId,
  documentId,
  sourceBundleId,
  member,
  branch,
  onOpenToss,
}: SessionWorkspaceProps & { branch: Branch }) {
  const cache = useQueryClient();
  const params = {
    params: { path: { workspace_id: workspaceId, branch_id: branch.id } },
  };
  const sessionParams = {
    params: { path: { workspace_id: workspaceId, session_id: sessionId } },
  };
  const documentParams = {
    params: { path: { workspace_id: workspaceId, document_id: documentId } },
  };
  const turns = api.useQuery(
    "get",
    "/api/v1/workspaces/{workspace_id}/branches/{branch_id}/turns",
    params,
  );
  const proposals = api.useQuery(
    "get",
    "/api/v1/workspaces/{workspace_id}/documents/{document_id}/proposals",
    documentParams,
    { enabled: Boolean(documentId) },
  );
  const preview = api.useQuery(
    "get",
    "/api/v1/workspaces/{workspace_id}/branches/{branch_id}/bundle-preview",
    params,
    { enabled: false },
  );
  const curate = api.useMutation(
    "post",
    "/api/v1/workspaces/{workspace_id}/branches/{branch_id}/curation-ops",
  );
  const publish = api.useMutation(
    "post",
    "/api/v1/workspaces/{workspace_id}/branches/{branch_id}/bundles",
  );
  const toss = api.useMutation(
    "post",
    "/api/v1/workspaces/{workspace_id}/bundles/{bundle_id}/tosses",
  );
  const propose = api.useMutation(
    "post",
    "/api/v1/workspaces/{workspace_id}/documents/{document_id}/proposals",
  );
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [summary, setSummary] = useState("");
  const [proposalText, setProposalText] = useState("");
  const [bundleId, setBundleId] = useState<string | null>(
    sourceBundleId ?? null,
  );
  const [previewVersion, setPreviewVersion] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  const canParticipate =
    member?.permissions.includes("session.participate") ?? false;
  const refreshBranch = () =>
    cache.invalidateQueries(
      {
        queryKey: api.queryOptions(
          "get",
          "/api/v1/workspaces/{workspace_id}/sessions/{session_id}/branches",
          sessionParams,
        ).queryKey,
        exact: true,
      },
      { throwOnError: true },
    );
  const refreshCommittedRun = async () => {
    // Branch metadata lives in the session's branch-list resource. These are the
    // only two resources invalidated on RUN_FINISHED; no transcript append exists.
    await Promise.all([
      cache.invalidateQueries(
        {
          queryKey: api.queryOptions(
            "get",
            "/api/v1/workspaces/{workspace_id}/branches/{branch_id}/turns",
            params,
          ).queryKey,
          exact: true,
        },
        { throwOnError: true },
      ),
      refreshBranch(),
    ]);
  };
  const perform = async (operation: () => Promise<void>) => {
    setBusy(true);
    setStatus("");
    try {
      await operation();
    } catch (reason) {
      setStatus(
        reason instanceof Error ? reason.message : "요청에 실패했습니다.",
      );
    } finally {
      setBusy(false);
    }
  };
  const queryError = turns.error || proposals.error;
  return (
    <>
      {queryError && (
        <p role="alert">
          {queryError instanceof Error
            ? queryError.message
            : "자료를 불러오지 못했습니다."}
        </p>
      )}
      <div className="workspace-grid">
        <section className="chat-panel" aria-label="Agent conversation">
          {turns.data && canParticipate ? (
            <Suspense fallback={<p role="status">Agent 연결 중…</p>}>
              <AgentChat
                auth={auth}
                apiBase={apiBase}
                workspaceId={workspaceId}
                branchId={branch.id}
                sessionId={sessionId}
                turns={turns.data}
                onSaved={refreshCommittedRun}
              />
            </Suspense>
          ) : (
            <p className="muted">
              {turns.isLoading
                ? "대화 동기화 중…"
                : "이 branch는 읽기만 가능합니다."}
            </p>
          )}
        </section>
        <aside className="curation-panel">
          <section>
            <div className="section-heading">
              <h2>근거 선별</h2>
              <span>{selected.size}</span>
            </div>
            {!turns.data?.length ? (
              <p className="muted">
                완료된 대화가 저장되면 근거로 고를 수 있습니다.
              </p>
            ) : (
              <form
                onSubmit={(event) => {
                  event.preventDefault();
                  void perform(async () => {
                    await curate.mutateAsync({
                      ...params,
                      body: {
                        expected_version: branch.version,
                        operation: {
                          kind: "join",
                          turn_ids: [...selected],
                          content: summary.trim(),
                        },
                      },
                    });
                    setPreviewVersion(null);
                    setBundleId(null);
                    await refreshBranch();
                    await cache.invalidateQueries({
                      queryKey: api.queryOptions(
                        "get",
                        "/api/v1/workspaces/{workspace_id}/branches/{branch_id}/bundle-preview",
                        params,
                      ).queryKey,
                      exact: true,
                    });
                    setStatus(
                      "선별을 적용했습니다. Bundle 미리보기를 확인하세요.",
                    );
                  });
                }}
              >
                <ul className="turn-list">
                  {turns.data.map((turn) => (
                    <li key={turn.id}>
                      <label>
                        <input
                          type="checkbox"
                          checked={selected.has(turn.id)}
                          aria-label={`${turn.content} 선택`}
                          onChange={() =>
                            setSelected((current) => {
                              const next = new Set(current);
                              if (next.has(turn.id)) next.delete(turn.id);
                              else next.add(turn.id);
                              return next;
                            })
                          }
                        />
                        <span>
                          <small>{turn.role}</small>
                          {turn.content}
                        </span>
                      </label>
                    </li>
                  ))}
                </ul>
                <label>
                  인용 요약
                  <input
                    value={summary}
                    onChange={(event) => setSummary(event.target.value)}
                  />
                </label>
                <button
                  className="button"
                  disabled={
                    busy || !canParticipate || !selected.size || !summary.trim()
                  }
                  type="submit"
                >
                  선별 적용
                </button>
              </form>
            )}
            <button
              className="button secondary"
              disabled={busy || !canParticipate}
              type="button"
              onClick={() =>
                void perform(async () => {
                  const result = await preview.refetch({ throwOnError: true });
                  if (result.data) setPreviewVersion(branch.version);
                })
              }
            >
              Bundle 미리보기
            </button>
            {previewVersion === branch.version && preview.data && (
              <section aria-label="Bundle preview">
                <h3>Bundle preview</h3>
                {preview.data.map((item, index) => (
                  <p key={index}>{item.content}</p>
                ))}
                <label>
                  Bundle 제목
                  <input
                    value={summary}
                    onChange={(event) => setSummary(event.target.value)}
                  />
                </label>
                <button
                  className="button"
                  disabled={
                    busy || !summary.trim() || preview.data.length === 0
                  }
                  type="button"
                  onClick={() =>
                    void perform(async () => {
                      const published = await publish.mutateAsync({
                        ...params,
                        body: {
                          expected_version: branch.version,
                          title: summary.trim(),
                        },
                      });
                      setBundleId(published.resource_id);
                      await refreshBranch();
                      setStatus("Bundle을 발행했습니다.");
                    })
                  }
                >
                  Bundle 발행
                </button>
              </section>
            )}
            {bundleId && (
              <button
                className="button accent"
                disabled={busy}
                type="button"
                onClick={() =>
                  void perform(async () => {
                    const created = await toss.mutateAsync({
                      params: {
                        path: {
                          workspace_id: workspaceId,
                          bundle_id: bundleId,
                        },
                      },
                      body: {},
                    });
                    onOpenToss(created.token);
                  })
                }
              >
                Toss 만들기
              </button>
            )}
          </section>
          <section>
            <h2>Main 변경 제안</h2>
            <form
              onSubmit={(event) => {
                event.preventDefault();
                void perform(async () => {
                  await propose.mutateAsync({
                    ...documentParams,
                    body: {
                      source_session_id: sessionId,
                      content: proposalText.trim(),
                      bundle_ids: bundleId ? [bundleId] : [],
                      citations: bundleId
                        ? [
                            {
                              bundle_id: bundleId,
                              bundle_item_position: 0,
                              claim_anchor: proposalText.trim(),
                            },
                          ]
                        : [],
                    },
                  });
                  setProposalText("");
                  await cache.invalidateQueries({
                    queryKey: api.queryOptions(
                      "get",
                      "/api/v1/workspaces/{workspace_id}/documents/{document_id}/proposals",
                      documentParams,
                    ).queryKey,
                    exact: true,
                  });
                  setStatus("Main 변경 제안을 만들었습니다.");
                });
              }}
            >
              <label>
                제안 본문
                <textarea
                  value={proposalText}
                  onChange={(event) => setProposalText(event.target.value)}
                  rows={4}
                />
              </label>
              <button
                className="button secondary"
                disabled={
                  busy || !canParticipate || !documentId || !proposalText.trim()
                }
                type="submit"
              >
                Proposal 만들기
              </button>
            </form>
            <div className="proposal-list">
              {proposals.data
                ?.filter((proposal) => proposal.source_session_id === sessionId)
                .map((proposal) => (
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
        </aside>
      </div>
      <p role="status" aria-live="polite" className="status-bar">
        {status}
      </p>
    </>
  );
}
