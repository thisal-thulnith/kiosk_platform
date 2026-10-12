// Offline shell for the screens: network first, cached copy if the server can't be reached.
// Only the screen files are cached. API calls (/v1/...) always go to the server.
const CACHE = "kiosk-screens-v3";

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  // Pages and the app's files only; API calls (/v1) and photos (/media) always go to the server.
  if (e.request.method !== "GET" || url.origin !== location.origin || url.pathname.startsWith("/v1") || url.pathname.startsWith("/media")) return;
  e.respondWith(
    fetch(e.request)
      .then((res) => {
        if (res.ok) {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(e.request, copy));
        }
        return res;
      })
      .catch(() => caches.match(e.request, { ignoreSearch: true }).then((hit) => hit || Response.error())),
  );
});
