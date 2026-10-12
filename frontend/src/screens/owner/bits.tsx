// Small pieces the owner app's pages share: numbers that count up, small stat cards, a smooth bar
// chart, horizontal bars, key/value rows, the period picker and a one-value prompt.
import { animate, motion, useReducedMotion } from "motion/react";
import { CalendarDays, Star } from "lucide-react";
import { Children, useEffect, useRef, useState, type ReactNode } from "react";
import { Button, Field, IconButton, Input, Modal, Segmented, Skeleton, ease } from "../../ui/kit";

export const secs = (n: number | null | undefined): string => (n === null || n === undefined ? "—" : n < 60 ? `${Math.round(n)}s` : `${Math.floor(n / 60)}m ${String(Math.round(n % 60)).padStart(2, "0")}s`);
export const CHANNEL: Record<string, string> = { cashier: "Counter / POS", kiosk: "Kiosk", table: "Table", waiter: "Waiter" };
export const METHOD: Record<string, string> = { cash: "Cash", card: "Card", lankaqr: "QR payment", pos: "Their POS" };
export const clockOf = (iso: string) => new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

type Tone = "ok" | "warn" | "bad" | undefined;
export const toneText = (t: Tone) => (t === "bad" ? "text-bad" : t === "warn" ? "text-warn" : t === "ok" ? "text-ok" : "");

/** Money for a big number (KPIs): whole rupees, with a small "Rs" — exact amounts stay in lists. */
export const rs = (cents: number | null | undefined): ReactNode => (
  <>
    <span className="mr-1 text-[0.62em] font-semibold text-muted">Rs</span>
    {Math.round((cents ?? 0) / 100).toLocaleString("en-LK")}
  </>
);

/** A number that counts up softly to its new value (instant with "reduce motion"). */
export function CountUp({ value, format = (n) => String(Math.round(n)) }: { value: number; format?: (n: number) => ReactNode }) {
  const reduce = useReducedMotion();
  const [shown, setShown] = useState(reduce ? value : 0);
  const from = useRef(reduce ? value : 0);
  useEffect(() => {
    if (reduce) return setShown(value);
    const c = animate(from.current, value, { duration: 0.7, ease: [0.22, 1, 0.36, 1], onUpdate: (v) => ((from.current = v), setShown(v)) });
    return () => c.stop();
  }, [value, reduce]);
  return <>{format(shown)}</>;
}

/** A page's sub-views (People | Tables | Feedback…): sliding pill tabs inside a <nav>. */
export function SubNav<T extends string>({ label, value, onChange, options, right }: { label: string; value: T; onChange: (v: T) => void; options: [T, ReactNode][]; right?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-center gap-3">
      <nav aria-label={label} className="min-w-0 max-w-full">
        <Segmented value={value} onChange={onChange} options={options} />
      </nav>
      {right ? <div className="ml-auto flex items-center gap-2">{right}</div> : null}
    </div>
  );
}

/** A white section that holds a table-like list: title row, then rows split by hairlines. */
export function Panel({ title, hint, right, children, className = "" }: { title?: ReactNode; hint?: ReactNode; right?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`min-w-0 overflow-hidden rounded-2xl bg-surface shadow-soft ${className}`}>
      {title ? (
        <div className="flex items-end justify-between gap-3 px-4 pb-3 pt-4 sm:px-5 sm:pt-5">
          <div className="min-w-0">
            <h2 className="text-lg font-bold tracking-[-0.01em]">{title}</h2>
            {hint ? <p className="truncate text-sm text-muted">{hint}</p> : null}
          </div>
          {right}
        </div>
      ) : null}
      {children}
    </section>
  );
}

/** Column headings of a table-like list (from laptops up). `cols` is a CSS grid template shared with the
 *  rows; the first `left` columns read left to right, the rest (numbers) are right-aligned. */
export function TableHead({ cols, left = 1, children }: { cols: string; left?: number; children: ReactNode }) {
  return (
    <div style={{ "--cols": cols } as React.CSSProperties} className="hidden grid-cols-(--cols) items-center gap-4 whitespace-nowrap border-t border-line bg-canvas/60 px-5 py-2 text-xs font-semibold uppercase tracking-wide text-muted lg:grid">
      {Children.toArray(children).map((c, i) => (
        <span key={i} className={`truncate ${i < left ? "text-left" : "text-right"}`}>
          {c}
        </span>
      ))}
    </div>
  );
}
/** Class + style for one table row that lines up with its TableHead from tablets up. */
export const tableRow = (cols: string) => ({ style: { "--cols": cols } as React.CSSProperties, cls: "lg:grid lg:grid-cols-(--cols) lg:items-center lg:gap-4" });

/** One number in a strip: small label, big bold value, optional hint (Uber-merchant style). */
export function Kpi({ label, value, hint, tone, wide = false }: { label: ReactNode; value: ReactNode; hint?: ReactNode; tone?: Tone; wide?: boolean }) {
  return (
    <div className={`kpi min-w-0 bg-surface px-4 py-4 sm:px-5 sm:py-5 ${wide ? "max-md:col-span-2" : ""}`}>
      <div className="truncate text-[13px] font-semibold text-muted">{label}</div>
      <div className={`num mt-1.5 truncate text-2xl font-bold leading-tight tracking-tight sm:text-[28px] ${toneText(tone)}`}>{value}</div>
      {hint ? <div className="mt-1 flex min-w-0 items-center gap-1.5 truncate text-[13px] text-muted">{hint}</div> : null}
    </div>
  );
}

/** A row of numbers in one flat white section, split by hairlines. */
export function KpiStrip({ children, cols = 4 }: { children: ReactNode; cols?: 3 | 4 | 5 | 6 }) {
  const md = { 3: "md:grid-cols-3", 4: "md:grid-cols-4", 5: "md:grid-cols-3 xl:grid-cols-5", 6: "md:grid-cols-3 xl:grid-cols-6" }[cols];
  return <div className={`grid grid-cols-2 gap-px overflow-hidden rounded-2xl bg-line shadow-soft ${md}`}>{children}</div>;
}

export function KpiSkeleton({ n = 4 }: { n?: number }) {
  return <Skeleton className={`rounded-2xl ${n > 4 ? "h-[220px] md:h-[200px] xl:h-[108px]" : "h-[220px] md:h-[108px]"}`} />;
}

/** Stars as a small row of icons (filled up to the value). */
export function Stars({ value, size = 14 }: { value: number; size?: number }) {
  return (
    <span className="inline-flex items-center gap-px" aria-label={`${value} of 5 stars`}>
      {[1, 2, 3, 4, 5].map((n) => (
        <Star key={n} size={size} strokeWidth={0} className={n <= Math.round(value) ? "fill-ink" : "fill-ink/15"} />
      ))}
    </span>
  );
}

/** Label on the left, value on the right; for detail sheets and small summaries. */
export function Rows({ rows }: { rows: [ReactNode, ReactNode][] }) {
  return (
    <div className="flex flex-col">
      {rows.map(([k, v], i) => (
        <div key={i} className="flex items-baseline justify-between gap-3 border-t border-line/60 py-2.5 first:border-0 first:pt-0">
          <span className="min-w-0 text-[15px] text-muted">{k}</span>
          <span className="num shrink-0 text-right text-[15px] font-semibold">{v}</span>
        </div>
      ))}
    </div>
  );
}

/** Horizontal bars, e.g. money per person. One series, in ink. */
export function Bars({ rows, format }: { rows: [string, number][]; format: (n: number) => string }) {
  const max = Math.max(1, ...rows.map((r) => r[1]));
  if (!rows.length) return <p className="py-6 text-center text-muted">Nothing yet</p>;
  return (
    <div className="flex flex-col gap-3">
      {rows.map(([label, v], i) => (
        <div key={label} className="grid grid-cols-[minmax(0,9rem)_1fr_auto] items-center gap-3 text-sm" title={`${label}: ${format(v)}`}>
          <span className="truncate font-semibold">{label}</span>
          <span className="h-1.5 overflow-hidden rounded-full bg-ink/[.06]">
            <motion.span className="block h-1.5 rounded-full bg-accent" initial={{ width: 0 }} animate={{ width: `${Math.max(2, (100 * v) / max)}%` }} transition={{ ...ease, duration: 0.6, delay: i * 0.04 }} />
          </span>
          <span className="num font-semibold">{format(v)}</span>
        </div>
      ))}
    </div>
  );
}

/** Columns over time (sales per hour): bars grow in, the value shows on hover, the best hour is marked. */
export function Columns({ rows: given, format }: { rows: [string, number][]; format: (n: number) => string }) {
  const [hover, setHover] = useState<number | null>(null);
  const rows = fillHours(given);
  if (!rows.length) return <p className="grid h-52 place-items-center text-muted lg:h-64">No sales yet</p>;
  const max = Math.max(1, ...rows.map((r) => r[1]));
  const best = rows.findIndex((r) => r[1] === max);
  const shown = hover ?? best;
  const step = rows.length > 12 ? 3 : rows.length > 7 ? 2 : 1;
  return (
    <div>
      <div className="mb-4 flex items-baseline gap-2 text-sm">
        <span className="num text-xl font-bold tracking-tight">{format(rows[shown][1])}</span>
        <span className="text-muted">
          {hover === null ? "best hour · " : ""}
          {rows[shown][0]}
        </span>
      </div>
      <div className="flex h-52 items-end gap-1 border-b border-line sm:gap-1.5 lg:h-64" onMouseLeave={() => setHover(null)}>
        {rows.map(([label, v], i) => (
          <button key={label} type="button" aria-label={`${label}: ${format(v)}`} onMouseEnter={() => setHover(i)} onFocus={() => setHover(i)} onClick={() => setHover(i)} className="group flex h-full min-w-0 max-w-16 flex-1 cursor-default flex-col justify-end">
            <motion.span
              className={`block w-full rounded-t-[5px] rounded-b-[2px] transition-colors ${i === shown ? "bg-accent" : "bg-accent/25 group-hover:bg-accent/45"}`}
              initial={{ height: 0 }}
              animate={{ height: `${Math.max(3, (100 * v) / max)}%` }}
              transition={{ ...ease, duration: 0.6, delay: i * 0.025 }}
            />
          </button>
        ))}
      </div>
      <div className="mt-2 flex gap-1 text-[11px] text-muted sm:gap-1.5">
        {rows.map(([label], i) => (
          <span key={label} className="min-w-0 max-w-16 flex-1 text-center">
            {i % step === 0 ? label.replace(/:00$/, "") : ""}
          </span>
        ))}
      </div>
    </div>
  );
}

/** "07:00" … "11:00" with only busy hours: add the quiet hours in between as 0, so time reads evenly. */
function fillHours(rows: [string, number][]): [string, number][] {
  if (!rows.length || !rows.every(([h]) => /^\d{2}:00$/.test(h))) return rows;
  const got = new Map(rows);
  const hours = rows.map(([h]) => Number(h.slice(0, 2)));
  const out: [string, number][] = [];
  // At least a normal trading day, so one busy hour is a bar among hours, not a slab.
  for (let h = Math.min(8, ...hours); h <= Math.max(22, ...hours); h++) {
    const k = `${String(h).padStart(2, "0")}:00`;
    out.push([k, got.get(k) ?? 0]);
  }
  return out;
}

// ------------------------------------------------------------------ periods

export type Range = { from: string; to: string; label: string; key?: string };
const iso = (d: Date) => d.toLocaleDateString("en-CA");
const parse = (s: string) => {
  const [y, m, d] = s.split("-").map(Number);
  return new Date(y, m - 1, d);
};
const addDays = (s: string, n: number) => {
  const d = parse(s);
  d.setDate(d.getDate() + n);
  return iso(d);
};

export function presets(tz: string): Record<"today" | "yesterday" | "week" | "month", Range> {
  const today = new Date(new Date().toLocaleString("en-US", { timeZone: tz }));
  const day = (n: number) => iso(new Date(today.getFullYear(), today.getMonth(), today.getDate() - n));
  const monday = (today.getDay() + 6) % 7;
  return {
    today: { from: day(0), to: day(0), label: "Today", key: "today" },
    yesterday: { from: day(1), to: day(1), label: "Yesterday", key: "yesterday" },
    week: { from: day(monday), to: day(0), label: "This week", key: "week" },
    month: { from: iso(new Date(today.getFullYear(), today.getMonth(), 1)), to: day(0), label: "This month", key: "month" },
  };
}

/** The period just before, to compare with: yesterday, the same days last week / last month, or the days before. */
export function previous(r: Range): Range {
  if (r.key === "week") return { from: addDays(r.from, -7), to: addDays(r.to, -7), label: "same days last week" };
  if (r.key === "month") {
    const f = parse(r.from);
    const t = parse(r.to);
    const pf = new Date(f.getFullYear(), f.getMonth() - 1, 1);
    const last = new Date(t.getFullYear(), t.getMonth(), 0).getDate();
    const pt = new Date(t.getFullYear(), t.getMonth() - 1, Math.min(t.getDate(), last));
    return { from: iso(pf), to: iso(pt), label: "same days last month" };
  }
  const n = Math.round((parse(r.to).getTime() - parse(r.from).getTime()) / 86400000) + 1;
  return { from: addDays(r.from, -n), to: addDays(r.to, -n), label: n === 1 ? (r.key === "today" ? "yesterday" : "the day before") : `the ${n} days before` };
}

const fmtDay = (s: string) => parse(s).toLocaleDateString([], { day: "numeric", month: "short" });
export const rangeText = (r: Range) => (r.key ? r.label : r.from === r.to ? fmtDay(r.from) : `${fmtDay(r.from)} – ${fmtDay(r.to)}`);

/** Today · Yesterday · Week · Month, and a calendar button for any dates. */
export function RangePicker({ tz, value, onChange }: { tz: string; value: Range; onChange: (r: Range) => void }) {
  const p = presets(tz);
  const [open, setOpen] = useState(false);
  const [from, setFrom] = useState(value.from);
  const [to, setTo] = useState(value.to);
  const key = (Object.keys(p) as (keyof typeof p)[]).find((k) => p[k].from === value.from && p[k].to === value.to) ?? "custom";
  return (
    <div className="flex min-w-0 items-center gap-1.5 sm:gap-2">
      <Segmented
        className="max-sm:[&>button]:px-3 [&>button]:h-9"
        value={key}
        onChange={(k) => (k === "custom" ? setOpen(true) : onChange(p[k as keyof typeof p]))}
        options={[["today", "Today"], ["yesterday", "Yesterday"], ["week", "Week"], ["month", "Month"], ...(key === "custom" ? ([["custom", rangeText(value)]] as [string, string][]) : [])]}
      />
      <IconButton label="Pick dates" variant="default" size={40} onClick={() => (setFrom(value.from), setTo(value.to), setOpen(true))}>
        <CalendarDays size={18} />
      </IconButton>
      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title="Pick dates"
        footer={
          <Button variant="primary" size="lg" className="w-full" disabled={!from || !to || to < from} onClick={() => (onChange({ from, to, label: "Custom" }), setOpen(false))}>
            Show these days
          </Button>
        }
      >
        <div className="grid grid-cols-2 gap-3">
          <Field label="From">
            <Input aria-label="From" type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
          </Field>
          <Field label="To">
            <Input aria-label="To" type="date" value={to} onChange={(e) => setTo(e.target.value)} />
          </Field>
        </div>
      </Modal>
    </div>
  );
}

/** Ask for one value (a number, a time) in a small window. */
export function usePrompt() {
  const [ask, setAsk] = useState<{ title: string; type: string; value: string; resolve: (v: string | null) => void } | null>(null);
  const prompt = (title: string, type = "number", value = "") => new Promise<string | null>((resolve) => setAsk({ title, type, value, resolve }));
  const close = (v: string | null) => (ask?.resolve(v), setAsk(null));
  const modal = (
    <Modal
      open={!!ask}
      onClose={() => close(null)}
      title={ask?.title}
      footer={
        <Button variant="primary" size="lg" className="w-full" type="submit" form="owner-prompt">
          Save
        </Button>
      }
    >
      {ask ? (
        <form id="owner-prompt" onSubmit={(e) => (e.preventDefault(), close(ask.value))}>
          <Input autoFocus aria-label={ask.title} type={ask.type} value={ask.value} onChange={(e) => setAsk({ ...ask, value: e.target.value })} className="h-14 text-xl font-bold" />
        </form>
      ) : null}
    </Modal>
  );
  return { prompt, modal };
}
