// Menu tiles, the options window (add-ons, meals), and the cart lines. Used by the POS and waiter app.
import { AnimatePresence, motion } from "motion/react";
import { Check, Minus, Pause, Plus, Search, ShoppingBag, Trash2, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { en, money } from "../lib/format";
import type { Menu, MenuItem, Modifier } from "../lib/types";
import { Dish } from "./food";
import { Badge, Button, inputCls, Modal, spring } from "./kit";

export type CartLine = { key: string; item: MenuItem; qty: number; mods: Modifier[]; combo: { choices: string[]; names: string[]; up: number } | null; notes: string; hold: boolean };

export const unitPrice = (c: CartLine): number => (c.item.offer?.price ?? c.item.price) + c.mods.reduce((s, m) => s + m.price_delta, 0) + (c.combo?.up ?? 0);
export const cartTotal = (lines: CartLine[]): number => lines.reduce((s, c) => s + unitPrice(c) * c.qty, 0);
export const toApiLines = (lines: CartLine[], allowHold = true) =>
  lines.map((c) => ({ menu_item_id: c.item.id, quantity: c.qty, modifier_ids: c.mods.map((m) => m.id), notes: c.notes || null, combo_choices: c.combo?.choices ?? [], hold: allowHold && c.hold }));

/** The window's size, kept up to date: layouts change between phone, tablet and laptop, portrait and landscape. */
export function useViewport(): { w: number; h: number } {
  const [v, setV] = useState(() => ({ w: window.innerWidth, h: window.innerHeight }));
  useEffect(() => {
    const on = () => setV({ w: window.innerWidth, h: window.innerHeight });
    window.addEventListener("resize", on);
    return () => window.removeEventListener("resize", on);
  }, []);
  return v;
}

/** A dish's picture as a rectangle (Uber Eats style): the photo, or a soft tinted tile with a line icon. */
function DishPhoto({ item, className = "" }: { item: MenuItem; className?: string }) {
  return <Dish src={item.image_url} name={en(item.name)} hint={en(item.description)} size={88} className={`h-full! w-full! rounded-none! ${item.is_available ? "" : "opacity-60 grayscale"} ${className}`} />;
}

/** The small round white "+" on a dish's photo (Uber Eats). */
function AddDot() {
  return (
    <span className="absolute bottom-2 right-2 grid h-8 w-8 place-items-center rounded-full bg-surface text-ink shadow-[0_2px_8px_rgb(28_43_51/18%)] transition group-hover:bg-ink group-hover:text-surface group-active:scale-90">
      <Plus size={18} strokeWidth={2.5} />
    </span>
  );
}

/** Menu prices read cleaner in whole rupees ("Rs 1,200"); bills and totals keep the cents. */
export const menuPrice = (cents: number): string => (cents % 100 === 0 ? `Rs ${(cents / 100).toLocaleString("en-LK")}` : money(cents));

function Price({ item }: { item: MenuItem }) {
  return (
    <span className="num text-[15px] font-semibold tracking-[-0.01em]">
      {menuPrice(item.offer?.price ?? item.price)}
      {item.offer ? <s className="ml-1.5 text-sm font-normal text-muted">{menuPrice(item.price)}</s> : null}
    </span>
  );
}

/** Each category gets one quiet colour, used as a fine line on its dish tiles (like Square's tiles). */
const CAT_HUES = ["#0866ff", "#0a8f4f", "#b26a00", "#7c4dff", "#00897b", "#c2185b", "#5d6b78"];
export const catHue = (index: number): string => CAT_HUES[index % CAT_HUES.length];

/** A dish without a photo: a text tile — name, a short line, price — elegant like a printed menu. */
function TextTile({ item, label, sub, hue, onPick }: { item: MenuItem; label: string; sub: string; hue: string; onPick: () => void }) {
  return (
    <button disabled={!item.is_available} onClick={onPick} data-item={en(item.name)} className="tile group relative flex min-h-[124px] flex-col overflow-hidden rounded-2xl bg-surface p-4 pt-[18px] text-left ring-1 ring-line transition hover:-translate-y-px hover:shadow-[0_6px_20px_rgb(28_43_51/8%)] hover:ring-ink/15 active:scale-[.98] disabled:opacity-55">
      <span className="absolute inset-x-0 top-0 h-[3px]" style={{ background: hue }} />
      <span className="line-clamp-2 text-[15px] font-semibold leading-snug">{label}</span>
      {sub ? <span className="mt-1 line-clamp-2 text-[13px] leading-snug text-muted">{sub}</span> : null}
      <span className="mt-auto flex items-end justify-between gap-2 pt-3">
        <Price item={item} />
        {item.is_available ? (
          <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-canvas text-ink transition group-hover:bg-ink group-hover:text-white group-active:scale-90">
            <Plus size={17} strokeWidth={2.5} />
          </span>
        ) : (
          <Badge tone="bad">Sold out</Badge>
        )}
      </span>
    </button>
  );
}

/** The menu: search, category pills (blue when chosen), then the dishes. On a big screen the dishes are
 *  cards with the photo on top; `compact` (phones) shows Uber Eats rows with the photo on the right. */
export function MenuGrid({ menu, onPick, compact = false, name = en }: { menu: Menu; onPick: (i: MenuItem) => void; compact?: boolean; name?: (t: MenuItem["name"]) => string }) {
  const cats = menu.categories;
  const [catId, setCat] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const cat = cats.find((c) => c.id === catId) ?? cats[0];
  const items = q.trim() ? cats.flatMap((c) => c.items).filter((i) => en(i.name).toLowerCase().includes(q.trim().toLowerCase())) : (cat?.items ?? []);
  const sub = (i: MenuItem) => en(i.description) || [i.combo_slots.length ? "Meal" : "", ...i.allergens.slice(0, 2)].filter(Boolean).join(" · ");
  return (
    <div className="flex min-h-0 flex-col gap-3">
      <label className="flex h-11 shrink-0 items-center gap-2.5 rounded-full bg-canvas px-4 transition focus-within:bg-surface focus-within:ring-2 focus-within:ring-accent">
        <Search size={18} className="shrink-0 text-muted" />
        <input aria-label="Search menu" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search the menu" className="h-full min-w-0 flex-1 bg-transparent! text-[15px] outline-none placeholder:text-muted" />
        {q ? (
          <button aria-label="Clear search" onClick={() => setQ("")} className="grid h-7 w-7 place-items-center rounded-full text-muted hover:bg-ink/[.05] hover:text-ink">
            <X size={16} />
          </button>
        ) : null}
      </label>
      <div className="chips -mx-1 flex shrink-0 gap-2 overflow-x-auto px-1 py-0.5 [scrollbar-width:none]">
        {cats.map((c) => {
          const on = c.id === cat?.id && !q.trim();
          return (
            <button key={c.id} onClick={() => (setCat(c.id), setQ(""))} className={`chip relative h-9 shrink-0 rounded-full px-4 text-sm font-semibold transition-colors active:scale-[.97] ${on ? "text-accent" : "bg-canvas text-ink hover:bg-line"}`}>
              {on ? <motion.span layoutId="menu-cat" transition={spring} className="absolute inset-0 rounded-full bg-accent-soft" /> : null}
              <span className="relative">{en(c.name)}</span>
            </button>
          );
        })}
      </div>
      <AnimatePresence mode="wait" initial={false}>
        <motion.div
          key={q.trim() ? "q" : (cat?.id ?? "")}
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -4 }}
          transition={{ duration: 0.16 }}
          className={compact ? "flex flex-col divide-y divide-line" : "grid grid-cols-[repeat(auto-fill,minmax(176px,1fr))] gap-3 pt-1"}
        >
          {!q.trim() && cat ? <h3 className={`text-lg font-bold tracking-tight ${compact ? "pb-1 pt-2" : "col-span-full -mb-1"}`}>{en(cat.name)}</h3> : null}
          {items.map((i) => {
            const hue = catHue(Math.max(0, cats.findIndex((c) => c.items.some((x) => x.id === i.id))));
            if (compact)
              return (
                <button key={i.id} disabled={!i.is_available} onClick={() => onPick(i)} data-item={en(i.name)} className="tile group flex items-center gap-4 py-3.5 text-left transition active:bg-ink/[.02] disabled:opacity-55">
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[15px] font-semibold">{name(i.name)}</span>
                    {sub(i) ? <span className="mt-0.5 line-clamp-1 text-sm leading-snug text-muted">{sub(i)}</span> : null}
                    <span className="mt-1 block"><Price item={i} /></span>
                  </span>
                  {i.image_url ? (
                    <span className="relative h-[80px] w-[96px] shrink-0 overflow-hidden rounded-xl bg-canvas">
                      <DishPhoto item={i} />
                      {i.is_available ? <AddDot /> : <Badge tone="bad" className="absolute bottom-2 left-2">Sold out</Badge>}
                    </span>
                  ) : i.is_available ? (
                    <span className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-canvas text-ink transition group-hover:bg-ink group-hover:text-white">
                      <Plus size={18} strokeWidth={2.5} />
                    </span>
                  ) : (
                    <Badge tone="bad">Sold out</Badge>
                  )}
                </button>
              );
            if (!i.image_url) return <TextTile key={i.id} item={i} label={name(i.name)} sub={sub(i)} hue={hue} onPick={() => onPick(i)} />;
            return (
              <button key={i.id} disabled={!i.is_available} onClick={() => onPick(i)} data-item={en(i.name)} className="tile group flex flex-col overflow-hidden rounded-2xl bg-surface text-left ring-1 ring-line transition hover:-translate-y-px hover:shadow-[0_6px_20px_rgb(28_43_51/8%)] active:scale-[.98] disabled:opacity-55">
                <span className="relative aspect-[16/10] w-full overflow-hidden bg-canvas">
                  <DishPhoto item={i} className="transition duration-300 group-hover:scale-[1.03]" />
                  {i.is_available ? <AddDot /> : <Badge tone="bad" className="absolute bottom-2 left-2">Sold out</Badge>}
                </span>
                <span className="flex flex-1 flex-col p-3.5">
                  <span className="line-clamp-1 text-[15px] font-semibold leading-snug">{name(i.name)}</span>
                  {sub(i) ? <span className="line-clamp-1 text-[13px] text-muted">{sub(i)}</span> : null}
                  <span className="mt-auto pt-2"><Price item={i} /></span>
                </span>
              </button>
            );
          })}
          {!items.length ? <p className="col-span-full py-10 text-center text-muted">{q.trim() ? `Nothing called “${q.trim()}”.` : "Nothing here right now."}</p> : null}
        </motion.div>
      </AnimatePresence>
    </div>
  );
}

/** Ask for add-ons and meal choices when the item has them; otherwise add straight away. */
export function useOptions(menu: Menu | null) {
  const [item, setItem] = useState<MenuItem | null>(null);
  const [resolve, setResolve] = useState<((c: Omit<CartLine, "key" | "qty" | "hold"> | null) => void) | null>(null);
  const ask = (i: MenuItem) =>
    new Promise<Omit<CartLine, "key" | "qty" | "hold"> | null>((res) => {
      if (!i.modifier_groups.length && !i.combo_slots.length) return res({ item: i, mods: [], combo: null, notes: "" });
      setItem(i);
      setResolve(() => res);
    });
  const modal = item && menu ? <OptionsModal item={item} menu={menu} onClose={(c) => (resolve?.(c), setItem(null))} /> : null;
  return { ask, modal };
}

function OptionsModal({ item, menu, onClose }: { item: MenuItem; menu: Menu; onClose: (c: Omit<CartLine, "key" | "qty" | "hold"> | null) => void }) {
  const [chosen, setChosen] = useState<Record<string, string[]>>({});
  const [picks, setPicks] = useState<(string | null)[]>(item.combo_slots.map(() => null));
  const [notes, setNotes] = useState("");
  const allItems = useMemo(() => Object.fromEntries(menu.categories.flatMap((c) => c.items).map((i) => [i.id, i])), [menu]);
  const valid = item.modifier_groups.every((g) => (chosen[g.id]?.length ?? 0) >= g.min_select) && picks.every(Boolean);
  const mods = item.modifier_groups.flatMap((g) => g.modifiers.filter((m) => chosen[g.id]?.includes(m.id)));
  const up = picks.reduce((s, id, i) => s + (id ? item.combo_slots[i].upcharges?.[id] ?? 0 : 0), 0);
  const unit = item.price + mods.reduce((s, m) => s + m.price_delta, 0) + up;
  // Uber Eats style: each choice is a row with a round (one) or square (many) check on the right.
  const Row = ({ on, disabled = false, multi, label, extra, onClick }: { on: boolean; disabled?: boolean; multi: boolean; label: string; extra: number; onClick: () => void }) => (
    <button disabled={disabled} onClick={onClick} className="flex w-full items-center gap-3 py-3 text-left transition active:bg-ink/[.02] disabled:opacity-40">
      <span className="min-w-0 flex-1">
        <span className="block text-[15px] font-medium">{label}</span>
        {extra ? <span className="num block text-sm text-muted">+{money(extra)}</span> : null}
      </span>
      <span className={`grid h-6 w-6 shrink-0 place-items-center transition ${multi ? "rounded-md" : "rounded-full"} ${on ? "bg-accent text-white" : "ring-2 ring-inset ring-ink/20"}`}>
        {on ? <Check size={15} strokeWidth={3} /> : null}
      </span>
    </button>
  );
  const Head = ({ title, need, req }: { title: string; need: string; req: boolean }) => (
    <div className="flex items-center justify-between gap-3 pb-1">
      <div>
        <div className="text-[17px] font-bold">{title}</div>
        <div className="text-sm text-muted">{need}</div>
      </div>
      {req ? <Badge>Required</Badge> : null}
    </div>
  );
  return (
    <Modal
      open
      onClose={() => onClose(null)}
      title={en(item.name)}
      footer={
        <Button
          variant="primary"
          size="lg"
          className="w-full"
          disabled={!valid}
          onClick={() =>
            onClose({ item, mods, notes, combo: item.combo_slots.length ? { choices: picks as string[], names: picks.map((id) => en(allItems[id!]?.name ?? menu.combo_parts[id!]?.name)), up } : null })
          }
        >
          Add to order · {money(unit)}
        </Button>
      }
    >
      <div className="flex flex-col gap-6">
        {en(item.description) ? <p className="-mt-1 text-[15px] text-muted">{en(item.description)}</p> : null}
        {item.combo_slots.map((slot, si) => (
          <div key={si}>
            <Head title={en(slot.name)} need="Choose 1" req />
            <div className="divide-y divide-line">
              {slot.item_ids.map((id) => {
                const part = allItems[id] ?? { name: menu.combo_parts[id]?.name, is_available: menu.combo_parts[id]?.is_available ?? true };
                return <Row key={id} multi={false} disabled={!part.is_available} on={picks[si] === id} label={en(part.name)} extra={slot.upcharges?.[id] ?? 0} onClick={() => setPicks((p) => p.map((x, i) => (i === si ? id : x)))} />;
              })}
            </div>
          </div>
        ))}
        {item.modifier_groups.map((g) => (
          <div key={g.id}>
            <Head title={en(g.name)} need={g.min_select ? `Choose ${g.min_select === g.max_select ? g.min_select : `${g.min_select} to ${g.max_select}`}` : `Choose up to ${g.max_select}`} req={g.min_select > 0} />
            <div className="divide-y divide-line">
              {g.modifiers.map((m) => {
                const on = !!chosen[g.id]?.includes(m.id);
                return (
                  <Row
                    key={m.id}
                    multi={g.max_select > 1}
                    on={on}
                    label={en(m.name)}
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
            </div>
          </div>
        ))}
        <input value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Note for the kitchen (optional)" maxLength={300} className={inputCls} />
      </div>
    </Modal>
  );
}

export function CartLines({ lines, setLines, allowHold, name = en }: { lines: CartLine[]; setLines: (l: CartLine[]) => void; allowHold: boolean; name?: (t: MenuItem["name"]) => string }) {
  const upd = (key: string, f: (c: CartLine) => CartLine | null) => setLines(lines.flatMap((c) => (c.key === key ? (f(c) ? [f(c)!] : []) : [c])));
  return (
    <div className="flex flex-col divide-y divide-line">
      <AnimatePresence initial={false} mode="popLayout">
        {lines.length ? (
          lines.map((c) => (
            <motion.div
              key={c.key}
              layout
              initial={{ opacity: 0, y: -8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, x: 40, transition: { duration: 0.18 } }}
              transition={spring}
              className="py-3"
            >
              <div className="flex items-start gap-3">
                <Dish src={c.item.image_url} name={en(c.item.name)} size={48} />
                <div className="min-w-0 flex-1">
                  <div className="truncate font-semibold leading-snug">{name(c.item.name)}</div>
                  {c.mods.length || c.combo || c.notes ? <div className="truncate text-sm text-muted">{[...(c.combo?.names ?? []), ...c.mods.map((m) => en(m.name)), c.notes].filter(Boolean).join(" · ")}</div> : <div className="num text-sm text-muted">{money(unitPrice(c))} each</div>}
                </div>
                <div className="num shrink-0 font-semibold">{money(unitPrice(c) * c.qty)}</div>
              </div>
              <div className="mt-2 flex items-center gap-2 pl-[60px]">
                <span className="inline-flex h-8 items-center rounded-full bg-canvas">
                  <button aria-label="Less" className="grid h-8 w-8 place-items-center rounded-full transition hover:bg-ink/[.06] active:scale-90" onClick={() => upd(c.key, (x) => (x.qty > 1 ? { ...x, qty: x.qty - 1 } : null))}>
                    {c.qty > 1 ? <Minus size={15} strokeWidth={2.5} /> : <Trash2 size={14} />}
                  </button>
                  <motion.span key={c.qty} initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }} className="num w-6 text-center text-sm font-bold">
                    {c.qty}
                  </motion.span>
                  <button aria-label="More" className="grid h-8 w-8 place-items-center rounded-full transition hover:bg-ink/[.06] active:scale-90" onClick={() => upd(c.key, (x) => ({ ...x, qty: Math.min(99, x.qty + 1) }))}>
                    <Plus size={15} strokeWidth={2.5} />
                  </button>
                </span>
                {allowHold ? (
                  <button title="Keep it until you fire the next course" onClick={() => upd(c.key, (x) => ({ ...x, hold: !x.hold }))} className={`ml-auto inline-flex h-8 items-center gap-1 rounded-full px-3 text-xs font-semibold transition ${c.hold ? "bg-accent-soft text-accent" : "text-muted hover:bg-ink/[.05] hover:text-ink"}`}>
                    <Pause size={12} strokeWidth={2.5} />
                    {c.hold ? "Held" : "Hold"}
                  </button>
                ) : null}
              </div>
            </motion.div>
          ))
        ) : (
          <motion.div key="empty" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="grid place-items-center gap-3 py-12 text-center text-muted">
            <span className="grid h-14 w-14 place-items-center rounded-full bg-canvas text-muted">
              <ShoppingBag size={24} />
            </span>
            Tap a dish to add it.
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

/** The totals under a cart, like a receipt: subtotal, discount, taxes, and the big total. */
export function CartSummary({ quote, fallback, labels }: { quote: { subtotal: number; discount_total: number; tax_lines: { name: { en?: string }; amount: number; rate_bp?: number }[]; total: number } | null; fallback: number; labels?: { subtotal?: string; discount?: string; total?: string } }) {
  return (
    <div className="border-t border-line pt-3">
      {quote ? (
        <div className="space-y-1 text-sm">
          <div className="flex justify-between text-muted">
            <span>{labels?.subtotal ?? "Subtotal"}</span>
            <span className="num text-ink">{money(quote.subtotal)}</span>
          </div>
          {quote.discount_total ? (
            <div className="flex justify-between text-muted">
              <span>{labels?.discount ?? "Discount"}</span>
              <span className="num text-ok">− {money(quote.discount_total)}</span>
            </div>
          ) : null}
          {quote.tax_lines.map((t, i) => (
            <div key={i} className="flex justify-between text-muted">
              <span>
                {en(t.name)}
                {t.rate_bp ? ` ${t.rate_bp / 100}%` : ""}
              </span>
              <span className="num">{money(t.amount)}</span>
            </div>
          ))}
        </div>
      ) : null}
      <div className={`flex items-baseline justify-between ${quote ? "mt-2.5" : ""}`}>
        <span className="text-[17px] font-bold">{labels?.total ?? "Total"}</span>
        <motion.span key={quote?.total ?? fallback} initial={{ opacity: 0.4 }} animate={{ opacity: 1 }} className="num text-xl font-bold tracking-tight">
          {money(quote?.total ?? fallback)}
        </motion.span>
      </div>
    </div>
  );
}
