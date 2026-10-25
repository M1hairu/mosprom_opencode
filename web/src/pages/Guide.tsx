import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router";
import { render, routeFacts, SITE_ID, sourceName, stops, type Route, type Site, type Stop, useSite } from "../guide/site";
import styles from "../guide/guide.module.css";
import { exhibitPhoto, zoneView } from "../guide/photos";
import { HallMap } from "../guide/HallMap";
import { registerServiceWorker } from "../guide/sw";
import { flush, pending, readState, writeState, type Pending, type VisitState } from "../guide/visit";
import { Button, Card, PageTitle, useOnline, type Tab } from "../ui/components";
import { IconAsk, IconMap, IconRequest, IconRoute } from "../ui/icons";
import { PhoneShell } from "../ui/shells";
import { ZoneStory } from "../guide/ZoneStory";

// Tab set of the guide (#29): to remove a tab, delete its line.
const TABS = [
  { id: "route", label: "Маршрут", icon: <IconRoute /> },
  { id: "map", label: "Карта", icon: <IconMap /> },
  { id: "ask", label: "Спросить", icon: <IconAsk /> },
  { id: "request", label: "Заявка", icon: <IconRequest /> },
] as const satisfies readonly Tab[];

type TabId = (typeof TABS)[number]["id"];

// One route for every guest (#353): the client path from the entrance to the test on the sample.
const ROLE = "prospect";

/** The visit in localStorage plus the queue sender: one send at a time, new events are kept. */
function useVisit(site: string) {
  const [state, setState] = useState<VisitState | null>(() => readState(site));
  const ref = useRef(state);
  const sending = useRef(false);

  const save = useCallback(
    (next: VisitState) => {
      ref.current = next;
      writeState(site, next);
      setState(next);
    },
    [site],
  );

  const sync = useCallback(async () => {
    const snapshot = ref.current;
    if (sending.current || !snapshot) return;
    sending.current = true;
    const result = await flush(site, snapshot);
    const tried = new Set(snapshot.queue.map((e) => e.client_event_id));
    const now = ref.current ?? snapshot;
    const added = now.queue.filter((e) => !tried.has(e.client_event_id));
    // A refused request (flush) changes lead; a new request made during the send stays.
    const lead = now.lead === snapshot.lead ? { lead: result.lead, leadFailed: result.leadFailed ?? now.leadFailed } : {};
    save({ ...now, ...lead, visitId: result.visitId, token: result.token, queue: [...result.queue, ...added] });
    sending.current = false;
    if (added.length > 0) void sync();
  }, [site, save]);

  const update = useCallback(
    (change: (s: VisitState | null) => VisitState) => {
      save(change(ref.current));
      void sync();
    },
    [save, sync],
  );

  useEffect(() => {
    void sync();
    const onOnline = () => void sync();
    window.addEventListener("online", onOnline);
    // navigator.onLine can be wrong: retry while something waits.
    const timer = setInterval(() => {
      const s = ref.current;
      if (s && (s.queue.length > 0 || !s.token)) void sync();
    }, 15_000);
    return () => {
      window.removeEventListener("online", onOnline);
      clearInterval(timer);
    };
  }, [sync]);

  return { state, update };
}

const enqueue = (s: VisitState, event: Pending): VisitState => ({ ...s, queue: [...s.queue, event] });

/** 1 зона, 2 зоны, 5 зон. */
function zonesWord(n: number): string {
  const [ten, one] = [n % 100, n % 10];
  if (ten >= 11 && ten <= 14) return `${n} зон`;
  return `${n} ${one === 1 ? "зона" : one >= 2 && one <= 4 ? "зоны" : "зон"}`;
}

export function Guide() {
  const params = useParams();
  const [search] = useSearchParams();
  const navigate = useNavigate();
  const site = params.site ?? search.get("site") ?? SITE_ID;
  const data = useSite();
  const { state, update } = useVisit(site);
  const [tab, setTab] = useState<TabId>("route");
  const handled = useRef(false);

  useEffect(() => registerServiceWorker(), []);

  const route = state ? data.routes.find((r) => r.role === ROLE) : undefined;
  const routeStops = useMemo(() => (route ? stops(route, data) : []), [route, data]);

  // Zone link of a QR code or an NFC tag: /z/<site>/<zone>?src=qr|nfc. The scan goes into the
  // stored visit, then the address becomes /guide: a reload does not send the scan again.
  useEffect(() => {
    if (handled.current || !params.zone) return;
    handled.current = true;
    const scan = { zone: params.zone, src: search.get("src") === "nfc" ? ("nfc" as const) : ("qr" as const) };
    update((s) => ({ ...(s ?? { role: ROLE, queue: [], stop: 0 }), scan }));
    navigate(`/guide?site=${encodeURIComponent(site)}`, { replace: true });
  }, [params.zone, search, update, navigate, site]);

  // A scan becomes an `arrive` event once the guest has a route; the card of the zone opens.
  useEffect(() => {
    const scan = state?.scan;
    if (!scan || !route || params.zone) return;
    update((s) => {
      const base = s ?? state;
      const index = stops(route, data).findIndex((st) => st.zone.id === scan.zone);
      return enqueue({ ...base, scan: undefined, stop: index >= 0 ? index : base.stop }, pending("arrive", scan.src, scan.zone));
    });
    setTab("route");
  }, [state, route, data, params.zone, update]);

  // The guest has no role choice: the first open starts the visit on the one route.
  useEffect(() => {
    if (!state || state.role !== ROLE) update((s) => ({ ...(s ?? { queue: [] }), role: ROLE, stop: 0 }));
  }, [state, update]);

  if (!state || !route) return <PhoneShell>{null}</PhoneShell>;

  const setStop = (stop: number) => update((s) => ({ ...(s ?? state), stop }));
  const current = Math.min(state.stop, routeStops.length - 1);

  return (
    <PhoneShell tabs={TABS} active={tab} onSelect={setTab}>
      {tab === "route" && (
        <RouteTab
          route={route}
          site={data}
          stops={routeStops}
          index={current}
          onIndex={setStop}
          onRequest={() => setTab("request")}
        />
      )}
      {tab === "map" && (
        <MapTab
          route={route}
          stops={routeStops}
          index={current}
          site={data}
          onOpen={(i) => {
            setStop(i);
            setTab("route");
          }}
        />
      )}
      {tab === "ask" && <AskTab route={route} site={data} />}
      {tab === "request" && (
        <RequestTab
          state={state}
          seen={routeStops.slice(0, current + 1)}
          onSend={() =>
            update((s) => {
              const event = pending("lead", "manual");
              return { ...enqueue(s ?? state, event), lead: event.client_event_id, leadFailed: undefined };
            })
          }
        />
      )}
    </PhoneShell>
  );
}

/** Graphite showcase of a zone: the 3D frame of the hall and the exhibit photo (white, red, graphite). */
function Showcase({ stop, kicker, site }: { stop: Stop; kicker: string; site: Site }) {
  const view = zoneView(stop.zone);
  const photo = exhibitPhoto(stop.zone);
  const name = photo && (site.items.find((i) => i.id === photo.id)?.name ?? photo.id);
  return (
    <section className={styles.showcase}>
      {view && <img className={styles.showcaseView} src={view} alt={`Зона «${stop.zone.name}» в концепте зала`} width={720} height={390} />}
      <div className={styles.showcaseText}>
        <p className={styles.kicker}>{kicker}</p>
        <h2>{stop.zone.name}</h2>
      </div>
      {photo && (
        <figure className={styles.exhibit}>
          <img src={photo.url} alt={name} width={88} height={88} loading="lazy" />
          <figcaption>
            <strong>{name}</strong>
            <span>Экспонат зоны</span>
          </figcaption>
        </figure>
      )}
    </section>
  );
}

function RouteTab({
  route,
  site,
  stops,
  index,
  onIndex,
  onRequest,
}: {
  route: Route;
  site: Site;
  stops: Stop[];
  index: number;
  onIndex: (i: number) => void;
  onRequest: () => void;
}) {
  const stop = stops[index];
  const last = index === stops.length - 1;
  return (
    <div className={styles.desk}>
      <PageTitle>Маршрут</PageTitle>
      <div className={styles.deskSide}>
        <Showcase stop={stop} site={site} kicker={`Зона ${index + 1} из ${stops.length} · около ${stop.minutes} мин`} />
        <div className={styles.nav}>
          <Button variant="secondary" data-film disabled={index === 0} onClick={() => onIndex(index - 1)}>
            Назад
          </Button>
          {last ? (
            <Button data-film onClick={onRequest}>К заявке</Button>
          ) : (
            <Button data-film onClick={() => onIndex(index + 1)}>Дальше</Button>
          )}
        </div>
      </div>
      <div className={styles.stop}>
        {stop.zone.status === "maintenance" && (
          <p className={styles.notice}>Зона на обслуживании. {stop.zone.maintenance?.replacement}</p>
        )}
        <ZoneStory key={stop.zone.id} stop={stop} site={site} />
      </div>
    </div>
  );
}

function MapTab({
  route,
  stops,
  index,
  site,
  onOpen,
}: {
  route: Route;
  stops: Stop[];
  index: number;
  site: Site;
  onOpen: (i: number) => void;
}) {
  const total = stops.reduce((sum, s) => sum + s.minutes, 0);
  return (
    <div className={styles.mapPage}>
      <PageTitle note={`${zonesWord(stops.length)} · около ${total} мин`}>Карта</PageTitle>
      <HallMap stops={stops} index={index} onOpen={onOpen} />
      <div>
        <ol className={styles.map}>
          {stops.map((s, i) => (
            <li key={`${s.zone.id}-${i}`}>
              <button type="button" data-film className={styles.mapItem} aria-current={i === index ? "step" : undefined} onClick={() => onOpen(i)}>
                <span className={styles.mapNum}>{i + 1}</span>
                <span className={styles.mapName}>{s.zone.name}</span>
                <span className={styles.meta}>{i < index ? "пройдена" : i === index ? "вы здесь" : `${s.minutes} мин`}</span>
              </button>
            </li>
          ))}
        </ol>
        {(route.skipped ?? []).length > 0 && (
          <Card title="Не на маршруте">
            {route.skipped!.map((s) => (
              <p key={s.zone}>
                <strong>{site.zones.find((z) => z.id === s.zone)?.name ?? s.zone}.</strong> {render(s.reason, site)}
              </p>
            ))}
          </Card>
        )}
      </div>
    </div>
  );
}

export function AskTab({ route, site }: { route: Route; site: Site }) {
  const facts = routeFacts(route, site);
  return (
    <>
      <PageTitle note="Задайте вопрос менеджеру рядом с вами. Числа маршрута — ниже, с источником.">Спросить</PageTitle>
      {facts.length === 0 ? (
        <Card>
          <p>У этого маршрута нет чисел. Спросите менеджера.</p>
        </Card>
      ) : (
        <ul className={styles.facts}>
          {facts.map((f) => (
            <li key={f.id}>
              <p className={styles.lead}>{f.text}</p>
              {f.case && (
                <p className={styles.meta}>
                  {f.public ? "Кейс ЛАССАРД" : "Источник: кейс ЛАССАРД"}, слайд {f.case.slide}
                  {f.check && " · уточняется"}
                </p>
              )}
              {f.public && (
                <p className={styles.meta}>
                  <a href={f.public.url} target="_blank" rel="noreferrer">
                    Источник: {sourceName(f.public.url)}
                  </a>
                  {f.case && f.public.value && ` — там: «${f.public.value}»`}
                  {!f.case && f.check && " · уточняется"}
                </p>
              )}
              {!f.case && !f.public && (
                <p className={styles.meta}>
                  Источник: нормы
                  {f.check && " · уточняется"}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

function RequestTab({ state, seen, onSend }: { state: VisitState; seen: Stop[]; onSend: () => void }) {
  const online = useOnline();
  const waiting = state.lead !== undefined && state.queue.some((e) => e.client_event_id === state.lead);
  return (
    <div className={styles.narrow}>
      <PageTitle note="Менеджер в зале обсудит тест на вашем образце.">Заявка</PageTitle>
      {state.lead ? (
        <Card title={waiting ? (online ? "Отправляем заявку" : "Заявка ждёт сеть") : "Заявка принята"}>
          <p role="status">
            {waiting
              ? online
                ? "Заявка записывается."
                : "Нет сети. Заявка уйдёт сама, когда сеть вернётся."
              : "Заявка записана. Покажите этот экран менеджеру в зале. Имя и телефон он запишет только с вашего согласия."}
          </p>
        </Card>
      ) : (
        <>
          {state.leadFailed && <p role="alert">Сервер не принял заявку. Покажите этот экран менеджеру в зале.</p>}
          <Card title="Вы посмотрели">
            <ul className={styles.seen}>
              {seen.map((s, i) => (
                <li key={`${s.zone.id}-${i}`}>{s.zone.name}</li>
              ))}
            </ul>
          </Card>
          <div className={styles.nav}>
            <Button wide onClick={onSend}>
              Оставить заявку
            </Button>
          </div>
        </>
      )}
    </div>
  );
}
