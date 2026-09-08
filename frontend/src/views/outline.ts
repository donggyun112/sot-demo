export type Heading = { id: string; title: string; depth: number };

/**
 * A citation anchors on the line an edit ADDED, which for a section is the
 * markdown heading — hashes and all. The outline strips those. Compare the
 * claim, not the syntax, or every section reads as unsupported.
 */
export function claimKey(text: string): string {
  return text.replace(/^#{1,6}\s+/, "").trim();
}

export type Passage = Heading & { text: string };

/**
 * The document as the passages it is made of: each heading and the prose
 * under it, in order. An update lands on a passage, so a passage is what a
 * reader points at when asking where a decision came from.
 */
export function passagesFrom(content: string): Passage[] {
  const lines = content.split("\n");
  const passages: Passage[] = [];
  let current: Passage | null = null;
  let index = 0;
  for (const line of lines) {
    const heading = /^(#{1,6})\s+(.+)$/.exec(line);
    if (heading) {
      if (current) passages.push(current);
      current = {
        id: `h-${index++}`,
        title: heading[2].trim(),
        depth: heading[1].length,
        text: line,
      };
      continue;
    }
    if (!current) {
      if (!line.trim()) continue;
      current = { id: "body", title: "", depth: 1, text: line };
      continue;
    }
    current.text += `\n${line}`;
  }
  if (current) passages.push(current);
  return passages;
}

export function headingsFrom(content: string): Heading[] {
  const found = [...content.matchAll(/^(#{1,6})\s+(.+)$/gm)].map((match, index) => ({
    id: `h-${index}`,
    title: match[2].trim(),
    depth: match[1].length,
  }));
  return found.length > 0 ? found : [{ id: "body", title: "", depth: 1 }];
}
