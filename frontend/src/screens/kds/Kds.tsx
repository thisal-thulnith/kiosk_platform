// Kitchen display: tickets by station, rush and VIP first, then by promised time. Tap an item to
// start it, tap again when done; Bump finishes the ticket. Recall, remake with a reason, sold out.
// Keys (bump bar): 1-9 select a ticket, Enter bump, F fire held, R recall. Always dark; tickets glide
// into place as others leave.
import { AnimatePresence, motion } from "motion/react";
import { Ban, Check, ChefHat, CircleCheck, Clock, Crown, Flame, Monitor, RotateCcw, Store, TriangleAlert, Utensils, Zap } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import type { Device } from "../../lib/device";
import { clock, en } from "../../lib/format";
import { chime, unlockSound } from "../../lib/sound";
import type { Me, Menu, OrderItem } from "../../lib/types";
import { useLive } from "../../ui/hooks";
import { Button, LivePill, Modal, SkeletonList, spring, useToast } from "../../ui/kit";
import { Logo } from "../../ui/logo";

type Ticket = { order_id: string; priority: string; promised_at: string | null; token: string; channel: string; table_ref: string | null; status: string; notes: string | null; age_seconds: number; colour: "green" | "yellow" | "red"; items: OrderItem[]; held: number };
type Load = { level: "normal" | "busy" | "overloaded"; open_tickets: number; score_minutes: number };
const REASONS = [["burnt", "Burnt"], ["dropped", "Dropped"], ["wrong_item", "Wrong item"], ["guest_complaint", "Guest complaint"], ["quality", "Quality"], ["other", "Other"]];
// Kitchens stay dark whatever the restaurant's theme (v4 dark: a soft charcoal page, raised grey
// tickets, light ink, the accent blue for what is cooking now): the shared colour tokens, re-set here.
const DARK = {
  "--color-canvas": "#18191a",
  "--color-surface": "#242526",
  "--color-ink": "#e4e6eb",
  "--color-muted": "#b0b3b8",
  "--color-line": "#3a3b3c",
  "--color-accent": "#2d88ff",
  "--color-accent-soft": "#1d3557",
  "--color-ok": "#31a24c",
  "--color-warn": "#f7b928",
  "--color-bad": "#f3425f",
  "--color-info": "#2d88ff",
  "--color-ok-soft": "color-mix(in oklab, #31a24c 22%, #242526)",
  "--color-warn-soft": "color-mix(in oklab, #f7b928 18%, #242526)",
  "--color-bad-soft": "color-mix(in oklab, #f3425f 22%, #242526)",
  "--color-info-soft": "#1d3557",
  "--color-brand-soft": "color-mix(in oklab, var(--color-brand) 22%, #242526)",
  "--shadow-soft": "0 0 0 1px rgb(255 255 255 / 6%)",
  colorScheme: "dark",
} as React.CSSProperties;
const TONE = { ok: { bar: "bg-ok", pill: "bg-ok-soft text-ok" }, warn: { bar: "bg-warn", pill: "bg-warn-soft text-warn" }, bad: { bar: "bg-bad", pill: "bg-bad-soft text-bad" } };
const fmt = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;

export function Kds({ device, me }: { device: Device; me: Me }) {
  const toast = useToast();
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [load, setLoad] = useState<Load | null>(null);
  const [loadedAt, setLoadedAt] = useState(Date.now());
  const [now, setNow] = useState(Date.now());
  const [sel, setSel] = useState(0);
  const [remake, setRemake] = useState<{ order: string; item: OrderItem } | null>(null);
  const [soldOut, setSoldOut] = useState(false);
  const station = me.device.station;

  const reload = useCallback(async () => {
    const q = station ? `?station=${encodeURIComponent(station)}` : "";
    const [t, l] = await Promise.all([device.get<{ tickets: Ticket[] }>(`/v1/kds/tickets${q}`), device.get<Load>("/v1/kds/load")]);
    setTickets((old) => {
      const known = new Set(old.map((x) => x.order_id));
      if (t.tickets.some((x) => !known.has(x.order_id) && x.status === "in_kitchen") && old.length) chime([740, 990]);
      return t.tickets;
    });
    setLoad(l);
    setLoadedAt(Date.now());
  }, [device, station]);
  useEffect(() => {
    void reload();
    const a = setInterval(() => setNow(Date.now()), 1000);
    const b = setInterval(reload, 30000);
    return () => (clearInterval(a), clearInterval(b));
  }, []);
  const live = useLive(device, (ev) => {
    if (ev.type === "order.voided" && ev.data?.order) {
      chime([330, 220, 330]);
      toast(`${ev.data.order.token} VOIDED — stop cooking`, "bad", 12000);
    }
    if (ev.type === "order.priority" && ev.data?.order) toast(`${ev.data.order.token} is now ${ev.data.order.priority.toUpperCase()}`, "info", 6000);
    if (ev.type === "stock.low") toast(`${en(ev.data.name)}: only ${ev.data.on_hand} left`, "info", 8000);
    void reload();
  });

  const post = async (path: string, body: unknown = {}) => {
    try {
      await device.post(path, body);
      await reload();
    } catch (x) {
      toast((x as Error).message, "bad");
    }
  };
  const tapItem = (t: Ticket, i: OrderItem) => {
    if (i.kds_status === "queued") return post(`/v1/kds/orders/${t.order_id}/items/${i.id}/start`);
    if (i.kds_status === "in_progress") return post(`/v1/kds/orders/${t.order_id}/items/${i.id}/done`);
    if (i.kds_status === "done") return setRemake({ order: t.order_id, item: i });
  };
  const bump = (t: Ticket) => post(`/v1/kds/orders/${t.order_id}/bump`, station ? { station } : {});
  useEffect(() => {
    const k = (e: KeyboardEvent) => {
      const t = tickets[sel];
      if (/^[1-9]$/.test(e.key)) setSel(Number(e.key) - 1);
      else if (e.key === "Enter" && t) void bump(t);
      else if (e.key.toLowerCase() === "f" && t?.held) void post(`/v1/orders/${t.order_id}/fire`, {});
      else if (e.key.toLowerCase() === "r") void post("/v1/kds/recall", station ? { station } : {});
    };
    document.addEventListener("keydown", k);
    return () => document.removeEventListener("keydown", k);
  });


  const extra = Math.floor((now - loadedAt) / 1000);
  const loadTone: keyof typeof TONE = load?.level === "overloaded" ? "bad" : load?.level === "busy" ? "warn" : "ok";
  // Dark on the whole page, so windows (remake, sold out) and messages are dark too.
  useEffect(() => {
    const root = document.documentElement;
    Object.entries(DARK).forEach(([k, v]) => k.startsWith("--") && root.style.setProperty(k, String(v)));
    root.style.colorScheme = "dark";
  }, []);
  return (
    <div className="flex h-full flex-col bg-canvas text-ink" style={DARK} onPointerDown={unlockSound}>
      <header className="flex shrink-0 items-center gap-2 border-b border-line bg-surface px-4 py-3 sm:px-5">
        <span className="hidden shrink-0 sm:block"><Logo url={me.venue.brand?.logo_url} name={me.venue.name} size={40} /></span>
        <div className="mr-1 min-w-0 flex-1">
          <div className="truncate text-xl font-bold tracking-tight">
            Kitchen <span className="font-semibold text-muted">· {me.device.name}</span>
          </div>
          <div className="truncate text-sm text-muted">{station ? `Station: ${station}` : "All stations"} · {me.venue.name}</div>
        </div>
        {load ? (
          <span className={`inline-flex h-10 shrink-0 items-center gap-2 rounded-full px-3.5 text-sm font-semibold sm:px-4 ${TONE[loadTone].pill}`}>
            <span className={`h-2 w-2 rounded-full ${TONE[loadTone].bar} ${load.level !== "normal" ? "animate-pulse" : ""}`} />
            <span className="hidden md:inline">{load.level === "normal" ? "Kitchen OK" : load.level === "busy" ? "Busy" : "Overloaded"} · </span>
            <span className="num">{load.open_tickets}</span> open
          </span>
        ) : null}
        <Button variant="soft" className="rounded-full bg-ink/[.08]! hover:bg-ink/[.14]!" onClick={() => post("/v1/kds/recall", station ? { station } : {})}>
          <RotateCcw size={18} /> <span className="hidden sm:inline">Recall</span>
        </Button>
        <Button variant="soft" className="rounded-full bg-ink/[.08]! hover:bg-ink/[.14]!" onClick={() => setSoldOut(true)}>
          <Ban size={18} /> <span className="hidden sm:inline">Sold out</span>
        </Button>
        <LivePill status={live.status} via={live.via} />
      </header>
      <main className="min-h-0 flex-1 overflow-auto p-3 sm:p-4">
        <div className="grid auto-rows-min grid-cols-[repeat(auto-fill,minmax(min(100%,300px),1fr))] items-start gap-3 sm:gap-4 2xl:grid-cols-[repeat(auto-fill,minmax(340px,1fr))]">
          <AnimatePresence mode="popLayout" initial={false}>
            {tickets.map((t, idx) => {
              const age = t.age_seconds + extra;
              const late = !!t.promised_at && new Date(t.promised_at).getTime() < now;
              const tone: keyof typeof TONE = t.colour === "red" ? "bad" : t.colour === "yellow" ? "warn" : "ok";
              const on = sel === idx;
              const Where = t.table_ref ? Utensils : t.channel === "kiosk" ? Monitor : Store;
              return (
                <motion.div
                  key={t.order_id}
                  layout
                  data-token={t.token}
                  onClick={() => setSel(idx)}
                  initial={{ opacity: 0, y: 24, scale: 0.96 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  exit={{ opacity: 0, scale: 0.9, transition: { duration: 0.2 } }}
                  transition={spring}
                  className={`flex flex-col overflow-hidden rounded-2xl bg-surface transition-shadow ${on ? "ring-2 ring-accent" : "ring-1 ring-white/[.06]"}`}
                >
                  <div className="flex items-start justify-between gap-3 border-b border-line px-4 pb-3 pt-4">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2.5">
                        <span className={`num grid h-7 min-w-7 place-items-center rounded-md px-1 text-sm font-bold ${on ? "bg-accent text-white" : "bg-ink/10 text-muted"}`}>{idx + 1}</span>
                        <span className="num text-[32px] font-bold leading-none tracking-tight">{t.token}</span>
                        {t.priority === "rush" ? (
                          <span className="inline-flex items-center gap-1 rounded-full bg-bad px-2.5 py-1 text-xs font-bold text-white">
                            <Zap size={13} /> RUSH
                          </span>
                        ) : t.priority === "vip" ? (
                          <span className="inline-flex items-center gap-1 rounded-full bg-warn-soft px-2.5 py-1 text-xs font-bold text-warn">
                            <Crown size={13} /> VIP
                          </span>
                        ) : t.priority !== "normal" ? (
                          <span className="rounded-full bg-ink/10 px-2.5 py-1 text-xs font-bold">{t.priority.toUpperCase()}</span>
                        ) : null}
                      </div>
                      <div className="mt-2 flex flex-wrap items-center gap-1.5 text-sm font-medium text-muted">
                        <Where size={15} />
                        {t.table_ref ? `Table ${t.table_ref}` : t.channel === "kiosk" ? "Kiosk" : "Counter"}
                        {t.promised_at && !late ? <span>· Due {clock(t.promised_at)}</span> : null}
                      </div>
                      {late ? (
                        <div className="mt-1 flex items-center gap-1.5 text-sm font-bold text-bad">
                          <TriangleAlert size={15} /> Late · due {clock(t.promised_at)}
                        </div>
                      ) : null}
                    </div>
                    <span className={`num inline-flex shrink-0 items-center gap-1.5 rounded-full px-3 py-1.5 text-lg font-semibold ${TONE[tone].pill}`}>
                      <Clock size={16} />
                      {fmt(age)}
                    </span>
                  </div>
                  <div className="flex flex-1 flex-col gap-1 px-2 py-2">
                    {t.items.map((i) => {
                      const st = i.kds_status;
                      return (
                        <button
                          key={i.id}
                          onClick={(e) => (e.stopPropagation(), void tapItem(t, i))}
                          className={`flex items-start gap-3 rounded-xl px-2.5 py-2.5 text-left transition active:scale-[.99] ${st === "done" ? "opacity-40" : st === "in_progress" ? "bg-accent-soft" : st === "held" ? "border border-dashed border-muted/40" : "hover:bg-ink/[.05]"}`}
                        >
                          <span className={`num grid h-8 min-w-8 shrink-0 place-items-center rounded-full px-1.5 text-base font-bold ${st === "in_progress" ? "bg-accent text-white" : st === "done" ? "bg-ok text-white" : "bg-ink/10"}`}>
                            {st === "done" ? <Check size={17} strokeWidth={3} /> : st === "in_progress" ? <ChefHat size={17} /> : i.quantity}
                          </span>
                          <span className="min-w-0 flex-1">
                            <span className={`block text-[19px] font-semibold leading-snug ${st === "done" ? "line-through" : st === "in_progress" ? "text-white" : ""}`}>
                              {st === "done" || st === "in_progress" ? `${i.quantity} × ` : ""}
                              {en(i.name)} {st === "held" ? <span className="ml-1 rounded-full bg-warn-soft px-2 py-0.5 text-xs font-bold text-warn">HELD</span> : null}
                            </span>
                            {i.modifiers.length ? <span className="block text-[15px] text-muted">{i.modifiers.map((m) => `+ ${en(m.name)}`).join("  ")}</span> : null}
                            {i.notes ? <span className="mt-1 block rounded-lg bg-warn-soft px-2 py-1 text-sm font-semibold text-warn">{i.notes}</span> : null}
                            {i.allergens.length ? (
                              <span className="mt-1 flex items-center gap-1 text-sm font-bold text-bad">
                                <TriangleAlert size={14} /> {i.allergens.join(", ")}
                              </span>
                            ) : null}
                          </span>
                        </button>
                      );
                    })}
                  </div>
                  <div className="flex gap-2 border-t border-line p-3">
                    {t.held ? (
                      <Button variant="soft" size="lg" className="flex-1 bg-ink/[.08]! hover:bg-ink/[.14]!" onClick={() => post(`/v1/orders/${t.order_id}/fire`, {})}>
                        <Flame size={19} /> Fire {t.held} held
                      </Button>
                    ) : null}
                    <Button variant={t.status === "ready" ? "soft" : "primary"} size="lg" className={`flex-1 shadow-none ${t.status === "ready" ? "bg-ok-soft! text-ok!" : "text-canvas! hover:bg-white!"}`} onClick={() => bump(t)}>
                      <Check size={20} strokeWidth={2.6} />
                      {t.status === "ready" ? "Done" : "Bump"}
                    </Button>
                  </div>
                </motion.div>
              );
            })}
          </AnimatePresence>
        </div>
        <AnimatePresence>
          {!tickets.length ? (
            <motion.div key="clear" initial={{ opacity: 0, scale: 0.96 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0 }} transition={{ ...spring, delay: 0.15 }} className="grid place-items-center gap-5 py-32 text-center">
              <span className="grid h-24 w-24 place-items-center rounded-full bg-ok-soft text-ok">
                <CircleCheck size={48} strokeWidth={1.8} />
              </span>
              <span className="text-3xl font-bold tracking-tight">All clear</span>
              <span className="-mt-3 text-lg text-muted">New tickets appear here</span>
            </motion.div>
          ) : null}
        </AnimatePresence>
      </main>
      {remake ? (
        <Modal open onClose={() => setRemake(null)} title={`Remake ${en(remake.item.name)}?`}>
          <div className="grid grid-cols-2 gap-2">
            {REASONS.map(([code, label]) => (
              <Button key={code} size="lg" onClick={() => (post(`/v1/kds/orders/${remake.order}/items/${remake.item.id}/remake`, { reason: code }), setRemake(null))}>
                {label}
              </Button>
            ))}
          </div>
        </Modal>
      ) : null}
      {soldOut ? <SoldOut device={device} station={station} onClose={() => setSoldOut(false)} /> : null}
    </div>
  );
}

function SoldOut({ device, station, onClose }: { device: Device; station: string | null; onClose: () => void }) {
  const [menu, setMenu] = useState<Menu | null>(null);
  const load = () => device.get<Menu>("/v1/menu").then(setMenu);
  useEffect(() => void load(), []);
  const items = menu?.categories.flatMap((c) => c.items).filter((i) => !station || i.station === station) ?? [];
  return (
    <Modal open onClose={onClose} title="Sold out">
      <p className="mb-3 text-sm text-muted">Switching a dish off hides it on every screen at once.</p>
      {!menu ? (
        <SkeletonList rows={5} />
      ) : (
        <div className="flex flex-col gap-1">
          {items.map((i) => (
            <button key={i.id} onClick={() => device.put(`/v1/menu/items/${i.id}/availability`, { is_available: !i.is_available }).then(load)} className="flex min-h-14 items-center justify-between gap-3 rounded-2xl px-3 py-2 text-left transition hover:bg-ink/[.04]">
              <span className={`font-semibold ${i.is_available ? "" : "text-muted line-through"}`}>{en(i.name)}</span>
              <span className={`relative h-8 w-14 shrink-0 rounded-full transition-colors ${i.is_available ? "bg-ok" : "bg-line"}`} aria-label={i.is_available ? "Available" : "Sold out"}>
                <motion.span layout transition={spring} className={`absolute top-1 h-6 w-6 rounded-full bg-white shadow ${i.is_available ? "right-1" : "left-1"}`} />
              </span>
            </button>
          ))}
        </div>
      )}
    </Modal>
  );
}
