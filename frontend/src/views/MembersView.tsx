import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Navigate, useParams } from "react-router";
import { can, useSot, useWorkspaceUi } from "../app/sot";
import { useWorkspaceMembers } from "../app/identity";
import { TopBar } from "../components/AppShell";
import styles from "./product.module.css";

export function MembersView() {
  const { t } = useTranslation();
  const { workspaceId = "" } = useParams();
  const queryClient = useQueryClient();
  const { api, user } = useSot();
  const { member, workspaces } = useWorkspaceUi();
  const [userId, setUserId] = useState("");
  const members = useWorkspaceMembers();
  const add = api.useMutation("post", "/api/v1/workspaces/{workspace_id}/members");
  if (member && !can(member, "workspace.manage")) {
    return <Navigate to={`/w/${workspaceId}`} replace />;
  }
  const workspaceName = workspaces.find((item) => item.id === workspaceId)?.name;
  const rows = members.data ?? [];
  return (
    <div className={styles.page}>
      <TopBar title={t("members.title")} />
      <div className={styles.center}>
        <div className={styles.stack}>
          <h1>{t("members.title")}</h1>
          <p className={styles.sub}>{workspaceName ?? t("members.hint")}</p>

          {members.isLoading && <p className={styles.empty}>{t("common.loading")}</p>}
          {members.isError && (
            <p className={styles.alert} role="alert">
              {t("common.error")}
            </p>
          )}
          {rows.map((item) => (
            <div key={item.user_id} className={styles.row} title={item.user_id}>
              <div>
                <div className={styles.rowTitle}>{item.display_name}</div>
                <div className={styles.meta}>{t(`workspaceRole.${item.role}`)}</div>
              </div>
              {item.user_id === user?.id && (
                <span className={styles.chip} data-tone="accent">
                  {t("members.you")}
                </span>
              )}
            </div>
          ))}

          <h2>{t("members.add")}</h2>
          <p className={styles.sub}>{t("members.hint")}</p>
          <form
            onSubmit={(event) => {
              event.preventDefault();
              if (!userId.trim()) return;
              add.mutate(
                {
                  params: { path: { workspace_id: workspaceId } },
                  body: { user_id: userId.trim(), role: "member" },
                },
                {
                  onSuccess: () => {
                    setUserId("");
                    void queryClient.invalidateQueries();
                  },
                },
              );
            }}
          >
            <label className={styles.label} htmlFor="member-user-id">
              {t("members.userId")}
              <input
                id="member-user-id"
                className={styles.input}
                value={userId}
                onChange={(event) => setUserId(event.target.value)}
                placeholder="00000000-0000-0000-0000-000000000000"
              />
            </label>
            <p className={styles.note}>{t("members.userIdHint")}</p>
            <div className={styles.toolbar}>
              <button
                className={styles.primary}
                type="submit"
                disabled={!userId.trim() || add.isPending}
              >
                {t("members.add")}
              </button>
            </div>
            {add.isSuccess && <p className={styles.empty}>{t("members.added")}</p>}
            {add.isError && (
              <p className={styles.alert} role="alert">
                {add.error instanceof Error ? add.error.message : t("common.error")}
              </p>
            )}
          </form>
        </div>
      </div>
    </div>
  );
}
