import { useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link, useNavigate, useParams } from "react-router";
import { can, rememberWorkspace, useSot, useWorkspaceUi } from "../app/sot";
import { useDisplayName, useTimestamp } from "../app/identity";
import { TopBar } from "../components/AppShell";
import styles from "./product.module.css";

export function SessionListView() {
  const { t } = useTranslation();
  const { workspaceId = "", documentId = "" } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { api } = useSot();
  const { member } = useWorkspaceUi();
  const nameOf = useDisplayName();
  const at = useTimestamp();
  rememberWorkspace(workspaceId);
  const sessions = api.useQuery(
    "get",
    "/api/v1/workspaces/{workspace_id}/documents/{document_id}/sessions",
    { params: { path: { workspace_id: workspaceId, document_id: documentId } } },
  );
  const proposals = api.useQuery(
    "get",
    "/api/v1/workspaces/{workspace_id}/documents/{document_id}/proposals",
    { params: { path: { workspace_id: workspaceId, document_id: documentId } } },
  );
  const label = (item: { status: string; document_id: string | null }) => {
    if (item.status === "closed") return t("sessionStatus.closed");
    if (!item.document_id) return t("sessions.shared");
    return t("sessionStatus.open");
  };
  const create = api.useMutation(
    "post",
    "/api/v1/workspaces/{workspace_id}/documents/{document_id}/sessions",
  );
  /*
    The argument behind a decision has usually already been had, somewhere
    else. Retyping it so the agent can read it is how it gets lost, so the
    file of it becomes a session: turn by turn, each one citable on its own.
  */
  const importSession = api.useMutation(
    "post",
    "/api/v1/workspaces/{workspace_id}/documents/{document_id}/imported-sessions",
  );
  const open = (created: { session_id: string }) => {
    void queryClient.invalidateQueries();
    void navigate(`/w/${workspaceId}/sessions/${created.session_id}`);
  };
  const importFile = async (file: File) => {
    importSession.mutate(
      {
        params: { path: { workspace_id: workspaceId, document_id: documentId } },
        body: { filename: file.name, content: await file.text() },
      },
      { onSuccess: open },
    );
  };
  const failure = [create.error, importSession.error].find(Boolean);
  const rows = sessions.data ?? [];
  const busy = create.isPending || importSession.isPending;
  return (
    <div className={styles.page}>
      <TopBar
        title={t("sessions.title")}
        actions={
          <Link
            className={styles.ghost}
            to={`/w/${workspaceId}/documents/${documentId}`}
          >
            {t("header.document")}
          </Link>
        }
      />
      <div className={styles.center}>
        <div className={styles.stack}>
          <h1>{t("sessions.title")}</h1>
          <p className={styles.sub}>{t("sessions.empty")}</p>

          {can(member, "session.create") && (
            <div className={styles.toolbar}>
              <button
                className={styles.primary}
                type="button"
                disabled={busy}
                onClick={() =>
                  create.mutate(
                    {
                      params: {
                        path: { workspace_id: workspaceId, document_id: documentId },
                      },
                      body: {},
                    },
                    { onSuccess: open },
                  )
                }
              >
                {t("sessions.new")}
              </button>
              <label className={styles.ghost}>
                {importSession.isPending
                  ? t("common.working")
                  : t("sessions.import")}
                <input
                  className={styles.fileInput}
                  type="file"
                  accept=".md,.markdown,.mdx,.txt,.json,text/markdown,text/plain,application/json"
                  disabled={busy}
                  onChange={(event) => {
                    const file = event.target.files?.[0];
                    /* Cleared, or the same file twice does nothing. */
                    event.target.value = "";
                    if (file) void importFile(file);
                  }}
                />
              </label>
            </div>
          )}
          <p className={styles.meta}>{t("sessions.importHint")}</p>
          {failure && (
            <p className={styles.alert} role="alert">
              {failure instanceof Error ? failure.message : t("common.error")}
            </p>
          )}

          {sessions.isLoading && <p className={styles.empty}>{t("common.loading")}</p>}
          {sessions.isError && (
            <p className={styles.alert} role="alert">
              {t("common.error")}
            </p>
          )}
          {sessions.isSuccess && rows.length === 0 && (
            <p className={styles.empty}>{t("sessions.emptyList")}</p>
          )}

          {rows.map((item) => (
            <Link
              key={item.id}
              className={styles.row}
              to={`/w/${workspaceId}/sessions/${item.id}`}
            >
              <div>
                <div className={styles.rowTitle}>
                  {item.imported_from ?? at(item.created_at)}
                </div>
                <div className={styles.meta}>
                  {item.imported_from
                    ? `${t("sessions.imported")} · ${nameOf(item.created_by)}`
                    : nameOf(item.created_by)}
                </div>
              </div>
              <span className={styles.chip}>{label(item)}</span>
            </Link>
          ))}

          {(proposals.data?.length ?? 0) > 0 && (
            <>
              <h2>{t("document.proposals")}</h2>
              {proposals.data?.map((item) => (
                <Link
                  key={item.id}
                  className={styles.row}
                  to={`/w/${workspaceId}/proposals/${item.id}`}
                >
                  <div>
                    <div className={styles.rowTitle}>{t("proposal.title")}</div>
                    <div className={styles.meta}>{at(item.created_at)}</div>
                  </div>
                  <span className={styles.chip}>{t(`proposalStatus.${item.status}`)}</span>
                </Link>
              ))}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
