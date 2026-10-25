import qrcode from "qrcode-generator";
import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router";
import type { ScreenMessage } from "../contracts";
import { exhibitPhoto, zoneRender, zoneView } from "../guide/photos";
import { render, SITE_ID, type Site, type Zone, useSite } from "../guide/site";
import { ScreenShell } from "../ui/shells";
import styles from "./screen.module.css";

/** Without a new scan the screen goes back to the splash after this time (#38, lead decision 3). */
export const IDLE_MS = 60_000;

/** Owner of the zone screen from SSE (#55): the latest scan wins; the stream reconnects by itself. */
function useScreen(site: string, zone: string) {
  const [message, setMessage] = useState<ScreenMessage | null>(null);
  const [connected, setConnected] = useState(true);
  useEffect(() => {
    const url = `/api/sites/${encodeURIComponent(site)}/zones/${encodeURIComponent(zone)}/stream`;
    let source: EventSource;
    let retry: ReturnType<typeof setTimeout> | undefined;
    const connect = () => {
      source = new EventSource(url);
      source.onopen = () => setConnected(true);
      source.onmessage = (e) => {
        setConnected(true);
        setMessage(JSON.parse(e.data) as ScreenMessage);
      };
      source.onerror = () => {
        setConnected(false);
        // A network break reconnects by itself; an error answer (502 during a deploy) closes the
        // stream for good, so the screen opens a new one.
        if (source.readyState === EventSource.CLOSED) retry = setTimeout(connect, 3000);
      };
    };
    connect();
    return () => {
      clearTimeout(retry);
      source.close();
    };
  }, [site, zone]);
  return { message, connected };
}

/** True while the scan is younger than IDLE_MS. An old scan (an offline queue sent late) shows the splash. */
function useFresh(since: string | null | undefined): boolean {
  const [fresh, setFresh] = useState(false);
  useEffect(() => {
    if (!since) {
      setFresh(false);
      return;
    }
    const left = IDLE_MS - (Date.now() - Math.min(Date.parse(since), Date.now()));
    setFresh(left > 0);
    if (left <= 0) return;
    const timer = setTimeout(() => setFresh(false), left);
    return () => clearTimeout(timer);
  }, [since]);
  return fresh;
}

export function Screen() {
  const { zone: zoneId = "" } = useParams();
  const site = useSite();
  const zone: Zone = site.zones.find((z) => z.id === zoneId) ?? { id: zoneId, name: zoneId };
  const { message, connected } = useScreen(SITE_ID, zoneId);
  const fresh = useFresh(message?.since);
  const guest = connected && fresh && message?.visit_id && message.role ? message.role : null;

  return (
    <ScreenShell zone={zone.name}>
      {guest ? <GuestContent site={site} zone={zone} role={guest} /> : <Splash site={site} zone={zone} />}
      {!connected && (
        <p className={styles.status} role="status">
          Нет связи с сервером. Экран переподключается сам.
        </p>
      )}
    </ScreenShell>
  );
}

/** Kiosk picture of the zone: the big render, then the small guide view if it fails, then nothing. */
function ZonePicture({ zone, className }: { zone: Zone; className: string }) {
  const [failed, setFailed] = useState(0);
  const src = [zoneRender(zone), zoneView(zone)].filter((u): u is string => !!u)[failed];
  if (!src) return null;
  return <img className={className} src={src} alt="" onError={() => setFailed((n) => n + 1)} />;
}

/** Splash: the zone, its key phrase and the QR code that opens the guide on this zone. */
function Splash({ site, zone }: { site: Site; zone: Zone }) {
  const url = `${location.origin}/z/${SITE_ID}/${zone.id}?src=qr`;
  return (
    <div className={styles.layout}>
      <ZonePicture key={zone.id} zone={zone} className={styles.backdrop} />
      <div className={styles.scrim} />
      <div className={styles.text}>
        <p className={styles.kicker}>Шоурум ЛАССАРД</p>
        <h1>{zone.name}</h1>
        {zone.messages?.[0] && <p className={styles.lead}>{render(zone.messages[0], site, true)}</p>}
      </div>
      <figure className={styles.qr}>
        <QrCode text={url} />
        <figcaption>Наведите камеру телефона — гид откроет маршрут по этой зоне</figcaption>
      </figure>
    </div>
  );
}

/** Content for the role of the guest who scanned the zone last. */
function GuestContent({ site, zone, role }: { site: Site; zone: Zone; role: string }) {
  const route = site.routes.find((r) => r.role === role);
  const steps = (route?.steps ?? []).filter((s) => s.zone === zone.id).map((s) => render(s.message, site, true));
  const lines = steps.length > 0 ? steps : (zone.messages ?? []).map((m) => render(m, site, true));
  const photo = exhibitPhoto(zone);
  return (
    <div className={styles.layout}>
      <ZonePicture key={zone.id} zone={zone} className={styles.backdrop} />
      <div className={styles.scrim} />
      <div className={styles.text}>
        <p className={styles.kicker}>{route ? "Маршрут гостя" : "Гость у зоны"}</p>
        <h1>{zone.name}</h1>
        <ul className={styles.lines}>
          {lines.map((line, i) => (
            <li key={i}>{line}</li>
          ))}
        </ul>
      </div>
      {photo && <img className={styles.photo} src={photo.url} alt={site.items.find((i) => i.id === photo.id)?.name ?? ""} />}
    </div>
  );
}

function QrCode({ text }: { text: string }) {
  const path = useMemo(() => {
    const qr = qrcode(0, "M");
    qr.addData(text);
    qr.make();
    const n = qr.getModuleCount();
    let d = "";
    for (let r = 0; r < n; r++) for (let c = 0; c < n; c++) if (qr.isDark(r, c)) d += `M${c} ${r}h1v1h-1z`;
    return { d, n };
  }, [text]);
  return (
    <svg className={styles.qrCode} viewBox={`-2 -2 ${path.n + 4} ${path.n + 4}`} role="img" aria-label={`QR-код: ${text}`}>
      <rect x="-2" y="-2" width={path.n + 4} height={path.n + 4} fill="#fff" />
      <path d={path.d} fill="#26262e" />
    </svg>
  );
}
