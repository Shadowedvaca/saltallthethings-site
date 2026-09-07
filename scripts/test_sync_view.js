"use strict";

const assert = require("node:assert/strict");
const createSyncView = require("../js/sync-view.js");

class Element {
  constructor(tag) {
    this.tagName = tag;
    this.className = "";
    this.textContent = "";
    this.children = [];
    this.listeners = {};
    this.attributes = {};
    this.named = {};
  }
  setAttribute(name, value) { this.attributes[name] = value; }
  addEventListener(name, listener) { (this.listeners[name] ||= []).push(listener); }
  dispatch(name) { (this.listeners[name] || []).forEach((listener) => listener({ target: this })); }
  appendChild(child) { this.children.push(child); }
  querySelector(selector) { return this.named[selector]; }
  set innerHTML(value) {
    this._innerHTML = value;
    this.children = [];
    if (value.includes("sync-notice-message")) {
      this.named[".sync-notice-message"] = new Element("span");
      this.named[".sync-notice-actions"] = new Element("span");
    }
  }
  get innerHTML() { return this._innerHTML || ""; }
}

function harness() {
  const body = new Element("body");
  const document = { body, createElement: (tag) => new Element(tag) };
  const states = [];
  let adapter;
  let retries = 0;
  const sync = {
    registerAdapter(candidate) {
      adapter = candidate;
      candidate.onSyncStatus({ state: "clean", reason: "started" });
    },
    setViewState(state) { states.push(state); },
    refreshNow() { retries += 1; return Promise.resolve({ revision: 9 }); }
  };
  let discarded = 0;
  const view = createSyncView({ document, sync, discard: () => { discarded += 1; } });
  return { adapter, body, states, view, retries: () => retries, discarded: () => discarded };
}

async function main() {
  const test = harness();
  const notice = test.view.element;
  assert.match(notice.className, /hidden/);
  assert.equal(notice.attributes.role, "status");

  const form = new Element("form");
  test.view.bindInputs(form, "draft");
  form.dispatch("input");
  assert.equal(test.view.hasUnsavedWork(), true);
  assert.equal(test.states.at(-1), "dirty");
  test.view.setDirty("editor", true);
  test.view.setDirty("draft", false);
  assert.equal(test.states.at(-1), "dirty", "one remaining scope keeps the page dirty");

  test.view.showConflict();
  test.adapter.onSyncStatus({ state: "disconnected", reason: "transport-failed", canRetry: true });
  assert.match(notice.className, /conflicted/, "transport loss must not hide a save conflict");

  test.adapter.onSyncStatus({ state: "conflicted", reason: "newer-canonical-revision" });
  assert.match(notice.className, /conflicted/);
  assert.match(notice.querySelector(".sync-notice-message").textContent, /unsaved work has been kept/i);
  let actions = notice.querySelector(".sync-notice-actions");
  assert.equal(actions.children.length, 2);
  actions.children[0].dispatch("click");
  assert.equal(test.discarded(), 0, "continue editing does not discard input");
  assert.equal(test.view.hasUnsavedWork(), true);
  actions = notice.querySelector(".sync-notice-actions");
  actions.children[0].dispatch("click");
  assert.equal(test.discarded(), 1);
  assert.equal(test.view.hasUnsavedWork(), false);
  assert.equal(test.states.at(-1), "clean");

  test.adapter.onSyncStatus({ state: "disconnected", reason: "transport-failed", canRetry: true });
  notice.querySelector(".sync-notice-actions").children[0].dispatch("click");
  assert.equal(test.retries(), 1);
  assert.match(notice.className, /refreshing/);

  test.adapter.onSyncStatus({ state: "clean", reason: "canonical-reloaded" });
  assert.match(notice.className, /hidden/);
  console.log("sync view tests passed");
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
