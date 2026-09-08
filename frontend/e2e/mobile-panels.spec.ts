import { expect, test } from "@playwright/test";

/**
 * Below 960px the outline and evidence rail collapse. They must stay reachable
 * through `?panel=`, and the header must never push the page sideways.
 */
test("keeps the evidence rail reachable on a phone viewport", async ({ page }) => {
  await page.route("https://accounts.google.com/gsi/client", (route) => route.fulfill({
    contentType: "application/javascript", body: `
      let options;
      window.google = { accounts: { id: {
        initialize(value) { options = value; },
        renderButton(element) {
          const button = document.createElement('button');
          button.textContent = 'Sign in with Google';
          button.onclick = () => options.callback({ credential: 'google-test-alice' });
          element.replaceChildren(button);
        }
      } } };`,
  }));
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await page.getByRole("button", { name: "Sign in with Google" }).click();
  await page.getByRole("button", { name: "Menu" }).click();
  await page.getByRole("button", { name: "Workspaces" }).click();
  await page.getByRole("menuitem", { name: "Alice Workspace", exact: true }).click();
  await page.waitForURL(/\/w\/[^/]+$/);
  await page.getByRole("main").getByRole("link", { name: /Alice Policy/ }).click();
  await expect(page.getByRole("heading", { name: "Alice Policy" })).toBeVisible();

  // "Pending changes" is the rail's own heading, so it tracks the rail itself
  // rather than an action that has since moved into the header.
  const rail = page.getByRole("heading", { name: "Pending changes" });
  await expect(rail).toBeHidden();
  await page.getByRole("button", { name: "Evidence" }).click();
  await expect(page).toHaveURL(/panel=evidence/);
  await expect(rail).toBeVisible();
  await page.getByRole("button", { name: "Hide" }).click();
  await expect(rail).toBeHidden();

  // This spec compiles in the Node project, which has no DOM lib; evaluate by
  // expression so the browser globals stay out of the type-check.
  const scroll = await page.evaluate<number>("document.documentElement.scrollWidth");
  const client = await page.evaluate<number>("document.documentElement.clientWidth");
  expect(scroll).toBeLessThanOrEqual(client);
});
