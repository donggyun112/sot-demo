import { lazy, Suspense, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import type { API } from "../api";
import type { AuthSession } from "../auth";
import type { Branch, CurrentMember } from "../types";

const AgentChat = lazy(() =>
  import("./AgentChat").then((module) => ({ default: module.AgentChat })),
);

interface SessionWorkspaceProps {
  auth: AuthSession;
  api: API;
  apiBase: string;
  workspaceId: string;
  sessionId: string;
  member?: CurrentMember;
  onOpenToss: (token: string) => void;
  publishedBundle: { branchId: string; bundleId: string } | null;
  onPublishedBundleChange: (
    value: { branchId: string; bundleId: string } | null,
  ) => void;
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
  if (error && (!session.data || !branches.data))
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
      {error && (
        <p role="alert">
          {error instanceof Error
            ? error.message
            : "세션을 동기화하지 못했습니다."}
        </p>
      )}
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
      <BranchWorkspace
        key={branch.id}
        {...props}
        branch={branch}
        documentId={session.data.document_id}
      />
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
  member,
  branch,
  onOpenToss,
  publishedBundle,
  onPublishedBundleChange,
}: SessionWorkspaceProps & { branch: Branch; documentId: string | null }) {
  const cache = useQueryClient();
  const params = {
    params: { path: { workspace_id: workspaceId, branch_id: branch.id } },
  };
  const sessionParams = {
    params: { path: { workspace_id: workspaceId, session_id: sessionId } },
  };
  const documentParams = {
    params: {
      path: { workspace_id: workspaceId, document_id: documentId ?? "" },
    },
  };
  const turns = api.useQuery(
    "get",
    "/api/v1/workspaces/{workspace_id}/branches/{branch_id}/turns",
    params,
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
  const [additionalApprovers, setAdditionalApprovers] = useState("");
  const bundleId =
    publishedBundle?.branchId === branch.id ? publishedBundle.bundleId : null;
  const [previewVersion, setPreviewVersion] = useState<number | null>(null);
  const [curationVersion, setCurationVersion] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  const canParticipate =
    member?.permissions.includes("session.participate") ?? false;
  const currentProjection =
    curationVersion === branch.version ? preview.data : undefined;
  const previewSources = preview.data?.flatMap((item) => item.source_ids) ?? [];
  const previewMatchesSelection =
    previewSources.length === selected.size &&
    previewSources.every((id) => selected.has(id));
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
  const queryError = turns.error;
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
            <p className="muted">
              적용하면 체크하지 않은 항목은 선별 결과에서 제외되며 복구할 수 없습니다.
              이미 합친 항목은 묶음 전체를 선택합니다. Bundle 미리보기에서 현재 묶음을 확인하세요.
            </p>
            {!turns.data?.length ? (
              <p className="muted">
                완료된 대화가 저장되면 근거로 고를 수 있습니다.
              </p>
            ) : (
              <form
                onSubmit={(event) => {
                  event.preventDefault();
                  void perform(async () => {
                    setPreviewVersion(null);
                    onPublishedBundleChange(null);
                    const latestBranches = await cache.fetchQuery({
                      ...api.queryOptions(
                        "get",
                        "/api/v1/workspaces/{workspace_id}/sessions/{session_id}/branches",
                        sessionParams,
                      ),
                      staleTime: 0,
                    });
                    let version = latestBranches.find(
                      (item) => item.id === branch.id,
                    )?.version;
                    if (version === undefined)
                      throw new Error("Branch를 다시 선택하세요.");
                    const current = await preview.refetch({ throwOnError: true });
                    const items = current.data ?? [];
                    setCurationVersion(version);
                    const available = new Set(
                      items.flatMap((item) => item.source_ids),
                    );
                    if ([...selected].some((id) => !available.has(id))) {
                      setSelected(new Set(
                        [...selected].filter((id) => available.has(id)),
                      ));
                      throw new Error("이미 제외된 Turn은 다시 선택할 수 없습니다.");
                    }
                    if (items.some((item) =>
                      item.source_ids.some((id) => selected.has(id)) &&
                      !item.source_ids.every((id) => selected.has(id)),
                    ))
                      throw new Error("이미 합친 Turn은 묶음 전체를 선택하거나 제외하세요.");
                    try {
                      // Drop excludes a whole projected item, including every source
                      // of an existing join. Never repeat old drops on a retry.
                      for (const item of items) {
                        if (item.source_ids.some((id) => selected.has(id))) continue;
                        const result = await curate.mutateAsync({
                          ...params,
                          body: {
                            expected_version: version,
                            operation: { kind: "drop", turn_id: item.source_ids[0] },
                          },
                        });
                        version = result.branch_version;
                      }
                      const joined = await curate.mutateAsync({
                        ...params,
                        body: {
                          expected_version: version,
                          operation: {
                            kind: "join",
                            turn_ids: items
                              .flatMap((item) => item.source_ids)
                              .filter((id) => selected.has(id)),
                            content: summary.trim(),
                          },
                        },
                      });
                      version = joined.branch_version;
                    } finally {
                      // Partial success is canonical too. Keep publication disabled
                      // and reload state whether a later operation succeeds or fails.
                      await Promise.all([
                        refreshBranch(),
                        preview.refetch({ throwOnError: true }),
                      ]);
                      setCurationVersion(version);
                    }
                    setStatus(
                      "선별을 적용했습니다. Bundle 미리보기를 확인하세요.",
                    );
                  });
                }}
              >
                <ul className="turn-list">
                  {turns.data.map((turn) => {
                    const group = currentProjection?.find(
                      (item) => item.source_ids.includes(turn.id),
                    )?.source_ids;
                    const excluded = currentProjection !== undefined && !group;
                    return (
                    <li key={turn.id}>
                      <label>
                        <input
                          type="checkbox"
                          checked={selected.has(turn.id)}
                          aria-label={`${turn.content} 선택`}
                          disabled={busy || excluded}
                          onChange={() => {
                            setPreviewVersion(null);
                            setSelected((current) => {
                              const next = new Set(current);
                              const ids = group ?? [turn.id];
                              if (next.has(turn.id))
                                ids.forEach((id) => next.delete(id));
                              else ids.forEach((id) => next.add(id));
                              return next;
                            });
                          }}
                        />
                        <span>
                          <small>{turn.role}</small>
                          {turn.content}
                          {excluded && <small>선별에서 제외됨</small>}
                        </span>
                      </label>
                    </li>
                    );
                  })}
                </ul>
                <label>
                  인용 요약
                  <input
                    value={summary}
                    disabled={busy}
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
                  if (result.data) {
                    setPreviewVersion(branch.version);
                    setCurationVersion(branch.version);
                  }
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
                {!previewMatchesSelection && (
                  <p className="muted">
                    체크한 항목과 미리보기가 다릅니다. 선별 적용 후 다시 확인하세요.
                  </p>
                )}
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
                    busy || !summary.trim() || preview.data.length === 0 ||
                    !previewMatchesSelection
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
                      onPublishedBundleChange({
                        branchId: branch.id,
                        bundleId: published.resource_id,
                      });
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
          {documentId && (
            <section>
              <h2>Main 변경 제안</h2>
              <form
                onSubmit={(event) => {
                  event.preventDefault();
                  if (!documentId) return;
                  const approverIds = [
                    ...new Set(
                      additionalApprovers
                        .split(",")
                        .map((value) => value.trim().toLowerCase())
                        .filter(Boolean),
                    ),
                  ];
                  if (
                    approverIds.some((value) => !z.uuid().safeParse(value).success)
                  ) {
                    setStatus("승인자 ID는 UUID 형식이어야 합니다.");
                    return;
                  }
                  void perform(async () => {
                    await propose.mutateAsync({
                      ...documentParams,
                      body: {
                        source_session_id: sessionId,
                        content: proposalText.trim(),
                        additional_approver_ids: approverIds,
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
                    setAdditionalApprovers("");
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
                <label>
                  추가 승인자 ID (쉼표로 구분)
                  <input
                    value={additionalApprovers}
                    onChange={(event) => setAdditionalApprovers(event.target.value)}
                  />
                </label>
                <p className="muted">
                  같은 Workspace의 멤버 ID를 입력하세요. 승인자로 지정해도 비공개
                  세션 접근 권한은 생기지 않습니다.
                </p>
                <button
                  className="button secondary"
                  disabled={
                    busy ||
                    !canParticipate ||
                    !documentId ||
                    !proposalText.trim()
                  }
                  type="submit"
                >
                  Proposal 만들기
                </button>
              </form>
            </section>
          )}
        </aside>
      </div>
      <p role="status" aria-live="polite" className="status-bar">
        {status}
      </p>
    </>
  );
}
