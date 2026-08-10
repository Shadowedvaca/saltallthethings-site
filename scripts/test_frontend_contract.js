"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const SongBankPage = require("../js/songs.js");
const SongPreparation = require("../js/show-song.js");
const EpisodeOverview = require("../js/episode-overview.js");
const Top3BankPage = require("../js/top3-bank.js");
const Top3EpisodePlanning = require("../js/top3-episode.js");

function domHarness() {
  const elements = new Map();
  const listeners = {};
  const body = {
    appendChild(element) {
      if (element.id) elements.set(element.id, element);
    },
  };
  function createElement(tagName) {
    return {
      tagName,
      id: "",
      className: "",
      textContent: "",
      children: [],
      disabled: false,
      classList: {
        add(name) {
          const element = this.element;
          if (!element.className.split(/\s+/).includes(name)) {
            element.className = (element.className + " " + name).trim();
          }
        },
        element: null,
      },
      setAttribute() {},
      appendChild(child) { this.children.push(child); },
      addEventListener(name, handler) { this["on" + name] = handler; },
    };
  }
  return {
    document: {
      body,
      getElementById: (id) => elements.get(id) || null,
      createElement(tagName) {
        const element = createElement(tagName);
        element.classList.element = element;
        return element;
      },
    },
    window: {
      addEventListener(name, handler) { listeners[name] = handler; },
    },
    listeners,
  };
}

function loadStorage(fetchImpl) {
  const errors = [];
  const dom = domHarness();
  const context = {
    Auth: { getToken: () => "test-token" },
    Toast: { error: (message) => errors.push(message) },
    console: { error: () => {} },
    fetch: fetchImpl,
    Promise,
    JSON,
    setTimeout,
    clearTimeout,
    document: dom.document,
    window: dom.window,
  };
  vm.createContext(context);
  const source = fs.readFileSync("js/storage.js", "utf8");
  vm.runInContext(source + "\n;globalThis.Storage = Storage;", context);
  return { storage: context.Storage, errors, dom };
}

function loadShowEngine(storage) {
  const context = { Date, Storage: storage };
  vm.createContext(context);
  const source = fs.readFileSync("js/show-engine.js", "utf8");
  vm.runInContext(source + "\n;globalThis.ShowEngine = ShowEngine;", context);
  return context.ShowEngine;
}

function response(status, data) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => data,
  };
}

function top3PageHarness(fetchImpl) {
  const elements = new Map();
  const formFieldIds = [
    "top3Description", "top3Name", "top3Rules", "top3HostNotes",
    "top3Example1", "top3Example2", "top3Example3",
  ];
  const ids = [
    "pageNotice", "top3Form", "top3FormHeading", "generateTop3Button",
    "saveTop3Button", "cancelTop3EditButton", "proposalNotice", "top3FormError",
    "top3Count", "top3List", "noTop3Concepts", ...formFieldIds,
  ];
  function element(id) {
    const attributes = new Map();
    const item = {
      id,
      value: "",
      textContent: "",
      innerHTML: "",
      className: id === "cancelTop3EditButton" || id === "noTop3Concepts" ? "hidden" : "",
      disabled: false,
      classList: {
        add(name) {
          if (!item.className.split(/\s+/).includes(name)) item.className = (item.className + " " + name).trim();
        },
        remove(name) {
          item.className = item.className.split(/\s+/).filter((candidate) => candidate && candidate !== name).join(" ");
        },
        toggle(name, force) {
          const present = item.className.split(/\s+/).includes(name);
          const enabled = force === undefined ? !present : Boolean(force);
          if (enabled) this.add(name); else this.remove(name);
          return enabled;
        },
      },
      setAttribute(name, value) { attributes.set(name, String(value)); },
      removeAttribute(name) { attributes.delete(name); },
      focus() { item.focused = true; },
      scrollIntoView() {},
      addEventListener() {},
    };
    return item;
  }
  ids.forEach((id) => elements.set(id, element(id)));
  elements.get("top3Form").reset = () => {
    formFieldIds.forEach((id) => { elements.get(id).value = ""; });
  };
  const toasts = [];
  const root = {
    document: {
      getElementById(id) { return elements.get(id) || null; },
      querySelectorAll(selector) {
        if (selector === "#top3Form input, #top3Form textarea") {
          return formFieldIds.map((id) => elements.get(id));
        }
        return [];
      },
    },
    Auth: { getToken: () => "test-token" },
    Toast: {
      success(message) { toasts.push({ type: "success", message }); },
      error(message) { toasts.push({ type: "error", message }); },
    },
    fetch: fetchImpl,
    crypto: { randomUUID: () => "stable-draft-id" },
    confirm: () => true,
  };
  return {
    page: Top3BankPage.createForTesting(root),
    elements,
    toasts,
  };
}

function top3Proposal() {
  return {
    name: "Top Dungeon Snacks",
    description: "Rank three snacks for a dungeon run.",
    rules: "Explain each rank.",
    hostNotes: "Keep the discussion surprising.",
    aiExample: ["Cheese wheel", "Spiced jerky", "Moonberry juice"],
    status: "active",
    source: "ai",
    aiProvider: "claude",
    aiModelId: "claude-test-model",
    aiGeneratedAt: "2026-08-03T12:00:00Z",
  };
}

function canonicalTop3Concept(payload) {
  return {
    ...payload,
    assignedEpisodes: [],
    createdByUserId: 101,
    createdAt: "2026-08-03T12:00:01Z",
    updatedAt: "2026-08-03T12:00:01Z",
  };
}

function state(revision, overrides = {}) {
  return {
    config: {},
    ideas: [],
    jokes: [],
    songs: [],
    guests: [],
    guestAssignments: [],
    showSlots: [],
    assignments: {},
    revision,
    ...overrides,
  };
}

function checkInlineScripts(filename, html) {
  const pattern = /<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/gi;
  for (const match of html.matchAll(pattern)) {
    if (match[1].trim()) new vm.Script(match[1], { filename });
  }
}

function testHomepageHeroSpacingContract(homepage) {
  const heroRule = homepage.match(/\.hero\s*\{([^}]+)\}/);
  const scrollHintRule = homepage.match(/\.scroll-hint\s*\{([^}]+)\}/);

  assert.ok(heroRule, "homepage defines the hero layout");
  assert.ok(scrollHintRule, "homepage defines the Explore scroll hint");
  assert.match(heroRule[1], /display:\s*flex/);
  assert.match(heroRule[1], /flex-direction:\s*column/);
  assert.match(heroRule[1], /gap:\s*clamp\(/);
  assert.match(scrollHintRule[1], /position:\s*relative/);
  assert.match(scrollHintRule[1], /bottom:\s*auto/);
  assert.match(scrollHintRule[1], /flex:\s*0\s+0\s+auto/);
  assert.doesNotMatch(scrollHintRule[1], /position:\s*absolute/);
  assert.match(
    homepage,
    /<p class="hero-subtitle">A little salt for your day<\/p>[\s\S]*<div class="scroll-hint">[\s\S]*<span>Explore<\/span>/,
  );
}

function testScheduleBoardCalendarView() {
  const engine = loadShowEngine();

  assert.deepEqual(
    { ...engine.getInitialCalendarView(new Date(2026, 2, 15, 12)) },
    { month: 2, year: 2026 },
  );
  assert.deepEqual(
    { ...engine.getInitialCalendarView(new Date(2026, 7, 9, 12)) },
    { month: 7, year: 2026 },
  );
  assert.deepEqual(
    { ...engine.getInitialCalendarView(new Date(2026, 0, 1, 12)) },
    { month: 0, year: 2026 },
  );
  assert.deepEqual(
    { ...engine.getInitialCalendarView(new Date(2026, 11, 31, 12)) },
    { month: 11, year: 2026 },
  );
  assert.deepEqual(
    { ...engine.moveCalendarView(2026, 11, 1) },
    { month: 0, year: 2027 },
  );
  assert.deepEqual(
    { ...engine.moveCalendarView(2026, 0, -1) },
    { month: 11, year: 2025 },
  );
}

async function testReleaseDateWaitsForCanonicalPersistence() {
  let slots = [{ id: "slot-1", releaseDate: "2026-08-18" }];
  let releaseSave;
  const saveGate = new Promise((resolve) => { releaseSave = resolve; });
  const storage = {
    getShowSlots: () => slots,
    async saveShowSlots(candidate) {
      await saveGate;
      slots = JSON.parse(JSON.stringify(candidate));
      return true;
    },
  };
  const engine = loadShowEngine(storage);
  const pending = engine.setReleaseDate("slot-1", "2026-08-20");
  assert.equal(slots[0].releaseDateOverride, undefined);
  releaseSave();
  assert.equal((await pending).releaseDateOverride, "2026-08-20");
  assert.equal(slots[0].releaseDateOverride, "2026-08-20");

  storage.saveShowSlots = async () => false;
  assert.equal(await engine.setReleaseDate("slot-1", "2026-08-21"), null);
  assert.equal(slots[0].releaseDateOverride, "2026-08-20");

  storage.saveShowSlots = async (candidate) => {
    slots = JSON.parse(JSON.stringify(candidate));
    return true;
  };
  assert.equal((await engine.resetReleaseDate("slot-1")).releaseDateOverride, undefined);
  assert.equal(slots[0].releaseDateOverride, undefined);
}

async function testSuccessfulCanonicalSave() {
  const requests = [];
  const harness = loadStorage(async (url, options = {}) => {
    requests.push({ url, options });
    if (url === "/api/export") return response(200, state(0));
    assert.equal(options.headers["If-Match"], "0");
    const ideas = JSON.parse(options.body).map((idea) => ({
      ...idea,
      updatedAt: "2026-07-29T12:00:00+00:00",
    }));
    const canonical = state(1, { ideas });
    return response(200, { ok: true, data: ideas, state: canonical, revision: 1 });
  });
  await harness.storage.init();
  const notifications = [];
  const unsubscribe = harness.storage.subscribe((event) => notifications.push({ ...event }));
  assert.equal(await harness.storage.addIdea({ id: "idea-1", status: "draft" }), true);
  assert.equal(harness.storage.getIdeas()[0].updatedAt, "2026-07-29T12:00:00+00:00");
  assert.equal(harness.storage._revision, 1);
  assert.deepEqual(harness.errors, []);
  assert.equal(requests[1].url, "/api/data/ideas");
  assert.deepEqual(notifications, [{ reason: "mutation", revision: 1 }]);
  unsubscribe();
  assert.equal(harness.storage._stateListeners.length, 0);
}

async function testGlobalQueuePreventsOutOfOrderWrites() {
  let revision = 0;
  let inFlight = 0;
  let maxInFlight = 0;
  let releaseFirst;
  const firstGate = new Promise((resolve) => { releaseFirst = resolve; });
  const requests = [];
  const harness = loadStorage(async (url, options = {}) => {
    if (url === "/api/export") return response(200, state(0));
    requests.push({ url, options });
    inFlight += 1;
    maxInFlight = Math.max(maxInFlight, inFlight);
    if (requests.length === 1) await firstGate;
    assert.equal(options.headers["If-Match"], String(revision));
    revision += 1;
    inFlight -= 1;
    const ideas = JSON.parse(options.body);
    return response(200, { ok: true, state: state(revision, { ideas }), revision });
  });
  await harness.storage.init();
  const first = harness.storage.addIdea({ id: "first", status: "draft" });
  const second = harness.storage.addIdea({ id: "second", status: "draft" });
  await Promise.resolve();
  await Promise.resolve();
  assert.equal(requests.length, 1);
  releaseFirst();
  assert.equal(await first, true);
  assert.equal(await second, true);
  assert.equal(requests.length, 2);
  assert.equal(maxInFlight, 1);
  assert.equal(harness.storage.getIdeas().length, 2);
  assert.equal(harness.storage._revision, 2);
}

async function testFailureRollbackRetryAndUnloadGuard() {
  let resolveWrite;
  const writeGate = new Promise((resolve) => { resolveWrite = resolve; });
  const harness = loadStorage(async (url) => {
    if (url === "/api/export") {
      return response(200, state(4, { ideas: [{ id: "existing", status: "draft" }] }));
    }
    await writeGate;
    return response(503, { detail: "isolated development failure" });
  });
  await harness.storage.init();
  const notifications = [];
  harness.storage.subscribe((event) => notifications.push({ ...event, ideaIds: harness.storage.getIdeas().map((idea) => idea.id) }));
  const pending = harness.storage.addIdea({ id: "not-persisted", status: "draft" });
  const cancelled = harness.storage.addJoke({
    id: "also-not-persisted", text: "queued", status: "unused",
  });
  await Promise.resolve();
  const event = { prevented: false, preventDefault() { this.prevented = true; } };
  harness.dom.listeners.beforeunload(event);
  assert.equal(event.prevented, true);
  resolveWrite();
  assert.equal(await pending, false);
  assert.equal(await cancelled, false);
  assert.deepEqual(Array.from(harness.storage.getIdeas(), (idea) => idea.id), ["existing"]);
  assert.deepEqual(Array.from(harness.storage.getJokes()), []);
  const status = harness.dom.document.getElementById("save-status");
  assert.match(status.className, /failed/);
  assert.equal(status.children[0].textContent, "Retry");
  assert.equal(harness.errors.length, 2);
  assert.deepEqual(notifications, [{ reason: "failure-rollback", revision: 4, ideaIds: ["existing"] }]);
}

async function testConflictReloadsAndCancelsStaleQueue() {
  let exportCount = 0;
  let mutationCount = 0;
  const harness = loadStorage(async (url) => {
    if (url === "/api/export") {
      exportCount += 1;
      return response(200, exportCount === 1
        ? state(7, { ideas: [{ id: "initial", status: "draft" }] })
        : state(8, { ideas: [{ id: "server-newer", status: "draft" }] }));
    }
    mutationCount += 1;
    return response(409, {
      detail: { message: "Server data changed", currentRevision: 8 },
    });
  });
  await harness.storage.init();
  const notifications = [];
  harness.storage.subscribe((event) => notifications.push({ ...event, ideaIds: harness.storage.getIdeas().map((idea) => idea.id) }));
  const stale = harness.storage.addIdea({ id: "stale-one", status: "draft" });
  const queued = harness.storage.addIdea({ id: "stale-two", status: "draft" });
  assert.equal(await stale, false);
  assert.equal(await queued, false);
  assert.equal(mutationCount, 1);
  assert.equal(harness.storage.getIdeas()[0].id, "server-newer");
  assert.equal(harness.storage._revision, 8);
  assert.match(harness.dom.document.getElementById("save-status").className, /conflict/);
  assert.deepEqual(notifications, [{ reason: "conflict", revision: 8, ideaIds: ["server-newer"] }]);
}

async function testAtomicScheduleAndImportRoutes() {
  const mutations = [];
  let revision = 2;
  const harness = loadStorage(async (url, options = {}) => {
    if (url === "/api/export") return response(200, state(revision));
    mutations.push({ url, options });
    assert.equal(options.headers["If-Match"], String(revision));
    revision += 1;
    return response(200, { ok: true, state: state(revision), revision });
  });
  await harness.storage.init();
  assert.equal(await harness.storage.assignIdeaToSlot("idea-1", "slot-1"), true);
  assert.equal(await harness.storage.assignSongToIdea("song-1", "idea-1"), true);
  assert.equal(await harness.storage.assignGuestToIdea("guest-1", "idea-1"), true);
  assert.equal(await harness.storage.unassignGuestFromIdea("guest-1", "idea-1"), true);
  assert.equal(await harness.storage.setGuestStatus("guest-1", "archived"), true);
  assert.equal(await harness.storage.deleteGuest("guest-1"), true);
  assert.equal(await harness.storage.importAll({ ideas: [], songs: [], guests: [], guestAssignments: [], showSlots: [], assignments: {} }), true);
  assert.equal(mutations[0].url, "/api/schedule/slot-1/assignment");
  assert.equal(mutations[0].options.method, "PUT");
  assert.equal(mutations[1].url, "/api/songs/song-1/assignment");
  assert.equal(mutations[1].options.method, "PUT");
  assert.deepEqual(mutations.slice(2, 6).map((entry) => [entry.url, entry.options.method]), [
    ["/api/guests/guest-1/assignments/idea-1", "PUT"],
    ["/api/guests/guest-1/assignments/idea-1", "DELETE"],
    ["/api/guests/guest-1/status", "PUT"],
    ["/api/guests/guest-1", "DELETE"],
  ]);
  assert.equal(mutations[6].url, "/api/import");
  assert.equal(mutations[6].options.method, "PUT");
  assert.deepEqual(JSON.parse(mutations[6].options.body), {
    ideas: [], songs: [], guests: [], guestAssignments: [], showSlots: [], assignments: {},
  });
}

async function testGuestDataUsesSharedCanonicalStorage() {
  const guest = {
    id: "guest-1",
    displayName: "Guest One",
    privateNotes: "Private",
    status: "active",
    totalAppearances: 1,
    firstAppearance: null,
    mostRecentAppearance: null,
    appearanceHistory: [{ ideaId: "idea-1", releaseDate: null, scheduled: false }],
  };
  const assignment = { guestId: "guest-1", ideaId: "idea-1", assignedAt: "2026-08-03T00:00:00Z" };
  const harness = loadStorage(async (url) => {
    if (url === "/api/export") {
      return response(200, state(5, { guests: [guest], guestAssignments: [assignment] }));
    }
    throw new Error(`Unexpected request ${url}`);
  });
  await harness.storage.init();
  assert.equal(harness.storage.getGuests()[0].displayName, "Guest One");
  assert.equal(harness.storage.getGuestAssignments()[0].ideaId, "idea-1");
  const exported = harness.storage.exportAll();
  assert.deepEqual(JSON.parse(JSON.stringify(exported.guests)), [guest]);
  assert.deepEqual(JSON.parse(JSON.stringify(exported.guestAssignments)), [assignment]);
}

function testSongBankBrowserStartupWithLexicalDependencies() {
  let authInitCalls = 0;
  const element = { addEventListener() {} };
  const document = {
    getElementById() { return element; },
    querySelector() { return element; },
  };
  const window = { document, confirm: () => true };
  const context = {
    window,
    Auth: { init() { authInitCalls += 1; } },
    Storage: {},
    Toast: {},
    URL,
    Set,
  };
  vm.createContext(context);
  vm.runInContext(fs.readFileSync("js/songs.js", "utf8"), context);
  assert.equal(authInitCalls, 1);
  assert.equal(typeof window.SongBankPage.start, "function");
  assert.equal(typeof window.onStorageReady, "function");
}

async function testSongManagementStorageRoutes() {
  const mutations = [];
  let revision = 11;
  let songs = [{
    id: "song-1",
    artist: "Artist",
    title: "Original",
    youtubeUrl: "https://youtu.be/abcdefghijk",
    privateNotes: "Private",
    status: "unused",
    assignedIdeaId: null,
  }];
  const harness = loadStorage(async (url, options = {}) => {
    if (url === "/api/export") return response(200, state(revision, { songs }));
    mutations.push({ url, options });
    assert.equal(options.headers["If-Match"], String(revision));
    revision += 1;
    if (url === "/api/data/songs") songs = JSON.parse(options.body);
    if (url.endsWith("/status")) songs[0] = { ...songs[0], status: "retired" };
    if (options.method === "DELETE" && url === "/api/songs/song-1") songs = [];
    return response(200, { ok: true, state: state(revision, { songs }), revision });
  });
  await harness.storage.init();
  assert.equal(await harness.storage.updateSong("song-1", { title: "Edited" }), true);
  assert.equal(harness.storage.getSongs()[0].title, "Edited");
  assert.equal(await harness.storage.setSongStatus("song-1", "retired"), true);
  assert.equal(harness.storage.getSongs()[0].status, "retired");
  assert.equal(await harness.storage.deleteSong("song-1"), true);
  assert.deepEqual(Array.from(harness.storage.getSongs()), []);
  assert.deepEqual(mutations.map((entry) => [entry.url, entry.options.method]), [
    ["/api/data/songs", "PUT"],
    ["/api/songs/song-1/status", "PUT"],
    ["/api/songs/song-1", "DELETE"],
  ]);
}

async function testTop3PrivateDataNeverEntersSharedStorage() {
  const harness = loadStorage(async (url) => {
    if (url === "/api/export") {
      return response(200, state(7, {
        top3Submissions: [{ picks: ["hidden-one", "hidden-two", "hidden-three"] }],
      }));
    }
    throw new Error(`Unexpected request ${url}`);
  });
  await harness.storage.init();
  assert.equal(harness.storage.get("top3Submissions"), null);
  assert.equal(Object.prototype.hasOwnProperty.call(harness.storage._cache, "top3Submissions"), false);
  assert.equal(Object.keys(harness.storage.exportAll()).some((key) => key.toLowerCase().startsWith("top3")), false);
}

function testSongManagementPageContract() {
  assert.equal(
    SongBankPage.validateYoutubeUrl("https://youtu.be/abcdefghijk"),
    "https://youtu.be/abcdefghijk",
  );
  assert.equal(
    SongBankPage.validateYoutubeUrl("https://www.youtube.com/watch?v=abcdefghijk"),
    "https://www.youtube.com/watch?v=abcdefghijk",
  );
  assert.throws(() => SongBankPage.validateYoutubeUrl("http://youtu.be/abcdefghijk"), /HTTPS/);
  assert.throws(() => SongBankPage.validateYoutubeUrl("https://example.com/abcdefghijk"), /YouTube/);
  assert.throws(
    () => SongBankPage.validateSongInput({ artist: " ", title: "Title", youtubeUrl: "https://youtu.be/abcdefghijk" }),
    /Artist is required/,
  );
  const context = SongBankPage.ideaContext(
    { assignedIdeaId: "idea-1" },
    [{ id: "idea-1", selectedTitle: "A Salty Episode" }],
    [{ id: "slot-1", episodeNumber: 42 }],
    { "slot-1": "idea-1" },
  );
  assert.equal(context, "Episode 42: A Salty Episode");
  assert.equal(
    SongBankPage.songMatches(
      { status: "unused", artist: "The Band", title: "Track", privateNotes: "memory" },
      "unused",
      "MEMORY",
      "",
    ),
    true,
  );
  const markup = SongBankPage.songCardMarkup({
    id: "song'quoted",
    artist: "<script>alert(1)</script>",
    title: 'A "Song"',
    youtubeUrl: "https://youtu.be/abcdefghijk",
    privateNotes: "<b>private</b>",
    status: "used",
    assignedIdeaId: "idea-1",
    createdAt: "2026-07-31T00:00:00Z",
    updatedAt: "2026-07-31T00:00:00Z",
  }, context);
  assert.doesNotMatch(markup, /<script>|<b>private<\/b>/);
  assert.match(markup, /&lt;script&gt;alert\(1\)&lt;\/script&gt;/);
  assert.match(markup, /song&#039;quoted/);
  assert.match(markup, /Remove assignment/);
  assert.match(markup, /rel="noopener noreferrer"/);
}

function testEpisodeSongPreparationContract() {
  const songs = [
    {
      id: "assigned-song",
      artist: "Assigned <Artist>",
      title: "Current & Song",
      youtubeUrl: "https://youtu.be/abcdefghijk",
      privateNotes: "Private <script>note</script>",
      status: "used",
      assignedIdeaId: "idea-1",
    },
    {
      id: "available-song",
      artist: "Available Artist",
      title: "Available Song",
      youtubeUrl: "https://youtu.be/lmnopqrstuv",
      privateNotes: "Available notes",
      status: "unused",
      assignedIdeaId: null,
    },
    {
      id: "other-used-song",
      artist: "Other Artist",
      title: "Already Used",
      youtubeUrl: "https://youtu.be/zyxwvutsrqp",
      privateNotes: "Other private notes",
      status: "used",
      assignedIdeaId: "idea-2",
    },
    {
      id: "retired-song",
      artist: "Retired Artist",
      title: "Retired Song",
      youtubeUrl: "https://youtu.be/qwertyuiopa",
      privateNotes: "Retired private notes",
      status: "retired",
      assignedIdeaId: null,
    },
  ];
  assert.equal(SongPreparation.songForIdea(songs, "idea-1").id, "assigned-song");
  assert.deepEqual(
    SongPreparation.availableSongs(songs).map((song) => song.id),
    ["available-song"],
  );
  const picker = SongPreparation.renderPicker("idea-1", songs);
  assert.match(picker, /Assigned &lt;Artist&gt;/);
  assert.match(picker, /Private &lt;script&gt;note&lt;\/script&gt;/);
  assert.match(picker, /Replace song/);
  assert.match(picker, /Available Artist/);
  assert.doesNotMatch(picker, /Already Used|Retired Song|Other private notes|Retired private notes/);
  assert.match(picker, /data-song-action="assign"/);
  assert.match(picker, /data-song-action="remove"/);
  assert.match(picker, /rel="noopener noreferrer"/);

  const preparation = SongPreparation.renderPreparation(songs[0]);
  assert.match(preparation, /Episode Song/);
  assert.match(preparation, /Private &lt;script&gt;note&lt;\/script&gt;/);
  assert.doesNotMatch(preparation, /<script>/);
  assert.equal(SongPreparation.renderPreparation(null), "");
}

async function testEpisodeOverviewContract() {
  const summary = "AI summary <unchanged> & ready.";
  const song = Object.freeze({
    id: "internal-song-id",
    artist: "Artist & Friends",
    title: "Title <Live>",
    youtubeUrl: "https://youtu.be/abc123?si=safe&feature=share",
    privateNotes: "PRIVATE SENTINEL",
    status: "used",
    assignedIdeaId: "internal-idea-id",
  });
  const before = JSON.stringify(song);
  const top3 = {
    listName: " Dungeon\n snacks & drinks ",
    contributors: [
      {
        displayName: "Rocket",
        picks: ["Rock one", "Rock two", "Rock three"],
        privateDiscussionNotes: "PRIVATE TOP 3 NOTES",
        submissionId: "internal-submission",
      },
      {
        displayName: "Trog",
        picks: ["Trog one", "Trog two", "Trog three"],
      },
      {
        displayName: "Guest <One>",
        picks: ["Guest\nfirst", "Guest second", "Guest third"],
        externalType: "guest",
        enteredByUserId: 999,
      },
      { displayName: "Missing", picks: [] },
    ],
    description: "PLANNING DESCRIPTION",
    rules: "PLANNING RULES",
    aiExample: ["AI ONE", "AI TWO", "AI THREE"],
  };
  const top3Before = JSON.stringify(top3);
  const expected = summary
    + "\n\nFeatured song: Artist & Friends — Title <Live>"
    + "\nYouTube: https://youtu.be/abc123?si=safe&feature=share"
    + "\n\nTop 3: Dungeon snacks & drinks"
    + "\n\nRocket"
    + "\n1. Rock one\n2. Rock two\n3. Rock three"
    + "\n\nTrog"
    + "\n1. Trog one\n2. Trog two\n3. Trog three"
    + "\n\nGuest <One>"
    + "\n1. Guest first\n2. Guest second\n3. Guest third";
  const composed = EpisodeOverview.compose(summary, song, top3);
  assert.equal(composed, expected);
  assert.equal(EpisodeOverview.compose(summary, null), summary);
  assert.equal(JSON.stringify(song), before);
  assert.equal(JSON.stringify(top3), top3Before);
  assert.doesNotMatch(composed, /PRIVATE SENTINEL|internal-song-id|internal-idea-id|used|PRIVATE TOP 3 NOTES|internal-submission|PLANNING|AI ONE|enteredByUserId|Missing/);

  const markup = EpisodeOverview.render(composed);
  assert.match(markup, /Spotify Overview/);
  assert.match(markup, /aria-describedby="spotifyOverviewStatus"/);
  assert.match(markup, /role="status" aria-live="polite"/);
  assert.match(markup, /Title &lt;Live&gt;/);
  assert.match(markup, /Guest &lt;One&gt;/);
  assert.doesNotMatch(markup, /Guest <One>/);
  assert.match(markup, /si=safe&amp;feature=share/);
  assert.doesNotMatch(markup, /PRIVATE SENTINEL|<Live>/);

  let clipboardPayload = null;
  assert.equal(await EpisodeOverview.copy(composed, {
    clipboard: { writeText: async (text) => { clipboardPayload = text; } },
  }, null), "clipboard");
  assert.equal(clipboardPayload, expected);
  assert.equal(JSON.stringify(song), before);
  assert.equal(JSON.stringify(top3), top3Before);

  let fallbackPayload = null;
  let removed = false;
  const textarea = {
    value: "",
    style: {},
    setAttribute() {},
    select() { fallbackPayload = this.value; },
  };
  const fallbackDocument = {
    createElement: () => textarea,
    execCommand(command) { assert.equal(command, "copy"); return true; },
    body: {
      appendChild(element) { assert.equal(element, textarea); },
      removeChild(element) { assert.equal(element, textarea); removed = true; },
    },
  };
  assert.equal(await EpisodeOverview.copy(composed, {}, fallbackDocument), "fallback");
  assert.equal(fallbackPayload, expected);
  assert.equal(removed, true);
  assert.equal(await EpisodeOverview.copy(composed, {
    clipboard: { writeText: async () => { throw new Error("permission denied"); } },
  }, fallbackDocument), "fallback");
  await assert.rejects(EpisodeOverview.copy(composed, {}, {
    createElement: () => textarea,
    execCommand: () => false,
    body: { appendChild() {}, removeChild() {} },
  }), /did not copy/);
}

function testTop3BankPageContract() {
  assert.deepEqual(Top3BankPage.normalizeExamples(["", "", ""], false), []);
  assert.deepEqual(
    Top3BankPage.normalizeExamples([" First ", "Second", "Third"], true),
    ["First", "Second", "Third"],
  );
  assert.throws(
    () => Top3BankPage.normalizeExamples(["One", "", "Three"], false),
    /all three fictional examples/,
  );
  assert.throws(
    () => Top3BankPage.normalizeExamples(["One", "one", "Three"], true),
    /must be distinct/,
  );
  assert.throws(
    () => Top3BankPage.validateConceptInput({ description: "Valid" }, false),
    /Shared name is required/,
  );
  const manual = Top3BankPage.validateConceptInput({
    name: " Manual concept ",
    description: " Shared definition ",
    rules: " Optional rules ",
    hostNotes: " Planning context ",
    aiExample: ["", "", ""],
  }, false);
  assert.deepEqual(manual.aiExample, []);
  assert.equal(manual.name, "Manual concept");

  const concept = {
    id: "concept-1",
    name: "Escaping <script>",
    description: "Description & definition",
    rules: "No <b>markup</b>",
    hostNotes: "Crew <private> context",
    aiExample: ["Example <one>", "Example two", "Example three"],
    status: "active",
    source: "ai",
    aiProvider: "claude",
    aiModelId: "model-id",
    aiGeneratedAt: "2026-08-01T00:00:00Z",
    assignedEpisodes: [{ ideaId: "idea-1", title: "Episode <title>", episodeNumber: "42" }],
  };
  const markup = Top3BankPage.conceptCardMarkup(concept);
  assert.doesNotMatch(markup, /<script>|<b>markup|<private>|<title>/);
  assert.match(markup, /Escaping &lt;script&gt;/);
  assert.match(markup, /Fictional examples — not participant picks/);
  assert.match(markup, /Assignment metadata only; participant picks are never shown here/);
  assert.match(markup, /Episode 42: Episode &lt;title&gt;/);
  assert.doesNotMatch(markup, /privateDiscussionNotes|participant submission/);
  assert.equal(
    Top3BankPage.conceptMatches(concept, "active", "episode 42", ""),
    true,
  );
  const payload = Top3BankPage.conceptPayload(concept);
  assert.equal(payload.aiProvider, "claude");
  assert.equal(payload.aiModelId, "model-id");
  assert.equal(Object.prototype.hasOwnProperty.call(payload, "assignedEpisodes"), false);
  assert.equal(Object.prototype.hasOwnProperty.call(payload, "picks"), false);

  const page = fs.readFileSync("top3.html", "utf8");
  const script = fs.readFileSync("js/top3-bank.js", "utf8");
  checkInlineScripts("top3.html", page);
  assert.match(page, /aria-current="page"/);
  assert.match(page, /role="status" aria-live="polite"/);
  assert.match(page, /role="alert"/);
  assert.match(page, /Fictional examples — not participant picks/);
  assert.match(page, /Nothing is banked until you explicitly save/);
  assert.match(page, /@media \(max-width: 1024px\)/);
  assert.match(page, /js\/top3-bank\.js/);
  assert.match(script, /\/ai\/top3-concept/);
  assert.match(script, /Regenerate AI Proposal/);
  assert.match(script, /Save AI Proposal/);
  assert.match(script, /method: existing \? 'PUT' : 'POST'/);
  assert.match(script, /method: 'DELETE', mutation: true/);
  assert.match(script, /await loadConcepts\(\)/);
  assert.match(script, /The Top 3 Bank changed on the server/);
  assert.match(script, /Your workshop entries are unchanged/);
  assert.match(script, /Your workshop remains available/);
  assert.match(script, /editingConceptId = concept\.id/);
  assert.match(script, /acceptedProvenance/);

  for (const filename of ["config.html", "jokes.html", "postproduction.html", "show_management.html", "songs.html", "top3.html"]) {
    assert.match(fs.readFileSync(filename, "utf8"), /href="top3\.html"/);
  }
}

async function testInitialTop3AIProposalReconcilesUnrelatedRevisionAndSaves() {
  let revision = 5;
  const concepts = [];
  const mutationRequests = [];
  const harness = top3PageHarness(async (url, options = {}) => {
    if (url === "/api/top3/concepts" && (!options.method || options.method === "GET")) {
      return response(200, { revision, concepts: JSON.parse(JSON.stringify(concepts)) });
    }
    if (url === "/api/ai/top3-concept") return response(200, top3Proposal());
    if (url === "/api/top3/concepts" && options.method === "POST") {
      mutationRequests.push({
        ifMatch: options.headers["If-Match"],
        body: JSON.parse(options.body),
      });
      if (options.headers["If-Match"] !== String(revision)) {
        return response(409, { detail: { message: "Server data changed", currentRevision: revision } });
      }
      concepts.push(canonicalTop3Concept(JSON.parse(options.body)));
      revision += 1;
      return response(201, { revision, concept: concepts[0] });
    }
    throw new Error(`Unexpected Top 3 request: ${options.method || "GET"} ${url}`);
  });

  await harness.page.onStorageReady();
  harness.elements.get("top3Description").value = "Rank dungeon snacks.";
  await harness.page.generateProposal();
  revision = 6; // Unrelated server data changed after generation; the bank did not.
  await harness.page.saveConcept({ preventDefault() {} });

  assert.equal(mutationRequests.length, 2);
  assert.deepEqual(mutationRequests.map((request) => request.ifMatch), ["5", "6"]);
  assert.equal(mutationRequests[0].body.id, "top3-stable-draft-id");
  assert.equal(mutationRequests[1].body.id, mutationRequests[0].body.id);
  assert.equal(concepts.length, 1);
  assert.equal(concepts[0].name, "Top Dungeon Snacks");
  assert.equal(harness.elements.get("top3Name").value, "");
  assert.deepEqual(harness.toasts, [{ type: "success", message: "Top 3 concept banked." }]);
}

async function testTop3AIProposalPreservesRealConflictForDeliberateRetry() {
  let revision = 10;
  const concepts = [];
  const mutationRequests = [];
  const harness = top3PageHarness(async (url, options = {}) => {
    if (url === "/api/top3/concepts" && (!options.method || options.method === "GET")) {
      return response(200, { revision, concepts: JSON.parse(JSON.stringify(concepts)) });
    }
    if (url === "/api/ai/top3-concept") return response(200, top3Proposal());
    if (url === "/api/top3/concepts" && options.method === "POST") {
      mutationRequests.push({
        ifMatch: options.headers["If-Match"],
        body: JSON.parse(options.body),
      });
      if (options.headers["If-Match"] !== String(revision)) {
        return response(409, { detail: { message: "Server data changed", currentRevision: revision } });
      }
      concepts.push(canonicalTop3Concept(JSON.parse(options.body)));
      revision += 1;
      return response(201, { revision, concept: concepts[concepts.length - 1] });
    }
    throw new Error(`Unexpected Top 3 request: ${options.method || "GET"} ${url}`);
  });

  await harness.page.onStorageReady();
  harness.elements.get("top3Description").value = "Rank dungeon snacks.";
  await harness.page.generateProposal();
  concepts.push(canonicalTop3Concept({
    ...top3Proposal(),
    id: "other-client-concept",
    name: "Other client concept",
  }));
  revision = 11;

  await harness.page.saveConcept({ preventDefault() {} });
  assert.equal(mutationRequests.length, 1);
  assert.match(harness.elements.get("top3FormError").textContent, /Top 3 Bank changed on the server/);
  assert.equal(harness.elements.get("top3Name").value, "Top Dungeon Snacks");
  assert.deepEqual(harness.toasts, []);

  await harness.page.saveConcept({ preventDefault() {} });
  assert.equal(mutationRequests.length, 2);
  assert.deepEqual(mutationRequests.map((request) => request.ifMatch), ["10", "11"]);
  assert.equal(mutationRequests[1].body.id, mutationRequests[0].body.id);
  assert.equal(concepts.length, 2);
  assert.equal(concepts.filter((concept) => concept.id === mutationRequests[0].body.id).length, 1);
  assert.deepEqual(harness.toasts, [{ type: "success", message: "Top 3 concept banked." }]);
}

function testTop3BankBrowserStartupWithLexicalDependencies() {
  let authInitCalls = 0;
  const element = { addEventListener() {} };
  const document = {
    getElementById() { return element; },
    querySelector() { return element; },
    querySelectorAll() { return []; },
  };
  const window = {
    document,
    confirm: () => true,
    crypto: { randomUUID: () => "test-id" },
    fetch: async () => response(200, { revision: 0, concepts: [] }),
  };
  const context = {
    window,
    Auth: { init() { authInitCalls += 1; }, getToken: () => "test-token" },
    Toast: { success() {}, error() {} },
    Set,
    Date,
    Math,
    encodeURIComponent,
  };
  vm.createContext(context);
  vm.runInContext(fs.readFileSync("js/top3-bank.js", "utf8"), context);
  assert.equal(authInitCalls, 1);
  assert.equal(typeof window.Top3BankPage.start, "function");
  assert.equal(typeof window.onStorageReady, "function");
}

function testTop3EpisodePlanningContract() {
  assert.deepEqual(
    Top3EpisodePlanning.validatePicks([" First ", "Second", "Third"]),
    ["First", "Second", "Third"],
  );
  assert.throws(() => Top3EpisodePlanning.validatePicks(["One", "Two"]), /exactly three/);
  assert.throws(() => Top3EpisodePlanning.validatePicks(["One", "", "Three"]), /all three/);
  assert.throws(() => Top3EpisodePlanning.validatePicks(["One", "one", "Three"]), /distinct/);

  const assignment = {
    ideaId: "idea-1",
    concept: {
      id: "concept-1",
      name: "Dungeon <snacks>",
      description: "Rank & explain",
      rules: "No <script>rules</script>",
      aiExample: ["Example <one>", "Example two", "Example three"],
      status: "active",
    },
    contributors: [
      {
        submissionId: "mine",
        contributorType: "account",
        displayName: "Rocket",
        complete: true,
        isCurrentUser: true,
        picks: ["My first", "My second", "My third"],
        privateDiscussionNotes: "my private notes",
      },
      {
        submissionId: "other",
        contributorType: "account",
        displayName: "Trog <host>",
        complete: true,
        isCurrentUser: false,
        picks: ["must-not-render-one", "must-not-render-two", "must-not-render-three"],
        privateDiscussionNotes: "must-not-render-notes",
      },
      {
        submissionId: "revealed-other",
        contributorType: "account",
        displayName: "observer",
        complete: true,
        isCurrentUser: false,
        revealed: true,
        revealedAt: "2026-08-01T12:00:00Z",
        picks: ["Revealed first", "Revealed second", "Revealed third"],
        privateDiscussionNotes: "revealed notes",
      },
      {
        submissionId: "external-one",
        contributorType: "external",
        externalType: "guest",
        displayName: "Guest <One>",
        complete: true,
        picks: ["Guest <first>", "Guest second", "Guest third"],
        privateDiscussionNotes: "Shared <notes>",
      },
    ],
  };
  const markup = Top3EpisodePlanning.assignmentMarkup("idea-1", assignment);
  assert.match(markup, /Dungeon &lt;snacks&gt;/);
  assert.match(markup, /Rank &amp; explain/);
  assert.doesNotMatch(markup, /<script>|Trog <host>/);
  assert.match(markup, /Shared fictional example/);
  assert.match(markup, /not a participant submission/);
  assert.match(markup, /My first/);
  assert.match(markup, /my private notes/);
  assert.match(markup, /Trog &lt;host&gt;/);
  assert.match(markup, /Ready — hidden/);
  assert.match(markup, /Reveal picks/);
  assert.match(markup, /Revealed only to you/);
  assert.match(markup, /Revealed first/);
  assert.match(markup, /revealed notes/);
  assert.match(markup, /Guest &lt;One&gt;/);
  assert.match(markup, /Guest &lt;first&gt;/);
  assert.match(markup, /Shared &lt;notes&gt;/);
  assert.match(markup, /Any authenticated host may edit or remove/);
  assert.doesNotMatch(markup, /must-not-render/);
  assert.match(markup, /permanently clears every submission/);
  Top3EpisodePlanning._state.episodes.set("idea-summary", assignment);
  const showSummary = Top3EpisodePlanning.summaryMarkup("idea-summary");
  Top3EpisodePlanning._state.episodes.delete("idea-summary");
  assert.match(showSummary, /Top 3 concept/);
  assert.match(showSummary, /data-top3-idea-id="idea-summary"/);
  assert.match(showSummary, /Dungeon &lt;snacks&gt;/);
  assert.match(showSummary, /Rank &amp; explain/);
  assert.match(showSummary, /Rules:/);
  assert.match(showSummary, /not participant picks/);
  assert.match(showSummary, /Participant results/);
  assert.match(showSummary, /My first|my private notes/);
  assert.match(showSummary, /Revealed first|revealed notes/);
  assert.match(showSummary, /Guest &lt;first&gt;|Shared &lt;notes&gt;/);
  assert.match(showSummary, /Ready — hidden/);
  assert.match(showSummary, /data-top3-action="reveal"/);
  assert.match(showSummary, /Reveal picks/);
  assert.doesNotMatch(showSummary, /must-not-render/);

  const page = fs.readFileSync("show_management.html", "utf8");
  const script = fs.readFileSync("js/top3-episode.js", "utf8");
  assert.match(page, /js\/top3-episode\.js/);
  assert.match(page, /Top3EpisodePlanning\.render\(idea\.id\)/);
  assert.match(page, /await Top3EpisodePlanning\.start/);
  assert.match(page, /await Top3EpisodePlanning\.loadEpisode\(idea\.id\)/);
  assert.match(page, /Top3EpisodePlanning\.summaryMarkup\(idea\.id\)/);
  assert.match(page, /@media \(max-width: 800px\)/);
  assert.match(script, /\/top3\/episodes\/.*\/assignment/);
  assert.match(script, /\/top3\/episodes\/.*\/submission/);
  assert.match(script, /\/reveals\//);
  assert.match(script, /\/external-submissions/);
  assert.match(script, /\/spotify-results/);
  assert.match(script, /This cannot be undone/);
  assert.match(script, /headers\['If-Match'\]/);
  assert.match(script, /await loadEpisode\(ideaId\)/);
  assert.match(script, /changed on the server/);
  assert.match(script, /Every existing Top 3 submission/);
  assert.match(script, /addEventListener\('click', handleClick, true\)/);
  assert.match(script, /root\.fetch\('\/api' \+ path/);
  assert.doesNotMatch(script, /Storage\./);
}

async function testTop3EpisodeBrowserActionsUseViewerScopedApi() {
  const listeners = {};
  const requests = [];
  let revision = 40;
  let confirmResult = true;
  const concept = {
    id: "concept-1",
    name: "Shared concept",
    description: "Shared description",
    rules: "Shared rules",
    aiExample: [],
    status: "active",
  };
  let assignment = null;
  const document = {
    addEventListener(type, handler, capture) { listeners[type] = { handler, capture }; },
  };
  const fetch = async (url, options = {}) => {
    requests.push({ url, options });
    if (url === "/api/top3/concepts") {
      return response(200, { revision, concepts: [concept] });
    }
    if (url === "/api/top3/episodes/idea-1" && (!options.method || options.method === "GET")) {
      return response(200, { revision, assignment });
    }
    if (url === "/api/top3/episodes/idea-1/assignment" && options.method === "PUT") {
      assert.equal(options.headers["If-Match"], String(revision));
      assert.deepEqual(JSON.parse(options.body), { conceptId: "concept-1" });
      revision += 1;
      assignment = {
        ideaId: "idea-1",
        concept,
        contributors: [{
          submissionId: null,
          contributorType: "account",
          displayName: "Rocket",
          complete: false,
          isCurrentUser: true,
        }],
      };
      return response(200, { revision, assignment });
    }
    if (url === "/api/top3/episodes/idea-1/submission" && options.method === "PUT") {
      assert.equal(options.headers["If-Match"], String(revision));
      const payload = JSON.parse(options.body);
      assert.deepEqual(payload, {
        id: "top3-submission-browser-id",
        picks: ["First", "Second", "Third"],
        privateDiscussionNotes: "Only my notes",
      });
      assert.equal(Object.prototype.hasOwnProperty.call(payload, "accountUserId"), false);
      revision += 1;
      assignment = {
        ideaId: "idea-1",
        concept,
        contributors: [{
          submissionId: payload.id,
          contributorType: "account",
          displayName: "Rocket",
          complete: true,
          isCurrentUser: true,
          picks: payload.picks,
          privateDiscussionNotes: payload.privateDiscussionNotes,
        }],
      };
      return response(200, { revision, assignment });
    }
    if (url === "/api/top3/episodes/idea-1/reveals/hidden-other" && options.method === "POST") {
      assert.equal(options.headers["If-Match"], String(revision));
      revision += 1;
      const hidden = assignment.contributors.find((item) => item.submissionId === "hidden-other");
      Object.assign(hidden, {
        revealed: true,
        revealedAt: "2026-08-01T12:00:00Z",
        picks: ["Hidden first", "Hidden second", "Hidden third"],
        privateDiscussionNotes: "Hidden notes",
      });
      return response(200, { revision, assignment });
    }
    if (url === "/api/top3/episodes/idea-1/external-submissions" && options.method === "POST") {
      assert.equal(options.headers["If-Match"], String(revision));
      const payload = JSON.parse(options.body);
      assert.deepEqual(payload, {
        id: "top3-submission-external-browser-id",
        displayName: "Guest Browser",
        externalType: "guest",
        picks: ["Guest First", "Guest Second", "Guest Third"],
        privateDiscussionNotes: "Shared browser notes",
      });
      assert.equal(Object.prototype.hasOwnProperty.call(payload, "accountUserId"), false);
      revision += 1;
      assignment.contributors.push({
        submissionId: payload.id,
        contributorType: "external",
        displayName: payload.displayName,
        externalType: payload.externalType,
        complete: true,
        picks: payload.picks,
        privateDiscussionNotes: payload.privateDiscussionNotes,
      });
      return response(201, { revision, assignment });
    }
    if (url === "/api/top3/episodes/idea-1/spotify-results" && options.method === "POST") {
      assert.deepEqual(JSON.parse(options.body), { purpose: "spotify-overview" });
      assert.equal(Object.prototype.hasOwnProperty.call(options.headers, "If-Match"), false);
      return response(200, {
        top3: {
          listName: concept.name,
          contributors: [{ displayName: "Guest Browser", picks: ["Guest First", "Guest Second", "Guest Third"] }],
        },
      });
    }
    throw new Error(`Unexpected Top 3 request ${url}`);
  };
  let uuidCounter = 0;
  const window = {
    document,
    confirm: () => confirmResult,
    crypto: { randomUUID: () => (++uuidCounter === 1 ? "browser-id" : "external-browser-id") },
    fetch,
  };
  const context = {
    window,
    Auth: { getToken: () => "viewer-token" },
    Toast: { success() {}, error() {} },
    Map,
    Set,
    Date,
    Math,
    Array,
    JSON,
    encodeURIComponent,
  };
  vm.createContext(context);
  vm.runInContext(fs.readFileSync("js/top3-episode.js", "utf8"), context);
  const api = window.Top3EpisodePlanning;
  let detailRefreshIdeaId = null;
  await api.start(() => {}, async (ideaId) => { detailRefreshIdeaId = ideaId; });
  await api.loadEpisode("idea-1");
  assert.equal(listeners.click.capture, true);

  const section = {
    dataset: { top3IdeaId: "idea-1" },
    querySelector(selector) {
      if (selector === "[data-top3-concept]") return { value: "concept-1" };
      throw new Error(`Unexpected section selector ${selector}`);
    },
  };
  const assignButton = {
    dataset: { top3Action: "assign" },
    closest(selector) { return selector === "[data-top3-idea-id]" ? section : null; },
  };
  await listeners.click.handler({
    target: { closest: () => assignButton },
    preventDefault() {},
    stopPropagation() {},
  });

  const form = {
    closest(selector) { return selector === "[data-top3-idea-id]" ? section : selector === "[data-top3-form]" ? form : null; },
    querySelectorAll() {
      return ["First", "Second", "Third"].map((value, index) => ({ value, dataset: { top3Pick: String(index) } }));
    },
    querySelector(selector) {
      if (selector === "[data-top3-notes]") return { value: "Only my notes" };
      throw new Error(`Unexpected form selector ${selector}`);
    },
  };
  await listeners.submit.handler({
    target: { closest: (selector) => selector === "[data-top3-form]" ? form : null },
    preventDefault() {},
    stopPropagation() {},
  });

  assert.deepEqual(await api.loadSpotifyResults("idea-1"), {
    listName: concept.name,
    contributors: [{ displayName: "Guest Browser", picks: ["Guest First", "Guest Second", "Guest Third"] }],
  });

  assignment.contributors.push({
    submissionId: "hidden-other",
    contributorType: "account",
    displayName: "Trog",
    complete: true,
    isCurrentUser: false,
    revealed: false,
  });
  api._state.episodes.set("idea-1", assignment);
  const revealButton = {
    dataset: { top3Action: "reveal", submissionId: "hidden-other", displayName: "Trog" },
    closest(selector) { return selector === "[data-top3-idea-id]" ? section : null; },
  };
  confirmResult = false;
  const beforeCancel = requests.length;
  await listeners.click.handler({
    target: { closest: () => revealButton },
    preventDefault() {},
    stopPropagation() {},
  });
  assert.equal(requests.length, beforeCancel);
  assert.equal(assignment.contributors.find((item) => item.submissionId === "hidden-other").revealed, false);

  confirmResult = true;
  await listeners.click.handler({
    target: { closest: () => revealButton },
    preventDefault() {},
    stopPropagation() {},
  });
  assert.equal(assignment.contributors.find((item) => item.submissionId === "hidden-other").revealed, true);
  assert.equal(detailRefreshIdeaId, "idea-1");

  const externalForm = {
    closest(selector) { return selector === "[data-top3-idea-id]" ? section : selector === "[data-top3-external-form]" ? externalForm : null; },
    querySelectorAll() {
      return ["Guest First", "Guest Second", "Guest Third"].map((value, index) => ({ value, dataset: { top3ExternalPick: String(index) } }));
    },
    querySelector(selector) {
      if (selector === "[data-top3-external-name]") return { value: "Guest Browser" };
      if (selector === "[data-top3-external-type]") return { value: "guest" };
      if (selector === "[data-top3-external-notes]") return { value: "Shared browser notes" };
      throw new Error(`Unexpected external form selector ${selector}`);
    },
  };
  await listeners.submit.handler({
    target: { closest: (selector) => selector === "[data-top3-external-form]" ? externalForm : null },
    preventDefault() {},
    stopPropagation() {},
  });

  const mutations = requests.filter((request) => request.options.method === "PUT");
  assert.deepEqual(mutations.map((request) => request.url), [
    "/api/top3/episodes/idea-1/assignment",
    "/api/top3/episodes/idea-1/submission",
  ]);
  assert.equal(requests.some((request) => request.url.endsWith("/reveals/hidden-other") && request.options.method === "POST"), true);
  assert.equal(requests.some((request) => request.url.endsWith("/external-submissions") && request.options.method === "POST"), true);
  assert.equal(requests.some((request) => request.url.endsWith("/spotify-results") && request.options.method === "POST"), true);
  for (const request of requests) {
    assert.equal(request.options.headers.Authorization, "Bearer viewer-token");
    assert.match(request.url, /^\/api\//);
  }
}

async function main() {
  const homepage = fs.readFileSync("index.html", "utf8");
  const showManagement = fs.readFileSync("show_management.html", "utf8");
  const jokesPage = fs.readFileSync("jokes.html", "utf8");
  const songsPage = fs.readFileSync("songs.html", "utf8");
  const configPage = fs.readFileSync("config.html", "utf8");
  const songBankScript = fs.readFileSync("js/songs.js", "utf8");
  const guestBankScript = fs.readFileSync("js/guests.js", "utf8");
  checkInlineScripts("show_management.html", showManagement);
  checkInlineScripts("jokes.html", jokesPage);
  checkInlineScripts("songs.html", songsPage);
  checkInlineScripts("config.html", configPage);
  testHomepageHeroSpacingContract(homepage);
  testScheduleBoardCalendarView();
  assert.match(showManagement, /const initialCalendarView = ShowEngine\.getInitialCalendarView\(\)/);
  assert.match(showManagement, /let currentMonth = initialCalendarView\.month/);
  assert.match(showManagement, /let currentYear = initialCalendarView\.year/);
  assert.match(showManagement, /ShowEngine\.moveCalendarView\(currentYear, currentMonth, delta\)/);
  for (const page of [showManagement, jokesPage, songsPage, configPage, fs.readFileSync("postproduction.html", "utf8")]) {
    assert.match(page, /href="songs\.html"/);
  }
  assert.match(songsPage, /aria-current="page"/);
  assert.match(songsPage, /role="status" aria-live="polite"/);
  assert.match(songsPage, /role="alert"/);
  assert.match(songsPage, /data-action="cancel-edit"/);
  assert.match(songsPage, /js\/songs\.js/);
  assert.match(showManagement, /!config\.claudeApiKeyConfigured/);
  assert.match(showManagement, /!config\.openaiApiKeyConfigured/);
  assert.match(showManagement, /await Storage\.addIdea\(idea\)/);
  assert.match(showManagement, /await Storage\.updateIdea\(ideaId/);
  assert.match(showManagement, /await Storage\.assignJokeToIdea\(jokeId, ideaId\)/);
  assert.match(showManagement, /await Storage\.freeJoke\(jokeId\)/);
  assert.match(showManagement, /js\/show-song\.js/);
  assert.match(showManagement, /js\/episode-overview\.js/);
  assert.match(showManagement, /SongPreparation\.renderPicker\(idea\.id, Storage\.getSongs\(\)\)/);
  assert.match(showManagement, /SongPreparation\.renderPreparation\(assignedSong\)/);
  assert.match(showManagement, /EpisodeOverview\.compose\(idea\.summary, assignedSong, top3SpotifyResults\)/);
  assert.match(showManagement, /await Top3EpisodePlanning\.loadSpotifyResults\(idea\.id\)/);
  assert.match(showManagement, /await EpisodeOverview\.copy\(currentSpotifyOverview, navigator, document\)/);
  assert.match(showManagement, /Copy failed\. Select the overview text and copy it manually\./);
  assert.match(showManagement, /await Storage\.assignSongToIdea\(songId, ideaId\)/);
  assert.match(showManagement, /await Storage\.freeSong\(songId\)/);
  assert.match(showManagement, /const expandedIdeas = new Set\(\)/);
  assert.ok(showManagement.includes("const isExpanded = expandedIdeas.has(idea.id);"));
  assert.ok(showManagement.includes("(isExpanded ? ' expanded' : '')"));
  assert.doesNotMatch(showManagement, /lastProcessedId|autoExpand/);
  assert.ok(showManagement.includes("function enterEditMode(ideaId) {"));
  assert.ok(showManagement.includes("if (expanded) expandedIdeas.add(ideaId);"));
  assert.ok(showManagement.includes("else expandedIdeas.delete(ideaId);"));
  assert.ok(showManagement.includes("await Top3EpisodePlanning.start(function() {"));
  assert.match(showManagement, /href="#idea\/.*openIdeaDisplay/);
  assert.match(showManagement, /function openIdeaDisplay\(ideaId\)/);
  assert.match(showManagement, /var slot = getScheduleInfoForIdea\(ideaId\)/);
  assert.doesNotMatch(showManagement, /getSlotForIdea/);
  assert.match(showManagement, /return slot \? openShowDisplay\(slot\.id\) : openShowDisplay\(null, ideaId\)/);
  assert.match(showManagement, /var slot = slotId \? slots\.find/);
  assert.match(showManagement, /slot \? slot\.episodeNumber : 'Unscheduled'/);
  assert.match(showManagement, /slot \? getNextShowInfo\(slot\.recordDate\) : null/);
  assert.match(showManagement, /location\.hash\.startsWith\('#idea\/'\)/);
  assert.match(showManagement, /function rerenderIdeasPreservingExpansion\(ideaId\)/);
  assert.match(showManagement, /selectTitle[\s\S]*rerenderIdeasPreservingExpansion\(ideaId\)/);
  assert.match(showManagement, /selectJokeForIdea[\s\S]*rerenderIdeasPreservingExpansion\(ideaId\)/);
  assert.match(showManagement, /selectSongForIdea[\s\S]*rerenderIdeasPreservingExpansion\(ideaId\)/);
  assert.match(showManagement, /clearSongFromIdea[\s\S]*rerenderIdeasPreservingExpansion\(ideaId\)/);
  assert.match(showManagement, /<details onclick="event\.stopPropagation\(\)"><summary[^>]*>Raw Notes/);
  assert.match(SongPreparation.renderPicker("idea-1", [
    { id: "assigned", artist: "Assigned", title: "Song", status: "used", assignedIdeaId: "idea-1" },
    { id: "available", artist: "Available", title: "Song", status: "unused", assignedIdeaId: null },
  ]), /song-replace" onclick="event\.stopPropagation\(\)"/);
  assert.match(showManagement, /Replace .* with/);
  assert.match(showManagement, /Remove .* from this episode/);
  assert.match(showManagement, /The latest server data is shown/);
  assert.match(showManagement, /await Storage\.deleteIdea\(ideaId\)/);
  assert.match(showManagement, /await Storage\.assignIdeaToSlot\(ideaId, slotId\)/);
  assert.match(showManagement, /await Storage\.unassignSlot\(slotId\)/);
  assert.doesNotMatch(showManagement, /freeJokesForIdea/);
  assert.doesNotMatch(showManagement, /lastModified/);
  assert.match(jokesPage, /!config\.claudeApiKeyConfigured/);
  assert.match(jokesPage, /!config\.openaiApiKeyConfigured/);
  assert.match(configPage, /row\.dataset\.segmentId = seg\.id/);
  assert.match(configPage, /const id = row\.dataset\.segmentId/);
  assert.match(configPage, /segment_.*Storage\.generateId\(\)/);
  assert.match(configPage, /await Storage\.importAll\(\{/);
  assert.match(configPage, /Storage\.subscribe\(loadConfig\)/);
  assert.match(jokesPage, /Storage\.subscribe\(renderJokes\)/);
  assert.match(showManagement, /Storage\.subscribe\(reconcileVisibleStorageState\)/);
  assert.match(songBankScript, /Storage\.subscribe\(renderSongs\)/);
  assert.match(guestBankScript, /Storage\.subscribe\(renderGuests\)/);
  assert.match(showManagement, /async function updateReleaseDate/);
  assert.match(showManagement, /await ShowEngine\.setReleaseDate/);
  assert.match(showManagement, /latest server state is displayed/);
  assert.doesNotMatch(configPage, /Promise\.all\(\[\s*Storage\.saveIdeas/);
  assert.match(showManagement, /data-segment-id=/);
  assert.match(showManagement, /var segmentId = segEl\.dataset\.segmentId/);
  assert.doesNotMatch(showManagement, /segmentId:\s*segName\.toLowerCase/);

  await testReleaseDateWaitsForCanonicalPersistence();
  await testSuccessfulCanonicalSave();
  await testGlobalQueuePreventsOutOfOrderWrites();
  await testFailureRollbackRetryAndUnloadGuard();
  await testConflictReloadsAndCancelsStaleQueue();
  await testAtomicScheduleAndImportRoutes();
  await testGuestDataUsesSharedCanonicalStorage();
  await testSongManagementStorageRoutes();
  await testTop3PrivateDataNeverEntersSharedStorage();
  testSongManagementPageContract();
  testSongBankBrowserStartupWithLexicalDependencies();
  testEpisodeSongPreparationContract();
  await testEpisodeOverviewContract();
  testTop3BankPageContract();
  await testInitialTop3AIProposalReconcilesUnrelatedRevisionAndSaves();
  await testTop3AIProposalPreservesRealConflictForDeliberateRetry();
  testTop3BankBrowserStartupWithLexicalDependencies();
  testTop3EpisodePlanningContract();
  await testTop3EpisodeBrowserActionsUseViewerScopedApi();
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
