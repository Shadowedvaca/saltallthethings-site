/**
 * Salt All The Things — Shared Data API
 * Cloudflare Worker + KV
 *
 * Routes:
 *   GET  /data/:key         — read a data key (ideas, jokes, config, etc.)
 *   PUT  /data/:key         — write a data key
 *   GET  /export            — dump all data as one JSON blob (for svtools)
 *   PUT  /import            — bulk import
 *   GET  /public/episodes   — public: released episodes (no auth)
 *   GET  /health            — public health check
 *
 * Auth: All routes except /health and /public/* require X-Auth header.
 */

const DATA_KEYS = ['config', 'ideas', 'jokes', 'showSlots', 'assignments'];

export default {
  async fetch(request, env) {
    // CORS preflight
    if (request.method === 'OPTIONS') {
      return new Response(null, {
        status: 204,
        headers: corsHeaders(request)
      });
    }

    const url = new URL(request.url);
    const path = url.pathname;

    // ---- Public routes (no auth) ----

    // Health check
    if (path === '/health') {
      return json({ status: 'ok', timestamp: new Date().toISOString() }, 200, request);
    }

    // Public episodes — returns only released episodes with titles/summaries
    if (request.method === 'GET' && path === '/public/episodes') {
      return handlePublicEpisodes(env, request);
    }

    // ---- Authenticated routes ----

    const authPassword = request.headers.get('X-Auth');
    if (!authPassword || authPassword !== env.ADMIN_PASSWORD) {
      return json({ error: 'Unauthorized' }, 401, request);
    }

    // GET /data/:key
    if (request.method === 'GET' && path.startsWith('/data/')) {
      const key = path.replace('/data/', '');
      if (!DATA_KEYS.includes(key)) {
        return json({ error: 'Invalid key. Valid keys: ' + DATA_KEYS.join(', ') }, 400, request);
      }
      const value = await env.SATT_DATA.get(key);
      return json(value ? JSON.parse(value) : null, 200, request);
    }

    // PUT /data/:key
    if (request.method === 'PUT' && path.startsWith('/data/')) {
      const key = path.replace('/data/', '');
      if (!DATA_KEYS.includes(key)) {
        return json({ error: 'Invalid key. Valid keys: ' + DATA_KEYS.join(', ') }, 400, request);
      }
      const body = await request.json();
      await env.SATT_DATA.put(key, JSON.stringify(body));
      return json({ ok: true, key: key }, 200, request);
    }

    // GET /export — full dump for svtools
    if (request.method === 'GET' && path === '/export') {
      const data = {};
      for (const key of DATA_KEYS) {
        const value = await env.SATT_DATA.get(key);
        data[key] = value ? JSON.parse(value) : null;
      }
      data.exportDate = new Date().toISOString();
      return json(data, 200, request);
    }

    // PUT /import — bulk import
    if (request.method === 'PUT' && path === '/import') {
      const data = await request.json();
      for (const key of DATA_KEYS) {
        if (data[key] !== undefined) {
          await env.SATT_DATA.put(key, JSON.stringify(data[key]));
        }
      }
      return json({ ok: true, imported: DATA_KEYS.filter(k => data[k] !== undefined) }, 200, request);
    }

    return json({ error: 'Not found' }, 404, request);
  }
};

/**
 * Public episodes endpoint.
 * Joins showSlots + assignments + ideas to return only:
 * - Episodes with a release date in the past
 * - That have an assigned idea with a title and summary
 * Returns: [{ episodeNumber, title, summary, releaseDate }]
 */
async function handlePublicEpisodes(env, request) {
  try {
    const [slotsRaw, assignmentsRaw, ideasRaw] = await Promise.all([
      env.SATT_DATA.get('showSlots'),
      env.SATT_DATA.get('assignments'),
      env.SATT_DATA.get('ideas')
    ]);

    const slots = slotsRaw ? JSON.parse(slotsRaw) : [];
    const assignments = assignmentsRaw ? JSON.parse(assignmentsRaw) : {};
    const ideas = ideasRaw ? JSON.parse(ideasRaw) : [];

    const today = new Date().toISOString().split('T')[0];
    const ideasMap = {};
    ideas.forEach(function(idea) { ideasMap[idea.id] = idea; });

    const episodes = [];
    for (const slot of slots) {
      // Only include released episodes (release date <= today)
      if (slot.releaseDate > today) continue;

      const ideaId = assignments[slot.id];
      if (!ideaId) continue;

      const idea = ideasMap[ideaId];
      if (!idea) continue;

      const title = idea.selectedTitle || (idea.titles && idea.titles[0]) || null;
      if (!title) continue;

      episodes.push({
        episodeNumber: slot.episodeNumber,
        title: title,
        summary: idea.summary || '',
        releaseDate: slot.releaseDate
      });
    }

    // Sort newest first
    episodes.sort(function(a, b) {
      return b.releaseDate.localeCompare(a.releaseDate);
    });

    // Cache for 5 minutes — episodes don't change that often
    const headers = {
      ...corsHeaders(request),
      'Content-Type': 'application/json',
      'Cache-Control': 'public, max-age=300'
    };

    return new Response(JSON.stringify(episodes), { status: 200, headers });

  } catch (err) {
    return json({ error: 'Failed to load episodes' }, 500, request);
  }
}

function json(data, status, request) {
  return new Response(JSON.stringify(data), {
    status: status,
    headers: {
      'Content-Type': 'application/json',
      ...corsHeaders(request)
    }
  });
}

function corsHeaders(request) {
  return {
    'Access-Control-Allow-Origin': request ? (request.headers.get('Origin') || '*') : '*',
    'Access-Control-Allow-Methods': 'GET, PUT, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type, X-Auth',
    'Access-Control-Max-Age': '86400'
  };
}
