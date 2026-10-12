// The POS, kept simple: the menu, the order being taken, and one "Needs you" list (calls, bills, food to
// take out, orders to hand over, tables to clean, feedback). Orders and the floor map are one tap away;
// the cash shift and lock are in "⋯". Works on a laptop, a tablet (portrait or landscape) and a phone:
//  - wide (landscape tablet / laptop): Needs you · Orders · Tables | menu | order
//  - medium (portrait tablet): Menu · Calls · Orders · Tables | order
//  - phone: one view at a time with tabs at the bottom; the order opens from the bar above them.
// Money is safe: one payment at a time per bill ("Being paid by Nimal"), one key per payment attempt,
// a check with the server after a network error, and no money buttons while offline.
import { useCallback, useEffect, useMemo, useState } from "react";
import type { Device } from "../../lib/device";
import { ApiError, newKey } from "../../lib/net";
import { chime, unlockSound } from "../../lib/sound";
import { ago, en, money, toCents } from "../../lib/format";
import type { Bill, Feedback, Me, Menu, Order, ServiceRequest, Shift, TableInfo } from "../../lib/types";
import { AnimatePresence, motion } from "motion/react";
import { Ban, Banknote, BellRing, Check, CheckCircle2, ChefHat, ChevronRight, ConciergeBell, DoorClosed, LayoutGrid, Lock, Monitor, Plus, Printer, ReceiptText, ScanLine, ShoppingBag, Sparkles, Trash2, Utensils, UtensilsCrossed, Wallet, X, Zap, type LucideIcon } from "lucide-react";
import { BillModal, printBill } from "../../ui/bill";
import { CallBanner, KIND, byPlace } from "../../ui/calls";
import { useIdleLock, useLive } from "../../ui/hooks";
import { Appear, Badge, Button, Card, Empty, ease, Field, IconButton, inputCls, ListRow, LivePill, Modal, MoreMenu, Skeleton, spring, useToast } from "../../ui/kit";
import { LedgerView } from "../../ui/ledger";
import { CartLines, CartSummary, cartTotal, MenuGrid, toApiLines, useOptions, useViewport, type CartLine } from "../../ui/ordering";
import { Logo } from "../../ui/logo";
import { heldByOther, OfflineBar, PaidSheet, PaymentModal, useNoConnection, type Receipt } from "../../ui/payment";
import { feedbackWords, readyIn, Stars, TableDot, TableGrid, TaskRow, VisitTasks } from "../../ui/tables";

type Panel = "calls" | "orders" | "tables";
type View = "menu" | Panel;
type Quote = { subtotal: number; discount_total: number; tax_lines: { name: { en?: string }; rate_bp: number; amount: number }[]; total: number };
type Act = (fn: () => Promise<unknown>, ok?: string) => Promise<void>;

export function Pos({ device, me, logout }: { device: Device; me: Me; logout: () => void }) {
  const toast = useToast();
  const [shift, setShift] = useState<Shift | null | undefined>(undefined);
  const [menu, setMenu] = useState<Menu | null>(null);
  const [orders, setOrders] = useState<Order[]>([]);
  const [tables, setTables] = useState<TableInfo[]>([]);
  const [calls, setCalls] = useState<ServiceRequest[]>([]);
  const [feedback, setFeedback] = useState<Feedback[]>([]);
  const [panel, setPanel] = useState<Panel>("calls"); // wide: the left panel
  const [view, setView] = useState<View>("menu"); // medium and phone: the one main view
  const [cart, setCart] = useState<CartLine[]>([]);
  const [cartTable, setCartTable] = useState<string | null>(null);
  const [quote, setQuote] = useState<Quote | null>(null);
  const [paying, setPaying] = useState<Order | null>(null);
  const [receipt, setReceipt] = useState<Receipt | null>(null);
  const [tableOpen, setTableOpen] = useState<string | null>(null);
  const [showLedger, setShowLedger] = useState(false);
  const [showShift, setShowShift] = useState(false);
  const [showCart, setShowCart] = useState(false);
  const [tick, setTick] = useState(0);
  const { ask, modal: optionsModal } = useOptions(menu);
  const { w } = useViewport();
  const layout = w >= 1180 ? "wide" : w >= 700 ? "medium" : "phone";
  const isManager = ["manager", "owner"].includes(me.staff?.role ?? "");
  const tab = me.venue.dine_in_mode === "tab";

  const loadShift = useCallback(() => device.get<Shift>("/v1/shifts/current").then(setShift).catch((e: ApiError) => (e.status === 404 ? setShift(null) : undefined)), [device]);
  const refresh = useCallback(async () => {
    const q = new URLSearchParams([["status", "placed"], ["status", "in_kitchen"], ["status", "ready"], ["limit", "200"]]);
    const [o, t, c, f] = await Promise.all([
      device.get<Order[]>(`/v1/orders?${q}`),
      device.get<TableInfo[]>("/v1/tables").catch(() => []),
      device.get<ServiceRequest[]>("/v1/service-requests").catch(() => []),
      device.get<Feedback[]>("/v1/feedback").catch(() => [] as Feedback[]),
    ]);
    setOrders(o);
    setTables(t);
    setCalls(c);
    setFeedback(f);
    setTick((n) => n + 1);
  }, [device]);
  const loadMenu = useCallback(() => device.get<Menu>("/v1/menu").then(setMenu), [device]);

  useEffect(() => {
    void loadShift();
    void loadMenu();
    void refresh();
  }, []);
  useIdleLock(5, logout);

  const live = useLive(device, (ev) => {
    if (ev.type === "resync") return void (loadMenu(), refresh());
    if (ev.type.startsWith("menu.")) return void loadMenu();
    if (ev.type === "service.requested") {
      chime([990, 740, 990]);
      const r = ev.data?.request;
      if (r) toast(`${r.where}: ${KIND[r.kind] ?? r.kind}`, "info", 9000);
    }
    if (ev.type === "order.created" && ev.data?.order?.channel !== "cashier") {
      chime([740, 990]);
      const o = ev.data.order as Order;
      toast(`New order ${o.token}${o.table_ref ? ` · Table ${o.table_ref}` : ""}`, "info", 6000);
    }
    if (ev.type === "order.ready") {
      chime([880, 1320]);
      const o = ev.data?.order as Order | undefined;
      if (o) toast(`Ready: ${o.token}${o.table_ref ? ` · Table ${o.table_ref}` : ""}`, "ok", 6000);
    }
    if (ev.type === "feedback.new" && ev.data?.feedback) {
      const f = ev.data.feedback as Feedback;
      chime(f.low ? [440, 330, 440, 330] : [740, 990]);
      toast(`${f.table_ref ? `Table ${f.table_ref}` : "Kiosk"}: ${f.rating} of 5 · “${feedbackWords(f)}”`, f.low ? "bad" : "info", f.low ? 15000 : 6000);
    }
    if (ev.type === "print.failed") toast(`Printer ${ev.data.printer}: ${ev.data.error}`, "bad", 9000);
    void refresh();
  });
  const online = live.status === "online";
  const noConnection = useNoConnection(live.status);

  // Price the cart on the server (never trust prices on a screen).
  useEffect(() => {
    if (!cart.length) return setQuote(null);
    const t = setTimeout(() => device.post<Quote>("/v1/orders/quote", { items: toApiLines(cart, !!cartTable) }).then(setQuote).catch((x) => toast((x as Error).message, "bad")), 150);
    return () => clearTimeout(t);
  }, [cart]);

  const addItem = async (i: Menu["categories"][number]["items"][number]) => {
    const c = await ask(i);
    if (c) setCart((l) => [...l, { ...c, key: newKey(), qty: 1, hold: false }]);
  };
  const [placing, setPlacing] = useState(false);
  const place = async () => {
    setPlacing(true);
    try {
      const o = await device.post<Order>("/v1/orders", { items: toApiLines(cart, !!cartTable), table_ref: cartTable }, newKey());
      setCart([]);
      setShowCart(false);
      const t = cartTable;
      setCartTable(null);
      await refresh();
      if (t && o.is_tab) toast(`Sent to the kitchen · Table ${t} (on its check)`, "ok");
      else openPay(o);
    } catch (x) {
      toast((x as Error).message, "bad", 6000);
    } finally {
      setPlacing(false);
    }
  };
  const act: Act = async (fn, ok) => {
    try {
      await fn();
      if (ok) toast(ok, "ok");
      await refresh();
    } catch (x) {
      toast((x as Error).message, "bad", 6000);
    }
  };
  const openPay = (o: Order) => {
    const who = heldByOther(o, me);
    if (who) return toast(`${who} is taking this payment right now`, "bad");
    setReceipt(null);
    setPaying(o);
  };
  const payOrder = async (id: string) => openPay(await device.get<Order>(`/v1/orders/${id}`));
  const holderAt = (ref: string) =>
    orders
      .filter((o) => o.table_ref === ref && o.payment_status !== "paid")
      .map((o) => heldByOther(o, me))
      .find(Boolean) ?? null;

  if (shift === undefined) return <PosSkeleton />;
  if (shift === null) return <OpenShift device={device} me={me} onOpen={loadShift} logout={logout} />;

  const openCalls = calls.filter((c) => c.status !== "done");
  const handOver = orders.filter((o) => o.status === "ready" && o.payment_status === "paid" && !o.table_ref);
  const toPay = orders.filter((o) => o.payment_status !== "paid").length;
  const toServe = tables.reduce((n, t) => n + (t.to_serve?.length ?? 0), 0);
  const toClean = tables.filter((t) => t.needs_cleaning && t.state === "cleaning").length;
  const inbox = byPlace(openCalls).length + handOver.length + toServe + toClean + feedback.filter((f) => !f.seen).length;
  const urgent = tables.filter((t) => ["calling", "bill", "ready", "cleaning"].includes(t.state)).length;
  const count = cart.reduce((n, c) => n + c.qty, 0);
  const payTable = (ref: string) => {
    const o = orders.find((x) => x.table_ref === ref && x.payment_status !== "paid");
    if (o) openPay(o);
    else toast(`Table ${ref}: nothing to pay`);
  };
  const addToTable = (ref: string) => {
    setCartTable(ref);
    setCart([]);
    setTableOpen(null);
    setView("menu");
    toast(`Adding to Table ${ref}: tap menu items`);
  };

  const content = (p: Panel) =>
    p === "tables" ? (
      <div className="flex flex-col gap-3 p-4">
        <FloorSummary tables={tables} />
        {tables.length ? <TableGrid tables={tables} onOpen={setTableOpen} holder={holderAt} /> : <Empty icon={<LayoutGrid size={24} />}>No tables yet.</Empty>}
      </div>
    ) : p === "calls" ? (
      <div className="flex flex-col py-2">
        <h3 className="px-4 pb-1 pt-2 text-lg font-bold tracking-tight">Needs you</h3>
        <VisitTasks
          device={device}
          tables={tables}
          calls={openCalls}
          feedback={feedback}
          pickWaiter
          act={act}
          onChanged={refresh}
          onOpen={setTableOpen}
          onBill={payTable}
          onPrint={(ref) => printBill(device, ref, toast)}
          holder={holderAt}
          moneyOff={!online}
          className="px-1"
          before={handOver.map((o) => (
            <TaskRow
              key={`h-${o.id}`}
              data-order={o.token}
              icon={<ShoppingBag size={19} />}
              tone="ok"
              title={`Hand over ${o.token}`}
              sub={`Ready · ${o.items.filter((i) => i.parent_position === null).map((i) => `${i.quantity}× ${en(i.name)}`).join(", ")}`}
              action={
                <Button variant="default" className="min-w-24 rounded-full" onClick={() => act(() => device.post(`/v1/orders/${o.id}/complete`), `${o.token} handed over`)}>
                  Hand over
                </Button>
              }
            />
          ))}
          empty={<Empty icon={<CheckCircle2 size={24} />}>All calm. Nothing needs you right now.</Empty>}
        />
      </div>
    ) : (
      <OrdersPanel device={device} me={me} online={online} orders={orders} isManager={isManager} onPay={payOrder} act={act} />
    );

  const tabsFor = (cur: string): [Panel, React.ReactNode][] => [
    ["calls", <TabLabel label="Calls" n={inbox} alert on={cur === "calls"} />],
    ["orders", <TabLabel label="Orders" n={toPay} on={cur === "orders"} />],
    ...(tables.length ? [["tables", <TabLabel label="Tables" n={urgent} on={cur === "tables"} />] as [Panel, React.ReactNode]] : []),
  ];

  const cartPanel = (
    <CartPanel
      cart={cart}
      setCart={setCart}
      count={count}
      cartTable={cartTable}
      tab={tab}
      quote={quote}
      placing={placing}
      onTakeaway={() => setCartTable(null)}
      onPlace={place}
    />
  );

  return (
    <div className="flex h-full flex-col bg-canvas" onPointerDown={unlockSound}>
      <header className="shrink-0 border-b border-line bg-surface">
        <div className="flex h-14 items-center gap-2 px-3 sm:h-16 sm:gap-3 sm:px-4">
          <Logo url={me.venue.brand?.logo_url} name={me.venue.name} size={34} />
          <div className="min-w-0 flex-1">
            <div className="truncate text-[15px] font-bold leading-tight sm:text-base">{me.venue.name}</div>
            <div className="truncate text-[13px] text-muted">
              {me.staff?.name}
              <span className="hidden sm:inline"> · {me.device.name}</span>
            </div>
          </div>
          <LivePill status={live.status} via={live.via} />
          {layout === "phone" ? (
            <IconButton label="Payments" variant="ghost" onClick={() => setShowLedger(true)}>
              <Wallet size={19} />
            </IconButton>
          ) : (
            <Button size="sm" variant="soft" className="rounded-full px-4" onClick={() => setShowLedger(true)}>
              <Wallet size={17} /> Payments
            </Button>
          )}
          <MoreMenu
            items={[
              { label: "Cash shift", icon: <Banknote size={17} />, onClick: () => (loadShift(), setShowShift(true)) },
              { label: "Lock", icon: <Lock size={17} />, onClick: logout },
            ]}
          />
        </div>
        {noConnection ? <OfflineBar /> : null}
      </header>

      {layout === "wide" ? (
        <div className="grid min-h-0 flex-1 grid-cols-[300px_minmax(0,1fr)_330px] divide-x divide-line bg-surface min-[1366px]:grid-cols-[340px_minmax(0,1fr)_380px] 2xl:grid-cols-[400px_minmax(0,1fr)_440px]">
          <section className={PANEL}>
            <div className="border-b border-line p-2.5">
              <PanelTabs value={panel} onChange={setPanel} options={tabsFor(panel)} />
            </div>
            <div className="min-h-0 flex-1 overflow-auto">
              <Fade k={panel}>{content(panel)}</Fade>
            </div>
          </section>
          <section className={`${PANEL_BASE} overflow-y-auto bg-subtle p-5 xl:p-6`}>{menu ? <Appear><MenuGrid menu={menu} onPick={addItem} /></Appear> : <MenuSkeleton />}</section>
          <aside className={`${PANEL} overflow-y-auto`}>{cartPanel}</aside>
        </div>
      ) : layout === "medium" ? (
        <div className="grid min-h-0 flex-1 grid-cols-[minmax(0,1fr)_minmax(300px,340px)] divide-x divide-line bg-surface">
          <section className={PANEL}>
            <div className="border-b border-line p-2.5">
              <PanelTabs<View> value={view} onChange={setView} options={[["menu", <TabLabel label="Menu" n={0} on={view === "menu"} />], ...tabsFor(view)]} />
            </div>
            <div className={`min-h-0 flex-1 overflow-auto ${view === "menu" ? "bg-subtle p-4" : ""}`}>
              <Fade k={view}>{view === "menu" ? menu ? <MenuGrid menu={menu} onPick={addItem} /> : <MenuSkeleton /> : content(view)}</Fade>
            </div>
          </section>
          <aside className={`${PANEL} overflow-y-auto`}>{cartPanel}</aside>
        </div>
      ) : (
        <>
          <main className="min-h-0 flex-1 overflow-auto">
            <Fade k={view}>{view === "menu" ? <div className="flex-1 bg-surface px-4 pb-4 pt-3">{menu ? <MenuGrid menu={menu} onPick={addItem} compact /> : <MenuSkeleton />}</div> : <div className="flex-1 bg-surface">{content(view)}</div>}</Fade>
          </main>
          {count || cartTable ? (
            <div className="shrink-0 border-t border-line bg-surface px-3 py-2">
              <Button variant="primary" size="lg" className="w-full justify-between! px-4" onClick={() => setShowCart(true)}>
                <span className="num grid h-7 min-w-7 place-items-center rounded-full bg-white/15 px-2 text-sm">{count}</span>
                <span className="truncate">{cartTable ? `Table ${cartTable} · View order` : "View order"}</span>
                <span className="num">{money(quote?.total ?? cartTotal(cart))}</span>
              </Button>
            </div>
          ) : null}
          <nav className="grid shrink-0 grid-cols-4 border-t border-line bg-surface pb-[max(env(safe-area-inset-bottom),4px)]">
            {(
              [
                ["menu", UtensilsCrossed, "Menu", 0, false],
                ["calls", BellRing, "Calls", inbox, true],
                ["orders", ReceiptText, "Orders", toPay, false],
                ["tables", LayoutGrid, "Tables", urgent, false],
              ] as [View, LucideIcon, string, number, boolean][]
            ).map(([v, Icon, label, n, alert]) => (
              <button key={v} onClick={() => setView(v)} aria-current={view === v ? "page" : undefined} className={`relative flex h-14 flex-col items-center justify-center gap-0.5 text-xs font-semibold transition-colors ${view === v ? "text-accent" : "text-muted"}`}>
                <span className="relative">
                  <Icon size={21} strokeWidth={view === v ? 2.4 : 1.9} />
                  {n ? <span className={`num absolute -right-3 -top-1.5 grid h-[17px] min-w-[17px] place-items-center rounded-full px-1 text-[10px] font-bold ring-2 ring-surface ${alert ? "bg-bad text-white" : "bg-ink text-surface"}`}>{n}</span> : null}
                </span>
                {label}
              </button>
            ))}
          </nav>
          {showCart ? (
            <Modal open onClose={() => setShowCart(false)}>
              <div className="-mx-6 -my-6 flex max-h-[85vh] flex-col">{cartPanel}</div>
            </Modal>
          ) : null}
        </>
      )}

      {optionsModal}
      {paying ? (
        <PaymentModal
          device={device}
          me={me}
          order={paying}
          online={online}
          split
          onClose={() => setPaying(null)}
          onPaid={(r) => {
            setPaying(null);
            setReceipt(r);
            void refresh();
          }}
        />
      ) : null}
      {receipt ? <PaidSheet receipt={receipt} onClose={() => setReceipt(null)} onNext={() => openPay(receipt.order)} /> : null}
      {tableOpen ? (
        <TableSheet
          device={device}
          me={me}
          online={online}
          table={tables.find((t) => t.table_ref === tableOpen)}
          calls={calls.filter((c) => c.table_ref === tableOpen)}
          orders={orders.filter((o) => o.table_ref === tableOpen)}
          onClose={() => setTableOpen(null)}
          onAdd={() => addToTable(tableOpen)}
          onPay={(id) => (setTableOpen(null), payOrder(id))}
          act={act}
          refresh={refresh}
        />
      ) : null}
      {showLedger ? (
        <Modal open wide onClose={() => setShowLedger(false)} title="Today's payments">
          <LedgerView device={device} refreshKey={tick} />
        </Modal>
      ) : null}
      {showShift && shift ? <ShiftModal device={device} shift={shift} online={online} onClose={() => setShowShift(false)} /> : null}
    </div>
  );
}

function Fade({ k, children }: { k: string; children: React.ReactNode }) {
  return (
    <AnimatePresence mode="wait" initial={false}>
      <motion.div key={k} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -4 }} transition={{ duration: 0.16 }} className="flex min-h-full flex-col">
        {children}
      </motion.div>
    </AnimatePresence>
  );
}

/** One calm surface: panels side by side, split by fine lines (no floating boxes). */
const PANEL_BASE = "flex min-h-0 flex-col overflow-hidden";
const PANEL = `${PANEL_BASE} bg-surface`;

/** The tabs over a panel: the chosen one in the accent blue (a soft blue pill that slides). */
function PanelTabs<T extends string>({ value, onChange, options }: { value: T; onChange: (v: T) => void; options: [T, React.ReactNode][] }) {
  return (
    <div className="flex gap-1" role="tablist">
      {options.map(([v, label]) => {
        const on = v === value;
        return (
          <button key={v} role="tab" aria-selected={on} onClick={() => onChange(v)} className={`relative flex h-11 min-w-0 flex-1 items-center justify-center rounded-xl px-2 text-[15px] font-semibold transition-colors ${on ? "text-accent" : "text-muted hover:bg-canvas hover:text-ink"}`}>
            {on ? <motion.span layoutId="pos-tab" transition={spring} className="absolute inset-0 rounded-xl bg-accent-soft" /> : null}
            <span className="relative inline-flex items-center gap-1.5 truncate">{label}</span>
          </button>
        );
      })}
    </div>
  );
}

/** The order being taken: takeaway or a table, the lines, the totals, one button. */
function CartPanel({ cart, setCart, count, cartTable, tab, quote, placing, onTakeaway, onPlace }: { cart: CartLine[]; setCart: (l: CartLine[]) => void; count: number; cartTable: string | null; tab: boolean; quote: Quote | null; placing: boolean; onTakeaway: () => void; onPlace: () => void }) {
  return (
    <>
      <div className="flex items-start justify-between gap-2 px-5 pb-3 pt-5">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h2 className="text-xl font-bold tracking-tight">Current order</h2>
            <AnimatePresence>
              {count ? (
                <motion.span key={count} initial={{ scale: 0.6, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} exit={{ scale: 0.6, opacity: 0 }} transition={spring} className="num grid h-6 min-w-6 place-items-center rounded-full bg-ink px-1.5 text-xs font-bold text-surface">
                  {count}
                </motion.span>
              ) : null}
            </AnimatePresence>
          </div>
          {cartTable ? (
            <span className="mt-2 inline-flex h-8 max-w-full items-center gap-1 rounded-full bg-accent-soft pl-3 pr-1 text-sm font-semibold text-accent">
              <span className="truncate">
                Table {cartTable} <span className="font-medium opacity-75">· {tab ? "on its check" : "table order"}</span>
              </span>
              <button aria-label="Back to takeaway" title="Back to takeaway" className="ml-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-full hover:bg-accent/10" onClick={onTakeaway}>
                <X size={14} />
              </button>
            </span>
          ) : (
            <span className="mt-2 inline-flex h-8 items-center gap-1.5 rounded-full bg-canvas px-3 text-sm font-semibold">
              <ShoppingBag size={15} /> Takeaway
            </span>
          )}
        </div>
        {cart.length ? (
          <IconButton label="Clear the order" variant="ghost" onClick={() => setCart([])}>
            <Trash2 size={18} />
          </IconButton>
        ) : null}
      </div>
      <div className="min-h-28 flex-1 overflow-auto border-t border-line px-5">
        <CartLines lines={cart} setLines={setCart} allowHold={!!cartTable} />
      </div>
      <div className="flex flex-col gap-3 px-5 pb-5">
        <AnimatePresence initial={false}>
          {cart.length ? (
            <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }} transition={ease} className="overflow-hidden">
              <CartSummary quote={quote} fallback={cartTotal(cart)} />
            </motion.div>
          ) : null}
        </AnimatePresence>
        <Button variant="primary" size="xl" className="w-full" disabled={!cart.length || !quote || placing} onClick={onPlace}>
          {cartTable && tab ? "Send to kitchen" : "Place & pay"}
        </Button>
      </div>
    </>
  );
}

/** A tab label with a small count. */
function TabLabel({ label, n, alert = false, on = false }: { label: string; n: number; alert?: boolean; on?: boolean }) {
  return (
    <>
      {label}
      {n ? <span className={`num grid h-5 min-w-5 place-items-center rounded-full px-1.5 text-[11px] font-bold ${alert ? "bg-bad text-white" : on ? "bg-accent text-white" : "bg-ink/[.08] text-ink"}`}>{n}</span> : null}
    </>
  );
}

/** One quiet line over the floor map: how many tables are in each state. */
function FloorSummary({ tables }: { tables: TableInfo[] }) {
  const n = (f: (t: TableInfo) => boolean) => tables.filter(f).length;
  const parts: [string, number][] = [
    ["need you", n((t) => ["calling", "bill", "ready", "cleaning"].includes(t.state))],
    ["eating", n((t) => ["eating", "cooking", "waiting_payment"].includes(t.state))],
    ["free", n((t) => t.state === "free")],
  ];
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1 text-sm text-muted">
      {parts.map(([label, v]) => (
        <span key={label}>
          <span className="num font-bold text-ink">{v}</span> {label}
        </span>
      ))}
    </div>
  );
}

function PosSkeleton() {
  return (
    <div className="flex h-full flex-col bg-canvas">
      <div className="h-16 border-b border-line bg-surface" />
      <div className="grid flex-1 gap-4 p-4 md:grid-cols-[1.6fr_1fr]">
        <div className={`${PANEL} p-5`}>
          <MenuSkeleton />
        </div>
        <div className={`${PANEL} hidden md:flex`} />
      </div>
    </div>
  );
}

function MenuSkeleton() {
  return (
    <div className="flex flex-col gap-3">
      <Skeleton className="h-11 rounded-full" />
      <div className="flex gap-2 overflow-hidden">
        {[0, 1, 2, 3, 4].map((i) => (
          <Skeleton key={i} className="h-9 w-24 shrink-0 rounded-full" />
        ))}
      </div>
      <div className="grid grid-cols-[repeat(auto-fill,minmax(150px,1fr))] gap-4 pt-2">
        {[0, 1, 2, 3, 4, 5].map((i) => (
          <div key={i} className="flex flex-col gap-2">
            <Skeleton className="aspect-[4/3]" />
            <Skeleton className="h-4 w-3/4" />
            <Skeleton className="h-4 w-1/3" />
          </div>
        ))}
      </div>
    </div>
  );
}

function Group({ title, count, children }: { title: string; count: number; children: React.ReactNode }) {
  if (!count) return null;
  return (
    <section className="flex flex-col">
      <div className="flex items-center gap-2 px-4 pb-1 pt-4">
        <h3 className="text-[15px] font-bold">{title}</h3>
        <span className="num text-sm font-semibold text-muted">{count}</span>
      </div>
      <div className="flex flex-col divide-y divide-line px-1">
        <AnimatePresence initial={false}>{children}</AnimatePresence>
      </div>
    </section>
  );
}

const CHANNEL_ICON: Record<string, LucideIcon> = { kiosk: Monitor, cashier: ShoppingBag, table: Utensils, waiter: Utensils };

/** One order: number and where, how much, what; one button and "⋯" under it (fits a narrow panel). */
function OrderCard({ o, amount, action, more, ok = false, note }: { o: Order; amount?: number; action?: React.ReactNode; more?: Parameters<typeof MoreMenu>[0]["items"]; ok?: boolean; note?: React.ReactNode }) {
  const items = o.items.filter((i) => i.parent_position === null && i.kds_status !== "voided");
  const where = o.table_ref ? `Table ${o.table_ref}` : o.channel === "kiosk" ? "Kiosk" : "Counter";
  const Icon = o.table_ref ? Utensils : (CHANNEL_ICON[o.channel] ?? ReceiptText);
  const hasMore = more?.some(Boolean);
  return (
    <motion.div layout initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, x: -20 }} transition={ease} data-order={o.token} className="flex gap-3 px-3 py-3.5">
      <span className={`grid h-10 w-10 shrink-0 place-items-center rounded-full ${ok ? "bg-ok-soft text-ok" : "bg-canvas text-ink/60"}`}>
        <Icon size={18} />
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline gap-2">
          <span className="flex min-w-0 flex-1 items-center gap-1.5 font-semibold">
            <span className="shrink-0">{o.token}</span>
            {o.priority !== "normal" ? <Badge tone="bad">{o.priority === "rush" ? "Rush" : o.priority}</Badge> : null}
          </span>
          <span className="num shrink-0 font-bold">{money(amount ?? o.total)}</span>
          {!action && hasMore ? <span className="-my-2 -mr-1 self-center"><MoreMenu items={more!} /></span> : null}
        </div>
        <div className="truncate text-sm text-muted">
          <span className="font-medium text-ink/80">{where}</span> · {note ?? items.map((i) => `${i.quantity}× ${en(i.name)}`).join(", ")}
        </div>
        {action ? (
          <div className="mt-2.5 flex items-center gap-1">
            {action}
            <span className="flex-1" />
            {hasMore ? <MoreMenu items={more!} /> : null}
          </div>
        ) : null}
      </div>
    </motion.div>
  );
}

function OrdersPanel({ device, me, online, orders, isManager, onPay, act }: { device: Device; me: Me; online: boolean; orders: Order[]; isManager: boolean; onPay: (id: string) => void; act: Act }) {
  const toast = useToast();
  const [find, setFind] = useState("");
  const toPay = orders.filter((o) => o.payment_status !== "paid");
  const ready = orders.filter((o) => o.status === "ready" && o.payment_status === "paid" && !o.table_ref);
  const kitchen = orders.filter((o) => o.status === "in_kitchen" && o.payment_status === "paid");
  const lookup = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!find.trim()) return;
    try {
      const o = await device.get<Order>(`/v1/orders/lookup?code=${encodeURIComponent(find.trim())}`);
      setFind("");
      if (o.payment_status !== "paid") onPay(o.id);
      else toast(`${o.token}: ${o.status}, ${o.payment_status}`);
    } catch (x) {
      toast((x as Error).message, "bad");
    }
  };
  const voidIt = (o: Order) => {
    const reason = prompt(`Void ${o.token}: why?`);
    if (reason) void act(() => device.post(`/v1/orders/${o.id}/void`, { reason }), `${o.token} voided`);
  };
  const rush = (o: Order) => act(() => device.post(`/v1/orders/${o.id}/priority`, { priority: "rush" }), `${o.token} is RUSH`);
  const fire = (o: Order) => act(() => device.post(`/v1/orders/${o.id}/fire`, {}), "Next course sent");
  const receipt = (o: Order) => act(() => device.post(`/v1/orders/${o.id}/print/receipt`), "Receipt printing");
  return (
    <div className="flex flex-col pb-2">
      <form onSubmit={lookup} className="mx-4 mt-4 flex h-11 items-center gap-2.5 rounded-full bg-canvas px-4 transition focus-within:bg-surface focus-within:ring-2 focus-within:ring-accent">
        <ScanLine size={18} className="shrink-0 text-muted" />
        <input value={find} onChange={(e) => setFind(e.target.value)} placeholder="Find an order or scan the slip" aria-label="Find order" className="h-full min-w-0 flex-1 bg-transparent! text-[15px] outline-none placeholder:text-muted" />
        {find.trim() ? (
          <button type="submit" className="text-sm font-semibold text-accent">
            Find
          </button>
        ) : null}
      </form>
      {!toPay.length && !ready.length && !kitchen.length ? <Empty icon={<ReceiptText size={24} />}>No open orders. New ones appear here by themselves.</Empty> : null}
      <Group title="Waiting for payment" count={toPay.length}>
        {toPay.map((o) => {
          const who = heldByOther(o, me);
          return (
            <OrderCard
              key={o.id}
              o={o}
              amount={o.total - o.paid_total}
              note={who ? <span className="font-semibold text-warn">Being paid by {who}</span> : undefined}
              action={
                <Button variant="default" size="sm" className="rounded-full px-4" disabled={!online || !!who} onClick={() => onPay(o.id)}>
                  Take payment
                </Button>
              }
              more={[o.status === "placed" && o.payment_status === "unpaid" && !who ? { label: "Cancel order", icon: <X size={17} />, danger: true, onClick: () => act(() => device.post(`/v1/orders/${o.id}/cancel`, { reason: "Cancelled at the POS" }), `${o.token} cancelled`) } : null]}
            />
          );
        })}
      </Group>
      <Group title="Ready to hand over" count={ready.length}>
        {ready.map((o) => (
          <OrderCard
            key={o.id}
            o={o}
            ok
            action={
              <Button variant="default" size="sm" className="rounded-full px-4" onClick={() => act(() => device.post(`/v1/orders/${o.id}/complete`), `${o.token} handed over`)}>
                <Check size={16} /> Hand over
              </Button>
            }
            more={[{ label: "Print receipt", icon: <Printer size={17} />, onClick: () => receipt(o) }]}
          />
        ))}
      </Group>
      <Group title="In the kitchen" count={kitchen.length}>
        {kitchen.map((o) => {
          const held = o.items.some((i) => i.kds_status === "held");
          return (
            <OrderCard
              key={o.id}
              o={o}
              action={
                held ? (
                  <Button variant="default" size="sm" className="rounded-full px-4" onClick={() => fire(o)}>
                    Fire
                  </Button>
                ) : null
              }
              more={[
                o.priority === "normal" ? { label: "Rush", icon: <Zap size={17} />, onClick: () => rush(o) } : null,
                { label: "Print receipt", icon: <Printer size={17} />, onClick: () => receipt(o) },
                isManager ? { label: "Void order", icon: <Ban size={17} />, danger: true, onClick: () => voidIt(o) } : null,
              ]}
            />
          );
        })}
      </Group>
    </div>
  );
}

const ORDER_STATUS: Record<string, string> = { placed: "Waiting payment", in_kitchen: "Cooking", ready: "Ready", completed: "Done" };

function TableSheet({ device, me, online, table, calls, orders, onClose, onAdd, onPay, act, refresh }: { device: Device; me: Me; online: boolean; table: TableInfo | undefined; calls: ServiceRequest[]; orders: Order[]; onClose: () => void; onAdd: () => void; onPay: (id: string) => void; act: Act; refresh: () => void }) {
  const toast = useToast();
  const [bill, setBill] = useState<Bill | null>(null);
  const owing = useMemo(() => table?.orders.filter((o) => o.payment_status !== "paid") ?? [], [table]);
  if (!table) return null;
  const ref = encodeURIComponent(table.table_ref);
  const name = table.table_ref;
  const first = owing[0];
  const holder = orders.filter((o) => o.payment_status !== "paid").map((o) => heldByOther(o, me)).find(Boolean) ?? null;
  const toServe = table.to_serve ?? [];
  const occupied = !!table.occupied_since || table.orders.length > 0;
  const cleaning = table.state === "cleaning";
  const fb = table.feedback;
  const promised = orders.filter((o) => o.status === "in_kitchen" || o.status === "placed").map((o) => o.promised_at).filter(Boolean).sort()[0];
  const openTable = () => act(() => device.post(`/v1/tables/${ref}/open`), `Table ${name} is open`);
  const served = (id: string) => act(() => device.post(`/v1/orders/${id}/served`), `Table ${name} served`);
  const cleaned = () => act(() => device.post(`/v1/tables/${ref}/cleaned`), `Table ${name} is free`).then(onClose);
  const guestsLeft = () => act(() => device.post(`/v1/tables/${ref}/close`), `Table ${name}: guests left`);
  const payOff = !online || !!holder;

  // The one main action for this table's state.
  const [label, run, off]: [React.ReactNode, () => void, boolean] = toServe.length
    ? [<><Check size={20} /> Served · {toServe[0].token}</>, () => served(toServe[0].id), false]
    : first
      ? [holder ? `Being paid by ${holder}` : `Take payment ${money(first.total - first.paid_total)}`, () => onPay(first.id), payOff]
      : cleaning
        ? [<><Sparkles size={19} /> Cleaned</>, cleaned, false]
        : table.open && occupied
          ? [<><DoorClosed size={19} /> Guests left</>, guestsLeft, false]
          : table.open
            ? [<><Plus size={20} /> Add items</>, onAdd, false]
            : ["Open table", openTable, false];

  const [Icon, title, sub]: [LucideIcon, string, string] = toServe.length
    ? [ConciergeBell, "Food is ready", `Take ${toServe.map((o) => o.token).join(", ")} to the table`]
    : table.state === "cooking" || table.state === "waiting_payment"
      ? [ChefHat, "Cooking", readyIn(promised) ?? "The kitchen is on it"]
      : cleaning
        ? [Sparkles, "Needs cleaning", "Guests left · reset it for the next guests"]
        : occupied
          ? [Utensils, "Eating", table.occupied_since ? `Seated ${ago(table.occupied_since)}` : "Guests are at the table"]
          : [Utensils, table.open ? "Free" : "Closed", table.open ? "Ready for guests" : "Open it when guests sit down"];

  return (
    <Modal
      open
      onClose={onClose}
      title={
        <span className="flex items-center gap-3">
          Table {name}
          <TableDot state={table.state} className="text-sm" />
        </span>
      }
      footer={
        <Button variant="primary" size="xl" className="w-full" disabled={off} onClick={run}>
          {label}
        </Button>
      }
    >
      <div className="flex flex-col gap-4">
        <div className="flex items-start justify-between gap-3 border-b border-line pb-4">
          <div>
            <div className="text-sm font-medium text-muted">{owing.length ? "To pay" : "Nothing to pay"}</div>
            <div className={`num text-4xl font-bold tracking-tight ${owing.length ? "" : "text-muted"}`}>{money(table.open_total)}</div>
            {holder ? <div className="mt-1 text-sm font-semibold text-warn">Being paid by {holder}</div> : null}
          </div>
          <MoreMenu
            items={[
              table.open && occupied ? { label: "Add items", icon: <Plus size={17} />, onClick: onAdd } : null,
              first && toServe.length && !payOff ? { label: "Take payment", icon: <Banknote size={17} />, onClick: () => onPay(first.id) } : null,
              owing.length ? { label: "Show the bill", icon: <ReceiptText size={17} />, onClick: () => device.get<Bill>(`/v1/tables/${ref}/bill`).then(setBill, (x) => toast((x as Error).message, "bad")) } : null,
              owing.length ? { label: "Print bill", icon: <Printer size={17} />, onClick: () => void printBill(device, name, toast) } : null,
              cleaning && toServe.length ? { label: "Cleaned", icon: <Sparkles size={17} />, onClick: cleaned } : null,
              table.open && !owing.length && occupied && (toServe.length || cleaning) ? { label: "Guests left · close table", icon: <DoorClosed size={17} />, danger: true, onClick: () => guestsLeft().then(onClose) } : null,
            ]}
          />
        </div>
        <div className="flex items-center gap-3">
          <span className={`grid h-11 w-11 shrink-0 place-items-center rounded-full ${toServe.length ? "bg-ok-soft text-ok" : cleaning ? "bg-warn-soft text-warn" : "bg-ink/[.06] text-ink/60"}`}>
            <Icon size={20} />
          </span>
          <div className="min-w-0">
            <div className="font-bold">{title}</div>
            <div className="truncate text-sm text-muted">{sub}</div>
          </div>
        </div>
        {calls.some((c) => c.status !== "done") ? (
          <div className="rounded-2xl ring-1 ring-line">
            <CallBanner device={device} calls={calls} pickWaiter onChanged={refresh} due={table.open_total} holder={holder} moneyOff={!online} onBill={first ? () => onPay(first.id) : undefined} onPrint={() => printBill(device, name, toast)} />
          </div>
        ) : null}
        {fb ? (
          <div className="flex items-start gap-3 rounded-2xl p-3.5 ring-1 ring-line" data-feedback={fb.id}>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2 text-sm font-medium text-muted">
                Guests said <Stars rating={fb.rating} low={fb.low} />
              </div>
              <div className="mt-0.5 font-semibold">“{feedbackWords(fb)}”</div>
              <div className="text-sm text-muted">{fb.seen ? `Seen${fb.seen_by ? ` by ${fb.seen_by}` : ""}` : ago(fb.created_at)}</div>
            </div>
            {!fb.seen ? (
              <Button variant="default" className="rounded-full" onClick={() => act(() => device.post(`/v1/feedback/${fb.id}/seen`), "Marked as seen")}>
                Seen
              </Button>
            ) : null}
          </div>
        ) : null}
        {table.orders.length ? (
          <div className="-mx-3 flex flex-col divide-y divide-line">
            {table.orders.map((o) => {
              const paid = o.payment_status === "paid";
              const ready = toServe.some((x) => x.id === o.id);
              return (
                <ListRow
                  key={o.id}
                  data-order={o.token}
                  lead={
                    <span className={`grid h-10 w-10 place-items-center rounded-full ${ready ? "bg-ok-soft text-ok" : "bg-ink/[.06] text-ink/60"}`}>
                      <ReceiptText size={18} />
                    </span>
                  }
                  title={
                    <>
                      {o.token} <span className="font-medium text-muted">· {ready ? "Ready to take out" : o.status === "ready" && o.served ? "Served" : (ORDER_STATUS[o.status] ?? o.status)}</span>
                    </>
                  }
                  sub={o.is_tab ? "On the check" : paid ? "Paid" : "Pay first"}
                  trail={
                    ready && toServe[0]?.id !== o.id ? (
                      <Button variant="default" className="rounded-full" onClick={() => served(o.id)}>
                        Served
                      </Button>
                    ) : paid ? (
                      <Badge tone="ok">Paid</Badge>
                    ) : (
                      <>
                        <span className="num font-bold">{money(o.total - o.paid_total)}</span>
                        <ChevronRight size={18} className="text-muted" />
                      </>
                    )
                  }
                  onClick={paid || payOff ? undefined : () => onPay(o.id)}
                />
              );
            })}
          </div>
        ) : !cleaning ? (
          <Empty icon={<UtensilsCrossed size={24} />}>{table.open ? "No orders yet." : "Closed. Open it when guests sit down."}</Empty>
        ) : null}
      </div>
      {bill ? <BillModal device={device} bill={bill} onClose={() => setBill(null)} /> : null}
    </Modal>
  );
}

function OpenShift({ device, me, onOpen, logout }: { device: Device; me: Me; onOpen: () => void; logout: () => void }) {
  const toast = useToast();
  const [float, setFloat] = useState("0");
  return (
    <div className="flex h-full items-center justify-center overflow-auto bg-canvas p-4 sm:p-6">
      <Appear className="w-full max-w-md">
        <Card className="p-6! sm:p-8!">
          <div className="flex items-center gap-3">
            <Logo url={me.venue.brand?.logo_url} name={me.venue.name} size={44} />
            <div className="min-w-0">
              <div className="truncate font-bold">{me.venue.name}</div>
              <div className="truncate text-sm text-muted">{me.device.name}</div>
            </div>
          </div>
          <h1 className="mt-6 text-2xl font-bold tracking-tight sm:mt-8">Open cash shift</h1>
          <p className="mt-1 text-muted">Hi {me.staff?.name}. Count the cash in the drawer to start.</p>
          <Field label="Opening float (Rs)" className="mt-6">
            <input aria-label="Opening float" inputMode="decimal" value={float} onChange={(e) => setFloat(e.target.value)} onFocus={(e) => e.target.select()} className={`${inputCls} num h-16! text-3xl! font-bold`} />
          </Field>
          <Button variant="primary" size="xl" className="mt-6 w-full" onClick={() => device.post("/v1/shifts/open", { opening_float: toCents(float) }).then(onOpen, (x) => toast((x as Error).message, "bad"))}>
            Open shift
          </Button>
          <Button variant="ghost" className="mt-2 w-full" onClick={logout}>
            Log out
          </Button>
        </Card>
      </Appear>
    </div>
  );
}

function ShiftModal({ device, shift, online, onClose }: { device: Device; shift: Shift; online: boolean; onClose: () => void }) {
  const toast = useToast();
  const [counted, setCounted] = useState("");
  const methods = Object.entries(shift.live.by_method);
  return (
    <Modal
      open
      onClose={onClose}
      title="Cash shift"
      footer={
        <Button
          variant="primary"
          size="lg"
          className="w-full"
          disabled={!counted || !online}
          onClick={() =>
            device.post<{ variance: number }>(`/v1/shifts/${shift.id}/close`, { counted_cash: toCents(counted) }).then(
              (c) => {
                toast(c.variance === 0 ? "Shift closed. Drawer is exact." : `Shift closed. ${c.variance > 0 ? "Over" : "Short"} by ${money(Math.abs(c.variance))}`, c.variance === 0 ? "ok" : "bad", 8000);
                setTimeout(() => location.reload(), 1500);
              },
              (x) => toast((x as Error).message, "bad"),
            )
          }
        >
          Close shift
        </Button>
      }
    >
      <div className="flex flex-col gap-4">
        <div className="border-b border-line pb-4">
          <div className="text-sm font-medium text-muted">Expected cash in drawer</div>
          <div className="num text-3xl font-bold tracking-tight">{money(shift.live.expected_cash)}</div>
          <div className="mt-1 text-sm text-muted">
            Opened {new Date(shift.opened_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })} · float {money(shift.opening_float)}
          </div>
        </div>
        {methods.length ? (
          <div className="flex flex-col">
            {methods.map(([m, v]) => (
              <div key={m} className="flex justify-between border-b border-line px-1 py-2.5 text-[15px] last:border-0">
                <span>
                  {m.charAt(0).toUpperCase()}
                  {m.slice(1)} <span className="text-muted">· {v.count}</span>
                </span>
                <span className="num font-semibold">
                  {money(v.charges)}
                  {v.refunds ? <span className="text-bad"> − {money(v.refunds)}</span> : null}
                </span>
              </div>
            ))}
          </div>
        ) : null}
        <Field label="Count the drawer to close the shift (Rs)">
          <input aria-label="Counted cash" inputMode="decimal" value={counted} onChange={(e) => setCounted(e.target.value)} className={`${inputCls} num h-16! text-3xl! font-bold`} />
        </Field>
      </div>
    </Modal>
  );
}
