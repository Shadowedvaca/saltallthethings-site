/* ============================================
   AI Service Module
   Handles API calls to Claude and ChatGPT
   ============================================ */

const AIService = {
  async processIdea(rawNotes) {
    const config = Storage.getConfig();

    if (!config.aiModel) {
      throw new Error('No AI model configured. Please set up your AI provider in Config.');
    }

    const systemPrompt = this._buildSystemPrompt(config);
    const userPrompt = this._buildUserPrompt(rawNotes, config);

    if (config.aiModel === 'claude') {
      return this._callClaude(systemPrompt, userPrompt, config);
    } else if (config.aiModel === 'openai') {
      return this._callOpenAI(systemPrompt, userPrompt, config);
    } else {
      throw new Error(`Unknown AI model: ${config.aiModel}`);
    }
  },

  _buildSystemPrompt(config) {
    const segmentList = config.segments
      .map((s, i) => `${i + 1}. ${s.name}${s.description ? ' — ' + s.description : ''}`)
      .join('\n');

    return `${config.showContext}

SHOW SEGMENTS (in order):
${segmentList}

YOUR TASK:
When given raw show notes/ideas from the host, you must return a JSON response with EXACTLY this structure (no markdown, no backticks, just pure JSON):

{
  "titles": ["Title Option 1", "Title Option 2", "Title Option 3"],
  "summary": "A 2-3 sentence clean summary of what this episode is about.",
  "outline": [
    {
      "segmentId": "opening",
      "segmentName": "Opening Hook / Intro",
      "talkingPoints": [
        "First conversation prompt or topic to discuss",
        "Second conversation prompt"
      ]
    }
  ]
}

RULES:
- Generate exactly ${config.titleCount} title options. Titles should be catchy, on-brand (salty, fun, WoW-themed), and hint at the main topic.
- The summary should be clean and compelling — good enough for a podcast description.
- The outline must include ALL segments listed above, in order.
- Each segment should have 2-5 talking points that are natural conversation starters, not lecture bullets.
- Talking points should be phrased as discussion prompts between two friends.
- Return ONLY valid JSON. No explanation, no markdown fences, no preamble.`;
  },

  _buildUserPrompt(rawNotes, config) {
    return `Here are Rocket's raw notes for an upcoming episode. Process these into the structured format:\n\n---\n${rawNotes}\n---`;
  },

  async _callClaude(systemPrompt, userPrompt, config) {
    if (!config.claudeApiKey) {
      throw new Error('Claude API key not configured. Add it in Config.');
    }

    const response = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': config.claudeApiKey,
        'anthropic-version': '2023-06-01',
        'anthropic-dangerous-direct-browser-access': 'true'
      },
      body: JSON.stringify({
        model: config.claudeModelId || 'claude-sonnet-4-5-20250929',
        max_tokens: 4096,
        system: systemPrompt,
        messages: [
          { role: 'user', content: userPrompt }
        ]
      })
    });

    if (!response.ok) {
      const errBody = await response.text();
      throw new Error(`Claude API error (${response.status}): ${errBody}`);
    }

    const data = await response.json();
    const text = data.content
      .filter(block => block.type === 'text')
      .map(block => block.text)
      .join('');

    return this._parseAIResponse(text);
  },

  async _callOpenAI(systemPrompt, userPrompt, config) {
    if (!config.openaiApiKey) {
      throw new Error('OpenAI API key not configured. Add it in Config.');
    }

    const response = await fetch('https://api.openai.com/v1/chat/completions', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${config.openaiApiKey}`
      },
      body: JSON.stringify({
        model: config.openaiModelId || 'gpt-4o',
        max_tokens: 4096,
        messages: [
          { role: 'system', content: systemPrompt },
          { role: 'user', content: userPrompt }
        ],
        temperature: 0.7
      })
    });

    if (!response.ok) {
      const errBody = await response.text();
      throw new Error(`OpenAI API error (${response.status}): ${errBody}`);
    }

    const data = await response.json();
    const text = data.choices[0]?.message?.content || '';

    return this._parseAIResponse(text);
  },

  _parseAIResponse(text) {
    // Strip markdown fences if present
    let cleaned = text.trim();
    if (cleaned.startsWith('```json')) {
      cleaned = cleaned.slice(7);
    } else if (cleaned.startsWith('```')) {
      cleaned = cleaned.slice(3);
    }
    if (cleaned.endsWith('```')) {
      cleaned = cleaned.slice(0, -3);
    }
    cleaned = cleaned.trim();

    try {
      const parsed = JSON.parse(cleaned);

      // Validate structure
      if (!Array.isArray(parsed.titles) || !parsed.summary || !Array.isArray(parsed.outline)) {
        throw new Error('Response missing required fields (titles, summary, outline)');
      }

      return {
        titles: parsed.titles,
        summary: parsed.summary,
        outline: parsed.outline
      };
    } catch (e) {
      console.error('Failed to parse AI response:', text);
      throw new Error(`Failed to parse AI response: ${e.message}`);
    }
  }
};
