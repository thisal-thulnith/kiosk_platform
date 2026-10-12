// The kiosk's building blocks: welcome, options sheet, cart rows, totals, order number, tracking and
// the guest's rating. Uber Eats style: white, big bold type, black main buttons, hairlines, photos
// first. Big touch targets (≥ 56 px), few words, soft spring motion.
import { AnimatePresence, motion } from "motion/react";
import { Check, ChefHat, Minus, PackageCheck, Plus, Receipt, Star, Trash2, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import type { Device } from "../../lib/device";
import { money } from "../../lib/format";
import T from "../../lib/i18n.json";
import type { Me, Menu, MenuItem, Order, Text } from "../../lib/types";
import { dishIcon } from "../../ui/food";
import { Button, IconButton, spring, useToast } from "../../ui/kit";
import { Logo } from "../../ui/logo";
import { type CartLine, unitPrice } from "../../ui/ordering";

export type Lang = "en" | "si" | "ta";
export type TFn = (k: keyof typeof T.en) => string;
export type LFn = (o: Text | undefined) => string;
export const LANG_NAMES: Record<Lang, string> = { en: "English", si: "සිංහල", ta: "தமிழ்" };

/** A word that may not be in the language file yet: the translation when there is one, else English. */
export const word = (lang: Lang, key: string, english: string): string => (T[lang] as Record<string, string | undefined>)[key] ?? english;

// ------------------------------------------------------------------ layout

/** One step of the flow: its content fills the middle of the screen (or starts at the top for lists),
 *  its actions sit at the bottom where a hand reaches them. */
export function Step({ children, foot, top = false }: { children: ReactNode; foot?: ReactNode; top?: boolean }) {
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="min-h-0 flex-1 overflow-auto">
        <div className={`mx-auto flex min-h-full w-full max-w-[920px] flex-col px-10 py-8 landscape:max-w-[1240px] ${top ? "" : "justify-center"}`}>{children}</div>
      </div>
      {foot ? <div className="mx-auto flex w-full max-w-[920px] shrink-0 items-center justify-center gap-4 px-10 pb-10 pt-4 landscape:max-w-[1240px]">{foot}</div> : null}
    </div>
  );
}

/** A bottom sheet (portrait kiosks reach the bottom best). */
export function Sheet({ open, onClose, children }: { open: boolean; onClose: () => void; children: ReactNode }) {
  return createPortal(
    <AnimatePresence>
      {open ? (
        <motion.div key="sheet" className="fixed inset-0 z-50 flex items-end justify-center bg-black/45" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.2 }} onClick={(e) => e.target === e.currentTarget && onClose()}>
          <motion.div role="dialog" aria-modal="true" data-modal initial={{ y: "100%" }} animate={{ y: 0 }} exit={{ y: "100%" }} transition={spring} className="flex max-h-[90vh] w-full max-w-[1080px] flex-col overflow-hidden rounded-t-[2rem] bg-surface text-ink shadow-[0_-12px_40px_rgb(0_0_0/16%)]">
            {children}
          </motion.div>
        </motion.div>
      ) : null}
    </AnimatePresence>,
    document.body,
  );
}

/** A dish photo that fills its box (rectangular, Uber Eats style), or the neutral line-icon tile. */
export function Photo({ src, name, hint, className = "", icon = 56 }: { src?: string | null; name: string; hint?: string; className?: string; icon?: number }) {
  if (src) return <img src={src} alt="" loading="lazy" className={`block bg-ink/[.05] object-cover ${className}`} />;
  const Icon = dishIcon(name, hint);
  return (
    <span aria-hidden className={`grid place-items-center bg-ink/[.05] text-ink/30 ${className}`}>
      <Icon size={icon} strokeWidth={1.4} />
    </span>
  );
}

// ------------------------------------------------------------------ welcome

export function Welcome({ me, langs, t, onStart, attract, dishes }: { me: Me; langs: Lang[]; t: TFn; onStart: (l: Lang) => void; attract: string[]; dishes: MenuItem[] }) {
  const [slide, setSlide] = useState(0);
  useEffect(() => {
    if (attract.length < 2) return;
    const h = setInterval(() => setSlide((s) => (s + 1) % attract.length), 6000);
    return () => clearInterval(h);
  }, [attract.length]);
  // No photos of the restaurant yet: a calm row of the menu's own dishes.
  const strip = dishes.filter((d) => d.is_available).slice(0, 4);
  return (
    <button onClick={() => onStart("en")} className="relative flex h-full w-full flex-col overflow-hidden bg-surface text-left text-ink">
      <div className="flex shrink-0 items-center gap-4 px-12 pt-12">
        <Logo url={me.venue.brand?.logo_url} name={me.venue.name} size={64} />
        <span className="min-w-0 truncate text-[28px] font-bold tracking-tight">{me.venue.name}</span>
      </div>
      {attract.length ? (
        // The restaurant's own photos, softly cross-fading.
        <div className="relative mx-12 mt-10 min-h-0 flex-1 overflow-hidden rounded-3xl bg-ink/[.05]">
          {attract.map((src, k) => (
            <img key={src} src={src} alt="" className={`absolute inset-0 h-full w-full object-cover transition-opacity duration-1000 ${k === slide ? "opacity-100" : "opacity-0"}`} />
          ))}
        </div>
      ) : (
        <div className="flex min-h-0 flex-1 flex-col justify-center px-12">
          <div className="grid grid-cols-2 gap-x-6 gap-y-8 landscape:grid-cols-4">
            {strip.map((d, k) => (
              <motion.span key={d.id} className="block" initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ ...spring, delay: 0.08 * k }}>
                <Photo src={d.image_url} name={d.name.en ?? ""} className="aspect-[4/3] w-full rounded-2xl" icon={72} />
                <span className="mt-3 block truncate text-2xl font-semibold">{d.name.en}</span>
                <span className="num mt-0.5 block text-xl text-muted">{money(d.offer?.price ?? d.price)}</span>
              </motion.span>
            ))}
          </div>
        </div>
      )}
      <div className="shrink-0 px-12 pb-14 pt-12">
        <h1 className="text-[64px] font-bold leading-[1.02] tracking-[-0.03em] landscape:text-[56px]">{t("welcome")}</h1>
        {langs.length > 1 ? <p className="mt-3 text-2xl text-muted">{t("choose")}</p> : null}
        <motion.span
          animate={{ scale: [1, 1.015, 1] }}
          transition={{ duration: 2.8, repeat: Infinity, ease: "easeInOut" }}
          className="mt-10 flex h-[104px] w-full items-center justify-center rounded-2xl bg-ink text-[40px] font-bold tracking-tight text-canvas"
        >
          {t("tapToStart")}
        </motion.span>
        {langs.length > 1 ? (
          <div className="mt-5 flex gap-4" onClick={(e) => e.stopPropagation()}>
            {langs.map((l) => (
              <span key={l} role="button" onClick={() => onStart(l)} className="inline-flex h-20 flex-1 items-center justify-center rounded-2xl bg-ink/[.06] px-8 text-2xl font-semibold transition active:scale-[.98]">
                {LANG_NAMES[l]}
              </span>
            ))}
          </div>
        ) : null}
      </div>
    </button>
  );
}

// ------------------------------------------------------------------ options (add-ons, meal choices)

type Picked = Omit<CartLine, "key" | "qty" | "hold">;

/** Ask for add-ons and meal choices when the dish has them; otherwise add it straight away. */
export function useKioskOptions(menu: Menu | null, L: LFn, t: TFn) {
  const [item, setItem] = useState<MenuItem | null>(null);
  const resolver = useRef<((c: Picked | null) => void) | null>(null);
  const last = useRef<MenuItem | null>(null);
  if (item) last.current = item;
  const ask = (i: MenuItem) =>
    new Promise<Picked | null>((res) => {
      if (!i.modifier_groups.length && !i.combo_slots.length) return res({ item: i, mods: [], combo: null, notes: "" });
      resolver.current = res;
      setItem(i);
    });
  const close = (c: Picked | null) => {
    resolver.current?.(c);
    resolver.current = null;
    setItem(null);
  };
  const shown = last.current;
  const modal = (
    <Sheet open={!!item} onClose={() => close(null)}>
      {shown && menu ? <Options key={shown.id} item={shown} menu={menu} L={L} t={t} onClose={close} /> : null}
    </Sheet>
  );
  return { ask, modal };
}

function Options({ item, menu, L, t, onClose }: { item: MenuItem; menu: Menu; L: LFn; t: TFn; onClose: (c: Picked | null) => void }) {
  const [chosen, setChosen] = useState<Record<string, string[]>>({});
  const [picks, setPicks] = useState<(string | null)[]>(item.combo_slots.map(() => null));
  const [notes, setNotes] = useState("");
  const allItems = useMemo(() => Object.fromEntries(menu.categories.flatMap((c) => c.items).map((i) => [i.id, i])), [menu]);
  const valid = item.modifier_groups.every((g) => (chosen[g.id]?.length ?? 0) >= g.min_select) && picks.every(Boolean);
  const mods = item.modifier_groups.flatMap((g) => g.modifiers.filter((m) => chosen[g.id]?.includes(m.id)));
  const up = picks.reduce((s, id, i) => s + (id ? (item.combo_slots[i].upcharges?.[id] ?? 0) : 0), 0);
  const unit = (item.offer?.price ?? item.price) + mods.reduce((s, m) => s + m.price_delta, 0) + up;
  const partName = (id: string) => L(allItems[id]?.name ?? menu.combo_parts[id]?.name);
  return (
    <>
      <div className="relative shrink-0">
        <Photo src={item.image_url} name={item.name.en ?? L(item.name)} className="h-[300px] w-full landscape:h-[220px]" icon={88} />
        <IconButton label="Close" size={60} variant="default" className="absolute right-6 top-6 ring-0! shadow-[0_2px_10px_rgb(0_0_0/12%)]" onClick={() => onClose(null)}>
          <X size={26} />
        </IconButton>
      </div>
      <div className="flex min-h-0 flex-1 flex-col overflow-auto px-10 pb-6 pt-7">
        <h2 className="text-[36px] font-bold leading-tight tracking-tight">{L(item.name)}</h2>
        <div className="num mt-1 text-2xl font-semibold">{money(item.offer?.price ?? item.price)}</div>
        {L(item.description) ? <p className="mt-2 text-xl leading-snug text-muted">{L(item.description)}</p> : null}
        {item.combo_slots.map((slot, si) => (
          <Group key={si} title={L(slot.name)} hint={t("required")} done={!!picks[si]}>
            {slot.item_ids.map((id) => {
              const avail = allItems[id]?.is_available ?? menu.combo_parts[id]?.is_available ?? true;
              const extra = slot.upcharges?.[id] ?? 0;
              return <Choice key={id} radio on={picks[si] === id} disabled={!avail} label={partName(id)} extra={extra} onClick={() => setPicks((p) => p.map((x, i) => (i === si ? id : x)))} />;
            })}
          </Group>
        ))}
        {item.modifier_groups.map((g) => (
          <Group key={g.id} title={L(g.name)} hint={g.min_select ? `${t("required")} ${g.min_select === g.max_select ? g.min_select : `${g.min_select}–${g.max_select}`}` : `${t("upTo")} ${g.max_select}`} done={g.min_select ? (chosen[g.id]?.length ?? 0) >= g.min_select : null}>
            {g.modifiers.map((m) => {
              const on = !!chosen[g.id]?.includes(m.id);
              return (
                <Choice
                  key={m.id}
                  radio={g.max_select === 1}
                  on={on}
                  label={L(m.name)}
                  extra={m.price_delta}
                  onClick={() =>
                    setChosen((c) => {
                      const cur = c[g.id] ?? [];
                      const next = on ? cur.filter((x) => x !== m.id) : g.max_select === 1 ? [m.id] : cur.length < g.max_select ? [...cur, m.id] : cur;
                      return { ...c, [g.id]: next };
                    })
                  }
                />
              );
            })}
          </Group>
        ))}
        <input value={notes} onChange={(e) => setNotes(e.target.value)} placeholder={t("notes")} maxLength={300} className="mt-8 h-16 shrink-0 rounded-xl bg-ink/[.05]! px-5 text-xl outline-none transition placeholder:text-muted focus:ring-2 focus:ring-ink" />
      </div>
      <div className="shrink-0 border-t border-line px-10 pb-9 pt-5">
        <Button
          variant="primary"
          size="xl"
          className="h-20 w-full justify-between! px-8! text-2xl!"
          disabled={!valid}
          onClick={() => onClose({ item, mods, notes, combo: item.combo_slots.length ? { choices: picks as string[], names: picks.map((id) => partName(id!)), up } : null })}
        >
          <span>{t("addToOrder")}</span>
          <span className="num">{money(unit)}</span>
        </Button>
      </div>
    </>
  );
}

/** done: null for an optional group (no tick, just a quiet hint). */
function Group({ title, hint, done, children }: { title: string; hint: string; done: boolean | null; children: ReactNode }) {
  return (
    <section className="mt-8">
      <div className="flex items-center justify-between gap-3 border-b border-line pb-3">
        <h3 className="text-2xl font-bold tracking-tight">{title}</h3>
        <span className={`inline-flex items-center gap-1.5 rounded-full px-3.5 py-1.5 text-base font-semibold transition ${done ? "bg-ok-soft text-ok" : done === null ? "bg-ink/[.06] text-muted" : "bg-ink text-canvas"}`}>
          {done ? <Check size={17} strokeWidth={3} /> : null}
          {hint}
        </span>
      </div>
      <div className="divide-y divide-line">{children}</div>
    </section>
  );
}

function Choice({ on, label, extra, onClick, radio = false, disabled = false }: { on: boolean; label: string; extra: number; onClick: () => void; radio?: boolean; disabled?: boolean }) {
  return (
    <button disabled={disabled} onClick={onClick} className="flex min-h-[76px] w-full items-center gap-4 py-3 text-left transition active:opacity-70 disabled:opacity-35">
      <span className="min-w-0 flex-1 text-xl font-medium leading-tight">{label}</span>
      {extra ? <span className="num shrink-0 text-lg text-muted">+{money(extra)}</span> : null}
      <span className={`grid h-8 w-8 shrink-0 place-items-center transition ${radio ? "rounded-full" : "rounded-lg"} ${on ? "bg-ink text-canvas" : "ring-2 ring-inset ring-ink/25"}`}>
        {on ? radio ? <span className="h-3 w-3 rounded-full bg-canvas" /> : <Check size={20} strokeWidth={3} /> : null}
      </span>
    </button>
  );
}

// ------------------------------------------------------------------ cart

/** − n + in a grey pill (Uber Eats style); the minus turns into a bin at one. */
function Stepper({ qty, onQty, big }: { qty: number; onQty: (q: number) => void; big: boolean }) {
  const btn = `grid place-items-center rounded-full text-ink transition active:scale-90 active:bg-ink/10 ${big ? "h-14 w-14" : "h-12 w-12"}`;
  return (
    <div className="flex shrink-0 items-center rounded-full bg-ink/[.06]">
      <button aria-label="Less" className={btn} onClick={() => onQty(qty - 1)}>
        {qty === 1 ? <Trash2 size={big ? 22 : 19} /> : <Minus size={big ? 22 : 19} strokeWidth={2.4} />}
      </button>
      <span className={`num relative grid place-items-center overflow-hidden font-bold ${big ? "h-14 w-9 text-2xl" : "h-12 w-7 text-lg"}`}>
        <AnimatePresence initial={false} mode="popLayout">
          <motion.span key={qty} initial={{ y: -16, opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ y: 16, opacity: 0 }} transition={spring}>
            {qty}
          </motion.span>
        </AnimatePresence>
      </span>
      <button aria-label="More" className={btn} onClick={() => onQty(qty + 1)}>
        <Plus size={big ? 22 : 19} strokeWidth={2.4} />
      </button>
    </div>
  );
}

/** One cart row: picture, name, choices, price, and − / + . */
export function Line({ c, L, onQty, big = false }: { c: CartLine; L: LFn; onQty: (q: number) => void; big?: boolean }) {
  const extra = [...(c.combo?.names ?? []), ...c.mods.map((m) => L(m.name)), c.notes].filter(Boolean).join(" · ");
  return (
    <div className={`flex items-center ${big ? "gap-6 py-5" : "gap-4 py-4"}`}>
      <Photo src={c.item.image_url} name={c.item.name.en ?? L(c.item.name)} className={`shrink-0 rounded-xl ${big ? "h-[88px] w-[112px]" : "h-16 w-20"}`} icon={big ? 34 : 26} />
      <div className="min-w-0 flex-1">
        <div className={`truncate font-semibold leading-tight ${big ? "text-2xl" : "text-lg"}`}>{L(c.item.name)}</div>
        {extra ? <div className={`truncate text-muted ${big ? "mt-0.5 text-lg" : "text-[15px]"}`}>{extra}</div> : null}
        <div className={`num text-muted ${big ? "mt-1 text-xl" : "text-[15px]"}`}>{money(unitPrice(c) * c.qty)}</div>
      </div>
      <Stepper qty={c.qty} onQty={onQty} big={big} />
    </div>
  );
}

type QuoteLike = { subtotal: number; discount_total: number; tax_lines: { name: Text; amount: number }[]; total: number };

/** Subtotal, discount and taxes as quiet rows, then the total in bold. */
export function Totals({ quote, fallback, labels, L, big = false }: { quote: QuoteLike | null; fallback: number; labels: { subtotal: string; discount: string; total: string }; L: LFn; big?: boolean }) {
  const row = `flex justify-between ${big ? "text-xl" : "text-[15px]"}`;
  return (
    <div>
      {quote ? (
        <div className={big ? "space-y-2.5" : "space-y-1.5"}>
          <div className={row}>
            <span className="text-muted">{labels.subtotal}</span>
            <span className="num">{money(quote.subtotal)}</span>
          </div>
          {quote.discount_total ? (
            <div className={row}>
              <span className="text-muted">{labels.discount}</span>
              <span className="num text-ok">− {money(quote.discount_total)}</span>
            </div>
          ) : null}
          {quote.tax_lines.map((x, i) => (
            <div key={i} className={`${row} text-muted`}>
              <span>{L(x.name)}</span>
              <span className="num">{money(x.amount)}</span>
            </div>
          ))}
        </div>
      ) : null}
      <div className={`flex items-baseline justify-between ${quote ? `border-t border-line ${big ? "mt-5 pt-5" : "mt-3 pt-3"}` : ""}`}>
        <span className={`font-bold ${big ? "text-3xl" : "text-lg"}`}>{labels.total}</span>
        <span className={`num font-bold tracking-tight ${big ? "text-[44px]" : "text-2xl"}`}>{money(quote?.total ?? fallback)}</span>
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ order number + tracking

export const Waiting = ({ text }: { text: string }) => (
  <p className="mt-8 flex items-center justify-center gap-3 text-center text-xl font-medium text-muted">
    <span className="flex gap-1.5">
      {[0, 1, 2].map((k) => (
        <motion.span key={k} className="h-2.5 w-2.5 rounded-full bg-ink" animate={{ opacity: [0.2, 1, 0.2] }} transition={{ duration: 1.2, repeat: Infinity, delay: k * 0.2 }} />
      ))}
    </span>
    {text}
  </p>
);

/** Minutes until the promised time (at least 1), or null when there is no promise or it has passed. */
function minutesLeft(iso: string | null, now: number): number | null {
  if (!iso) return null;
  const m = Math.ceil((new Date(iso).getTime() - now) / 60000);
  return m > 0 ? m : null;
}

export function Track({ device, order, t, lang, onDone }: { device: Device; order: Order; t: TFn; lang: Lang; onDone: () => void }) {
  const toast = useToast();
  const [phone, setPhone] = useState("");
  const [texted, setTexted] = useState(false);
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const h = setInterval(() => setNow(Date.now()), 15000);
    return () => clearInterval(h);
  }, []);
  const ready = order.status === "ready" || order.status === "completed";
  const at = ready ? 2 : order.status === "in_kitchen" ? 1 : 0;
  const isEn = lang === "en";
  const steps = [
    { label: t("step_placed"), icon: Receipt },
    { label: isEn ? "Cooking" : t("step_kitchen"), icon: ChefHat },
    { label: isEn ? "Ready to collect" : t("step_ready"), icon: PackageCheck },
  ];
  const mins = minutesLeft(order.promised_at, now);
  const headline = ready ? t("readyTitle") : at === 1 ? (isEn ? "Cooking your order" : t("step_kitchen")) : t("placed");
  const sub = ready ? t("readyBody") : mins ? `${t("readyIn")} ${mins} ${t("minutes")}` : at === 1 ? (isEn ? "Almost ready" : t("step_kitchen")) : t("step_placed");
  return (
    <Step foot={<Button variant="soft" size="xl" className="h-20 px-12 text-2xl!" onClick={onDone}>{t("newOrder")}</Button>}>
      <div className="grid items-start gap-10 landscape:grid-cols-[1fr_1fr] landscape:gap-14">
        <div>
          <div className="text-2xl font-medium text-muted">{t("yourNumber")}</div>
          <div className="num mt-1 text-[180px] font-black leading-[0.9] tracking-[-0.04em] landscape:text-[150px]" aria-label={t("yourNumber")} data-token={order.token}>
            {order.token}
          </div>
          <AnimatePresence mode="wait" initial={false}>
            <motion.div key={headline} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }} transition={spring} className="mt-10">
              <h1 className={`flex items-center gap-3 text-[44px] font-bold leading-tight tracking-tight ${ready ? "text-ok" : ""}`}>
                {ready ? (
                  <motion.span initial={{ scale: 0.4 }} animate={{ scale: 1 }} transition={{ ...spring, delay: 0.1 }} className="grid h-12 w-12 shrink-0 place-items-center rounded-full bg-ok text-white">
                    <Check size={28} strokeWidth={3} />
                  </motion.span>
                ) : null}
                {headline}
              </h1>
              <p className="num mt-2 text-2xl text-muted">{sub}</p>
            </motion.div>
          </AnimatePresence>
          <Progress steps={steps} at={at} ready={ready} />
        </div>

        <div className="flex flex-col gap-8 landscape:pt-4">
          {!ready && !texted ? (
            <section className="border-t border-line pt-8 landscape:border-t-0 landscape:pt-0">
              <h2 className="text-2xl font-bold tracking-tight">{t("textMe")}</h2>
              <p className="mt-1 text-lg leading-snug text-muted">{t("textMeSub")}</p>
              <div className="mt-5 flex gap-3">
                <input inputMode="tel" aria-label="Mobile number" value={phone} onChange={(e) => setPhone(e.target.value.replace(/[^\d+]/g, ""))} placeholder="07X XXX XXXX" className="num h-[72px] min-w-0 flex-1 rounded-xl bg-ink/[.05]! px-5 text-2xl font-semibold outline-none transition placeholder:font-normal placeholder:text-muted focus:ring-2 focus:ring-ink" />
                <Button variant="primary" size="xl" className="h-[72px] px-10 text-xl!" disabled={phone.length < 9} onClick={() => device.post(`/v1/orders/${order.id}/notify`, { phone }).then(() => (setTexted(true), setPhone(""), toast(t("textMeDone"), "ok"))).catch((e) => toast(e.message, "bad"))}>
                  {t("textMeSend")}
                </Button>
              </div>
            </section>
          ) : texted && !ready ? (
            <p className="flex items-center gap-3 border-t border-line pt-8 text-xl font-semibold landscape:border-t-0 landscape:pt-0">
              <span className="grid h-10 w-10 place-items-center rounded-full bg-ok-soft text-ok">
                <Check size={22} strokeWidth={3} />
              </span>
              {t("textMeDone")}
            </p>
          ) : null}
          <Rate device={device} order={order} lang={lang} first={ready} />
        </div>
      </div>
    </Step>
  );
}

/** Placed → cooking → ready: three segments that fill, the current one gently moving. */
function Progress({ steps, at, ready }: { steps: { label: string; icon: typeof Receipt }[]; at: number; ready: boolean }) {
  return (
    <div className="mt-10">
      <div className="grid grid-cols-3 gap-2">
        {steps.map((_, k) => (
          <span key={k} className="relative h-2 overflow-hidden rounded-full bg-ink/10">
            <motion.span className={`absolute inset-0 origin-left rounded-full ${ready ? "bg-ok" : "bg-ink"}`} initial={false} animate={{ scaleX: k <= at ? 1 : 0 }} transition={{ ...spring, delay: k * 0.08 }} />
            {k === at && !ready ? <motion.span className="absolute inset-y-0 w-1/3 rounded-full bg-gradient-to-r from-transparent via-canvas/45 to-transparent" animate={{ x: ["-100%", "300%"] }} transition={{ duration: 1.6, repeat: Infinity, ease: "easeInOut" }} /> : null}
          </span>
        ))}
      </div>
      <ol className="mt-4 grid grid-cols-3 gap-2">
        {steps.map(({ label, icon: Icon }, k) => {
          const on = k <= at;
          return (
            <li key={k} className={`flex items-center gap-2 text-lg font-semibold leading-tight transition-colors ${on ? "text-ink" : "text-muted"}`}>
              <Icon size={20} className="shrink-0" strokeWidth={2} />
              {label}
            </li>
          );
        })}
      </ol>
    </div>
  );
}

// ------------------------------------------------------------------ rating

const TAGS = ["food", "service", "speed", "value"] as const;
const TAG_EN: Record<(typeof TAGS)[number], string> = { food: "Food", service: "Service", speed: "Speed", value: "Value" };

/** "How was it?": one tap on a star; then, if the guest likes, what was good, and Send. Optional:
 *  it never holds the screen (the track view still clears itself). */
export function Rate({ device, order, lang, first }: { device: Device; order: Order; lang: Lang; first: boolean }) {
  const toast = useToast();
  const [stars, setStars] = useState(0);
  const [tags, setTags] = useState<string[]>([]);
  const [state, setState] = useState<"ask" | "busy" | "done">("ask");
  const send = async () => {
    setState("busy");
    try {
      await device.post("/v1/feedback", { rating: stars, tags, order_id: order.id });
      setState("done");
    } catch (e) {
      setState("ask");
      toast((e as Error).message, "bad");
    }
  };
  return (
    <section className={`border-t border-line pt-8 ${first ? "landscape:border-t-0 landscape:pt-0" : ""}`}>
      <AnimatePresence mode="wait" initial={false}>
        {state === "done" ? (
          <motion.div key="thanks" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={spring} className="flex items-center gap-4">
            <span className="grid h-14 w-14 place-items-center rounded-full bg-ok-soft text-ok">
              <Check size={28} strokeWidth={3} />
            </span>
            <span className="text-2xl font-bold tracking-tight">{word(lang, "rateThanks", "Thank you")}</span>
          </motion.div>
        ) : (
          <motion.div key="ask" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <h2 className="text-2xl font-bold tracking-tight">{word(lang, "rateTitle", "How was it?")}</h2>
            <div className="mt-4 flex gap-2" role="radiogroup" aria-label={word(lang, "rateTitle", "How was it?")}>
              {[1, 2, 3, 4, 5].map((n) => (
                <motion.button key={n} role="radio" aria-checked={stars === n} aria-label={`${n} / 5`} whileTap={{ scale: 0.85 }} onClick={() => setStars(n)} className="grid h-[72px] w-[72px] place-items-center rounded-full transition hover:bg-ink/[.04]">
                  <Star size={44} strokeWidth={1.6} className={`transition-colors ${n <= stars ? "fill-ink text-ink" : "text-ink/25"}`} />
                </motion.button>
              ))}
            </div>
            <AnimatePresence initial={false}>
              {stars ? (
                <motion.div key="more" initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }} transition={{ duration: 0.22 }} className="overflow-hidden">
                  <div className="flex flex-wrap gap-3 pt-5">
                    {TAGS.map((k) => {
                      const on = tags.includes(k);
                      return (
                        <button key={k} onClick={() => setTags((x) => (on ? x.filter((y) => y !== k) : [...x, k]))} className={`inline-flex h-14 items-center gap-2 rounded-full px-6 text-xl font-semibold transition active:scale-[.97] ${on ? "bg-ink text-canvas" : "bg-ink/[.06] text-ink"}`}>
                          {on ? <Check size={20} strokeWidth={2.6} /> : null}
                          {word(lang, `tag_${k}`, TAG_EN[k])}
                        </button>
                      );
                    })}
                  </div>
                  <Button variant="primary" size="xl" className="mt-6 h-[72px] w-full text-xl!" disabled={state === "busy"} onClick={send}>
                    {word(lang, "rateSend", "Send")}
                  </Button>
                </motion.div>
              ) : null}
            </AnimatePresence>
          </motion.div>
        )}
      </AnimatePresence>
    </section>
  );
}

