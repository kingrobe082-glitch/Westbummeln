// Service Worker für Westbummeln. Ausgeliefert von westbummeln/pwa.py unter /sw.js;
// davor steht die Zeile `const CONFIG = {...}` mit Version, Hüllen-Dateien und Netz-Pfaden.
//
// - App-Hülle (CSS, JS, Karte, Icons, Offline-Seite): beim Installieren in einen versionierten Cache,
//   danach aus dem Cache. Die Dateinamen enthalten in Produktion einen Inhalts-Hash.
// - Seitenaufrufe (die Startseite): immer übers Netz, nie aus dem Cache. Ohne Netz kommt die Offline-Seite,
//   nie ein alter Spielstand.
// - /api, /account, /admin, /auth, /healthz, alles Fremde und jedes POST: fasst der Worker nicht an.
'use strict';

const CACHE_PREFIX = 'westbummeln-shell-';
const CACHE_NAME = CACHE_PREFIX + CONFIG.version;
const SHELL = new Set(CONFIG.shell);

self.addEventListener('install', event => {
  event.waitUntil((async () => {
    const cache = await caches.open(CACHE_NAME);
    await cache.addAll(CONFIG.shell.map(url => new Request(url, { cache: 'reload' })));
    await self.skipWaiting(); // neue Version sofort aktiv, ohne dass alle Tabs geschlossen werden müssen
  })());
});

self.addEventListener('activate', event => {
  event.waitUntil((async () => {
    const names = await caches.keys();
    await Promise.all(names.filter(name => name.startsWith(CACHE_PREFIX) && name !== CACHE_NAME)
      .map(name => caches.delete(name)));
    if (self.registration.navigationPreload) await self.registration.navigationPreload.enable();
    await self.clients.claim();
  })());
});

function networkOnly(path) {
  return CONFIG.networkOnly.some(prefix => path === prefix || path.startsWith(prefix + '/'));
}

self.addEventListener('fetch', event => {
  const request = event.request;
  if (request.method !== 'GET') return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin || networkOnly(url.pathname)) return;

  if (request.mode === 'navigate') {
    event.respondWith((async () => {
      try {
        return (await event.preloadResponse) || await fetch(request);
      } catch {
        return (await caches.match(CONFIG.offline, { cacheName: CACHE_NAME })) || Response.error();
      }
    })());
    return;
  }

  if (SHELL.has(url.pathname) && !url.search) {
    event.respondWith((async () => {
      const cached = await caches.match(request, { cacheName: CACHE_NAME });
      return cached || fetch(request);
    })());
  }
});
