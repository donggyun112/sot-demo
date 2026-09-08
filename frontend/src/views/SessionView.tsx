import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link, useNavigate, useParams, useSearchParams } from "react-router";
import { can, rememberWorkspace, useSot, useWorkspaceUi } from "../app/sot";
import { titleFromTurns, useDisplayName, useTimestamp } from "../app/identity";
import { AgentChat } from "../components/AgentChat";
import { CopyId } from "../components/CopyId";

import { TopBar } from "../components/AppShell";
import { Action, Section } from "../components/Page";
import type { Turn } from "../types";
import styles from "./product.module.css";

export function SessionView() {
  const { t } = useTranslation();
  const { workspaceId = "", sessionId = "", branchId } = useParams();
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { api, auth, apiBase, user } = useSot();
  const { member } = useWorkspaceUi();
  const nameOf = useDisplayName();
  const at = useTimestamp();
  rememberWorkspace(workspaceId);

  /** Keep every other search param when one selection changes. */
  const setParam = (key: string, value: string | null) => {
    const next = new URLSearchParams(params);
    if (value === null) next.delete(key);
    else next.set(key, value);
    setParams(next, { replace: true });
  };

  const session = api.useQuery(
    "get",
    "/api/v1/workspaces/{workspace_id}/sessions/{session_id}",
    { params: { path: { workspace_id: workspaceId, session_id: sessionId } } },
  );
  const branches = api.useQuery(
    "get",
    "/api/v1/workspaces/{workspace_id}/sessions/{session_id}/branches",
    { params: { path: { workspace_id: workspaceId, session_id: sessionId } } },
  );
  const branchList = branches.data ?? [];
  const requested = branchId ?? params.get("branch") ?? "";
  const branch =
    branchList.find((item) => item.id === requested) ?? branchList[0];
  const turns = api.useQuery(
    "get",
    "/api/v1/workspaces/{workspace_id}/branches/{branch_id}/turns",
    { params: { path: { workspace_id: workspaceId, branch_id: branch?.id ?? "pending" } } },
    { enabled: Boolean(branch) },
  );
  const documentId = session.data?.document_id;
  const shared = !documentId;
  /*
    A session you hold as a viewer is one you can follow and not answer. The
    way out is not to ask its owner for write access: it is to take the
    conversation into a session of your own, which is what "talking in
    someone's session" meant all along.
  */
  const held = api.useQuery(
    "get",
    "/api/v1/workspaces/{workspace_id}/sessions/{session_id}/members",
    { params: { path: { workspace_id: workspaceId, session_id: sessionId } } },
  );
  const mine = (held.data ?? []).find((item) => item.user_id === user?.id);
  const readOnly = mine?.role === "viewer";
  const fork = api.useMutation(
    "post",
    "/api/v1/workspaces/{workspace_id}/sessions/{session_id}/forks",
  );
  /*
    A file someone puts in front of the agent is something they said, so it
    is appended as a turn: it shows in the transcript, the agent reads it as
    history, and a passage written out of it cites it.
  */
  const attach = api.useMutation(
    "post",
    "/api/v1/workspaces/{workspace_id}/branches/{branch_id}/attachments",
  );
  const origin = session.data?.forked_from_session_id;
  const turnList = turns.data ?? [];
  const panel = params.get("panel");
  const title = titleFromTurns(
    turnList,
    session.data ? at(session.data.created_at) : t("sessions.untitledSession"),
  );

  if (session.isError) {
    return (
      <div className={styles.page}>
        <TopBar title={t("sessions.title")} />
        <div className={styles.center}>
          <p className={styles.alert} role="alert">
            {t("sessions.notFound")}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <TopBar
        title={title}
        actions={
          documentId ? (
            <>
              <Link
                className={styles.ghost}
                to={`/w/${workspaceId}/documents/${documentId}`}
              >
                {t("header.document")}
              </Link>
              <Link
                className={styles.ghost}
                to={`/w/${workspaceId}/documents/${documentId}/sessions`}
              >
                {t("header.sessions")}
              </Link>
            </>
          ) : (
            <span className={styles.chip}>{t("sessions.shared")}</span>
          )
        }
      />
      <div className={styles.panelBar}>
        <button
          type="button"
          className={styles.ghost}
          onClick={() => setParam("panel", panel === "side" ? null : "side")}
        >
          {panel === "side" ? t("document.hide") : t("sessions.showSide")}
        </button>
      </div>
      <div className={styles.session}>
        <div className={styles.thread}>
          <div className={styles.threadHead}>
            <span className={styles.threadTitle}>{title}</span>
            <span className={styles.chip} data-tone={shared ? "accent" : undefined}>
              {shared ? t("sessions.shared") : t("sessions.original")}
            </span>
            <span className={styles.chip}>
              {t("sessions.turnCount", { count: turnList.length })}
            </span>
            <span className={styles.meta}>
              {nameOf(session.data?.created_by)}
            </span>
          </div>
          <p className={styles.banner}>
            {shared ? t("sessions.bannerShared") : t("sessions.bannerOriginal")}
          </p>
          {origin && (
            <p className={styles.banner}>
              {t("sessions.forkedFrom")}{" "}
              <Link
                className={styles.ghost}
                to={`/w/${workspaceId}/sessions/${origin}`}
              >
                {t("sessions.forkOpen")}
              </Link>
            </p>
          )}
          {readOnly && branch && (
            <div className={styles.banner}>
              <button
                type="button"
                className={styles.primary}
                disabled={fork.isPending || !can(member, "session.create")}
                title={
                  can(member, "session.create")
                    ? t("sessions.forkHint")
                    : t("sessions.needParticipate")
                }
                onClick={() =>
                  fork.mutate(
                    {
                      params: {
                        path: {
                          workspace_id: workspaceId,
                          session_id: sessionId,
                        },
                      },
                      body: { branch_id: branch.id },
                    },
                    {
                      onSuccess: (created) => {
                        void queryClient.invalidateQueries();
                        void navigate(
                          `/w/${workspaceId}/sessions/${created.session_id}`,
                        );
                      },
                    },
                  )
                }
              >
                {fork.isPending ? t("common.working") : t("sessions.fork")}
              </button>
              <p className={styles.note}>{t("sessions.forkHint")}</p>
              {fork.isError && (
                <p className={styles.alert} role="alert">
                  {t("common.error")}
                </p>
              )}
            </div>
          )}
          {branches.isLoading && (
            <p className={styles.banner}>{t("common.loading")}</p>
          )}
          {branch && (
            <AgentChat
              auth={auth}
              apiBase={apiBase}
              workspaceId={workspaceId}
              branchId={branch.id}
              sessionId={sessionId}
              turns={turnList}
              // New turns move the branch version and the bundle projection,
              // not just the transcript. Refetching turns alone leaves the
              // bundle preview stuck on the empty state it loaded with.
              onSaved={() => queryClient.invalidateQueries().then(() => undefined)}
              canSend={can(member, "session.participate")}
              youLabel={user?.display_name ?? t("people.you")}
              nameOf={nameOf}
              highlightCall={params.get("call") ?? undefined}
              onAttach={
                can(member, "session.participate") && !readOnly
                  ? async (file) => {
                      await attach.mutateAsync({
                        params: {
                          path: {
                            workspace_id: workspaceId,
                            branch_id: branch.id,
                          },
                        },
                        body: {
                          expected_version: branch.version,
                          filename: file.name,
                          content: await file.text(),
                        },
                      });
                      await queryClient.invalidateQueries();
                    }
                  : undefined
              }
            />
          )}
        </div>
        <SessionSide
          open={panel === "side"}
          workspaceId={workspaceId}
          sessionId={sessionId}
          shared={shared}
          documentId={documentId}
          branches={branchList}
          branch={branch}
          onBranch={(id) => setParam("branch", id)}
          turns={turnList}
          readOnly={readOnly}
          onProposed={(id) => void navigate(`/w/${workspaceId}/proposals/${id}`)}
        />
      </div>
    </div>
  );
}

function CurationTurns({
  workspaceId,
  branchId,
  version,
  onVersion,
  turns,
  groups,
  editable,
}: {
  workspaceId: string;
  branchId: string;
  version: number;
  onVersion: (version: number) => void;
  turns: Turn[];
  /** Turn id -> every source of the bundle item it survives in. */
  groups: Map<string, readonly string[]>;
  editable: boolean;
}) {
  const { t } = useTranslation();
  const { api } = useSot();
  const nameOf = useDisplayName();
  const queryClient = useQueryClient();
  const [editId, setEditId] = useState<string | null>(null);
  const [editText, setEditText] = useState("");
  const [joinIds, setJoinIds] = useState<string[]>([]);
  const curate = api.useMutation(
    "post",
    "/api/v1/workspaces/{workspace_id}/branches/{branch_id}/curation-ops",
  );
  const run = (
    operation:
      | { kind: "drop"; turn_id: string }
      | { kind: "edit"; turn_id: string; content: string }
      | { kind: "join"; turn_ids: string[]; content: string }
      | { kind: "restore"; turn_id: string },
  ) =>
    curate.mutate(
      {
        params: { path: { workspace_id: workspaceId, branch_id: branchId } },
        body: { expected_version: version, operation },
      },
      {
        // Take the version from the response: back-to-back ops must not race
        // the branches refetch and fail on a stale expected_version.
        onSuccess: (result) => {
          setJoinIds([]);
          onVersion(result.branch_version);
          void queryClient.invalidateQueries();
        },
      },
    );
  return (
    <Section title={t("sessions.curation")} count={turns.length}>
      {turns.length === 0 && <p className={styles.empty}>{t("sessions.noTurns")}</p>}
      {curate.isError && (
        <p className={styles.alert} role="alert">
          {curate.error instanceof Error ? curate.error.message : t("common.error")}
        </p>
      )}
      {turns.map((turn) => {
        // Curation is an append-only op log; the bundle preview, not the turn
        // list, says what survived. Show that here or Drop looks like a no-op.
        const dropped = !groups.has(turn.id);
        return (
        <article
          key={turn.id}
          className={styles.turn}
          data-picked={joinIds.includes(turn.id) ? "true" : "false"}
          data-dropped={dropped ? "true" : "false"}
        >
          <div className={styles.turnHead}>
            <span className={styles.turnWho}>
              {turn.role === "user" ? nameOf(turn.created_by) : t("agent.name")} ·{" "}
              {turn.ordinal}
              {dropped && (
                <span className={styles.chip} data-tone="danger">
                  {t("sessions.dropped")}
                </span>
              )}
            </span>
            {/* A dropped turn is gone from the projection, so every other op
                on it is rejected. Putting it back is the one thing left. */}
            {editable && dropped && (
              <div className={styles.turnActions}>
                <button
                  type="button"
                  className={styles.ghost}
                  onClick={() => run({ kind: "restore", turn_id: turn.id })}
                >
                  {t("sessions.restore")}
                </button>
              </div>
            )}
            {editable && !dropped && (
              <div className={styles.turnActions}>
                <button
                  type="button"
                  className={styles.ghost}
                  onClick={() => run({ kind: "drop", turn_id: turn.id })}
                >
                  {t("sessions.drop")}
                </button>
                <button
                  type="button"
                  className={styles.ghost}
                  onClick={() => {
                    setEditId(turn.id);
                    setEditText(turn.content);
                  }}
                >
                  {t("sessions.edit")}
                </button>
                <button
                  type="button"
                  className={styles.ghost}
                  aria-pressed={joinIds.includes(turn.id)}
                  /* Joining takes whole bundle items: picking one source of an
                     already-joined item is rejected as a partial selection. */
                  onClick={() => {
                    const group = groups.get(turn.id) ?? [turn.id];
                    setJoinIds((current) =>
                      current.includes(turn.id)
                        ? current.filter((id) => !group.includes(id))
                        : [...current, ...group.filter((id) => !current.includes(id))],
                    );
                  }}
                >
                  {t("sessions.join")}
                </button>
              </div>
            )}
          </div>
          {editId === turn.id ? (
            <form
              onSubmit={(event) => {
                event.preventDefault();
                run({ kind: "edit", turn_id: turn.id, content: editText });
                setEditId(null);
              }}
            >
              <textarea
                className={styles.input}
                aria-label={t("sessions.edit")}
                value={editText}
                onChange={(event) => setEditText(event.target.value)}
              />
              <div className={styles.turnActions}>
                <button className={styles.primary} type="submit">
                  {t("sessions.saveEdit")}
                </button>
                <button
                  className={styles.ghost}
                  type="button"
                  onClick={() => setEditId(null)}
                >
                  {t("common.cancel")}
                </button>
              </div>
            </form>
          ) : (
            <div className={styles.turnBody}>{turn.content}</div>
          )}
        </article>
        );
      })}
      {editable && joinIds.length >= 2 && (
        <button
          type="button"
          className={styles.primary}
          onClick={() =>
            run({
              kind: "join",
              turn_ids: joinIds,
              content: turns
                .filter((turn) => joinIds.includes(turn.id))
                .map((turn) => turn.content)
                .join("\n"),
            })
          }
        >
          {t("sessions.joinSelected")}
        </button>
      )}
    </Section>
  );
}

function SessionSide({
  open,
  workspaceId,
  sessionId,
  shared,
  documentId,
  branches,
  branch,
  onBranch,
  turns,
  readOnly,
  onProposed,
}: {
  open: boolean;
  workspaceId: string;
  sessionId: string;
  shared: boolean;
  documentId: string | null | undefined;
  branches: { id: string; version: number }[];
  branch: { id: string; version: number } | undefined;
  onBranch: (id: string) => void;
  turns: Turn[];
  /** True when you hold this session to read: it is not yours to hand on. */
  readOnly: boolean;
  onProposed: (id: string) => void;
}) {
  const { t } = useTranslation();
  const { api } = useSot();
  const queryClient = useQueryClient();
  const { member } = useWorkspaceUi();
  const branchId = branch?.id;
  const preview = api.useQuery(
    "get",
    "/api/v1/workspaces/{workspace_id}/branches/{branch_id}/bundle-preview",
    {
      params: { path: { workspace_id: workspaceId, branch_id: branchId ?? "pending" } },
    },
    { enabled: Boolean(branchId) && can(member, "session.read") },
  );
  const send = api.useMutation(
    "post",
    "/api/v1/workspaces/{workspace_id}/sessions/{session_id}/members",
  );
  const nameOf = useDisplayName();
  const { user } = useSot();
  /* Who the session is being handed to, while its last look is open. */
  const [sending, setSending] = useState<string | null>(null);
  const members = api.useQuery(
    "get",
    "/api/v1/workspaces/{workspace_id}/sessions/{session_id}/members",
    { params: { path: { workspace_id: workspaceId, session_id: sessionId } } },
  );
  const roster = api.useQuery(
    "get",
    "/api/v1/workspaces/{workspace_id}/members",
    { params: { path: { workspace_id: workspaceId } } },
  );
  /* Only people who do not already hold it, and never yourself: you are the
     one sending it, and adding yourself twice is a conflict, not an action. */
  const candidates = (roster.data ?? []).filter(
    (item) =>
      item.user_id !== user?.id &&
      !(members.data ?? []).some((held) => held.user_id === item.user_id),
  );
  const propose = api.useMutation(
    "post",
    "/api/v1/workspaces/{workspace_id}/documents/{document_id}/proposals",
  );
  const attached = api.useQuery(
    "get",
    "/api/v1/workspaces/{workspace_id}/documents/{document_id}",
    {
      params: {
        path: { workspace_id: workspaceId, document_id: documentId ?? "pending" },
      },
    },
    { enabled: Boolean(documentId) },
  );
  const participate = can(member, "session.participate") && !readOnly;
  const previewItems = preview.data ?? [];
  const [bumped, setBumped] = useState<{ id: string; version: number } | null>(null);
  const version = Math.max(
    branch?.version ?? 0,
    bumped && branchId && bumped.id === branchId ? bumped.version : 0,
  );
  const failure = send.error;
  // The bundle preview is what gets proposed when the body is left blank, so it
  // counts against the same review limit.
  return (
    <aside className={styles.side} data-open={open ? "true" : "false"}>
      <div>
        <Section
          title={t("sessions.side")}
          aside={<CopyId label={t("sessions.copyId")} value={sessionId} />}
        >
          <div className={styles.chips}>
            <span
              className={styles.chip}
              data-tone={shared ? "accent" : undefined}
            >
              {shared ? t("sessions.shared") : t("sessions.original")}
            </span>
          </div>
        </Section>
      </div>

      {/* Where this draft is headed. A session exists to change a document. */}
      <Section title={t("sessions.target")}>
        {documentId ? (
          <div className={styles.sideCard}>
            <Link to={`/w/${workspaceId}/documents/${documentId}`}>
              {attached.data?.document.title || t("docs.untitled")}
            </Link>
            <p className={styles.note}>
              {attached.data
                ? t("docs.revision", {
                    number: attached.data.current_revision.number,
                  })
                : t("common.loading")}
            </p>
          </div>
        ) : (
          <p className={styles.empty}>{t("sessions.noCite")}</p>
        )}
      </Section>

      {failure && (
        <p className={styles.alert} role="alert">
          {failure instanceof Error ? failure.message : t("common.error")}
        </p>
      )}

      {/*
        The whole path from draft to canonical text stays on screen, above the
        detail it acts on, so it survives a long curation list. Steps you cannot
        take yet say why instead of vanishing.
      */}
      {renderPath()}

      {branches.length > 1 && (
        <Section title={t("sessions.branch")} count={branches.length}>
          <select
            className={styles.select}
            aria-label={t("sessions.branch")}
            value={branchId ?? ""}
            onChange={(event) => onBranch(event.target.value)}
          >
            {branches.map((item, index) => (
              <option key={item.id} value={item.id}>
                {t("sessions.branchLabel", { index: index + 1 })}
              </option>
            ))}
          </select>
        </Section>
      )}

      <Section title={t("sessions.preview")} count={previewItems.length}>
        {previewItems.length === 0 ? (
          <p className={styles.empty}>{t("sessions.previewEmpty")}</p>
        ) : (
          previewItems.map((item, index) => (
            <div key={index} className={styles.sideCard}>
              <div className={styles.who}>{t(`turnRole.${item.role}`)}</div>
              <div className={styles.turnBody}>{item.content}</div>
            </div>
          ))
        )}
      </Section>

      {/*
        Choosing what to hand over belongs to the moment you hand it over.
        In the rail it was a permanent instrument nobody asked for; here it is
        the last look before someone else reads the conversation.
      */}
      {sending && branchId != null && (
        <div className={styles.overlay}>
          <div
            className={`${styles.sheet} ${styles.sendSheet}`}
            role="dialog"
            aria-modal="true"
            aria-labelledby="send-review"
          >
            <h2 id="send-review">{t("send.review", { name: nameOf(sending) })}</h2>
            <p className={styles.note}>{t("send.reviewHint")}</p>
            <div className={styles.sendSheetBody}>
              {branchId != null && (
                <CurationTurns
                  workspaceId={workspaceId}
                  branchId={branchId}
                  version={version}
                  onVersion={(next) => setBumped({ id: branchId, version: next })}
                  turns={turns}
                  groups={
            new Map(
              previewItems.flatMap((item) =>
                item.source_ids.map(
                  (id) => [id, item.source_ids] as [string, readonly string[]],
                ),
              ),
            )
          }
                  editable={participate}
                />
              )}
            </div>
            <div className={styles.sheetActions}>
              <button
                className={styles.primary}
                type="button"
                disabled={send.isPending}
                onClick={() =>
                  send.mutate(
                    {
                      params: {
                        path: { workspace_id: workspaceId, session_id: sessionId },
                      },
                      body: { user_id: sending, role: "editor" },
                    },
                    {
                      onSuccess: () => {
                        setSending(null);
                        void queryClient.invalidateQueries();
                      },
                    },
                  )
                }
              >
                {send.isPending ? t("common.working") : t("send.confirm")}
              </button>
              <button
                className={styles.ghost}
                type="button"
                onClick={() => setSending(null)}
              >
                {t("common.cancel")}
              </button>
            </div>
          </div>
        </div>
      )}
    </aside>
  );

  /** Declared below the return (hoisted) to keep it out of the panel's layout. */
  function renderPath() {
    return (
      <Section title={t("sessions.path")}>
        {/*
          Handing a session over is adding the recipient to it: they open the
          same conversation and keep working in it. A link would have handed
          out a read-only copy of the turns instead.
        */}
        <Section title={t("send.title")} count={members.data?.length}>
          {members.data?.map((item) => (
            <div key={item.user_id} className={styles.row}>
              <div className={styles.rowTitle}>{nameOf(item.user_id)}</div>
              <span className={styles.chip}>{t(`sessionRole.${item.role}`)}</span>
            </div>
          ))}
        </Section>

        {/*
          Send is a list of people, not a picker: the members who do not hold
          it yet, each with the one action that applies to them. A dropdown
          made "nobody" a selectable option and let you pick yourself, which
          only ever ended in a conflict.
        */}
        {!readOnly && (
        <Section title={t("send.title2")} count={candidates.length}>
          {!participate ? (
            <p className={styles.note}>{t("sessions.needParticipate")}</p>
          ) : candidates.length === 0 ? (
            <p className={styles.empty}>{t("send.everyone")}</p>
          ) : (
            candidates.map((item) => (
              <div key={item.user_id} className={styles.row}>
                <div className={styles.rowTitle}>{item.display_name}</div>
                <button
                  type="button"
                  className={styles.ghost}
                  onClick={() => setSending(item.user_id)}
                >
                  {t("send.action")}
                </button>
              </div>
            ))
          )}
          {send.isError && (
            <p className={styles.alert} role="alert">
              {t("common.error")}
            </p>
          )}
        </Section>
        )}

        {/*
          The agent writes document updates, not the person: ask it in the
          session and it calls sot_update with the evidence it cited. A form
          here would have had a human retype the document by hand and invent
          the citation anchors, which is how this screen used to work.
        */}
        <p className={styles.note}>
          {documentId
            ? participate
              ? t("sessions.agentUpdates")
              : t("sessions.needParticipate")
            : t("sessions.needDocument")}
        </p>
      </Section>
    );
  }
}
