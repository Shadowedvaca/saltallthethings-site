"use strict";

const assert = require("node:assert/strict");
const SyncCoordinator = require("../js/sync.js");

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((ok, fail) => { resolve = ok; reject = fail; });
  return { promise, resolve, reject };
}

async function settle() {
  await new Promise((resolve) => setImmediate(resolve));
}

class FakeAbortController {
  constructor() {
    this.signal = { aborted: false };
  }
  abort() {
    this.signal.aborted = true;
  }
}

class FakeClock {
  constructor() {
    this.timers = [];
  }
  setTimeout(callback, delay) {
    const timer = { callback, delay, cancelled: false };
    this.timers.push(timer);
    return timer;
  }
  clearTimeout(timer) {
    timer.cancelled = true;
  }
  runNext() {
    const timer = this.timers.find((candidate) => !candidate.cancelled);
    assert.ok(timer, "expected a pending timer");
    timer.cancelled = true;
    timer.callback();
    return timer.delay;
  }
  activeCount() {
    return this.timers.filter((timer) => !timer.cancelled).length;
  }
}

function harness(overrides) {
  let revision = 5;
  let canonicalRevision = 5;
  const clock = new FakeClock();
  const connections = [];
  const loads = [];
  const statuses = [];
  const transport = (options) => {
    const pending = deferred();
    connections.push({ options, pending });
    return pending.promise;
  };
  const coordinator = new SyncCoordinator(Object.assign({
    getToken: () => "signed-token",
    getRevision: () => revision,
    loadCanonical: async (reason) => {
      loads.push(reason);
      revision = canonicalRevision;
      return { revision };
    },
    transport,
    AbortController: FakeAbortController,
    clock
  }, overrides || {}));
  coordinator.registerAdapter({ onSyncStatus: (status) => statuses.push(status) });
  return {
    coordinator,
    clock,
    connections,
    loads,
    statuses,
    setRevision(value) { revision = value; },
    setCanonicalRevision(value) { canonicalRevision = value; }
  };
}

async function testCleanRefreshAndOrdering() {
  const test = harness();
  assert.equal(test.coordinator.start(), true);
  assert.equal(test.connections.length, 1);
  assert.equal(test.connections[0].options.after, 5);

  test.setCanonicalRevision(6);
  test.connections[0].options.onSignal({ resource: "canonical-state", revision: 6 });
  await settle();
  assert.deepEqual(test.loads, ["revision-advanced"]);
  assert.equal(test.coordinator.acknowledgedRevision, 6);
  assert.equal(test.statuses.at(-1).state, "clean");

  test.connections[0].options.onSignal({ resource: "canonical-state", revision: 6 });
  test.connections[0].options.onSignal({ resource: "canonical-state", revision: 4 });
  test.connections[0].options.onSignal({ resource: "other", revision: 9 });
  assert.equal(test.loads.length, 1);

  test.setRevision(7);
  test.connections[0].options.onSignal({ resource: "canonical-state", revision: 7 });
  await settle();
  assert.equal(test.loads.length, 1, "self-originated revision must not reload");
  assert.equal(test.coordinator.acknowledgedRevision, 7);
  test.coordinator.stop("test-complete");
}

async function testCoalescesSignals() {
  const pendingLoad = deferred();
  let loadCount = 0;
  const test = harness({
    loadCanonical: () => {
      loadCount += 1;
      return pendingLoad.promise;
    }
  });
  test.coordinator.start();
  test.connections[0].options.onSignal({ resource: "canonical-state", revision: 6 });
  test.connections[0].options.onSignal({ resource: "canonical-state", revision: 7 });
  assert.equal(loadCount, 1);
  pendingLoad.resolve({ revision: 7 });
  await settle();
  assert.equal(test.coordinator.acknowledgedRevision, 7);
  test.coordinator.stop("test-complete");
}

async function testSignalDuringReloadGetsOneFollowUpCatchUp() {
  const first = deferred();
  const loadReasons = [];
  let calls = 0;
  const test = harness({
    loadCanonical: (reason) => {
      loadReasons.push(reason);
      calls += 1;
      return calls === 1 ? first.promise : Promise.resolve({ revision: 7 });
    }
  });
  test.coordinator.start();
  test.connections[0].options.onSignal({ resource: "canonical-state", revision: 6 });
  test.connections[0].options.onSignal({ resource: "canonical-state", revision: 7 });
  first.resolve({ revision: 6 });
  await settle();
  await settle();
  assert.deepEqual(loadReasons, ["revision-advanced", "coalesced-catch-up"]);
  assert.equal(test.coordinator.acknowledgedRevision, 7);
  test.coordinator.stop("test-complete");
}

async function testReconnectCatchUpAndBackoff() {
  const test = harness();
  test.coordinator.start();
  test.connections[0].pending.reject(new Error("offline"));
  await settle();
  assert.equal(test.statuses.at(-1).state, "disconnected");
  assert.equal(test.statuses.at(-1).retryInMs, 1000);
  test.setCanonicalRevision(9);
  assert.equal(test.clock.runNext(), 1000);
  await settle();
  assert.equal(test.loads.at(-1), "reconnect-catch-up");
  assert.equal(test.connections.length, 2);
  assert.equal(test.connections[1].options.after, 9);

  test.connections[1].pending.reject(new Error("still offline"));
  await settle();
  assert.equal(test.statuses.at(-1).retryInMs, 2000);
  assert.equal(test.clock.runNext(), 2000);
  await settle();
  assert.equal(test.connections.length, 3);
  test.coordinator.stop("test-complete");
}

async function testDirtyConflictAndExplicitCatchUp() {
  const test = harness();
  test.coordinator.start();
  test.coordinator.setViewState("dirty");
  test.connections[0].options.onSignal({ resource: "canonical-state", revision: 6 });
  assert.equal(test.statuses.at(-1).state, "conflicted");
  assert.equal(test.loads.length, 0);
  test.connections[0].pending.resolve();
  await settle();
  assert.equal(test.statuses.at(-1).state, "conflicted", "disconnect must not hide a pending edit conflict");
  test.setCanonicalRevision(6);
  test.coordinator.setViewState("clean");
  await settle();
  assert.deepEqual(test.loads, ["view-clean-catch-up"]);
  assert.equal(test.coordinator.acknowledgedRevision, 6);
  assert.throws(() => test.coordinator.setViewState("unknown"), /clean or dirty/);
  test.coordinator.stop("test-complete");
}

async function testFailureAndTeardown() {
  const test = harness({ loadCanonical: async () => { throw new Error("reload failed"); } });
  test.coordinator.start();
  test.connections[0].options.onSignal({ resource: "canonical-state", revision: 6 });
  await settle();
  assert.equal(test.coordinator.acknowledgedRevision, 5);
  assert.equal(test.statuses.at(-1).state, "disconnected");
  assert.equal(test.statuses.at(-1).canRetry, true);

  test.connections[0].pending.reject(new Error("offline"));
  await settle();
  assert.equal(test.clock.activeCount(), 1);
  test.coordinator.start();
  assert.equal(test.clock.activeCount(), 0);
  const activeSignal = test.connections.at(-1).options.signal;
  test.coordinator.start();
  assert.equal(activeSignal.aborted, true);
  const replacementSignal = test.connections.at(-1).options.signal;
  test.coordinator.stop("logout");
  assert.equal(replacementSignal.aborted, true);
  assert.equal(test.clock.activeCount(), 0);
}

async function testAuthLifecycle() {
  const test = harness({ getToken: () => null });
  assert.equal(test.coordinator.start(), false);
  assert.equal(test.connections.length, 0);
  assert.equal(test.statuses.at(-1).reason, "not-authenticated");

  const authorized = harness();
  authorized.coordinator.start();
  const error = new Error("expired");
  error.status = 401;
  authorized.connections[0].pending.reject(error);
  await settle();
  assert.equal(authorized.coordinator.running, false);
  assert.equal(authorized.statuses.at(-1).reason, "authentication-ended");
}

async function testSseParser() {
  const encoded = new TextEncoder();
  const chunks = [
    encoded.encode(": keep-alive\r\n\r\nevent: revision\r\ndata: {\"resource\":\"canonical-state\","),
    encoded.encode("\"revision\":12}\r\n\r\nevent: revision\r\ndata: invalid\r\n\r\n")
  ];
  let released = false;
  const signals = [];
  await SyncCoordinator.fetchSseTransport({
    resource: "canonical-state",
    after: 11,
    token: "signed-token",
    signal: {},
    onSignal: (signal) => signals.push(signal),
    fetch: async () => ({
      ok: true,
      body: {
        getReader: () => ({
          read: async () => chunks.length ? { value: chunks.shift(), done: false } : { done: true },
          releaseLock: () => { released = true; }
        })
      }
    })
  });
  assert.deepEqual(signals, [{ resource: "canonical-state", revision: 12 }]);
  assert.equal(released, true);

  await assert.rejects(
    SyncCoordinator.fetchSseTransport({
      resource: "canonical-state", after: 0, token: "token", signal: {},
      onSignal: () => {}, fetch: async () => ({ ok: false, status: 401 })
    }),
    (error) => error.status === 401
  );
}

async function main() {
  await testCleanRefreshAndOrdering();
  await testCoalescesSignals();
  await testSignalDuringReloadGetsOneFollowUpCatchUp();
  await testReconnectCatchUpAndBackoff();
  await testDirtyConflictAndExplicitCatchUp();
  await testFailureAndTeardown();
  await testAuthLifecycle();
  await testSseParser();
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
