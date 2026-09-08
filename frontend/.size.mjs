import { chromium } from "@playwright/test";
const b = await chromium.launch();
const c = await b.newContext({ viewport: { width: 1400, height: 950 } });
const p = await c.newPage();
await p.goto("http://localhost:3000/");
await p.getByRole("button", { name: /Google 없이|without Google/ }).first().click();
await p.waitForURL(/\/w\//, { timeout: 15000 });
await p.waitForTimeout(1200);
await p.getByRole("link", { name: /^DESIGN$/ }).first().click();
await p.waitForTimeout(2500);
const info = await p.evaluate(() => {
  const wanted = ["version: alpha", "spacing:", "components:", "typography:", "rounded:"];
  const out = [];
  for (const el of document.querySelectorAll("main *")) {
    const t = (el.textContent ?? "").trimStart();
    if (!wanted.some((w) => t.startsWith(w))) continue;
    if (el.children.length && el.firstElementChild?.textContent?.trimStart()?.startsWith(wanted.find((w) => t.startsWith(w)))) continue;
    const cs = getComputedStyle(el);
    out.push({
      tag: el.tagName,
      cls: el.className?.toString().slice(0, 60),
      size: cs.fontSize,
      weight: cs.fontWeight,
      family: cs.fontFamily.slice(0, 30),
      head: t.replace(/\s+/g, " ").slice(0, 50),
    });
  }
  return out;
});
console.log(JSON.stringify(info, null, 1));
const html = await p.evaluate(() => {
  const el = [...document.querySelectorAll("main *")].find((e) => (e.textContent ?? "").trimStart().startsWith("components:"));
  return el?.parentElement?.outerHTML.slice(0, 900);
});
console.log("HTML", html);
await b.close();
