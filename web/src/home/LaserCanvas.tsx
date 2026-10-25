import { useEffect, useRef, useState } from "react";
import type { LaserScene } from "./laserScene";

let webgl: boolean | undefined;

/** True for a software rasterizer (SwiftShader, llvmpipe): the hero scene takes seconds per frame there. */
export function isSoftwareRenderer(name: string): boolean {
  return /swiftshader|llvmpipe|softpipe|software/i.test(name);
}

/** Probes WebGL once per page load and frees the probe context. A software rasterizer counts as no WebGL. */
function hasWebGL(): boolean {
  if (webgl === undefined) {
    try {
      const gl = document.createElement("canvas").getContext("webgl2");
      const info = gl?.getExtension("WEBGL_debug_renderer_info");
      const name = gl && info ? String(gl.getParameter(info.UNMASKED_RENDERER_WEBGL)) : "";
      webgl = Boolean(gl) && !isSoftwareRenderer(name);
      gl?.getExtension("WEBGL_lose_context")?.loseContext();
    } catch {
      webgl = false;
    }
  }
  return webgl;
}

// Canvas of the hero scene. The three.js module loads after the text paints; without WebGL
// (or on a software rasterizer, which blocks the page for seconds per frame) the CSS backdrop stays. Reduced motion draws one still frame.
export function LaserCanvas({ hero, className }: { hero: React.RefObject<HTMLElement | null>; className: string }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const el = canvas.current;
    const section = hero.current;
    if (!el || !section || !hasWebGL()) return;
    // ?heroAt=<s> freezes the scene at that cycle time: screenshots of each phase.
    const at = new URLSearchParams(window.location.search).get("heroAt");
    const stillAt = at !== null && Number.isFinite(Number(at)) ? Number(at) : undefined;
    const still = stillAt !== undefined || window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let scene: LaserScene | null = null;
    let disposed = false;
    let visible = true;
    const sync = () => scene?.setPaused(!visible || document.hidden);
    const onScroll = () => scene?.setScroll(window.scrollY / Math.max(1, section.offsetHeight));
    const onPointer = (e: PointerEvent) => {
      scene?.setPointer((e.clientX / window.innerWidth) * 2 - 1, (e.clientY / window.innerHeight) * 2 - 1);
      // Only a mouse aims the beam: on a touch screen the finger scrolls the page.
      const r = el.getBoundingClientRect();
      const inside = e.clientX >= r.left && e.clientX <= r.right && e.clientY >= r.top && e.clientY <= r.bottom;
      scene?.setAim(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1, inside && e.pointerType === "mouse");
    };
    const onLeave = (e: PointerEvent) => {
      if (!e.relatedTarget) scene?.setAim(0, 0, false);
    };
    const io = new IntersectionObserver(([entry]) => {
      visible = entry.isIntersecting;
      sync();
    });
    io.observe(section);
    import("./laserScene")
      .then(({ startLaserScene }) => {
        if (disposed) return;
        scene = startLaserScene(el, {
          still,
          stillAt,
          onFirstFrame: () => !disposed && setReady(true),
          // Back to the CSS backdrop: a lost context leaves a black canvas.
          onLost: () => !disposed && setReady(false),
        });
        onScroll();
        sync();
      })
      .catch((e: unknown) => console.error("hero: 3D-сцена не загрузилась", e));
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("pointermove", onPointer, { passive: true });
    document.addEventListener("pointerout", onLeave);
    document.addEventListener("visibilitychange", sync);
    return () => {
      disposed = true;
      io.disconnect();
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("pointermove", onPointer);
      document.removeEventListener("pointerout", onLeave);
      document.removeEventListener("visibilitychange", sync);
      scene?.dispose();
    };
  }, [hero]);

  return <canvas ref={canvas} className={className} data-ready={ready} aria-hidden="true" />;
}
