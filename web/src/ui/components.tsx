// Base components of all surfaces. Styles: ui.module.css on the tokens of tokens.css.
import { useSyncExternalStore, type ButtonHTMLAttributes, type ReactNode } from "react";
import logoUrl from "./logo-lassard.svg";
import styles from "./ui.module.css";

/** Brandbook p. 23: logo height on screens is at least 40 px (the arrow on the page is vertical). */
const LOGO_MIN_HEIGHT = 40;

/** Colour logo on a white background (brandbook p. 25). A smaller height is raised to the minimum. */
export function Logo({ height = LOGO_MIN_HEIGHT }: { height?: number }) {
  const h = Math.max(height, LOGO_MIN_HEIGHT);
  return <img className={styles.logo} src={logoUrl} alt="ЛАССАРД" height={h} width={Math.round(h * 4.1)} />;
}

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  /** primary — the one main action of the screen: red plate with a cut corner. */
  variant?: "primary" | "secondary";
  wide?: boolean;
};

export function Button({ variant = "primary", wide = false, className, type = "button", ...rest }: ButtonProps) {
  const cls = [styles.button, styles[variant], wide && styles.wide, className].filter(Boolean).join(" ");
  return <button type={type} className={cls} {...rest} />;
}

export function Card({ title, children }: { title?: ReactNode; children: ReactNode }) {
  return (
    <section className={styles.card}>
      {title && <h2 className={styles.cardTitle}>{title}</h2>}
      {children}
    </section>
  );
}

/** Page heading: h1 with the red skewed plate of the brandbook (p. 33). */
export function PageTitle({ children, note }: { children: ReactNode; note?: ReactNode }) {
  return (
    <header className={styles.title}>
      <h1>{children}</h1>
      {note && <p>{note}</p>}
    </header>
  );
}

export function EmptyState({ title, text, action }: { title: ReactNode; text?: ReactNode; action?: ReactNode }) {
  return (
    <div className={styles.empty}>
      <div className={styles.emptyMark} aria-hidden="true" />
      <p className={styles.emptyTitle}>{title}</p>
      {text && <p className={styles.emptyText}>{text}</p>}
      {action}
    </div>
  );
}

function subscribeOnline(onChange: () => void) {
  window.addEventListener("online", onChange);
  window.addEventListener("offline", onChange);
  return () => {
    window.removeEventListener("online", onChange);
    window.removeEventListener("offline", onChange);
  };
}

export function useOnline(): boolean {
  return useSyncExternalStore(subscribeOnline, () => navigator.onLine);
}

/** Shows only without network. The surface can give its own text. */
export function OfflineBanner({ text = "Нет сети. Проверьте подключение к Wi-Fi шоурума." }: { text?: string }) {
  const online = useOnline();
  if (online) return null;
  return (
    <p className={styles.offline} role="status">
      {text}
    </p>
  );
}

export type Tab<Id extends string = string> = { id: Id; label: string; icon: ReactNode };

/** More than 5 tabs do not fit 360 px with a label under each icon. */
export const MAX_TABS = 5;

/** Bottom tab bar of the phone: icon with a label, up to 5 items. */
export function TabBar<Id extends string>({
  tabs,
  active,
  onSelect,
}: {
  tabs: readonly Tab<Id>[];
  active: Id;
  onSelect: (id: Id) => void;
}) {
  if (tabs.length > MAX_TABS) throw new Error(`TabBar: ${tabs.length} вкладок, допустимо не больше ${MAX_TABS}`);
  const index = Math.max(0, tabs.findIndex((t) => t.id === active));
  return (
    <nav className={styles.tabbar} aria-label="Разделы">
      {/* One red plate slides to the active tab. */}
      <span className={styles.tabMarker} style={{ width: `${100 / tabs.length}%`, transform: `translateX(${index * 100}%)` }} aria-hidden="true" />
      {tabs.map((t) => (
        <button
          key={t.id}
          type="button"
          className={styles.tab}
          aria-current={t.id === active ? "page" : undefined}
          onClick={() => {
            onSelect(t.id);
          }}
        >
          <span className={styles.tabIcon} aria-hidden="true">
            {t.icon}
          </span>
          <span className={styles.tabLabel}>{t.label}</span>
        </button>
      ))}
    </nav>
  );
}
