import { useEffect, useLayoutEffect, useRef } from "react";
import { useLocation } from "react-router";

// Every change of the address opens the new page along the beam cut (home/LaserLink.tsx,
// laserReveal). The zone screen in the hall is a kiosk: no cut there.
type Overlay = typeof import("../home/LaserLink");
let mod: Overlay | null = null;
const load = () =>
  import("../home/LaserLink").then((m) => {
    mod = m;
    return m;
  });

export function OpticCut() {
  const { pathname } = useLocation();
  const last = useRef(pathname);
  const here = useRef(pathname);
  here.current = pathname;
  // Load the overlay ahead: then the cut covers the new page before its first paint.
  useEffect(() => {
    // The film clip loads too, not on the kiosk; about 0.3 MB for one screen
    // shape, the other one after the phone turns.
    const warm = () => {
      if (here.current.startsWith("/screen")) return;
      void (mod ? mod.warmFilm() : load().then((m) => m.warmFilm()).catch(() => undefined));
    };
    warm();
    window.addEventListener("resize", warm);
    return () => {
      window.removeEventListener("resize", warm);
    };
  }, []);
  // A guest who came in on the kiosk path gets the clip once they leave it.
  useEffect(() => {
    if (!pathname.startsWith("/screen") && mod) void mod.warmFilm();
  }, [pathname]);
  // Every screen-changing click: links, tabs, buttons marked data-film.
  useEffect(() => {
    let replaying = false;
    const onClick = (e: MouseEvent) => {
      if (replaying || !mod || here.current.startsWith("/screen")) return;
      if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      const t = (e.target as Element | null)?.closest?.('a[href], [role="tab"], [data-film]') as HTMLElement | null;
      if (!t || t.closest("[data-laser], [data-no-film], .laser-wipe") || t.matches(":disabled, [aria-disabled='true'], [aria-current='page'], [aria-selected='true']")) return;
      if (t instanceof HTMLAnchorElement && (t.target === "_blank" || t.hasAttribute("download") || t.origin !== window.location.origin)) return;
      const replay = () => {
        replaying = true;
        try {
          t.click();
        } finally {
          replaying = false;
        }
      };
      if (mod.opticClick(replay)) {
        e.preventDefault();
        e.stopPropagation();
      }
    };
    document.addEventListener("click", onClick, true);
    return () => document.removeEventListener("click", onClick, true);
  }, []);
  useLayoutEffect(() => {
    if (last.current === pathname) return;
    last.current = pathname;
    if (pathname.startsWith("/screen")) return;
    if (mod) mod.laserReveal();
    else void load().then((m) => m.laserReveal()).catch(() => undefined);
  }, [pathname]);
  return null;
}
