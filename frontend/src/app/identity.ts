import { useTranslation } from "react-i18next";
import { useParams } from "react-router";
import { useSot } from "./sot";

/** Workspace roster, so ids can be rendered as the names people recognise. */
export function useWorkspaceMembers() {
  const { api } = useSot();
  const { workspaceId = "" } = useParams();
  return api.useQuery(
    "get",
    "/api/v1/workspaces/{workspace_id}/members",
    { params: { path: { workspace_id: workspaceId } } },
    { enabled: Boolean(workspaceId) },
  );
}

/**
 * Resolves a user id to a name. Self reads as "You"; everyone else comes from
 * the workspace roster. A raw UUID is never a fallback.
 */
export function useDisplayName() {
  const { t } = useTranslation();
  const { user } = useSot();
  const members = useWorkspaceMembers();
  const byId = new Map(
    (members.data ?? []).map((item) => [item.user_id, item.display_name]),
  );
  return (userId: string | null | undefined) => {
    if (!userId) return t("people.unknown");
    if (user && userId === user.id) return t("people.you");
    return byId.get(userId) ?? t("people.someone");
  };
}

/** Absolute timestamp — sessions have no title, so this is the row identity. */
export function useTimestamp() {
  const { i18n } = useTranslation();
  return (iso: string | null | undefined) => {
    if (!iso) return "";
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return "";
    return new Intl.DateTimeFormat(i18n.language, {
      dateStyle: "medium",
      timeStyle: "short",
    }).format(date);
  };
}

/** First line of the first human turn, used as a session title. */
export function titleFromTurns(
  turns: { role: string; content: string }[],
  fallback: string,
) {
  const first = turns.find((turn) => turn.role === "user" && turn.content.trim());
  if (!first) return fallback;
  const line = first.content.trim().split("\n")[0].replace(/^#+\s*/, "");
  return line.length > 60 ? `${line.slice(0, 59)}…` : line;
}

/** Ordinal label for opaque ids (bundles) that users never type. */
export function ordinalLabel(prefix: string, index: number) {
  return `${prefix} ${index + 1}`;
}
