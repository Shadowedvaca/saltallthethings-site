/* Authenticated Guest Bank management and appearance-history page. */
(function(root, factory) {
  if (typeof module === 'object' && module.exports) {
    module.exports = factory(root);
  } else {
    var api = factory({
      document: root.document,
      confirm: root.confirm.bind(root),
      Auth: Auth,
      Storage: Storage,
      Toast: Toast
    });
    root.GuestBankPage = api;
    root.onStorageReady = api.onStorageReady;
    api.start();
  }
})(typeof window !== 'undefined' ? window : globalThis, function(root) {
  'use strict';

  var currentFilter = 'all';
  var currentQuery = '';
  var editingGuestId = null;

  function escapeHtml(value) {
    if (value == null) return '';
    return String(value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  function validateGuestInput(values) {
    var displayName = String(values.displayName || '').trim();
    var privateNotes = String(values.privateNotes || '').trim();
    if (!displayName) throw new Error('Display name is required.');
    if (displayName.length > 200) throw new Error('Display name must be at most 200 characters.');
    if (privateNotes.length > 8000) throw new Error('Private host notes must be at most 8000 characters.');
    return { displayName: displayName, privateNotes: privateNotes };
  }

  function formatDate(value) {
    if (!value) return '';
    var date = new Date(value);
    if (Number.isNaN(date.getTime())) return '';
    return date.toLocaleDateString('en-US', {
      month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC'
    });
  }

  function historySearchText(guest) {
    return (guest.appearanceHistory || []).map(function(appearance) {
      return [appearance.title, appearance.ideaId, appearance.episodeNumber, appearance.releaseDate, appearance.scheduled ? 'scheduled' : 'unscheduled'].join(' ');
    }).join(' ');
  }

  function guestMatches(guest, filter, query) {
    if (filter !== 'all' && guest.status !== filter) return false;
    var needle = String(query || '').trim().toLowerCase();
    if (!needle) return true;
    return [guest.displayName, guest.privateNotes, historySearchText(guest)]
      .some(function(value) { return String(value || '').toLowerCase().includes(needle); });
  }

  function appearanceMarkup(appearance) {
    var episode = appearance.episodeNumber == null
      ? ''
      : '<strong>Episode ' + escapeHtml(appearance.episodeNumber) + ':</strong> ';
    var schedule = appearance.scheduled && appearance.releaseDate
      ? '<span class="text-muted"> — ' + escapeHtml(formatDate(appearance.releaseDate)) + '</span>'
      : '<span class="guest-unscheduled"> — Unscheduled</span>';
    return '<li data-idea-id="' + escapeHtml(appearance.ideaId) + '">'
      + episode + escapeHtml(appearance.title || 'Untitled episode idea') + schedule + '</li>';
  }

  function guestCardMarkup(guest) {
    var id = escapeHtml(guest.id);
    var total = Number.isInteger(guest.totalAppearances) ? guest.totalAppearances : 0;
    var first = guest.firstAppearance ? formatDate(guest.firstAppearance) : 'Not scheduled';
    var recent = guest.mostRecentAppearance ? formatDate(guest.mostRecentAppearance) : 'Not scheduled';
    var history = Array.isArray(guest.appearanceHistory) ? guest.appearanceHistory : [];
    var notes = guest.privateNotes
      ? '<div class="guest-notes"><strong class="text-xs text-muted">PRIVATE HOST NOTES</strong><br>' + escapeHtml(guest.privateNotes) + '</div>'
      : '<div class="guest-notes text-muted text-sm">No private host notes.</div>';
    var historyMarkup = history.length
      ? '<details class="guest-history"><summary>Appearance history (' + total + ')</summary><ul>'
        + history.map(appearanceMarkup).join('') + '</ul></details>'
      : '<div class="guest-history text-muted text-sm">No episode appearances yet.</div>';
    var actions = '<button type="button" class="btn btn-ghost btn-sm" data-action="edit" data-guest-id="' + id + '" aria-label="Edit ' + escapeHtml(guest.displayName) + '">Edit</button>';
    actions += guest.status === 'archived'
      ? '<button type="button" class="btn btn-ghost btn-sm" data-action="restore" data-guest-id="' + id + '">Restore</button>'
      : '<button type="button" class="btn btn-ghost btn-sm" data-action="archive" data-guest-id="' + id + '">Archive</button>';
    actions += '<button type="button" class="btn btn-danger btn-sm" data-action="delete" data-guest-id="' + id + '" aria-describedby="guest-delete-' + id + '">Delete</button>';
    var deletionGuidance = total
      ? '<span id="guest-delete-' + id + '" class="text-xs text-muted">Remove all show assignments before deleting this guest.</span>'
      : '<span id="guest-delete-' + id + '" class="text-xs text-muted">Deletion is permanent.</span>';
    return '<article class="guest-item ' + escapeHtml(guest.status) + '" data-record-id="' + id + '">'
      + '<div class="guest-heading"><h3>' + escapeHtml(guest.displayName) + '</h3>'
      + '<span class="badge badge-' + (guest.status === 'active' ? 'processed' : 'draft') + '">' + escapeHtml(guest.status) + '</span></div>'
      + notes
      + '<dl class="guest-stats"><div class="guest-stat"><dt>Total appearances</dt><dd>' + total + '</dd></div>'
      + '<div class="guest-stat"><dt>First appearance</dt><dd>' + escapeHtml(first) + '</dd></div>'
      + '<div class="guest-stat"><dt>Most recent</dt><dd>' + escapeHtml(recent) + '</dd></div></dl>'
      + historyMarkup
      + '<div class="guest-meta">Added ' + escapeHtml(formatDate(guest.createdAt)) + (guest.updatedAt ? ' · Updated ' + escapeHtml(formatDate(guest.updatedAt)) : '') + '</div>'
      + '<div class="guest-actions">' + actions + '</div>' + deletionGuidance + '</article>';
  }

  function announce(message) {
    var element = root.document.getElementById('pageNotice');
    if (element) element.textContent = message || '';
  }

  function renderGuests() {
    var guests = root.Storage.getGuests();
    var visible = guests.filter(function(guest) {
      return guestMatches(guest, currentFilter, currentQuery);
    }).sort(function(left, right) {
      if (left.status !== right.status) return left.status === 'active' ? -1 : 1;
      return left.displayName.localeCompare(right.displayName);
    });
    var active = guests.filter(function(guest) { return guest.status === 'active'; }).length;
    var archived = guests.length - active;
    root.document.getElementById('guestCount').textContent = guests.length + ' total · ' + active + ' active · ' + archived + ' archived';
    root.document.getElementById('guestList').innerHTML = visible.map(guestCardMarkup).join('');
    root.document.getElementById('noGuests').classList.toggle('hidden', visible.length !== 0);
  }

  function clearErrors() {
    root.document.querySelectorAll('#guestForm input, #guestForm textarea').forEach(function(field) {
      field.classList.remove('field-error');
      field.removeAttribute('aria-invalid');
    });
    root.document.getElementById('guestFormError').textContent = '';
  }

  function showError(message, fieldId) {
    root.document.getElementById('guestFormError').textContent = message;
    if (fieldId) {
      var field = root.document.getElementById(fieldId);
      field.classList.add('field-error');
      field.setAttribute('aria-invalid', 'true');
      field.focus();
    }
  }

  function resetForm() {
    editingGuestId = null;
    root.document.getElementById('guestForm').reset();
    root.document.getElementById('guestFormHeading').textContent = 'Add a Guest';
    root.document.getElementById('saveGuestButton').textContent = 'Add Guest';
    root.document.getElementById('cancelGuestEditButton').classList.add('hidden');
    clearErrors();
  }

  function editGuest(guestId) {
    var guest = root.Storage.getGuests().find(function(candidate) { return candidate.id === guestId; });
    if (!guest) {
      announce('That guest is no longer available. The latest Guest Bank is shown.');
      renderGuests();
      return;
    }
    editingGuestId = guest.id;
    root.document.getElementById('guestDisplayName').value = guest.displayName;
    root.document.getElementById('guestPrivateNotes').value = guest.privateNotes || '';
    root.document.getElementById('guestFormHeading').textContent = 'Edit Guest';
    root.document.getElementById('saveGuestButton').textContent = 'Save Changes';
    root.document.getElementById('cancelGuestEditButton').classList.remove('hidden');
    clearErrors();
    root.document.getElementById('guestDisplayName').focus();
    root.document.getElementById('guestFormHeading').scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  async function submitGuest(event) {
    event.preventDefault();
    clearErrors();
    var values;
    try {
      values = validateGuestInput({
        displayName: root.document.getElementById('guestDisplayName').value,
        privateNotes: root.document.getElementById('guestPrivateNotes').value
      });
    } catch (error) {
      showError(error.message, /name/i.test(error.message) ? 'guestDisplayName' : 'guestPrivateNotes');
      return;
    }
    var existing = editingGuestId
      ? root.Storage.getGuests().find(function(guest) { return guest.id === editingGuestId; })
      : null;
    if (editingGuestId && !existing) {
      showError('That guest no longer exists. The latest Guest Bank is shown.');
      renderGuests();
      return;
    }
    var button = root.document.getElementById('saveGuestButton');
    button.disabled = true;
    announce(existing ? 'Saving guest changes…' : 'Adding guest…');
    var success = existing
      ? await root.Storage.updateGuest(existing.id, values)
      : await root.Storage.addGuest(Object.assign({
        id: 'guest-' + root.Storage.generateId(),
        status: 'active',
        createdAt: new Date().toISOString()
      }, values));
    button.disabled = false;
    if (!success) {
      announce('Save failed or conflicted. The latest server data is shown; review your change and try again.');
      renderGuests();
      return;
    }
    var wasEditing = Boolean(existing);
    resetForm();
    renderGuests();
    announce(wasEditing ? 'Guest changes saved.' : 'Guest added to the bank.');
    root.Toast.success(wasEditing ? 'Guest updated.' : 'Guest added.');
  }

  async function runLifecycleAction(action, guestId) {
    var guest = root.Storage.getGuests().find(function(candidate) { return candidate.id === guestId; });
    if (!guest) {
      announce('That guest is no longer available. The latest Guest Bank is shown.');
      renderGuests();
      return;
    }
    var total = Number.isInteger(guest.totalAppearances) ? guest.totalAppearances : 0;
    if (action === 'delete' && total > 0) {
      var guidance = 'This guest is assigned to ' + total + ' show' + (total === 1 ? '' : 's') + '. Remove every assignment in Show Management before deleting the guest.';
      announce(guidance);
      root.Toast.error(guidance);
      return;
    }
    var confirmed = action !== 'delete' || root.confirm('Delete “' + guest.displayName + '”? This cannot be undone.');
    if (!confirmed) return;
    announce(action === 'delete' ? 'Deleting guest…' : action === 'archive' ? 'Archiving guest…' : 'Restoring guest…');
    var success = action === 'delete'
      ? await root.Storage.deleteGuest(guestId)
      : await root.Storage.setGuestStatus(guestId, action === 'archive' ? 'archived' : 'active');
    renderGuests();
    if (!success) {
      announce(action === 'delete'
        ? 'Guest could not be deleted. Remove every show assignment first, or review the latest server data and retry.'
        : 'The update failed or conflicted. The latest server data is shown; review and retry.');
      return;
    }
    if (editingGuestId === guestId && action === 'delete') resetForm();
    announce(action === 'delete' ? 'Guest deleted.' : action === 'archive' ? 'Guest archived with appearance history preserved.' : 'Guest restored and available for future assignment.');
  }

  function bindEvents() {
    root.document.getElementById('guestForm').addEventListener('submit', submitGuest);
    root.document.getElementById('cancelGuestEditButton').addEventListener('click', resetForm);
    root.document.querySelector('[data-action="logout"]').addEventListener('click', function() { root.Auth.logout(); });
    root.document.getElementById('guestSearch').addEventListener('input', function(event) {
      currentQuery = event.target.value;
      renderGuests();
    });
    root.document.querySelector('.guest-filters').addEventListener('click', function(event) {
      var button = event.target.closest('[data-filter]');
      if (!button) return;
      currentFilter = button.dataset.filter;
      root.document.querySelectorAll('[data-filter]').forEach(function(candidate) {
        var active = candidate.dataset.filter === currentFilter;
        candidate.classList.toggle('active', active);
        candidate.setAttribute('aria-pressed', active ? 'true' : 'false');
      });
      renderGuests();
    });
    root.document.getElementById('guestList').addEventListener('click', async function(event) {
      var button = event.target.closest('[data-action][data-guest-id]');
      if (!button) return;
      if (button.dataset.action === 'edit') {
        editGuest(button.dataset.guestId);
        return;
      }
      button.disabled = true;
      try {
        await runLifecycleAction(button.dataset.action, button.dataset.guestId);
      } finally {
        button.disabled = false;
      }
    });
  }

  function onStorageReady() {
    renderGuests();
    announce('Guest Bank loaded.');
  }

  function start() {
    bindEvents();
    root.Auth.init();
  }

  return {
    escapeHtml: escapeHtml,
    validateGuestInput: validateGuestInput,
    guestMatches: guestMatches,
    appearanceMarkup: appearanceMarkup,
    guestCardMarkup: guestCardMarkup,
    renderGuests: renderGuests,
    runLifecycleAction: runLifecycleAction,
    onStorageReady: onStorageReady,
    start: start
  };
});
