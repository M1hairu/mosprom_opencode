import { useEffect, useRef, useState } from "react";
import factsJson from "../../../content/facts.json";
import { getHealth } from "../api";
import { buildLabel } from "../format";
import { LaserCanvas } from "../home/LaserCanvas";
import { LaserLink, laserReveal } from "../home/LaserLink";
import { Logo } from "../ui/components";
import styles from "./home.module.css";

// Start page — the first screen of the jury link. Hero: a laser engraves the logo live (3D),
// then the customer route, a number with its source and a door to each surface.
const ROUTE = [
  { n: "01", title: "История и масштаб", text: "Гость видит путь компании и масштаб производства." },
  { n: "02", title: "Оборудование", text: "Гость видит станки в работе и узнаёт, что они делают." },
  { n: "03", title: "Тест на образце", text: "Менеджер принимает образец гостя. Тест идёт в цехе на закрытом станке, протокол — в переговорной." },
  { n: "04", title: "Сделка", text: "Менеджер и гость обсуждают заказ в переговорной." },
];

// Chunks of the surfaces: loaded on hover so the laser page change shows a ready page.
const PRELOAD: Record<string, () => Promise<unknown>> = {
  "/guide": () => import("./Guide"),
  "/screen/entrance": () => import("./Screen"),
  "/planner": () => import("./Planner"),
};

const SURFACES = [
  { to: "/guide", n: "01", title: "Гид посетителя", text: "Телефон гостя: маршрут по зонам, факты с источником, заявка. Вход — QR или NFC у зоны." },
  { to: "/screen/entrance", n: "02", title: "Экран зоны", text: "Экран 16:9 в зале показывает маршрут гостя, который отсканировал зону." },
];

const AREA = factsJson.facts.find((f) => f.id === "area_production" && f.public);

/** Adds data-in to [data-reveal] elements once they scroll into view. */
function useReveal(root: React.RefObject<HTMLElement | null>) {
  useEffect(() => {
    const els = root.current?.querySelectorAll<HTMLElement>("[data-reveal]") ?? [];
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (!e.isIntersecting) continue;
          (e.target as HTMLElement).dataset.in = "";
          io.unobserve(e.target);
        }
      },
      { threshold: 0.2 },
    );
    els.forEach((el) => io.observe(el));
    return () => io.disconnect();
  }, [root]);
}

/** Counts from 0 to `to` once the element is visible. */
function CountUp({ to }: { to: number }) {
  const ref = useRef<HTMLSpanElement>(null);
  const [v, setV] = useState(0);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setV(to);
      return;
    }
    let raf = 0;
    const io = new IntersectionObserver(([e]) => {
      if (!e.isIntersecting) return;
      io.disconnect();
      const t0 = performance.now();
      const tick = (now: number) => {
        const k = Math.min(1, (now - t0) / 1600);
        setV(Math.round(to * (1 - Math.pow(1 - k, 4))));
        if (k < 1) raf = requestAnimationFrame(tick);
      };
      raf = requestAnimationFrame(tick);
    });
    io.observe(el);
    return () => {
      io.disconnect();
      cancelAnimationFrame(raf);
    };
  }, [to]);
  return <span ref={ref}>{v.toLocaleString("ru-RU")}</span>;
}

/** Card tilt and the light spot follow the pointer (CSS variables). */
function onCardMove(e: React.PointerEvent<HTMLAnchorElement>) {
  const r = e.currentTarget.getBoundingClientRect();
  const x = (e.clientX - r.left) / r.width;
  const y = (e.clientY - r.top) / r.height;
  e.currentTarget.style.setProperty("--mx", `${x * 100}%`);
  e.currentTarget.style.setProperty("--my", `${y * 100}%`);
  e.currentTarget.style.setProperty("--rx", `${(0.5 - y) * 6}deg`);
  e.currentTarget.style.setProperty("--ry", `${(x - 0.5) * 8}deg`);
}

function onCardLeave(e: React.PointerEvent<HTMLAnchorElement>) {
  e.currentTarget.style.setProperty("--rx", "0deg");
  e.currentTarget.style.setProperty("--ry", "0deg");
}

// Final flythrough v5 (#464): the first thing a visitor sees. Three parts under the 5 MB git limit, played in a row
// and looped; the button restarts from part 1 in full screen.
const FILM = ["/renders/video/flythrough_v5_1.mp4", "/renders/video/flythrough_v5_2.mp4", "/renders/video/flythrough_v5_3.mp4"];
const FILM_POSTER = "/renders/video/flythrough_v5.webp";

function FilmHero() {
  const video = useRef<HTMLVideoElement>(null);
  const [part, setPart] = useState(0);
  function next() {
    setPart((p) => (p + 1) % FILM.length);
  }
  function watch() {
    const v = video.current;
    if (!v) return;
    setPart(0);
    v.controls = true;
    void v.requestFullscreen?.().catch(() => undefined);
  }
  return (
    <section className={styles.film} aria-label="Пролёт по шоуруму ЛАССАРД">
      <video
        ref={video}
        className={styles.filmVideo}
        src={FILM[part]}
        poster={FILM_POSTER}
        autoPlay
        muted
        playsInline
        onEnded={next}
        preload="auto"
      />
      <div className={styles.filmCaption}>
        <p className={styles.filmKicker}>Пролёт по залу 219 · 1:42</p>
        <h2 className={styles.filmTitle}>Шоурум ЛАССАРД целиком</h2>
        <button type="button" className={styles.filmButton} onClick={watch}>
          <span aria-hidden="true">▶</span> Смотреть с начала
        </button>
      </div>
    </section>
  );
}

// Static gallery from web/public/renders/, outside the SPA router.
const RENDERS = "/renders/index.html";

export function Home() {
  const [build, setBuild] = useState("сборка: …");
  const [scrolled, setScrolled] = useState(false);
  const page = useRef<HTMLDivElement>(null);
  const hero = useRef<HTMLElement>(null);
  useReveal(page);
  useEffect(() => {
    void laserReveal();
    getHealth()
      .then((h) => setBuild(buildLabel(h)))
      .catch((e: unknown) => setBuild(`API недоступен: ${String(e)}`));
    const onScroll = () => setScrolled(window.scrollY > 24);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <div className={styles.page} ref={page}>
      <header className={styles.bar} data-scrolled={scrolled}>
        <Logo />
      </header>

      <FilmHero />

      <section className={styles.hero} ref={hero}>
        <div className={styles.backdrop} aria-hidden="true" />
        <LaserCanvas hero={hero} className={styles.canvas} />
        <div className={styles.heroText}>
          <p className={styles.kicker}>
            <span className={styles.dot} aria-hidden="true" />
            Рядом с цехом
          </p>
          <h1 className={styles.title}>
            <span className={styles.line}>
              <span>Шоурум</span>
            </span>{" "}
            <span className={styles.line}>
              <span className={styles.brand}>ЛАССАРД</span>
            </span>
          </h1>
          <p className={styles.lead}>
            История и масштаб → оборудование → тест на образце гостя → сделка. Гость идёт по маршруту со своим телефоном.
          </p>
          <div className={styles.actions}>
            <LaserLink className={styles.primary} to="/guide" preload={PRELOAD["/guide"]}>
              <span>Открыть гид</span>
              <span aria-hidden="true">→</span>
            </LaserLink>
            <LaserLink className={styles.ghost} to="/planner" preload={PRELOAD["/planner"]}>
              План зала в 3D
            </LaserLink>
            <a className={styles.ghost} href={RENDERS}>
              Рендеры зала
            </a>
          </div>
        </div>
        <span className={styles.scrollCue} aria-hidden="true" />
      </section>

      <main>
        <section className={styles.route} aria-labelledby="route-h">
          <div className={styles.wrap}>
            <p className={styles.eyebrow} data-reveal>
              Путь клиента
            </p>
            <h2 id="route-h" className={styles.h2} data-reveal>
              Четыре шага от входа до сделки
            </h2>
            <ol className={styles.steps} data-reveal>
              {ROUTE.map((s, i) => (
                <li key={s.n} className={styles.step} style={{ "--i": i } as React.CSSProperties}>
                  <span className={styles.stepNode} aria-hidden="true" />
                  <span className={styles.stepN}>{s.n}</span>
                  <h3 className={styles.stepTitle}>{s.title}</h3>
                  <p className={styles.stepText}>{s.text}</p>
                </li>
              ))}
            </ol>
          </div>
        </section>

        {AREA?.public && (
          <section className={styles.fact} aria-label="Масштаб производства">
            <div className={styles.wrap} data-reveal>
              <p className={styles.factValue}>
                <CountUp to={AREA.value} />
                <span className={styles.factUnit}>{AREA.unit}</span>
              </p>
              <p className={styles.factText}>производственных площадей.</p>
            </div>
          </section>
        )}

        <section className={styles.surfaces} aria-labelledby="surfaces-h">
          <div className={styles.wrap}>
            <p className={styles.eyebrow} data-reveal>
              Продукт
            </p>
            <h2 id="surfaces-h" className={styles.h2} data-reveal>
              Части продукта
            </h2>
            <ul className={styles.tiles}>
              {SURFACES.map((s, i) => (
                <li key={s.to} data-reveal style={{ "--i": i } as React.CSSProperties}>
                  <LaserLink className={styles.tile} to={s.to} preload={PRELOAD[s.to]} onPointerMove={onCardMove} onPointerLeave={onCardLeave}>
                    <span className={styles.tileN}>{s.n}</span>
                    <span className={styles.tileTitle}>{s.title}</span>
                    <span className={styles.tileText}>{s.text}</span>
                    <span className={styles.tileMore} aria-hidden="true">
                      Открыть <span>→</span>
                    </span>
                  </LaserLink>
                </li>
              ))}
            </ul>
          </div>
        </section>
      </main>

      <footer className={styles.footer}>
        <p role="status">{build}</p>
      </footer>
    </div>
  );
}
