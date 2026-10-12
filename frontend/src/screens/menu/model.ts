// What the admin menu API sends and takes (src/kiosk/api/routers/admin_menu.py), and small helpers.
import type { Text } from "../../lib/types";

export type { Text };
export type Win = { days: number[]; start: string; end: string };
export type AdminCategory = { id: string; name: Text; sort: number; windows: Win[]; is_active: boolean };
export type AdminModifier = { id?: string; name: Text; price_delta: number; sort?: number; is_active?: boolean };
export type AdminGroup = { id?: string; name: Text; min_select: number; max_select: number; sort?: number; modifiers: AdminModifier[] };
export type AdminSlot = { name: Text; item_ids: string[]; upcharges: Record<string, number> };
export type AdminItem = {
  id: string;
  category_id: string;
  name: Text;
  description: Text;
  price: number;
  external_code: string | null;
  station: string;
  prep_minutes: number | null;
  tax_category: string;
  allergens: string[];
  image_url: string | null;
  windows: Win[];
  sort: number;
  is_active: boolean;
  is_available: boolean;
  combo_slots: AdminSlot[];
  suggest_ids: string[];
  modifier_groups: AdminGroup[];
};
export type TaxRule = {
  id: string;
  code: string;
  name: Text;
  rate_bp: number;
  applies_to: string[];
  compound: boolean;
  sequence: number;
  effective_from: string;
  effective_to: string | null;
  is_active: boolean;
};

export const LANGS = [
  ["en", "English"],
  ["si", "සිංහල"],
  ["ta", "தமிழ்"],
] as const;
export type Lang = (typeof LANGS)[number][0];
export const ALLERGENS = ["gluten", "egg", "milk", "soy", "nuts", "peanuts", "fish", "shellfish", "sesame"];
export const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
export const TAX_CATEGORIES = ["food", "beverage", "alcohol", "retail"];
export const SAVED = "Saved. Every screen shows the change now";

const COLORS = ["#c8102e", "#d97706", "#15803d", "#0e7490", "#7c3aed", "#be185d", "#4d7c0f", "#b45309", "#1d4ed8"];
export const tileColor = (id: string) => COLORS[[...id].reduce((n, ch) => (n * 31 + ch.charCodeAt(0)) >>> 0, 0) % COLORS.length];

/** Cents to a plain "450.00" for a number input. */
export const rupees = (cents: number | null | undefined) => (Number(cents || 0) / 100).toFixed(2);

/** Keep only filled-in languages; the API needs English. */
export const cleanText = (t: Text): Text => Object.fromEntries(Object.entries(t).map(([k, v]) => [k, (v ?? "").trim()]).filter(([, v]) => v)) as Text;

let seq = 0;
export const newKey = () => `k${++seq}`;

/** Dates are shown and entered in the venue's own time zone (YYYY-MM-DD). */
export const localDate = (iso: string, tz: string) => new Date(iso).toLocaleDateString("en-CA", { timeZone: tz });
export function tzOffset(tz: string): string {
  const part = new Intl.DateTimeFormat("en-US", { timeZone: tz, timeZoneName: "longOffset" }).formatToParts(new Date()).find((x) => x.type === "timeZoneName");
  const off = (part?.value || "GMT+05:30").replace("GMT", "");
  return off === "" ? "+00:00" : off;
}

export const windowLabel = (w: Win) => {
  const days = [...w.days].sort();
  const d = days.length === 7 ? "" : `${days.map((i) => DAYS[i]).join(" ")} `;
  return `${d}${w.start}–${w.end}`;
};
