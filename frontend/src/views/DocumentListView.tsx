import { useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link, useNavigate, useParams } from "react-router";
import { can, useSot, useWorkspaceUi } from "../app/sot";
import { TopBar } from "../components/AppShell";
import { headingsFrom } from "./outline";
import styles from "./product.module.css";

export function DocumentListView() {
  const { t } = useTranslation();
  const { workspaceId = "" } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { api } = useSot();
  const { member } = useWorkspaceUi();
  const documents = api.useQuery("get", "/api/v1/workspaces/{workspace_id}/documents", {
    params: { path: { workspace_id: workspaceId } },
  });
  const create = api.useMutation("post", "/api/v1/workspaces/{workspace_id}/documents");
  const createError =
    create.error instanceof Error ? create.error.message : t("common.error");
  const rows = documents.data ?? [];
  const isEmpty = documents.isSuccess && rows.length === 0;
  const open = (created: { document: { id: string } }) => {
    void queryClient.invalidateQueries();
    void navigate(`/w/${workspaceId}/documents/${created.document.id}`);
  };
  const createDocument = () =>
    create.mutate(
      {
        params: { path: { workspace_id: workspaceId } },
        body: { title: t("docs.untitled"), content: "" },
      },
      { onSuccess: open },
    );
  /*
    A document that already exists as a file starts as that file. Its first
    revision is the document being born, not an update to it, so this asks
    nobody to approve it — and everything after it still goes through the
    agent and its approvers.
  */
  const uploadDocument = async (file: File) => {
    const content = await file.text();
    /*
      Only a top-level heading names a document. Taking the first heading of
      any depth read a file whose h1 is missing — one that opens with front
      matter, say — as being called after whatever section came first.
    */
    const heading = headingsFrom(content).find(
      (one) => one.depth === 1 && one.title,
    );
    create.mutate(
      {
        params: { path: { workspace_id: workspaceId } },
        body: {
          title: heading?.title ?? file.name.replace(/\.mdx?$/i, ""),
          content,
        },
      },
      { onSuccess: open },
    );
  };
  return (
    <div className={styles.page}>
      <TopBar title={t("docs.title")} />
      <div className={styles.center}>
        <div className={styles.stack}>
          <h1>{isEmpty ? t("docs.emptyTitle") : t("docs.title")}</h1>
          {isEmpty && <p className={styles.sub}>{t("docs.empty")}</p>}

          {documents.isLoading && <p className={styles.empty}>{t("common.loading")}</p>}
          {documents.isError && (
            <p className={styles.alert} role="alert">
              {t("common.error")}
            </p>
          )}

          {can(member, "document.create") && documents.isSuccess && (
            <div className={styles.toolbar}>
              <button
                className={styles.primary}
                type="button"
                disabled={create.isPending}
                onClick={createDocument}
              >
                {t("docs.create")}
              </button>
              <label className={styles.ghost}>
                {create.isPending ? t("common.working") : t("docs.upload")}
                <input
                  className={styles.fileInput}
                  type="file"
                  accept=".md,.markdown,.mdx,text/markdown,text/plain"
                  onChange={(event) => {
                    const file = event.target.files?.[0];
                    /* Clear it, or picking the same file twice does nothing. */
                    event.target.value = "";
                    if (file) void uploadDocument(file);
                  }}
                />
              </label>
            </div>
          )}
          {create.isError && (
            <p className={styles.alert} role="alert">
              {createError}
            </p>
          )}

          {rows.map((doc) => (
            <Link
              key={doc.id}
              className={styles.row}
              to={`/w/${workspaceId}/documents/${doc.id}`}
            >
              <div>
                <div className={styles.rowTitle}>
                  {doc.title || t("docs.untitled")}
                </div>
                <div className={styles.meta}>
                  {t("docs.revision", { number: doc.version })}
                </div>
              </div>
              <span className={styles.chip}>{t("docs.open")}</span>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
