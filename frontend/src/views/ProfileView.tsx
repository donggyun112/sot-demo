import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { lastWorkspace, useSot, useWorkspaceUi } from "../app/sot";
import { CopyId } from "../components/CopyId";
import { TopBar } from "../components/AppShell";
import styles from "./product.module.css";

export function ProfileView() {
  const { t } = useTranslation();
  const { api, user, onLogout } = useSot();
  const logoutAll = api.useMutation("post", "/api/v1/auth/logout-all");
  const { workspaces } = useWorkspaceUi();
  const workspaceId = lastWorkspace() ?? workspaces[0]?.id;
  const workspaceName = workspaces.find((item) => item.id === workspaceId)?.name;
  const me = api.useQuery(
    "get",
    "/api/v1/workspaces/{workspace_id}/members/me",
    { params: { path: { workspace_id: workspaceId ?? "pending" } } },
    { enabled: Boolean(workspaceId) },
  );
  const profile = api.useQuery("get", "/api/v1/me");
  const person = profile.data ?? user;
  return (
    <div className={styles.page}>
      <TopBar title={t("profile.title")} />
      <div className={styles.center}>
        <div className={styles.stack}>
          <h1>{t("profile.title")}</h1>
          {person && (
            <>
              <h2>{t("profile.account")}</h2>
              <div className={styles.row}>
                <div>
                  <div className={styles.rowTitle}>{person.display_name}</div>
                  <div className={styles.meta}>{person.email}</div>
                </div>
                <CopyId label={t("profile.userId")} value={person.id} />
              </div>
              <p className={styles.note}>{t("profile.userIdHint")}</p>
            </>
          )}

          {me.data && (
            <>
              <h2>{t("profile.role")}</h2>
              <div className={styles.row}>
                <div>
                  <div className={styles.rowTitle}>
                    {workspaceName ?? t("workspace.switch")}
                  </div>
                  <div className={styles.meta}>{t(`workspaceRole.${me.data.role}`)}</div>
                </div>
              </div>
            </>
          )}

          <h2>{t("workspace.switch")}</h2>
          {workspaces.map((item) => (
            <Link key={item.id} className={styles.row} to={`/w/${item.id}`}>
              <div className={styles.rowTitle}>{item.name}</div>
              {item.id === workspaceId && (
                <span className={styles.chip} data-tone="accent">
                  {t("workspace.current")}
                </span>
              )}
            </Link>
          ))}

          <div className={styles.toolbar}>
            <button
              className={styles.ghost}
              type="button"
              disabled={logoutAll.isPending}
              onClick={() => logoutAll.mutate({}, { onSuccess: () => onLogout() })}
            >
              {t("profile.logoutAll")}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
