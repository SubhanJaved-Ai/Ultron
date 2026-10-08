// Jarvis 2.0 — Service Worker with Network-First Strategy for Hologram Core
const CACHE_NAME = 'jarvis-pwa-hologram-v2';

self.addEventListener('install', (event) => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.map((key) => {
          if (key !== CACHE_NAME) {
            return caches.delete(key);
          }
        })
      );
    }).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  // Pass-through API and WebSocket requests immediately
  if (
    event.request.url.includes('/v1/') ||
    event.request.url.includes('/api/') ||
    event.request.url.includes('/ws')
  ) {
    return;
  }

  // Network-First for HTML/hologram so updates appear instantly
  event.respondWith(
    fetch(event.request)
      .then((networkResponse) => {
        if (networkResponse && networkResponse.status === 200) {
          const responseClone = networkResponse.clone();
          caches.open(CACHE_NAME).then((cache) => {
            cache.put(event.request, responseClone);
          });
        }
        return networkResponse;
      })
      .catch(() => {
        return caches.match(event.request);
      })
  );
});
