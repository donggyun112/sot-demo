export type Heading = { id: string; title: string; depth: number };

export function headingsFrom(content: string): Heading[] {
  const found = [...content.matchAll(/^(#{1,6})\s+(.+)$/gm)].map((match, index) => ({
    id: `h-${index}`,
    title: match[2].trim(),
    depth: match[1].length,
  }));
  return found.length > 0 ? found : [{ id: "body", title: "", depth: 1 }];
}
