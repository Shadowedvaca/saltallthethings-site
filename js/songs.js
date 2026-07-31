/* Authenticated Song Bank management page. */
(function(root, factory) {
  var api = factory(root);
  if (typeof module === 'object' && module.exports) {
    module.exports = api;
  } else {
    root.SongBankPage = api;
    root.onStorageReady = api.onStorageReady;
    api.start();
  }
})(typeof window !== 'undefined' ? window : globalThis, function(root) {
  'use strict';

  var currentFilter = 'all';
  var currentQuery = '';
  var editingSongId = null;
  var youtubeHosts = new Set([
    'youtube.com', 'www.youtube.com', 'm.youtube.com', 'music.youtube.com',
    'youtu.be', 'www.youtu.be'
  ]);
  var videoIdPattern = /^[A-Za-z0-9_-]{6,64}$/;

  function escapeHtml(value) {
    if (value == null) return '';
    return String(value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  function validateYoutubeUrl(value) {
    var text = String(value || '').trim();
    var parsed;
    try {
      parsed = new URL(text);
    } catch (error) {
      throw new Error('Enter a valid YouTube URL.');
    }
    var host = parsed.hostname.toLowerCase();
    if (parsed.protocol !== 'https:' || parsed.username || parsed.password || parsed.port || !youtubeHosts.has(host)) {
      throw new Error('Use an official HTTPS YouTube link.');
    }
    var parts = parsed.pathname.split('/').filter(Boolean);
    var videoId = null;
    if (host === 'youtu.be' || host === 'www.youtu.be') {
      if (parts.length === 1) videoId = parts[0];
    } else if (parsed.pathname.replace(/\/$/, '') === '/watch') {
      var values = parsed.searchParams.getAll('v');
      if (values.length === 1) videoId = values[0];
    } else if (parts.length === 2 && ['shorts', 'live', 'embed'].includes(parts[0])) {
      videoId = parts[1];
    }
    if (!videoId || !videoIdPattern.test(videoId)) {
      throw new Error('Use a YouTube watch, short, live, embed, or youtu.be video link.');
    }
    return text;
  }

  function validateSongInput(values) {
    var artist = String(values.artist || '').trim();
    var title = String(values.title || '').trim();
    if (!artist) throw new Error('Artist is required.');
    if (!title) throw new Error('Song title is required.');
    return {
      artist: artist,
      title: title,
      youtubeUrl: validateYoutubeUrl(values.youtubeUrl),
      privateNotes: String(values.privateNotes || '').trim()
    };
  }

  function ideaContext(song, ideas, slots, assignments) {
    if (!song.assignedIdeaId) return '';
    var idea = ideas.find(function(candidate) { return candidate.id === song.assignedIdeaId; });
    var title = idea ? (idea.selectedTitle || (idea.titles && idea.titles[0]) || 'Untitled episode idea') : 'Unavailable episode idea';
    var slotId = Object.keys(assignments || {}).find(function(candidateSlotId) {
      return assignments[candidateSlotId] === song.assignedIdeaId;
    });
    var slot = slotId ? slots.find(function(candidate) { return candidate.id === slotId; }) : null;
    var episode = slot && (slot.episodeNumber || slot.episodeNum);
    return episode ? 'Episode ' + episode + ': ' + title : title;
  }

  function songMatches(song, filter, query, context) {
    if (filter !== 'all' && song.status !== filter) return false;
    var needle = String(query || '').trim().toLowerCase();
    if (!needle) return true;
    return [song.artist, song.title, song.privateNotes, context]
      .some(function(value) { return String(value || '').toLowerCase().includes(needle); });
  }

  function formatDate(value) {
    if (!value) return '';
    var date = new Date(value);
    if (Number.isNaN(date.getTime())) return '';
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
  }

  function songCardMarkup(song, context) {
    var statusClass = song.status === 'unused' ? 'processed' : song.status === 'used' ? 'scheduled' : 'draft';
    var id = escapeHtml(song.id);
    var assignment = context
      ? '<div class="song-meta"><strong>Assigned:</strong> ' + escapeHtml(context) + '</div>'
      : '<div class="song-meta">Not assigned to an episode</div>';
    var notes = song.privateNotes
      ? '<div class="song-notes"><strong class="text-xs text-muted">PRIVATE TALKING POINTS</strong><br>' + escapeHtml(song.privateNotes) + '</div>'
      : '<div class="song-notes text-muted text-sm">No private talking points.</div>';
    var actions = '<button type="button" class="btn btn-ghost btn-sm" data-action="edit" data-song-id="' + id + '" aria-label="Edit ' + escapeHtml(song.title) + '">Edit</button>';
    if (song.status === 'retired') {
      actions += '<button type="button" class="btn btn-ghost btn-sm" data-action="restore" data-song-id="' + id + '">Restore</button>';
    } else {
      if (song.status === 'used') {
        actions += '<button type="button" class="btn btn-ghost btn-sm" data-action="free" data-song-id="' + id + '">Remove assignment</button>';
      }
      actions += '<button type="button" class="btn btn-ghost btn-sm" data-action="retire" data-song-id="' + id + '">Retire</button>';
    }
    actions += '<button type="button" class="btn btn-danger btn-sm" data-action="delete" data-song-id="' + id + '">Delete</button>';
    return '<article class="song-item ' + escapeHtml(song.status) + '" data-record-id="' + id + '">'
      + '<div class="song-heading"><div><h3><span class="song-artist">' + escapeHtml(song.artist) + '</span> — ' + escapeHtml(song.title) + '</h3>'
      + '<a class="text-sm" href="' + escapeHtml(song.youtubeUrl) + '" target="_blank" rel="noopener noreferrer">Open YouTube link</a></div>'
      + '<span class="badge badge-' + statusClass + '">' + escapeHtml(song.status) + '</span></div>'
      + notes + assignment
      + '<div class="song-meta">Added ' + escapeHtml(formatDate(song.createdAt)) + (song.updatedAt ? ' · Updated ' + escapeHtml(formatDate(song.updatedAt)) : '') + '</div>'
      + '<div class="song-actions">' + actions + '</div></article>';
  }

  function announce(message) {
    var element = root.document.getElementById('pageNotice');
    if (element) element.textContent = message || '';
  }

  function renderSongs() {
    var songs = root.Storage.getSongs();
    var ideas = root.Storage.getIdeas();
    var slots = root.Storage.getShowSlots();
    var assignments = root.Storage.getAssignments();
    var visible = songs.map(function(song) {
      return { song: song, context: ideaContext(song, ideas, slots, assignments) };
    }).filter(function(item) {
      return songMatches(item.song, currentFilter, currentQuery, item.context);
    }).sort(function(left, right) {
      var order = { unused: 0, used: 1, retired: 2 };
      var difference = order[left.song.status] - order[right.song.status];
      if (difference) return difference;
      return (left.song.artist + left.song.title).localeCompare(right.song.artist + right.song.title);
    });
    var unused = songs.filter(function(song) { return song.status === 'unused'; }).length;
    var used = songs.filter(function(song) { return song.status === 'used'; }).length;
    root.document.getElementById('songCount').textContent = songs.length + ' total · ' + unused + ' unused · ' + used + ' used';
    root.document.getElementById('songsList').innerHTML = visible.map(function(item) {
      return songCardMarkup(item.song, item.context);
    }).join('');
    root.document.getElementById('noSongs').classList.toggle('hidden', visible.length !== 0);
  }

  function clearFieldErrors() {
    root.document.querySelectorAll('#songForm input, #songForm textarea').forEach(function(field) {
      field.classList.remove('field-error');
      field.removeAttribute('aria-invalid');
    });
    root.document.getElementById('songFormError').textContent = '';
  }

  function showFormError(message, fieldId) {
    root.document.getElementById('songFormError').textContent = message;
    if (fieldId) {
      var field = root.document.getElementById(fieldId);
      field.classList.add('field-error');
      field.setAttribute('aria-invalid', 'true');
      field.focus();
    }
  }

  function resetForm() {
    editingSongId = null;
    root.document.getElementById('songForm').reset();
    root.document.getElementById('songFormHeading').textContent = 'Add a Song';
    root.document.getElementById('saveSongButton').textContent = 'Add Song';
    root.document.getElementById('cancelEditButton').classList.add('hidden');
    clearFieldErrors();
  }

  function editSong(songId) {
    var song = root.Storage.getSongs().find(function(candidate) { return candidate.id === songId; });
    if (!song) {
      announce('That song is no longer available. The latest Song Bank is shown.');
      renderSongs();
      return;
    }
    editingSongId = song.id;
    root.document.getElementById('songArtist').value = song.artist;
    root.document.getElementById('songTitle').value = song.title;
    root.document.getElementById('songYoutubeUrl').value = song.youtubeUrl;
    root.document.getElementById('songPrivateNotes').value = song.privateNotes || '';
    root.document.getElementById('songFormHeading').textContent = 'Edit Song';
    root.document.getElementById('saveSongButton').textContent = 'Save Changes';
    root.document.getElementById('cancelEditButton').classList.remove('hidden');
    clearFieldErrors();
    root.document.getElementById('songArtist').focus();
    root.document.getElementById('songFormHeading').scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  async function submitSong(event) {
    event.preventDefault();
    clearFieldErrors();
    var values;
    try {
      values = validateSongInput({
        artist: root.document.getElementById('songArtist').value,
        title: root.document.getElementById('songTitle').value,
        youtubeUrl: root.document.getElementById('songYoutubeUrl').value,
        privateNotes: root.document.getElementById('songPrivateNotes').value
      });
    } catch (error) {
      var fieldId = /Artist/.test(error.message) ? 'songArtist' : /title/.test(error.message) ? 'songTitle' : 'songYoutubeUrl';
      showFormError(error.message, fieldId);
      return;
    }
    var button = root.document.getElementById('saveSongButton');
    button.disabled = true;
    announce(editingSongId ? 'Saving song changes…' : 'Adding song…');
    var success;
    if (editingSongId) {
      success = await root.Storage.updateSong(editingSongId, values);
    } else {
      success = await root.Storage.addSong(Object.assign({
        id: root.Storage.generateId(),
        status: 'unused',
        assignedIdeaId: null,
        createdAt: new Date().toISOString()
      }, values));
    }
    button.disabled = false;
    if (!success) {
      announce('Save failed. The latest server data was restored; review the message and try again.');
      renderSongs();
      return;
    }
    var wasEditing = Boolean(editingSongId);
    resetForm();
    renderSongs();
    announce(wasEditing ? 'Song changes saved.' : 'Song added to the bank.');
    root.Toast.success(wasEditing ? 'Song updated.' : 'Song added.');
  }

  async function runLifecycleAction(action, songId) {
    var song = root.Storage.getSongs().find(function(candidate) { return candidate.id === songId; });
    if (!song) {
      announce('That song is no longer available. The latest Song Bank is shown.');
      renderSongs();
      return;
    }
    var confirmed = true;
    if (action === 'delete') {
      confirmed = root.confirm('Delete “' + song.artist + ' — ' + song.title + '”? This cannot be undone.' + (song.assignedIdeaId ? ' Its episode assignment will also be removed.' : ''));
    } else if (action === 'retire') {
      confirmed = root.confirm('Retire “' + song.artist + ' — ' + song.title + '”?' + (song.assignedIdeaId ? ' Its episode assignment will be removed.' : ''));
    } else if (action === 'free') {
      confirmed = root.confirm('Remove this song from its assigned episode?');
    }
    if (!confirmed) return;
    announce('Updating Song Bank…');
    var success = false;
    if (action === 'delete') success = await root.Storage.deleteSong(songId);
    if (action === 'retire') success = await root.Storage.setSongStatus(songId, 'retired');
    if (action === 'restore') success = await root.Storage.setSongStatus(songId, 'unused');
    if (action === 'free') success = await root.Storage.freeSong(songId);
    renderSongs();
    if (!success) {
      announce('The action failed. The latest server data is shown; review the message and try again.');
      return;
    }
    if (editingSongId === songId && action === 'delete') resetForm();
    announce(action === 'delete' ? 'Song deleted.' : action === 'retire' ? 'Song retired.' : action === 'restore' ? 'Song restored.' : 'Episode assignment removed.');
  }

  function bindEvents() {
    root.document.getElementById('songForm').addEventListener('submit', submitSong);
    root.document.getElementById('cancelEditButton').addEventListener('click', resetForm);
    root.document.querySelector('[data-action="logout"]').addEventListener('click', function() { root.Auth.logout(); });
    root.document.getElementById('songSearch').addEventListener('input', function(event) {
      currentQuery = event.target.value;
      renderSongs();
    });
    root.document.querySelector('.song-filters').addEventListener('click', function(event) {
      var button = event.target.closest('[data-filter]');
      if (!button) return;
      currentFilter = button.dataset.filter;
      root.document.querySelectorAll('[data-filter]').forEach(function(candidate) {
        var active = candidate.dataset.filter === currentFilter;
        candidate.classList.toggle('active', active);
        candidate.setAttribute('aria-pressed', active ? 'true' : 'false');
      });
      renderSongs();
    });
    root.document.getElementById('songsList').addEventListener('click', function(event) {
      var button = event.target.closest('[data-action][data-song-id]');
      if (!button) return;
      if (button.dataset.action === 'edit') editSong(button.dataset.songId);
      else runLifecycleAction(button.dataset.action, button.dataset.songId);
    });
  }

  function onStorageReady() {
    renderSongs();
    announce('Song Bank loaded.');
  }

  function start() {
    bindEvents();
    root.Auth.init();
  }

  return {
    escapeHtml: escapeHtml,
    validateYoutubeUrl: validateYoutubeUrl,
    validateSongInput: validateSongInput,
    ideaContext: ideaContext,
    songMatches: songMatches,
    songCardMarkup: songCardMarkup,
    onStorageReady: onStorageReady,
    start: start
  };
});
