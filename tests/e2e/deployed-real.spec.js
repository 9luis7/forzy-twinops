import { expect, test } from "@playwright/test";

const deploymentConfigured = Boolean(process.env.DEPLOYMENT_URL?.trim());
const allowStubRefresh = process.env.TWINOPS_E2E_ALLOW_STUB_REFRESH === "1";
const assetPath = "/api/v2/assets/forzy-motor-01";

test.describe("deployed real TwinOps preview", () => {
  test.skip(!deploymentConfigured, "DEPLOYMENT_URL is required for deployed probes");

  test("renders only the real asset and serves the packaged model", async ({
    page,
    request,
  }) => {
    const snapshotResponse = await request.get(`${assetPath}/snapshot`);
    expect(snapshotResponse.status()).toBe(200);
    const snapshot = await snapshotResponse.json();
    expect(snapshot.schemaVersion).toBe("2.0");
    expect(snapshot.asset).toEqual({
      assetId: "forzy-motor-01",
      displayName: "Conjunto motor-bomba monitorado",
      officialTag: null,
    });
    expect(snapshot.channels.map(({ sensorId }) => sensorId).sort()).toEqual([
      "s1",
      "s2",
    ]);

    await page.goto("/");
    await expect(
      page.getByRole("heading", { name: "Conjunto motor-bomba monitorado" })
    ).toBeVisible();
    await expect(page.getByText("TAG não fornecida")).toBeVisible();
    await expect(
      page.getByText(/MTR-BMB-042|Área 01|Ordens de serviço/)
    ).toHaveCount(0);
    if (snapshot.channels.some(({ receivedAt }) => receivedAt !== null)) {
      await expect(page.getByText(/Capturado pelo TwinOps às/).first()).toBeVisible();
    } else {
      await expect(page.getByText("Nenhuma leitura real foi persistida ainda.")).toBeVisible();
    }

    const healthResponse = await request.get("/api/v2/integration/health");
    expect(healthResponse.status()).toBe(200);
    const health = await healthResponse.json();
    expect(health.status).toBe("ok");
    expect(Object.keys(health.integration.sensors).sort()).toEqual(["s1", "s2"]);

    const manifestResponse = await request.get(
      "/models/conjunto-motor-bomba.manifest.json"
    );
    expect(manifestResponse.status()).toBe(200);
    expect(manifestResponse.headers()["content-type"]).toContain("application/json");
    const manifest = await manifestResponse.json();
    expect(manifest.assetId).toBe("forzy-motor-01");
    expect(manifest.modelUrl).toBe("/models/conjunto-motor-bomba.glb");
    for (const [path, contentTypes, magic] of [
      [manifest.modelUrl, ["model/gltf-binary", "application/octet-stream"], Buffer.from("glTF")],
      [
        "/models/conjunto-motor-bomba-preview.png",
        ["image/png"],
        Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
      ],
    ]) {
      const response = await request.get(path);
      expect(response.status()).toBe(200);
      const contentType = response.headers()["content-type"]?.split(";", 1)[0];
      expect(contentTypes).toContain(contentType);
      const body = await response.body();
      expect(body.byteLength).toBeGreaterThanOrEqual(magic.byteLength);
      expect(body.subarray(0, magic.byteLength).equals(magic)).toBe(true);
    }
  });

  test("refreshes only against the explicitly allowed controlled stub", async ({
    request,
  }) => {
    test.skip(!allowStubRefresh, "TWINOPS_E2E_ALLOW_STUB_REFRESH=1 is required");
    const healthResponse = await request.get("/api/v2/integration/health");
    expect(healthResponse.status()).toBe(200);
    const health = await healthResponse.json();
    test.skip(health.integration.state !== "active", "Forzy collection window is closed");

    const response = await request.post(`${assetPath}/refresh`);
    expect(response.status()).toBe(200);
    const envelope = await response.json();
    expect(envelope.refreshAttempted).toBe(true);
    expect(Object.keys(envelope.outcomes).sort()).toEqual(["s1", "s2"]);
    for (const outcome of Object.values(envelope.outcomes)) {
      expect(["stored", "unchanged"]).toContain(outcome);
    }
    expect(envelope.snapshot.schemaVersion).toBe("2.0");
    expect(envelope.snapshot.asset.assetId).toBe("forzy-motor-01");
    expect(envelope.snapshot.assessment).toEqual(expect.any(Object));
    expect(["normal", "watch", "alert", "insufficient_data"]).toContain(
      envelope.snapshot.assessment.assessment.status
    );
    expect(envelope.snapshot.assessment.assessment.scoreSemantics).toBe(
      "relative_to_historical_baseline_not_failure_probability"
    );
    expect(envelope.snapshot.assessment.model.name).toBe("robust-baseline");
  });
});
