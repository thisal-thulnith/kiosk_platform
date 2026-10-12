// What the platform offers right now. GET /v1/features -> { coming_soon: ["kiosk", "status"] }:
// screen types that are built but not offered yet (marked "Coming soon" in the consoles, and their
// screens show a coming-soon page). Fetched once per page; the last answer is kept for offline starts.
import { useEffect, useState } from "react";
import { request } from "./net";
import { store } from "./store";

export type Features = { coming_soon: string[]; demo?: boolean; app_url?: string | null; admin_url?: string | null };

const KEY = "kiosk:features";
let pending: Promise<Features> | null = null;
let known: Features | null = store.get<Features>(KEY);

/** The features (one request per page, shared by every caller). Offline: the last known answer. */
export function features(): Promise<Features> {
  pending ??= request<Features>("GET", "/v1/features")
    .then((f) => {
      known = { coming_soon: Array.isArray(f?.coming_soon) ? f.coming_soon : [], demo: f?.demo === true, app_url: f?.app_url ?? null, admin_url: f?.admin_url ?? null };
      store.set(KEY, known);
      return known;
    })
    .catch(() => known ?? { coming_soon: [] });
  return pending;
}

/** Is this screen type coming soon? (from the last known answer; call features() first to be sure) */
export const isComingSoon = (type: string): boolean => !!known?.coming_soon.includes(type);

/** The coming-soon screen types, for React: [] until loaded (then re-renders). */
export function useComingSoon(): string[] {
  const [list, setList] = useState<string[]>(known?.coming_soon ?? []);
  useEffect(() => {
    let on = true;
    void features().then((f) => on && setList(f.coming_soon));
    return () => void (on = false);
  }, []);
  return list;
}

/** Where restaurants' screens live (links and QR codes for tablets). Same address when not split. */
export const appOrigin = (): string => (known?.app_url || location.origin).replace(/\/$/, "");
/** Where our team's consoles live. */
export const adminOrigin = (): string => (known?.admin_url || location.origin).replace(/\/$/, "");
