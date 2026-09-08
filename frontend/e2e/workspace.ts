import { expect, type Page } from "@playwright/test";

/*
  Switching workspaces is a client-side navigation: the click returns before
  the URL changes, so waiting on the URL's shape alone matches the workspace
  we came from and hands back its id. The switcher's own label is the first
  thing that only the destination can produce.
*/
export async function openWorkspace(page: Page, name: string) {
  await page.getByRole("button", { name: "Workspaces" }).click();
  await page.getByRole("menuitem", { name, exact: true }).click();
  await expect(page.getByRole("button", { name: "Workspaces" })).toHaveText(
    new RegExp(name),
  );
  await page.waitForURL(/\/w\/[^/]+$/);
  return new URL(page.url()).pathname.split("/")[2];
}
