import { useEffect, useId, useRef, useState } from "react";
import { room, zones } from "../../../content/plan-219-zoned.json";
import type { Stop } from "./site";
import styles from "./guide.module.css";

type Point = [number, number];
const [, , [width, height]] = room.boundary;
const bounds = (polygon: number[][]) => {
  const xs = polygon.map(([x]) => x);
  const ys = polygon.map(([, y]) => height - y);
  return { x: (Math.min(...xs) + Math.max(...xs)) / 2, top: Math.min(...ys), bottom: Math.max(...ys), right: Math.max(...xs) };
};

type Place = { pin: Point; label: Point; door: Point[] };

// Shared aisle between the north row and the rest of the hall; spines lead to the west column and the meeting room.
const AISLE = 7.6;
const WEST_SPINE = 6.2;
const MEETING_SPINE = 13;

/** Pin, label and the door path from the pin to the aisle (its last point lies on the aisle). */
function position(id: string): Place | undefined {
  const zone = zones.find((z) => z.id === id);
  if (!zone) return;
  const b = bounds(zone.polygon);
  if (id === "engraving") return { pin: [b.x, 5.3], label: [b.x, 1.65], door: [[b.x, 5.3], [b.x, 6.45], [WEST_SPINE, 6.45], [WEST_SPINE, AISLE]] };
  if (b.top === 0) return { pin: [b.x, 5.3], label: [b.x, 1.65], door: [[b.x, 5.3], [b.x, AISLE]] };
  if (id === "cutting") return { pin: [3.25, 10.65], label: [3.25, 8.1], door: [[3.25, 10.65], [WEST_SPINE, 10.65], [WEST_SPINE, AISLE]] };
  if (id === "test_lab") return { pin: [3.25, 13.9], label: [3.25, 15.6], door: [[3.25, 13.9], [WEST_SPINE, 13.9], [WEST_SPINE, AISLE]] };
  if (id === "meeting") return { pin: [8.85, 13.9], label: [8.85, 15.8], door: [[8.85, 13.9], [MEETING_SPINE, 13.9], [MEETING_SPINE, AISLE]] };
  return { pin: [b.x, b.top + 1.25], label: [b.x, b.top + 3], door: [[b.x, b.top + 1.25], [b.x, AISLE]] };
}

/** Neighbouring zones in one row or column get a straight arrow, unless it would cross a zone label. */
function direct(a: Place, b: Place): boolean {
  const [ax, ay] = a.pin;
  const [bx, by] = b.pin;
  if (ay === by) return Math.abs(ax - bx) <= 7 && ay !== AISLE;
  if (ax !== bx || Math.abs(ay - by) > 4) return false;
  const [lo, hi] = [Math.min(ay, by), Math.max(ay, by)];
  return ![a.label, b.label].some(([x, y]) => x === ax && y > lo && y < hi);
}

const shift = (points: Point[], d: number): Point[] => points.map(([x, y]) => [x + d, y + d]);

/** Keep the line clear of the numbered markers, including the arrowhead at the destination. */
function trim(points: Point[]): Point[] {
  const clean = points.filter((p, i) => i === 0 || p[0] !== points[i - 1][0] || p[1] !== points[i - 1][1]);
  if (clean.length < 2) return [];
  for (const [end, next] of [[0, 1], [clean.length - 1, clean.length - 2]]) {
    const p = clean[end];
    const q = clean[next];
    const length = Math.abs(q[0] - p[0]) + Math.abs(q[1] - p[1]);
    if (length > 0.8) clean[end] = [p[0] + ((q[0] - p[0]) / length) * 0.8, p[1] + ((q[1] - p[1]) / length) * 0.8];
  }
  return clean;
}

/**
 * Schematic connections between consecutive stops; they follow the shared aisle and are not surveyed walking paths.
 * The way out of a pin and the way into it run side by side, and links whose aisle parts overlap get separate lanes.
 */
export function routeLinks(ids: string[]): Point[][] {
  const places = ids.map(position);
  const lanes: [number, number][][] = [];
  return ids.slice(1).map((_, i) => {
    const a = places[i];
    const b = places[i + 1];
    if (!a || !b) return [];
    if (direct(a, b)) return trim([a.pin, b.pin]);
    const out = shift(a.door, 0.2);
    const into = shift(b.door, -0.2).reverse();
    const from = out[out.length - 1][0];
    const to = into[0][0];
    const span: [number, number] = [Math.min(from, to) - 0.15, Math.max(from, to) + 0.15];
    let lane = lanes.findIndex((taken) => taken.every(([lo, hi]) => span[1] < lo || span[0] > hi));
    if (lane < 0) lane = lanes.push([]) - 1;
    lanes[lane].push(span);
    // Lanes fill the aisle from its middle outwards: 0, -1, +1, -2, +2… steps of 0.3 m; no two lanes share a line.
    const y = AISLE + (lane % 2 ? -1 : 1) * Math.ceil(lane / 2) * 0.3;
    return trim([...out.slice(0, -1), [from, y], [to, y], ...into.slice(1)]);
  });
}

function lines(name: string): string[] {
  return name.split(" ").reduce<string[]>((result, word) => {
    const last = result.length - 1;
    if (last >= 0 && `${result[last]} ${word}`.length <= 17) result[last] += ` ${word}`;
    else result.push(word);
    return result;
  }, []);
}

export function HallMap({ stops, index, onOpen }: { stops: Stop[]; index: number; onOpen: (i: number) => void }) {
  const arrowId = useId().replace(/:/g, "");
  const [overview, setOverview] = useState(false);
  const scroll = useRef<HTMLDivElement>(null);
  const activeZone = stops[index]?.zone.id;
  const markers = [
    ...zones.filter((z) => !stops.some((s) => s.zone.id === z.id)).map((zone) => ({ zone, stopIndex: -1 })),
    ...stops.flatMap((stop, stopIndex) => {
      const zone = zones.find((z) => z.id === stop.zone.id);
      return zone ? [{ zone, stopIndex }] : [];
    }),
  ];
  useEffect(() => {
    const container = scroll.current;
    const active = activeZone && position(activeZone);
    if (container && active && !overview) {
      container.scrollLeft = (active.pin[0] / width) * container.scrollWidth - container.clientWidth / 2;
    }
  }, [activeZone, overview]);
  return (
    <figure className={styles.hall}>
      <div className={styles.hallHeader}>
        <div><strong>Схема зала</strong><span>Нажмите на зону, чтобы открыть её</span></div>
        <button type="button" onClick={() => setOverview(!overview)} aria-pressed={overview}>{overview ? "Крупнее" : "Весь зал"}</button>
      </div>
      <div ref={scroll} className={styles.hallScroll} tabIndex={0} role="region" aria-label="Карта зала. На узком экране прокрутите в сторону">
        <svg className={overview ? styles.hallOverview : undefined} viewBox={`-0.35 -0.35 ${width + 0.7} ${height + 0.7}`} role="group" aria-label="Зоны и порядок остановок вашего маршрута">
          <defs>
            <marker id={arrowId} viewBox="0 0 8 8" refX="7" refY="4" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M1 1 7 4 1 7" className={styles.hallArrow} /></marker>
          </defs>
          <rect width={width} height={height} rx="0.2" className={styles.hallRoom} />
          {zones.map((z) => {
            const i = stops.findIndex((s) => s.zone.id === z.id);
            return <polygon key={z.id} className={i < 0 ? styles.hallOff : i === index ? styles.hallHere : styles.hallZone} points={z.polygon.map(([x, y]) => `${x},${height - y}`).join(" ")} onClick={i < 0 ? undefined : () => onOpen(i)} />;
          })}
          <g aria-hidden="true" className={styles.hallLinks}>
            {routeLinks(stops.map((s) => s.zone.id)).map((points, i) => <polyline key={`${stops[i + 1].zone.id}-${i}`} className={styles.hallPath} points={points.map((p) => p.join(",")).join(" ")} markerEnd={`url(#${arrowId})`} />)}
          </g>
          {markers.map(({ zone: z, stopIndex: i }) => {
            const p = position(z.id)!;
            const name = i < 0 ? z.name : stops[i].zone.name;
            return (
              <g key={`${z.id}-${i}`} className={i < 0 ? styles.hallInactive : i === index ? styles.hallPinHere : styles.hallPin}
                role={i < 0 ? undefined : "button"} tabIndex={i < 0 ? undefined : 0} data-film={i < 0 ? undefined : ""}
                aria-label={i < 0 ? undefined : `${i + 1}. ${name}${i === index ? ". Вы здесь" : ""}`}
                aria-current={i === index ? "step" : undefined}
                onClick={i < 0 ? undefined : () => onOpen(i)}
                onKeyDown={i < 0 ? undefined : (event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); onOpen(i); } }}>
                <title>{name}</title>
                <text className={styles.hallLabel} x={p.label[0]} y={p.label[1]}>{lines(name).map((line, n) => <tspan key={n} x={p.label[0]} dy={n === 0 ? 0 : 0.58}>{line}</tspan>)}</text>
                {i >= 0 && <><circle cx={p.pin[0]} cy={p.pin[1]} r="0.67" /><text className={styles.hallNumber} x={p.pin[0]} y={p.pin[1]}>{i + 1}</text></>}
              </g>
            );
          })}
        </svg>
      </div>
      <figcaption><span className={styles.hallLegend}><i />Текущая зона <b>→</b>Порядок осмотра</span><span>Номера — шаги маршрута. Линии условные, это не план эвакуации.</span><span className={styles.hallHint}>Прокрутите карту в сторону или нажмите «Весь зал».</span></figcaption>
    </figure>
  );
}
