/* Authenticated Top 3 concept workshop and bank page. */
(function(root, factory) {
  if (typeof module === 'object' && module.exports) {
    var exported = factory(root);
    exported.createForTesting = factory;
    module.exports = exported;
  } else {
    var api = factory({
      document: root.document,
      confirm: root.confirm.bind(root),
      crypto: root.crypto,
      Auth: Auth,
      Toast: Toast,
      fetch: root.fetch.bind(root)
    });
    root.Top3BankPage = api;
    root.onStorageReady = api.onStorageReady;
    api.start();
  }
})(typeof window !== 'undefined' ? window : globalThis, function(root) {
  'use strict';

  var concepts = [];
  var revision = null;
  var currentFilter = 'all';
  var currentQuery = '';
  var editingConceptId = null;
  var acceptedProvenance = null;
  var draftConceptId = null;

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

  function bankFingerprint(items) {
    return JSON.stringify((items || []).map(function(concept) {
      return {
        concept: conceptPayload(concept),
        assignedEpisodes: (concept.assignedEpisodes || []).map(function(assignment) {
          return {
            ideaId: assignment.ideaId,
            title: assignment.title,
            episodeNumber: assignment.episodeNumber
          };
        }).sort(function(left, right) { return left.ideaId.localeCompare(right.ideaId); })
      };
    }).sort(function(left, right) { return left.concept.id.localeCompare(right.concept.id); }));
  }

  async function apiRequest(path, options) {
    options = options || {};
    var headers = Object.assign({
      'Content-Type': 'application/json',
      'Authorization': 'Bearer ' + root.Auth.getToken()
    }, options.headers || {});
    if (options.mutation) {
      if (!Number.isInteger(revision)) throw new Error('The Top 3 revision is unavailable. Reload the bank and try again.');
      headers['If-Match'] = String(revision);
    }
    var response = await root.fetch('/api' + path, {
      method: options.method || 'GET',
      headers: headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body)
    });
    var body = await response.json().catch(function() { return {}; });
    if (!response.ok) {
      var conflict = response.status === 409;
      var bankChanged = false;
      if (conflict) {
        var beforeConflict = bankFingerprint(concepts);
        await loadConcepts();
        bankChanged = beforeConflict !== bankFingerprint(concepts);
        // A shared revision can advance for unrelated application data. Retry
        // once only when the canonical bank projection proves this mutation
        // cannot overwrite a concurrent Top 3 concept or assignment change.
        if (options.mutation && !options.conflictRetry && !bankChanged) {
          return apiRequest(path, Object.assign({}, options, { conflictRetry: true }));
        }
      }
      var error = new Error(conflict
        ? bankChanged
          ? 'The Top 3 Bank changed on the server. The latest concepts are shown; your proposal is preserved for review and retry.'
          : 'The server revision changed again while saving. The latest Top 3 Bank is shown; your proposal is preserved for retry.'
        : errorMessage(body, response.status));
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

  function generateId() {
    if (root.crypto && typeof root.crypto.randomUUID === 'function') {
      return 'top3-' + root.crypto.randomUUID();
    }
    return 'top3-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 10);
  }

  function normalizeExamples(values, required) {
    var examples = values.map(function(value) { return String(value || '').trim(); });
    var completed = examples.filter(Boolean);
    if (!completed.length && !required) return [];
    if (completed.length !== 3) throw new Error('Provide all three fictional examples or leave all three blank.');
    if (examples.some(function(value) { return value.length > 200; })) throw new Error('Each fictional example must be at most 200 characters.');
    var distinct = new Set(examples.map(function(value) { return value.toLowerCase(); }));
    if (distinct.size !== 3) throw new Error('The three fictional examples must be distinct.');
    return examples;
  }

  function validateConceptInput(values, requireExamples) {
    var name = String(values.name || '').trim();
    var description = String(values.description || '').trim();
    var rules = String(values.rules || '').trim();
    var hostNotes = String(values.hostNotes || '').trim();
    if (!description) throw new Error('Concept description is required.');
    if (!name) throw new Error('Shared name is required before saving. Generate a proposal or enter a name.');
    if (name.length > 200) throw new Error('Shared name must be at most 200 characters.');
    if (description.length > 4000) throw new Error('Description must be at most 4000 characters.');
    if (rules.length > 4000) throw new Error('Rules must be at most 4000 characters.');
    if (hostNotes.length > 8000) throw new Error('Host notes must be at most 8000 characters.');
    return {
      name: name,
      description: description,
      rules: rules,
      hostNotes: hostNotes,
      aiExample: normalizeExamples(values.aiExample || [], requireExamples)
    };
  }

  function conceptPayload(concept) {
    return {
      id: concept.id,
      name: concept.name,
      description: concept.description,
      rules: concept.rules || '',
      hostNotes: concept.hostNotes || '',
      aiExample: Array.isArray(concept.aiExample) ? concept.aiExample : [],
      status: concept.status || 'active',
      source: concept.source || 'manual',
      aiProvider: concept.aiProvider || null,
      aiModelId: concept.aiModelId || null,
      aiGeneratedAt: concept.aiGeneratedAt || null
    };
  }

  function conceptMatches(concept, filter, query) {
    if (filter !== 'all' && concept.status !== filter) return false;
    var needle = String(query || '').trim().toLowerCase();
    if (!needle) return true;
    var assignmentText = (concept.assignedEpisodes || []).map(function(assignment) {
      var episode = assignment.episodeNumber ? 'Episode ' + assignment.episodeNumber : '';
      return [episode, assignment.title, assignment.ideaId].join(' ');
    }).join(' ');
    return [concept.name, concept.description, concept.rules, concept.hostNotes, assignmentText]
      .concat(concept.aiExample || [])
      .some(function(value) { return String(value || '').toLowerCase().includes(needle); });
  }

  function formatDate(value) {
    if (!value) return '';
    var date = new Date(value);
    if (Number.isNaN(date.getTime())) return '';
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
  }

  function conceptCardMarkup(concept) {
    var id = escapeHtml(concept.id);
    var source = concept.source === 'ai' ? 'AI-assisted' : 'Manual';
    var examples = concept.aiExample && concept.aiExample.length === 3
      ? '<div class="top3-example-box"><strong>Fictional examples — not participant picks</strong><ol>'
        + concept.aiExample.map(function(example) { return '<li>' + escapeHtml(example) + '</li>'; }).join('')
        + '</ol></div>'
      : '<div class="top3-example-box text-muted text-sm"><strong>Fictional examples</strong><br>No examples saved. This does not represent an incomplete participant submission.</div>';
    var assignments = concept.assignedEpisodes || [];
    var assignmentMarkup = assignments.length
      ? '<div class="top3-assignment"><strong>Assigned to ' + assignments.length + ' episode' + (assignments.length === 1 ? '' : 's') + ':</strong><ul>'
        + assignments.map(function(assignment) {
          var episode = assignment.episodeNumber ? 'Episode ' + escapeHtml(assignment.episodeNumber) + ': ' : '';
          return '<li>' + episode + escapeHtml(assignment.title) + '</li>';
        }).join('') + '</ul><span class="text-xs text-muted">Assignment metadata only; participant picks are never shown here.</span></div>'
      : '<div class="top3-assignment">Not assigned to an episode.</div>';
    var rules = concept.rules
      ? '<div class="top3-copy"><strong class="text-xs text-muted">RULES</strong><br>' + escapeHtml(concept.rules) + '</div>'
      : '<div class="top3-copy text-muted text-sm">No participation rules.</div>';
    var notes = concept.hostNotes
      ? '<div class="top3-copy"><strong class="text-xs text-muted">HOST PLANNING NOTES</strong><br>' + escapeHtml(concept.hostNotes) + '</div>'
      : '';
    var actions = '<button type="button" class="btn btn-ghost btn-sm" data-action="edit" data-concept-id="' + id + '" aria-label="Edit ' + escapeHtml(concept.name) + '">Edit</button>';
    if (concept.status === 'retired') {
      actions += '<button type="button" class="btn btn-ghost btn-sm" data-action="restore" data-concept-id="' + id + '">Restore</button>';
    } else {
      actions += '<button type="button" class="btn btn-ghost btn-sm" data-action="retire" data-concept-id="' + id + '">Retire</button>';
    }
    actions += '<button type="button" class="btn btn-danger btn-sm" data-action="delete" data-concept-id="' + id + '"' + (assignments.length ? ' aria-describedby="assignment-' + id + '"' : '') + '>Delete</button>';
    var provenance = concept.source === 'ai'
      ? ' · ' + escapeHtml(concept.aiProvider) + ' / ' + escapeHtml(concept.aiModelId) + ' · Generated ' + escapeHtml(formatDate(concept.aiGeneratedAt))
      : '';
    return '<article class="top3-item ' + escapeHtml(concept.status) + '" data-record-id="' + id + '">'
      + '<div class="top3-heading"><div><h3>' + escapeHtml(concept.name) + '</h3><span class="text-xs text-muted">' + source + provenance + '</span></div>'
      + '<span class="badge badge-' + (concept.status === 'active' ? 'processed' : 'draft') + '">' + escapeHtml(concept.status) + '</span></div>'
      + '<div class="top3-copy">' + escapeHtml(concept.description) + '</div>' + rules + notes + examples
      + '<div id="assignment-' + id + '">' + assignmentMarkup + '</div>'
      + '<div class="top3-meta">Added ' + escapeHtml(formatDate(concept.createdAt)) + (concept.updatedAt ? ' · Updated ' + escapeHtml(formatDate(concept.updatedAt)) : '') + '</div>'
      + '<div class="top3-actions">' + actions + '</div></article>';
  }

  function announce(message) {
    var element = root.document.getElementById('pageNotice');
    if (element) element.textContent = message || '';
  }

  function renderConcepts() {
    var visible = concepts.filter(function(concept) {
      return conceptMatches(concept, currentFilter, currentQuery);
    }).sort(function(left, right) {
      if (left.status !== right.status) return left.status === 'active' ? -1 : 1;
      return left.name.localeCompare(right.name);
    });
    var active = concepts.filter(function(concept) { return concept.status === 'active'; }).length;
    var assigned = concepts.filter(function(concept) { return (concept.assignedEpisodes || []).length; }).length;
    root.document.getElementById('top3Count').textContent = concepts.length + ' total · ' + active + ' active · ' + assigned + ' assigned';
    root.document.getElementById('top3List').innerHTML = visible.map(conceptCardMarkup).join('');
    root.document.getElementById('noTop3Concepts').classList.toggle('hidden', visible.length !== 0);
  }

  function clearErrors() {
    root.document.querySelectorAll('#top3Form input, #top3Form textarea').forEach(function(field) {
      field.classList.remove('field-error');
      field.removeAttribute('aria-invalid');
    });
    root.document.getElementById('top3FormError').textContent = '';
  }

  function showError(message, fieldId) {
    root.document.getElementById('top3FormError').textContent = message;
    if (fieldId) {
      var field = root.document.getElementById(fieldId);
      field.classList.add('field-error');
      field.setAttribute('aria-invalid', 'true');
      field.focus();
    }
  }

  function formValues() {
    return {
      name: root.document.getElementById('top3Name').value,
      description: root.document.getElementById('top3Description').value,
      rules: root.document.getElementById('top3Rules').value,
      hostNotes: root.document.getElementById('top3HostNotes').value,
      aiExample: [1, 2, 3].map(function(rank) {
        return root.document.getElementById('top3Example' + rank).value;
      })
    };
  }

  function setFormValues(concept) {
    root.document.getElementById('top3Name').value = concept.name || '';
    root.document.getElementById('top3Description').value = concept.description || '';
    root.document.getElementById('top3Rules').value = concept.rules || '';
    root.document.getElementById('top3HostNotes').value = concept.hostNotes || '';
    [1, 2, 3].forEach(function(rank) {
      root.document.getElementById('top3Example' + rank).value = (concept.aiExample || [])[rank - 1] || '';
    });
  }

  function resetForm() {
    editingConceptId = null;
    acceptedProvenance = null;
    draftConceptId = null;
    root.document.getElementById('top3Form').reset();
    root.document.getElementById('top3FormHeading').textContent = 'Create a Top 3 Concept';
    root.document.getElementById('generateTop3Button').textContent = 'Generate AI Proposal';
    root.document.getElementById('saveTop3Button').textContent = 'Save Manually';
    root.document.getElementById('cancelTop3EditButton').classList.add('hidden');
    root.document.getElementById('proposalNotice').textContent = '';
    clearErrors();
  }

  function editConcept(conceptId) {
    var concept = concepts.find(function(candidate) { return candidate.id === conceptId; });
    if (!concept) {
      announce('That concept is no longer available. The latest Top 3 Bank is shown.');
      renderConcepts();
      return;
    }
    editingConceptId = concept.id;
    acceptedProvenance = concept.source === 'ai' ? {
      source: 'ai',
      aiProvider: concept.aiProvider,
      aiModelId: concept.aiModelId,
      aiGeneratedAt: concept.aiGeneratedAt
    } : null;
    setFormValues(concept);
    root.document.getElementById('top3FormHeading').textContent = 'Edit Top 3 Concept';
    root.document.getElementById('generateTop3Button').textContent = 'Regenerate AI Proposal';
    root.document.getElementById('saveTop3Button').textContent = acceptedProvenance ? 'Save AI Concept Changes' : 'Save Changes';
    root.document.getElementById('cancelTop3EditButton').classList.remove('hidden');
    root.document.getElementById('proposalNotice').textContent = acceptedProvenance ? 'This banked concept retains its AI provenance.' : '';
    clearErrors();
    root.document.getElementById('top3Description').focus();
    root.document.getElementById('top3FormHeading').scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  async function generateProposal() {
    clearErrors();
    var values = formValues();
    if (!String(values.description || '').trim()) {
      showError('Concept description is required before AI generation.', 'top3Description');
      return;
    }
    var button = root.document.getElementById('generateTop3Button');
    button.disabled = true;
    announce(editingConceptId || acceptedProvenance ? 'Regenerating AI proposal…' : 'Generating AI proposal…');
    var proposal;
    var beforeGeneration = bankFingerprint(concepts);
    try {
      proposal = await apiRequest('/ai/top3-concept', {
        method: 'POST',
        body: {
          description: String(values.description).trim(),
          name: String(values.name || '').trim() || null,
          rules: String(values.rules || '').trim() || null,
          hostNotes: String(values.hostNotes || '').trim() || null
        }
      });
    } catch (error) {
      showError(error.message);
      announce('AI generation failed. Your workshop entries are unchanged; correct the issue and retry.');
      button.disabled = false;
      return;
    }

    acceptedProvenance = {
      source: 'ai',
      aiProvider: proposal.aiProvider,
      aiModelId: proposal.aiModelId,
      aiGeneratedAt: proposal.aiGeneratedAt
    };
    setFormValues(proposal);
    root.document.getElementById('generateTop3Button').textContent = 'Regenerate AI Proposal';
    root.document.getElementById('saveTop3Button').textContent = editingConceptId ? 'Save AI Concept Changes' : 'Save AI Proposal';
    try {
      // AI generation is intentionally read-only, but its network round trip
      // can outlive another mutation. Refresh both the bank and revision while
      // leaving the generated workshop values untouched.
      await loadConcepts();
      var bankChanged = beforeGeneration !== bankFingerprint(concepts);
      renderConcepts();
      root.document.getElementById('proposalNotice').textContent = bankChanged
        ? 'AI proposal loaded and preserved. The Top 3 Bank changed during generation, so the latest concepts are shown; review both before saving.'
        : 'AI proposal loaded for review. These are fictional examples, not participant picks. Nothing has been saved yet.';
      announce(bankChanged
        ? 'AI proposal ready. The latest Top 3 Bank was reconciled for review.'
        : 'AI proposal ready for review and editing.');
      root.document.getElementById('top3Name').focus();
    } catch (error) {
      showError('The AI proposal is preserved, but the latest Top 3 revision could not be loaded. Retry generation or reload before saving.');
      announce('AI proposal ready, but revision reconciliation failed. Do not save until the bank reloads successfully.');
    } finally {
      button.disabled = false;
    }
  }

  async function saveConcept(event) {
    event.preventDefault();
    clearErrors();
    var values;
    try {
      values = validateConceptInput(formValues(), Boolean(acceptedProvenance));
    } catch (error) {
      var fieldId = /description/i.test(error.message) ? 'top3Description' : /name/i.test(error.message) ? 'top3Name' : null;
      showError(error.message, fieldId);
      return;
    }
    var existing = editingConceptId
      ? concepts.find(function(concept) { return concept.id === editingConceptId; })
      : null;
    if (editingConceptId && !existing) {
      showError('That concept no longer exists. The latest bank is shown; start a new concept or retry another edit.');
      return;
    }
    var provenance = acceptedProvenance || {
      source: 'manual', aiProvider: null, aiModelId: null, aiGeneratedAt: null
    };
    if (!existing && !draftConceptId) draftConceptId = generateId();
    var payload = Object.assign({
      id: existing ? existing.id : draftConceptId,
      status: existing ? existing.status : 'active'
    }, values, provenance);
    var button = root.document.getElementById('saveTop3Button');
    button.disabled = true;
    announce(existing ? 'Saving concept changes…' : 'Banking concept…');
    try {
      await apiRequest(existing ? '/top3/concepts/' + encodeURIComponent(existing.id) : '/top3/concepts', {
        method: existing ? 'PUT' : 'POST',
        mutation: true,
        body: payload
      });
      await loadConcepts();
      var wasEditing = Boolean(existing);
      resetForm();
      renderConcepts();
      announce(wasEditing ? 'Concept changes saved.' : 'Concept added to the Top 3 Bank.');
      root.Toast.success(wasEditing ? 'Top 3 concept updated.' : 'Top 3 concept banked.');
    } catch (error) {
      renderConcepts();
      showError(error.message);
      announce('Save failed. Your workshop remains available; review the latest bank and retry.');
    } finally {
      button.disabled = false;
    }
  }

  async function runLifecycleAction(action, conceptId) {
    var concept = concepts.find(function(candidate) { return candidate.id === conceptId; });
    if (!concept) {
      announce('That concept is no longer available. The latest Top 3 Bank is shown.');
      renderConcepts();
      return;
    }
    var assignments = concept.assignedEpisodes || [];
    var confirmed = true;
    if (action === 'delete') {
      confirmed = root.confirm('Delete “' + concept.name + '”? This cannot be undone.' + (assignments.length ? ' Assigned concepts cannot be deleted until their episode assignments are removed.' : ''));
    } else if (action === 'retire') {
      confirmed = root.confirm('Retire “' + concept.name + '”? It will remain visible and can be restored.');
    }
    if (!confirmed) return;
    announce('Updating Top 3 Bank…');
    try {
      if (action === 'delete') {
        await apiRequest('/top3/concepts/' + encodeURIComponent(concept.id), {
          method: 'DELETE', mutation: true
        });
      } else {
        var payload = conceptPayload(concept);
        payload.status = action === 'restore' ? 'active' : 'retired';
        await apiRequest('/top3/concepts/' + encodeURIComponent(concept.id), {
          method: 'PUT', mutation: true, body: payload
        });
      }
      await loadConcepts();
      if (editingConceptId === conceptId && action === 'delete') resetForm();
      renderConcepts();
      announce(action === 'delete' ? 'Concept deleted.' : action === 'retire' ? 'Concept retired.' : 'Concept restored.');
    } catch (error) {
      renderConcepts();
      announce('The action failed. ' + error.message);
      root.Toast.error(error.message);
    }
  }

  function bindEvents() {
    root.document.getElementById('top3Form').addEventListener('submit', saveConcept);
    root.document.getElementById('generateTop3Button').addEventListener('click', generateProposal);
    root.document.getElementById('cancelTop3EditButton').addEventListener('click', resetForm);
    root.document.querySelector('[data-action="logout"]').addEventListener('click', function() { root.Auth.logout(); });
    root.document.getElementById('top3Search').addEventListener('input', function(event) {
      currentQuery = event.target.value;
      renderConcepts();
    });
    root.document.querySelector('.top3-filters').addEventListener('click', function(event) {
      var button = event.target.closest('[data-filter]');
      if (!button) return;
      currentFilter = button.dataset.filter;
      root.document.querySelectorAll('[data-filter]').forEach(function(candidate) {
        var active = candidate.dataset.filter === currentFilter;
        candidate.classList.toggle('active', active);
        candidate.setAttribute('aria-pressed', active ? 'true' : 'false');
      });
      renderConcepts();
    });
    root.document.getElementById('top3List').addEventListener('click', function(event) {
      var button = event.target.closest('[data-action][data-concept-id]');
      if (!button) return;
      if (button.dataset.action === 'edit') editConcept(button.dataset.conceptId);
      else runLifecycleAction(button.dataset.action, button.dataset.conceptId);
    });
  }

  async function onStorageReady() {
    try {
      await loadConcepts();
      renderConcepts();
      announce('Top 3 Bank loaded.');
    } catch (error) {
      showError(error.message);
      announce('Top 3 Bank failed to load. Reload the page to retry.');
    }
  }

  function start() {
    bindEvents();
    root.Auth.init();
  }

  return {
    escapeHtml: escapeHtml,
    normalizeExamples: normalizeExamples,
    validateConceptInput: validateConceptInput,
    conceptPayload: conceptPayload,
    bankFingerprint: bankFingerprint,
    conceptMatches: conceptMatches,
    conceptCardMarkup: conceptCardMarkup,
    generateProposal: generateProposal,
    saveConcept: saveConcept,
    onStorageReady: onStorageReady,
    start: start
  };
});
