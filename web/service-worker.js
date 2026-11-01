'use strict';
const CACHE = 'wuji-public-shell-v1';
const PUBLIC = ['/web/offline.html', '/web/icons/wuji-180.png', '/web/icons/wuji-192.png', '/web/icons/wuji-512.png'];
self.addEventListener('install', event => event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(PUBLIC))));
self.addEventListener('activate', event => event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k.startsWith('wuji-public-shell-') && k !== CACHE).map(k => caches.delete(k))))));
self.addEventListener('message', event => { if (event.data && event.data.type === 'SKIP_WAITING') self.skipWaiting(); });
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);
  if (url.origin !== self.location.origin || event.request.method !== 'GET') return;
  if (event.request.mode === 'navigate') {
    event.respondWith(fetch(event.request, { cache: 'no-store' }).catch(() => caches.match('/web/offline.html')));
  } else if (PUBLIC.includes(url.pathname)) {
    event.respondWith(caches.match(event.request).then(cached => cached || fetch(event.request)));
  }
  // API, saves, configuration, private HTML and model output are NEVER cached.
});
