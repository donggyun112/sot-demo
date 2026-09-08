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
  const rows = sessions.data ?? [];
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
                disabled={create.isPending}
                onClick={() =>
                  create.mutate(
                    {
                      params: {
                        path: { workspace_id: workspaceId, document_id: documentId },
                      },
                      body: {},
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
                {t("sessions.new")}
              </button>
            </div>
          )}
          {create.isError && (
            <p className={styles.alert} role="alert">
              {create.error instanceof Error
                ? create.error.message
                : t("common.error")}
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
                <div className={styles.rowTitle}>{at(item.created_at)}</div>
                <div className={styles.meta}>{nameOf(item.created_by)}</div>
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
                  <span className={styles.chip}>{t(`sessionStatus.${item.status}`)}</span>
                </Link>
              ))}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
