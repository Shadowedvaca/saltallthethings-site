/* Deterministic public episode overview composition and clipboard support. */
(function(root, factory) {
  var api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.EpisodeOverview = api;
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

  function publicSongBlock(song) {
    if (!song) return '';
    return 'Featured song: ' + String(song.artist || '') + ' — ' + String(song.title || '')
      + '\nYouTube: ' + String(song.youtubeUrl || '');
  }

  function compose(summary, song) {
    var publicSummary = summary == null ? '' : String(summary);
    var songBlock = publicSongBlock(song);
    if (!songBlock) return publicSummary;
    if (!publicSummary) return songBlock;
    return publicSummary + '\n\n' + songBlock;
  }

  function render(text) {
    return '<div class="show-display-section spotify-overview">'
      + '<div class="spotify-overview-heading"><h2>Spotify Overview</h2>'
      + '<button type="button" class="btn btn-secondary btn-sm" onclick="copySpotifyOverview()" aria-describedby="spotifyOverviewStatus">Copy overview</button></div>'
      + '<pre id="spotifyOverviewText" tabindex="0">' + escapeHtml(text) + '</pre>'
      + '<p id="spotifyOverviewStatus" class="spotify-overview-status" role="status" aria-live="polite"></p>'
      + '</div>';
  }

  async function copy(text, navigatorObject, documentObject) {
    var payload = String(text == null ? '' : text);
    if (navigatorObject && navigatorObject.clipboard && typeof navigatorObject.clipboard.writeText === 'function') {
      try {
        await navigatorObject.clipboard.writeText(payload);
        return 'clipboard';
      } catch (error) {
        // Continue to the selectable-text fallback below.
      }
    }
    if (!documentObject || typeof documentObject.createElement !== 'function'
        || !documentObject.body || typeof documentObject.execCommand !== 'function') {
      throw new Error('Clipboard access is unavailable.');
    }
    var textarea = documentObject.createElement('textarea');
    textarea.value = payload;
    textarea.setAttribute('readonly', '');
    textarea.style.position = 'fixed';
    textarea.style.opacity = '0';
    documentObject.body.appendChild(textarea);
    textarea.select();
    var copied;
    try {
      copied = documentObject.execCommand('copy');
    } finally {
      documentObject.body.removeChild(textarea);
    }
    if (!copied) throw new Error('The browser did not copy the overview.');
    return 'fallback';
  }

  return {
    escapeHtml: escapeHtml,
    publicSongBlock: publicSongBlock,
    compose: compose,
    render: render,
    copy: copy
  };
});
