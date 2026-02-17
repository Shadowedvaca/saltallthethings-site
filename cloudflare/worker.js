/**
 * Salt All The Things — Shared Data API
 * Cloudflare Worker + KV
 *
 * Routes:
 *   GET  /data/:key           — read a data key (ideas, jokes, config, etc.)
 *   PUT  /data/:key           — write a data key
 *   GET  /export              — dump all data as one JSON blob (for svtools)
 *   PUT  /import              — bulk import
 *   GET  /public/episodes     — public: released episodes (no auth)
 *   GET  /public/homepage     — public: YouTube video IDs (no auth)
 *   GET  /health              — public health check
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

    // Public homepage config — returns YouTube video IDs for homepage
    if (request.method === 'GET' && path === '/public/homepage') {
      return handlePublicHomepage(env, request);
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
 * - Episodes with a release date in the past (PST timezone)
 * - That have an assigned idea with a title and summary
 * 
 * Query params:
 *   page (optional): page number, default 1
 *   limit (optional): episodes per page, default 10, max 50
 * 
 * Returns: {
 *   episodes: [{ episodeNumber, title, summary, releaseDate }],
 *   pagination: { page, limit, total, totalPages, hasMore }
 * }
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

    // Get current date in PST (UTC-8 or UTC-7 depending on DST)
    // For simplicity, we'll use a fixed UTC-8 offset
    const nowUTC = new Date();
    const nowPST = new Date(nowUTC.getTime() - (8 * 60 * 60 * 1000));
    const todayPST = nowPST.toISOString().split('T')[0];
    
    const ideasMap = {};
    ideas.forEach(function(idea) { ideasMap[idea.id] = idea; });

    const allEpisodes = [];
    for (const slot of slots) {
      // Only include released episodes (release date <= today in PST)
      if (slot.releaseDate > todayPST) continue;

      const ideaId = assignments[slot.id];
      if (!ideaId) continue;

      const idea = ideasMap[ideaId];
      if (!idea) continue;

      const title = idea.selectedTitle || (idea.titles && idea.titles[0]) || null;
      if (!title) continue;

      allEpisodes.push({
        episodeNumber: slot.episodeNumber,
        title: title,
        summary: idea.summary || '',
        releaseDate: slot.releaseDate
      });
    }

    // Sort newest first
    allEpisodes.sort(function(a, b) {
      return b.releaseDate.localeCompare(a.releaseDate);
    });

    // Pagination
    const url = new URL(request.url);
    const page = Math.max(1, parseInt(url.searchParams.get('page') || '1', 10));
    const limit = Math.min(50, Math.max(1, parseInt(url.searchParams.get('limit') || '10', 10)));
    
    const total = allEpisodes.length;
    const totalPages = Math.ceil(total / limit);
    const startIdx = (page - 1) * limit;
    const endIdx = startIdx + limit;
    const episodes = allEpisodes.slice(startIdx, endIdx);

    const responseData = {
      episodes: episodes,
      pagination: {
        page: page,
        limit: limit,
        total: total,
        totalPages: totalPages,
        hasMore: page < totalPages
      }
    };

    // Cache for 5 minutes — episodes don't change that often
    const headers = {
      ...corsHeaders(request),
      'Content-Type': 'application/json',
      'Cache-Control': 'public, max-age=300'
    };

    return new Response(JSON.stringify(responseData), { status: 200, headers });

  } catch (err) {
    return json({ error: 'Failed to load episodes' }, 500, request);
  }
}

/**
 * Public homepage config endpoint.
 * Returns YouTube video IDs and recent episodes for the homepage.
 * No auth required.
 */
async function handlePublicHomepage(env, request) {
  try {
    const configRaw = await env.SATT_DATA.get('config');
    const config = configRaw ? JSON.parse(configRaw) : {};

    const data = {
      youtubeVideo1: config.youtubeVideo1 || '',
      youtubeVideo2: config.youtubeVideo2 || '',
      youtubeVideo3: config.youtubeVideo3 || ''
    };

    // Cache for 5 minutes
    const headers = {
      ...corsHeaders(request),
      'Content-Type': 'application/json',
      'Cache-Control': 'public, max-age=300'
    };

    return new Response(JSON.stringify(data), { status: 200, headers });

  } catch (err) {
    return json({ error: 'Failed to load homepage config' }, 500, request);
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
