import type { Health } from "./contracts";

// Short commit for people; the suffix -dirty (uncommitted changes) stays visible.
export function buildLabel(h: Health): string {
  const [commit, ...rest] = h.sha.split("-");
  const short = /^[0-9a-f]{40}$/.test(commit) ? commit.slice(0, 7) : commit;
  return `сборка ${[short, ...rest].join("-")}`;
}
