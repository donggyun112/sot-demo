import { expect, it } from "vitest";
import { claimKey, headingsFrom, passagesFrom } from "./outline";

it("reads a citation anchor and an outline heading as the same claim", () => {
  // The backend anchors on the line the edit ADDED, which for a section is the
  // markdown heading, hashes and all. The outline strips them. Comparing the
  // two verbatim made every section read as unsupported.
  const anchor = "## 감사·모니터링";
  const [heading] = headingsFrom("# 문서\n\n## 감사·모니터링\n\n본문").slice(1);

  expect(heading.title).toBe("감사·모니터링");
  expect(anchor).not.toBe(heading.title);
  expect(claimKey(anchor)).toBe(claimKey(heading.title));
});

it("leaves a claim that is not a heading alone", () => {
  expect(claimKey("계정당 초당 10회로 한다.")).toBe("계정당 초당 10회로 한다.");
});

it("splits a document into the passages an update lands on", () => {
  const passages = passagesFrom(
    "머리말\n\n## 문제 정의\n토큰이 샌다.\n\n## 감사·모니터링\n이력을 남긴다.",
  );

  expect(passages.map((one) => one.title)).toEqual([
    "",
    "문제 정의",
    "감사·모니터링",
  ]);
  // A passage keeps its own heading, so it renders as itself.
  expect(passages[1].text.trim()).toBe("## 문제 정의\n토큰이 샌다.");
  expect(passages[2].text.trim()).toBe("## 감사·모니터링\n이력을 남긴다.");
  expect(passages[0].text.trim()).toBe("머리말");
});

it("keeps a document with no headings as one passage", () => {
  const passages = passagesFrom("계정당 초당 10회로 한다.");
  expect(passages).toHaveLength(1);
  expect(passages[0].title).toBe("");
});
