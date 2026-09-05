import { expect, test } from "@playwright/test";

test("Alice and Bob publish a cited revision through the complete SOT path", async ({
  page,
}) => {
  const suffix = Date.now().toString(36);
  const sessionTitle = `격리 검토 ${suffix}`;
  const citeSummary = `프로세스 격리 선택 ${suffix}`;
  const proposal = `각 사용자 작업은 별도 프로세스로 격리한다. ${suffix}`;

  await page.goto("/");
  const revisionLabel = page.getByText(/MAIN · REVISION \d+/);
  await expect(revisionLabel).toBeVisible();
  const initialRevision = Number((await revisionLabel.textContent())?.match(/\d+/)?.[0]);

  await page.getByRole("button", { name: "새 세션" }).click();
  await page.getByLabel("세션 제목").fill(sessionTitle);
  await page.getByRole("button", { name: "세션 만들기" }).click();
  await expect(page.getByRole("heading", { name: `세션 · ${sessionTitle}` })).toBeVisible();

  const chatInput = page.getByPlaceholder("주장을 검토하거나 대안을 요청하세요");
  await chatInput.fill("사용자별 작업 격리 방식을 검토해줘");
  await chatInput.press("Enter");
  await expect(page.getByRole("checkbox").first()).toBeVisible({ timeout: 30_000 });

  for (const checkbox of await page.getByRole("checkbox").all()) {
    await checkbox.check();
  }
  await page.getByLabel("인용 요약").fill(citeSummary);
  await page.getByRole("button", { name: "Cite 만들기" }).click();
  await page.getByRole("button", { name: "Toss 만들기" }).click();
  await expect(page.getByText("PUBLIC TOSS")).toBeVisible();
  await expect(page.getByRole("heading", { name: citeSummary })).toBeVisible();

  await page.getByLabel("작업자").selectOption("bob");
  await page.getByRole("button", { name: "Bob으로 fork" }).click();
  await expect(page.getByText("BOB BRANCH", { exact: false })).toBeVisible();

  await page.getByLabel("제안 본문").fill(proposal);
  await page.getByRole("button", { name: "Proposal 만들기" }).click();
  await expect(page.getByText(proposal)).toBeVisible();
  await page.getByRole("button", { name: "승인" }).click();
  await expect(page.getByRole("status")).toContainText("1/2 승인");

  await page.getByLabel("작업자").selectOption("alice");
  const bobBranch = await page
    .getByLabel("Branch")
    .locator("option", { hasText: "bob" })
    .getAttribute("value");
  expect(bobBranch).not.toBeNull();
  await page.getByLabel("Branch").selectOption(bobBranch!);
  await page.getByRole("button", { name: "승인" }).click();
  await expect(page.getByRole("status")).toContainText(`revision ${initialRevision + 1}`);

  await page.getByRole("button", { name: "요청 제한 토큰" }).click();
  await expect(page.getByText(proposal)).toBeVisible();
  await expect(page.getByLabel("Main revision provenance")).toContainText(citeSummary);
});
