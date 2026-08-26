import { expect, test } from "@playwright/test";

const snapshotPattern = "**/api/v2/assets/forzy-motor-01/snapshot";

test("animates bootstrap and makes a failed retry visibly responsive", async ({ page }) => {
  let holdManualRetry = false;
  let manualRetryCount = 0;
  let releaseManualRetry;
  const manualRetryGate = new Promise((resolve) => {
    releaseManualRetry = resolve;
  });

  await page.route(snapshotPattern, async (route) => {
    if (holdManualRetry) {
      manualRetryCount += 1;
      await manualRetryGate;
    } else {
      await new Promise((resolve) => setTimeout(resolve, 1_000));
    }
    await route.fulfill({
      body: JSON.stringify({ detail: "snapshot unavailable" }),
      contentType: "application/json",
      status: 500,
    });
  });

  await page.goto("/");

  const loading = page.getByRole("status", {
    name: "Carregando o último snapshot real…",
  });
  await expect(loading).toHaveAttribute("aria-busy", "true");
  const ring = loading.locator(".loading-state__ring");
  await expect(ring).toHaveCSS("animation-name", "loading-ring-turn");
  const firstTransform = await ring.evaluate((element) => getComputedStyle(element).transform);
  await page.waitForTimeout(180);
  const nextTransform = await ring.evaluate((element) => getComputedStyle(element).transform);
  expect(nextTransform).not.toBe(firstTransform);

  await expect(page.getByRole("heading", { name: "Dados reais indisponíveis" })).toBeVisible();
  holdManualRetry = true;
  const button = page.locator("button.refresh-action");
  await expect(button).toHaveAccessibleName("Atualizar agora");
  await button.focus();
  await button.click();

  await expect(button).toBeFocused();
  await expect(button).toHaveAccessibleName("Consultando dados reais…");
  await expect(button).toHaveAttribute("aria-busy", "true");
  await expect(button).toHaveAttribute("aria-disabled", "true");
  await expect(page.getByRole("status")).toContainText(
    "Consultando o backend por um snapshot real…",
  );
  await expect.poll(() => manualRetryCount).toBe(1);

  await button.evaluate((element) => element.click());
  await page.waitForTimeout(100);
  expect(manualRetryCount).toBe(1);

  releaseManualRetry();
  await expect(button).toBeFocused();
  await expect(button).toHaveAccessibleName("Atualizar agora");
  await expect(button).toHaveAttribute("aria-busy", "false");
  await expect(button).toHaveAttribute("aria-disabled", "false");
  await expect(page.getByRole("status")).toContainText(
    "A nova tentativa falhou. O backend continua indisponível.",
  );
});
