// Layout shells of the surfaces: phone (/guide), zone screen 16:9 (/screen/:zone), desktop
// (/planner). A shell gives the frame; the page gives content.
import { useLayoutEffect, useRef, useSyncExternalStore, type ReactNode } from "react";
import { Link } from "react-router";
import { Logo, OfflineBanner, TabBar, type Tab } from "./components";
import styles from "./shells.module.css";

/** Logo as a link to the start page. */
function HomeLogo() {
  return (
    <Link to="/" className={styles.homeLink} aria-label="ЛАССАРД — на главную">
      <Logo />
    </Link>
  );
}

/** Red button to the start page at the right edge of every bar. */
function HomeButton() {
  return (
    <Link to="/" className={styles.homeButton}>
      На главную
    </Link>
  );
}

/** Phone of the visitor, 360–430 px: logo, content with its own scroll, tab bar at the bottom.
 *  Without tabs (the guide while it loads) there is no tab bar. */
// From this width the guide is a desktop page (#305): the tabs move from the bottom into the top bar.
const WIDE = "(min-width: 1024px)";

function useWide(): boolean {
  return useSyncExternalStore(
    (change) => {
      const query = window.matchMedia?.(WIDE);
      query?.addEventListener("change", change);
      return () => query?.removeEventListener("change", change);
    },
    () => window.matchMedia?.(WIDE).matches ?? false,
  );
}

export function PhoneShell<Id extends string>({
  tabs,
  active,
  onSelect,
  children,
}: {
  tabs?: readonly Tab<Id>[];
  active?: Id;
  onSelect?: (id: Id) => void;
  children: ReactNode;
}) {
  // The new tab slides in from the side of its tab; the content starts at the top.
  const index = tabs && active ? tabs.findIndex((t) => t.id === active) : -1;
  const prev = useRef(index);
  // The direction holds while the tab stays: a re-render must not cut the slide short.
  const dir = useRef<"none" | "next" | "back">("none");
  if (index !== prev.current) dir.current = index > prev.current ? "next" : "back";
  const main = useRef<HTMLElement>(null);
  useLayoutEffect(() => {
    if (prev.current !== index && main.current) main.current.scrollTop = 0;
    prev.current = index;
  }, [index]);
  const wide = useWide();
  const tabBar = tabs && active && onSelect && <TabBar tabs={tabs} active={active} onSelect={onSelect} />;
  return (
    <div className={styles.phone}>
      <header className={styles.phoneBar}>
        <HomeLogo />
        {wide && tabBar && <div className={styles.phoneTabs}>{tabBar}</div>}
        <HomeButton />
      </header>
      <OfflineBanner />
      <main className={styles.phoneMain} ref={main}>
        <div key={active ?? ""} className={styles.phonePane} data-dir={dir.current}>
          {children}
        </div>
      </main>
      {!wide && tabBar}
    </div>
  );
}

/** Zone screen 16:9 in the hall: no scroll, sizes follow the viewport height. */
export function ScreenShell({ zone, children }: { zone: ReactNode; children: ReactNode }) {
  return (
    <div className={styles.screen}>
      <header className={styles.screenBar}>
        <HomeLogo />
        <span className={styles.screenZone}>{zone}</span>
        <HomeButton />
      </header>
      <OfflineBanner text="Нет сети. Экран показывает последнее загруженное содержание." />
      <main className={styles.screenMain}>{children}</main>
      <footer className={styles.screenLines} aria-hidden="true" />
      {/* Watermark (p. 31): opacity 40 % or less. */}
      <span className={styles.watermark} aria-hidden="true">
        LASSARD
      </span>
    </div>
  );
}

/** Desktop: top bar; the page fills the rest of the window. */
export function DesktopShell({ children }: { children: ReactNode }) {
  return (
    <div className={styles.desktop}>
      <header className={styles.bar}>
        <HomeLogo />
        <HomeButton />
      </header>
      <OfflineBanner />
      <div className={styles.desktopMain}>{children}</div>
    </div>
  );
}
