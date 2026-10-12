// The restaurant's look: its main colour, logo and light / dark screens. Applied to the whole page
// (CSS variables), remembered so the next start shows the right colours before the server answers.
import { store } from "./store";

export type Brand = { color: string; logo_url: string | null; theme: "light" | "dark"; name?: string };
export const DEFAULT_BRAND: Brand = { color: "#f5a524", logo_url: null, theme: "light" };
const KEY = "kiosk:brand";

/** White or dark text on the brand colour, whichever reads better. */
export function textOn(hex: string): string {
  const n = parseInt(hex.slice(1), 16);
  const [r, g, b] = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map((c) => {
    const v = c / 255;
    return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
  });
  const lum = 0.2126 * r + 0.7152 * g + 0.0722 * b;
  return lum > 0.5 ? "#23201c" : "#ffffff";
}

export function applyBrand(b: Partial<Brand> | null | undefined, remember = true): Brand {
  const brand: Brand = { ...DEFAULT_BRAND, ...(b ?? {}) };
  if (!/^#[0-9a-f]{6}$/i.test(brand.color)) brand.color = DEFAULT_BRAND.color;
  const root = document.documentElement;
  root.style.setProperty("--color-brand", brand.color);
  root.style.setProperty("--color-on-brand", textOn(brand.color));
  root.dataset.theme = brand.theme === "dark" ? "dark" : "light";
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", brand.color);
  if (remember) store.set(KEY, brand);
  return brand;
}

/** Brand from an admin venue's settings (consoles). */
export const brandOf = (settings: Record<string, any> | undefined, name?: string): Brand => ({
  color: settings?.brand_color || DEFAULT_BRAND.color,
  logo_url: settings?.logo_url || null,
  theme: settings?.theme === "dark" ? "dark" : "light",
  name,
});

// On load: last known brand, so a restart opens in the restaurant's colours at once.
applyBrand(store.get<Brand>(KEY), false);
