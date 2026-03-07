/* ============================================
   Post-Production Module
   Handles post-production queue display,
   asset scanning, and file key editing.
   ============================================ */

const PostProd = {
  _apiBase: 'https://saltallthethings.com/api',
  _queue: [],
  _showComplete: false,

  _headers() {
    return {
      'Content-Type': 'application/json',
      'Authorization': 'Bearer ' + Auth.getToken()
    };
  },

  async loadQueue() {
    try {
      const resp = await fetch(this._apiBase + '/postproduction', {
        headers: this._headers()
      });
      if (!resp.ok) throw new Error('API error: ' + resp.status);
      this._queue = await resp.json();
      this.renderTable();
    } catch (err) {
      Toast.error('Failed to load queue: ' + err.message);
    }
  },

  async scanAll() {
    const btn = document.getElementById('refreshBtn');
    btn.disabled = true;
    btn.innerHTML = '<svg viewBox="0 0 50 50" style="width:14px;height:14px;display:inline-block;vertical-align:middle;margin-right:6px;"><circle cx="25" cy="25" r="20" fill="none" stroke="currentColor" stroke-width="4" stroke-dasharray="80 40" stroke-linecap="round"><animateTransform attributeName="transform" type="rotate" values="0 25 25;360 25 25" dur="0.8s" repeatCount="indefinite"/></circle></svg>Scanning...';
    try {
      const resp = await fetch(this._apiBase + '/postproduction/scan', {
        method: 'POST',
        headers: this._headers()
      });
      if (resp.status === 400) {
        Toast.error('Drive not configured. Set folder IDs in Config first.');
        return;
      }
      if (!resp.ok) throw new Error('Scan failed: ' + resp.status);
      const result = await resp.json();
      await this.loadQueue();
      const n = result.scanned;
      Toast.success('Scanned ' + n + ' episode' + (n !== 1 ? 's' : '') + '.');
    } catch (err) {
      Toast.error('Scan failed: ' + err.message);
    } finally {
      btn.disabled = false;
      btn.textContent = 'Refresh Assets';
    }
  },

  async _updateKey(slotId, newKey) {
    const keyResp = await fetch(this._apiBase + '/postproduction/' + slotId + '/key', {
      method: 'PUT',
      headers: this._headers(),
      body: JSON.stringify({ productionFileKey: newKey })
    });
    if (!keyResp.ok) throw new Error('Failed to update key: ' + keyResp.status);
    const keyRow = await keyResp.json();

    // Attempt single-slot scan; fall back gracefully if not configured
    let updatedRow = keyRow;
    let toastMsg = 'Key updated.';
    try {
      const scanResp = await fetch(this._apiBase + '/postproduction/' + slotId + '/scan', {
        method: 'POST',
        headers: this._headers()
      });
      if (scanResp.ok) {
        updatedRow = await scanResp.json();
        toastMsg = 'Key updated and assets scanned.';
      } else if (scanResp.status === 400) {
        toastMsg = 'Key updated. Configure Drive folder IDs in Config to enable scanning.';
      }
    } catch (_) {
      // scan is best-effort
    }

    // Patch queue and re-render
    const idx = this._queue.findIndex(r => r.slotId === slotId);
    if (idx !== -1) this._queue[idx] = updatedRow;
    this.renderTable();
    Toast.success(toastMsg);
  },

  // --- Badge rendering ---

  _badgeHtml(assetObj, hasKey) {
    if (!hasKey) return '<span class="pp-badge pp-na">n/a</span>';
    if (!assetObj) return '<span class="pp-badge pp-missing">--</span>';
    if (assetObj.conflict) return '<span class="pp-badge pp-conflict">conflict</span>';
    if (assetObj.stale) return '<span class="pp-badge pp-stale">stale</span>';
    if (assetObj.present) return '<span class="pp-badge pp-ok">ok</span>';
    return '<span class="pp-badge pp-missing">--</span>';
  },

  // Transcript badge checks for stale (raw audio newer than transcript)
  _transcriptAsset(inv) {
    if (!inv || !inv.transcript_txt) return null;
    if (!inv.transcript_txt.present) return inv.transcript_txt;
    const rawMod = inv.raw_audio && inv.raw_audio.modified;
    const txtMod = inv.transcript_txt.modified;
    if (rawMod && txtMod && rawMod > txtMod) {
      return { present: true, stale: true };
    }
    return inv.transcript_txt;
  },

  _nextStepLabel(nextStep) {
    return {
      set_key: 'Set file key',
      upload_raw: 'Upload raw audio',
      transcribe: 'Run transcription',
      retranscribe: 'Re-transcribe',
      generate_art: 'Generate art',
      awaiting_editor: 'Awaiting editor',
      complete: 'Complete'
    }[nextStep] || nextStep;
  },

  // --- Table rendering ---

  renderTable() {
    const tbody = document.getElementById('queueBody');
    const rows = this._showComplete
      ? this._queue
      : this._queue.filter(r => r.nextStep !== 'complete');

    if (rows.length === 0) {
      const msg = this._queue.length === 0
        ? 'No recorded episodes in the queue yet.'
        : 'All episodes complete. Use "Show complete" to see them.';
      tbody.innerHTML = '<tr><td colspan="9" class="pp-empty">' + escHtml(msg) + '</td></tr>';
      return;
    }

    tbody.innerHTML = rows.map(row => {
      const inv = row.assetInventory;
      const hasKey = !!row.productionFileKey;
      const rawBadge = this._badgeHtml(inv ? inv.raw_audio : null, hasKey);
      const transcriptBadge = this._badgeHtml(this._transcriptAsset(inv), hasKey);
      const artBadge = this._badgeHtml(inv ? inv.album_art : null, hasKey);
      const finishedBadge = this._badgeHtml(inv ? inv.finished_audio : null, hasKey);

      const title = row.selectedTitle
        ? escHtml(row.selectedTitle)
        : '<em class="pp-no-title">No title assigned</em>';

      const keyVal = escHtml(row.productionFileKey || '');
      const keyDisplay = row.productionFileKey
        ? '<span class="pp-key-text">' + keyVal + '</span>'
        : '<span class="pp-key-placeholder">Click to set</span>';

      const nextClass = row.nextStep === 'complete' ? ' pp-complete' : (row.nextStep === 'set_key' ? ' pp-urgent' : '');

      return '<tr data-slot="' + escHtml(row.slotId) + '">'
        + '<td class="col-ep">' + escHtml(row.episodeNumber || '') + '</td>'
        + '<td class="col-title">' + title + '</td>'
        + '<td class="col-date">' + escHtml(row.recordDate || '') + '</td>'
        + '<td class="col-key">'
        +   '<div class="pp-key-display" onclick="PostProd.startKeyEdit(\'' + escHtml(row.slotId) + '\')" title="Click to edit">' + keyDisplay + '</div>'
        +   '<input class="pp-key-input" type="text" value="' + keyVal + '" placeholder="e.g. EP003_Title_2026-03-04" style="display:none" data-slot="' + escHtml(row.slotId) + '">'
        + '</td>'
        + '<td class="col-asset">' + rawBadge + '</td>'
        + '<td class="col-asset">' + transcriptBadge + '</td>'
        + '<td class="col-asset">' + artBadge + '</td>'
        + '<td class="col-asset">' + finishedBadge + '</td>'
        + '<td class="col-next' + nextClass + '">' + escHtml(this._nextStepLabel(row.nextStep)) + '</td>'
        + '</tr>';
    }).join('');

    // Attach key input event listeners
    tbody.querySelectorAll('.pp-key-input').forEach(function(input) {
      input.addEventListener('keydown', function(e) {
        if (e.key === 'Enter') { e.preventDefault(); input.blur(); }
        if (e.key === 'Escape') { PostProd.cancelKeyEdit(input.dataset.slot); }
      });
      input.addEventListener('blur', function() {
        PostProd.commitKeyEdit(input.dataset.slot, input);
      });
    });
  },

  // --- Inline key editing ---

  startKeyEdit(slotId) {
    var row = document.querySelector('tr[data-slot="' + slotId + '"]');
    if (!row) return;
    row.querySelector('.pp-key-display').style.display = 'none';
    var input = row.querySelector('.pp-key-input');
    input.style.display = 'block';
    input.focus();
    input.select();
  },

  cancelKeyEdit(slotId) {
    var row = document.querySelector('tr[data-slot="' + slotId + '"]');
    if (!row) return;
    row.querySelector('.pp-key-display').style.display = '';
    row.querySelector('.pp-key-input').style.display = 'none';
  },

  async commitKeyEdit(slotId, input) {
    var existingRow = this._queue.find(function(r) { return r.slotId === slotId; });
    var oldKey = existingRow ? (existingRow.productionFileKey || '') : '';
    var newKey = input.value.trim();

    if (newKey === oldKey) {
      this.cancelKeyEdit(slotId);
      return;
    }

    if (!newKey && oldKey) {
      if (!confirm('Clear the production file key for this episode? It will not be scannable until a key is set.')) {
        input.value = oldKey;
        this.cancelKeyEdit(slotId);
        return;
      }
    }

    input.disabled = true;
    try {
      await this._updateKey(slotId, newKey);
    } finally {
      input.disabled = false;
    }
  },

  toggleShowComplete() {
    this._showComplete = !this._showComplete;
    document.getElementById('showCompleteBtn').textContent = this._showComplete ? 'Hide complete' : 'Show complete';
    this.renderTable();
  }
};

function escHtml(str) {
  if (str == null) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
