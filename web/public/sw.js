// Service worker of the guide (#29): pages and build files from the cache when there is no network.
// /api/* is never cached: events wait in the guide's own queue (src/guide/visit.ts).
const CACHE = "lassard-v1";
const SHELL = "/index.html";

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(CACHE)
      .then((c) => c.add(SHELL))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

// The page sends the build files it loaded before the worker took control.
self.addEventListener("message", (event) => {
  if (event.data?.type === "cache" && Array.isArray(event.data.urls)) {
    event.waitUntil(caches.open(CACHE).then((c) => c.addAll(event.data.urls)));
  }
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  const url = new URL(req.url);
  if (req.method !== "GET" || url.origin !== location.origin || url.pathname.startsWith("/api/")) return;

  // SPA pages: network first (a new build shows at once), the last page from the cache without network.
  if (req.mode === "navigate") {
    event.respondWith(
      fetch(req)
        .then((res) => {
          // Only the SPA page: a picture or version.txt opened in a tab must not become the shell.
          // The static render gallery (/renders/) is a separate page, not the SPA shell.
          if (res.ok && (res.headers.get("content-type") ?? "").includes("text/html") && !url.pathname.startsWith("/renders/")) {
            const copy = res.clone();
            caches.open(CACHE).then((c) => c.put(SHELL, copy));
          }
          return res;
        })
        .catch(() => caches.match(SHELL, { ignoreVary: true }).then((hit) => hit ?? Response.error())),
    );
    return;
  }

  // Zone renders of the kiosk (/renders/*.webp): network first, so a new render shows at once;
  // the copy of what was shown stays for a break of the network. Only full-size files: the small
  // _s files of the gallery page are not cached.
  if (req.destination === "image" && /^\/renders\/(?!.*_s\.webp$)[^/]+\.webp$/.test(url.pathname)) {
    event.respondWith(
      fetch(req)
        .then((res) => {
          if (res.ok) {
            const copy = res.clone();
            caches.open(CACHE).then((c) => c.put(req, copy));
          }
          return res;
        })
        .catch(() => caches.match(req, { ignoreVary: true }).then((hit) => hit ?? Response.error())),
    );
    return;
  }

  // Build files have a hash in the name: the cached copy never gets old.
  if (url.pathname.startsWith("/assets/")) {
    event.respondWith(
      // ignoreVary: a proxy may add Vary (Origin, Accept-Encoding); the hashed file is the same.
      caches.match(req, { ignoreVary: true }).then(
        (hit) =>
          hit ??
          fetch(req).then((res) => {
            if (res.ok) {
              const copy = res.clone();
              caches.open(CACHE).then((c) => c.put(req, copy));
            }
            return res;
          }),
      ),
    );
  }
});
