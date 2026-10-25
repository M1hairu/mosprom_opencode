import type { Health } from "./contracts";

export async function getHealth(): Promise<Health> {
  const r = await fetch("/api/health");
  if (!r.ok) throw new Error(`API ${r.status}`);
  return (await r.json()) as Health;
}
