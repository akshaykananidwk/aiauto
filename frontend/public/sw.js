// Minimal service worker: cache-first for static assets, network for API.
const CACHE = 'aiauto-v1'

self.addEventListener('install', (event) => {
  self.skipWaiting()
  event.waitUntil(caches.open(CACHE).then(c => c.addAll(['./', './index.html'])))
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    ).then(() => self.clients.claim())
  )
})

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url)
  if (event.request.method !== 'GET' || url.pathname.startsWith('/api')) return
  event.respondWith(
    caches.match(event.request).then(cached => {
      const fetched = fetch(event.request).then(resp => {
        if (resp.ok && url.origin === location.origin) {
          const clone = resp.clone()
          caches.open(CACHE).then(c => c.put(event.request, clone))
        }
        return resp
      }).catch(() => cached)
      return cached || fetched
    })
  )
})
