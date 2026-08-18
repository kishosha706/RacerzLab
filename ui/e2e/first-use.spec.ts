import { expect, test, type Page } from "@playwright/test";

const health = {
  status: "ok",
  app: "RacerZLab",
  version: "0.1.0",
  instance_id: null,
};

async function stubStartupApi(page: Page, sessions: unknown[] = []) {
  await page.route("**/api/health", (route) => route.fulfill({ json: health }));
  await page.route("**/api/sessions", (route) => route.fulfill({ json: sessions }));
}

test("first launch enters the evidence-first session picker once", async ({ page }) => {
  const pageErrors: Error[] = [];
  page.on("pageerror", (error) => pageErrors.push(error));
  await stubStartupApi(page);

  await page.goto("/");
  await expect(page.getByRole("button", { name: "Enter RacerZLab garage" })).toBeVisible();
  await page.getByRole("button", { name: "Enter RacerZLab garage" }).click();
  await expect(page.getByRole("heading", { name: "Pick up the engineering thread" })).toBeVisible();
  await expect(page.getByText("No previous sessions yet.")).toBeVisible();
  await expect(page.getByRole("button", { name: /New engineering session/ })).toBeVisible();
  expect(pageErrors).toEqual([]);
});

test("returning driver bypasses the splash and can resume exact last session", async ({ page }) => {
  const session = {
    session_id: "session-alpha",
    name: "Atlanta baseline test",
    track_name: "Atlanta 2022 Oval",
    car_name: "NASCAR Next Gen",
    run_ids: ["run-alpha"],
    created_at: "2026-08-18T12:00:00Z",
    updated_at: "2026-08-18T13:00:00Z",
    archived: false,
    notes: null,
  };
  await page.addInitScript(() => {
    localStorage.setItem("racerzlab.launchSplashDismissed.v1", "true");
    localStorage.setItem("racerzlab.lastSessionId.v1", "session-alpha");
  });
  await stubStartupApi(page, [session]);

  await page.goto("/");
  await expect(page.getByRole("button", { name: "Enter RacerZLab garage" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /Resume last session Atlanta baseline test/ })).toBeVisible();
  await expect(page.getByText(/Current alpha decision scope: NASCAR Next Gen oval telemetry/)).toBeVisible();
});
