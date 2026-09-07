/* Page-level dirty-state and reconciliation UI for canonical revision sync. */
(function(root, factory) {
  if (typeof module === 'object' && module.exports) {
    module.exports = factory;
  } else {
    root.SyncView = factory;
  }
})(typeof window !== 'undefined' ? window : globalThis, function createSyncView(options) {
  'use strict';

  options = options || {};
  var document = options.document;
  var sync = options.sync;
  var discard = options.discard || function() {};
  var scopes = new Set();
  var localConflict = false;
  var status = { state: 'disconnected', reason: 'not-started' };
  var notice = document.createElement('section');
  notice.className = 'sync-notice hidden';
  notice.setAttribute('role', 'status');
  notice.setAttribute('aria-live', 'polite');
  notice.innerHTML = '<span class="sync-notice-message"></span><span class="sync-notice-actions"></span>';
  document.body.appendChild(notice);

  function render(message, actions, state) {
    notice.className = 'sync-notice ' + state;
    notice.querySelector('.sync-notice-message').textContent = message;
    var actionsRoot = notice.querySelector('.sync-notice-actions');
    actionsRoot.innerHTML = '';
    (actions || []).forEach(function(action) {
      var button = document.createElement('button');
      button.type = 'button';
      button.textContent = action.label;
      button.addEventListener('click', action.run);
      actionsRoot.appendChild(button);
    });
  }

  function hide() {
    notice.className = 'sync-notice hidden';
  }

  function acceptLatest() {
    discard();
    scopes.clear();
    localConflict = false;
    sync.setViewState('clean');
  }

  function retry() {
    render('Checking for the latest saved data…', [], 'refreshing');
    sync.refreshNow('user-retry').catch(function() {});
  }

  function showConflict(message) {
    localConflict = true;
    adapter.onSyncStatus({
      state: 'conflicted',
      reason: 'save-conflict',
      message: message || null
    });
  }

  var adapter = {
    onSyncStatus: function(next) {
      status = next;
      if (next.state === 'conflicted') {
        render('Newer saved data is available. Your unsaved work has been kept.', [
          { label: 'Continue editing', run: function() {
            render('Unsaved work kept. Finish or cancel it before loading newer data.', [
              { label: 'Discard & load latest', run: acceptLatest }
            ], 'conflicted');
          } },
          { label: 'Discard & load latest', run: acceptLatest }
        ], 'conflicted');
      } else if (next.state === 'refreshing') {
        render('Loading newer saved data…', [], 'refreshing');
      } else if (next.state === 'disconnected' && localConflict) {
        render('Newer saved data is available. Your unsaved work has been kept.', [
          { label: 'Discard & load latest', run: acceptLatest }
        ], 'conflicted');
      } else if (next.state === 'disconnected' && next.canRetry) {
        render('Live updates are disconnected. Your current work is unchanged.', [
          { label: 'Retry now', run: retry }
        ], 'disconnected');
      } else {
        hide();
      }
    }
  };
  sync.registerAdapter(adapter);

  var adapterView = {
    setDirty: function(scope, dirty) {
      if (!scope) throw new TypeError('Dirty scope is required');
      if (dirty) scopes.add(scope);
      else scopes.delete(scope);
      if (scopes.size === 0) localConflict = false;
      sync.setViewState(scopes.size ? 'dirty' : 'clean');
    },
    clear: function() {
      scopes.clear();
      localConflict = false;
      sync.setViewState('clean');
    },
    bindInputs: function(container, scope) {
      function changed() { adapterView.setDirty(scope, true); }
      container.addEventListener('input', changed);
      container.addEventListener('change', changed);
    },
    hasUnsavedWork: function() { return scopes.size > 0; },
    getStatus: function() { return status; },
    acceptLatest: acceptLatest,
    showConflict: showConflict,
    element: notice
  };
  return adapterView;
});
