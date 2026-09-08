/**
 * JSON for reading, where the values are prose.
 *
 * `JSON.stringify` escapes the newlines inside a string, so an edit whose
 * `replace` is a section of the document arrives as one unbroken line with
 * `\n` written out in it — the least readable form of the most important
 * thing in the record. Multi-line strings are printed as the lines they are;
 * everything else is printed as JSON.
 */
const INDENT = "  ";

export function readableJson(value: unknown, depth = 0): string {
  const pad = INDENT.repeat(depth);
  const inner = INDENT.repeat(depth + 1);
  if (typeof value === "string" && value.includes("\n"))
    /* The quotes stay, so it still reads as a value and not as a heading. */
    return `"${value.split("\n").join(`\n${inner}`)}"`;
  if (Array.isArray(value)) {
    if (value.length === 0) return "[]";
    const items = value.map((item) => inner + readableJson(item, depth + 1));
    return `[\n${items.join(",\n")}\n${pad}]`;
  }
  if (value && typeof value === "object") {
    const entries = Object.entries(value);
    if (entries.length === 0) return "{}";
    const lines = entries.map(
      ([key, item]) =>
        `${inner}${JSON.stringify(key)}: ${readableJson(item, depth + 1)}`,
    );
    return `{\n${lines.join(",\n")}\n${pad}}`;
  }
  return JSON.stringify(value) ?? "null";
}
