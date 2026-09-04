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
test("Show Management starts every show collapsed and expands cards independently", async ({ page }) => {
  await isolateNetwork(page);
  await page.clock.install({ time: new Date("2026-08-09T12:00:00") });
  await page.addInitScript(() => {
    const payload = btoa(JSON.stringify({ exp: 4102444800 }));
    localStorage.setItem("satt_jwt", JSON.stringify({ token: "test." + payload + ".signature" }));
  });
  const apiRequests = [];
  await page.route("**/api/top3/**", async (route) => {
    const pathname = new URL(route.request().url()).pathname;
    const body = pathname === "/api/top3/concepts"
      ? { revision: 0, concepts: [] }
      : { revision: 0, assignment: null };
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
  });
  await page.route("**/api/export", async (route) => {
    apiRequests.push(new URL(route.request().url()).pathname);
    const idea = (id, title, status) => ({
      id, rawNotes: title + " notes", titles: [title], selectedTitle: title,
      summary: title + " summary", outline: [], status,
      createdAt: "2026-08-08T12:00:00Z", updatedAt: "2026-08-08T12:00:00Z", imageFileId: null,
    });
    await route.fulfill({
      status: 200, contentType: "application/json",
      body: JSON.stringify({
        config: {},
        ideas: [
          idea("scheduled", "Scheduled Show", "scheduled"),
          idea("unscheduled", "Unscheduled Show", "processed"),
          idea("recent", "Recently Edited Show", "processed"),
        ],
        jokes: [], songs: [], guests: [], guestAssignments: [],
        showSlots: [
          { id: "slot-scheduled", episodeNumber: "EP030", episodeNum: 30, recordDate: "2026-08-11", releaseDate: "2026-08-18", isRollout: false },
          { id: "slot-horizon", episodeNumber: "EP050", episodeNum: 50, recordDate: "2027-01-05", releaseDate: "2027-01-12", isRollout: false },
        ],
        assignments: { "slot-scheduled": "scheduled" },
        revision: 0,
      }),
    });
  });

  await page.goto("/show_management.html");
  const cards = page.locator(".idea-list-card");
  await expect(cards).toHaveCount(3);
  for (let index = 0; index < 3; index += 1) await expect(cards.nth(index)).not.toHaveClass(/expanded/);

  const scheduled = page.locator("#idea-scheduled");
  const unscheduled = page.locator("#idea-unscheduled");
  await scheduled.locator(".idea-header").click();
  await expect(scheduled).toHaveClass(/expanded/);
  await expect(scheduled.getByRole("button", { name: /Edit/ })).toBeVisible();
  await expect(unscheduled).not.toHaveClass(/expanded/);
  await unscheduled.locator(".idea-header").click();
  await expect(unscheduled).toHaveClass(/expanded/);
  await expect(scheduled).toHaveClass(/expanded/);
  await scheduled.locator(".idea-header").click();
  await expect(scheduled).not.toHaveClass(/expanded/);
  await expect(unscheduled).toHaveClass(/expanded/);

  const assignmentsBeforeView = await page.evaluate(() => Storage.getAssignments());
  await unscheduled.getByRole("link", { name: /View/ }).click();
  await expect(page.locator("#showDisplayOverlay")).toHaveClass(/active/);
  await expect(page.locator("#showDisplayContent")).toContainText("Unscheduled Show");
  await expect(page.locator("#showDisplayContent")).toContainText("No schedule slot assigned");
  await expect(page).toHaveURL(/#idea\/unscheduled$/);
  await page.getByRole("button", { name: /Close/ }).click();

  await scheduled.getByRole("link", { name: /View/ }).click();
  await expect(page.locator("#showDisplayOverlay")).toHaveClass(/active/);
  await expect(page.locator("#showDisplayContent")).toContainText("Scheduled Show");
  await expect(page.locator("#showDisplayContent")).toContainText("EP030");
  await expect(page).toHaveURL(/#show\/slot-scheduled$/);
  await page.getByRole("button", { name: /Close/ }).click();
  expect(await page.evaluate(() => Storage.getAssignments())).toEqual(assignmentsBeforeView);

  await page.reload();
  await expect.poll(() => apiRequests.length).toBe(2);
  await expect(cards).toHaveCount(3);
  for (let index = 0; index < 3; index += 1) await expect(cards.nth(index)).not.toHaveClass(/expanded/);
  expect(apiRequests).toEqual(["/api/export", "/api/export"]);
});

test("past, future, and unscheduled show edits use one workflow and preserve schedule state", async ({ page }) => {
  await isolateNetwork(page);
  await page.clock.install({ time: new Date("2026-08-25T12:00:00") });
  await page.addInitScript(() => {
    const payload = btoa(JSON.stringify({ exp: 4102444800 }));
    localStorage.setItem("satt_jwt", JSON.stringify({ token: "test." + payload + ".signature" }));
  });

  let revision = 0;
  let ideaMutations = 0;
  const idea = (id, title, status) => ({
    id, rawNotes: title + " notes", titles: [title], selectedTitle: title,
    summary: title + " summary", outline: [], status,
    createdAt: "2026-08-09T12:00:00Z", updatedAt: "2026-08-09T12:00:00Z", imageFileId: null,
  });
  let canonicalIdeas = [
    idea("future-edit", "Future Editable Show", "scheduled"),
    idea("past-edit", "Past Editable Show", "scheduled"),
    idea("unscheduled-edit", "Unscheduled Editable Show", "processed"),
  ];
  const futureSlot = {
    id: "slot-future", episodeNumber: "EP041", episodeNum: 41,
    recordDate: "2026-09-01", releaseDate: "2026-09-08",
    releaseDateOverride: null, isRollout: false,
  };
  const pastSlot = {
    id: "slot-past", episodeNumber: "EP040", episodeNum: 40,
    recordDate: "2026-08-11", releaseDate: "2026-08-18",
    releaseDateOverride: "2026-08-19", isRollout: false,
  };
  const canonicalState = () => ({
    config: {}, ideas: canonicalIdeas, jokes: [], songs: [], guests: [], guestAssignments: [],
    showSlots: [pastSlot, futureSlot],
    assignments: { "slot-past": "past-edit", "slot-future": "future-edit" }, revision,
  });

  await page.route("**/api/top3/**", async (route) => {
    const pathname = new URL(route.request().url()).pathname;
    const body = pathname === "/api/top3/concepts"
      ? { revision, concepts: [] }
      : { revision, assignment: null };
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
  });
  await page.route("**/api/export", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(canonicalState()) });
  });
  await page.route("**/api/data/ideas", async (route) => {
    ideaMutations += 1;
    expect(route.request().headers()["if-match"]).toBe(String(revision));
    canonicalIdeas = JSON.parse(route.request().postData()).map((item) => ({
      ...item, updatedAt: "2026-08-09T12:01:00Z",
    }));
    revision += 1;
    await route.fulfill({
      status: 200, contentType: "application/json",
      body: JSON.stringify({ ok: true, state: canonicalState(), revision }),
    });
  });

  await page.goto("/show_management.html");
  let scheduled = page.locator("#idea-future-edit");
  await expect(scheduled).not.toHaveClass(/expanded/);
  await expect(scheduled.getByRole("button", { name: "Edit show" })).toBeVisible();

  const scheduleBefore = await page.evaluate(() => ({
    assignments: Storage.getAssignments(),
    slots: Storage.getShowSlots(),
  }));
  await scheduled.getByRole("button", { name: "Edit show" }).click();
  await expect(scheduled).toHaveClass(/expanded/);
  await scheduled.locator("[data-edit-summary]").fill("Scheduled content saved in place");
  await scheduled.getByRole("button", { name: "Save Changes" }).click();
  await expect(scheduled).toContainText("Scheduled content saved in place");
  expect(ideaMutations).toBe(1);
  expect(await page.evaluate(() => ({
    assignments: Storage.getAssignments(),
    slots: Storage.getShowSlots(),
  }))).toEqual(scheduleBefore);
  expect(await page.evaluate(() => Storage.getIdeas().find((item) => item.id === "future-edit").status)).toBe("scheduled");

  await page.reload();
  scheduled = page.locator("#idea-future-edit");
  await expect(scheduled).toContainText("Scheduled content saved in place");
  expect(await page.evaluate(() => ({
    assignments: Storage.getAssignments(),
    slots: Storage.getShowSlots(),
  }))).toEqual(scheduleBefore);

  await scheduled.getByRole("button", { name: "Edit show" }).click();
  await scheduled.locator("[data-edit-summary]").fill("Discard this scheduled edit");
  await scheduled.getByRole("button", { name: "Cancel" }).click();
  await expect(scheduled).toContainText("Scheduled content saved in place");
  await expect(scheduled).not.toContainText("Discard this scheduled edit");
  expect(ideaMutations).toBe(1);
  expect(await page.evaluate(() => ({
    assignments: Storage.getAssignments(),
    slots: Storage.getShowSlots(),
  }))).toEqual(scheduleBefore);

  const unscheduled = page.locator("#idea-unscheduled-edit");
  await expect(unscheduled.getByRole("button", { name: "Edit show" })).toBeVisible();
  await unscheduled.getByRole("button", { name: "Edit show" }).click();
  await unscheduled.locator("[data-edit-summary]").fill("Unscheduled workflow still edits");
  await unscheduled.getByRole("button", { name: "Save Changes" }).click();
  await expect(unscheduled).toContainText("Unscheduled workflow still edits");
  expect(ideaMutations).toBe(2);
  expect(await page.evaluate(() => Storage.getIdeas().find((item) => item.id === "unscheduled-edit").status)).toBe("processed");
  expect(await page.evaluate(() => ({
    assignments: Storage.getAssignments(),
    slots: Storage.getShowSlots(),
  }))).toEqual(scheduleBefore);

  await page.getByRole("heading", { name: "Past Episodes" }).click();
  let past = page.locator("#idea-past-edit");
  await expect(past.getByRole("button", { name: "Edit show" })).toBeVisible();
  await past.getByRole("button", { name: "Edit show" }).click();
  await past.locator("[data-edit-summary]").fill("Past show content remains editable");
  await past.getByRole("button", { name: "Save Changes" }).click();
  await expect(past).toContainText("Past show content remains editable");
  expect(ideaMutations).toBe(3);
  expect(await page.evaluate(() => Storage.getIdeas().find((item) => item.id === "past-edit").status)).toBe("scheduled");
  expect(await page.evaluate(() => ({
    assignments: Storage.getAssignments(),
    slots: Storage.getShowSlots(),
  }))).toEqual(scheduleBefore);

  await page.reload();
  await page.getByRole("heading", { name: "Past Episodes" }).click();
  past = page.locator("#idea-past-edit");
  await expect(past).toContainText("Past show content remains editable");
  await expect(page.locator("#idea-future-edit")).toContainText("Scheduled content saved in place");
  await expect(page.locator("#idea-unscheduled-edit")).toContainText("Unscheduled workflow still edits");
  expect(await page.evaluate(() => ({
    assignments: Storage.getAssignments(),
    slots: Storage.getShowSlots(),
  }))).toEqual(scheduleBefore);
});

test("episode number override persists across management, view, schedule, and reset", async ({ page }) => {
  await isolateNetwork(page);
  await page.clock.install({ time: new Date("2026-08-25T12:00:00") });
  await page.addInitScript(() => {
    const payload = btoa(JSON.stringify({ exp: 4102444800 }));
    localStorage.setItem("satt_jwt", JSON.stringify({ token: "test." + payload + ".signature" }));
  });

  let revision = 0;
  let episodeNumberMutations = 0;
  const idea = {
    id: "override-edit", rawNotes: "Override notes", titles: ["Override Show"],
    selectedTitle: "Override Show", summary: "Override summary", outline: [], status: "scheduled",
    createdAt: "2026-08-09T12:00:00Z", updatedAt: "2026-08-09T12:00:00Z", imageFileId: null,
  };
  const slot = {
    id: "slot-override", episodeNumber: "EP041", episodeNum: 41,
    episodeNumberOverride: null, effectiveEpisodeNumber: "EP041",
    recordDate: "2026-09-01", releaseDate: "2026-09-08",
    releaseDateOverride: "2026-09-09", isRollout: false,
  };
  const horizon = {
    id: "slot-horizon", episodeNumber: "EP060", episodeNum: 60,
    episodeNumberOverride: null, effectiveEpisodeNumber: "EP060",
    recordDate: "2027-01-12", releaseDate: "2027-01-19",
    releaseDateOverride: null, isRollout: false,
  };
  const canonicalState = () => ({
    config: {}, ideas: [idea], jokes: [], songs: [], guests: [], guestAssignments: [],
    showSlots: [slot, horizon], assignments: { "slot-override": "override-edit" }, revision,
  });

  await page.route("**/api/top3/**", async (route) => {
    const pathname = new URL(route.request().url()).pathname;
    const body = pathname === "/api/top3/concepts"
      ? { revision, concepts: [] }
      : { revision, assignment: null };
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
  });
  await page.route("**/api/export", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(canonicalState()) });
  });
  await page.route("**/api/schedule/slot-override/episode-number", async (route) => {
    episodeNumberMutations += 1;
    expect(route.request().headers()["if-match"]).toBe(String(revision));
    if (route.request().method() === "PUT") {
      const payload = JSON.parse(route.request().postData());
      expect(payload).toEqual({ episodeNumber: 40 });
      slot.episodeNumberOverride = 40;
      slot.effectiveEpisodeNumber = "EP040";
    } else {
      expect(route.request().method()).toBe("DELETE");
      slot.episodeNumberOverride = null;
      slot.effectiveEpisodeNumber = "EP041";
    }
    revision += 1;
    await route.fulfill({
      status: 200, contentType: "application/json",
      body: JSON.stringify({ ok: true, state: canonicalState(), revision }),
    });
  });

  await page.goto("/show_management.html");
  let card = page.locator("#idea-override-edit");
  const scheduleBefore = await page.evaluate(() => ({
    assignments: Storage.getAssignments(),
    recordDate: Storage.getShowSlots()[0].recordDate,
    releaseDate: Storage.getShowSlots()[0].releaseDate,
    releaseDateOverride: Storage.getShowSlots()[0].releaseDateOverride,
  }));
  await card.getByRole("button", { name: "Edit show" }).click();

  const numberInput = card.getByRole("spinbutton", { name: "Episode number override" });
  await numberInput.fill("");
  await card.getByRole("button", { name: "Save Number" }).click();
  await expect(page.getByText("Episode number must be a positive whole number.")).toBeVisible();
  expect(episodeNumberMutations).toBe(0);

  await numberInput.fill("40");
  await card.getByRole("button", { name: "Save Number" }).click();
  await expect(card).toContainText("EP040");
  expect(episodeNumberMutations).toBe(1);
  expect(await page.evaluate(() => ({
    assignments: Storage.getAssignments(),
    recordDate: Storage.getShowSlots()[0].recordDate,
    releaseDate: Storage.getShowSlots()[0].releaseDate,
    releaseDateOverride: Storage.getShowSlots()[0].releaseDateOverride,
  }))).toEqual(scheduleBefore);

  await card.getByRole("link", { name: /View/ }).click();
  await expect(page.locator("#showDisplayContent .ep-badge")).toHaveText("EP040");
  await page.getByRole("button", { name: /Close/ }).click();
  await page.getByRole("button", { name: "Schedule Board" }).click();
  await page.getByRole("button", { name: /Next/ }).click();
  await expect(page.locator('[data-slot-id="slot-override"] .ep-num')).toHaveText("EP040");

  await page.reload();
  card = page.locator("#idea-override-edit");
  await expect(card).toContainText("EP040");
  await card.getByRole("button", { name: "Edit show" }).click();
  await expect(card.getByRole("spinbutton", { name: "Episode number override" })).toHaveValue("40");
  await card.getByRole("button", { name: "Use Automatic" }).click();
  await expect(card).toContainText("EP041");
  expect(episodeNumberMutations).toBe(2);

  await page.reload();
  card = page.locator("#idea-override-edit");
  await expect(card).toContainText("EP041");
  expect(await page.evaluate(() => ({
    assignments: Storage.getAssignments(),
    recordDate: Storage.getShowSlots()[0].recordDate,
    releaseDate: Storage.getShowSlots()[0].releaseDate,
    releaseDateOverride: Storage.getShowSlots()[0].releaseDateOverride,
  }))).toEqual(scheduleBefore);
});
test("Show Management reconciles successful and conflicted mutations without a page reload", async ({ page }) => {
  await isolateNetwork(page);
  await page.clock.install({ time: new Date("2026-08-09T12:00:00") });
  await page.addInitScript(() => {
    const payload = btoa(JSON.stringify({ exp: 4102444800 }));
    localStorage.setItem("satt_jwt", JSON.stringify({ token: "test." + payload + ".signature" }));
  });

  let revision = 0;
  let mutationCount = 0;
  let exportCount = 0;
  const idea = (id, notes, status = "draft") => ({
    id, rawNotes: notes, titles: [], selectedTitle: null, summary: null, outline: [], status,
    createdAt: "2026-08-09T12:00:00Z", updatedAt: "2026-08-09T12:00:00Z", imageFileId: null,
  });
  let canonicalIdeas = [idea("existing", "Existing canonical draft")];
  const canonicalState = () => ({
    config: {}, ideas: canonicalIdeas, jokes: [], songs: [], guests: [], guestAssignments: [],
    showSlots: [
      { id: "slot-horizon", episodeNumber: "EP050", episodeNum: 50, recordDate: "2027-01-05", releaseDate: "2027-01-12", isRollout: false },
    ],
    assignments: {}, revision,
  });

  await page.route("**/api/top3/**", async (route) => {
    const pathname = new URL(route.request().url()).pathname;
    const body = pathname === "/api/top3/concepts"
      ? { revision, concepts: [] }
      : { revision, assignment: null };
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
  });
  await page.route("**/api/export", async (route) => {
    exportCount += 1;
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(canonicalState()) });
  });
  await page.route("**/api/data/ideas", async (route) => {
    mutationCount += 1;
    if (mutationCount === 1) {
      expect(route.request().headers()["if-match"]).toBe("0");
      canonicalIdeas = JSON.parse(route.request().postData()).map((item) => ({
        ...item, updatedAt: "2026-08-09T12:01:00Z",
      }));
      revision = 1;
      await route.fulfill({
        status: 200, contentType: "application/json",
        body: JSON.stringify({ ok: true, state: canonicalState(), revision }),
      });
      return;
    }

    expect(route.request().headers()["if-match"]).toBe("1");
    canonicalIdeas = canonicalIdeas.concat([idea("server-newer", "Server canonical concurrent draft")]);
    revision = 2;
    await route.fulfill({
      status: 409, contentType: "application/json",
      body: JSON.stringify({ detail: { message: "Server data changed", currentRevision: revision } }),
    });
  });

  await page.goto("/show_management.html");
  await expect(page.locator(".idea-list-card")).toHaveCount(1);

  await page.locator("#ideaNotes").fill("Created without reload");
  await page.getByRole("button", { name: "Save as Draft" }).click();
  await expect(page.locator("#ideasList")).toContainText("Created without reload");
  await expect(page.locator(".idea-list-card")).toHaveCount(2);
  expect(exportCount).toBe(1);

  await page.locator("#ideaNotes").fill("Client stale draft");
  await page.getByRole("button", { name: "Save as Draft" }).click();
  await expect(page.locator("#ideasList")).toContainText("Server canonical concurrent draft");
  await expect(page.locator("#ideasList")).not.toContainText("Client stale draft");
  await expect(page.locator("#save-status")).toContainText("Newer server data loaded");
  await expect(page.locator(".idea-list-card")).toHaveCount(3);
  expect(exportCount).toBe(2);
  expect(mutationCount).toBe(2);

  await page.reload();
  await expect(page.locator("#ideasList")).toContainText("Created without reload");
  await expect(page.locator("#ideasList")).toContainText("Server canonical concurrent draft");
  await expect(page.locator("#ideasList")).not.toContainText("Client stale draft");
  await expect(page.locator(".idea-list-card")).toHaveCount(3);
  expect(exportCount).toBe(3);
});
