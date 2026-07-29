/* ============================================
   Storage Module (v3 — Hetzner API-backed)

   In-memory cache + FastAPI backend.
   All reads are synchronous from cache.
   Writes update the cache optimistically, then
   resolve only after the API acknowledges them.
   ============================================ */

const Storage = {
  _apiUrl: '/api',
  _cache: {},               // in-memory data store
  _ready: false,
  _syncing: {},             // serialize in-flight saves per key
  _writeVersion: {},

  // ---- Initialization ----
  async init() {
    const token = this._getToken();
    if (!token) throw new Error('Not authenticated');

    try {
      const resp = await fetch(this._apiUrl + '/export', {
        headers: { 'Authorization': 'Bearer ' + token }
      });
      if (resp.status === 401) throw new Error('Invalid credentials');
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

  _getToken() {
    return typeof Auth !== 'undefined' ? Auth.getToken() : null;
  },

  // ---- Core get/set (synchronous from cache) ----
  get(key) {
    return this._cache[key] !== undefined ? this._cache[key] : null;
  },

  async set(key, value) {
    var previous = this._clone(this._cache[key]);
    var version = (this._writeVersion[key] || 0) + 1;
    this._writeVersion[key] = version;
    this._cache[key] = value;
    try {
      var canonical = await this._pushToApi(key, value);
      if (this._writeVersion[key] === version && canonical !== undefined) {
        this._cache[key] = canonical;
      }
      return true;
    } catch (err) {
      if (this._writeVersion[key] === version) this._cache[key] = previous;
      console.error('API save failed for', key, err);
      if (typeof Toast !== 'undefined') {
        Toast.error('Failed to save ' + key + ': ' + err.message);
      }
      return false;
    }
  },

  _pushToApi(key, value) {
    const token = this._getToken();
    if (!token) return Promise.reject(new Error('Not authenticated'));

    var prior = this._syncing[key] || Promise.resolve();
    var operation = prior.catch(function() {}).then(async () => {
      var resp = await fetch(this._apiUrl + '/data/' + key, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token },
        body: JSON.stringify(value)
      });
      var body = await resp.json().catch(function() { return {}; });
      if (!resp.ok) {
        throw new Error(body.detail || body.error || ('API error: ' + resp.status));
      }
      return body.data;
    });
    this._syncing[key] = operation;
    operation.then(() => {
      if (this._syncing[key] === operation) delete this._syncing[key];
    }, () => {
      if (this._syncing[key] === operation) delete this._syncing[key];
    });
    return operation;
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
    var jokes = this._clone(this.getJokes());
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
    var assignments = this._clone(this.getAssignments());
    for (var sid in assignments) {
      if (assignments[sid] === ideaId) delete assignments[sid];
    }
    assignments[slotId] = ideaId;
    this.saveAssignments(assignments);
    this.updateIdea(ideaId, { status: 'scheduled' });
  },

  unassignSlot(slotId) {
    var assignments = this._clone(this.getAssignments());
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

  async importAll(data) {
    var writes = [];
    if (data.config) writes.push(this.saveConfig(data.config));
    if (data.ideas) writes.push(this.saveIdeas(data.ideas));
    if (data.jokes) writes.push(this.saveJokes(data.jokes));
    if (data.showSlots) writes.push(this.saveShowSlots(data.showSlots));
    if (data.assignments) writes.push(this.saveAssignments(data.assignments));
    var results = await Promise.all(writes);
    return results.every(function(result) { return result; });
  }
};
