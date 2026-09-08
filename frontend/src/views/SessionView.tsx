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
          bundleId={params.get("bundle")}
          onPublished={(id) => setParam("bundle", id)}
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
              {t(`turnRole.${turn.role}`)} · {turn.ordinal}
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
  bundleId,
  onPublished,
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
  bundleId: string | null;
  onPublished: (id: string) => void;
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
  const publish = api.useMutation(
    "post",
    "/api/v1/workspaces/{workspace_id}/branches/{branch_id}/bundles",
  );
  const send = api.useMutation(
    "post",
    "/api/v1/workspaces/{workspace_id}/sessions/{session_id}/members",
  );
  const nameOf = useDisplayName();
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
  const [recipient, setRecipient] = useState("");
  /* Only people who do not already hold it can be sent it. */
  const candidates = (roster.data ?? []).filter(
    (item) => !(members.data ?? []).some((held) => held.user_id === item.user_id),
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
  const participate = can(member, "session.participate");
  const previewItems = preview.data ?? [];
  const [bumped, setBumped] = useState<{ id: string; version: number } | null>(null);
  const version = Math.max(
    branch?.version ?? 0,
    bumped && branchId && bumped.id === branchId ? bumped.version : 0,
  );
  const failure = [publish.error, send.error].find(Boolean);
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

      <div role="region" aria-label={t("sessions.preview")}>
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
      </div>

    </aside>
  );

  /** Declared below the return (hoisted) to keep it out of the panel's layout. */
  function renderPath() {
    return (
      <Section title={t("sessions.path")}>
        <Action
          variant="primary"
          label={t("sessions.publish")}
          hint={t("sessions.publishHint")}
          pending={publish.isPending}
          blockedBy={
            !participate
              ? t("sessions.needParticipate")
              : previewItems.length === 0
                ? t("sessions.needCurated")
                : bundleId
                  ? t("sessions.alreadyPublished")
                  : undefined
          }
          onClick={() => {
            if (branchId == null) return;
            publish.mutate(
              {
                params: { path: { workspace_id: workspaceId, branch_id: branchId } },
                body: {
                  expected_version: version,
                  // Whoever opens the link reads a conversation, so name
                  // it after the conversation rather than after the record.
                  title: titleFromTurns(turns, t("sessions.untitledSession")),
                },
              },
              {
                onSuccess: (result) => {
                  setBumped({ id: branchId, version: result.branch_version });
                  onPublished(result.resource_id);
                },
              },
            )
          }}
        />

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
          {participate ? (
            <form
              onSubmit={(event) => {
                event.preventDefault();
                if (!recipient) return;
                send.mutate(
                  {
                    params: {
                      path: { workspace_id: workspaceId, session_id: sessionId },
                    },
                    body: { user_id: recipient, role: "editor" },
                  },
                  {
                    onSuccess: () => {
                      setRecipient("");
                      void queryClient.invalidateQueries();
                    },
                  },
                );
              }}
            >
              <label className={styles.label} htmlFor="session-recipient">
                {t("send.recipient")}
                <select
                  id="session-recipient"
                  className={styles.select}
                  value={recipient}
                  onChange={(event) => setRecipient(event.target.value)}
                >
                  <option value="">{t("send.choose")}</option>
                  {candidates.map((item) => (
                    <option key={item.user_id} value={item.user_id}>
                      {item.display_name}
                    </option>
                  ))}
                </select>
              </label>
              <button
                className={styles.primary}
                type="submit"
                disabled={!recipient || send.isPending}
              >
                {send.isPending ? t("common.working") : t("send.action")}
              </button>
              {send.isError && (
                <p className={styles.alert} role="alert">
                  {t("common.error")}
                </p>
              )}
            </form>
          ) : (
            <p className={styles.note}>{t("sessions.needParticipate")}</p>
          )}
        </Section>

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
