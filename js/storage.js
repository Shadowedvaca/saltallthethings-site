/* ============================================
   Storage Module (v2 — API-backed)
   
   In-memory cache + Cloudflare Worker API.
   All reads are synchronous from cache.
   All writes update cache immediately, then
   push to API in the background.
   ============================================ */

const Storage = {
  _apiUrl: '__API_URL__',   // replaced at deploy time, or set manually
  _cache: {},               // in-memory data store
  _ready: false,
  _syncing: {},             // track in-flight saves per key

  // ---- Initialization ----
  async init() {
    const password = this._getPassword();
    if (!password) throw new Error('Not authenticated');

    // If API URL not configured, fall back to localStorage
    if (this._apiUrl === '__' + 'API_URL' + '__' || !this._apiUrl) {
      console.warn('Storage: No API URL configured, using localStorage fallback.');
      this._useLocalFallback = true;
      this._loadFromLocalStorage();
      this._ready = true;
      return;
    }

    try {
      const resp = await fetch(this._apiUrl + '/export', {
        headers: { 'X-Auth': password }
      });
      if (resp.status === 401) throw new Error('Invalid password');
      if (!resp.ok) throw new Error('API error: ' + resp.status);
      const data = await resp.json();

      // Populate cache
      this._cache.config = data.config || null;
      this._cache.ideas = data.ideas || [];
      this._cache.jokes = data.jokes || [];
      this._cache.showSlots = data.showSlots || [];
      this._cache.assignments = data.assignments || {};
      this._ready = true;

    } catch (err) {
      console.error('Storage.init failed:', err);
      throw err;
    }
  },

  _getPassword() {
    try {
      const raw = sessionStorage.getItem('satt_auth_token');
      if (!raw) return null;
      const session = JSON.parse(raw);
      return session.password || null;
    } catch { return null; }
  },

  // ---- Core get/set (synchronous from cache) ----
  get(key) {
    if (this._useLocalFallback) {
      try {
        const raw = localStorage.getItem('satt_' + key);
        return raw ? JSON.parse(raw) : null;
      } catch { return null; }
    }
    return this._cache[key] !== undefined ? this._cache[key] : null;
  },

  set(key, value) {
    if (this._useLocalFallback) {
      try { localStorage.setItem('satt_' + key, JSON.stringify(value)); } catch(e) { console.error(e); }
      return true;
    }
    this._cache[key] = value;
    this._pushToApi(key, value);
    return true;
  },

  _pushToApi(key, value) {
    const password = this._getPassword();
    if (!password || !this._apiUrl) return;

    // Debounce: if already saving this key, mark as dirty
    if (this._syncing[key]) {
      this._syncing[key].dirty = true;
      this._syncing[key].value = value;
      return;
    }

    this._syncing[key] = { dirty: false, value: value };

    fetch(this._apiUrl + '/data/' + key, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', 'X-Auth': password },
      body: JSON.stringify(value)
    })
    .then(resp => {
      if (!resp.ok) console.error('API save failed for', key, resp.status);
    })
    .catch(err => console.error('API save error for', key, err))
    .finally(() => {
      const pending = this._syncing[key];
      delete this._syncing[key];
      // If more writes came in while we were saving, save again
      if (pending && pending.dirty) {
        this._pushToApi(key, pending.value);
      }
    });
  },

  _loadFromLocalStorage() {
    ['config', 'ideas', 'jokes', 'showSlots', 'assignments'].forEach(key => {
      try {
        const raw = localStorage.getItem('satt_' + key);
        this._cache[key] = raw ? JSON.parse(raw) : null;
      } catch { this._cache[key] = null; }
    });
  },

  // ---- Config ----
  getConfig() {
    return this.get('config') || {
      aiModel: 'claude',
      claudeApiKey: '',
      claudeModelId: 'claude-sonnet-4-5-20250929',
      openaiApiKey: '',
      openaiModelId: 'gpt-4o',
      titleCount: 3,
      jokeCount: 5,
      showContext: this._defaultShowContext(),
      jokeContext: this._defaultJokeContext(),
      segments: this._defaultSegments()
    };
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
    var jokes = this.getJokes();
    jokes.push(joke);
    return this.saveJokes(jokes);
  },

  updateJoke(jokeId, updates) {
    var jokes = this.getJokes();
    var idx = jokes.findIndex(function(j) { return j.id === jokeId; });
    if (idx !== -1) {
      Object.assign(jokes[idx], updates);
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

  markJokeUsed(jokeId, ideaId) {
    return this.updateJoke(jokeId, { status: 'used', usedByIdeaId: ideaId });
  },

  markJokeUnused(jokeId) {
    return this.updateJoke(jokeId, { status: 'unused', usedByIdeaId: null });
  },

  freeJokesForIdea(ideaId) {
    var jokes = this.getJokes();
    jokes.forEach(function(j) {
      if (j.usedByIdeaId === ideaId) {
        j.status = 'unused';
        j.usedByIdeaId = null;
      }
    });
    return this.saveJokes(jokes);
  },

  getJokeForIdea(ideaId) {
    return this.getJokes().find(function(j) { return j.usedByIdeaId === ideaId; }) || null;
  },

  // ---- Show Ideas ----
  getIdeas() {
    return this.get('ideas') || [];
  },

  saveIdeas(ideas) {
    return this.set('ideas', ideas);
  },

  addIdea(idea) {
    var ideas = this.getIdeas();
    ideas.push(idea);
    return this.saveIdeas(ideas);
  },

  updateIdea(ideaId, updates) {
    var ideas = this.getIdeas();
    var idx = ideas.findIndex(function(i) { return i.id === ideaId; });
    if (idx !== -1) {
      Object.assign(ideas[idx], updates);
      return this.saveIdeas(ideas);
    }
    return false;
  },

  deleteIdea(ideaId) {
    var ideas = this.getIdeas().filter(function(i) { return i.id !== ideaId; });
    return this.saveIdeas(ideas);
  },

  // ---- Show Slots ----
  getShowSlots() {
    return this.get('showSlots') || [];
  },

  saveShowSlots(slots) {
    return this.set('showSlots', slots);
  },

  // ---- Assignments ----
  getAssignments() {
    return this.get('assignments') || {};
  },

  saveAssignments(assignments) {
    return this.set('assignments', assignments);
  },

  assignIdeaToSlot(ideaId, slotId) {
    var assignments = this.getAssignments();
    for (var sid in assignments) {
      if (assignments[sid] === ideaId) delete assignments[sid];
    }
    assignments[slotId] = ideaId;
    this.saveAssignments(assignments);
    this.updateIdea(ideaId, { status: 'scheduled' });
  },

  unassignSlot(slotId) {
    var assignments = this.getAssignments();
    var ideaId = assignments[slotId];
    if (ideaId) {
      delete assignments[slotId];
      this.saveAssignments(assignments);
      this.updateIdea(ideaId, { status: 'processed' });
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
      showSlots: this.getShowSlots(),
      assignments: this.getAssignments(),
      exportDate: new Date().toISOString()
    };
  },

  importAll(data) {
    if (data.config) this.saveConfig(data.config);
    if (data.ideas) this.saveIdeas(data.ideas);
    if (data.jokes) this.saveJokes(data.jokes);
    if (data.showSlots) this.saveShowSlots(data.showSlots);
    if (data.assignments) this.saveAssignments(data.assignments);
  },

  // Migrate localStorage data to API (one-time)
  async migrateFromLocalStorage() {
    var data = {};
    ['config', 'ideas', 'jokes', 'showSlots', 'assignments'].forEach(function(key) {
      try {
        var raw = localStorage.getItem('satt_' + key);
        if (raw) data[key] = JSON.parse(raw);
      } catch(e) {}
    });

    if (Object.keys(data).length === 0) return false;

    var password = this._getPassword();
    var resp = await fetch(this._apiUrl + '/import', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', 'X-Auth': password },
      body: JSON.stringify(data)
    });
    if (!resp.ok) throw new Error('Migration failed: ' + resp.status);

    // Reload cache from API
    await this.init();
    return true;
  }
};
