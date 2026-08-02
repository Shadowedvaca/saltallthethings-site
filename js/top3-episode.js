/* Viewer-scoped Top 3 episode assignment and private submission controls. */
(function(root, factory) {
  if (typeof module === 'object' && module.exports) {
    module.exports = factory(root);
  } else {
    root.Top3EpisodePlanning = factory({
      document: root.document,
      confirm: root.confirm.bind(root),
      crypto: root.crypto,
      Auth: Auth,
      Toast: Toast,
      fetch: root.fetch.bind(root)
    });
  }
})(typeof window !== 'undefined' ? window : globalThis, function(root) {
  'use strict';

  var concepts = [];
  var revision = null;
  var episodes = new Map();
  var loading = new Set();
  var errors = new Map();
  var onChange = function() {};
  var bound = false;

  function escapeHtml(value) {
    if (value == null) return '';
    return String(value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  function errorMessage(body, status) {
    var detail = body && (body.error || body.detail);
    if (detail && typeof detail === 'object') detail = detail.message;
    return detail || 'Top 3 request failed (' + status + ').';
  }

  async function apiRequest(path, options) {
    options = options || {};
    var headers = Object.assign({
      'Content-Type': 'application/json',
      'Authorization': 'Bearer ' + root.Auth.getToken()
    }, options.headers || {});
    if (options.mutation) {
      if (!Number.isInteger(revision)) throw new Error('The Top 3 revision is unavailable. Reload and try again.');
      headers['If-Match'] = String(revision);
    }
    var response = await root.fetch('/api' + path, {
      method: options.method || 'GET',
      headers: headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body)
    });
    var body = await response.json().catch(function() { return {}; });
    if (!response.ok) {
      var error = new Error(errorMessage(body, response.status));
      error.status = response.status;
      throw error;
    }
    if (Number.isInteger(body.revision)) revision = body.revision;
    return body;
  }

  async function loadConcepts() {
    var body = await apiRequest('/top3/concepts');
    concepts = Array.isArray(body.concepts) ? body.concepts : [];
    revision = body.revision;
    return concepts;
  }

  async function loadEpisode(ideaId) {
    var body = await apiRequest('/top3/episodes/' + encodeURIComponent(ideaId));
    episodes.set(ideaId, body.assignment || null);
    errors.delete(ideaId);
    return body.assignment || null;
  }

  async function reload(ideaId) {
    loading.add(ideaId);
    onChange(ideaId);
    try {
      await loadConcepts();
      await loadEpisode(ideaId);
    } catch (error) {
      errors.set(ideaId, error.message);
    } finally {
      loading.delete(ideaId);
      onChange(ideaId);
    }
  }

  function ensureEpisode(ideaId) {
    if (episodes.has(ideaId) || loading.has(ideaId)) return;
    reload(ideaId);
  }

  function generateId() {
    if (root.crypto && typeof root.crypto.randomUUID === 'function') {
      return 'top3-submission-' + root.crypto.randomUUID();
    }
    return 'top3-submission-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 10);
  }

  function validatePicks(values) {
    if (!Array.isArray(values) || values.length !== 3) throw new Error('Enter exactly three ranked picks.');
    var picks = values.map(function(value) { return String(value || '').trim(); });
    if (picks.some(function(value) { return !value; })) throw new Error('Enter all three ranked picks.');
    if (picks.some(function(value) { return value.length > 200; })) throw new Error('Each pick must be at most 200 characters.');
    if (new Set(picks.map(function(value) { return value.toLowerCase(); })).size !== 3) throw new Error('Your three ranked picks must be distinct.');
    return picks;
  }

  function conceptOptions(selectedId) {
    var available = concepts.filter(function(concept) {
      return concept.status === 'active' || concept.id === selectedId;
    });
    if (!available.length) return '<option value="">No active concepts available</option>';
    return '<option value="">Choose a banked concept...</option>' + available.map(function(concept) {
      return '<option value="' + escapeHtml(concept.id) + '"' + (concept.id === selectedId ? ' selected' : '') + '>'
        + escapeHtml(concept.name) + (concept.status === 'retired' ? ' (retired)' : '') + '</option>';
    }).join('');
  }

  function contributorsMarkup(contributors) {
    var accounts = (contributors || []).filter(function(item) { return item.contributorType === 'account'; });
    if (!accounts.length) return '<p class="text-sm text-muted">No account contributors are available.</p>';
    return '<ul class="top3-contributors">' + accounts.map(function(item) {
      return '<li><span>' + escapeHtml(item.displayName) + (item.isCurrentUser ? ' (you)' : '') + '</span>'
        + '<span class="badge ' + (item.complete ? 'badge-scheduled' : 'badge-draft') + '">'
        + (item.complete ? 'Ready' : 'Waiting') + '</span></li>';
    }).join('') + '</ul><p class="text-xs text-muted">Status only. Other contributors\' picks and private notes are never loaded into this page.</p>';
  }

  function ownSubmission(contributors) {
    return (contributors || []).find(function(item) { return item.isCurrentUser; }) || null;
  }

  function assignmentMarkup(ideaId, assignment) {
    var concept = assignment.concept;
    var own = ownSubmission(assignment.contributors);
    var picks = own && Array.isArray(own.picks) ? own.picks : ['', '', ''];
    var notes = own && typeof own.privateDiscussionNotes === 'string' ? own.privateDiscussionNotes : '';
    var examples = Array.isArray(concept.aiExample) && concept.aiExample.length === 3
      ? '<div class="top3-shared-example"><strong>Shared fictional example — not a participant submission</strong><ol>'
        + concept.aiExample.map(function(example) { return '<li>' + escapeHtml(example) + '</li>'; }).join('') + '</ol></div>'
      : '<p class="text-xs text-muted">No shared fictional example is saved for this concept.</p>';
    var pickFields = picks.map(function(pick, index) {
      return '<label>Rank ' + (index + 1) + '<input class="edit-field edit-field-sm" data-top3-pick="' + index + '" maxlength="200" value="' + escapeHtml(pick) + '" autocomplete="off" required></label>';
    }).join('');
    return '<div class="top3-concept-summary"><div><strong>' + escapeHtml(concept.name) + '</strong><p>' + escapeHtml(concept.description) + '</p>'
      + (concept.rules ? '<p><span class="text-xs text-muted">RULES</span><br>' + escapeHtml(concept.rules) + '</p>' : '<p class="text-xs text-muted">No additional participation rules.</p>')
      + examples + '</div></div>'
      + '<div class="top3-assignment-controls"><label for="top3-concept-' + escapeHtml(ideaId) + '">Assigned concept</label><div class="top3-control-row">'
      + '<select id="top3-concept-' + escapeHtml(ideaId) + '" class="edit-field edit-field-sm" data-top3-concept>' + conceptOptions(concept.id) + '</select>'
      + '<button type="button" class="btn btn-secondary btn-sm" data-top3-action="assign">Replace</button>'
      + '<button type="button" class="btn btn-ghost btn-sm" data-top3-action="remove-assignment">Remove</button></div>'
      + '<p class="text-xs text-muted">Replacing or removing the concept permanently clears every submission tied to this episode assignment.</p></div>'
      + '<div class="top3-preparation-grid"><div><h5>Contributor readiness</h5>' + contributorsMarkup(assignment.contributors) + '</div>'
      + '<form data-top3-form><h5>Your private ranked picks</h5><div class="top3-picks">' + pickFields + '</div>'
      + '<label>Private discussion notes<textarea class="edit-field" data-top3-notes rows="3" maxlength="8000" placeholder="Optional notes visible only to you before reveal">' + escapeHtml(notes) + '</textarea></label>'
      + '<div class="top3-control-row"><button type="submit" class="btn btn-primary btn-sm">' + (own && own.complete ? 'Save private changes' : 'Save my three picks') + '</button>'
      + (own && own.complete ? '<button type="button" class="btn btn-ghost btn-sm" data-top3-action="delete-submission">Delete my submission</button>' : '')
      + '</div><p class="text-xs text-muted">Your account owns this single submission. Picks and notes are sent only to the viewer-scoped Top 3 API.</p></form></div>';
  }

  function summaryMarkup(ideaId) {
    var assignment = episodes.get(ideaId);
    if (!assignment) return '';
    var concept = assignment.concept;
    var examples = Array.isArray(concept.aiExample) && concept.aiExample.length === 3
      ? '<div class="top3-shared-example"><strong>Shared fictional example — not participant picks</strong><ol>'
        + concept.aiExample.map(function(example) { return '<li>' + escapeHtml(example) + '</li>'; }).join('') + '</ol></div>'
      : '';
    return '<div class="show-display-section"><h2>Top 3 concept</h2><h3>' + escapeHtml(concept.name) + '</h3>'
      + '<p>' + escapeHtml(concept.description) + '</p>'
      + (concept.rules ? '<p><strong>Rules:</strong> ' + escapeHtml(concept.rules) + '</p>' : '')
      + examples + '</div>';
  }

  function render(ideaId) {
    ensureEpisode(ideaId);
    var error = errors.get(ideaId);
    var busy = loading.has(ideaId);
    var assignment = episodes.get(ideaId);
    var body = '';
    if (error) {
      body = '<p class="top3-error" role="alert">' + escapeHtml(error) + '</p><button type="button" class="btn btn-secondary btn-sm" data-top3-action="reload">Reload Top 3 planning</button>';
    } else if (busy || !episodes.has(ideaId)) {
      body = '<p class="text-sm text-muted" role="status" aria-live="polite">Loading private Top 3 planning...</p>';
    } else if (!assignment) {
      body = '<p class="text-sm text-muted">No Top 3 concept is assigned to this episode.</p><div class="top3-control-row">'
        + '<select class="edit-field edit-field-sm" data-top3-concept aria-label="Top 3 concept">' + conceptOptions(null) + '</select>'
        + '<button type="button" class="btn btn-secondary btn-sm" data-top3-action="assign">Assign concept</button></div>'
        + '<p class="text-xs text-muted">Concept definitions are shared. Participant picks remain account-private.</p>';
    } else {
      body = assignmentMarkup(ideaId, assignment);
    }
    return '<section class="top3-episode" data-top3-idea-id="' + escapeHtml(ideaId) + '" onclick="event.stopPropagation()">'
      + '<div class="top3-section-heading"><h4>Top 3 preparation</h4><a href="top3.html">Open Top 3 Bank</a></div>' + body + '</section>';
  }

  async function mutate(ideaId, path, options, successMessage) {
    loading.add(ideaId);
    errors.delete(ideaId);
    onChange(ideaId);
    try {
      await loadEpisode(ideaId);
      var body = await apiRequest(path, Object.assign({}, options, { mutation: true }));
      episodes.set(ideaId, body.assignment || null);
      if (root.Toast && successMessage) root.Toast.success(successMessage);
    } catch (error) {
      if (error.status === 409) {
        await loadConcepts().catch(function() {});
        await loadEpisode(ideaId).catch(function() {});
        errors.set(ideaId, 'Top 3 planning changed on the server. The latest assignment is shown; review it and retry.');
      } else {
        errors.set(ideaId, error.message);
      }
      if (root.Toast) root.Toast.error(errors.get(ideaId));
    } finally {
      loading.delete(ideaId);
      onChange(ideaId);
    }
  }

  function sectionFor(target) {
    return target && target.closest ? target.closest('[data-top3-idea-id]') : null;
  }

  async function handleClick(event) {
    var button = event.target.closest && event.target.closest('[data-top3-action]');
    if (!button) return;
    var section = sectionFor(button);
    if (!section) return;
    event.preventDefault();
    event.stopPropagation();
    var ideaId = section.dataset.top3IdeaId;
    var action = button.dataset.top3Action;
    if (action === 'reload') return reload(ideaId);
    if (action === 'assign') {
      var select = section.querySelector('[data-top3-concept]');
      var conceptId = select && select.value;
      if (!conceptId) {
        errors.set(ideaId, 'Choose an active Top 3 concept first.');
        onChange(ideaId);
        return;
      }
      var current = episodes.get(ideaId);
      if (current && current.concept.id !== conceptId && !root.confirm('Replace this concept? Every existing Top 3 submission for this episode will be permanently deleted.')) return;
      return mutate(ideaId, '/top3/episodes/' + encodeURIComponent(ideaId) + '/assignment', { method: 'PUT', body: { conceptId: conceptId } }, current ? 'Top 3 concept replaced.' : 'Top 3 concept assigned.');
    }
    if (action === 'remove-assignment') {
      if (!root.confirm('Remove this concept? Every existing Top 3 submission for this episode will be permanently deleted.')) return;
      return mutate(ideaId, '/top3/episodes/' + encodeURIComponent(ideaId) + '/assignment', { method: 'DELETE' }, 'Top 3 assignment removed.');
    }
    if (action === 'delete-submission') {
      if (!root.confirm('Delete your private Top 3 submission? This cannot be undone.')) return;
      return mutate(ideaId, '/top3/episodes/' + encodeURIComponent(ideaId) + '/submission', { method: 'DELETE' }, 'Your Top 3 submission was deleted.');
    }
  }

  async function handleSubmit(event) {
    var form = event.target.closest && event.target.closest('[data-top3-form]');
    if (!form) return;
    event.preventDefault();
    event.stopPropagation();
    var section = sectionFor(form);
    var ideaId = section.dataset.top3IdeaId;
    try {
      var pickInputs = Array.from(form.querySelectorAll('[data-top3-pick]'));
      pickInputs.sort(function(a, b) { return Number(a.dataset.top3Pick) - Number(b.dataset.top3Pick); });
      var picks = validatePicks(pickInputs.map(function(input) { return input.value; }));
      var notes = String(form.querySelector('[data-top3-notes]').value || '').trim();
      if (notes.length > 8000) throw new Error('Private discussion notes must be at most 8000 characters.');
      var assignment = episodes.get(ideaId);
      var own = assignment && ownSubmission(assignment.contributors);
      await mutate(ideaId, '/top3/episodes/' + encodeURIComponent(ideaId) + '/submission', {
        method: 'PUT',
        body: { id: own && own.submissionId ? own.submissionId : generateId(), picks: picks, privateDiscussionNotes: notes }
      }, 'Your private Top 3 picks were saved.');
    } catch (error) {
      errors.set(ideaId, error.message);
      if (root.Toast) root.Toast.error(error.message);
      onChange(ideaId);
    }
  }

  function bind() {
    if (bound || !root.document) return;
    // Capture before the episode card's propagation guard so Top 3 controls
    // remain interactive without toggling the surrounding expandable card.
    root.document.addEventListener('click', handleClick, true);
    root.document.addEventListener('submit', handleSubmit);
    bound = true;
  }

  async function start(changeCallback) {
    onChange = typeof changeCallback === 'function' ? changeCallback : function() {};
    bind();
    try {
      await loadConcepts();
    } catch (error) {
      if (root.Toast) root.Toast.error('Top 3 planning is unavailable: ' + error.message);
    }
    onChange(null);
  }

  return {
    escapeHtml: escapeHtml,
    validatePicks: validatePicks,
    contributorsMarkup: contributorsMarkup,
    assignmentMarkup: assignmentMarkup,
    summaryMarkup: summaryMarkup,
    render: render,
    loadConcepts: loadConcepts,
    loadEpisode: loadEpisode,
    reload: reload,
    start: start,
    _state: { concepts: function() { return concepts; }, episodes: episodes, errors: errors }
  };
});
