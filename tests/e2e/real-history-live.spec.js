import { expect, test } from "@playwright/test";

const backendUrl = "http://127.0.0.1:8000";

test("CSV real reaches the canonical API and live frontend", async ({
  page,
  request,
}) => {
  const snapshotResponsePromise = page.waitForResponse(
    (response) =>
      response.url().includes("/api/v1/twin/assets/MTR-BMB-042/snapshot") &&
      response.status() === 200
  );
  await page.goto("/");
  const snapshotResponse = await snapshotResponsePromise;
  const snapshot = await snapshotResponse.json();
  expect(snapshot.assetTag).toBe("MTR-BMB-042");
  expect(snapshot.channels.map((channel) => channel.sensorId)).toEqual([
    "s1",
    "s2",
  ]);
  expect(snapshot.channels.every((channel) => channel.sourceMode === "historical")).toBe(
    true
  );
  expect(snapshot.assessment.assessment.scoreSemantics).toBe(
    "relative_to_historical_baseline_not_failure_probability"
  );

  await expect(page.getByText("Dados canônicos S1/S2")).toBeVisible();
  await page.locator("button.nav-item").filter({ hasText: "Ativos" }).click();
  await page.locator("button.ascard").filter({ hasText: "MTR-BMB-042" }).click();

  await expect(page.getByRole("heading", { name: "Motor Bomba de Sucção 042" })).toBeVisible();
  await expect(page.getByText("Indeterminado", { exact: true })).toBeVisible();
  await expect(page.getByRole("img", { name: /S1 · Velocidade RMS/ })).toBeVisible();
  await expect(page.getByRole("img", { name: /S2 · Temperatura/ })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Histórico canônico" })).toBeVisible();
  await expect(page.getByText(/nenhum traçado sintético é exibido/i)).toBeVisible();

  const healthResponse = await request.get(`${backendUrl}/api/v1/system/health`);
  expect(healthResponse.ok()).toBeTruthy();
  const health = await healthResponse.json();
  expect(health.collector.sensors.s1.sampleCount).toBe(7183);
  expect(health.collector.sensors.s2.sampleCount).toBe(7183);
});
