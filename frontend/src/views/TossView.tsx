import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate, useParams } from "react-router";
import { lastWorkspace, useSot, useWorkspaceUiOptional } from "../app/sot";
import { titleFromTurns, useTimestamp } from "../app/identity";
import { Section } from "../components/Page";
import { Transcript } from "../components/Turn";
import styles from "./product.module.css";

export function TossView() {
  const { t } = useTranslation();
  const { shareToken = "" } = useParams();
  const { api, user } = useSot();
  const ui = useWorkspaceUiOptional();
  const navigate = useNavigate();
  const at = useTimestamp();
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
  const attribution = toss.data?.attribution;
  const title = titleFromTurns(items, toss.data?.title || t("toss.untitled"));
  // A link carries one shared session today. It is still listed rather than
  // assumed, so the reader sees WHAT was shared before reading it.
  const [open, setOpen] = useState(true);

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

      {toss.isLoading ? (
        <div className={styles.center}>
          <p className={styles.empty}>{t("common.loading")}</p>
        </div>
      ) : toss.isError ? (
        <div className={styles.center}>
          <p className={styles.alert} role="alert">
            {t("toss.notFound")}
          </p>
        </div>
      ) : (
        /* A shared link is a shared session, so it is read the way a session
           is read: what was shared on the side, the conversation in the middle. */
        <div className={styles.session}>
          <div className={styles.thread}>
            <div className={styles.threadHead}>
              <span className={styles.threadTitle}>{title}</span>
              <span className={styles.chip} data-tone="accent">
                {t("sessions.shared")}
              </span>
              <span className={styles.chip}>
                {t("sessions.turnCount", { count: items.length })}
              </span>
              {attribution && (
                <span className={styles.meta}>
                  {attribution.author_display_name}
                </span>
              )}
            </div>
            <p className={styles.banner}>{t("toss.readOnly")}</p>
            {items.length === 0 ? (
              <div className={styles.center}>
                <p className={styles.empty}>{t("toss.empty")}</p>
              </div>
            ) : (
              <div className={styles.publicThread}>
                <Transcript
                  turns={items}
                  youLabel={attribution?.author_display_name ?? t("people.someone")}
                  agentLabel={t("agent.name")}
                />
              </div>
            )}
          </div>

          <aside className={styles.side} data-open="true">
            <Section title={t("sessions.title")} count={1}>
              <button
                type="button"
                className={styles.row}
                data-on={open ? "true" : "false"}
                onClick={() => setOpen(true)}
              >
                <div>
                  <div className={styles.rowTitle}>{title}</div>
                  <div className={styles.meta}>
                    {attribution
                      ? `${attribution.author_display_name} · ${at(attribution.published_at)}`
                      : t("people.unknown")}
                  </div>
                </div>
                <span className={styles.chip}>
                  {t("sessions.turnCount", { count: items.length })}
                </span>
              </button>
            </Section>

            <Section title={t("toss.continue")}>
              <p className={styles.note}>{t("toss.createHint")}</p>
              {user ? (
                <button
                  className={styles.primary}
                  type="button"
                  disabled={!ui?.workspaces.length || items.length === 0}
                  onClick={() => setSheet(true)}
                >
                  {t("toss.fork")}
                </button>
              ) : (
                <Link className={styles.primary} to="/login">
                  {t("toss.signIn")}
                </Link>
              )}
              {fork.isError && (
                <p className={styles.alert} role="alert">
                  {fork.error instanceof Error
                    ? fork.error.message
                    : t("common.error")}
                </p>
              )}
            </Section>
          </aside>
        </div>
      )}

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
