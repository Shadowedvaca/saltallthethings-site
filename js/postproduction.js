/* ============================================
   Post-Production Module
   Handles post-production queue display,
   asset scanning, file key editing, and
   AI art direction generation.
   ============================================ */

const PostProd = {
  _apiBase: 'https://saltallthethings.com/api',
  _queue: [],
  _showComplete: false,
  _artDirection: {},
  _artDirectionLoading: {},
  _imageFileIds: {},
  _imageLoading: {},

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
      // Pre-populate image file IDs from DB so art panels show existing images
      this._queue.forEach(r => {
        if (r.imageFileId) this._imageFileIds[r.slotId] = r.imageFileId;
      });
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

  _autoKey(row) {
    if (!row.episodeNumber || !row.selectedTitle || !row.recordDate) return '';
    var slug = row.selectedTitle
      .replace(/[^a-zA-Z0-9\s]/g, '')
      .trim()
      .replace(/\s+/g, '-');
    return row.episodeNumber + '_' + slug + '_' + row.recordDate;
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

  // --- Art direction ---

  async generateArtDirection(slotId) {
    const row = this._queue.find(r => r.slotId === slotId);
    if (!row || !row.ideaId) return;

    this._artDirectionLoading[slotId] = true;
    this.renderTable();

    try {
      const resp = await fetch(this._apiBase + '/ai/generate-art-direction', {
        method: 'POST',
        headers: this._headers(),
        body: JSON.stringify({ ideaId: row.ideaId })
      });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        throw new Error(err.error || ('API error: ' + resp.status));
      }
      const result = await resp.json();
      this._artDirection[slotId] = result;
      Toast.success('Art direction generated.');
      if (result.referenceImageWarnings && result.referenceImageWarnings.length > 0) {
        Toast.error('Reference image warnings: ' + result.referenceImageWarnings.join('; '));
      }
      // Reload so Dir badge updates immediately
      await this.loadQueue();
    } catch (err) {
      Toast.error('Art direction failed: ' + err.message);
    } finally {
      this._artDirectionLoading[slotId] = false;
      this.renderTable();
    }
  },

  dismissArtDirection(slotId) {
    delete this._artDirection[slotId];
    this.renderTable();
  },

  async openArtDirection(slotId) {
    this._artDirectionLoading[slotId] = true;
    this.renderTable();
    try {
      const resp = await fetch(this._apiBase + '/postproduction/' + slotId + '/art-direction', {
        headers: this._headers()
      });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        throw new Error(err.detail || ('API error: ' + resp.status));
      }
      this._artDirection[slotId] = await resp.json();
    } catch (err) {
      Toast.error('Failed to load art direction: ' + err.message);
    } finally {
      this._artDirectionLoading[slotId] = false;
      this.renderTable();
    }
  },

  async generateEpisodeArt(slotId) {
    const row = this._queue.find(r => r.slotId === slotId);
    if (!row || !row.ideaId) return;

    const textarea = document.getElementById('pp-prompt-' + slotId);
    const rawPrompt = textarea ? textarea.value.trim() : '';
    if (!rawPrompt) { Toast.error('Image prompt is empty — fill in the prompt first.'); return; }
    const styleDesc = (Storage.getConfig().referenceStyleDescription || '').trim();
    const prompt = styleDesc ? styleDesc + '\n\n' + rawPrompt : rawPrompt;
    if (prompt.length > 4000) { Toast.error('Prompt is ' + prompt.length + ' chars — trim it under 4000 before generating.'); return; }

    this._imageLoading[slotId] = true;
    this.renderTable();

    try {
      const resp = await fetch(this._apiBase + '/ai/generate-episode-art', {
        method: 'POST',
        headers: this._headers(),
        body: JSON.stringify({ ideaId: row.ideaId, imagePrompt: prompt })
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        const msg = data.error || ('API error: ' + resp.status);
        if (msg.toLowerCase().includes('rejected')) {
          Toast.error('OpenAI rejected the prompt — try editing it');
        } else {
          Toast.error('Art generation failed: ' + msg);
        }
        return;
      }
      this._imageFileIds[slotId] = data.imageFileId;
      // Update queue row imageFileId so badge reflects new state after reload
      const idx = this._queue.findIndex(r => r.slotId === slotId);
      if (idx !== -1) this._queue[idx].imageFileId = data.imageFileId;
      Toast.success('Album art generated and uploaded to Drive.');
      // Reload queue to refresh asset inventory (Art badge → ok)
      await this.loadQueue();
    } catch (err) {
      Toast.error('Art generation failed: ' + err.message);
    } finally {
      this._imageLoading[slotId] = false;
      this.renderTable();
    }
  },

  _updatePromptCount(slotId) {
    const ta = document.getElementById('pp-prompt-' + slotId);
    const counter = document.getElementById('pp-prompt-count-' + slotId);
    if (!ta || !counter) return;
    const styleDesc = (Storage.getConfig().referenceStyleDescription || '').trim();
    const combined = styleDesc ? styleDesc + '\n\n' + ta.value : ta.value;
    const len = combined.length;
    counter.textContent = len + ' / 4000';
    counter.style.color = len > 4000 ? '#e05c5c' : 'var(--text-muted)';
  },

  copyPrompt(slotId) {
    const textarea = document.getElementById('pp-prompt-' + slotId);
    if (!textarea) return;
    const styleDesc = (Storage.getConfig().referenceStyleDescription || '').trim();
    const text = styleDesc ? styleDesc + '\n\n' + textarea.value : textarea.value;
    if (navigator.clipboard) {
      navigator.clipboard.writeText(text)
        .then(() => Toast.success('Prompt copied to clipboard.'))
        .catch(() => { textarea.select(); document.execCommand('copy'); Toast.success('Prompt copied.'); });
    } else {
      textarea.select();
      document.execCommand('copy');
      Toast.success('Prompt copied.');
    }
  },

  async rebuildPrompt(slotId) {
    const btn = document.getElementById('pp-rebuild-btn-' + slotId);
    if (btn) { btn.disabled = true; btn.textContent = 'Rebuilding...'; }

    const get = function(id) { const el = document.getElementById(id); return el ? el.value : ''; };
    const getLines = function(id) {
      const el = document.getElementById(id);
      if (!el) return [];
      return el.value.split('\n').map(function(l) { return l.trim(); }).filter(function(l) { return l; });
    };

    const existingArt = this._artDirection[slotId] || {};
    const body = {
      archetype: {
        id: (existingArt.archetype || {}).id || '',
        name: get('pp-archetype-name-' + slotId).trim(),
        reason: get('pp-archetype-reason-' + slotId).trim()
      },
      sceneSummary: get('pp-scene-' + slotId).trim(),
      environment: get('pp-env-' + slotId).trim(),
      bigElementalRole: get('pp-bige-' + slotId).trim(),
      babyGags: getLines('pp-gags-' + slotId),
      topics: getLines('pp-topics-' + slotId),
      tone: get('pp-tone-' + slotId).trim(),
      props: getLines('pp-props-' + slotId)
    };

    try {
      const resp = await fetch(this._apiBase + '/ai/rebuild-image-prompt', {
        method: 'POST',
        headers: this._headers(),
        body: JSON.stringify(body)
      });
      if (!resp.ok) {
        const err = await resp.json().catch(function() { return {}; });
        throw new Error(err.error || ('API error: ' + resp.status));
      }
      const result = await resp.json();
      const ta = document.getElementById('pp-prompt-' + slotId);
      if (ta) { ta.value = result.finalImagePrompt; this._updatePromptCount(slotId); }
      Toast.success('Image prompt rebuilt from current fields.');
    } catch (err) {
      Toast.error('Rebuild failed: ' + err.message);
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = 'Rebuild Prompt'; }
    }
  },

  async saveArtDirection(slotId) {
    const sid = slotId;
    const btn = document.getElementById('pp-save-btn-' + sid);
    if (btn) { btn.disabled = true; btn.textContent = 'Saving...'; }

    const get = function(id) {
      const el = document.getElementById(id);
      return el ? el.value : '';
    };
    const getLines = function(id) {
      const el = document.getElementById(id);
      if (!el) return [];
      return el.value.split('\n').map(function(l) { return l.trim(); }).filter(function(l) { return l; });
    };

    const existingArt = this._artDirection[slotId] || {};
    const archetypeId = (existingArt.archetype || {}).id || '';

    const body = {
      topics: getLines('pp-topics-' + sid),
      tone: get('pp-tone-' + sid).trim(),
      archetype: {
        id: archetypeId,
        name: get('pp-archetype-name-' + sid).trim(),
        reason: get('pp-archetype-reason-' + sid).trim()
      },
      environment: get('pp-env-' + sid).trim(),
      bigElementalRole: get('pp-bige-' + sid).trim(),
      babyGags: getLines('pp-gags-' + sid),
      props: getLines('pp-props-' + sid),
      sceneSummary: get('pp-scene-' + sid).trim(),
      finalImagePrompt: get('pp-prompt-' + sid).trim()
    };

    try {
      const resp = await fetch(this._apiBase + '/postproduction/' + slotId + '/art-direction', {
        method: 'PUT',
        headers: this._headers(),
        body: JSON.stringify(body)
      });
      if (!resp.ok) {
        const err = await resp.json().catch(function() { return {}; });
        throw new Error(err.detail || ('API error: ' + resp.status));
      }
      const saved = await resp.json();
      this._artDirection[slotId] = saved;
      this.renderTable();
      Toast.success('Art direction saved.');
    } catch (err) {
      Toast.error('Save failed: ' + err.message);
      if (btn) { btn.disabled = false; btn.textContent = 'Save Direction'; }
    }
  },

  _generateArtButtonHtml(slotId) {
    if (this._imageLoading[slotId]) {
      return '<span class="pp-art-gen-loading">'
        + '<svg viewBox="0 0 50 50" style="width:13px;height:13px;display:inline-block;vertical-align:middle;margin-right:5px;">'
        + '<circle cx="25" cy="25" r="20" fill="none" stroke="currentColor" stroke-width="5" stroke-dasharray="80 40" stroke-linecap="round">'
        + '<animateTransform attributeName="transform" type="rotate" values="0 25 25;360 25 25" dur="0.8s" repeatCount="indefinite"/>'
        + '</circle></svg>Generating...</span>';
    }
    const label = this._imageFileIds[slotId] ? 'Regenerate Art' : 'Generate Art';
    return '<button class="btn btn-primary btn-sm" onclick="PostProd.generateEpisodeArt(\'' + escHtml(slotId) + '\')">' + label + '</button>';
  },

  _artImagePreviewHtml(slotId) {
    const fileId = this._imageFileIds[slotId];
    if (!fileId) return '';
    const url = 'https://drive.google.com/thumbnail?id=' + encodeURIComponent(fileId) + '&sz=w400';
    return '<div class="pp-art-preview">'
      + '<span class="pp-art-label">Generated Album Art</span>'
      + '<img src="' + url + '" alt="Album art preview" class="pp-art-img" loading="lazy">'
      + '</div>';
  },

  _artDirectionRowHtml(slotId) {
    const art = this._artDirection[slotId];
    if (!art) return '';

    const sid = escHtml(slotId);
    const styleDesc = (Storage.getConfig().referenceStyleDescription || '').trim();
    const rawPrompt = art.finalImagePrompt || '';
    const combinedLen = (styleDesc ? styleDesc + '\n\n' + rawPrompt : rawPrompt).length;

    const stylePrefixBlock = styleDesc
      ? '<div><span class="pp-art-label">Style Prefix (from Config \u2014 read-only)</span>'
        + '<div class="pp-style-prefix">' + escHtml(styleDesc) + '</div></div>'
      : '';

    return '<tr class="pp-art-row">'
      + '<td colspan="13" class="pp-art-cell">'
      + '<div class="pp-art-panel">'

      // Archetype row — editable name + reason
      + '<div class="pp-art-meta">'
      + '<input id="pp-archetype-name-' + sid + '" class="pp-art-input" type="text"'
      + ' value="' + escHtml(art.archetype.name) + '" placeholder="Archetype name"'
      + ' style="width:200px;font-weight:700;color:var(--gold)">'
      + '<span style="color:var(--text-muted);margin:0 8px;flex-shrink:0">&mdash;</span>'
      + '<input id="pp-archetype-reason-' + sid + '" class="pp-art-input" type="text"'
      + ' value="' + escHtml(art.archetype.reason) + '" placeholder="Archetype reason" style="flex:1">'
      + '</div>'

      // 2-column grid: Scene, Baby Gags, Topics, Tone+Props
      + '<div class="pp-art-grid">'
      + '<div><span class="pp-art-label">Scene</span>'
      + '<textarea id="pp-scene-' + sid + '" class="pp-art-field-textarea">' + escHtml(art.sceneSummary || '') + '</textarea></div>'
      + '<div><span class="pp-art-label">Baby Gags (one per line)</span>'
      + '<textarea id="pp-gags-' + sid + '" class="pp-art-field-textarea">' + escHtml((art.babyGags || []).join('\n')) + '</textarea></div>'
      + '<div><span class="pp-art-label">Topics (one per line)</span>'
      + '<textarea id="pp-topics-' + sid + '" class="pp-art-field-textarea">' + escHtml((art.topics || []).join('\n')) + '</textarea></div>'
      + '<div>'
      + '<span class="pp-art-label">Tone</span>'
      + '<input id="pp-tone-' + sid + '" class="pp-art-input" type="text" value="' + escHtml(art.tone || '') + '" style="margin-bottom:10px;width:100%">'
      + '<span class="pp-art-label" style="margin-top:6px">Props (one per line)</span>'
      + '<textarea id="pp-props-' + sid + '" class="pp-art-field-textarea">' + escHtml((art.props || []).join('\n')) + '</textarea>'
      + '</div>'
      + '</div>'

      // Environment + Big Elemental Role
      + '<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px 24px;">'
      + '<div><span class="pp-art-label">Environment</span>'
      + '<input id="pp-env-' + sid + '" class="pp-art-input" type="text" value="' + escHtml(art.environment || '') + '" style="width:100%"></div>'
      + '<div><span class="pp-art-label">Big Elemental Role</span>'
      + '<input id="pp-bige-' + sid + '" class="pp-art-input" type="text" value="' + escHtml(art.bigElementalRole || '') + '" style="width:100%"></div>'
      + '</div>'

      // Style prefix (read-only) + Final image prompt
      + stylePrefixBlock
      + '<div class="pp-art-prompt-wrap">'
      + '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:4px;gap:8px;">'
      + '<span class="pp-art-label" style="margin-bottom:0">Final Image Prompt (editable)</span>'
      + '<div style="display:flex;align-items:center;gap:8px;flex-shrink:0">'
      + '<button id="pp-rebuild-btn-' + sid + '" class="btn btn-ghost btn-sm" onclick="PostProd.rebuildPrompt(\'' + sid + '\')" style="font-size:0.75rem">Rebuild Prompt</button>'
      + '<span id="pp-prompt-count-' + sid + '" style="font-size:0.72rem;color:var(--text-muted);">' + combinedLen + ' / 4000</span>'
      + '</div>'
      + '</div>'
      + '<textarea id="pp-prompt-' + sid + '" class="pp-art-textarea" oninput="PostProd._updatePromptCount(\'' + sid + '\')">' + escHtml(rawPrompt) + '</textarea>'
      + '<div class="pp-art-actions">'
      + '<button class="btn btn-primary btn-sm" id="pp-save-btn-' + sid + '" onclick="PostProd.saveArtDirection(\'' + sid + '\')">Save Direction</button>'
      + '<button class="btn btn-secondary btn-sm" onclick="PostProd.copyPrompt(\'' + sid + '\')">Copy Prompt</button>'
      + this._generateArtButtonHtml(slotId)
      + '<button class="btn btn-ghost btn-sm" onclick="PostProd.generateArtDirection(\'' + sid + '\')">Re-run AI</button>'
      + '<button class="btn btn-ghost btn-sm pp-art-dismiss" onclick="PostProd.dismissArtDirection(\'' + sid + '\')">&#x2715; Dismiss</button>'
      + '</div>'
      + '</div>'

      + this._artImagePreviewHtml(slotId)
      + '</div>'
      + '</td>'
      + '</tr>';
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
      tbody.innerHTML = '<tr><td colspan="13" class="pp-empty">' + escHtml(msg) + '</td></tr>';
      return;
    }

    tbody.innerHTML = rows.map(row => {
      const inv = row.assetInventory;
      const hasKey = !!row.productionFileKey;
      const rawBadge = this._badgeHtml(inv ? inv.raw_audio : null, hasKey);
      const trogBadge = this._badgeHtml(inv ? inv.raw_trog : null, hasKey);
      const rocketBadge = this._badgeHtml(inv ? inv.raw_rocket : null, hasKey);
      const transcriptBadge = this._badgeHtml(this._transcriptAsset(inv), hasKey);
      const artBadge = this._badgeHtml(inv ? inv.album_art : null, hasKey);
      const artDirBadge = this._badgeHtml(inv ? inv.art_direction : null, hasKey);
      const finishedBadge = this._badgeHtml(inv ? inv.finished_audio : null, hasKey);

      const title = row.selectedTitle
        ? escHtml(row.selectedTitle)
        : '<em class="pp-no-title">No title assigned</em>';

      const keyVal = escHtml(row.productionFileKey || '');
      const keyDisplay = row.productionFileKey
        ? '<span class="pp-key-text">' + keyVal + '</span>'
        : '<span class="pp-key-placeholder">Click to set</span>';

      const nextClass = row.nextStep === 'complete' ? ' pp-complete' : (row.nextStep === 'set_key' ? ' pp-urgent' : '');

      // Actions cell — show Open/Generate Art Direction based on state
      const hasTranscript = inv && inv.transcript_txt && inv.transcript_txt.present && inv.transcript_txt.drive_file_id;
      const canGenerateArt = hasKey && hasTranscript && row.ideaId;
      const hasSavedDir = inv && inv.art_direction && inv.art_direction.present && inv.art_direction.drive_file_id;
      let actionCell = '<td class="col-actions">';
      if (this._artDirectionLoading[row.slotId]) {
        actionCell += '<span class="pp-art-loading"><svg viewBox="0 0 50 50" style="width:12px;height:12px;display:inline-block;vertical-align:middle;margin-right:4px;"><circle cx="25" cy="25" r="20" fill="none" stroke="currentColor" stroke-width="5" stroke-dasharray="80 40" stroke-linecap="round"><animateTransform attributeName="transform" type="rotate" values="0 25 25;360 25 25" dur="0.8s" repeatCount="indefinite"/></circle></svg>Generating...</span>';
      } else if (this._artDirection[row.slotId]) {
        // Panel is open — no button needed (Dismiss is in the panel)
      } else if (hasSavedDir) {
        actionCell += '<button class="btn btn-ghost btn-sm pp-art-btn" onclick="PostProd.openArtDirection(\'' + escHtml(row.slotId) + '\')">Open Art Direction</button>';
      } else if (canGenerateArt) {
        actionCell += '<button class="btn btn-ghost btn-sm pp-art-btn" onclick="PostProd.generateArtDirection(\'' + escHtml(row.slotId) + '\')">Generate Art Direction</button>';
      }
      actionCell += '</td>';

      const rowHtml = '<tr data-slot="' + escHtml(row.slotId) + '">'
        + '<td class="col-ep">' + escHtml(row.episodeNumber || '') + '</td>'
        + '<td class="col-title">' + title + '</td>'
        + '<td class="col-date">' + escHtml(row.recordDate || '') + '</td>'
        + '<td class="col-key">'
        +   '<div class="pp-key-display" onclick="PostProd.startKeyEdit(\'' + escHtml(row.slotId) + '\')" title="Click to edit">' + keyDisplay + '</div>'
        +   '<input class="pp-key-input" type="text" value="' + keyVal + '" placeholder="e.g. EP003_Title_2026-03-04" style="display:none" data-slot="' + escHtml(row.slotId) + '">'
        + '</td>'
        + '<td class="col-asset">' + rawBadge + '</td>'
        + '<td class="col-asset">' + trogBadge + '</td>'
        + '<td class="col-asset">' + rocketBadge + '</td>'
        + '<td class="col-asset">' + transcriptBadge + '</td>'
        + '<td class="col-asset">' + artDirBadge + '</td>'
        + '<td class="col-asset">' + artBadge + '</td>'
        + '<td class="col-asset">' + finishedBadge + '</td>'
        + '<td class="col-next' + nextClass + '">' + escHtml(this._nextStepLabel(row.nextStep)) + '</td>'
        + actionCell
        + '</tr>';

      return rowHtml + this._artDirectionRowHtml(row.slotId);
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
    // Pre-fill with auto-generated key if not yet set
    if (!input.value) {
      var queueRow = this._queue.find(function(r) { return r.slotId === slotId; });
      if (queueRow) input.value = this._autoKey(queueRow);
    }
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
