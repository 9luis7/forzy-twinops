import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 180_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  reporter: "list",
  use: {
    baseURL: "http://127.0.0.1:4173",
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "desktop-chrome",
      use: { ...devices["Desktop Chrome"], channel: "chrome" },
    },
  ],
  webServer: [
    {
      command:
        "services\\twinops\\.venv\\Scripts\\python.exe scripts\\e2e_backend.py",
      url: "http://127.0.0.1:8000/api/v1/system/health",
      timeout: 180_000,
      reuseExistingServer: false,
      stdout: "pipe",
      stderr: "pipe",
    },
    {
      command:
        "npm.cmd run dev -- --host 127.0.0.1 --port 4173 --strictPort",
      url: "http://127.0.0.1:4173",
      timeout: 60_000,
      reuseExistingServer: false,
      env: {
        VITE_TWINOPS_DATA_MODE: "live",
        VITE_TWINOPS_API_BASE_URL: "",
        TWINOPS_API_PROXY_TARGET: "http://127.0.0.1:8000",
      },
      stdout: "pipe",
      stderr: "pipe",
    },
  ],
});
