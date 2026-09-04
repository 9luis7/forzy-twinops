import { defineConfig } from "@playwright/test";


export default defineConfig({
  testDir: "./tests/e2e",
  testMatch: "rag/**/*.spec.js",
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  reporter: "list",
  use: {
    baseURL: "http://127.0.0.1:4175",
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
  projects: [{
    name: "bundled-chromium",
    use: { browserName: "chromium" },
  }],
  webServer: {
    command: "npm run dev -- --host 127.0.0.1 --port 4175 --strictPort",
    url: "http://127.0.0.1:4175",
    timeout: 60_000,
    reuseExistingServer: false,
    env: { VITE_RAG_ADMIN_ENABLED: "true" },
    stdout: "pipe",
    stderr: "pipe",
  },
});
