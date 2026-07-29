"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

function loadStorage(fetchImpl) {
  const errors = [];
  const context = {
    Auth: { getToken: () => "test-token" },
    Toast: { error: (message) => errors.push(message) },
    console: { error: () => {} },
    fetch: fetchImpl,
    Promise,
    JSON,
  };
  vm.createContext(context);
  const source = fs.readFileSync("js/storage.js", "utf8");
  vm.runInContext(source + "\n;globalThis.Storage = Storage;", context);
  return { storage: context.Storage, errors };
}

function response(status, data) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => data,
  };
}

function checkInlineScripts(filename, html) {
  const pattern = /<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/gi;
  for (const match of html.matchAll(pattern)) {
    if (match[1].trim()) new vm.Script(match[1], { filename });
  }
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
  assert.doesNotMatch(showManagement, /freeJokesForIdea/);
  assert.doesNotMatch(showManagement, /lastModified/);
  assert.match(jokesPage, /!config\.claudeApiKeyConfigured/);
  assert.match(jokesPage, /!config\.openaiApiKeyConfigured/);
  assert.match(configPage, /row\.dataset\.segmentId = seg\.id/);
  assert.match(configPage, /const id = row\.dataset\.segmentId/);
  assert.match(configPage, /segment_.*Storage\.generateId\(\)/);
  assert.match(showManagement, /data-segment-id=/);
  assert.match(showManagement, /var segmentId = segEl\.dataset\.segmentId/);
  assert.doesNotMatch(
    showManagement,
    /segmentId:\s*segName\.toLowerCase/,
  );

  const successful = loadStorage(async (_url, options) => {
    const ideas = JSON.parse(options.body);
    return response(200, {
      ok: true,
      data: ideas.map((idea) => ({
        ...idea,
        updatedAt: "2026-07-28T12:00:00+00:00",
      })),
    });
  });

  const defaults = successful.storage.getConfig();
  assert.equal(defaults.claudeApiKeyConfigured, false);
  assert.equal(defaults.openaiApiKeyConfigured, false);
  assert.equal("claudeApiKey" in defaults, false);
  assert.equal("openaiApiKey" in defaults, false);

  const saved = await successful.storage.addIdea({
    id: "idea-1",
    titles: [],
    status: "draft",
  });
  assert.equal(saved, true);
  assert.equal(
    successful.storage.getIdeas()[0].updatedAt,
    "2026-07-28T12:00:00+00:00",
  );
  assert.deepEqual(successful.errors, []);

  const failing = loadStorage(async () =>
    response(503, { detail: "isolated test failure" }),
  );
  failing.storage._cache.ideas = [{ id: "existing", status: "draft" }];
  const failed = await failing.storage.addIdea({
    id: "not-persisted",
    status: "draft",
  });
  assert.equal(failed, false);
  assert.equal(failing.storage.getIdeas().length, 1);
  assert.equal(failing.storage.getIdeas()[0].id, "existing");
  assert.equal(failing.errors.length, 1);
  assert.match(failing.errors[0], /^Failed to save ideas:/);

  const jokeRequests = [];
  const lifecycle = loadStorage(async (url, options) => {
    jokeRequests.push({ url, options });
    return response(200, {
      ok: true,
      data: [{
        id: "joke-1",
        text: "Atomic joke",
        status: "used",
        usedByIdeaId: "idea-1",
      }],
    });
  });
  assert.equal(
    await lifecycle.storage.assignJokeToIdea("joke-1", "idea-1"),
    true,
  );
  assert.equal(jokeRequests.length, 1);
  assert.equal(jokeRequests[0].url, "/api/jokes/joke-1/assignment");
  assert.equal(jokeRequests[0].options.method, "PUT");
  assert.equal(JSON.parse(jokeRequests[0].options.body).ideaId, "idea-1");
  assert.equal(lifecycle.storage.getJokes()[0].usedByIdeaId, "idea-1");
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
