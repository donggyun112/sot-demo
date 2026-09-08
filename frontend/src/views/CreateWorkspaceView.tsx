import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router";
import { rememberWorkspace, useSot } from "../app/sot";
import { TopBar } from "../components/AppShell";
import type { Workspace } from "../types";
import styles from "./product.module.css";

export function CreateWorkspaceView() {
  const { t } = useTranslation();
  const { api, user, onLogout } = useSot();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const create = api.useMutation("post", "/api/v1/workspaces");
  return (
    <div className={styles.page}>
      {/* First run happens outside the shell, so this screen carries the
          signed-in identity itself. */}
      <header className={styles.publicBar}>
        <span className={styles.brandMark}>{t("brand.name")}</span>
        {user && <span className={styles.meta}>{user.display_name}</span>}
        <button type="button" className={styles.ghost} onClick={onLogout}>
          {t("header.signOut")}
        </button>
      </header>
      <TopBar title={t("workspace.createTitle")} />
      <div className={styles.center}>
        <form
          className={styles.stack}
          onSubmit={(event) => {
            event.preventDefault();
            const trimmed = name.trim();
            if (!trimmed || create.isPending) return;
            create.mutate(
              { body: { name: trimmed } },
              {
                onSuccess: (workspace) => {
                  rememberWorkspace(workspace.id);
                  queryClient.setQueryData(
                    api.queryOptions("get", "/api/v1/workspaces").queryKey,
                    (current: Workspace[] | undefined) =>
                      current?.some((item) => item.id === workspace.id)
                        ? current
                        : [...(current ?? []), workspace],
                  );
                  void navigate(`/w/${workspace.id}`);
                },
              },
            );
          }}
        >
          <h1>{t("workspace.createTitle")}</h1>
          <p className={styles.sub}>{t("workspace.createHint")}</p>
          <label className={styles.label}>
            {t("workspace.name")}
            <input
              className={styles.input}
              value={name}
              onChange={(event) => setName(event.target.value)}
              autoFocus
              aria-label={t("workspace.name")}
            />
          </label>
          <button
            className={styles.primary}
            type="submit"
            disabled={!name.trim() || create.isPending}
          >
            {t("workspace.submit")}
          </button>
          {create.isError && (
            <p className={styles.alert} role="alert">
              {create.error instanceof Error
                ? create.error.message
                : t("common.error")}
            </p>
          )}
        </form>
      </div>
    </div>
  );
}
