import { expect, test } from "@playwright/test";

const shots = "/private/tmp/claude-501/-Users-dongkseo-project-sot-demo/1bd2a129-d407-488e-90ca-e46e0bc99639/scratchpad/shots";

test("the Korean hero wraps between words, never inside one", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.addInitScript(() => localStorage.setItem("sot.locale", "ko"));
  await page.goto("/");
  const heading = page.getByRole("heading", { level: 1 });
  await expect(heading).toBeVisible();

  // This spec compiles in the Node project, which has no DOM lib, so the
  // browser globals are reached through globalThis rather than typed here.
  const breaks = await heading.evaluate((el) => {
    const dom = globalThis as unknown as {
      document: { createRange(): Range };
    };
    type Range = {
      setStart(node: unknown, offset: number): void;
      setEnd(node: unknown, offset: number): void;
      getBoundingClientRect(): { top: number };
    };
    const node = el.firstChild as unknown as { textContent: string | null };
    const text = node.textContent ?? "";
    const range = dom.document.createRange();
    const at: number[] = [];
    let top: number | null = null;
    for (let i = 0; i < text.length; i++) {
      range.setStart(node, i);
      range.setEnd(node, i + 1);
      const y = range.getBoundingClientRect().top;
      if (top === null) top = y;
      else if (y > top + 1) {
        at.push(i);
        top = y;
      }
    }
    return at.map((i) => ({ before: text[i - 1], after: text[i] }));
  });

  expect(breaks.length).toBeGreaterThan(0);
  for (const point of breaks) {
    expect(`${point.before}|${point.after}`).toMatch(/\s\||\|\s/);
  }
  await page.screenshot({ path: `${shots}/hero.png` });

  // The local entry actually signs you in.
  await page.getByRole("button", { name: "Google 없이 계속하기" }).click();
  await expect(page).toHaveURL(/\/(w|workspaces)\//);
});
