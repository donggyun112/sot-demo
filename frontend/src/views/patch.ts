export type PatchLine = { kind: "ctx" | "add" | "del"; text: string };
export type DocumentEdit = { find: string; replace: string };

/**
 * One hunk per edit: the text it replaces, then the text it puts there.
 *
 * A proposal is a set of anchored edits, so the diff is exactly what the agent
 * wrote — not a guess made by comparing two whole documents, which reported
 * every untouched line as removed and re-added.
 */
export function editPatch(edits: readonly DocumentEdit[]): PatchLine[] {
  const lines: PatchLine[] = [];
  edits.forEach((edit, index) => {
    if (index > 0) lines.push({ kind: "ctx", text: "" });
    if (edit.find)
      for (const text of edit.find.split("\n")) lines.push({ kind: "del", text });
    for (const text of edit.replace.split("\n")) lines.push({ kind: "add", text });
  });
  return lines;
}

/** The first line a proposal adds, for list rows that need one line. */
export function editSummary(edits: readonly DocumentEdit[]): string {
  const first = edits.find((edit) => edit.replace.trim());
  return (first?.replace ?? "").split("\n")[0].trim();
}
