import { expect, it } from "vitest";
import { readableJson } from "./readableJson";

it("prints the lines of a multi-line value as lines", () => {
  // The most important thing in a tool record is the text an edit adds, and
  // JSON.stringify writes it out as one line with \n spelled into it.
  const payload = { edits: [{ find: "", replace: "## 문제 정의\n토큰이 샌다." }] };

  const shown = readableJson(payload);

  expect(shown).toContain("## 문제 정의\n");
  expect(shown).not.toContain("\\n");
  expect(shown.split("\n").length).toBeGreaterThan(4);
});

it("leaves everything else reading as JSON", () => {
  expect(readableJson({ status: "open", branchVersion: 4 })).toBe(
    '{\n  "status": "open",\n  "branchVersion": 4\n}',
  );
  expect(readableJson([])).toBe("[]");
  expect(readableJson({})).toBe("{}");
  expect(readableJson(null)).toBe("null");
  expect(readableJson("one line")).toBe('"one line"');
});

it("indents a wrapped value to the depth it sits at", () => {
  const shown = readableJson({ a: { b: "x\ny" } });
  // The continuation lines up under the value, not against the margin.
  expect(shown).toBe('{\n  "a": {\n    "b": "x\n      y"\n  }\n}');
});
