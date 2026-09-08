export type Heading = { id: string; title: string; depth: number };

/**
 * A citation anchors on the line an edit ADDED, which for a section is the
 * markdown heading — hashes and all. The outline strips those. Compare the
 * claim, not the syntax, or every section reads as unsupported.
 */
export function claimKey(text: string): string {
  return text.replace(/^#{1,6}\s+/, "").trim();
}

export function headingsFrom(content: string): Heading[] {
  const found = [...content.matchAll(/^(#{1,6})\s+(.+)$/gm)].map((match, index) => ({
    id: `h-${index}`,
    title: match[2].trim(),
    depth: match[1].length,
  }));
  return found.length > 0 ? found : [{ id: "body", title: "", depth: 1 }];
}
