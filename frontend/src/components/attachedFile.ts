/**
 * A file someone brought into a conversation, as a reader needs to see it.
 *
 * The turn stores the name, a blank line, then the file. Printing that put a
 * hundred lines of someone else's YAML in the middle of the transcript, so
 * the transcript shows the file: its name, how long it is, and what kind it
 * is. The whole text is still what the agent reads.
 */
export interface AttachedFile {
  name: string;
  lines: number;
  /** Uppercased extension, for the badge. Empty when the name has none. */
  kind: string;
}

export function fileKind(name: string): string {
  const dot = name.lastIndexOf(".");
  /* A leading dot is the whole name of a dotfile, not an extension. */
  if (dot <= 0) return "";
  return name.slice(dot + 1).toUpperCase();
}

export function countLines(text: string): number {
  if (!text) return 0;
  /* A trailing newline ends the last line, it does not start another. */
  return text.replace(/\n$/, "").split("\n").length;
}

/** Splits an attachment turn back into the file it was. */
export function attachedFile(content: string): AttachedFile {
  const [name = "", body = ""] = splitOnce(content);
  return { name, lines: countLines(body), kind: fileKind(name) };
}

/**
 * The name is the first line and the file is everything after the blank line
 * that follows it. A file whose own first line is blank keeps it.
 */
function splitOnce(content: string): [string, string] {
  const at = content.indexOf("\n\n");
  if (at === -1) return [content.trim(), ""];
  return [content.slice(0, at).trim(), content.slice(at + 2)];
}
