import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link, useNavigate, useParams } from "react-router";
import { useOpenProposals } from "../app/inbox";
import { useSot } from "../app/sot";
import { useDisplayName, useTimestamp } from "../app/identity";
import { TopBar } from "../components/AppShell";
import { PageState, Section } from "../components/Page";
import { editSummary } from "./patch";
import styles from "./product.module.css";

/** What is waiting on me, and what I set in motion. */
export function InboxView() {
  const { t } = useTranslation();
  const { workspaceId = "" } = useParams();
  const { loading, waitingOnMe, mine, all } = useOpenProposals();
  const nameOf = useDisplayName();
  const at = useTimestamp();
  const { api } = useSot();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  // An invitation is not scoped to a workspace you are not in yet.
  const invitations = api.useQuery("get", "/api/v1/invitations", {});
  const accept = api.useMutation("post", "/api/v1/invitations/{invitation_id}/accept");
  const decline = api.useMutation(
    "post",
    "/api/v1/invitations/{invitation_id}/decline",
  );
  const redeem = api.useMutation("post", "/api/v1/invitations/redeem");
  const [code, setCode] = useState("");
  const pending = invitations.data ?? [];

  const row = (
    proposal: (typeof all)[number]["proposal"],
    documentTitle: string,
  ) => (
    <Link
      key={proposal.id}
      className={styles.row}
      to={`/w/${workspaceId}/proposals/${proposal.id}`}
    >
      <div>
        <div className={styles.rowTitle}>
          {editSummary(proposal.current_version.edits).slice(0, 70) ||
            t("proposal.title")}
        </div>
        <div className={styles.meta}>
          {documentTitle} · {nameOf(proposal.created_by)} ·{" "}
          {at(proposal.created_at)}
        </div>
      </div>
      <span
        className={styles.chip}
        data-tone={proposal.status === "approved" ? "ok" : undefined}
      >
        {proposal.approvals.filter((a) => a.version === proposal.version).length}
        {"/"}
        {proposal.current_version.required_approver_ids.length}
      </span>
    </Link>
  );

  return (
    <>
      <TopBar title={t("nav.inbox")} />
      <div className={styles.center}>
        <div className={styles.stack}>
          {loading && <PageState title={t("common.loading")} />}

          {pending.length > 0 && (
            <Section title={t("invite.waiting")} count={pending.length}>
              {pending.map((item) => (
                <div key={item.id} className={styles.row}>
                  <div>
                    <div className={styles.rowTitle}>{item.workspace_name}</div>
                    <div className={styles.meta}>
                      {t("invite.from", { name: item.inviter_display_name })} ·{" "}
                      {t(`workspaceRole.${item.role}`)} ·{" "}
                      {t("invite.expires", { at: at(item.expires_at) })}
                    </div>
                  </div>
                  <div className={styles.turnActions}>
                    <button
                      className={styles.primary}
                      type="button"
                      disabled={accept.isPending}
                      onClick={() =>
                        accept.mutate(
                          { params: { path: { invitation_id: item.id } } },
                          {
                            onSuccess: (joined) => {
                              void queryClient.invalidateQueries();
                              void navigate(`/w/${joined.workspace_id}`);
                            },
                          },
                        )
                      }
                    >
                      {t("invite.accept")}
                    </button>
                    <button
                      className={styles.ghost}
                      type="button"
                      disabled={decline.isPending}
                      onClick={() =>
                        decline.mutate(
                          { params: { path: { invitation_id: item.id } } },
                          { onSuccess: () => void queryClient.invalidateQueries() },
                        )
                      }
                    >
                      {t("invite.decline")}
                    </button>
                  </div>
                </div>
              ))}
            </Section>
          )}

          {!loading && all.length === 0 && pending.length === 0 && (
            <PageState
              title={t("inbox.emptyTitle")}
              description={t("inbox.empty")}
            />
          )}

          {/* An invitation that reached you by hand rather than by mail. */}
          <Section title={t("invite.haveCode")}>
            <form
              onSubmit={(event) => {
                event.preventDefault();
                if (!code.trim()) return;
                redeem.mutate(
                  { body: { code: code.trim().toUpperCase() } },
                  {
                    onSuccess: (joined) => {
                      setCode("");
                      void queryClient.invalidateQueries();
                      void navigate(`/w/${joined.workspace_id}`);
                    },
                  },
                );
              }}
            >
              <label className={styles.label} htmlFor="invite-code">
                {t("invite.code")}
                <input
                  id="invite-code"
                  className={styles.input}
                  value={code}
                  onChange={(event) => setCode(event.target.value)}
                  placeholder="ABCD234XYZ"
                />
              </label>
              <button
                className={styles.primary}
                type="submit"
                disabled={code.trim().length !== 10 || redeem.isPending}
              >
                {t("invite.join")}
              </button>
              {redeem.isError && (
                <p className={styles.alert} role="alert">
                  {t("invite.badCode")}
                </p>
              )}
            </form>
          </Section>

          {waitingOnMe.length > 0 && (
            <Section title={t("inbox.waiting")} count={waitingOnMe.length}>
              {waitingOnMe.map((item) => row(item.proposal, item.documentTitle))}
            </Section>
          )}

          {mine.length > 0 && (
            <Section title={t("inbox.mine")} count={mine.length}>
              {mine.map((item) => row(item.proposal, item.documentTitle))}
            </Section>
          )}
        </div>
      </div>
    </>
  );
}
