// Waiter app (phone, portrait or landscape). Three tabs only:
//  - Tasks: what to do now, most urgent first (unhappy guests, calls, bills, food to take out, tables
//    to clean, new feedback). One button per task.
//  - Tables: the floor; a table's page has one main button for what comes next.
//  - Me: my cash (hand it over at the end of service) and my payments today.
// Taking money: the bill is held for this waiter while the payment window is open, the change shows in
// big numbers, and the receipt prints where the app says. Without a connection, money buttons pause.
import { useCallback, useEffect, useState } from "react";
import type { Device } from "../../lib/device";
import { ago, en, money, toCents } from "../../lib/format";
import { newKey } from "../../lib/net";
import { chime, unlockSound } from "../../lib/sound";
import type { Bill, Feedback, Me, Menu, Order, ServiceRequest, Shift, TableInfo } from "../../lib/types";
import { AnimatePresence, motion } from "motion/react";
import { Banknote, Check, CheckCircle2, ChefHat, ConciergeBell, DoorClosed, Flame, LayoutGrid, ListChecks, Lock, Plus, Printer, ReceiptText, Sparkles, UserRound, Utensils, UtensilsCrossed, type LucideIcon } from "lucide-react";
import { CallBanner, KIND, byPlace } from "../../ui/calls";
import { useIdleLock, useLive } from "../../ui/hooks";
import { Button, Card, ease, Empty, Field, inputCls, LivePill, Modal, MoreMenu, Skeleton, SkeletonList, Status, useToast } from "../../ui/kit";
import { Logo } from "../../ui/logo";
import { Dish } from "../../ui/food";
import { LedgerView } from "../../ui/ledger";
import { CartLines, cartTotal, MenuGrid, toApiLines, useOptions, useViewport, type CartLine } from "../../ui/ordering";
import { heldByOther, OfflineBar, PaidSheet, PaymentModal, useNoConnection, type Receipt } from "../../ui/payment";
import { feedbackWords, readyIn, Stars, TableDot, TableGrid, VisitTasks } from "../../ui/tables";
import { BillModal, printBill } from "../../ui/bill";

type Tab = "tasks" | "tables" | "me";
type View = { name: "floor" } | { name: "table"; ref: string } | { name: "order"; ref: string };
const DOT: Record<string, [string, "muted" | "info" | "ok" | "warn"]> = { queued: ["Waiting", "muted"], in_progress: ["Cooking", "info"], done: ["Ready", "ok"], held: ["Held", "warn"] };
const OPEN = [["status", "placed"], ["status", "in_kitchen"], ["status", "ready"], ["limit", "200"]];
// Landscape phones are short: classes with "[@media(max-height:500px)]:" make the bars smaller there.

export function Waiter({ device, me, logout }: { device: Device; me: Me; logout: () => void }) {
  const toast = useToast();
  const [view, setViewRaw] = useState<View>({ name: "floor" });
  const [tab, setTab] = useState<Tab>("tasks");
  const [tables, setTables] = useState<TableInfo[] | null>(null);
  const [calls, setCalls] = useState<ServiceRequest[]>([]);
  const [feedback, setFeedback] = useState<Feedback[]>([]);
  const [orders, setOrders] = useState<Order[]>([]); // every open order (holds, food to take out, the checks)
  const [menu, setMenu] = useState<Menu | null>(null);
  const [paying, setPaying] = useState<Order | null>(null);
  const [receipt, setReceipt] = useState<Receipt | null>(null);
  const [bill, setBill] = useState<Bill | null>(null);
  const [cash, setCash] = useState(false);
  const [tick, setTick] = useState(0);
  const setView = (v: View) => (setReceipt(null), setViewRaw(v));

  const refresh = useCallback(async () => {
    const [t, c, o, f] = await Promise.all([
      device.get<TableInfo[]>("/v1/tables"),
      device.get<ServiceRequest[]>("/v1/service-requests"),
      device.get<Order[]>(`/v1/orders?${new URLSearchParams(OPEN)}`),
      device.get<Feedback[]>("/v1/feedback").catch(() => [] as Feedback[]),
    ]);
    setTables(t);
    setCalls(c);
    setOrders(o);
    setFeedback(f);
    setTick((n) => n + 1);
  }, [device]);

  useEffect(() => {
    void refresh();
    device.get<Menu>("/v1/menu").then(setMenu);
  }, []);
  useIdleLock(10, logout);

  const live = useLive(device, (ev) => {
    if (ev.type.startsWith("menu.")) return void device.get<Menu>("/v1/menu").then(setMenu);
    if (ev.type === "service.requested") {
      chime([990, 740, 990]);
      const r = ev.data?.request;
      if (r) toast(`${r.where}: ${KIND[r.kind] ?? r.kind}`, "info", 9000);
    }
    if (ev.type === "service.acknowledged") {
      const r = ev.data?.request as ServiceRequest;
      if (r?.coming && r.coming.staff_id !== me.staff?.id) toast(`${r.coming.name} is going to ${r.where}`);
    }
    if (ev.type === "order.ready" && ev.data?.order?.table_ref) {
      chime([880, 1320]);
      toast(`Food ready · Table ${ev.data.order.table_ref}`, "ok", 6000);
    }
    if (ev.type === "feedback.new" && ev.data?.feedback) {
      const f = ev.data.feedback as Feedback;
      if (f.low) chime([440, 330, 440]);
      toast(`${f.table_ref ?? "Kiosk"}: ${f.rating} of 5 · “${feedbackWords(f)}”`, f.low ? "bad" : "info", f.low ? 12000 : 6000);
    }
    void refresh();
  });
  const online = live.status === "online";
  const noConnection = useNoConnection(live.status);

  const act = async (fn: () => Promise<unknown>, ok?: string) => {
    try {
      await fn();
      if (ok) toast(ok, "ok");
      await refresh();
    } catch (x) {
      toast((x as Error).message, "bad", 6000);
    }
  };
  const unpaidAt = (ref: string) => orders.filter((o) => o.table_ref === ref && o.payment_status !== "paid");
  const holderAt = (ref: string) => unpaidAt(ref).map((o) => heldByOther(o, me)).find(Boolean) ?? null;
  const payTable = (ref: string) => {
    const o = unpaidAt(ref)[0];
    if (!o) return toast(`${ref}: nothing to pay`);
    setReceipt(null);
    setPaying(o);
  };

  const list = tables ?? [];
  const openCalls = calls.filter((c) => c.status !== "done");
  const unseen = feedback.filter((f) => !f.seen);
  const todo = byPlace(openCalls).length + list.reduce((n, t) => n + (t.to_serve?.length ?? 0) + (t.needs_cleaning && t.state === "cleaning" ? 1 : 0), 0) + unseen.length;
  const needYou = list.filter((t) => ["calling", "bill", "ready", "cleaning"].includes(t.state)).length;
  const food = Object.fromEntries(orders.filter((o) => o.status === "ready").map((o) => [o.id, o.items.filter((i) => i.parent_position === null).map((i) => `${i.quantity}× ${en(i.name)}`).join(", ")]));
  const openTable = (ref: string) => setView({ name: "table", ref });

  const NAV: [Tab, LucideIcon, React.ReactNode, number][] = [
    ["tasks", ListChecks, "Tasks", todo],
    ["tables", LayoutGrid, "Tables", needYou],
    ["me", UserRound, <>Me<span className="sr-only"> · My payments and cash</span></>, 0],
  ];
  const title = { tasks: "Tasks", tables: "Tables", me: "Me" }[tab];
  const hint = tab === "tasks" ? (todo ? `${todo} to do · most urgent first` : "All done") : tab === "tables" ? `${list.length} tables${needYou ? ` · ${needYou} need you` : ""}` : `${me.staff?.name ?? ""} · today`;

  return (
    <div className="flex min-h-full w-full flex-col bg-canvas" onPointerDown={unlockSound}>
      <header className="sticky top-0 z-20 border-b border-line bg-surface/95 backdrop-blur-md">
        <div className={`flex items-center gap-3 px-4 py-2.5 sm:px-6 [@media(max-height:500px)]:py-1.5`}>
          <Logo url={me.venue.brand?.logo_url} name={me.venue.name} size={32} />
          <div className="min-w-0 flex-1">
            <div className="truncate text-[15px] font-bold leading-tight">{me.staff?.name}</div>
            <div className="truncate text-xs text-muted">{me.venue.name}</div>
          </div>
          <LivePill status={live.status} via={live.via} />
          <MoreMenu items={[{ label: "Lock", icon: <Lock size={17} />, onClick: logout }]} />
        </div>
        {noConnection ? <OfflineBar /> : null}
      </header>
      <main className={`flex flex-1 flex-col gap-4 px-4 pb-32 pt-4 sm:px-6 sm:pt-6 [@media(max-height:500px)]:pb-24 [@media(max-height:500px)]:pt-3`}>
        <AnimatePresence mode="wait" initial={false}>
          <motion.div key={view.name === "floor" ? `floor-${tab}` : `${view.name}-${view.ref}`} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.15 }} className="flex flex-col gap-4">
            {view.name === "floor" ? (
              <>
                <div>
                  <h1 className={`text-[28px] font-bold leading-tight tracking-tight [@media(max-height:500px)]:text-2xl`}>{title}</h1>
                  <p className="text-[15px] text-muted">{hint}</p>
                </div>
                {tab === "tasks" ? (
                  tables === null ? (
                    <SkeletonList rows={4} />
                  ) : (
                    <VisitTasks
                      device={device}
                      tables={list}
                      calls={openCalls}
                      feedback={feedback}
                      pickWaiter={false}
                      act={act}
                      onChanged={refresh}
                      onOpen={openTable}
                      onBill={payTable}
                      onPrint={(ref) => printBill(device, ref, toast)}
                      holder={holderAt}
                      moneyOff={!online}
                      foodNote={(id) => food[id]}
                      className="overflow-hidden rounded-2xl bg-surface px-1 shadow-soft"
                      empty={
                        <Card className="py-4!">
                          <Empty icon={<CheckCircle2 size={24} />}>Nothing to do right now. New tasks appear here by themselves.</Empty>
                        </Card>
                      }
                    />
                  )
                ) : tab === "tables" ? (
                  tables === null ? (
                    <div className="grid grid-cols-2 gap-2.5">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-26 rounded-2xl" />)}</div>
                  ) : list.length ? (
                    <TableGrid tables={list} size="lg" onOpen={openTable} holder={holderAt} />
                  ) : (
                    <Empty icon={<LayoutGrid size={24} />}>No tables yet.</Empty>
                  )
                ) : (
                  <MeTab device={device} tick={tick} onHandOver={() => setCash(true)} />
                )}
              </>
            ) : view.name === "table" ? (
              <TableCheck
                device={device}
                me={me}
                online={online}
                table={list.find((t) => t.table_ref === view.ref)}
                calls={openCalls.filter((c) => c.table_ref === view.ref)}
                orders={orders.filter((o) => o.table_ref === view.ref)}
                menu={menu}
                backTo={tab === "tasks" ? "Tasks" : "Tables"}
                onBack={() => setView({ name: "floor" })}
                onAdd={() => setView({ name: "order", ref: view.ref })}
                onBill={() => device.get<Bill>(`/v1/tables/${encodeURIComponent(view.ref)}/bill`).then(setBill, (x) => toast((x as Error).message, "bad"))}
                onPay={() => payTable(view.ref)}
                act={act}
                refresh={refresh}
              />
            ) : menu ? (
              <OrderForTable device={device} menu={menu} table={view.ref} onDone={() => (setView({ name: "table", ref: view.ref }), refresh())} />
            ) : null}
          </motion.div>
        </AnimatePresence>
      </main>
      {view.name === "floor" ? (
        <nav className="fixed inset-x-0 bottom-0 z-20 border-t border-line bg-surface/95 pb-[max(env(safe-area-inset-bottom),6px)] backdrop-blur-md">
          <div className="mx-auto grid max-w-2xl grid-cols-3">
            {NAV.map(([v, Icon, label, n]) => {
              const on = tab === v;
              return (
                <button key={v} onClick={() => setTab(v)} aria-current={on ? "page" : undefined} className={`relative flex h-15 flex-col items-center justify-center gap-1 text-xs font-semibold transition-colors [@media(max-height:500px)]:h-12 [@media(max-height:500px)]:flex-row [@media(max-height:500px)]:gap-4 ${on ? "text-accent" : "text-muted hover:text-ink"}`}>
                  <span className="relative">
                    <Icon size={22} strokeWidth={on ? 2.4 : 1.9} />
                    {n ? <span className="num absolute -right-3 -top-1.5 grid h-[17px] min-w-[17px] place-items-center rounded-full bg-bad px-1 text-[10px] font-bold text-white ring-2 ring-surface">{n}</span> : null}
                  </span>
                  <span>{label}</span>
                </button>
              );
            })}
          </div>
        </nav>
      ) : null}
      {paying ? (
        <PaymentModal
          device={device}
          me={me}
          order={paying}
          online={online}
          onClose={() => setPaying(null)}
          onPaid={(r) => {
            setPaying(null);
            setReceipt(r);
            void refresh();
          }}
        />
      ) : null}
      {receipt ? (
        <PaidSheet
          receipt={receipt}
          onClose={() => setReceipt(null)}
          onNext={() => {
            setReceipt(null);
            setPaying(receipt.order);
          }}
        />
      ) : null}
      {bill ? (
        <BillModal
          device={device}
          bill={bill}
          payDisabled={!online || !!holderAt(bill.table_ref)}
          onClose={() => setBill(null)}
          onPay={() => {
            setBill(null);
            payTable(bill.table_ref);
          }}
        />
      ) : null}
      {cash ? <CashBag device={device} online={online} onClose={() => (setCash(false), setTick((n) => n + 1))} /> : null}
    </div>
  );
}

/** Me: the cash I carry (hand it over at the end), then every payment I took today. */
function MeTab({ device, tick, onHandOver }: { device: Device; tick: number; onHandOver: () => void }) {
  const [bag, setBag] = useState<Shift | null | undefined>(undefined);
  useEffect(() => {
    device.get<Shift>("/v1/shifts/current").then(setBag, () => setBag(null));
  }, [device, tick]);
  return (
    <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,360px)_minmax(0,1fr)]">
      <section>
        <h2 className="mb-2 text-lg font-bold">My cash</h2>
        <Card className="flex items-center gap-3 p-4!">
          <span className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-canvas text-ink/70">
            <Banknote size={20} />
          </span>
          <div className="min-w-0 flex-1">
            <div className="text-sm font-medium text-muted">To hand over</div>
            {bag === undefined ? <Skeleton className="mt-1 h-6 w-28" /> : <div className="num text-xl font-bold">{money(bag?.live.expected_cash ?? 0)}</div>}
          </div>
          <Button variant="default" className="rounded-full" disabled={!bag} onClick={onHandOver}>
            Hand over
          </Button>
        </Card>
      </section>
      <section>
        <h2 className="mb-2 text-lg font-bold">My payments</h2>
        <Card>
          <LedgerView device={device} mine refreshKey={tick} />
        </Card>
      </section>
    </div>
  );
}

/** The main button(s), fixed at the bottom of the phone: one black main action, at most one quiet one. */
function BottomBar({ children }: { children: React.ReactNode }) {
  return (
    <div className={`fixed inset-x-0 bottom-0 z-20 border-t border-line bg-surface px-4 sm:px-6 pb-[max(env(safe-area-inset-bottom),12px)] pt-3 [@media(max-height:500px)]:pb-2 [@media(max-height:500px)]:pt-2`}>
      <motion.div initial={{ y: 16, opacity: 0 }} animate={{ y: 0, opacity: 1 }} transition={ease} className="mx-auto flex max-w-2xl gap-2">
        {children}
      </motion.div>
    </div>
  );
}
const BAR_BTN = `[@media(max-height:500px)]:h-12 [@media(max-height:500px)]:text-base`;

function BackButton({ onClick, children }: { onClick: () => void; children: React.ReactNode }) {
  return (
    <button onClick={onClick} className="-ml-3 inline-flex h-11 items-center rounded-full px-3 text-[15px] font-semibold text-ink transition hover:bg-ink/[.05] active:scale-[.97]">
      {children}
    </button>
  );
}

/** The state of the visit, said plainly: one icon, one sentence, one quiet line. */
function VisitState({ icon: Icon, tone, title, sub, children }: { icon: LucideIcon; tone: "ok" | "info" | "warn" | "muted" | "bad"; title: string; sub?: React.ReactNode; children?: React.ReactNode }) {
  const tint = { ok: "bg-ok-soft text-ok", info: "bg-info-soft text-info", warn: "bg-warn-soft text-warn", bad: "bg-bad-soft text-bad", muted: "bg-canvas text-ink/60" }[tone];
  return (
    <Card className="p-0!">
      <div className="flex items-center gap-3 p-4">
        <span className={`grid h-11 w-11 shrink-0 place-items-center rounded-full ${tint}`}>
          <Icon size={21} />
        </span>
        <div className="min-w-0 flex-1">
          <div className="text-[17px] font-bold leading-snug">{title}</div>
          {sub ? <div className="text-sm text-muted">{sub}</div> : null}
        </div>
      </div>
      {children ? <div className="divide-y divide-line border-t border-line">{children}</div> : null}
    </Card>
  );
}

function TableCheck({ device, me, online, table, calls, orders, menu, backTo, onBack, onAdd, onBill, onPay, act, refresh }: { device: Device; me: Me; online: boolean; table: TableInfo | undefined; calls: ServiceRequest[]; orders: Order[]; menu: Menu | null; backTo: string; onBack: () => void; onAdd: () => void; onBill: () => void; onPay: () => void; act: (fn: () => Promise<unknown>, ok?: string) => Promise<void>; refresh: () => void }) {
  const toast = useToast();
  if (!table)
    return (
      <div className="flex flex-col gap-4">
        <Skeleton className="h-10 w-28 rounded-full" />
        <Skeleton className="h-24 rounded-2xl" />
        <SkeletonList rows={3} />
      </div>
    );
  const unpaid = orders.filter((o) => o.payment_status !== "paid");
  const due = unpaid.reduce((n, o) => n + o.total - o.paid_total, 0);
  const holder = unpaid.map((o) => heldByOther(o, me)).find(Boolean) ?? null;
  const lines = orders.flatMap((o) => o.items.filter((i) => i.parent_position === null && i.kds_status !== "voided").map((i) => ({ ...i, order: o })));
  const photo = Object.fromEntries((menu?.categories ?? []).flatMap((c) => c.items).map((i) => [i.id, i.image_url]));
  const ref = encodeURIComponent(table.table_ref);
  const name = table.table_ref;
  const openTable = () => act(() => device.post(`/v1/tables/${ref}/open`), `Table ${name} is open`);
  const close = () => act(() => device.post(`/v1/tables/${ref}/close`), `${name}: guests left`);
  const cleaned = () => act(() => device.post(`/v1/tables/${ref}/cleaned`), `${name} is free`);
  const served = (id: string) => act(() => device.post(`/v1/orders/${id}/served`), `${name} served`);
  const print = () => printBill(device, name, toast);
  const held = orders.filter((o) => o.items.some((i) => i.kds_status === "held"));
  const toServe = table.to_serve?.length ? table.to_serve : orders.filter((o) => o.status === "ready" && !o.served_at).map((o) => ({ id: o.id, token: o.token }));
  const cooking = orders.filter((o) => o.status === "in_kitchen" || o.status === "placed");
  const promised = cooking.map((o) => o.promised_at).filter(Boolean).sort()[0];
  const occupied = !!table.occupied_since || orders.length > 0;
  const cleaning = table.state === "cleaning" || (table.needs_cleaning && !occupied);
  const wantsBill = table.state === "bill" || calls.some((c) => c.kind === "request_bill");
  const fb = table.feedback;
  const payOff = !online || !!holder;
  const side = calls.length > 0 || toServe.length > 0 || cooking.length > 0 || cleaning || occupied || (!!fb && !fb.seen);

  // The one main action for this state, and at most one quiet one next to it.
  type A = { label: React.ReactNode; onClick: () => void; disabled?: boolean };
  const payMain: A = { label: holder ? `Being paid by ${holder}` : `Take payment · ${money(due)}`, onClick: onPay, disabled: payOff };
  let main: A;
  let quiet: A | null = null;
  if (toServe.length) {
    main = { label: <><Check size={20} /> Served{toServe.length > 1 ? ` · ${toServe[0].token}` : ""}</>, onClick: () => served(toServe[0].id) };
    if (due) quiet = { label: "Take payment", onClick: onPay, disabled: payOff };
  } else if (due) {
    main = payMain;
    if (wantsBill || table.state === "waiting_payment") quiet = { label: <><Printer size={18} /> Print bill</>, onClick: () => void print() };
    else if (table.open) quiet = { label: <><Plus size={18} /> Add</>, onClick: onAdd };
  } else if (cleaning) {
    main = { label: <><Sparkles size={19} /> Cleaned</>, onClick: cleaned };
  } else if (table.open) {
    main = { label: <><Plus size={20} /> Add items</>, onClick: onAdd };
    if (occupied) quiet = { label: "Guests left", onClick: close };
  } else {
    main = { label: "Open table", onClick: openTable };
  }
  if (main === payMain && quiet && !holder) main = { ...payMain, label: "Take payment" }; // narrow: the amount is shown above

  return (
    <div className="flex flex-col gap-4">
      <div>
        <BackButton onClick={onBack}>← {backTo}</BackButton>
      </div>
      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <h1 className={`text-[32px] font-bold leading-none tracking-tight [@media(max-height:500px)]:text-[26px]`}>Table {name}</h1>
          <div className="mt-2.5 flex flex-wrap items-center gap-x-3 gap-y-1">
            <TableDot state={table.state} className="text-sm" />
            <span className="text-[15px]">{due ? <><span className="num font-bold">{money(due)}</span> <span className="text-muted">to pay</span></> : <span className="text-muted">Nothing to pay</span>}</span>
          </div>
          {holder ? <div className="mt-1.5 text-sm font-semibold text-warn">Being paid by {holder}</div> : null}
        </div>
        <MoreMenu
          items={[
            due && table.open ? { label: "Add items", icon: <Plus size={17} />, onClick: onAdd } : null,
            due ? { label: "Show the bill", icon: <ReceiptText size={17} />, onClick: onBill } : null,
            due ? { label: "Print bill", icon: <Printer size={17} />, onClick: () => void print() } : null,
            ...held.map((o) => ({ label: "Fire next course", icon: <Flame size={17} />, onClick: () => act(() => device.post(`/v1/orders/${o.id}/fire`, {}), "Next course sent") })),
            cleaning && main.onClick !== cleaned ? { label: "Cleaned", icon: <Sparkles size={17} />, onClick: cleaned } : null,
            table.open && !due && occupied && quiet?.onClick !== close ? { label: "Guests left", icon: <DoorClosed size={17} />, danger: true, onClick: () => close().then(onBack) } : null,
          ]}
        />
      </div>

      <div className={`grid items-start gap-4 ${side ? "md:grid-cols-2" : ""}`}>
        {side ? (
          <div className="flex min-w-0 flex-col gap-4">
            <AnimatePresence initial={false}>
              {calls.length ? (
                <motion.div key="calls" initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }} transition={ease}>
                  <Card className="p-0!">
                    <CallBanner device={device} calls={calls} pickWaiter={false} onChanged={refresh} onBill={onPay} due={due} holder={holder} moneyOff={!online} infoOnly />
                  </Card>
                </motion.div>
              ) : null}
            </AnimatePresence>

            {toServe.length ? (
              <VisitState icon={ConciergeBell} tone="ok" title="Food is ready" sub="Take it to the table, then tap Served">
                {toServe.length > 1
                  ? toServe.map((o) => (
                      <div key={o.id} className="flex items-center gap-3 px-4 py-2.5">
                        <span className="flex-1 font-semibold">Order {o.token}</span>
                        <Button variant="default" className="rounded-full" onClick={() => served(o.id)}>
                          <Check size={15} /> Served
                        </Button>
                      </div>
                    ))
                  : null}
              </VisitState>
            ) : cooking.length ? (
              <VisitState icon={ChefHat} tone="info" title="Cooking" sub={readyIn(promised) ?? "The kitchen is on it"} />
            ) : cleaning ? (
              <VisitState icon={Sparkles} tone="warn" title="Needs cleaning" sub="Guests left · reset it for the next guests" />
            ) : occupied && !calls.length ? (
              <VisitState icon={Utensils} tone="muted" title="Eating" sub={table.occupied_since ? `Seated ${ago(table.occupied_since)}` : "Guests are at the table"} />
            ) : null}

            {fb && !fb.seen ? (
              <Card className="flex items-start gap-3 p-4!" data-feedback={fb.id}>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 text-sm font-medium text-muted">
                    Guests said <Stars rating={fb.rating} low={fb.low} />
                  </div>
                  <div className="mt-1 text-[15px] font-semibold">“{feedbackWords(fb)}”</div>
                  <div className="text-sm text-muted">{ago(fb.created_at)}</div>
                </div>
                <Button variant="default" className="rounded-full" onClick={() => act(() => device.post(`/v1/feedback/${fb.id}/seen`), "Marked as seen")}>
                  Seen
                </Button>
              </Card>
            ) : null}
          </div>
        ) : null}

        {lines.length ? (
          <Card className="min-w-0 p-0!">
            <div className="flex items-baseline justify-between px-4 pb-1 pt-4">
              <h2 className="text-lg font-bold">The check</h2>
              <span className="num text-sm text-muted">{money(orders.reduce((n, o) => n + o.total, 0))}</span>
            </div>
            <div className="divide-y divide-line px-4">
              {lines.map((i) => {
                const [label, tone] = DOT[i.kds_status] ?? [i.kds_status, "muted"];
                return (
                  <div key={i.id} className="flex items-center gap-3 py-3">
                    <Dish src={photo[i.menu_item_id]} name={en(i.name)} size={44} />
                    <div className="min-w-0 flex-1">
                      <div className="truncate font-semibold">
                        <span className="font-medium text-muted">{i.quantity}×</span> {en(i.name)}
                      </div>
                      <div className="num text-sm text-muted">{money(i.line_total)}</div>
                    </div>
                    <Status tone={tone}>{label}</Status>
                  </div>
                );
              })}
            </div>
          </Card>
        ) : !cleaning ? (
          <Card className="py-2!">
            <Empty icon={<UtensilsCrossed size={24} />}>{table.open ? "No orders yet." : "Closed. Open it when guests sit down."}</Empty>
          </Card>
        ) : null}
      </div>

      <BottomBar>
        {quiet ? (
          <Button variant="default" size="xl" className={`shrink-0 whitespace-nowrap px-5 ${BAR_BTN}`} disabled={quiet.disabled} onClick={quiet.onClick}>
            {quiet.label}
          </Button>
        ) : null}
        <Button variant="primary" size="xl" className={`min-w-0 flex-1 whitespace-nowrap px-4 ${BAR_BTN}`} disabled={main.disabled} onClick={main.onClick}>
          <span className="inline-flex min-w-0 items-center gap-2 truncate">{main.label}</span>
        </Button>
      </BottomBar>
    </div>
  );
}

function OrderForTable({ device, menu, table, onDone }: { device: Device; menu: Menu; table: string; onDone: () => void }) {
  const toast = useToast();
  const [cart, setCart] = useState<CartLine[]>([]);
  const [key] = useState(newKey);
  const [sending, setSending] = useState(false);
  const { ask, modal } = useOptions(menu);
  const { w } = useViewport();
  const count = cart.reduce((n, c) => n + c.qty, 0);
  const send = async () => {
    setSending(true);
    try {
      await device.post("/v1/orders", { items: toApiLines(cart, false), table_ref: table }, key);
      toast(`Sent to the kitchen · Table ${table}`, "ok");
      onDone();
    } catch (x) {
      toast((x as Error).message, "bad");
    } finally {
      setSending(false);
    }
  };
  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between gap-3">
        <BackButton onClick={onDone}>← Table {table}</BackButton>
        <h2 className="truncate text-lg font-bold">Add items</h2>
      </div>
      <AnimatePresence initial={false}>
        {cart.length ? (
          <motion.div key="round" initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }} transition={ease}>
            <Card className="px-4! py-3!">
              <h2 className="pt-1 text-lg font-bold">This round</h2>
              <CartLines lines={cart} setLines={setCart} allowHold={false} />
            </Card>
          </motion.div>
        ) : null}
      </AnimatePresence>
      <Card className="px-4! pb-1! pt-4!">
        <MenuGrid
          menu={menu}
          compact={w < 640}
          onPick={async (i) => {
            const c = await ask(i);
            if (c) setCart((l) => [...l, { ...c, key: newKey(), qty: 1, hold: false }]);
          }}
        />
      </Card>
      <BottomBar>
        <Button variant="primary" size="xl" className={`w-full justify-between! px-4 ${BAR_BTN}`} disabled={!cart.length || sending} onClick={send}>
          <span className="num grid h-8 min-w-8 place-items-center rounded-full bg-white/15 px-2 text-sm">{count}</span>
          <span>Send to kitchen</span>
          <span className="num text-base">{money(cartTotal(cart))}</span>
        </Button>
      </BottomBar>
      {modal}
    </div>
  );
}

function CashBag({ device, online, onClose }: { device: Device; online: boolean; onClose: () => void }) {
  const toast = useToast();
  const [bag, setBag] = useState<Shift | null | undefined>(undefined);
  const [handed, setHanded] = useState("");
  useEffect(() => {
    device.get<Shift>("/v1/shifts/current").then(
      (b) => (setBag(b), setHanded((b.live.expected_cash / 100).toFixed(2))),
      () => setBag(null),
    );
  }, [device]);
  return (
    <Modal
      open
      onClose={onClose}
      title="Hand over my cash"
      footer={
        bag ? (
          <Button
            variant="primary"
            size="lg"
            className="w-full"
            disabled={!online}
            onClick={() =>
              device.post<{ variance: number }>(`/v1/shifts/${bag.id}/close`, { counted_cash: toCents(handed) }).then(
                (c) => (toast(c.variance === 0 ? "Cash handed over. Exact." : `Handed over. ${c.variance > 0 ? "Over" : "Short"} by ${money(Math.abs(c.variance))}`, c.variance === 0 ? "ok" : "bad", 8000), onClose()),
                (x) => toast((x as Error).message, "bad"),
              )
            }
          >
            Hand over (end of service)
          </Button>
        ) : undefined
      }
    >
      {bag === undefined ? (
        <div className="flex flex-col gap-3">
          <Skeleton className="h-20" />
          <Skeleton className="h-16" />
        </div>
      ) : bag === null ? (
        <Empty icon={<Banknote size={24} />}>No cash collected yet.</Empty>
      ) : (
        <div className="flex flex-col gap-4">
          <div className="border-b border-line pb-4">
            <div className="text-sm font-medium text-muted">Cash to hand over</div>
            <div className="num text-[32px] font-bold tracking-tight">{money(bag.live.expected_cash)}</div>
          </div>
          <Field label="Handed over to the cashier / manager (Rs)">
            <input aria-label="Cash handed over" inputMode="decimal" value={handed} onChange={(e) => setHanded(e.target.value)} className={`${inputCls} num h-16! text-3xl! font-bold`} />
          </Field>
        </div>
      )}
    </Modal>
  );
}
