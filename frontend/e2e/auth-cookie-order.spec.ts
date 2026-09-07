import { expect, test } from "@playwright/test";
import type { components } from "../src/generated/api";

// This spec is compiled in the Node project. The implementation is imported
// inside Chromium below; only its test-used surface crosses evaluate's boundary.
type BrowserAuth = {
  loginWithGoogle(credential: string): Promise<void>;
  refresh(): Promise<void>;
  logout(): Promise<void>;
  fetch(request: Request): Promise<Response>;
};
type RaceWindow = {
  cookieRace: { auth: BrowserAuth; starts: string[]; pending: Promise<unknown>[] };
};
const api = "http://127.0.0.1:18001/api/v1";

for (const operation of ["refresh", "logout", "recovery"] as const) {
  test(`delayed ${operation} headers cannot replace a newer login cookie after reload`, async ({ page }) => {
    // A narrow real-browser AuthSession regression, not a second product journey.
    // Only response delivery is delayed; Google exchange/rotation/revocation are real.
    await page.route("https://accounts.google.com/gsi/client", (route) => route.fulfill({ body: "" }));
    const boot = page.waitForResponse((response) => response.url().endsWith("/auth/refresh"));
    await page.goto("/");
    await boot;
    await page.evaluate(async (base) => {
      const path = "/src/auth.ts";
      const { AuthSession } = await import(path);
      const starts: string[] = [];
      const auth = new AuthSession((request: Request) => {
        starts.push(request.url.split("/").at(-1)!);
        return fetch(request);
      }, base) as BrowserAuth;
      await auth.loginWithGoogle("google-test-alice");
      (globalThis as unknown as RaceWindow).cookieRace = { auth, starts, pending: [] };
    }, api);

    let captured!: () => void;
    const headersCaptured = new Promise<void>((resolve) => { captured = resolve; });
    let release!: () => void;
    const hold = new Promise<void>((resolve) => { release = resolve; });
    let delayed = false;
    await page.route(`${api}/auth/${operation === "logout" ? "logout" : "refresh"}`, async (route) => {
      if (delayed) return route.continue();
      delayed = true;
      const response = await route.fetch();
      captured();
      await hold;
      await route.fulfill({ response });
    });
    if (operation === "recovery") {
      await page.route(`${api}/me`, (route) => route.fulfill({ status: 401, json: {} }));
    }
    await page.evaluate(({ operation, api }) => {
      const race = (globalThis as unknown as RaceWindow).cookieRace;
      race.pending.push(operation === "recovery"
        ? race.auth.fetch(new Request(`${api}/me`)).catch((error: unknown) => {
          if (!(error instanceof DOMException) || error.name !== "AbortError") throw error;
        })
        : race.auth[operation]());
    }, { operation, api });
    await headersCaptured;
    const before = await page.evaluate(async () => {
      const race = (globalThis as unknown as RaceWindow).cookieRace;
      race.pending.push(race.auth.loginWithGoogle("google-test-bob"));
      await Promise.resolve();
      await Promise.resolve();
      return race.starts;
    });
    // If a regression dispatches B while A is still held, finish B first to
    // reproduce the hostile header ordering deterministically in Chromium.
    if (before.filter((path) => path === "google").length > 1) {
      await page.evaluate(() => (globalThis as unknown as RaceWindow).cookieRace.pending.at(-1));
    }
    release();
    await page.evaluate(() => Promise.all((globalThis as unknown as RaceWindow).cookieRace.pending));
    await page.unroute(`${api}/me`);
    const refreshed = page.waitForResponse((response) => response.url().endsWith("/auth/refresh"));
    await page.reload();
    const response = await refreshed;
    expect(response.status()).toBe(200);
    const body = await response.json() as components["schemas"]["AuthResponse"];
    expect(body.user.display_name).toBe("Bob");
    expect(before.filter((path) => path === "google")).toHaveLength(1);
    await expect(page.getByRole("combobox", { name: "Workspace", exact: true })).toBeVisible();
    expect(await page.evaluate(() => [localStorage.length, sessionStorage.length])).toEqual([0, 0]);
  });
}
