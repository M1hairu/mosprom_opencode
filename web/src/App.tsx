import { BrowserRouter, Link, Route, Routes } from "react-router";
import { Component, lazy, Suspense, type ReactNode } from "react";
import { OpticCut } from "./ui/OpticCut";

// Each surface is a separate build chunk: the guide on a phone loads only its own code.
// Declarative mode of react-router: the data router adds ~18 KB gzip to the guide budget.
const SURFACES = [
  { path: "/guide", Page: lazy(() => import("./pages/Guide").then((m) => ({ default: m.Guide }))) },
  // Zone link of a QR code or an NFC tag (backend/src/api/visits.py): opens the guide with a scan.
  { path: "/z/:site/:zone", Page: lazy(() => import("./pages/Guide").then((m) => ({ default: m.Guide }))) },
  { path: "/screen/:zone", Page: lazy(() => import("./pages/Screen").then((m) => ({ default: m.Screen }))) },
  { path: "/planner", Page: lazy(() => import("./pages/Planner").then((m) => ({ default: m.Planner }))) },
];

// Start page of make demo: what the product is, the surfaces, the build commit.
const Home = lazy(() => import("./pages/Home").then((m) => ({ default: m.Home })));

function NotFound() {
  return (
    <main>
      <h1>Страница не найдена</h1>
      <Link to="/">На главную</Link>
    </main>
  );
}

/** A failed chunk or a render error must not leave a blank page. */
class ErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  componentDidCatch(error: unknown) {
    console.error("page failed", error);
  }
  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <main>
        <h1>Страница не загрузилась</h1>
        <button onClick={() => location.reload()}>Обновить</button>
      </main>
    );
  }
}

export function App() {
  return (
    <BrowserRouter>
      <OpticCut />
      <ErrorBoundary>
      <Suspense>
        <Routes>
          <Route path="/" element={<Home />} />
          {SURFACES.map(({ path, Page }) => (
            <Route key={path} path={path} element={<Page />} />
          ))}
          <Route path="*" element={<NotFound />} />
        </Routes>
      </Suspense>
      </ErrorBoundary>
    </BrowserRouter>
  );
}
