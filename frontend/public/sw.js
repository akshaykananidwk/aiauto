// AIAuto service worker.
// Strategy matters: the app shell (HTML) is NETWORK-FIRST so users always
// get the newest frontend immediately after a platform update — a stale
// cached shell would keep serving old JS with old bugs. Hashed build
// assets are immutable, so they are cache-first.
const CACHE = 'aiauto-v3'

self.addEventListener('install', (event) => {
  self.skipWaiting()
  event.waitUntil(caches.open(CACHE).then(c => c.addAll(['./'])))
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
  if (event.request.method !== 'GET' || url.origin !== location.origin) return
  if (url.pathname.startsWith('/api')) return // never cache API traffic

  // app shell / navigations: network first, cache only as offline fallback
  if (event.request.mode === 'navigate' || url.pathname === '/' ||
      url.pathname.endsWith('.html')) {
    event.respondWith(
      fetch(event.request).then(resp => {
        const clone = resp.clone()
        caches.open(CACHE).then(c => c.put(event.request, clone))
        return resp
      }).catch(() => caches.match(event.request).then(c => c || caches.match('./')))
    )
    return
  }

  // hashed immutable build assets: cache first
  if (url.pathname.startsWith('/assets/')) {
    event.respondWith(
      caches.match(event.request).then(cached => cached || fetch(event.request).then(resp => {
        if (resp.ok) {
          const clone = resp.clone()
          caches.open(CACHE).then(c => c.put(event.request, clone))
        }
        return resp
      }))
    )
    return
  }

  // everything else (icons, manifest): stale-while-revalidate
  event.respondWith(
    caches.match(event.request).then(cached => {
      const fetched = fetch(event.request).then(resp => {
        if (resp.ok) {
          const clone = resp.clone()
          caches.open(CACHE).then(c => c.put(event.request, clone))
        }
        return resp
      }).catch(() => cached)
      return cached || fetched
    })
  )
})
