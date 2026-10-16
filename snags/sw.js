const CACHE = 'snags-v1';
const CDN = /(^|\.)(jsdelivr\.net|googleapis\.com|gstatic\.com)$/;

self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', e => e.waitUntil(self.clients.claim()));

self.addEventListener('fetch', e => {
  if (e.request.method !== 'GET') return;
  const url = new URL(e.request.url);
  const own = url.origin === location.origin;
  if (!own && !CDN.test(url.hostname)) return;
  e.respondWith((async () => {
    const cache = await caches.open(CACHE);
    const hit = await cache.match(e.request, { ignoreVary: true });
    // Pinned library files never change: serve from cache. Our own files: network first so updates land.
    if (hit && !own) return hit;
    try {
      // Our own files: ask the server every time, or the browser's short-term cache can hide an update for hours.
      const res = await (own ? fetch(e.request.url, { cache: 'no-cache' }) : fetch(e.request));
      if (res.ok) cache.put(e.request, res.clone());
      return res;
    } catch (err) {
      if (hit) return hit;
      throw err;
    }
  })());
});
