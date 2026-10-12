// Clean addresses, one place: every restaurant has its own path, e.g. /demo/pos, /demo/kitchen,
// /demo/owner. Our team's console is /platform and a tablet's start page is /.
// Table screens are the Android app (/demo/table only explains that).

/** Device type -> the screen's name in the address. */
export const SCREEN_SLUG: Record<string, string> = { cashier: "pos", waiter: "waiter", kds: "kitchen", kiosk: "kiosk", status: "board", table: "table", board: "table" };
export const SCREEN_NAME: Record<string, string> = { cashier: "POS", waiter: "Waiter app", kds: "Kitchen display", kiosk: "Self-order kiosk", status: "Order status board", table: "Table screen", board: "Menu board" };
export const LAUNCH_KEY = "kiosk:launch";

const codePart = (code?: string | null) => (code ? `/${code.toLowerCase()}` : "");

/** A screen's address: /{code}/{screen}, plus ?slot= when one browser runs several screens. */
export function screenAddress(type: string, slot = "main", code?: string | null): string {
  const base = `${codePart(code)}/${SCREEN_SLUG[type] ?? type}`;
  return slot && slot !== "main" ? `${base}?slot=${encodeURIComponent(slot)}` : base;
}

/** Without a code, for links that only know the type (the screen adds its code by itself). */
export const SCREEN_URL: Record<string, string> = Object.fromEntries(Object.entries(SCREEN_SLUG).map(([t, s]) => [t, `/${s}`]));

/** A restaurant console: owner, menu, setup, wall. */
export const consoleUrl = (page: "owner" | "menu" | "setup" | "wall", code?: string | null): string => `${codePart(code)}/${page}`;

/** The restaurant code in this page's address (/demo/pos -> "demo"), if any. */
export function codeInAddress(): string | null {
  const parts = location.pathname.split("/").filter(Boolean);
  return parts.length >= 2 ? parts[0].toLowerCase() : null;
}

/** Put the restaurant's code into the address bar (keeps ?slot= and the rest). */
export function showCodeInAddress(code: string, screen: string): void {
  const want = `/${code.toLowerCase()}/${screen}`;
  if (location.pathname !== want) history.replaceState(history.state, "", want + location.search + location.hash);
}
