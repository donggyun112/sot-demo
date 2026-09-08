import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate, useParams } from "react-router";
import { lastWorkspace, useSot, useWorkspaceUiOptional } from "../app/sot";
import { MarkdownBody } from "../components/MarkdownBody";
import styles from "./product.module.css";

export function TossView() {
  const { t } = useTranslation();
  const { shareToken = "" } = useParams();
  const { api, user } = useSot();
  const ui = useWorkspaceUiOptional();
  const navigate = useNavigate();
  // Sharing is usually within the workspace you are already in, so default to
  // the one you came from rather than the first in the list.
  const remembered = lastWorkspace();
  const [destination, setDestination] = useState(
    ui?.workspaces.find((item) => item.id === remembered)?.id ??
      ui?.workspaces[0]?.id ??
      "",
  );
  const [sheet, setSheet] = useState(false);
  const toss = api.useQuery("get", "/api/v1/tosses/{token}", {
    params: { path: { token: shareToken } },
  });
  const fork = api.useMutation(
    "post",
    "/api/v1/workspaces/{workspace_id}/tosses/{token}/fork",
  );
  const items = toss.data?.items ?? [];
  return (
    <div className={styles.page}>
      {/* Public route: no workspace chrome, only the mark and the way back in. */}
      <header className={styles.publicBar}>
        <Link className={styles.brandMark} to={user ? "/" : "/login"}>
          {t("brand.name")}
        </Link>
        {user ? (
          <Link className={styles.ghost} to="/">
            {t("nav.openApp")}
          </Link>
        ) : (
          <Link className={styles.ghost} to="/login">
            {t("toss.signIn")}
          </Link>
        )}
      </header>
      <div className={styles.center}>
        <div className={styles.stack}>
          <h1>{t("toss.title")}</h1>
          {toss.data?.title && <p className={styles.sub}>{toss.data.title}</p>}

          {toss.isLoading && <p className={styles.empty}>{t("common.loading")}</p>}
          {toss.isError && (
            <p className={styles.alert} role="alert">
              {t("toss.notFound")}
            </p>
          )}
          {toss.isSuccess && items.length === 0 && (
            <p className={styles.empty}>{t("toss.empty")}</p>
          )}

          {items.map((item, index) => (
            <div key={index} className={styles.row}>
              <MarkdownBody text={item.content} />
            </div>
          ))}

          {items.length > 0 && (
            <div className={styles.toolbar}>
              {user ? (
                <button
                  className={styles.primary}
                  type="button"
                  disabled={!ui?.workspaces.length}
                  onClick={() => setSheet(true)}
                >
                  {t("toss.fork")}
                </button>
              ) : (
                <Link className={styles.primary} to="/login">
                  {t("toss.signIn")}
                </Link>
              )}
            </div>
          )}

          {fork.isError && (
            <p className={styles.alert} role="alert">
              {fork.error instanceof Error ? fork.error.message : t("common.error")}
            </p>
          )}
        </div>
      </div>

      {sheet && (
        <div className={styles.overlay}>
          <form
            className={styles.sheet}
            onSubmit={(event) => {
              event.preventDefault();
              if (!destination) return;
              fork.mutate(
                {
                  params: { path: { workspace_id: destination, token: shareToken } },
                  body: {},
                },
                {
                  onSuccess: (result) => {
                    setSheet(false);
                    void navigate(`/w/${destination}/sessions/${result.session_id}`);
                  },
                },
              );
            }}
          >
            <h2>{t("toss.fork")}</h2>
            <label className={styles.label}>
              {t("toss.destination")}
              <select
                className={styles.select}
                value={destination}
                onChange={(event) => setDestination(event.target.value)}
              >
                {ui?.workspaces.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                  </option>
                ))}
              </select>
            </label>
            <div className={styles.sheetActions}>
              <button
                className={styles.primary}
                type="submit"
                disabled={fork.isPending}
              >
                {t("toss.confirm")}
              </button>
              <button
                className={styles.ghost}
                type="button"
                onClick={() => setSheet(false)}
              >
                {t("common.cancel")}
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
