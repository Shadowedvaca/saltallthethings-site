/* ============================================
   Storage Module
   localStorage wrapper for all persistent data
   ============================================ */

const Storage = {
  _prefix: 'satt_',

  get(key) {
    try {
      const raw = localStorage.getItem(this._prefix + key);
      return raw ? JSON.parse(raw) : null;
    } catch (e) {
      console.error('Storage.get error:', key, e);
      return null;
    }
  },

  set(key, value) {
    try {
      localStorage.setItem(this._prefix + key, JSON.stringify(value));
      return true;
    } catch (e) {
      console.error('Storage.set error:', key, e);
      return false;
    }
  },

  remove(key) {
    localStorage.removeItem(this._prefix + key);
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
      showContext: this._defaultShowContext(),
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

  _defaultShowContext() {
    return `You are helping plan episodes for "Salt All The Things," a weekly World of Warcraft podcast.

ABOUT THE SHOW:
- Two hosts: Rocket (primary host, content writer) and Trog (co-host, technical/backend)
- Tagline: "Two friends, two decades of WoW, and zero filter — the good, the bad, and the salty."
- Tone: Conversational, authentic, unfiltered. Two friends talking WoW — not a corporate production.
- Format: ~60 minute weekly episodes
- The show leans into honest opinions, humor, and the "salt" — frustrations, hot takes, and real talk about the game.

AUDIENCE:
- WoW players (current and returning), MMO enthusiasts, gaming community members who appreciate unfiltered discussion.

STYLE NOTES:
- Keep conversation points natural — these are talking prompts, not scripts
- Each conversation point should spark discussion between two friends, not be a lecture topic
- Lean into the "salty" brand — don't shy away from controversial takes
- Include moments for humor, banter, and tangents
- Mix serious analysis with casual, fun discussion`;
  },

  // ---- Show Ideas ----
  getIdeas() {
    return this.get('ideas') || [];
  },

  saveIdeas(ideas) {
    return this.set('ideas', ideas);
  },

  addIdea(idea) {
    const ideas = this.getIdeas();
    ideas.push(idea);
    return this.saveIdeas(ideas);
  },

  updateIdea(ideaId, updates) {
    const ideas = this.getIdeas();
    const idx = ideas.findIndex(i => i.id === ideaId);
    if (idx !== -1) {
      ideas[idx] = { ...ideas[idx], ...updates };
      return this.saveIdeas(ideas);
    }
    return false;
  },

  deleteIdea(ideaId) {
    const ideas = this.getIdeas().filter(i => i.id !== ideaId);
    return this.saveIdeas(ideas);
  },

  // ---- Show Slots ----
  getShowSlots() {
    return this.get('showSlots') || [];
  },

  saveShowSlots(slots) {
    return this.set('showSlots', slots);
  },

  // ---- Assignments (ideaId -> slotId mapping) ----
  getAssignments() {
    return this.get('assignments') || {};
  },

  saveAssignments(assignments) {
    return this.set('assignments', assignments);
  },

  assignIdeaToSlot(ideaId, slotId) {
    const assignments = this.getAssignments();
    // Remove any existing assignment for this idea
    for (const [sid, iid] of Object.entries(assignments)) {
      if (iid === ideaId) delete assignments[sid];
    }
    // Remove any existing assignment for this slot
    if (assignments[slotId]) {
      // Unassign the old idea
    }
    assignments[slotId] = ideaId;
    this.saveAssignments(assignments);

    // Update idea status
    this.updateIdea(ideaId, { status: 'scheduled' });
  },

  unassignSlot(slotId) {
    const assignments = this.getAssignments();
    const ideaId = assignments[slotId];
    if (ideaId) {
      delete assignments[slotId];
      this.saveAssignments(assignments);
      // Revert idea status to processed
      this.updateIdea(ideaId, { status: 'processed' });
    }
  },

  getIdeaForSlot(slotId) {
    const assignments = this.getAssignments();
    return assignments[slotId] || null;
  },

  getSlotForIdea(ideaId) {
    const assignments = this.getAssignments();
    for (const [slotId, iid] of Object.entries(assignments)) {
      if (iid === ideaId) return slotId;
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
      showSlots: this.getShowSlots(),
      assignments: this.getAssignments(),
      exportDate: new Date().toISOString()
    };
  },

  importAll(data) {
    if (data.config) this.saveConfig(data.config);
    if (data.ideas) this.saveIdeas(data.ideas);
    if (data.showSlots) this.saveShowSlots(data.showSlots);
    if (data.assignments) this.saveAssignments(data.assignments);
  }
};
