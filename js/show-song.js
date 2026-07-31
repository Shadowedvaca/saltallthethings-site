/* Song selection and private preparation rendering for Show Management. */
(function(root, factory) {
  var api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.SongPreparation = api;
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

  function songForIdea(songs, ideaId) {
    return songs.find(function(song) {
      return song.status === 'used' && song.assignedIdeaId === ideaId;
    }) || null;
  }

  function availableSongs(songs) {
    return songs.filter(function(song) { return song.status === 'unused'; })
      .sort(function(left, right) {
        return (left.artist + left.title).localeCompare(right.artist + right.title);
      });
  }

  function songChoiceMarkup(song, ideaId, verb) {
    return '<button type="button" class="song-choice" data-song-action="assign" data-idea-id="'
      + escapeHtml(ideaId) + '" data-song-id="' + escapeHtml(song.id) + '">'
      + '<strong>' + escapeHtml(song.artist) + '</strong> — ' + escapeHtml(song.title)
      + '<span>' + escapeHtml(verb) + '</span></button>';
  }

  function assignedSongMarkup(song, ideaId) {
    var notes = song.privateNotes
      ? '<div class="song-prep-notes"><strong>Private talking points</strong><p>' + escapeHtml(song.privateNotes) + '</p></div>'
      : '<p class="text-sm text-muted mt-sm">No private talking points saved.</p>';
    return '<div class="song-prep-card">'
      + '<div class="song-prep-heading"><div><strong>' + escapeHtml(song.artist) + '</strong> — ' + escapeHtml(song.title)
      + '<div><a href="' + escapeHtml(song.youtubeUrl) + '" target="_blank" rel="noopener noreferrer">Open YouTube link</a></div></div>'
      + '<button type="button" class="btn btn-ghost btn-sm" data-song-action="remove" data-idea-id="'
      + escapeHtml(ideaId) + '" data-song-id="' + escapeHtml(song.id) + '">Remove</button></div>'
      + notes + '</div>';
  }

  function renderPicker(ideaId, songs) {
    var assigned = songForIdea(songs, ideaId);
    var available = availableSongs(songs);
    var html = assigned ? assignedSongMarkup(assigned, ideaId) : '';
    if (available.length > 0) {
      var choices = available.map(function(song) {
        return songChoiceMarkup(song, ideaId, assigned ? 'Replace current song' : 'Assign to this episode');
      }).join('');
      if (assigned) {
        html += '<details class="song-replace"><summary>Replace song</summary><div class="song-choice-list">' + choices + '</div></details>';
      } else {
        html += '<div class="song-choice-list">' + choices + '</div>';
      }
    } else if (!assigned) {
      html = '<p class="text-sm text-muted">No unused songs available. <a href="songs.html">Build your Song Bank</a> first.</p>';
    } else {
      html += '<p class="text-xs text-muted mt-sm">No other unused songs are available.</p>';
    }
    return html;
  }

  function renderPreparation(song) {
    if (!song) return '';
    var notes = song.privateNotes
      ? '<div class="show-display-song-notes"><strong>Private talking points</strong><p>' + escapeHtml(song.privateNotes) + '</p></div>'
      : '<p class="text-muted">No private talking points saved.</p>';
    return '<div class="show-display-section show-display-song">'
      + '<h2>Episode Song</h2>'
      + '<div class="show-display-song-title"><strong>' + escapeHtml(song.artist) + '</strong> — ' + escapeHtml(song.title) + '</div>'
      + '<p><a href="' + escapeHtml(song.youtubeUrl) + '" target="_blank" rel="noopener noreferrer">Open YouTube link</a></p>'
      + notes + '</div>';
  }

  return {
    escapeHtml: escapeHtml,
    songForIdea: songForIdea,
    availableSongs: availableSongs,
    renderPicker: renderPicker,
    renderPreparation: renderPreparation
  };
});
