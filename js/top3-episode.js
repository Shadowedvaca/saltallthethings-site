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
  var editingExternal = new Map();
  var onChange = function() {};
  var onDetailChange = function() {};
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

  async function loadSpotifyResults(ideaId) {
    var body = await apiRequest('/top3/episodes/' + encodeURIComponent(ideaId) + '/spotify-results', {
      method: 'POST',
      body: { purpose: 'spotify-overview' }
    });
    return body.top3 || null;
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
      var status = '<span class="badge ' + (item.complete ? 'badge-scheduled' : 'badge-draft') + '">'
        + (item.complete ? (item.isCurrentUser || item.revealed ? 'Ready' : 'Ready — hidden') : 'Waiting') + '</span>';
      var action = item.complete && !item.isCurrentUser && !item.revealed
        ? '<button type="button" class="btn btn-ghost btn-sm" data-top3-action="reveal" data-submission-id="' + escapeHtml(item.submissionId) + '" data-display-name="' + escapeHtml(item.displayName) + '">Reveal picks</button>'
        : '';
      var revealed = item.revealed && Array.isArray(item.picks)
        ? '<div class="top3-revealed" data-revealed-submission="' + escapeHtml(item.submissionId) + '"><strong>Revealed only to you</strong><ol>'
          + item.picks.map(function(pick) { return '<li>' + escapeHtml(pick) + '</li>'; }).join('') + '</ol>'
          + (item.privateDiscussionNotes ? '<p>' + escapeHtml(item.privateDiscussionNotes) + '</p>' : '')
          + '<span class="text-xs text-muted">Revealed ' + escapeHtml(item.revealedAt || '') + '</span></div>'
        : '';
      return '<li><div class="top3-contributor-heading"><span>' + escapeHtml(item.displayName) + (item.isCurrentUser ? ' (you)' : '') + '</span>'
        + '<span class="top3-contributor-actions">' + status + action + '</span></div>' + revealed + '</li>';
    }).join('') + '</ul><p class="text-xs text-muted">Hidden submissions expose status only. Reveal is irreversible for your account and never reveals your picks to anyone else.</p>';
  }

  function externalResultsMarkup(ideaId, contributors) {
    var external = (contributors || []).filter(function(item) { return item.contributorType === 'external'; });
    var editingId = editingExternal.get(ideaId) || null;
    var editing = external.find(function(item) { return item.submissionId === editingId; }) || null;
    var picks = editing && Array.isArray(editing.picks) ? editing.picks : ['', '', ''];
    var cards = external.length ? '<div class="top3-external-list">' + external.map(function(item) {
      return '<article class="top3-external-result"><div class="top3-contributor-heading"><strong>' + escapeHtml(item.displayName) + '</strong>'
        + '<span class="badge badge-scheduled">' + escapeHtml(item.externalType) + ' — shared</span></div><ol>'
        + (item.picks || []).map(function(pick) { return '<li>' + escapeHtml(pick) + '</li>'; }).join('') + '</ol>'
        + (item.privateDiscussionNotes ? '<p>' + escapeHtml(item.privateDiscussionNotes) + '</p>' : '')
        + '<div class="top3-control-row"><button type="button" class="btn btn-ghost btn-sm" data-top3-action="edit-external" data-submission-id="' + escapeHtml(item.submissionId) + '">Edit</button>'
        + '<button type="button" class="btn btn-ghost btn-sm" data-top3-action="delete-external" data-submission-id="' + escapeHtml(item.submissionId) + '" data-display-name="' + escapeHtml(item.displayName) + '">Remove</button></div></article>';
    }).join('') + '</div>' : '<p class="text-sm text-muted">No guest or listener results captured.</p>';
    var pickFields = picks.map(function(pick, index) {
      return '<label>Rank ' + (index + 1) + '<input class="edit-field edit-field-sm" data-top3-external-pick="' + index + '" maxlength="200" value="' + escapeHtml(pick) + '" required></label>';
    }).join('');
    return '<section class="top3-external"><h5>Guest and listener results</h5>' + cards
      + '<form data-top3-external-form><h6>' + (editing ? 'Edit shared result' : 'Capture shared result') + '</h6>'
      + '<div class="top3-external-identity"><label>Contributor name<input class="edit-field edit-field-sm" data-top3-external-name maxlength="200" value="' + escapeHtml(editing ? editing.displayName : '') + '" required></label>'
      + '<label>Contributor type<select class="edit-field edit-field-sm" data-top3-external-type><option value="guest"' + (editing && editing.externalType === 'guest' ? ' selected' : '') + '>Guest</option><option value="listener"' + (editing && editing.externalType === 'listener' ? ' selected' : '') + '>Listener</option></select></label></div>'
      + '<div class="top3-picks">' + pickFields + '</div><label>Shared discussion notes<textarea class="edit-field" data-top3-external-notes rows="2" maxlength="8000">' + escapeHtml(editing ? editing.privateDiscussionNotes : '') + '</textarea></label>'
      + '<div class="top3-control-row"><button type="submit" class="btn btn-secondary btn-sm">' + (editing ? 'Save shared changes' : 'Add shared result') + '</button>'
      + (editing ? '<button type="button" class="btn btn-ghost btn-sm" data-top3-action="cancel-external">Cancel edit</button>' : '') + '</div>'
      + '<p class="text-xs text-muted">External results have no account owner. Any authenticated host may edit or remove these shared recording results.</p></form></section>';
  }

  function ownSubmission(contributors) {
    return (contributors || []).find(function(item) { return item.isCurrentUser; }) || null;
  }

  function revealButtonMarkup(item) {
    if (!item || !item.complete || item.contributorType !== 'account' || item.isCurrentUser || item.revealed) return '';
    return '<button type="button" class="btn btn-ghost btn-sm" data-top3-action="reveal" data-submission-id="' + escapeHtml(item.submissionId) + '" data-display-name="' + escapeHtml(item.displayName) + '">Reveal picks</button>';
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
      + '</div><p class="text-xs text-muted">Your account owns this single submission. Picks and notes are sent only to the viewer-scoped Top 3 API.</p></form></div>'
      + externalResultsMarkup(ideaId, assignment.contributors);
  }

  function summaryMarkup(ideaId) {
    var assignment = episodes.get(ideaId);
    if (!assignment) return '';
    var concept = assignment.concept;
    var examples = Array.isArray(concept.aiExample) && concept.aiExample.length === 3
      ? '<div class="top3-shared-example"><strong>Shared fictional example — not participant picks</strong><ol>'
        + concept.aiExample.map(function(example) { return '<li>' + escapeHtml(example) + '</li>'; }).join('') + '</ol></div>'
      : '';
    var participantRows = (assignment.contributors || []).map(function(item) {
      var visible = item.contributorType === 'external' || item.isCurrentUser || item.revealed;
      var state = item.complete ? (visible ? 'Submitted' : 'Ready — hidden') : 'Waiting';
      var result = visible && Array.isArray(item.picks)
        ? '<ol>' + item.picks.map(function(pick) { return '<li>' + escapeHtml(pick) + '</li>'; }).join('') + '</ol>'
          + (item.privateDiscussionNotes ? '<p>' + escapeHtml(item.privateDiscussionNotes) + '</p>' : '')
        : '';
      return '<li><div class="top3-contributor-heading"><strong>' + escapeHtml(item.displayName)
        + (item.isCurrentUser ? ' (you)' : '') + '</strong><span class="top3-contributor-actions"><span class="badge ' + (item.complete ? 'badge-scheduled' : 'badge-draft') + '">'
        + state + '</span>' + revealButtonMarkup(item) + '</span></div>' + result + '</li>';
    }).join('');
    return '<div class="show-display-section" data-top3-idea-id="' + escapeHtml(ideaId) + '"><h2>Top 3 concept</h2><h3>' + escapeHtml(concept.name) + '</h3>'
      + '<p>' + escapeHtml(concept.description) + '</p>'
      + (concept.rules ? '<p><strong>Rules:</strong> ' + escapeHtml(concept.rules) + '</p>' : '')
      + examples + '<h3>Participant results</h3><ul class="top3-contributors">' + participantRows + '</ul></div>';
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
      return true;
    } catch (error) {
      if (error.status === 409) {
        await loadConcepts().catch(function() {});
        await loadEpisode(ideaId).catch(function() {});
        errors.set(ideaId, 'Top 3 planning changed on the server. The latest assignment is shown; review it and retry.');
      } else {
        errors.set(ideaId, error.message);
      }
      if (root.Toast) root.Toast.error(errors.get(ideaId));
      return false;
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
    if (action === 'reveal') {
      var revealId = button.dataset.submissionId;
      var revealName = button.dataset.displayName || 'this contributor';
      if (!root.confirm('Reveal ' + revealName + '\'s private Top 3 picks and notes to your account? This cannot be undone.')) return;
      var revealed = await mutate(ideaId, '/top3/episodes/' + encodeURIComponent(ideaId) + '/reveals/' + encodeURIComponent(revealId), { method: 'POST' }, revealName + '\'s picks were revealed only to you.');
      if (revealed) await onDetailChange(ideaId);
      return revealed;
    }
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
    if (action === 'edit-external') {
      editingExternal.set(ideaId, button.dataset.submissionId);
      errors.delete(ideaId);
      onChange(ideaId);
      return;
    }
    if (action === 'cancel-external') {
      editingExternal.delete(ideaId);
      errors.delete(ideaId);
      onChange(ideaId);
      return;
    }
    if (action === 'delete-external') {
      var externalId = button.dataset.submissionId;
      var externalName = button.dataset.displayName || 'this external result';
      if (!root.confirm('Remove the shared Top 3 result for ' + externalName + '? This cannot be undone.')) return;
      var removed = await mutate(ideaId, '/top3/episodes/' + encodeURIComponent(ideaId) + '/external-submissions/' + encodeURIComponent(externalId), { method: 'DELETE' }, 'Shared external result removed.');
      if (removed && editingExternal.get(ideaId) === externalId) editingExternal.delete(ideaId);
      return;
    }
  }

  async function handleSubmit(event) {
    var externalForm = event.target.closest && event.target.closest('[data-top3-external-form]');
    if (externalForm) {
      event.preventDefault();
      event.stopPropagation();
      var externalSection = sectionFor(externalForm);
      var externalIdeaId = externalSection.dataset.top3IdeaId;
      try {
        var externalName = String(externalForm.querySelector('[data-top3-external-name]').value || '').trim();
        if (!externalName) throw new Error('External contributor name is required.');
        if (externalName.length > 200) throw new Error('External contributor name must be at most 200 characters.');
        var externalType = externalForm.querySelector('[data-top3-external-type]').value;
        if (externalType !== 'guest' && externalType !== 'listener') throw new Error('External contributor type must be guest or listener.');
        var externalPickInputs = Array.from(externalForm.querySelectorAll('[data-top3-external-pick]'));
        externalPickInputs.sort(function(a, b) { return Number(a.dataset.top3ExternalPick) - Number(b.dataset.top3ExternalPick); });
        var externalPicks = validatePicks(externalPickInputs.map(function(input) { return input.value; }));
        var externalNotes = String(externalForm.querySelector('[data-top3-external-notes]').value || '').trim();
        if (externalNotes.length > 8000) throw new Error('Shared discussion notes must be at most 8000 characters.');
        var editingId = editingExternal.get(externalIdeaId) || null;
        var externalPath = '/top3/episodes/' + encodeURIComponent(externalIdeaId) + '/external-submissions' + (editingId ? '/' + encodeURIComponent(editingId) : '');
        var externalSaved = await mutate(externalIdeaId, externalPath, {
          method: editingId ? 'PUT' : 'POST',
          body: {
            id: editingId || generateId(),
            displayName: externalName,
            externalType: externalType,
            picks: externalPicks,
            privateDiscussionNotes: externalNotes
          }
        }, editingId ? 'Shared external result updated.' : 'Shared external result added.');
        if (externalSaved) editingExternal.delete(externalIdeaId);
      } catch (error) {
        errors.set(externalIdeaId, error.message);
        if (root.Toast) root.Toast.error(error.message);
        onChange(externalIdeaId);
      }
      return;
    }
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

  async function start(changeCallback, detailChangeCallback) {
    onChange = typeof changeCallback === 'function' ? changeCallback : function() {};
    onDetailChange = typeof detailChangeCallback === 'function' ? detailChangeCallback : function() {};
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
    externalResultsMarkup: externalResultsMarkup,
    assignmentMarkup: assignmentMarkup,
    revealButtonMarkup: revealButtonMarkup,
    summaryMarkup: summaryMarkup,
    render: render,
    loadConcepts: loadConcepts,
    loadEpisode: loadEpisode,
    loadSpotifyResults: loadSpotifyResults,
    reload: reload,
    start: start,
    _state: { concepts: function() { return concepts; }, episodes: episodes, errors: errors }
  };
});
