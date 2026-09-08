import { expect, it } from "vitest";
import { editPatch, editSummary } from "./patch";

it("renders one hunk per edit and leaves untouched lines out of it", () => {
  expect(
    editPatch([
      { find: "초기 합의", replace: "새 합의" },
      { find: "", replace: "## 근거\n세션에서 인용" },
    ]),
  ).toEqual([
    { kind: "del", text: "초기 합의" },
    { kind: "add", text: "새 합의" },
    { kind: "ctx", text: "" },
    { kind: "add", text: "## 근거" },
    { kind: "add", text: "세션에서 인용" },
  ]);
});

it("summarises a proposal by the first line it actually adds", () => {
  expect(
    editSummary([
      { find: "지운다", replace: "" },
      { find: "", replace: "## 저장소 선택\n결정: Postgres" },
    ]),
  ).toBe("## 저장소 선택");
});
