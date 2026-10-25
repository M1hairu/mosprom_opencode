// Visit of the guest and the offline queue of events (#29, #55).
//
// The guest is anonymous: the visit token is the only identity (D-008). Events wait in
// localStorage until the network is back; client_event_id makes a resend safe.
import type { EventIn, VisitCreated } from "../contracts";

export type Pending = Omit<EventIn, "visit_token">;

export type VisitState = {
  role: string;
  visitId?: string;
  token?: string;
  queue: Pending[];
  /** Index of the open route card. */
  stop: number;
  /** client_event_id of the sent request (event `lead`). */
  lead?: string;
  /** The server refused the request (4xx): the guest sees it, not «принята». */
  leadFailed?: boolean;
  /** Zone scan that waits for the role answer. */
  scan?: { zone: string; src: "qr" | "nfc" };
};

const key = (site: string) => `lassard.guide.${site}`;

export function readState(site: string): VisitState | null {
  try {
    const raw = localStorage.getItem(key(site));
    return raw ? (JSON.parse(raw) as VisitState) : null;
  } catch {
    return null;
  }
}

export function writeState(site: string, state: VisitState): void {
  try {
    localStorage.setItem(key(site), JSON.stringify(state));
  } catch {
    // Private mode or full storage: the visit lives only in memory.
  }
}

/** Works without a secure context too: crypto.randomUUID needs HTTPS, a phone on LAN may not have it. */
export function eventId(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

export function pending(kind: Pending["kind"], src: Pending["src"], zone?: string): Pending {
  return { kind, src, zone_id: zone ?? null, client_event_id: eventId(), occurred_at: new Date().toISOString() };
}

async function post(url: string, body: unknown): Promise<Response> {
  // A hung request on weak Wi-Fi must not hold the queue: after 10 s it counts as no network.
  return fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    // Safari before 16 has no AbortSignal.timeout: there the request simply has no timeout.
    signal: "timeout" in AbortSignal ? AbortSignal.timeout(10_000) : undefined,
  });
}

/**
 * Sends the queue in order: creates the visit first if it has no token yet.
 * Stops at the first network error or server error and keeps the rest for the next try.
 * Returns the new state; the caller saves it.
 */
export async function flush(site: string, state: VisitState): Promise<VisitState> {
  let next = { ...state, queue: [...state.queue] };
  try {
    if (!next.token) {
      if (!next.role) return next; // the role question is not answered yet
      const r = await post("/api/visits", { site_id: site, role: next.role });
      if (!r.ok) return next;
      const visit = (await r.json()) as VisitCreated;
      next = { ...next, visitId: visit.visit_id, token: visit.token };
    }
    while (next.queue.length > 0) {
      const r = await post("/api/events", { ...next.queue[0], visit_token: next.token });
      if (r.status === 404) {
        // The server lost the visit (database reset): a new visit takes the same queue.
        return flush(site, { ...next, visitId: undefined, token: undefined });
      }
      if (r.status >= 500) return next;
      // 2xx — written or a duplicate; 4xx — the server will never take it: drop it either way.
      if (!r.ok) {
        console.warn("event refused", r.status, next.queue[0].kind);
        if (next.queue[0].client_event_id === next.lead) next = { ...next, lead: undefined, leadFailed: true };
      }
      next = { ...next, queue: next.queue.slice(1) };
    }
  } catch {
    // No network: the queue waits.
  }
  return next;
}
