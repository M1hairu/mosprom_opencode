// /planner: plan of hall 219 in 3D (Three.js) with zones and exhibits.
// The 3D view fills the window under the bar (#353, #430): no 2D, no side panel, no title line.
import { lazy, Suspense, useEffect, useMemo, useState } from "react";
import type { PlanDocument } from "../planner/model";
import { buildScene } from "../planner/scene";
import { loadConceptPlan } from "../planner/source";
import styles from "../planner/planner.module.css";
import { DesktopShell } from "../ui/shells";

const Planner3D = lazy(() => import("../planner/Planner3D"));

const NO_HIGHLIGHT = new Map();

export function Planner() {
  const [plan, setPlan] = useState<PlanDocument | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadConceptPlan()
      .then(setPlan)
      .catch((e: unknown) => setError(`План не загружен: ${String(e)}`));
  }, []);

  const scene = useMemo(() => (plan ? buildScene(plan) : null), [plan]);

  return (
    <DesktopShell>
      <main className={styles.page}>
        {/* No visible title bar (#430): the 3D view starts right under the site bar. */}
        <h1 className={styles.hiddenTitle}>План зала в 3D</h1>
        {error && <p role="alert">{error}</p>}
        {scene && (
          <Suspense fallback={<p className={styles.notice}>Загрузка 3D…</p>}>
            <Planner3D scene={scene} highlight={NO_HIGHLIGHT} />
          </Suspense>
        )}
      </main>
    </DesktopShell>
  );
}
