// Owner app: Menu & stock, and Settings (look, screens, AI, guests).
import { consoleUrl } from "../../lib/screens";
import { AnimatePresence, motion } from "motion/react";
import { Clock, Download, MonitorSmartphone, PackagePlus, Search, Sparkles, Trash2, UserX, Warehouse } from "lucide-react";
import { useState } from "react";
import { ago, money } from "../../lib/format";
import { BrandEditor } from "../../ui/brandEditor";
import { Dish } from "../../ui/food";
import { Avatar } from "../../ui/logo";
import { Badge, Button, Card, Empty, Field, Input, MoreMenu, SectionTitle, Skeleton, SkeletonList, Status, inputCls, useToast } from "../../ui/kit";
import { Kpi, KpiSkeleton, KpiStrip, Panel, Rows, SubNav, TableHead, clockOf, tableRow, usePrompt } from "./bits";
import { useReport, type Ctx, type SubProps } from "./Owner";

type Name = { en?: string };

// ------------------------------------------------------------------ menu & stock

type StockRow = { menu_item_id: string; name: Name; on_hand: number; low_at: number; state: "ok" | "low" | "out"; perishable_until: string | null };
type Stock = { items: StockRow[]; moves: { at: string; name: Name | null; change: number; reason: string }[] };
const STATE = { ok: ["ok", "OK"], low: ["warn", "Low"], out: ["bad", "Out"] } as const;

export function StockPage(ctx: Ctx) {
  const toast = useToast();
  const { prompt, modal } = usePrompt();
  const [stock, reload, failed] = useReport<Stock>(ctx, "/stock", false);
  const [items] = useReport<{ id: string; name: Name; combo_slots?: unknown[] }[]>(ctx, "/menu/items", false);
  const [pick, setPick] = useState("");
  const [qty, setQty] = useState("20");
  const [moves, setMoves] = useState(false);
  const call = async (method: string, path: string, body: unknown, msg: string) => {
    try {
      await ctx.admin.api(method, ctx.admin.v(path), body);
      toast(msg, "ok");
      reload();
    } catch (e) {
      toast((e as Error).message, "bad");
    }
  };
  const move = async (s: StockRow, kind: string, title: string) => {
    const n = await prompt(`${s.name.en}: ${title}`, "number", kind === "count" ? String(s.on_hand) : "");
    if (n) void call("POST", `/stock/${s.menu_item_id}/moves`, { kind, quantity: Number(n) }, "Stock updated");
  };
  const useBy = async (s: StockRow) => {
    const t = await prompt(`${s.name.en}: use by (empty clears it)`, "time", s.perishable_until ? new Date(s.perishable_until).toTimeString().slice(0, 5) : "");
    if (t === null) return;
    if (!t) return call("PUT", `/stock/${s.menu_item_id}`, { clear_perishable: true }, "Use-by cleared");
    const [hh, mm] = t.split(":").map(Number);
    const d = new Date();
    d.setHours(hh, mm, 0, 0);
    if (d < new Date()) d.setDate(d.getDate() + 1); // 00:30 typed at 23:40 means tomorrow
    void call("PUT", `/stock/${s.menu_item_id}`, { perishable_until: d.toISOString() }, "Use-by saved");
  };
  const tracked = new Set(stock?.items.map((s) => s.menu_item_id) ?? []);
  const low = stock?.items.filter((s) => s.state !== "ok").length ?? 0;

  const row = tableRow(STOCK_COLS);

  if (!stock)
    return failed ? (
      <Card>
        <Empty icon={<Warehouse size={24} />} action={<a href={consoleUrl("menu", ctx.admin.venue?.code)} className="text-sm font-semibold text-accent hover:underline">Open the menu editor</a>}>
          Stock tracking (Inventory) is not in this package.
        </Empty>
      </Card>
    ) : (
      <div className="flex flex-col gap-4">
        <KpiSkeleton />
        <SkeletonList rows={4} />
      </div>
    );
  const out = stock.items.filter((s) => s.state === "out").length;
  return (
    <div className="flex flex-col gap-4">
      {modal}
      <KpiStrip>
        <Kpi label="Items counted" value={stock.items.length} hint="sold out by themselves at zero" />
        <Kpi label="Running low" value={low - out} tone={low - out ? "warn" : undefined} />
        <Kpi label="Out" value={out} tone={out ? "bad" : undefined} />
        <Kpi label="Latest moves" value={stock.moves.length} hint="deliveries, counts, waste" />
      </KpiStrip>
      <div className="grid items-start gap-4 xl:grid-cols-[minmax(0,1fr)_380px] 2xl:grid-cols-[minmax(0,1fr)_420px]">
        <Panel title="Stock" hint={stock.items.length ? (low ? `${low} running low or out` : "Everything is in stock") : undefined}>
          <TableHead cols={STOCK_COLS}>
            <span>Item</span>
            <span>Left</span>
            <span>Alert at</span>
            <span>Use by</span>
            <span />
          </TableHead>
          {stock.items.length ? null : <Empty icon={<Warehouse size={24} />}>Nothing counted yet. Pick an item to start counting it.</Empty>}
          <AnimatePresence initial={false}>
            {stock.items.map((s) => (
              <motion.div key={s.menu_item_id} layout initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0, height: 0 }} style={row.style} className={`flex items-center gap-3 border-t border-line px-4 py-3 sm:px-5 ${row.cls}`}>
                <span className="flex min-w-0 flex-1 items-center gap-3">
                  <Dish name={s.name.en ?? ""} size={44} />
                  <span className="min-w-0">
                    <span className="flex items-center gap-2 font-semibold">
                      <span className="truncate">{s.name.en}</span> <Badge tone={STATE[s.state][0]}>{STATE[s.state][1]}</Badge>
                    </span>
                    <span className="block truncate text-sm text-muted lg:hidden">{`${s.on_hand} left · alert at ${s.low_at}${s.perishable_until ? ` · use by ${clockOf(s.perishable_until)}` : ""}`}</span>
                  </span>
                </span>
                <span className={`num hidden text-right text-[15px] font-bold lg:block ${s.state === "out" ? "text-bad" : s.state === "low" ? "text-warn" : ""}`}>{s.on_hand}</span>
                <span className="num hidden text-right text-[15px] text-muted lg:block">{s.low_at}</span>
                <span className="num hidden text-right text-[15px] text-muted lg:block">{s.perishable_until ? clockOf(s.perishable_until) : "—"}</span>
                <span className="flex shrink-0 items-center justify-end gap-1">
                  <Button size="sm" onClick={() => move(s, "delivery", "how many arrived?")}>
                    <PackagePlus size={16} /> <span className="max-sm:hidden">Delivery</span>
                  </Button>
                  <MoreMenu
                    items={[
                      { label: "Count the shelf", onClick: () => move(s, "count", "how many on the shelf?") },
                      { label: "Wasted", onClick: () => move(s, "waste", "how many wasted?") },
                      { label: "Use by…", icon: <Clock size={18} />, onClick: () => useBy(s) },
                      { label: "Stop counting", icon: <Trash2 size={18} />, danger: true, onClick: () => confirm(`Stop counting ${s.name.en}?`) && call("DELETE", `/stock/${s.menu_item_id}`, undefined, "No longer tracked") },
                    ]}
                  />
                </span>
              </motion.div>
            ))}
          </AnimatePresence>
        </Panel>

        <div className="grid items-start gap-4 lg:grid-cols-2 xl:grid-cols-1">
          <Card>
            <SectionTitle title="Count an item" hint="Sales come off when cooking starts. At zero it is sold out on every screen, back after a delivery." />
            <div className="flex flex-col gap-3">
              <Field label="Item">
                <select aria-label="Item to track" value={pick} onChange={(e) => setPick(e.target.value)} className={inputCls}>
                  <option value="">Pick an item…</option>
                  {(items ?? [])
                    .filter((i) => !tracked.has(i.id) && !(i.combo_slots ?? []).length)
                    .map((i) => (
                      <option key={i.id} value={i.id}>
                        {i.name.en}
                      </option>
                    ))}
                </select>
              </Field>
              <div className="grid grid-cols-[1fr_auto] items-end gap-3">
                <Field label="Portions now">
                  <Input aria-label="Portions now" type="number" min={0} value={qty} onChange={(e) => setQty(e.target.value)} />
                </Field>
                <Button variant="primary" className="h-12 px-6" disabled={!pick} onClick={() => call("PUT", `/stock/${pick}`, { on_hand: Number(qty), low_at: Math.max(1, Math.round(Number(qty) / 5)) }, "Now tracking").then(() => setPick(""))}>
                  Track
                </Button>
              </div>
            </div>
          </Card>

          <Card>
            <SectionTitle
              title="Latest stock moves"
              right={
                stock.moves.length > 5 ? (
                  <button onClick={() => setMoves((m) => !m)} className="text-sm font-semibold text-accent hover:underline">
                    {moves ? "Less" : "Show all"}
                  </button>
                ) : null
              }
            />
            {stock.moves.length ? (
              <Rows
                rows={stock.moves.slice(0, moves ? 20 : 5).map((m) => [
                  <span>
                    <span className="num mr-2 text-muted">{clockOf(m.at)}</span>
                    <span className="text-ink">{m.name?.en ?? ""}</span> <span className="text-sm">· {m.reason.replace("_", " ")}</span>
                  </span>,
                  <span className={m.change > 0 ? "text-ok" : ""}>{m.change > 0 ? `+${m.change}` : m.change}</span>,
                ])}
              />
            ) : (
              <p className="py-4 text-center text-sm text-muted">No moves yet</p>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}

const STOCK_COLS = "minmax(0,2.4fr) repeat(3,minmax(0,0.8fr)) minmax(9.5rem,auto)";

// ------------------------------------------------------------------ settings

type SView = "look" | "screens" | "ai" | "guests";

export function SettingsPage({ ctx, sub, setSub, onLook }: { ctx: Ctx; onLook: () => void } & SubProps) {
  const view: SView = sub === "screens" || sub === "ai" || sub === "guests" ? sub : "look";
  return (
    <div className="flex flex-col gap-4">
      <SubNav<SView>
        label="Settings view"
        value={view}
        onChange={setSub}
        options={[
          ["look", "Look"],
          ["screens", "Screens"],
          ["ai", "AI"],
          ["guests", "Guests"],
        ]}
      />
      <motion.div key={view} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.22 }}>
        {view === "look" ? <BrandEditor admin={ctx.admin} onSaved={onLook} /> : view === "screens" ? <ScreensPage {...ctx} /> : view === "ai" ? <AiPage {...ctx} /> : <GuestsPage {...ctx} />}
      </motion.div>
    </div>
  );
}

// ------------------------------------------------------------------ screens

type Dev = { id: string; type: string; name: string; table_ref: string | null; paired: boolean; is_active: boolean; connected: boolean; last_seen_at: string | null; client: Record<string, string> | null };
const KIND: Record<string, string> = { cashier: "POS", waiter: "Waiter", kds: "Kitchen", kiosk: "Kiosk", status: "Status board", table: "Table", board: "Menu board" };

function ScreensPage(ctx: Ctx) {
  const [d] = useReport<Dev[]>(ctx, "/devices", false);
  if (!d)
    return (
      <div className="flex flex-col gap-4">
        <KpiSkeleton />
        <SkeletonList rows={5} />
      </div>
    );
  const live = d.filter((x) => x.is_active).sort((a, b) => Number(a.connected) - Number(b.connected));
  const online = live.filter((x) => x.connected).length;
  const row = tableRow(SCREEN_COLS);
  return (
    <div className="flex flex-col gap-4">
      <KpiStrip>
        <Kpi label="Online now" value={`${online} / ${live.length}`} tone={live.some((x) => x.paired && !x.connected) ? "warn" : undefined} />
        <Kpi label="Offline" value={live.filter((x) => x.paired && !x.connected).length} />
        <Kpi label="Not set up" value={live.filter((x) => !x.paired).length} />
        <Kpi label="Screens" value={live.length} />
      </KpiStrip>
      <Panel title="Every screen" hint="Set up and changed by our installation team. Call support if one stays offline.">
        <TableHead cols={SCREEN_COLS} left={2}>
          <span>Screen</span>
          <span>Kind</span>
          <span>Device</span>
          <span>Status</span>
        </TableHead>
        {live.length ? null : <Empty icon={<MonitorSmartphone size={24} />}>No screens yet.</Empty>}
        {live.map((x) => {
          const c = x.client ?? {};
          const device = x.paired ? [c.model, c.os, c.app === "android" ? `App ${c.app_version ?? ""}` : c.browser, c.ip].filter(Boolean).join(" · ") || "Set up" : "Not set up yet";
          return (
            <div key={x.id} style={row.style} className={`flex items-center gap-3 border-t border-line px-4 py-3 sm:px-5 ${row.cls}`}>
              <span className="flex min-w-0 flex-1 items-center gap-3">
                <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-canvas text-ink/70">
                  <MonitorSmartphone size={20} />
                </span>
                <span className="min-w-0">
                  <span className="block truncate font-semibold">{x.name}</span>
                  <span className="block truncate text-sm text-muted lg:hidden">
                    {KIND[x.type] ?? x.type} · {device}
                  </span>
                </span>
              </span>
              <span className="hidden truncate text-[15px] lg:block">{KIND[x.type] ?? x.type}</span>
              <span className="hidden truncate text-right text-sm text-muted lg:block" title={device}>
                {device}
              </span>
              <span className="shrink-0 text-right">
                <Status tone={x.connected ? "ok" : x.paired ? "bad" : "muted"}>{x.connected ? "Online" : x.last_seen_at ? `Seen ${ago(x.last_seen_at)}` : "Never"}</Status>
              </span>
            </div>
          );
        })}
      </Panel>
    </div>
  );
}
const SCREEN_COLS = "minmax(0,1.6fr) minmax(0,1fr) minmax(0,2fr) minmax(0,1fr)";

// ------------------------------------------------------------------ guests

type Member = { id: string; name: string | null; phone: string; tier: string | null; points: number; visits: number };

function GuestsPage(ctx: Ctx) {
  const toast = useToast();
  const [q, setQ] = useState("");
  const [rows, reload, failed] = useReport<Member[]>(ctx, `/customers${q.trim() ? `?q=${encodeURIComponent(q.trim())}` : ""}`, false);
  const row = tableRow(MEMBER_COLS);
  return (
    <Panel
      title="Loyalty members"
      hint="Joined with their consent (PDPA). Export answers an access request; Forget answers a delete request."
      right={
        <label className="relative hidden w-72 shrink-0 lg:block">
          <Search size={18} className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-muted" />
          <Input aria-label="Search members" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search phone or name" className="h-10! pl-11" />
        </label>
      }
    >
      <label className="relative mx-4 mb-3 block lg:hidden">
        <Search size={18} className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-muted" />
        <Input aria-label="Search members" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search phone or name" className="pl-11" />
      </label>
      <TableHead cols={MEMBER_COLS}>
        <span>Member</span>
        <span>Phone</span>
        <span>Tier</span>
        <span>Points</span>
        <span>Visits</span>
        <span />
      </TableHead>
      {!rows ? (
        failed ? (
          <Empty>Loyalty is not in this package.</Empty>
        ) : (
          <div className="p-4">
            <SkeletonList rows={3} />
          </div>
        )
      ) : rows.length ? (
        rows.slice(0, 50).map((c) => (
          <div key={c.id} style={row.style} className={`flex items-center gap-3 border-t border-line px-4 py-2.5 sm:px-5 ${row.cls}`}>
            <span className="flex min-w-0 flex-1 items-center gap-3">
              <Avatar size={38} />
              <span className="min-w-0">
                <span className="block truncate font-semibold">{c.name || "—"}</span>
                <span className="block truncate text-sm text-muted lg:hidden">
                  {c.phone} · {c.tier || "No tier"} · {c.points} points · {c.visits} visits
                </span>
              </span>
            </span>
            <span className="num hidden text-right text-[15px] lg:block">{c.phone}</span>
            <span className="hidden text-right lg:block">{c.tier ? <Badge>{c.tier}</Badge> : <span className="text-muted">—</span>}</span>
            <span className="num hidden text-right text-[15px] font-semibold lg:block">{c.points}</span>
            <span className="num hidden text-right text-[15px] lg:block">{c.visits}</span>
            <span className="flex justify-end">
              <MoreMenu
                items={[
                  { label: "Export their data", icon: <Download size={18} />, onClick: () => ctx.admin.download(ctx.admin.v(`/customers/${c.id}/export`), `member-${c.id}.json`).catch((e) => toast(e.message, "bad")) },
                  {
                    label: "Forget this member",
                    icon: <UserX size={18} />,
                    danger: true,
                    onClick: async () => {
                      if (!confirm(`Forget ${c.name || c.phone}? Their phone and name are deleted; sales stay anonymous.`)) return;
                      await ctx.admin.api("POST", ctx.admin.v(`/customers/${c.id}/forget`));
                      toast("Member forgotten", "ok");
                      reload();
                    },
                  },
                ]}
              />
            </span>
          </div>
        ))
      ) : (
        <Empty>No members yet.</Empty>
      )}
    </Panel>
  );
}
const MEMBER_COLS = "minmax(0,2fr) minmax(0,1.2fr) minmax(0,1fr) minmax(0,0.8fr) minmax(0,0.8fr) 40px";

// ------------------------------------------------------------------ AI

type Offer = { id: string; name: string; status: string; price: number; offer_price: number; discount_bp: number; ends_at: string; reason: string };
type Ai = { mode: string; level: number; insights?: string[]; log?: { at: string; kind: string; reason: string }[]; offers?: Offer[] };
const LEVELS: [number, string, string][] = [
  [0, "Off", "Like Manual"],
  [1, "Insights", "Tips for you and the staff only"],
  [2, "Upsell", "+ suggest to guests what people buy together"],
  [3, "Busy help", "+ reorder screens, quick items when the kitchen is busy, longer wait shown"],
  [4, "Deals", "+ deals to clear stock before its use-by time, within your cap"],
];

function AiPage(ctx: Ctx) {
  const toast = useToast();
  const [ai, reload] = useReport<Ai>(ctx, "/ai", false);
  const venue = ctx.admin.venue!;
  const cfg = venue.settings ?? {};
  const [level, setLevel] = useState<number>(Number(cfg.ai_level ?? 1));
  const [cap, setCap] = useState(String((cfg.ai_price_cap_bp ?? 1000) / 100));
  const [approve, setApprove] = useState(cfg.ai_requires_approval !== false);
  const inv = !venue.plan?.modules || venue.plan.modules.includes("R-INV");
  const save = async (settings: Record<string, unknown>, msg: string) => {
    try {
      ctx.admin.venue = await ctx.admin.api("PATCH", ctx.admin.v(""), { settings });
      toast(msg, "ok");
      reload();
    } catch (e) {
      toast((e as Error).message, "bad");
    }
  };
  const decide = async (o: Offer, d: "approve" | "reject") => {
    try {
      await ctx.admin.api("POST", ctx.admin.v(`/ai/offers/${o.id}/${d}`));
      toast(d === "approve" ? `Deal live: ${o.name} ${money(o.offer_price)}` : "Deal stopped", "ok");
      reload();
    } catch (e) {
      toast((e as Error).message, "bad");
    }
  };
  if (!ai) return <Skeleton className="h-80 rounded-2xl" />;
  const on = ai.mode === "ai";
  const changed = level !== ai.level;
  return (
    <div className="grid items-start gap-4 lg:grid-cols-[1.2fr_1fr]">
      <Card>
        <SectionTitle title="AI mode" hint="Levels 1–3 never change prices. Level 4 only lowers prices, within your cap. Allergens, refunds and emergencies never depend on AI." right={<Badge tone={on ? "info" : "muted"}>{on ? `On · level ${ai.level}` : "Manual"}</Badge>} />
        <div role="radiogroup" aria-label="AI level" className="flex flex-col gap-1.5">
          {LEVELS.map(([v, n, d]) => {
            const disabled = v === 4 && !inv;
            const sel = level === v;
            return (
              <button key={v} role="radio" aria-checked={sel} disabled={disabled} onClick={() => setLevel(v)} className={`flex items-center gap-3 rounded-xl px-3 py-2.5 text-left ring-1 transition disabled:opacity-40 ${sel ? "bg-accent-soft ring-2 ring-accent" : "ring-transparent hover:bg-canvas"}`}>
                <span className={`grid h-5 w-5 shrink-0 place-items-center rounded-full ring-2 ${sel ? "ring-accent" : "ring-line"}`}>{sel ? <span className="h-2.5 w-2.5 rounded-full bg-accent" /> : null}</span>
                <span className="min-w-0">
                  <span className="block font-semibold">
                    {v} · {n}
                  </span>
                  <span className="block text-sm text-muted">
                    {d}
                    {disabled ? " (needs Inventory)" : ""}
                  </span>
                </span>
              </button>
            );
          })}
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          {on ? (
            <>
              <Button variant="primary" disabled={!changed} onClick={() => save({ ai_level: level }, "AI level saved")}>
                Save level
              </Button>
              <Button variant="ghost" onClick={() => save({ mode: "manual" }, "Back to Manual. Screens update now.")}>
                Back to Manual
              </Button>
            </>
          ) : (
            <Button variant="primary" onClick={() => save({ mode: "ai", ai_level: level }, "AI mode is on")}>
              <Sparkles size={18} /> Turn AI mode on
            </Button>
          )}
        </div>
      </Card>

      <div className="flex flex-col gap-4">
        {on && ai.level >= 4 ? (
          <Card>
            <SectionTitle title="Deals" />
            <div className="mb-3 flex flex-wrap items-end gap-3">
              <Field label="Largest discount %" className="w-36">
                <Input aria-label="Largest discount %" type="number" min={0} max={50} value={cap} onChange={(e) => setCap(e.target.value)} />
              </Field>
              <label className="flex h-12 items-center gap-2 text-[15px] font-medium">
                <input type="checkbox" checked={approve} onChange={(e) => setApprove(e.target.checked)} className="h-5 w-5 accent-accent" /> I approve every deal first
              </label>
              <Button onClick={() => save({ ai_price_cap_bp: Math.round(Number(cap) * 100), ai_requires_approval: approve }, "Deal limits saved")}>Save limits</Button>
            </div>
            {ai.offers?.length ? (
              ai.offers.map((o) => (
                <div key={o.id} className="flex flex-wrap items-center gap-2 border-t border-line py-3">
                  <div className="min-w-[200px] flex-1">
                    <span className="font-semibold">{o.name}</span> <Badge tone={o.status === "active" ? "ok" : o.status === "proposed" ? "warn" : "muted"}>{o.status}</Badge>
                    <div className="text-sm">
                      <s className="text-muted">{money(o.price)}</s> → <b>{money(o.offer_price)}</b> ({o.discount_bp / 100}% off, until {clockOf(o.ends_at)})
                    </div>
                    <div className="text-sm text-muted">{o.reason}</div>
                  </div>
                  {o.status === "proposed" ? (
                    <Button size="sm" variant="ok" onClick={() => decide(o, "approve")}>
                      Approve
                    </Button>
                  ) : null}
                  {["proposed", "active"].includes(o.status) ? (
                    <Button size="sm" onClick={() => decide(o, "reject")}>
                      {o.status === "active" ? "Stop" : "Reject"}
                    </Button>
                  ) : null}
                </div>
              ))
            ) : (
              <p className="text-sm text-muted">No deals yet. They appear when plenty of a tracked item is left close to its use-by time.</p>
            )}
          </Card>
        ) : null}
        {ai.insights?.length ? (
          <Card>
            <SectionTitle title="Insights" />
            <ul className="flex flex-col gap-2 text-[15px]">
              {ai.insights.map((x, i) => (
                <li key={i} className="flex gap-2">
                  <Sparkles size={16} className="mt-1 shrink-0 text-muted" />
                  {x}
                </li>
              ))}
            </ul>
          </Card>
        ) : null}
        {ai.log?.length ? (
          <Card>
            <SectionTitle title="Why: latest AI decisions" />
            {ai.log.slice(0, 10).map((x, i) => (
              <div key={i} className="border-t border-line/60 py-2 text-sm text-muted first:border-0">
                <span className="num">{new Date(x.at).toLocaleTimeString()}</span> · <span className="font-medium text-ink">{x.kind}</span>: {x.reason}
              </div>
            ))}
          </Card>
        ) : null}
      </div>
    </div>
  );
}
