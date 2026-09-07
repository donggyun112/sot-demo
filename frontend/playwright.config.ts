import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 90_000,
  retries: 0,
  workers: 1,
  use: {
    baseURL: "http://127.0.0.1:18000",
    actionTimeout: 10_000,
    // Authenticated traces contain bearer/refresh credentials and Toss capabilities.
    trace: "off",
  },
  webServer: [
    {
      command: "uv run --project . python -m tests.e2e_app",
      cwd: "../backend",
      url: "http://127.0.0.1:18001/healthz",
      env: { SOT_ENVIRONMENT: "test", SOT_CORS_ORIGINS: '["http://127.0.0.1:18000"]' },
      reuseExistingServer: false,
      gracefulShutdown: { signal: "SIGTERM", timeout: 10_000 },
    },
    {
      command: "pnpm dev --host 127.0.0.1 --port 18000 --strictPort",
      url: "http://127.0.0.1:18000",
      env: { VITE_GOOGLE_CLIENT_ID: "sot-browser-test-client", VITE_API_BASE: "http://127.0.0.1:18001/api/v1" },
      reuseExistingServer: false,
      gracefulShutdown: { signal: "SIGTERM", timeout: 10_000 },
    },
  ],
});
