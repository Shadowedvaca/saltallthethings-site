/* Reusable multi-guest selection and private preparation rendering. */
(function(root, factory) {
  var api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.GuestPreparation = api;
})(typeof window !== 'undefined' ? window : globalThis, function() {
  'use strict';

  function escapeHtml(value) {
    if (value == null) return '';
    return String(value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  function compareGuests(left, right) {
    var byName = String(left.displayName || '').localeCompare(String(right.displayName || ''));
    return byName || String(left.id || '').localeCompare(String(right.id || ''));
  }

  function assignmentIds(assignments, ideaId) {
    return new Set((assignments || []).filter(function(assignment) {
      return assignment.ideaId === ideaId;
    }).map(function(assignment) { return assignment.guestId; }));
  }

  function guestsForIdea(guests, assignments, ideaId) {
    var ids = assignmentIds(assignments, ideaId);
    return (guests || []).filter(function(guest) { return ids.has(guest.id); }).sort(compareGuests);
  }

  function availableGuests(guests, assignments, ideaId) {
    var assigned = assignmentIds(assignments, ideaId);
    return (guests || []).filter(function(guest) {
      return guest.status === 'active' && !assigned.has(guest.id);
    }).sort(compareGuests);
  }

  function guestCardMarkup(guest, ideaId) {
    var archived = guest.status === 'archived';
    var notes = guest.privateNotes
      ? '<div class="show-guest-notes"><strong>Private host notes</strong><p>' + escapeHtml(guest.privateNotes) + '</p></div>'
      : '<p class="text-xs text-muted mt-sm">No private host notes.</p>';
    return '<div class="show-guest-card' + (archived ? ' archived' : '') + '">'
      + '<div class="show-guest-heading"><div><strong>' + escapeHtml(guest.displayName) + '</strong>'
      + (archived ? '<span class="badge badge-draft">archived</span>' : '') + '</div>'
      + '<button type="button" class="btn btn-ghost btn-sm" data-guest-action="remove" data-idea-id="'
      + escapeHtml(ideaId) + '" data-guest-id="' + escapeHtml(guest.id) + '" aria-label="Remove '
      + escapeHtml(guest.displayName) + ' from this show">Remove</button></div>' + notes + '</div>';
  }

  function choiceMarkup(guest, ideaId) {
    return '<button type="button" class="guest-choice" data-guest-action="assign" data-idea-id="'
      + escapeHtml(ideaId) + '" data-guest-id="' + escapeHtml(guest.id) + '"><strong>'
      + escapeHtml(guest.displayName) + '</strong><span>Assign to this show</span></button>';
  }

  function renderPicker(ideaId, guests, assignments) {
    var assigned = guestsForIdea(guests, assignments, ideaId);
    var available = availableGuests(guests, assignments, ideaId);
    var html = assigned.length
      ? '<div class="show-guest-list">' + assigned.map(function(guest) {
        return guestCardMarkup(guest, ideaId);
      }).join('') + '</div>'
      : '<p class="text-sm text-muted">No guests assigned to this show.</p>';
    if (available.length) {
      html += '<details class="guest-add" onclick="event.stopPropagation()"><summary>Add guest</summary><div class="guest-choice-list">'
        + available.map(function(guest) { return choiceMarkup(guest, ideaId); }).join('')
        + '</div></details>';
    } else {
      html += '<p class="text-xs text-muted mt-sm">No additional active guests available. <a href="guests.html">Open the Guest Bank</a> to create or restore a guest.</p>';
    }
    return html;
  }

  function renderSummary(ideaId, guests, assignments) {
    var assigned = guestsForIdea(guests, assignments, ideaId);
    if (!assigned.length) return '';
    return '<div class="show-guest-summary"><strong>Guests:</strong> '
      + assigned.map(function(guest) {
        return '<span>' + escapeHtml(guest.displayName)
          + (guest.status === 'archived' ? ' <em>(archived)</em>' : '') + '</span>';
      }).join(', ') + '</div>';
  }

  function renderPreparation(guests) {
    if (!guests || !guests.length) return '';
    return '<div class="show-display-section show-display-guests"><h2>Guests</h2><div class="show-display-guest-list">'
      + guests.map(function(guest) {
        var notes = guest.privateNotes
          ? '<div class="show-display-guest-notes"><strong>Private host notes</strong><p>' + escapeHtml(guest.privateNotes) + '</p></div>'
          : '<p class="text-muted">No private host notes.</p>';
        return '<article class="show-display-guest' + (guest.status === 'archived' ? ' archived' : '') + '"><h3>'
          + escapeHtml(guest.displayName) + (guest.status === 'archived' ? ' <span class="badge badge-draft">archived</span>' : '')
          + '</h3>' + notes + '</article>';
      }).join('') + '</div></div>';
  }

  return {
    escapeHtml: escapeHtml,
    guestsForIdea: guestsForIdea,
    availableGuests: availableGuests,
    renderPicker: renderPicker,
    renderSummary: renderSummary,
    renderPreparation: renderPreparation
  };
});
