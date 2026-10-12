import { inputCls as kitInput } from "../../ui/kit";

// Types and small helpers for the package catalogue (GET /v1/platform/catalog) and quotes.

export type Module = { code: string; name: string; kind: "required" | "optional" | "recommended"; device_type: string | null; hotel: boolean };
export type TierInfo = { screens: Record<string, number>; modules: string[]; addons: string[] };
export type Flow = {
  code: string;
  name: string;
  about: string;
  screens: Record<string, number>;
  modules: string[];
  hardware: Record<string, number>;
  settings: Record<string, unknown>;
  needs: string[];
  group: "core" | "more" | "hidden";
};
export type Catalog = {
  modules: Module[];
  packs: Record<string, { name: string; tiers: Record<string, TierInfo> }>;
  hardware: Record<string, string>;
  flows: Flow[];
};

export type Plan = {
  pack: string;
  tier: string | null;
  modules: string[];
  screens: Record<string, number>;
  hardware: Record<string, number>;
  requirements: { item: string; min: number; reasons: string[] }[];
  flows: string[];
  settings: Record<string, unknown>;
  warnings: string[];
};
export type QuoteLine = { item: string; name: string; qty: number; monthly: number; once: number };
export type Quote = { plan: Plan; lines: QuoteLine[]; monthly_total: number; once_total: number; missing_prices: string[] };

/** What the picker sends to /quote, /tenants (plan) and /venues/{id}/plan. */
export type PlanValue = { pack: string; tier?: string; add?: string[]; modules?: string[]; screens: Record<string, number>; hardware: Record<string, number>; flows: string[] };

export type TenantVenue = {
  id: string;
  name: string;
  code: string;
  timezone: string;
  screens: number;
  screens_online: number;
  plan: Plan | null;
  setup: { done: number; total: number; ready: boolean };
};
export type Tenant = { id: string; name: string; created_at: string; venues: TenantVenue[]; admins: { email: string; role: string; is_active: boolean }[] };

export const SCREEN_LABEL: Record<string, string> = {
  table: "Table screens",
  kiosk: "Self-order kiosks",
  cashier: "POS (cashier) screens",
  kds: "Kitchen displays",
  status: "Status boards",
  waiter: "Waiter apps",
  board: "Overhead menu boards",
  room: "Room kiosks",
};
export const PRICED_SCREENS = ["table", "kiosk", "cashier", "kds", "status", "waiter", "board", "room"];
/** Not offered any more (waiter handhelds as an add-on, menu boards) or not built yet (voice). */
export const HIDDEN_MODULES = ["R-BOARD", "R-VOICE"];
export const isCustom = (pack: string) => pack === "custom" || pack === "hotel";
export const cap = (s: string) => (s ? s[0].toUpperCase() + s.slice(1) : s);

/** The UI says "QR payment" (the API and module codes keep LankaQR). */
export const say = (s: string) => s.replace(/LankaQR/g, "QR payment");

export function planLabel(plan: Plan | null | undefined, catalog: Catalog): string {
  if (!plan) return "No package (unrestricted)";
  const pack = catalog.packs[plan.pack]?.name || plan.pack;
  return plan.tier ? `${pack} · ${cap(plan.tier)}` : pack;
}

export function randomPassword(): string {
  const a = new Uint32Array(3);
  crypto.getRandomValues(a);
  return [...a].map((x) => x.toString(36)).join("-").slice(0, 16);
}

export const inputCls = `${kitInput} disabled:bg-canvas`;
