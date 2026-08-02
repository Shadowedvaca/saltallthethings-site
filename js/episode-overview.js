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

  function compactLine(value) {
    return String(value == null ? '' : value).replace(/\s+/g, ' ').trim();
  }

  function publicTop3Block(top3) {
    if (!top3 || !Array.isArray(top3.contributors)) return '';
    var listName = compactLine(top3.listName);
    if (!listName) return '';
    var contributors = top3.contributors.map(function(item) {
      var displayName = compactLine(item && item.displayName);
      var picks = item && Array.isArray(item.picks)
        ? item.picks.map(compactLine)
        : [];
      if (!displayName || picks.length !== 3 || picks.some(function(pick) { return !pick; })) return null;
      return { displayName: displayName, picks: picks };
    }).filter(Boolean);
    if (!contributors.length) return '';
    var lines = ['Top 3: ' + listName];
    contributors.forEach(function(contributor) {
      lines.push(
        '',
        contributor.displayName,
        '1. ' + contributor.picks[0],
        '2. ' + contributor.picks[1],
        '3. ' + contributor.picks[2]
      );
    });
    return lines.join('\n');
  }

  function compose(summary, song, top3) {
    var publicSummary = summary == null ? '' : String(summary);
    var blocks = [publicSummary, publicSongBlock(song), publicTop3Block(top3)].filter(function(block) { return block; });
    return blocks.join('\n\n');
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
    publicTop3Block: publicTop3Block,
    compose: compose,
    render: render,
    copy: copy
  };
});
