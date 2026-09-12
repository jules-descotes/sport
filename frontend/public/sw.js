/**
 * Service worker minimal — la coquille, et rien d'autre.
 *
 * Objectif unique ici : l'app installée s'ouvre et affiche quelque chose même
 * sans réseau.
 *
 * Deux règles, pas une de plus :
 *   - les navigations passent par le réseau, avec repli sur le cache ;
 *   - les fichiers immuables de Next (/_next/static) sont servis depuis le cache.
 * L'API n'est jamais mise en cache : une prévision périmée est pire que rien.
 *
 * **La file hors ligne du lot 2 ne vit pas ici.** Elle est dans la page
 * (`lib/offline-queue.ts`), et c'est délibéré : ce qu'on met en attente n'est
 * pas une requête à rejouer à l'identique mais une notation à envoyer, avec sa
 * règle propre — une erreur réseau se retente, un refus de l'API se jette, et
 * re-noter la même session remplace l'entrée au lieu d'en ajouter une. Un
 * service worker qui rejouerait des requêtes ne saurait rien faire de tout ça.
 *
 * Conséquence à connaître : la notation hors ligne marche sur un écran **déjà
 * ouvert**. Naviguer sans réseau vers un écran jamais visité tombe sur
 * `offline.html` — la navigation demande au serveur une charge utile que le
 * cache n'a pas.
 */

const CACHE = "sport-shell-v1";
const OFFLINE_URL = "/offline.html";
const PRECACHE = [OFFLINE_URL, "/icons/icon-192.png", "/icons/icon-512.png"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(CACHE)
      .then((cache) => cache.addAll(PRECACHE))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key))),
      )
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const { request } = event;

  if (request.method !== "GET") return;

  const url = new URL(request.url);

  // Jamais de cache sur l'API ni sur d'autres origines.
  if (url.origin !== self.location.origin) return;
  if (url.pathname.startsWith("/api/")) return;

  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request)
        .then((response) => {
          const copy = response.clone();
          caches.open(CACHE).then((cache) => cache.put(request, copy));
          return response;
        })
        .catch(async () => {
          const cached = await caches.match(request);
          return cached || caches.match(OFFLINE_URL);
        }),
    );
    return;
  }

  if (url.pathname.startsWith("/_next/static") || url.pathname.startsWith("/icons/")) {
    event.respondWith(
      caches.match(request).then(
        (cached) =>
          cached ||
          fetch(request).then((response) => {
            const copy = response.clone();
            caches.open(CACHE).then((cache) => cache.put(request, copy));
            return response;
          }),
      ),
    );
  }
});
