/**
 * Salt All The Things — Shared Data API
 * Cloudflare Worker + KV
 *
 * Routes:
 *   GET  /data/:key      — read a data key (ideas, jokes, config, etc.)
 *   PUT  /data/:key      — write a data key
 *   GET  /export         — dump all data as one JSON blob (for svtools)
 *   GET  /health         — public health check
 *
 * Auth: All routes except /health require X-Auth header matching ADMIN_PASSWORD secret.
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

    // Public health check
    if (path === '/health') {
      return json({ status: 'ok', timestamp: new Date().toISOString() }, 200, request);
    }

    // Auth check — compare raw password from header to stored secret
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
