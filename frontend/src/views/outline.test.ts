import { expect, it } from "vitest";
import { claimKey, headingsFrom } from "./outline";

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
