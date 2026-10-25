// Pictures of the guide: exhibit photos from lassard.ru (the jury allowed them, 24.10) and one
// render of each zone (web/public/renders, 960 px). Files: media/<item id>.webp, media/view-<zone id>.webp.
import type { Zone } from "./site";

const files = import.meta.glob("./media/*.webp", { eager: true, query: "?url", import: "default" }) as Record<string, string>;
const byName = Object.fromEntries(Object.entries(files).map(([path, url]) => [path.slice("./media/".length, -".webp".length), url]));

/** Every picture of the guide: the service worker caches them all, so the route works offline (#29, p. 5). */
export const MEDIA_URLS: string[] = Object.values(files);

/** Render of the zone in the hall (web/public/renders, v2), if the concept has one. */
export function zoneView(zone: Zone): string | undefined {
  return byName[`view-${zone.id}`];
}

// Zone id -> file of the 1920 x 1080 render in web/public/renders (found by comparing the frames with
// media/view-<zone>.webp). The zone screen in the hall shows these; phones keep the small view files.
const RENDERS: Record<string, string> = {
  crystals: "10_zona_kristallov",
  cutting: "26_smart_base_okno_v_ceh",
  diodes: "17_pyupitr_diody",
  edu_class: "33_lazernyy_klass",
  engraving: "23_zona_gravirovki",
  entrance: "04_zal_ot_vhoda",
  handheld: "28_ruchnye_apparaty",
  laser_sources: "19_zona_istochnikov",
  meeting: "35_peregovornaya",
  optomechanics: "31_optomehanika",
  quantrons: "15_zona_kvantronov",
  robots: "22_zona_robotov",
  test_lab: "36_demo_zona",
};

/** Full-size render of the zone for the kiosk screen. Not in MEDIA_URLS: phones do not cache it. */
export function zoneRender(zone: Zone): string | undefined {
  const file = RENDERS[zone.id];
  return file ? `/renders/${file}.webp` : undefined;
}

/** Photo of the first exhibit of the zone that has one. */
export function exhibitPhoto(zone: Zone): { id: string; url: string } | undefined {
  const id = (zone.exhibits ?? []).find((e) => byName[e]);
  return id ? { id, url: byName[id] } : undefined;
}
