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
  const revision = document.data?.current_revision;
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
                  <span className={styles.chip} data-tone="ok">
                    {t("document.canonical")}
                  </span>
                  {t("docs.revision", { number: revision.number })}
                  {open.length > 0 && (
                    <span className={styles.chip} data-tone="accent">
                      {t("document.pendingCount", { count: open.length })}
                    </span>
                  )}
                </div>
                <h1>{document.data?.document.title || t("docs.untitled")}</h1>
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
