/* ============================================
   Storage Module (v3 — Hetzner API-backed)

   In-memory cache + FastAPI backend.
   All reads are synchronous from cache.
   Writes update the cache optimistically, then
   resolve only after the API acknowledges them.
   ============================================ */

const Storage = {
  _apiUrl: '/api',
  _cache: {},
  _serverState: null,
  _ready: false,
  _revision: null,
  _syncing: Promise.resolve(),
  _writeGeneration: 0,
  _pendingWrites: 0,
  _statusTimer: null,
  _beforeUnloadRegistered: false,
  _stateListeners: [],

  // Full-array writes remain supported for ideas, jokes, slots, and
  // assignments, but every mutation is serialized globally and guarded by
  // the exact revision returned by /api/export. A stale page is reloaded and
  // its queued writes are cancelled instead of overwriting newer server data.
  async init() {
    const token = this._getToken();
    if (!token) throw new Error('Not authenticated');
    this._registerBeforeUnload();
    try {
      await this._reloadLatest();
      this._ready = true;
      this._setStatus('saved', 'All changes saved');
    } catch (err) {
      this._setStatus('failed', 'Unable to load saved data', () => this.init());
      console.error('Storage.init failed:', err);
      throw err;
    }
  },

  _getToken() {
    return typeof Auth !== 'undefined' ? Auth.getToken() : null;
  },

  _applyState(state, reason) {
    if (!state) return;
    if (Object.prototype.hasOwnProperty.call(state, 'config')) this._cache.config = state.config || null;
    if (Object.prototype.hasOwnProperty.call(state, 'ideas')) this._cache.ideas = state.ideas || [];
    if (Object.prototype.hasOwnProperty.call(state, 'jokes')) this._cache.jokes = state.jokes || [];
    if (Object.prototype.hasOwnProperty.call(state, 'songs')) this._cache.songs = state.songs || [];
    if (Object.prototype.hasOwnProperty.call(state, 'guests')) this._cache.guests = state.guests || [];
    if (Object.prototype.hasOwnProperty.call(state, 'guestAssignments')) this._cache.guestAssignments = state.guestAssignments || [];
    if (Object.prototype.hasOwnProperty.call(state, 'showSlots')) this._cache.showSlots = state.showSlots || [];
    if (Object.prototype.hasOwnProperty.call(state, 'assignments')) this._cache.assignments = state.assignments || {};
    if (Number.isInteger(state.revision)) this._revision = state.revision;
    if (Number.isInteger(state.revision)) {
      this._serverState = {
        config: this._clone(this._cache.config),
        ideas: this._clone(this._cache.ideas),
        jokes: this._clone(this._cache.jokes),
        songs: this._clone(this._cache.songs),
        guests: this._clone(this._cache.guests),
        guestAssignments: this._clone(this._cache.guestAssignments),
        showSlots: this._clone(this._cache.showSlots),
        assignments: this._clone(this._cache.assignments),
        revision: this._revision
      };
    }
    this._notifyStateListeners(reason || 'canonical');
  },

  _restoreServerState(reason) {
    if (!this._serverState) return;
    var canonical = this._clone(this._serverState);
    this._cache.config = canonical.config;
    this._cache.ideas = canonical.ideas;
    this._cache.jokes = canonical.jokes;
    this._cache.songs = canonical.songs;
    this._cache.guests = canonical.guests;
    this._cache.guestAssignments = canonical.guestAssignments;
    this._cache.showSlots = canonical.showSlots;
    this._cache.assignments = canonical.assignments;
    this._revision = canonical.revision;
    this._notifyStateListeners(reason || 'rollback');
  },

  async _reloadLatest(reason) {
    const token = this._getToken();
    if (!token) throw new Error('Not authenticated');
    const resp = await fetch(this._apiUrl + '/export', {
      headers: { 'Authorization': 'Bearer ' + token }
    });
    if (resp.status === 401) throw new Error('Invalid credentials');
    if (!resp.ok) throw new Error('API error: ' + resp.status);
    const data = await resp.json();
    this._applyState(data, reason || 'reload');
    return data;
  },

  subscribe(listener) {
    if (typeof listener !== 'function') throw new TypeError('Storage listener must be a function');
    if (!this._stateListeners.includes(listener)) this._stateListeners.push(listener);
    return () => {
      this._stateListeners = this._stateListeners.filter(function(candidate) {
        return candidate !== listener;
      });
    };
  },

  _notifyStateListeners(reason) {
    var event = { reason: reason, revision: this._revision };
    this._stateListeners.slice().forEach(function(listener) {
      try {
        listener(event);
      } catch (error) {
        console.error('Storage state listener failed:', error);
      }
    });
  },

  get(key) {
    return this._cache[key] !== undefined ? this._cache[key] : null;
  },

  async set(key, value) {
    this._cache[key] = value;
    try {
      await this._enqueueMutation(
        () => this._request('/data/' + key, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(value)
        }),
        () => this.set(key, value)
      );
      return true;
    } catch (err) {
      console.error('API save failed for', key, err);
      if (typeof Toast !== 'undefined') Toast.error('Failed to save ' + key + ': ' + err.message);
      return false;
    }
  },

  _enqueueMutation(run, retry) {
    var generation = this._writeGeneration;
    this._pendingWrites += 1;
    this._setStatus('saving', 'Saving changes…');
    var prior = this._syncing || Promise.resolve();
    var operation = prior.catch(function() {}).then(async () => {
      if (generation !== this._writeGeneration) {
        var cancelled = new Error('A previous save failed; review the latest data before retrying.');
        cancelled.status = 409;
        cancelled.cancelled = true;
        throw cancelled;
      }
      return run();
    }).then((body) => {
      this._applyState(body.state || body, 'mutation');
      return body;
    }).catch(async (err) => {
      if (!err.cancelled) this._writeGeneration += 1;
      if (err.status === 409 && !err.cancelled) {
        try {
          await this._reloadLatest('conflict');
          this._setStatus('conflict', 'Newer server data loaded. Review your change and save again.');
        } catch (reloadError) {
          this._restoreServerState('conflict-rollback');
          this._setStatus('failed', 'Conflict detected; reload failed', () => this._reloadLatest());
        }
      } else if (!err.cancelled) {
        this._restoreServerState('failure-rollback');
        this._setStatus('failed', 'Save failed', retry);
      }
      throw err;
    }).finally(() => {
      this._pendingWrites = Math.max(0, this._pendingWrites - 1);
      if (this._pendingWrites === 0 && generation === this._writeGeneration) {
        this._setStatus('saved', 'All changes saved');
      }
    });
    this._syncing = operation;
    return operation;
  },

  async _request(path, options) {
    const token = this._getToken();
    if (!token) throw new Error('Not authenticated');
    var requestOptions = Object.assign({}, options || {});
    requestOptions.headers = Object.assign(
      { 'Authorization': 'Bearer ' + token },
      requestOptions.headers || {}
    );
    if (requestOptions.method && requestOptions.method !== 'GET') {
      if (!Number.isInteger(this._revision)) throw new Error('Data revision is unavailable; reload before saving.');
      requestOptions.headers['If-Match'] = String(this._revision);
    }
    var resp = await fetch(this._apiUrl + path, requestOptions);
    var body = await resp.json().catch(function() { return {}; });
    if (!resp.ok) {
      var detail = body.detail;
      var message = detail && typeof detail === 'object' ? detail.message : detail;
      var error = new Error(message || body.error || ('API error: ' + resp.status));
      error.status = resp.status;
      error.detail = detail;
      throw error;
    }
    return body;
  },

  _ensureStatusElement() {
    if (typeof document === 'undefined' || !document.body) return null;
    var element = document.getElementById('save-status');
    if (element) return element;
    element = document.createElement('div');
    element.id = 'save-status';
    element.className = 'save-status saved';
    element.setAttribute('role', 'status');
    element.setAttribute('aria-live', 'polite');
    document.body.appendChild(element);
    return element;
  },

  _setStatus(kind, message, retry) {
    var element = this._ensureStatusElement();
    if (!element) return;
    if (this._statusTimer) {
      clearTimeout(this._statusTimer);
      this._statusTimer = null;
    }
    element.className = 'save-status ' + kind;
    element.textContent = message;
    if (retry) {
      var button = document.createElement('button');
      button.type = 'button';
      button.textContent = 'Retry';
      button.addEventListener('click', () => {
        button.disabled = true;
        retry();
      });
      element.appendChild(button);
    }
    if (kind === 'saved') {
      this._statusTimer = setTimeout(function() {
        element.classList.add('quiet');
      }, 2500);
    }
  },

  _registerBeforeUnload() {
    if (this._beforeUnloadRegistered || typeof window === 'undefined') return;
    window.addEventListener('beforeunload', (event) => {
      if (this._pendingWrites <= 0) return;
      event.preventDefault();
      event.returnValue = '';
    });
    this._beforeUnloadRegistered = true;
  },

  _clone(value) {
    return value === undefined ? undefined : JSON.parse(JSON.stringify(value));
  },
  // ---- Config ----
  getConfig() {
    var stored = this.get('config');
    var defaults = {
      aiModel: 'claude',
      claudeApiKeyConfigured: false,
      claudeModelId: 'claude-sonnet-4-5-20250929',
      openaiApiKeyConfigured: false,
      openaiModelId: 'gpt-4o',
      titleCount: 3,
      jokeCount: 5,
      youtubeVideo1: '',
      youtubeVideo2: '',
      youtubeVideo3: '',
      showContext: this._defaultShowContext(),
      jokeContext: this._defaultJokeContext(),
      segments: this._defaultSegments()
    };

    // If no stored config, return defaults
    if (!stored) return defaults;

    // Merge stored config with defaults (stored values take precedence)
    return Object.assign({}, defaults, stored);
  },

  saveConfig(config) {
    return this.set('config', config);
  },

  _defaultSegments() {
    return [
      { id: 'opening', name: 'Opening Hook / Intro', description: 'Set the tone, tease the episode topics' },
      { id: 'listener', name: 'Listener Corner', description: 'Community questions, comments, shoutouts (future segment)' },
      { id: 'updates', name: 'What are Rocket and Trog up to?', description: 'Personal WoW updates, what they\'ve been playing' },
      { id: 'housing', name: 'Rocket\'s Housing Update', description: 'Rocket\'s ongoing housing/life update segment' },
      { id: 'main', name: 'Main Topic', description: 'The core discussion topic for the episode' },
      { id: 'salt', name: 'A Little Sprinkle of Salt for your week', description: 'Salty takes, hot takes, complaints, rants' },
      { id: 'closing', name: 'Wrap-Up / What\'s Next / Closing', description: 'Preview next episode, calls to action, sign off' }
    ];
  },

  _defaultJokeContext() {
    return 'You are a comedy writer for "Salt All The Things," a World of Warcraft podcast.\n\nThe show opens with a short, punchy salt-themed joke or one-liner. These are quick openers — not long bits. Think dad jokes, puns, and one-liners that play on the word "salt," saltiness (frustration/complaining), NaCl, seasoning, the Dead Sea, etc. They can also riff on WoW culture, gaming, or nerd life — as long as they tie back to salt somehow.\n\nTONE: Groan-worthy, fun, occasionally clever. The kind of joke that makes you smile even as you shake your head. Not crude or offensive — just cheesy, playful, salty humor.\n\nFORMAT: Each joke should be 1-2 sentences max. Setup + punchline or just a one-liner.\n\nWhen given a theme/topic hint, try to work that into some of the jokes while keeping others as general salt jokes for variety.';
  },

  _defaultShowContext() {
    return 'You are helping plan episodes for "Salt All The Things," a weekly World of Warcraft podcast.\n\nABOUT THE SHOW:\n- Two hosts: Rocket (primary host, content writer) and Trog (co-host, technical/backend)\n- Tagline: "Two friends, two decades of WoW, and zero filter — the good, the bad, and the salty."\n- Tone: Conversational, authentic, unfiltered. Two friends talking WoW — not a corporate production.\n- Format: ~60 minute weekly episodes\n- The show leans into honest opinions, humor, and the "salt" — frustrations, hot takes, and real talk about the game.\n\nAUDIENCE:\n- WoW players (current and returning), MMO enthusiasts, gaming community members who appreciate unfiltered discussion.\n\nSTYLE NOTES:\n- Keep conversation points natural — these are talking prompts, not scripts\n- Each conversation point should spark discussion between two friends, not be a lecture topic\n- Lean into the "salty" brand — don\'t shy away from controversial takes\n- Include moments for humor, banter, and tangents\n- Mix serious analysis with casual, fun discussion';
  },

  // ---- Jokes ----
  getJokes() {
    return this.get('jokes') || [];
  },

  saveJokes(jokes) {
    return this.set('jokes', jokes);
  },

  addJoke(joke) {
    var jokes = this._clone(this.getJokes());
    jokes.push(joke);
    return this.saveJokes(jokes);
  },

  updateJoke(jokeId, updates) {
    var jokes = this._clone(this.getJokes());
    var idx = jokes.findIndex(function(j) { return j.id === jokeId; });
    if (idx !== -1) {
      Object.assign(jokes[idx], updates);
      if (updates.status && updates.status !== 'used') {
        jokes[idx].usedByIdeaId = null;
      }
      return this.saveJokes(jokes);
    }
    return false;
  },

  deleteJoke(jokeId) {
    var jokes = this.getJokes().filter(function(j) { return j.id !== jokeId; });
    return this.saveJokes(jokes);
  },

  getUnusedJokes() {
    return this.getJokes().filter(function(j) { return j.status === 'unused'; });
  },

  getUsedJokes() {
    return this.getJokes().filter(function(j) { return j.status === 'used'; });
  },

  async assignJokeToIdea(jokeId, ideaId) {
    try {
      await this._enqueueMutation(
        () => this._request('/jokes/' + encodeURIComponent(jokeId) + '/assignment', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ ideaId: ideaId })
        }),
        () => this.assignJokeToIdea(jokeId, ideaId)
      );
      return true;
    } catch (err) {
      console.error('Joke assignment failed:', err);
      if (typeof Toast !== 'undefined') Toast.error('Failed to assign joke: ' + err.message);
      return false;
    }
  },

  async freeJoke(jokeId) {
    try {
      await this._enqueueMutation(
        () => this._request('/jokes/' + encodeURIComponent(jokeId) + '/assignment', { method: 'DELETE' }),
        () => this.freeJoke(jokeId)
      );
      return true;
    } catch (err) {
      console.error('Free joke failed:', err);
      if (typeof Toast !== 'undefined') Toast.error('Failed to free joke: ' + err.message);
      return false;
    }
  },

  getJokeForIdea(ideaId) {
    return this.getJokes().find(function(j) { return j.usedByIdeaId === ideaId; }) || null;
  },

  // ---- Songs ----
  getSongs() {
    return this.get('songs') || [];
  },

  saveSongs(songs) {
    return this.set('songs', songs);
  },

  addSong(song) {
    var songs = this._clone(this.getSongs());
    songs.push(song);
    return this.saveSongs(songs);
  },

  updateSong(songId, updates) {
    var songs = this._clone(this.getSongs());
    var index = songs.findIndex(function(song) { return song.id === songId; });
    if (index === -1) return false;
    Object.assign(songs[index], updates);
    return this.saveSongs(songs);
  },

  async assignSongToIdea(songId, ideaId) {
    try {
      await this._enqueueMutation(
        () => this._request('/songs/' + encodeURIComponent(songId) + '/assignment', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ ideaId: ideaId })
        }),
        () => this.assignSongToIdea(songId, ideaId)
      );
      return true;
    } catch (err) {
      console.error('Song assignment failed:', err);
      if (typeof Toast !== 'undefined') Toast.error('Failed to assign song: ' + err.message);
      return false;
    }
  },

  async freeSong(songId) {
    try {
      await this._enqueueMutation(
        () => this._request('/songs/' + encodeURIComponent(songId) + '/assignment', { method: 'DELETE' }),
        () => this.freeSong(songId)
      );
      return true;
    } catch (err) {
      console.error('Free song failed:', err);
      if (typeof Toast !== 'undefined') Toast.error('Failed to free song: ' + err.message);
      return false;
    }
  },

  async setSongStatus(songId, status) {
    try {
      await this._enqueueMutation(
        () => this._request('/songs/' + encodeURIComponent(songId) + '/status', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ status: status })
        }),
        () => this.setSongStatus(songId, status)
      );
      return true;
    } catch (err) {
      console.error('Song status update failed:', err);
      if (typeof Toast !== 'undefined') Toast.error('Failed to update song: ' + err.message);
      return false;
    }
  },

  async deleteSong(songId) {
    try {
      await this._enqueueMutation(
        () => this._request('/songs/' + encodeURIComponent(songId), { method: 'DELETE' }),
        () => this.deleteSong(songId)
      );
      return true;
    } catch (err) {
      console.error('Delete song failed:', err);
      if (typeof Toast !== 'undefined') Toast.error('Failed to delete song: ' + err.message);
      return false;
    }
  },

  getSongForIdea(ideaId) {
    return this.getSongs().find(function(song) { return song.assignedIdeaId === ideaId; }) || null;
  },

  // ---- Guests ----
  getGuests() {
    return this.get('guests') || [];
  },

  getGuestAssignments() {
    return this.get('guestAssignments') || [];
  },

  saveGuests(guests) {
    return this.set('guests', guests);
  },

  addGuest(guest) {
    var guests = this._clone(this.getGuests());
    guests.push(guest);
    return this.saveGuests(guests);
  },

  updateGuest(guestId, updates) {
    var found = false;
    var guests = this._clone(this.getGuests()).map(function(guest) {
      if (guest.id !== guestId) return guest;
      found = true;
      return Object.assign({}, guest, updates, { id: guest.id });
    });
    if (!found) return Promise.resolve(false);
    return this.saveGuests(guests);
  },

  async assignGuestToIdea(guestId, ideaId) {
    try {
      await this._enqueueMutation(
        () => this._request('/guests/' + encodeURIComponent(guestId) + '/assignments/' + encodeURIComponent(ideaId), { method: 'PUT' }),
        () => this.assignGuestToIdea(guestId, ideaId)
      );
      return true;
    } catch (err) {
      console.error('Guest assignment failed:', err);
      if (typeof Toast !== 'undefined') Toast.error('Failed to assign guest: ' + err.message);
      return false;
    }
  },

  async unassignGuestFromIdea(guestId, ideaId) {
    try {
      await this._enqueueMutation(
        () => this._request('/guests/' + encodeURIComponent(guestId) + '/assignments/' + encodeURIComponent(ideaId), { method: 'DELETE' }),
        () => this.unassignGuestFromIdea(guestId, ideaId)
      );
      return true;
    } catch (err) {
      console.error('Guest unassignment failed:', err);
      if (typeof Toast !== 'undefined') Toast.error('Failed to unassign guest: ' + err.message);
      return false;
    }
  },

  async setGuestStatus(guestId, status) {
    try {
      await this._enqueueMutation(
        () => this._request('/guests/' + encodeURIComponent(guestId) + '/status', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ status: status })
        }),
        () => this.setGuestStatus(guestId, status)
      );
      return true;
    } catch (err) {
      console.error('Guest status update failed:', err);
      if (typeof Toast !== 'undefined') Toast.error('Failed to update guest: ' + err.message);
      return false;
    }
  },

  async deleteGuest(guestId) {
    try {
      await this._enqueueMutation(
        () => this._request('/guests/' + encodeURIComponent(guestId), { method: 'DELETE' }),
        () => this.deleteGuest(guestId)
      );
      return true;
    } catch (err) {
      console.error('Delete guest failed:', err);
      if (typeof Toast !== 'undefined') Toast.error('Failed to delete guest: ' + err.message);
      return false;
    }
  },

  // ---- Show Ideas ----
  getIdeas() {
    return this.get('ideas') || [];
  },

  saveIdeas(ideas) {
    return this.set('ideas', ideas);
  },

  addIdea(idea) {
    var ideas = this._clone(this.getIdeas());
    ideas.push(idea);
    return this.saveIdeas(ideas);
  },

  updateIdea(ideaId, updates) {
    var ideas = this._clone(this.getIdeas());
    var idx = ideas.findIndex(function(i) { return i.id === ideaId; });
    if (idx !== -1) {
      Object.assign(ideas[idx], updates);
      return this.saveIdeas(ideas);
    }
    return false;
  },

  async deleteIdea(ideaId) {
    try {
      await this._enqueueMutation(
        () => this._request('/ideas/' + encodeURIComponent(ideaId), { method: 'DELETE' }),
        () => this.deleteIdea(ideaId)
      );
      return true;
    } catch (err) {
      console.error('Delete idea failed:', err);
      if (typeof Toast !== 'undefined') Toast.error('Failed to delete idea: ' + err.message);
      return false;
    }
  },

  // ---- Show Slots ----
  getShowSlots() {
    return this.get('showSlots') || [];
  },

  saveShowSlots(slots) {
    return this.set('showSlots', slots);
  },

  async setEpisodeNumberOverride(slotId, episodeNumber) {
    try {
      await this._enqueueMutation(
        () => this._request('/schedule/' + encodeURIComponent(slotId) + '/episode-number', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ episodeNumber: episodeNumber })
        }),
        () => this.setEpisodeNumberOverride(slotId, episodeNumber)
      );
      return true;
    } catch (err) {
      console.error('Episode number override failed:', err);
      if (typeof Toast !== 'undefined') Toast.error('Failed to save episode number: ' + err.message);
      return false;
    }
  },

  async clearEpisodeNumberOverride(slotId) {
    try {
      await this._enqueueMutation(
        () => this._request('/schedule/' + encodeURIComponent(slotId) + '/episode-number', { method: 'DELETE' }),
        () => this.clearEpisodeNumberOverride(slotId)
      );
      return true;
    } catch (err) {
      console.error('Episode number reset failed:', err);
      if (typeof Toast !== 'undefined') Toast.error('Failed to reset episode number: ' + err.message);
      return false;
    }
  },

  // ---- Assignments ----
  getAssignments() {
    return this.get('assignments') || {};
  },

  saveAssignments(assignments) {
    return this.set('assignments', assignments);
  },

  async assignIdeaToSlot(ideaId, slotId) {
    try {
      await this._enqueueMutation(
        () => this._request('/schedule/' + encodeURIComponent(slotId) + '/assignment', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ ideaId: ideaId })
        }),
        () => this.assignIdeaToSlot(ideaId, slotId)
      );
      return true;
    } catch (err) {
      console.error('Schedule assignment failed:', err);
      if (typeof Toast !== 'undefined') Toast.error('Failed to schedule idea: ' + err.message);
      return false;
    }
  },

  async unassignSlot(slotId) {
    if (!this.getAssignments()[slotId]) return true;
    try {
      await this._enqueueMutation(
        () => this._request('/schedule/' + encodeURIComponent(slotId) + '/assignment', { method: 'DELETE' }),
        () => this.unassignSlot(slotId)
      );
      return true;
    } catch (err) {
      console.error('Schedule unassignment failed:', err);
      if (typeof Toast !== 'undefined') Toast.error('Failed to unschedule idea: ' + err.message);
      return false;
    }
  },

  getIdeaForSlot(slotId) {
    return this.getAssignments()[slotId] || null;
  },

  getSlotForIdea(ideaId) {
    var assignments = this.getAssignments();
    for (var slotId in assignments) {
      if (assignments[slotId] === ideaId) return slotId;
    }
    return null;
  },

  // ---- Utilities ----
  generateId() {
    return Date.now().toString(36) + Math.random().toString(36).substr(2, 9);
  },

  exportAll() {
    return {
      config: this.getConfig(),
      ideas: this.getIdeas(),
      jokes: this.getJokes(),
      songs: this.getSongs(),
      guests: this.getGuests(),
      guestAssignments: this.getGuestAssignments(),
      showSlots: this.getShowSlots(),
      assignments: this.getAssignments(),
      exportDate: new Date().toISOString()
    };
  },

  async importAll(data) {
    var payload = {};
    ['config', 'ideas', 'jokes', 'songs', 'guests', 'guestAssignments', 'showSlots', 'assignments'].forEach(function(key) {
      if (Object.prototype.hasOwnProperty.call(data, key)) payload[key] = data[key];
    });
    try {
      await this._enqueueMutation(
        () => this._request('/import', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        }),
        () => this.importAll(payload)
      );
      return true;
    } catch (err) {
      console.error('Import failed:', err);
      if (typeof Toast !== 'undefined') Toast.error('Failed to import data: ' + err.message);
      return false;
    }
  }
};
