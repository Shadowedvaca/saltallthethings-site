"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

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
  assert.equal(await harness.storage.importAll({ ideas: [], showSlots: [], assignments: {} }), true);
  assert.equal(mutations[0].url, "/api/schedule/slot-1/assignment");
  assert.equal(mutations[0].options.method, "PUT");
  assert.equal(mutations[1].url, "/api/import");
  assert.equal(mutations[1].options.method, "PUT");
  assert.deepEqual(JSON.parse(mutations[1].options.body), {
    ideas: [], showSlots: [], assignments: {},
  });
}

async function main() {
  const showManagement = fs.readFileSync("show_management.html", "utf8");
  const jokesPage = fs.readFileSync("jokes.html", "utf8");
  const configPage = fs.readFileSync("config.html", "utf8");
  checkInlineScripts("show_management.html", showManagement);
  checkInlineScripts("jokes.html", jokesPage);
  checkInlineScripts("config.html", configPage);
  assert.match(showManagement, /!config\.claudeApiKeyConfigured/);
  assert.match(showManagement, /!config\.openaiApiKeyConfigured/);
  assert.match(showManagement, /await Storage\.addIdea\(idea\)/);
  assert.match(showManagement, /await Storage\.updateIdea\(ideaId/);
  assert.match(showManagement, /await Storage\.assignJokeToIdea\(jokeId, ideaId\)/);
  assert.match(showManagement, /await Storage\.freeJoke\(jokeId\)/);
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
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
