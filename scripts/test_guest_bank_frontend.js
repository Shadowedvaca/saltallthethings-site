"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const GuestBank = require("../js/guests.js");

function guest(overrides = {}) {
  return Object.assign({
    id: "guest-one",
    displayName: "Guest One",
    privateNotes: "Private notes",
    status: "active",
    createdAt: "2026-08-03T00:00:00Z",
    updatedAt: "2026-08-03T01:00:00Z",
    totalAppearances: 0,
    firstAppearance: null,
    mostRecentAppearance: null,
    appearanceHistory: [],
  }, overrides);
}

function testValidationAndSearch() {
  assert.deepEqual(
    GuestBank.validateGuestInput({ displayName: "  Guest One  ", privateNotes: " notes " }),
    { displayName: "Guest One", privateNotes: "notes" },
  );
  assert.throws(
    () => GuestBank.validateGuestInput({ displayName: " ", privateNotes: "" }),
    /Display name is required/,
  );
  assert.throws(
    () => GuestBank.validateGuestInput({ displayName: "x".repeat(201), privateNotes: "" }),
    /at most 200/,
  );
  const searchable = guest({
    privateNotes: "Bring the raid story",
    appearanceHistory: [{
      ideaId: "idea-one",
      title: "Dungeon etiquette",
      episodeNumber: 27,
      releaseDate: null,
      scheduled: false,
    }],
  });
  assert.equal(GuestBank.guestMatches(searchable, "active", "raid"), true);
  assert.equal(GuestBank.guestMatches(searchable, "active", "dungeon"), true);
  assert.equal(GuestBank.guestMatches(searchable, "active", "unscheduled"), true);
  assert.equal(GuestBank.guestMatches(searchable, "archived", "raid"), false);
}

function testEscapedStatisticsAndHistoryMarkup() {
  const markup = GuestBank.guestCardMarkup(guest({
    id: "guest-safe",
    displayName: "Guest <script>alert(1)</script>",
    privateNotes: "Host <b>only</b> & private",
    status: "archived",
    totalAppearances: 2,
    firstAppearance: "2026-08-10",
    mostRecentAppearance: "2026-08-20",
    appearanceHistory: [
      {
        ideaId: "idea-scheduled",
        title: "Scheduled <show>",
        episodeNumber: 12,
        releaseDate: "2026-08-10",
        scheduled: true,
      },
      {
        ideaId: "idea-unscheduled",
        title: "Future & unscheduled",
        episodeNumber: null,
        releaseDate: null,
        scheduled: false,
      },
    ],
  }));
  assert.match(markup, /guest-item archived/);
  assert.match(markup, /Guest &lt;script&gt;alert\(1\)&lt;\/script&gt;/);
  assert.doesNotMatch(markup, /<script>|<b>only<\/b>|Scheduled <show>/);
  assert.match(markup, /Host &lt;b&gt;only&lt;\/b&gt; &amp; private/);
  assert.match(markup, /Total appearances<\/dt><dd>2/);
  assert.match(markup, /Aug 10, 2026/);
  assert.match(markup, /Aug 20, 2026/);
  assert.match(markup, /Episode 12/);
  assert.match(markup, /Future &amp; unscheduled/);
  assert.match(markup, /Unscheduled/);
  assert.match(markup, /Remove all show assignments before deleting this guest/);
  assert.match(markup, /data-action="restore"/);

  const unscheduledOnly = GuestBank.guestCardMarkup(guest({
    totalAppearances: 1,
    appearanceHistory: [{
      ideaId: "idea-future",
      title: "Future show",
      episodeNumber: null,
      releaseDate: null,
      scheduled: false,
    }],
  }));
  assert.equal((unscheduledOnly.match(/Not scheduled/g) || []).length, 2);
  assert.doesNotMatch(unscheduledOnly, /Invalid Date/);
}

function testAuthenticatedResponsivePageContract() {
  const page = fs.readFileSync("guests.html", "utf8");
  const script = fs.readFileSync("js/guests.js", "utf8");
  assert.match(page, /id="protectedContent" style="display:none;"/);
  assert.match(page, /aria-current="page">Guest Bank/);
  assert.match(page, /role="status" aria-live="polite"/);
  assert.match(page, /role="alert"/);
  assert.match(page, /role="group" aria-label="Filter guests by status"/);
  assert.match(page, /maxlength="200"/);
  assert.match(page, /maxlength="8000"/);
  assert.match(page, /@media \(max-width: 1024px\)/);
  assert.match(page, /@media \(max-width: 768px\)/);
  assert.match(page, /js\/auth\.js/);
  assert.match(page, /js\/storage\.js/);
  assert.match(page, /js\/guests\.js/);
  assert.match(script, /Save failed or conflicted/);
  assert.match(script, /Remove every assignment in Show Management/);
  assert.match(script, /Guest archived with appearance history preserved/);
  assert.doesNotMatch(script, /assignGuestToIdea|unassignGuestFromIdea/);

  for (const filename of [
    "config.html",
    "jokes.html",
    "postproduction.html",
    "show_management.html",
    "songs.html",
    "top3.html",
  ]) {
    assert.match(fs.readFileSync(filename, "utf8"), /href="guests\.html">Guest Bank<\/a>/);
  }
}

async function testLifecycleFeedbackAndStorageCalls() {
  let records = [guest({ id: "assigned", totalAppearances: 2 })];
  const notices = [];
  const errors = [];
  const elements = {
    pageNotice: { set textContent(value) { notices.push(value); } },
    guestCount: { textContent: "" },
    guestList: { innerHTML: "" },
    noGuests: { classList: { toggle() {} } },
  };
  let deleted = null;
  let statusChange = null;
  const root = {
    document: { getElementById(id) { return elements[id]; } },
    confirm() { return true; },
    Toast: { error(message) { errors.push(message); } },
    Storage: {
      getGuests() { return records; },
      async deleteGuest(id) {
        deleted = id;
        records = records.filter((record) => record.id !== id);
        return true;
      },
      async setGuestStatus(id, status) {
        statusChange = [id, status];
        records = records.map((record) => record.id === id ? Object.assign({}, record, { status }) : record);
        return true;
      },
    },
  };
  const interactive = require("../js/guests.js");
  const originalDocument = globalThis.document;
  assert.equal(typeof interactive.runLifecycleAction, "function");
  // CommonJS captures globalThis; provide only the narrow test dependencies.
  Object.assign(globalThis, root);
  try {
    await interactive.runLifecycleAction("delete", "assigned");
    assert.equal(deleted, null);
    assert.match(notices.at(-1), /Remove every assignment in Show Management/);
    assert.match(errors.at(-1), /assigned to 2 shows/);

    records = [guest({ id: "clear", totalAppearances: 0 })];
    await interactive.runLifecycleAction("archive", "clear");
    assert.deepEqual(statusChange, ["clear", "archived"]);
    await interactive.runLifecycleAction("delete", "clear");
    assert.equal(deleted, "clear");
    assert.match(notices.at(-1), /Guest deleted/);
  } finally {
    globalThis.document = originalDocument;
    delete globalThis.confirm;
    delete globalThis.Toast;
    delete globalThis.Storage;
  }
}

async function main() {
  testValidationAndSearch();
  testEscapedStatisticsAndHistoryMarkup();
  testAuthenticatedResponsivePageContract();
  await testLifecycleFeedbackAndStorageCalls();
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
