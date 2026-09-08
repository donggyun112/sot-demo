import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Navigate, useParams } from "react-router";
import { can, useSot, useWorkspaceUi } from "../app/sot";
import { useTimestamp, useWorkspaceMembers } from "../app/identity";
import { TopBar } from "../components/AppShell";
import { CopyId } from "../components/CopyId";
import { Section } from "../components/Page";
import styles from "./product.module.css";

export function MembersView() {
  const { t } = useTranslation();
  const { workspaceId = "" } = useParams();
  const queryClient = useQueryClient();
  const { api, user } = useSot();
  const { member, workspaces } = useWorkspaceUi();
  const at = useTimestamp();
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("member");
  const members = useWorkspaceMembers();
  const invitations = api.useQuery(
    "get",
    "/api/v1/workspaces/{workspace_id}/invitations",
    { params: { path: { workspace_id: workspaceId } } },
  );
  const invite = api.useMutation(
    "post",
    "/api/v1/workspaces/{workspace_id}/invitations",
  );
  const revoke = api.useMutation(
    "delete",
    "/api/v1/workspaces/{workspace_id}/invitations/{invitation_id}",
  );
  if (member && !can(member, "workspace.manage")) {
    return <Navigate to={`/w/${workspaceId}`} replace />;
  }
  const workspaceName = workspaces.find((item) => item.id === workspaceId)?.name;
  const rows = members.data ?? [];
  const pending = invitations.data ?? [];
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
            <div key={item.user_id} className={styles.row}>
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

          {/*
            An invitation is not membership: it names someone by the address
            their colleagues already know, and grants nothing until they accept.
          */}
          <h2>{t("invite.title")}</h2>
          <p className={styles.sub}>{t("invite.hint")}</p>
          <form
            onSubmit={(event) => {
              event.preventDefault();
              if (!email.trim()) return;
              invite.mutate(
                {
                  params: { path: { workspace_id: workspaceId } },
                  body: { email: email.trim(), role: role as "member" | "viewer" },
                },
                {
                  onSuccess: () => {
                    setEmail("");
                    void queryClient.invalidateQueries();
                  },
                },
              );
            }}
          >
            <label className={styles.label} htmlFor="invite-email">
              {t("invite.email")}
              <input
                id="invite-email"
                className={styles.input}
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="teammate@example.com"
              />
            </label>
            <label className={styles.label} htmlFor="invite-role">
              {t("invite.role")}
              <select
                id="invite-role"
                className={styles.select}
                value={role}
                onChange={(event) => setRole(event.target.value)}
              >
                {/* Ownership is not transferable by invitation. */}
                <option value="member">{t("workspaceRole.member")}</option>
                <option value="viewer">{t("workspaceRole.viewer")}</option>
              </select>
            </label>
            <div className={styles.toolbar}>
              <button
                className={styles.primary}
                type="submit"
                disabled={!email.trim() || invite.isPending}
              >
                {invite.isPending ? t("common.working") : t("invite.action")}
              </button>
            </div>
            {invite.isSuccess &&
              (invite.data?.code ? (
                /* Nothing carried it, so the code is what the inviter passes
                   on. It is shown once, here, and never in the listing. */
                <div className={styles.sideCard}>
                  <div className={styles.who}>{t("invite.handOver")}</div>
                  <CopyId label={t("invite.copyCode")} value={invite.data.code} />
                </div>
              ) : (
                <p className={styles.empty}>{t("invite.sent")}</p>
              ))}
            {invite.isError && (
              <p className={styles.alert} role="alert">
                {invite.error instanceof Error
                  ? invite.error.message
                  : t("common.error")}
              </p>
            )}
          </form>

          <Section title={t("invite.pending")} count={pending.length}>
            {pending.length === 0 ? (
              <p className={styles.empty}>{t("invite.noPending")}</p>
            ) : (
              pending.map((item) => (
                <div key={item.id} className={styles.row}>
                  <div>
                    <div className={styles.rowTitle}>{item.invitee_email}</div>
                    <div className={styles.meta}>
                      {t(`workspaceRole.${item.role}`)} ·{" "}
                      {t("invite.expires", { at: at(item.expires_at) })}
                    </div>
                  </div>
                  <button
                    className={styles.ghost}
                    type="button"
                    disabled={revoke.isPending}
                    onClick={() =>
                      revoke.mutate(
                        {
                          params: {
                            path: {
                              workspace_id: workspaceId,
                              invitation_id: item.id,
                            },
                          },
                        },
                        { onSuccess: () => void queryClient.invalidateQueries() },
                      )
                    }
                  >
                    {t("invite.revoke")}
                  </button>
                </div>
              ))
            )}
          </Section>
        </div>
      </div>
    </div>
  );
}
