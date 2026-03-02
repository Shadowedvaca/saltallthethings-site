/* ============================================
   AI Service Module (v2 — server-side proxy)

   All AI calls go through the FastAPI backend.
   Prompt construction lives in prompts.py.
   ============================================ */

const API_BASE = 'https://saltallthethings.com/api';

const AIService = {
  async processIdea(rawNotes) {
    const token = Auth.getToken();
    const response = await fetch(`${API_BASE}/ai/process-idea`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify({ rawNotes })
    });
    if (!response.ok) {
      const err = await response.json();
      throw new Error(err.error || `AI error (${response.status})`);
    }
    const data = await response.json();
    return this._parseAIResponse(data);
  },

  async generateJokes(themeHint) {
    const token = Auth.getToken();
    const response = await fetch(`${API_BASE}/ai/generate-jokes`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify({ themeHint: themeHint || '' })
    });
    if (!response.ok) {
      const err = await response.json();
      throw new Error(err.error || `AI error (${response.status})`);
    }
    const data = await response.json();
    return data.jokes;  // string[]
  },

  _parseAIResponse(data) {
    // Validate structure returned from the proxy
    if (!Array.isArray(data.titles) || !data.summary || !Array.isArray(data.outline)) {
      throw new Error('Response missing required fields (titles, summary, outline)');
    }
    return {
      titles: data.titles,
      summary: data.summary,
      outline: data.outline
    };
  }
};
