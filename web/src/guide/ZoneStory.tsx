import { useEffect, useRef, useState } from "react";
import { parseBlock, parts, segments, type Block, type Seg, type Stat } from "./story";
import { render, sourceName, type Fact, type Site, type Stop } from "./site";
import z from "./zone.module.css";

// Zone card of the guide as a story: the key phrase, then a block per route message — big
// numbers with their sources, a timeline of years, notes — and «Что в зоне» folded.

const reduced = () => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;

/** Marks [data-reveal] children once they scroll into the phone's view (data-in). */
function useReveal(root: React.RefObject<HTMLElement | null>, key: string) {
  useEffect(() => {
    const els = root.current?.querySelectorAll<HTMLElement>("[data-reveal]") ?? [];
    if (reduced() || typeof IntersectionObserver === "undefined") {
      els.forEach((el) => (el.dataset.in = ""));
      return;
    }
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (!e.isIntersecting) continue;
          (e.target as HTMLElement).dataset.in = "";
          io.unobserve(e.target);
        }
      },
      { threshold: 0.15 },
    );
    els.forEach((el) => io.observe(el));
    return () => io.disconnect();
  }, [root, key]);
}

/** Counts up to the value once the tile is visible; the final value with reduced motion. */
function Count({ value }: { value: number }) {
  const ref = useRef<HTMLSpanElement>(null);
  const [v, setV] = useState(() => (reduced() ? value : 0));
  useEffect(() => {
    const el = ref.current;
    if (!el || reduced() || typeof IntersectionObserver === "undefined") {
      setV(value);
      return;
    }
    let raf = 0;
    const io = new IntersectionObserver(([e]) => {
      if (!e.isIntersecting) return;
      io.disconnect();
      const t0 = performance.now();
      const tick = (now: number) => {
        const k = Math.min(1, (now - t0) / 1300);
        setV(Math.round(value * (1 - Math.pow(1 - k, 4))));
        if (k < 1) raf = requestAnimationFrame(tick);
      };
      raf = requestAnimationFrame(tick);
    });
    io.observe(el);
    return () => {
      io.disconnect();
      cancelAnimationFrame(raf);
    };
  }, [value]);
  return <span ref={ref}>{v.toLocaleString("ru-RU")}</span>;
}

/** Source of a number, as the «Спросить» tab gives it: the case slide, the public source and
 *  what that source says when it differs (TRAP-8), «уточняется» for a number to check. */
function Source({ fact }: { fact: Fact }) {
  const check = fact.check ? <span className={z.check}>уточняется</span> : null;
  return (
    <span className={z.source}>
      {fact.case && <span>кейс ЛАССАРД, слайд {fact.case.slide}</span>}
      {fact.public && (
        <span>
          <a href={fact.public.url} target="_blank" rel="noreferrer">
            {sourceName(fact.public.url)} ↗
          </a>
          {fact.case && fact.public.value && <> — там: «{fact.public.value}»</>}
        </span>
      )}
      {!fact.case && !fact.public && <span>нормы</span>}
      {check}
    </span>
  );
}

function Segs({ segs }: { segs: Seg[] }) {
  return (
    <>
      {segs.map((s, i) =>
        s.kind === "text" ? (
          <span key={i}>{s.text}</span>
        ) : s.kind === "item" ? (
          <b key={i} className={z.item}>
            {s.name}
          </b>
        ) : (
          <span key={i}>
            <b className={z.num}>{s.fact.text}</b>
            {s.fact.check && <span className={z.check}>уточняется</span>}
          </span>
        ),
      )}
    </>
  );
}

function Tile({ stat, wide, i }: { stat: Stat; wide: boolean; i: number }) {
  return (
    <li className={z.tile} data-wide={wide} data-reveal style={{ "--i": i } as React.CSSProperties}>
      {stat.prefix && <span className={z.prefix}>{stat.prefix}</span>}
      {stat.value !== undefined ? (
        <span className={z.big}>
          <Count value={stat.value} />
          {stat.unit && <span className={z.unit}>{stat.unit}</span>}
        </span>
      ) : null}
      <span className={stat.value !== undefined ? z.caption : z.captionOnly}>{stat.caption}</span>
      <Source fact={stat.fact} />
    </li>
  );
}

function StoryBlock({ block }: { block: Block }) {
  if (block.rules)
    return (
      <section className={z.rules} data-reveal>
        <h3 className={z.rulesTitle}>
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path d="M12 2 4 5v6c0 5 3.4 9.3 8 11 4.6-1.7 8-6 8-11V5l-8-3Z" fill="none" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
            <path d="m8.5 12 2.5 2.5 4.5-5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
          </svg>
          {block.label}
        </h3>
        <ul>
          {block.notes.map((n, i) => (
            <li key={i}>
              <Segs segs={n} />
            </li>
          ))}
        </ul>
      </section>
    );
  // Wide tiles keep the grid even: the first one when the count is odd, the first and the last
  // when it is even and long.
  const n = block.stats.length;
  const wide = (i: number) => (n % 2 === 1 ? i === 0 : n >= 4 && (i === 0 || i === n - 1));
  return (
    <section className={z.block}>
      {block.label && (
        <h3 className={z.label} data-reveal>
          {block.label}
        </h3>
      )}
      {block.years.length > 0 && (
        <ol className={z.timeline} data-reveal>
          {block.years.map((y, i) => (
            <li key={y.fact.id} style={{ "--i": i } as React.CSSProperties}>
              <span className={z.node} aria-hidden="true" />
              <span className={z.year}>{y.year}</span>
              <span className={z.yearText}>{y.caption}</span>
              <Source fact={y.fact} />
            </li>
          ))}
        </ol>
      )}
      {block.stats.length > 0 && (
        <ul className={z.tiles}>
          {block.stats.map((s, i) => (
            <Tile key={s.fact.id} stat={s} wide={wide(i)} i={i} />
          ))}
        </ul>
      )}
      {block.notes.length > 0 && (
        <ul className={z.notes}>
          {block.notes.map((n, i) => (
            <li key={i} data-reveal style={{ "--i": i } as React.CSSProperties}>
              <Segs segs={n} />
            </li>
          ))}
        </ul>
      )}
      {block.next && (
        <p className={z.next} data-reveal>
          <span className={z.nextLabel}>Рядом</span>
          <span>
            <Segs segs={block.next} />
          </span>
        </p>
      )}
    </section>
  );
}

export function ZoneStory({ stop, site }: { stop: Stop; site: Site }) {
  const root = useRef<HTMLDivElement>(null);
  // New content for the same zone (the published document replaces the build) brings new
  // nodes: the reveal runs again on any change of the zone texts.
  useReveal(root, [stop.zone.id, ...stop.raw, stop.zone.display ?? "", ...(stop.zone.messages ?? [])].join("\n"));
  const lead = stop.zone.messages?.[0];
  const blocks = stop.raw.map((m) => parseBlock(m, site));
  const display = stop.zone.display ? parts(stop.zone.display) : [];
  return (
    <div className={z.story} ref={root}>
      {lead && (
        <p className={z.lead} data-reveal>
          {render(lead, site)}
        </p>
      )}
      {blocks.map((b, i) => (
        <StoryBlock key={i} block={b} />
      ))}
      {display.length > 0 && (
        <details className={z.inZone} data-reveal>
          <summary>
            Что в зоне <span className={z.count}>{display.length}</span>
          </summary>
          <ul>
            {display.map((d, i) => (
              <li key={i}>
                <Segs segs={segments(d, site)} />
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
