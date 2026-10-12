// The restaurant's look: main colour, logo and light / dark screens, with a live preview. Used in the
// Setup console (Restaurant step) and the Owner app (Look tab). Every screen picks it up on its next
// load; the console itself changes at once.
import { useRef, useState, type CSSProperties, type ReactNode } from "react";
import type { Admin, Venue } from "../lib/admin";
import { applyBrand, brandOf, textOn } from "../lib/brand";
import { money } from "../lib/format";
import { net } from "../lib/net";
import { Dish } from "./food";
import { Check, ImageUp, Moon, Plus, Sun } from "lucide-react";
import { Button, Card, Segmented, inputCls, useToast } from "./kit";
import { Logo } from "./logo";

export const SWATCHES: [string, string][] = [
  ["Amber", "#f5a524"],
  ["Tomato", "#ef4444"],
  ["Orange", "#f97316"],
  ["Emerald", "#10b981"],
  ["Teal", "#0f766e"],
  ["Sky", "#0ea5e9"],
  ["Indigo", "#6366f1"],
  ["Plum", "#a21caf"],
  ["Coffee", "#92400e"],
  ["Charcoal", "#334155"],
];
const HEX = /^#[0-9a-f]{6}$/i;
type Theme = "light" | "dark";

/** CSS variables that make everything inside wear this colour (and dark screens), like the real screens. */
function previewVars(color: string, theme: Theme): CSSProperties {
  const dark = theme === "dark";
  const surface = dark ? "#242526" : "#ffffff"; // the same light / dark tokens as theme.css
  return {
    "--color-brand": color,
    "--color-on-brand": textOn(color),
    "--color-brand-dark": `color-mix(in oklab, ${color} 82%, black)`,
    "--color-brand-soft": `color-mix(in oklab, ${color} 14%, ${surface})`,
    "--color-ink": dark ? "#e4e6eb" : "#1c2b33",
    "--color-muted": dark ? "#b0b3b8" : "#65676b",
    "--color-line": dark ? "#3a3b3c" : "#e4e6eb",
    "--color-canvas": dark ? "#18191a" : "#f0f2f5",
    "--color-surface": surface,
    colorScheme: theme,
  } as CSSProperties;
}

export function BrandEditor({ admin, onSaved, className = "" }: { admin: Admin; onSaved?: (v: Venue) => void; className?: string }) {
  const toast = useToast();
  const venue = admin.venue!;
  const start = brandOf(venue.settings, venue.name);
  const [color, setColor] = useState(start.color);
  const [hex, setHex] = useState(start.color);
  const [logo, setLogo] = useState<string | null>(start.logo_url);
  const [theme, setTheme] = useState<Theme>(start.theme);
  const [saved, setSaved] = useState({ color: start.color, logo: start.logo_url, theme: start.theme });
  const [busy, setBusy] = useState<"upload" | "save" | null>(null);
  const file = useRef<HTMLInputElement>(null);
  const dirty = color !== saved.color || logo !== saved.logo || theme !== saved.theme;

  const pick = (c: string) => (setColor(c.toLowerCase()), setHex(c.toLowerCase()));
  const typed = (v: string) => {
    const t = v.startsWith("#") ? v : `#${v}`;
    setHex(t);
    if (HEX.test(t)) setColor(t.toLowerCase());
  };

  const upload = async (f: File | undefined) => {
    if (!f) return;
    if (f.size > 5 * 1024 * 1024) return toast("The logo must be 5 MB or smaller.", "bad");
    setBusy("upload");
    try {
      const res = await fetch(net.base() + admin.v("/media"), { method: "POST", headers: { ...admin.headers(), "Content-Type": f.type }, body: f });
      const data = await res.json().catch(() => null);
      if (!res.ok) throw new Error(data?.error?.message || "Upload failed");
      setLogo(data.url);
      toast("Logo uploaded. Press Save to use it.", "info");
    } catch (x) {
      toast((x as Error).message, "bad", 6000);
    } finally {
      setBusy(null);
      if (file.current) file.current.value = "";
    }
  };

  const save = async () => {
    if (!HEX.test(color)) return toast("Pick a colour like #f5a524.", "bad");
    setBusy("save");
    try {
      const v = await admin.api<Venue>("PATCH", admin.v(""), { settings: { brand_color: color, logo_url: logo ?? "", theme } });
      admin.venue = v;
      applyBrand(brandOf(v.settings, v.name), false);
      setSaved({ color, logo, theme });
      toast("Saved. Every screen shows the new look now", "ok");
      onSaved?.(v);
    } catch (x) {
      toast((x as Error).message, "bad", 6000);
    } finally {
      setBusy(null);
    }
  };
  const undo = () => (pick(saved.color), setLogo(saved.logo), setTheme(saved.theme));
  const custom = !SWATCHES.some(([, c]) => c === color);

  return (
    <Card className={`brand-editor @container flex flex-col gap-0 p-0! ${className}`}>
      <div className="grid @4xl:grid-cols-[minmax(0,1fr)_360px] @6xl:grid-cols-[minmax(0,1fr)_440px]">
        <div className="flex min-w-0 flex-col">
          <div className="px-5 pb-4 pt-5">
            <h2 className="text-lg font-bold tracking-[-0.01em]">Look &amp; logo</h2>
            <p className="text-sm text-muted">Your colour and logo on every screen: kiosk, tables, POS, kitchen and receipts.</p>
          </div>

          <Setting title="Main colour" hint="Buttons and highlights on the guests' screens.">
            <div className="flex flex-wrap gap-2" role="radiogroup" aria-label="Main colour">
              {SWATCHES.map(([name, c]) => (
                <button
                  key={c}
                  type="button"
                  role="radio"
                  aria-checked={color === c}
                  aria-label={name}
                  title={name}
                  onClick={() => pick(c)}
                  className={`grid h-9 w-9 place-items-center rounded-full transition active:scale-95 ${color === c ? "ring-2 ring-ink ring-offset-2 ring-offset-surface" : "hover:scale-105"}`}
                  style={{ background: c, color: textOn(c) }}
                >
                  {color === c ? <Check size={16} strokeWidth={3} /> : null}
                </button>
              ))}
              <label className={`relative grid h-9 w-9 shrink-0 cursor-pointer place-items-center rounded-full transition hover:scale-105 ${custom ? "ring-2 ring-ink ring-offset-2 ring-offset-surface" : ""}`} style={{ background: custom ? color : "conic-gradient(#ef4444,#f5a524,#10b981,#0ea5e9,#6366f1,#a21caf,#ef4444)" }} title="Any colour">
                <input type="color" aria-label="Custom colour" value={HEX.test(color) ? color : "#f5a524"} onChange={(e) => pick(e.target.value)} className="absolute inset-0 cursor-pointer opacity-0" />
                {custom ? <Check size={18} strokeWidth={3} style={{ color: HEX.test(color) ? textOn(color) : undefined }} /> : null}
              </label>
            </div>
            <div className="mt-3 w-36">
              <input aria-label="Colour code" value={hex} onChange={(e) => typed(e.target.value.trim())} maxLength={7} spellCheck={false} className={`${inputCls} font-mono uppercase ${HEX.test(hex) ? "" : "ring-2 ring-bad"}`} />
            </div>
          </Setting>

          <Setting title="Logo" hint="Square PNG works best, up to 5 MB. No logo: a clean mark in your colour.">
            <div className="flex flex-wrap items-center gap-4">
              <span style={previewVars(color, "light")}>
                <Logo url={logo} name={venue.name} size={64} className="rounded-2xl ring-1 ring-line" />
              </span>
              <input ref={file} type="file" accept="image/png,image/jpeg,image/webp" aria-label="Logo file" className="hidden" onChange={(e) => upload(e.target.files?.[0])} />
              <Button type="button" onClick={() => file.current?.click()} disabled={busy === "upload"}>
                <ImageUp size={18} /> {busy === "upload" ? "Uploading…" : logo ? "Change logo" : "Upload logo"}
              </Button>
              {logo ? (
                <Button type="button" variant="ghost" onClick={() => setLogo(null)}>
                  Remove
                </Button>
              ) : null}
            </div>
          </Setting>

          <Setting title="Screens" hint="Light or dark guest screens.">
            <Segmented<Theme>
              value={theme}
              onChange={setTheme}
              options={[
                ["light", <><Sun size={16} /> Light</>],
                ["dark", <><Moon size={16} /> Dark</>],
              ]}
            />
          </Setting>
        </div>

        <div className="border-t border-line p-5 @4xl:border-l @4xl:border-t-0">
          <BrandPreview color={color} theme={theme} logo={logo} name={venue.name} />
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3 border-t border-line px-5 py-4">
        <Button variant="primary" onClick={save} disabled={!dirty || busy === "save" || !HEX.test(color)}>
          {busy === "save" ? "Saving…" : "Save look"}
        </Button>
        {dirty ? (
          <Button variant="ghost" onClick={undo}>
            Undo changes
          </Button>
        ) : (
          <span className="text-sm text-muted">Saved. Screens show it on their next load.</span>
        )}
      </div>
    </Card>
  );
}

/** One setting: its name and a short line on the left (above on narrow screens), the control on the right. */
function Setting({ title, hint, children }: { title: string; hint?: string; children: ReactNode }) {
  return (
    <div className="grid gap-3 border-t border-line px-5 py-5 @2xl:grid-cols-[220px_minmax(0,1fr)] @2xl:gap-6">
      <div>
        <div className="text-[15px] font-semibold">{title}</div>
        {hint ? <div className="text-sm text-muted">{hint}</div> : null}
      </div>
      <div className="min-w-0">{children}</div>
    </div>
  );
}

/** A small guest screen in the chosen colour: the selected category, two dishes and the black main button. */
function BrandPreview({ color, theme, logo, name }: { color: string; theme: Theme; logo: string | null; name: string }) {
  return (
    <div aria-label="Preview" className="brand-preview mx-auto flex w-full max-w-[420px] flex-col gap-4 rounded-2xl bg-canvas p-4 text-ink shadow-soft" style={previewVars(color, theme)}>
      <div className="flex items-center gap-2.5">
        <Logo url={logo} name={name} size={36} className="rounded-xl" />
        <span className="min-w-0 truncate font-bold">{name}</span>
        <span className="ml-auto text-xs font-semibold text-muted">Preview</span>
      </div>
      <div className="flex gap-1.5">
        {["Mains", "Drinks", "Desserts"].map((c, i) => (
          <span key={c} className={`rounded-full px-3 py-1.5 text-[13px] font-semibold ${i === 0 ? "bg-brand text-on-brand" : "bg-ink/[.06] text-ink"}`}>
            {c}
          </span>
        ))}
      </div>
      <div className="grid grid-cols-2 gap-3">
        <MiniDish name="Chicken Kottu" price={95000} />
        <MiniDish name="Garden Salad" price={65000} />
      </div>
      <Button variant="primary" className="w-full" tabIndex={-1}>
        Add to order
      </Button>
      <Button variant="ok" className="w-full" tabIndex={-1}>
        Checkout · {money(160000)}
      </Button>
    </div>
  );
}

function MiniDish({ name, price }: { name: string; price: number }) {
  return (
    <div className="flex min-w-0 flex-col">
      <Dish name={name} size={120} className="aspect-[4/3] h-auto! w-full! rounded-xl!" />
      <span className="mt-2 truncate text-[13px] font-semibold leading-tight">{name}</span>
      <span className="mt-1 flex items-center justify-between">
        <span className="num text-[13px] text-muted">{money(price)}</span>
        <span className="grid h-6 w-6 place-items-center rounded-full bg-ink text-canvas">
          <Plus size={14} strokeWidth={2.5} />
        </span>
      </span>
    </div>
  );
}
