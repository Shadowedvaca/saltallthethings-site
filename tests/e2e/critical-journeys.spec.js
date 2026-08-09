const { test, expect } = require("@playwright/test");

async function isolateNetwork(page) {
  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    if (url.hostname === "127.0.0.1") return route.continue();
    return route.abort("blockedbyclient");
  });
}

test("public hero keeps subtitle and Explore separate without horizontal overflow", async ({ page }) => {
  await isolateNetwork(page);
  const viewports = [
    { width: 1440, height: 900 },
    { width: 768, height: 1024 },
    { width: 390, height: 844 },
    { width: 360, height: 640 },
  ];
  for (const viewport of viewports) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await page.goto("/index.html");
    const subtitle = await page.locator(".hero-subtitle").boundingBox();
    const explore = await page.locator(".scroll-hint").boundingBox();
    expect(subtitle).not.toBeNull();
    expect(explore).not.toBeNull();
    expect(explore.y).toBeGreaterThanOrEqual(subtitle.y + subtitle.height);
    const widths = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, client: document.documentElement.clientWidth }));
    expect(widths.scroll).toBeLessThanOrEqual(widths.client + 1);
  }
});

test("Show Management rejects an unauthenticated browser locally", async ({ page }) => {
  await isolateNetwork(page);
  await page.goto("/show_management.html");
  await expect(page).toHaveURL(/\/login\.html\?next=%2Fshow_management\.html$/);
  await expect(page.getByRole("heading", { name: "Salt All The Things" })).toBeVisible();
  await expect(page.getByText("Crew Access", { exact: true })).toBeVisible();
});

test("Schedule Board opens to the current local month and resets on reload", async ({ page }) => {
  await isolateNetwork(page);
  await page.clock.install({ time: new Date("2026-12-31T12:00:00") });
  await page.addInitScript(() => {
    const payload = btoa(JSON.stringify({ exp: 4102444800 }));
    localStorage.setItem("satt_jwt", JSON.stringify({ token: `test.${payload}.signature` }));
  });
  const apiRequests = [];
  await page.route("**/api/export", async (route) => {
    apiRequests.push(new URL(route.request().url()).pathname);
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        config: {},
        ideas: [],
        jokes: [],
        songs: [],
        guests: [],
        guestAssignments: [],
        showSlots: [],
        assignments: {},
        revision: 0,
      }),
    });
  });

  await page.goto("/show_management.html");
  await page.getByRole("button", { name: "Schedule Board" }).click();
  await expect(page.locator("#calendarTitle")).toHaveText("December 2026");

  await page.getByRole("button", { name: /Next/ }).click();
  await expect(page.locator("#calendarTitle")).toHaveText("January 2027");
  await page.getByRole("button", { name: /Prev/ }).click();
  await expect(page.locator("#calendarTitle")).toHaveText("December 2026");

  await page.reload();
  await page.getByRole("button", { name: "Schedule Board" }).click();
  await expect(page.locator("#calendarTitle")).toHaveText("December 2026");
  expect(apiRequests).toEqual(["/api/export", "/api/export"]);
});
