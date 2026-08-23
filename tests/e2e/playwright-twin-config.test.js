import { expect, test } from "vitest";
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";

const configUrl = new URL("../../playwright.twin.config.js", import.meta.url);

async function loadTwinConfig() {
  if (!existsSync(fileURLToPath(configUrl))) {
    throw new Error("E1_PLAYWRIGHT_TWIN_CONFIG_MISSING");
  }
  return (await import(fileURLToPath(configUrl))).default;
}

test("uses only bundled Chromium for the frontend-only D twin suite", async () => {
  const config = await loadTwinConfig();
  const [project] = config.projects;

  expect(config.testDir).toBe("./tests/e2e");
  expect(config.testMatch).toBe("twin/**/*.spec.js");
  expect(config.use.baseURL).toBe("http://127.0.0.1:4174");
  expect(config.webServer).toMatchObject({
    command: "npm.cmd run dev -- --host 127.0.0.1 --port 4174 --strictPort",
    url: "http://127.0.0.1:4174",
    reuseExistingServer: false,
  });
  expect(config.webServer).not.toHaveProperty("env");
  expect(config.projects).toHaveLength(1);
  expect(project).toMatchObject({ name: "bundled-chromium", use: { browserName: "chromium" } });
  expect(project.use).not.toHaveProperty("channel");

  const exposedConfig = JSON.stringify(config);
  expect(exposedConfig).not.toMatch(/python|sqlite|postgres|\.env|deployment|https:|credential/i);
});
