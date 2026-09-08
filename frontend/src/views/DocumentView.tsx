import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link, useNavigate, useParams, useSearchParams } from "react-router";
import { can, rememberWorkspace, useSot, useWorkspaceUi } from "../app/sot";
import { ordinalLabel, useDisplayName, useTimestamp } from "../app/identity";
import { TopBar } from "../components/AppShell";
import { Section } from "../components/Page";
import { MarkdownBody } from "../components/MarkdownBody";
import { headingsFrom } from "./outline";
import { editSummary } from "./patch";
import styles from "./product.module.css";

export function DocumentView() {
  const { t } = useTranslation();
  const { workspaceId = "", documentId = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { api } = useSot();
  const { member } = useWorkspaceUi();
  const nameOf = useDisplayName();
  const at = useTimestamp();
  rememberWorkspace(workspaceId);
  const proposals = api.useQuery(
    "get",
    "/api/v1/workspaces/{workspace_id}/documents/{document_id}/proposals",
    { params: { path: { workspace_id: workspaceId, document_id: documentId } } },
  );
  const document = api.useQuery(
    "get",
    "/api/v1/workspaces/{workspace_id}/documents/{document_id}",
    { params: { path: { workspace_id: workspaceId, document_id: documentId } } },
  );
  const sessions = api.useQuery(
    "get",
    "/api/v1/workspaces/{workspace_id}/documents/{document_id}/sessions",
    { params: { path: { workspace_id: workspaceId, document_id: documentId } } },
  );
  const create = api.useMutation(
    "post",
    "/api/v1/workspaces/{workspace_id}/documents/{document_id}/sessions",
  );
  const rename = api.useMutation(
    "patch",
    "/api/v1/workspaces/{workspace_id}/documents/{document_id}",
  );
  const history = api.useQuery(
    "get",
    "/api/v1/workspaces/{workspace_id}/documents/{document_id}/revisions",
    { params: { path: { workspace_id: workspaceId, document_id: documentId } } },
  );
  /*
    Reading an old revision is reading, not editing: the number lives in the
    URL so a link to "what it said then" is a link someone else can open.
  */
  const reading = Number(params.get("revision")) || null;
  const past = api.useQuery(
    "get",
    "/api/v1/workspaces/{workspace_id}/documents/{document_id}/revisions/{number}",
    {
      params: {
        path: {
          workspace_id: workspaceId,
          document_id: documentId,
          number: reading ?? 1,
        },
      },
    },
    { enabled: reading !== null },
  );
  const [renaming, setRenaming] = useState<string | null>(null);
  const current = document.data?.current_revision;
  const revision = reading !== null ? (past.data ?? current) : current;
  const headings = headingsFrom(revision?.content ?? "");
  const selected = params.get("block") ?? headings[0]?.id;
  const heading = headings.find((item) => item.id === selected) ?? headings[0];
  const panel = params.get("panel");
  const citations = revision?.citations ?? [];
  /** Merged proposals are already in the text; only unresolved ones are pending. */
  const open = (proposals.data ?? []).filter(
    (item) => item.status === "open" || item.status === "approved",
  );
  const cited = citations.filter(
    (item) => heading && item.claim_anchor === heading.title,
  );
  /** Keep every other search param — selection is not the only thing in the URL. */
  const setParam = (key: string, value: string | null) => {
    const next = new URLSearchParams(params);
    if (value === null) next.delete(key);
    else next.set(key, value);
    setParams(next, { replace: true });
  };
  const startSession = () =>
    create.mutate(
      {
        params: { path: { workspace_id: workspaceId, document_id: documentId } },
        body: {},
      },
      {
        onSuccess: (created) => {
          void queryClient.invalidateQueries();
          void navigate(`/w/${workspaceId}/sessions/${created.session_id}`);
        },
      },
    );
  return (
    <div className={styles.page}>
      <TopBar
        title={document.data?.document.title ?? t("header.document")}
        actions={
          <>
            <Link
              className={styles.ghost}
              to={`/w/${workspaceId}/documents/${documentId}/sessions`}
            >
              {t("header.sessions")}
            </Link>
            {/* The screen's one primary action sits in its header. */}
            <button
              type="button"
              className={styles.primary}
              disabled={create.isPending || !can(member, "session.create")}
              title={
                can(member, "session.create")
                  ? t("document.startSessionHint")
                  : t("sessions.needParticipate")
              }
              onClick={startSession}
            >
              {create.isPending ? t("common.working") : t("document.startSession")}
            </button>
          </>
        }
      />
      {document.isError ? (
        <div className={styles.center}>
          <p className={styles.alert} role="alert">
            {t("document.notFound")}
          </p>
        </div>
      ) : document.isLoading || !revision ? (
        <div className={styles.center}>
          <p className={styles.empty}>{t("common.loading")}</p>
        </div>
      ) : (
        <>
          <div className={styles.panelBar}>
            <button
              type="button"
              className={styles.ghost}
              onClick={() =>
                setParam("panel", panel === "evidence" ? null : "evidence")
              }
            >
              {panel === "evidence" ? t("document.hide") : t("document.showEvidence")}
            </button>
          </div>
          {/* Outline lives in the shell, nested under this document. */}
          <div className={styles.columns}>
            <article className={styles.doc}>
              <div className={styles.card}>
                <div className={styles.cardHead}>
                  <span
                    className={styles.chip}
                    data-tone={reading === null ? "ok" : "accent"}
                  >
                    {t("document.canonical")}
                  </span>
                  {t("docs.revision", { number: revision.number })}
                  {open.length > 0 && (
                    <span className={styles.chip} data-tone="accent">
                      {t("document.pendingCount", { count: open.length })}
                    </span>
                  )}
                </div>
                {/* Reading an old revision has to say so, or the page lies. */}
                {reading !== null && reading !== current?.number && (
                  <p className={styles.banner} role="status">
                    {t("document.reading", { number: reading })}{" "}
                    <button
                      type="button"
                      className={styles.ghost}
                      onClick={() => setParam("revision", null)}
                    >
                      {t("document.backToCurrent")}
                    </button>
                  </p>
                )}
                {renaming === null ? (
                  <div className={styles.titleRow}>
                    <h1>{document.data?.document.title || t("docs.untitled")}</h1>
                    {can(member, "document.create") && (
                      <button
                        type="button"
                        className={styles.ghost}
                        onClick={() =>
                          setRenaming(document.data?.document.title ?? "")
                        }
                      >
                        {t("document.rename")}
                      </button>
                    )}
                  </div>
                ) : (
                  <form
                    className={styles.titleRow}
                    onSubmit={(event) => {
                      event.preventDefault();
                      const title = renaming.trim();
                      if (!title) return;
                      rename.mutate(
                        {
                          params: {
                            path: {
                              workspace_id: workspaceId,
                              document_id: documentId,
                            },
                          },
                          body: { title },
                        },
                        {
                          onSuccess: () => {
                            setRenaming(null);
                            void queryClient.invalidateQueries();
                          },
                        },
                      );
                    }}
                  >
                    <input
                      className={styles.input}
                      aria-label={t("document.renameLabel")}
                      value={renaming}
                      autoFocus
                      maxLength={200}
                      onChange={(event) => setRenaming(event.target.value)}
                    />
                    <button
                      type="submit"
                      className={styles.primary}
                      disabled={rename.isPending || !renaming.trim()}
                    >
                      {rename.isPending
                        ? t("common.working")
                        : t("document.renameSave")}
                    </button>
                    <button
                      type="button"
                      className={styles.ghost}
                      onClick={() => setRenaming(null)}
                    >
                      {t("common.cancel")}
                    </button>
                  </form>
                )}
                {rename.isError && (
                  <p className={styles.alert} role="alert">
                    {t("common.error")}
                  </p>
                )}
                <MarkdownBody text={revision.content} />
              </div>
            </article>

            <aside
              className={styles.rail}
              data-open={panel === "evidence" ? "true" : "false"}
            >
              {/*
                A canonical document is only trustworthy if you can see what is
                pending against it and where each claim came from. Both live
                here, in that order, plus the one way to start a change.
              */}
              <Section title={t("document.pending")} count={open.length}>
                {open.length === 0 ? (
                  <p className={styles.empty}>{t("document.noPending")}</p>
                ) : (
                  open.map((item) => (
                    <Link
                      key={item.id}
                      className={styles.row}
                      to={`/w/${workspaceId}/proposals/${item.id}`}
                    >
                      <div>
                        <div className={styles.rowTitle}>
                          {editSummary(item.current_version.edits).slice(0, 60) ||
                            t("proposal.title")}
                        </div>
                        <div className={styles.meta}>
                          {t("proposal.approvers")}:{" "}
                          {item.current_version.required_approver_ids.length}
                        </div>
                      </div>
                      <span
                        className={styles.chip}
                        data-tone={item.status === "approved" ? "ok" : "accent"}
                      >
                        {t(`proposalStatus.${item.status}`)}
                      </span>
                    </Link>
                  ))
                )}
              </Section>

              {/* The work in progress against this document. Without it the
                  rail is three empty states stacked on each other. */}
              <Section title={t("sessions.title")} count={sessions.data?.length}>
                {sessions.data?.length === 0 ? (
                  <p className={styles.empty}>{t("sessions.emptyList")}</p>
                ) : (
                  sessions.data?.map((item) => (
                    <Link
                      key={item.id}
                      className={styles.row}
                      to={`/w/${workspaceId}/sessions/${item.id}`}
                    >
                      <div>
                        <div className={styles.rowTitle}>{at(item.created_at)}</div>
                        <div className={styles.meta}>{nameOf(item.created_by)}</div>
                      </div>
                      <span className={styles.chip}>
                        {t(`sessionStatus.${item.status}`)}
                      </span>
                    </Link>
                  ))
                )}
                {create.isError && (
                  <p className={styles.alert} role="alert">
                    {t("common.error")}
                  </p>
                )}
              </Section>

              {/*
                A canonical document is a series of decisions, so its history
                is part of reading it: what changed, when, and which proposal
                carried it. Selecting one reads it in place.
              */}
              <Section title={t("document.history")} count={history.data?.length}>
                {history.data?.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    className={styles.row}
                    data-selected={item.number === reading ? "true" : undefined}
                    onClick={() =>
                      setParam(
                        "revision",
                        item.number === reading ||
                          item.number === current?.number
                          ? null
                          : String(item.number),
                      )
                    }
                  >
                    <div>
                      <div className={styles.rowTitle}>
                        {t("document.historyOf", { number: item.number })}
                      </div>
                      <div className={styles.meta}>
                        {at(item.created_at)} ·{" "}
                        {t("document.historyBy", {
                          name: nameOf(item.created_by),
                        })}
                      </div>
                    </div>
                    <span className={styles.chip}>
                      {item.proposal_id
                        ? t("document.historyProposal")
                        : t("document.historyInitial")}
                    </span>
                  </button>
                ))}
              </Section>

              <Section
                title={t("document.evidence")}
                count={cited.length}
                aside={
                  heading?.title ? (
                    <span className={styles.meta}>{heading.title}</span>
                  ) : undefined
                }
              >
                {cited.length === 0 ? (
                  <p className={styles.empty}>{t("document.naked")}</p>
                ) : (
                  cited.map((item) => {
                    const bundleIndex = [
                      ...new Set(citations.map((one) => one.bundle_id)),
                    ].indexOf(item.bundle_id);
                    return (
                      <div
                        key={`${item.bundle_id}-${item.bundle_item_position}`}
                        className={styles.sideCard}
                        title={item.bundle_id}
                      >
                        <div className={styles.who}>
                          {t("document.citation", {
                            bundle: ordinalLabel(t("proposal.bundle"), bundleIndex),
                            position: item.bundle_item_position + 1,
                          })}
                        </div>
                        <div className={styles.turnBody}>{item.claim_anchor}</div>
                      </div>
                    );
                  })
                )}
              </Section>

            </aside>
          </div>
        </>
      )}
    </div>
  );
}
