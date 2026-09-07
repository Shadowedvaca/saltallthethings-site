/* Reusable canonical-revision synchronization coordinator. */
var SyncCoordinator = (function(root, factory) {
  if (typeof module === 'object' && module.exports) {
    module.exports = factory;
  } else {
    root.SyncCoordinator = factory;
  }
  return factory;
})(typeof window !== 'undefined' ? window : globalThis, function SyncCoordinator(options) {
  'use strict';

  options = options || {};
  this.resource = options.resource || 'canonical-state';
  this.getToken = options.getToken;
  this.getRevision = options.getRevision;
  this.loadCanonical = options.loadCanonical;
  this.fetch = options.fetch;
  this.AbortController = options.AbortController || AbortController;
  this.clock = options.clock || globalThis;
  this.transport = options.transport || SyncCoordinator.fetchSseTransport;
  this.adapters = [];
  this.running = false;
  this.generation = 0;
  this.retryAttempt = 0;
  this.retryTimer = null;
  this.controller = null;
  this.refreshing = null;
  this.refreshPending = false;
  this.observedRevision = 0;
  this.acknowledgedRevision = 0;
  this.editing = false;
  this.conflicted = false;
  this.status = { state: 'disconnected', reason: 'not-started' };

  if (typeof options.addPageListener === 'function') {
    var coordinator = this;
    options.addPageListener('pagehide', function() { coordinator.stop('navigation'); });
  }
});

SyncCoordinator.fetchSseTransport = async function(options) {
  var response = await options.fetch('/api/sync/revisions?resource=' +
    encodeURIComponent(options.resource) + '&after=' + options.after, {
      headers: { 'Authorization': 'Bearer ' + options.token },
      cache: 'no-store',
      signal: options.signal
    });
  if (!response.ok) {
    var error = new Error('Revision stream failed: ' + response.status);
    error.status = response.status;
    throw error;
  }
  if (!response.body || typeof response.body.getReader !== 'function') {
    throw new Error('Revision stream is unavailable in this browser');
  }

  var reader = response.body.getReader();
  var decoder = new TextDecoder();
  var buffer = '';
  try {
    while (true) {
      var chunk = await reader.read();
      if (chunk.done) break;
      buffer += decoder.decode(chunk.value, { stream: true }).replace(/\r\n/g, '\n');
      var boundary;
      while ((boundary = buffer.indexOf('\n\n')) !== -1) {
        var block = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        var eventName = '';
        var dataLines = [];
        block.split('\n').forEach(function(line) {
          if (line.indexOf('event:') === 0) eventName = line.slice(6).trim();
          if (line.indexOf('data:') === 0) dataLines.push(line.slice(5).trim());
        });
        if (eventName !== 'revision' || dataLines.length === 0) continue;
        try {
          options.onSignal(JSON.parse(dataLines.join('\n')));
        } catch (error) {
          // A malformed hint is ignored; canonical state is never sourced here.
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
};

SyncCoordinator.prototype.registerAdapter = function(adapter) {
  if (!adapter || typeof adapter.onSyncStatus !== 'function') {
    throw new TypeError('Sync adapter must provide onSyncStatus(status)');
  }
  if (this.adapters.indexOf(adapter) === -1) this.adapters.push(adapter);
  adapter.onSyncStatus(this._snapshot());
  var coordinator = this;
  return function() {
    coordinator.adapters = coordinator.adapters.filter(function(candidate) {
      return candidate !== adapter;
    });
  };
};

SyncCoordinator.prototype._snapshot = function(extra) {
  return Object.assign({
    state: this.status.state,
    reason: this.status.reason,
    observedRevision: this.observedRevision,
    acknowledgedRevision: this.acknowledgedRevision
  }, extra || {});
};

SyncCoordinator.prototype._setStatus = function(state, reason, extra) {
  this.status = { state: state, reason: reason };
  var snapshot = this._snapshot(extra);
  this.adapters.slice().forEach(function(adapter) {
    try {
      adapter.onSyncStatus(snapshot);
    } catch (error) {
      console.error('Sync adapter failed:', error);
    }
  });
};

SyncCoordinator.prototype.start = function() {
  this.stop('reinitialized');
  var token = this.getToken && this.getToken();
  if (!token) {
    this._setStatus('disconnected', 'not-authenticated');
    return false;
  }
  var revision = this.getRevision && this.getRevision();
  this.acknowledgedRevision = Number.isInteger(revision) ? revision : 0;
  this.observedRevision = this.acknowledgedRevision;
  this.running = true;
  this.retryAttempt = 0;
  this.editing = false;
  this.conflicted = false;
  this._setStatus('clean', 'started');
  this._connect(this.generation);
  return true;
};

SyncCoordinator.prototype.stop = function(reason) {
  this.running = false;
  this.generation += 1;
  if (this.retryTimer !== null) {
    this.clock.clearTimeout(this.retryTimer);
    this.retryTimer = null;
  }
  if (this.controller) {
    this.controller.abort();
    this.controller = null;
  }
  this.refreshing = null;
  this.refreshPending = false;
  this._setStatus('disconnected', reason || 'stopped');
};

SyncCoordinator.prototype.setViewState = function(state) {
  if (state !== 'clean' && state !== 'dirty') {
    throw new TypeError('View state must be clean or dirty');
  }
  this.editing = state === 'dirty';
  if (this.editing) {
    this._setStatus(this.conflicted ? 'conflicted' : 'dirty', 'view-editing');
    return;
  }
  this.conflicted = false;
  this._setStatus('clean', 'view-clean');
  if (this.observedRevision > this.acknowledgedRevision) {
    this.refreshNow('view-clean-catch-up').catch(function() {});
  }
};

SyncCoordinator.prototype._connect = function(generation) {
  if (!this.running || generation !== this.generation) return;
  var token = this.getToken && this.getToken();
  if (!token) {
    this.stop('authentication-ended');
    return;
  }
  this.controller = new this.AbortController();
  var coordinator = this;
  Promise.resolve(this.transport({
    resource: this.resource,
    after: this.acknowledgedRevision,
    token: token,
    signal: this.controller.signal,
    fetch: this.fetch,
    onSignal: function(signal) { coordinator._onSignal(signal); }
  })).then(function() {
    coordinator._onDisconnect(generation, new Error('Revision stream ended'));
  }).catch(function(error) {
    coordinator._onDisconnect(generation, error);
  });
};

SyncCoordinator.prototype._onSignal = function(signal) {
  if (!this.running || !signal || signal.resource !== this.resource ||
      !Number.isInteger(signal.revision) || signal.revision < 0) return;
  if (signal.revision <= this.observedRevision) return;
  this.observedRevision = signal.revision;

  var localRevision = this.getRevision && this.getRevision();
  if (Number.isInteger(localRevision) && signal.revision <= localRevision) {
    this.acknowledgedRevision = Math.max(this.acknowledgedRevision, localRevision);
    this.retryAttempt = 0;
    this._setStatus(this.editing ? 'dirty' : 'clean', 'self-acknowledged');
    return;
  }
  if (this.editing) {
    this.conflicted = true;
    this._setStatus('conflicted', 'newer-canonical-revision');
    return;
  }
  if (this.refreshing) {
    this.refreshPending = true;
    return;
  }
  this.refreshNow('revision-advanced').catch(function() {});
};

SyncCoordinator.prototype.refreshNow = function(reason) {
  if (this.refreshing) return this.refreshing;
  if (!this.running) return Promise.reject(new Error('Synchronization is stopped'));
  var coordinator = this;
  this._setStatus('refreshing', reason || 'manual-refresh');
  this.refreshing = Promise.resolve(this.loadCanonical(reason || 'remote-sync'))
    .then(function(state) {
      var revision = state && state.revision;
      if (!Number.isInteger(revision)) revision = coordinator.getRevision();
      if (!Number.isInteger(revision)) throw new Error('Canonical revision missing');
      coordinator.acknowledgedRevision = revision;
      coordinator.observedRevision = Math.max(coordinator.observedRevision, revision);
      if (reason !== 'reconnect-catch-up') coordinator.retryAttempt = 0;
      coordinator.conflicted = false;
      coordinator._setStatus(coordinator.editing ? 'dirty' : 'clean', 'canonical-reloaded');
      return state;
    }).catch(function(error) {
      coordinator._setStatus('disconnected', 'refresh-failed', {
        error: error.message,
        canRetry: true
      });
      throw error;
    }).finally(function() {
      coordinator.refreshing = null;
      if (coordinator.refreshPending) {
        coordinator.refreshPending = false;
        if (coordinator.running && !coordinator.editing &&
            coordinator.observedRevision > coordinator.acknowledgedRevision) {
          coordinator.refreshNow('coalesced-catch-up').catch(function() {});
        }
      }
    });
  return this.refreshing;
};

SyncCoordinator.prototype._onDisconnect = function(generation, error) {
  if (!this.running || generation !== this.generation) return;
  this.controller = null;
  if (error && error.status === 401) {
    this.stop('authentication-ended');
    return;
  }
  var delay = Math.min(30000, 1000 * Math.pow(2, this.retryAttempt));
  this.retryAttempt += 1;
  if (this.editing && this.conflicted) {
    this._setStatus('conflicted', 'newer-canonical-revision', {
      transportDisconnected: true,
      retryInMs: delay
    });
  } else {
    this._setStatus('disconnected', 'transport-failed', {
      retryInMs: delay,
      canRetry: true
    });
  }
  var coordinator = this;
  this.retryTimer = this.clock.setTimeout(function() {
    coordinator.retryTimer = null;
    if (!coordinator.running || generation !== coordinator.generation) return;
    var catchUp = coordinator.editing
      ? Promise.resolve()
      : coordinator.refreshNow('reconnect-catch-up');
    catchUp.catch(function() {}).finally(function() {
      coordinator._connect(generation);
    });
  }, delay);
};

if (typeof window !== 'undefined') {
  window.Sync = new SyncCoordinator({
    getToken: function() { return Auth.getToken(); },
    getRevision: function() { return Storage.getRevision(); },
    loadCanonical: function(reason) { return Storage._reloadLatest(reason); },
    transport: SyncCoordinator.fetchSseTransport,
    fetch: window.fetch.bind(window),
    AbortController: window.AbortController,
    clock: window,
    addPageListener: window.addEventListener.bind(window)
  });
}
