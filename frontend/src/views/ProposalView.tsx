import { useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router";
import { can, useSot, useWorkspaceUi } from "../app/sot";
import { ordinalLabel, useDisplayName } from "../app/identity";
import { TopBar } from "../components/AppShell";
import { MarkdownBody } from "../components/MarkdownBody";
import { editPatch } from "./patch";
import styles from "./product.module.css";

export function ProposalView() {
  const { t } = useTranslation();
  const { workspaceId = "", proposalId = "" } = useParams();
  const { api } = useSot();
  const { member } = useWorkspaceUi();
  const nameOf = useDisplayName();
  const queryClient = useQueryClient();
  const refresh = () => void queryClient.invalidateQueries();
  const proposal = api.useQuery(
    "get",
    "/api/v1/workspaces/{workspace_id}/proposals/{proposal_id}",
    { params: { path: { workspace_id: workspaceId, proposal_id: proposalId } } },
  );
  const decide = api.useMutation(
    "post",
    "/api/v1/workspaces/{workspace_id}/proposals/{proposal_id}/decisions",
  );
  const merge = api.useMutation(
    "post",
    "/api/v1/workspaces/{workspace_id}/proposals/{proposal_id}/merge",
  );
  const data = proposal.data;
  const version = data?.current_version;
  const document = api.useQuery(
    "get",
    "/api/v1/workspaces/{workspace_id}/documents/{document_id}",
    {
      params: {
        path: {
          workspace_id: workspaceId,
          document_id: data?.document_id ?? "pending",
        },
      },
    },
    { enabled: Boolean(data?.document_id) },
  );
  const patch = editPatch(version?.edits ?? []);
  /** Bundle ids are opaque; number them in first-seen order instead. */
  const bundleOrder = [
    ...new Set((version?.citations ?? []).map((item) => item.bundle_id)),
  ];
  const failure = [decide.error, merge.error].find(Boolean);
  return (
    <div className={styles.page}>
      <TopBar title={t("proposal.title")} />
      <div className={styles.center}>
        <div className={styles.stack}>
          <h1>{t("proposal.title")}</h1>

          {proposal.isLoading && <p className={styles.empty}>{t("common.loading")}</p>}
          {proposal.isError && (
            <p className={styles.alert} role="alert">
              {t("proposal.notFound")}
            </p>
          )}

          {data && version && (
            <>
              <div className={styles.chips}>
                <span
                  className={styles.chip}
                  data-tone={
                    data.status === "merged"
                      ? "ok"
                      : data.status === "rejected"
                        ? "danger"
                        : "accent"
                  }
                >
                  {t(`proposalStatus.${data.status}`)}
                </span>
                <span className={styles.chip}>
                  {t("proposal.version")} {version.version}
                </span>
              </div>

              <h2>{t("proposal.patch")}</h2>
              <pre className={styles.patch}>
                {patch.map((line, index) => (
                  <div key={`${line.kind}-${index}`} data-kind={line.kind}>
                    {line.kind === "add" ? "+" : line.kind === "del" ? "-" : " "}
                    {line.text}
                  </div>
                ))}
              </pre>

              <h2>{t("proposal.citations")}</h2>
              {version.citations.length === 0 ? (
                <p className={styles.empty}>{t("proposal.noCitations")}</p>
              ) : (
                /*
                  An ordinal on its own — "bundle 1, item 6" — tells a reader
                  nothing, so each claim leads back to the conversation the
                  update was written in.
                */
                version.citations.map((item) => (
                  <Link
                    key={`${item.bundle_id}-${item.bundle_item_position}`}
                    className={styles.row}
                    title={item.bundle_id}
                    to={`/w/${workspaceId}/sessions/${data.source_session_id}`}
                  >
                    <div>
                      <div className={styles.rowTitle}>{item.claim_anchor}</div>
                      <div className={styles.meta}>
                        {t("document.citation", {
                          bundle: ordinalLabel(
                            t("proposal.bundle"),
                            bundleOrder.indexOf(item.bundle_id),
                          ),
                          position: item.bundle_item_position + 1,
                        })}
                      </div>
                    </div>
                    <span className={styles.chip}>
                      {t("document.historyOpenSession")}
                    </span>
                  </Link>
                ))
              )}

              <h2>{t("proposal.approvers")}</h2>
              <div className={styles.chips}>
                {version.required_approver_ids.map((id) => (
                  <span key={id} className={styles.chip} title={id}>
                    {nameOf(id)}
                  </span>
                ))}
              </div>

              <h2>{t("proposal.decisions")}</h2>
              {data.approvals.length === 0 ? (
                <p className={styles.empty}>{t("proposal.noDecisions")}</p>
              ) : (
                data.approvals.map((item) => (
                  <div
                    key={`${item.approver_user_id}-${item.version}`}
                    className={styles.row}
                    title={item.approver_user_id}
                  >
                    <div>
                      <div className={styles.rowTitle}>
                        {nameOf(item.approver_user_id)}
                      </div>
                      <div className={styles.meta}>
                        {t("proposal.version")} {item.version}
                      </div>
                    </div>
                    <span
                      className={styles.chip}
                      data-tone={item.decision === "approve" ? "ok" : "danger"}
                    >
                      {item.decision}
                    </span>
                  </div>
                ))
              )}

              {failure && (
                <p className={styles.alert} role="alert">
                  {failure instanceof Error ? failure.message : t("common.error")}
                </p>
              )}

              <div className={styles.toolbar}>
                {can(member, "session.participate") && data.status === "open" && (
                  <>
                    <button
                      className={styles.primary}
                      type="button"
                      disabled={decide.isPending}
                      onClick={() =>
                        decide.mutate(
                          {
                            params: {
                              path: {
                                workspace_id: workspaceId,
                                proposal_id: proposalId,
                              },
                            },
                            body: {
                              decision: "approve",
                              expected_version: data.version,
                            },
                          },
                          { onSuccess: refresh },
                        )
                      }
                    >
                      {t("proposal.approve")}
                    </button>
                    <button
                      className={styles.ghost}
                      type="button"
                      disabled={decide.isPending}
                      onClick={() =>
                        decide.mutate(
                          {
                            params: {
                              path: {
                                workspace_id: workspaceId,
                                proposal_id: proposalId,
                              },
                            },
                            body: {
                              decision: "reject",
                              expected_version: data.version,
                            },
                          },
                          { onSuccess: refresh },
                        )
                      }
                    >
                      {t("proposal.reject")}
                    </button>
                  </>
                )}
                {can(member, "document.publish") && data.status === "approved" && (
                  <button
                    className={styles.primary}
                    type="button"
                    disabled={merge.isPending}
                    onClick={() =>
                      merge.mutate(
                        {
                          params: {
                            path: {
                              workspace_id: workspaceId,
                              proposal_id: proposalId,
                            },
                          },
                          body: { expected_version: data.version },
                        },
                        { onSuccess: refresh },
                      )
                    }
                  >
                    {t("proposal.merge")}
                  </button>
                )}
                <span className={styles.spacer} />
                <Link
                  className={styles.ghost}
                  to={`/w/${workspaceId}/documents/${data.document_id}`}
                >
                  {t("header.document")}
                </Link>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
