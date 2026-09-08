import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router";
import { useOpenProposals } from "../app/inbox";
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

          {!loading && all.length === 0 && (
            <PageState
              title={t("inbox.emptyTitle")}
              description={t("inbox.empty")}
            />
          )}

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
