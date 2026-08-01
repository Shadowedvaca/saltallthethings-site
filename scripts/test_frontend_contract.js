"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const SongBankPage = require("../js/songs.js");
const SongPreparation = require("../js/show-song.js");
const EpisodeOverview = require("../js/episode-overview.js");

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

function response(status, data) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => data,
  };
}

function state(revision, overrides = {}) {
  return {
    config: {},
    ideas: [],
    jokes: [],
    songs: [],
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
  assert.equal(await harness.storage.addIdea({ id: "idea-1", status: "draft" }), true);
  assert.equal(harness.storage.getIdeas()[0].updatedAt, "2026-07-29T12:00:00+00:00");
  assert.equal(harness.storage._revision, 1);
  assert.deepEqual(harness.errors, []);
  assert.equal(requests[1].url, "/api/data/ideas");
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
  const stale = harness.storage.addIdea({ id: "stale-one", status: "draft" });
  const queued = harness.storage.addIdea({ id: "stale-two", status: "draft" });
  assert.equal(await stale, false);
  assert.equal(await queued, false);
  assert.equal(mutationCount, 1);
  assert.equal(harness.storage.getIdeas()[0].id, "server-newer");
  assert.equal(harness.storage._revision, 8);
  assert.match(harness.dom.document.getElementById("save-status").className, /conflict/);
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
  assert.equal(await harness.storage.importAll({ ideas: [], songs: [], showSlots: [], assignments: {} }), true);
  assert.equal(mutations[0].url, "/api/schedule/slot-1/assignment");
  assert.equal(mutations[0].options.method, "PUT");
  assert.equal(mutations[1].url, "/api/songs/song-1/assignment");
  assert.equal(mutations[1].options.method, "PUT");
  assert.equal(mutations[2].url, "/api/import");
  assert.equal(mutations[2].options.method, "PUT");
  assert.deepEqual(JSON.parse(mutations[2].options.body), {
    ideas: [], songs: [], showSlots: [], assignments: {},
  });
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
  const expected = summary
    + "\n\nFeatured song: Artist & Friends — Title <Live>"
    + "\nYouTube: https://youtu.be/abc123?si=safe&feature=share";
  const composed = EpisodeOverview.compose(summary, song);
  assert.equal(composed, expected);
  assert.equal(EpisodeOverview.compose(summary, null), summary);
  assert.equal(JSON.stringify(song), before);
  assert.doesNotMatch(composed, /PRIVATE SENTINEL|internal-song-id|internal-idea-id|used/);

  const markup = EpisodeOverview.render(composed);
  assert.match(markup, /Spotify Overview/);
  assert.match(markup, /aria-describedby="spotifyOverviewStatus"/);
  assert.match(markup, /role="status" aria-live="polite"/);
  assert.match(markup, /Title &lt;Live&gt;/);
  assert.match(markup, /si=safe&amp;feature=share/);
  assert.doesNotMatch(markup, /PRIVATE SENTINEL|<Live>/);

  let clipboardPayload = null;
  assert.equal(await EpisodeOverview.copy(composed, {
    clipboard: { writeText: async (text) => { clipboardPayload = text; } },
  }, null), "clipboard");
  assert.equal(clipboardPayload, expected);
  assert.equal(JSON.stringify(song), before);

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

async function main() {
  const showManagement = fs.readFileSync("show_management.html", "utf8");
  const jokesPage = fs.readFileSync("jokes.html", "utf8");
  const songsPage = fs.readFileSync("songs.html", "utf8");
  const configPage = fs.readFileSync("config.html", "utf8");
  checkInlineScripts("show_management.html", showManagement);
  checkInlineScripts("jokes.html", jokesPage);
  checkInlineScripts("songs.html", songsPage);
  checkInlineScripts("config.html", configPage);
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
  assert.match(showManagement, /EpisodeOverview\.compose\(idea\.summary, assignedSong\)/);
  assert.match(showManagement, /await EpisodeOverview\.copy\(currentSpotifyOverview, navigator, document\)/);
  assert.match(showManagement, /Copy failed\. Select the overview text and copy it manually\./);
  assert.match(showManagement, /await Storage\.assignSongToIdea\(songId, ideaId\)/);
  assert.match(showManagement, /await Storage\.freeSong\(songId\)/);
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
  assert.doesNotMatch(configPage, /Promise\.all\(\[\s*Storage\.saveIdeas/);
  assert.match(showManagement, /data-segment-id=/);
  assert.match(showManagement, /var segmentId = segEl\.dataset\.segmentId/);
  assert.doesNotMatch(showManagement, /segmentId:\s*segName\.toLowerCase/);

  await testSuccessfulCanonicalSave();
  await testGlobalQueuePreventsOutOfOrderWrites();
  await testFailureRollbackRetryAndUnloadGuard();
  await testConflictReloadsAndCancelsStaleQueue();
  await testAtomicScheduleAndImportRoutes();
  await testSongManagementStorageRoutes();
  testSongManagementPageContract();
  testEpisodeSongPreparationContract();
  await testEpisodeOverviewContract();
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
