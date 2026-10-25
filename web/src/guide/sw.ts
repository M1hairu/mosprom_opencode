// Service worker of the guide (public/sw.js): the guide opens without network (#29, S7.4).
import { MEDIA_URLS } from "./photos";

/** Registers /sw.js and hands it the files this page already loaded (fetched before the worker
 *  controlled the page) and the pictures of every zone (the guest has not opened them yet). */
export function registerServiceWorker(): void {
  // Dev server: Vite serves modules, not the build. HTTP on LAN: no service worker at all.
  if (!import.meta.env.PROD || !("serviceWorker" in navigator)) return;
  navigator.serviceWorker
    .register("/sw.js")
    .then(() => navigator.serviceWorker.ready)
    .then((reg) => {
      const urls = performance
        .getEntriesByType("resource")
        .map((e) => new URL(e.name))
        .filter((u) => u.origin === location.origin && u.pathname.startsWith("/assets/"))
        .map((u) => u.pathname);
      reg.active?.postMessage({ type: "cache", urls: [...new Set([...urls, ...MEDIA_URLS])] });
    })
    .catch(() => {
      // Without the worker the guide still works online.
    });
}
