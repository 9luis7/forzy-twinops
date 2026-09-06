import { expect, test } from "vitest";
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";


const configUrl = new URL("../../playwright.rag.config.js", import.meta.url);


test("uses bundled Chromium and a Vite-only server for deterministic RAG E2E", async () => {
  if (!existsSync(fileURLToPath(configUrl))) {
    throw new Error("RAG_PLAYWRIGHT_CONFIG_MISSING");
  }
  const config = (await import(fileURLToPath(configUrl))).default;
  const [project] = config.projects;

  expect(config.testDir).toBe("./tests/e2e");
  expect(config.testMatch).toBe("rag/**/*.spec.js");
  expect(config.use.baseURL).toBe("http://127.0.0.1:4175");
  expect(config.webServer).toMatchObject({
    command: "npm run dev -- --host 127.0.0.1 --port 4175 --strictPort",
    url: "http://127.0.0.1:4175",
    reuseExistingServer: false,
    env: { VITE_RAG_ADMIN_ENABLED: "true" },
  });
  expect(project).toMatchObject({ name: "bundled-chromium", use: { browserName: "chromium" } });
  expect(project.use).not.toHaveProperty("channel");
  expect(JSON.stringify(config)).not.toMatch(/python|sqlite|postgres|gateway|credential/i);
});
