import { chromium } from "@playwright/test";

const out =
  "/private/tmp/claude-501/-Users-dongkseo-project-sot-demo/1bd2a129-d407-488e-90ca-e46e0bc99639/scratchpad/shots";
const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 1280, height: 1400 } });
const page = await context.newPage();
page.on("pageerror", (e) => console.log("PAGEERROR", e.message));
page.on("response", (r) => {
  const u = new URL(r.url()).pathname;
  if (u.startsWith("/api/") && r.status() >= 400)
    console.log("HTTP", r.status(), r.request().method(), u);
});

await page.addInitScript(() => localStorage.setItem("sot.locale", "ko"));
await page.goto("http://localhost:3000/");
await page.getByRole("button", { name: /Google 없이|without Google/ }).click();
await page.waitForURL(/\/w\//, { timeout: 15000 });

// The user's document, by title.
const link = page.getByRole("link", { name: /API 토큰은 어떻게/ }).first();
await link.click();
await page.waitForTimeout(1500);
await page.screenshot({ path: `${out}/live-document.png`, fullPage: true });

const cited = page.locator("[data-cited]");
console.log("cited passages:", await cited.count());
for (const el of await cited.all()) {
  const heading = (await el.locator("h1,h2,h3,h4").first().textContent()) ?? "(none)";
  const link = el.getByRole("link", { name: "이 구간을 만든 세션" });
  console.log(" -", heading.trim(), "| link:", await link.count());
}

// Hover one so the way in is on screen, then follow it.
const target = cited.filter({ hasText: "감사·모니터링" }).first();
if (await target.count()) {
  await target.hover();
  await page.waitForTimeout(300);
  await page.screenshot({ path: `${out}/live-hover.png`, fullPage: true });
  await target.getByRole("link", { name: "이 구간을 만든 세션" }).click();
  await page.waitForTimeout(1500);
  console.log("landed on:", new URL(page.url()).pathname);
  await page.screenshot({ path: `${out}/live-session.png`, fullPage: true });
}
await browser.close();
