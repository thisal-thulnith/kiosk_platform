// The table screen (a tablet on each table), in the browser: the same flow the Android table app
// follows (docs/ANDROID_APP_GUIDE.md, Part D). Welcome → menu → send to the kitchen → follow the
// order (cooking, on its way, enjoy) → ask for the bill (cash / card / QR) → thank you and rating.
// The restaurant's settings decide the details: pay after eating (tab) or pay first, staff open the
// table or not, the waiter brings the food or guests collect it.
import { AnimatePresence, motion } from "motion/react";
import { BellRing, Check, ChefHat, CreditCard, HandCoins, Plus, QrCode, Receipt, ShoppingBag, Utensils, X } from "lucide-react";
import { QRCodeSVG } from "qrcode.react";
import { useCallback, useEffect, useRef, useState } from "react";
import type { Device } from "../../lib/device";
import { en, money } from "../../lib/format";
import { ApiError, newKey } from "../../lib/net";
import { chime, unlockSound } from "../../lib/sound";
import { store } from "../../lib/store";
import type { Me, Menu, MenuItem, Order, Payment, PayWith, Text } from "../../lib/types";
import T from "../../lib/i18n.json";
import { useLive } from "../../ui/hooks";
import { dishIcon } from "../../ui/food";
import { Button, LivePill, spring, useToast } from "../../ui/kit";
import { Logo } from "../../ui/logo";
import { DevButtons } from "../../ui/payment";
import { type CartLine, cartTotal, toApiLines } from "../../ui/ordering";
import { type Lang, LANG_NAMES, Line, Photo, Rate, Sheet, Totals, Waiting, Welcome, useKioskOptions, word } from "../kiosk/parts";

type View = "welcome" | "menu" | "order" | "qr" | "card" | "thanks";
type Quote = { subtotal: number; discount_total: number; tax_total: number; total: number; tax_lines: { name: Text; amount: number }[] };
type Call = { id: string; kind: string; status: string; pay_with: PayWith | null; coming: { staff_id: string; name: string } | null };
const IDLE_BROWSING = 90; // seconds: guests left without ordering -> welcome
const THANKS_SECONDS = 45; // after paying, back to welcome (privacy)
const OVER = ["completed", "cancelled", "expired", "voided"];

export function Table({ device, me }: { device: Device; me: Me }) {
  const toast = useToast();
  const ref = me.table?.ref ?? me.device.table_ref ?? "";
  const tab = me.venue.dine_in_mode === "tab";
  const waiterBrings = me.venue.serve_mode === "waiter";
  const [lang, setLang] = useState<Lang>("en");
  const t = (k: keyof typeof T.en) => (T[lang] as Record<string, string>)[k] ?? T.en[k];
  const w = (key: string, english: string) => word(lang, key, english);
  const L = (o: Text | undefined) => (o && (o[lang] || o.en)) || "";
  const langs = (me.venue.languages.filter((l) => l in LANG_NAMES) as Lang[]) || ["en"];

  const [open, setOpen] = useState(me.table ? me.table.access !== "staff_opens" || me.table.open : true);
  const [view, setView] = useState<View>("welcome");
  const [menu, setMenu] = useState<Menu | null>(null);
  const [cat, setCat] = useState<string | null>(null);
  const [cart, setCart] = useState<CartLine[]>([]);
  const [quote, setQuote] = useState<Quote | null>(null);
  const [review, setReview] = useState(false);
  const [order, setOrder] = useState<Order | null>(null);
  const [calls, setCalls] = useState<Call[]>([]);
  const [billSheet, setBillSheet] = useState(false);
  const [pending, setPending] = useState<Payment | null>(null);
  const [busy, setBusy] = useState(false);
  const idem = useRef<string | null>(null);
  const orderKey = `${device.key}:order`;
  const options = useKioskOptions(menu, L, t);

  const loadMenu = useCallback(() => device.get<Menu>("/v1/menu").then(setMenu).catch(() => {}), [device]);
  const loadCalls = useCallback(() => device.get<Call[]>("/v1/service-requests?mine=true").then(setCalls).catch(() => {}), [device]);
  const reset = useCallback(() => {
    store.set(orderKey, null);
    setCart([]), setQuote(null), setOrder(null), setPending(null), setReview(false), setBillSheet(false), setLang("en"), setView("welcome");
  }, [orderKey]);

  /** Follow our order. Paid (tab) or cancelled ends the visit on this screen. */
  const follow = useCallback(
    (o: Order) => {
      setOrder(o);
      if (["cancelled", "expired", "voided"].includes(o.status)) {
        toast(w("orderCancelled", "Your order was cancelled. Please call a waiter if this is wrong."), "bad", 7000);
        return reset();
      }
      if (o.payment_status === "paid") {
        setPending(null);
        setView((v) => (tab || v === "qr" || v === "card" ? "thanks" : v === "welcome" ? v : "order"));
      }
    },
    [tab, lang],
  );
  const refresh = useCallback(async () => {
    const id = order?.id ?? store.get<string>(orderKey);
    if (!id) return;
    try {
      follow(await device.get<Order>(`/v1/orders/${id}`));
    } catch {
      store.set(orderKey, null);
    }
  }, [order, follow]);

  useEffect(() => {
    void loadMenu();
    void loadCalls();
    // A reload (or a new day on the tablet) picks up this table's open order again.
    device
      .get<Order[]>(`/v1/orders?table_ref=${encodeURIComponent(ref)}&limit=10`)
      .then((list) => {
        const mine = list.find((o) => !OVER.includes(o.status) && !(o.payment_status === "paid" && (o.served_at || !waiterBrings)));
        if (mine) store.set(orderKey, mine.id), setOrder(mine), setView("order");
      })
      .catch(() => {});
  }, []);

  const live = useLive(device, (ev) => {
    const d = ev.data ?? {};
    if (ev.type.startsWith("menu.")) void loadMenu();
    if (ev.type === "venue.settings") location.reload();
    if (ev.type === "table.state" && d.table_ref === ref) setOpen(me.table?.access !== "staff_opens" || !!d.open);
    if (ev.type === "table.cleared" && d.table_ref === ref) reset();
    if (ev.type.startsWith("service.")) void loadCalls();
    const o = d.order as Order | undefined;
    if (o && (o.id === order?.id || (o.table_ref === ref && !order))) {
      if (ev.type === "order.ready") chime([880, 1320, 1760]);
      if (!order) store.set(orderKey, o.id);
      follow(o);
    }
  });
  // Waiting for a payment or following the kitchen: poll too, in case an event was missed.
  useEffect(() => {
    if (!["order", "qr", "card"].includes(view)) return;
    const p = setInterval(refresh, view === "order" ? 8000 : 2500);
    return () => clearInterval(p);
  }, [view, refresh]);

  // Price the cart on the server (never trust prices here).
  useEffect(() => {
    if (!cart.length) return setQuote(null);
    const h = setTimeout(() => device.post<Quote>("/v1/orders/quote", { items: toApiLines(cart, false) }).then(setQuote).catch((e) => toast(e.message, "bad")), 150);
    return () => clearTimeout(h);
  }, [cart]);

  // Guests walked away while browsing (nothing ordered): back to welcome. Thank-you clears itself.
  useEffect(() => {
    if (view !== "menu" && view !== "thanks") return;
    if (view === "menu" && order) return;
    let timer: ReturnType<typeof setTimeout>;
    const arm = () => (clearTimeout(timer), (timer = setTimeout(reset, (view === "thanks" ? THANKS_SECONDS : IDLE_BROWSING) * 1000)));
    arm();
    document.addEventListener("pointerdown", arm);
    return () => (clearTimeout(timer), document.removeEventListener("pointerdown", arm));
  }, [view, order]);

  const callWaiter = async () => {
    try {
      await device.post("/v1/service-requests", { kind: "call_waiter" });
      toast(w("called", "A waiter is on the way"), "ok");
      void loadCalls();
    } catch (e) {
      toast((e as Error).message, "bad");
    }
  };
  const add = async (i: MenuItem) => {
    const c = await options.ask(i);
    if (!c) return;
    setCart((lines) => {
      const sig = (x: Omit<CartLine, "key" | "qty" | "hold">) => [x.item.id, x.mods.map((m) => m.id).sort().join(), x.notes, x.combo?.choices.join()].join("|");
      const same = lines.find((x) => sig(x) === sig(c));
      return same ? lines.map((x) => (x === same ? { ...x, qty: Math.min(99, x.qty + 1) } : x)) : [...lines, { ...c, key: newKey(), qty: 1, hold: false }];
    });
  };
  const setQty = (key: string, q: number) => setCart((ls) => (q ? ls.map((x) => (x.key === key ? { ...x, qty: Math.min(99, q) } : x)) : ls.filter((x) => x.key !== key)));
  const send = async () => {
    setBusy(true);
    idem.current ||= newKey(); // the same key on a retry: the order is never sent twice
    try {
      const o = await device.post<Order>("/v1/orders", { items: toApiLines(cart, false) }, idem.current);
      idem.current = null;
      store.set(orderKey, o.id);
      setOrder(o), setCart([]), setReview(false), setView("order");
      toast(tab || o.status !== "placed" ? w("sentToKitchen", "Sent to the kitchen") : w("placedPay", "Order placed. Please pay to start cooking"), "ok");
    } catch (e) {
      const code = e instanceof ApiError ? e.code : "";
      if (code !== "network") idem.current = null;
      if (code === "table_closed") void callWaiter();
      toast((e as Error).message, "bad", 7000);
      void loadMenu();
    } finally {
      setBusy(false);
    }
  };
  const askBill = async (how: PayWith) => {
    if (!order) return;
    setBillSheet(false);
    if (how === "qr" && me.payments.lankaqr) return payHere("lankaqr");
    try {
      await device.post("/v1/service-requests", { kind: "request_bill", order_id: order.id, pay_with: how });
      toast(w("billComing", "Your waiter is bringing the bill"), "ok");
      void loadCalls();
    } catch (e) {
      toast((e as Error).message, "bad");
    }
  };
  const payHere = async (how: "lankaqr" | "card-terminal") => {
    if (!order) return;
    setBusy(true);
    try {
      const r = await device.post<{ payment: Payment; order: Order }>(`/v1/orders/${order.id}/payments/${how}`, {}, newKey());
      setPending(r.payment), setOrder(r.order), setView(how === "lankaqr" ? "qr" : "card");
    } catch (e) {
      const code = e instanceof ApiError ? e.code : "";
      toast(code === "lankaqr_unavailable" ? t("qrUnavailable") : code === "being_paid" ? w("beingPaid", "Your waiter is taking the payment") : (e as Error).message, "bad", 6000);
    } finally {
      setBusy(false);
    }
  };
  const stopPending = async () => {
    if (order && pending) await device.post(`/v1/orders/${order.id}/payments/${pending.id}/cancel`).catch(() => {});
    setPending(null), setView("order");
  };

  const count = cart.reduce((n, c) => n + c.qty, 0);
  const total = quote?.total ?? cartTotal(cart);
  const cats = menu?.categories ?? [];
  const current = cats.find((c) => c.id === cat) ?? cats[0];
  const inCart = (id: string) => cart.reduce((n, c) => n + (c.item.id === id ? c.qty : 0), 0);
  const labels = { subtotal: t("subtotal"), discount: w("discount", "Discount"), total: t("total") };
  const waiterCall = calls.find((c) => c.kind === "call_waiter" && c.status !== "done");
  const billCall = calls.find((c) => c.kind === "request_bill" && c.status !== "done");

  // ------------------------------------------------------------------ closed / welcome
  if (!open && !order)
    return (
      <div className="flex h-full flex-col items-center justify-center gap-8 bg-surface px-8 text-center text-ink" onPointerDown={unlockSound}>
        <Logo url={me.venue.brand?.logo_url} name={me.venue.name} size={88} className="rounded-3xl" />
        <div>
          <h1 className="text-[40px] font-bold leading-tight tracking-tight">{w("welcomeTable", "Welcome")}</h1>
          <p className="mt-2 text-xl text-muted">{w("tableClosed", "Your waiter will open this table for you in a moment.")}</p>
        </div>
        <CallButton call={waiterCall} onCall={callWaiter} w={w} big />
        <span className="text-sm font-semibold text-muted">
          {me.venue.name} · {w("table", "Table")} {ref}
        </span>
      </div>
    );
  if (view === "welcome")
    return (
      <div className="relative h-full" onPointerDown={unlockSound}>
        <Welcome me={me} langs={langs} t={t} onStart={(l) => (setLang(l), setView(order ? "order" : "menu"))} attract={me.venue.attract_images} dishes={cats.flatMap((c) => c.items)} />
        <span className="absolute right-8 top-10 rounded-full bg-ink/[.06] px-4 py-2 text-lg font-semibold">
          {w("table", "Table")} {ref}
        </span>
      </div>
    );

  // ------------------------------------------------------------------ the visit
  return (
    <div className="flex h-full flex-col overflow-hidden bg-surface text-ink" onPointerDown={unlockSound}>
      <header className="flex h-[72px] shrink-0 items-center gap-3 border-b border-line px-5 sm:px-8">
        <Logo url={me.venue.brand?.logo_url} name={me.venue.name} size={40} />
        <div className="min-w-0">
          <div className="truncate text-lg font-bold leading-tight tracking-tight">{me.venue.name}</div>
          <div className="text-sm text-muted">
            {w("table", "Table")} {ref}
          </div>
        </div>
        <span className="flex-1" />
        {langs.length > 1 ? (
          <div className="hidden rounded-full bg-ink/[.06] p-1 md:flex">
            {langs.map((l) => (
              <button key={l} onClick={() => setLang(l)} className={`relative h-10 rounded-full px-4 text-[15px] font-semibold ${l === lang ? "text-canvas" : "text-ink/60"}`}>
                {l === lang ? <motion.span layoutId="table-lang" transition={spring} className="absolute inset-0 rounded-full bg-ink" /> : null}
                <span className="relative">{LANG_NAMES[l]}</span>
              </button>
            ))}
          </div>
        ) : null}
        {order && view === "menu" ? (
          <Button size="lg" variant="soft" className="rounded-full" onClick={() => setView("order")}>
            <Receipt size={18} /> {w("myOrder", "My order")}
          </Button>
        ) : null}
        <CallButton call={waiterCall} onCall={callWaiter} w={w} />
        <LivePill status={live.status} via={live.via} />
      </header>

      <AnimatePresence mode="wait" initial={false}>
        <motion.div key={view} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.2 }} className="flex min-h-0 flex-1">
          {view === "menu" && menu ? (
            <>
              <div className="flex min-h-0 flex-1 flex-col">
                <nav className="flex shrink-0 gap-2 overflow-x-auto px-5 py-4 [scrollbar-width:none] sm:px-8">
                  {cats.map((c) => {
                    const on = c.id === current?.id;
                    const Icon = dishIcon(en(c.name), en(c.items[0]?.name));
                    return (
                      <button key={c.id} onClick={() => setCat(c.id)} className={`relative inline-flex h-12 shrink-0 items-center gap-2 rounded-full px-5 text-base font-semibold ${on ? "text-canvas" : "bg-ink/[.06]"}`}>
                        {on ? <motion.span layoutId="table-cat" transition={spring} className="absolute inset-0 rounded-full bg-ink" /> : null}
                        <Icon size={18} className="relative" />
                        <span className="relative">{L(c.name)}</span>
                      </button>
                    );
                  })}
                </nav>
                <main className={`min-h-0 flex-1 overflow-auto px-5 sm:px-8 ${count ? "pb-32 lg:pb-8" : "pb-8"}`}>
                  {current ? (
                    <div className="grid grid-cols-[repeat(auto-fill,minmax(200px,1fr))] gap-x-5 gap-y-7 pt-2">
                      {current.items.map((i) => (
                        <Dish key={i.id} i={i} n={inCart(i.id)} L={L} sold={t("soldOut")} onAdd={() => add(i)} />
                      ))}
                    </div>
                  ) : null}
                </main>
              </div>
              {/* Landscape tablets: the order on the right. */}
              <aside className="hidden w-[400px] shrink-0 flex-col border-l border-line px-6 pb-6 pt-5 lg:flex">
                <h2 className="text-2xl font-bold tracking-tight">{w("newRound", order ? "Add to your order" : "Your order")}</h2>
                <div className="mt-2 flex min-h-0 flex-1 flex-col divide-y divide-line overflow-auto">
                  {cart.map((c) => (
                    <Line key={c.key} c={c} L={L} onQty={(q) => setQty(c.key, q)} />
                  ))}
                  {!cart.length ? (
                    <div className="grid flex-1 place-items-center text-center text-muted">
                      <span className="flex flex-col items-center gap-3">
                        <ShoppingBag size={30} strokeWidth={1.6} className="text-ink/30" />
                        {w("pickDishes", "Tap a dish to add it")}
                      </span>
                    </div>
                  ) : null}
                </div>
                {cart.length ? (
                  <div className="border-t border-line pt-4">
                    <Totals quote={quote} fallback={total} labels={labels} L={L} />
                  </div>
                ) : null}
                <Button variant="primary" size="xl" className="mt-4 justify-between!" disabled={!count} onClick={() => setReview(true)}>
                  <span>{w("review", "Review order")}</span>
                  {count ? <span className="num">{money(total)}</span> : null}
                </Button>
              </aside>
              <AnimatePresence>
                {count ? (
                  <motion.button key="bar" initial={{ y: 120 }} animate={{ y: 0 }} exit={{ y: 120 }} transition={spring} onClick={() => setReview(true)} className="fixed inset-x-5 bottom-6 flex h-[72px] items-center gap-4 rounded-2xl bg-ink px-6 text-canvas shadow-[0_10px_30px_rgb(0_0_0/22%)] lg:hidden">
                    <span className="num grid h-10 min-w-10 place-items-center rounded-full bg-canvas/15 px-2 font-bold">{count}</span>
                    <span className="flex-1 text-left text-xl font-semibold">{w("review", "Review order")}</span>
                    <span className="num text-xl font-bold">{money(total)}</span>
                  </motion.button>
                ) : null}
              </AnimatePresence>
            </>
          ) : null}

          {view === "order" && order ? <OrderView order={order} me={me} tab={tab} waiterBrings={waiterBrings} billCall={billCall} device={device} lang={lang} L={L} w={w} labels={labels} busy={busy} onMore={() => setView("menu")} onBill={() => setBillSheet(true)} onPay={payHere} /> : null}

          {view === "qr" && pending ? (
            <Center>
              <h1 className="text-[34px] font-bold tracking-tight">{t("scan")}</h1>
              <p className="num mt-1 text-[44px] font-bold tracking-tight">{money(pending.amount)}</p>
              <div className="mx-auto mt-6 rounded-3xl bg-white p-6 ring-1 ring-line">
                <QRCodeSVG value={pending.qr_payload ?? ""} size={300} style={{ width: "min(300px, 38vh)", height: "auto" }} />
              </div>
              <Waiting text={t("waiting")} />
              {pending.gateway_ref ? (
                <div className="mt-4 flex justify-center">
                  <DevButtons kind="mock-gateway" ref_={pending.gateway_ref} />
                </div>
              ) : null}
              <Button variant="soft" size="lg" className="mt-6" onClick={stopPending}>
                {t("back")}
              </Button>
            </Center>
          ) : null}

          {view === "card" && pending ? (
            <Center>
              <span className="mx-auto grid h-36 w-36 place-items-center rounded-full bg-ink/[.06]">
                <CreditCard size={60} strokeWidth={1.5} />
              </span>
              <h1 className="mt-8 text-[34px] font-bold tracking-tight">{t("tapCard")}</h1>
              <p className="num mt-1 text-[44px] font-bold tracking-tight">{money(pending.amount)}</p>
              <Waiting text={t("cardWaiting")} />
              {pending.gateway_ref ? (
                <div className="mt-4 flex justify-center">
                  <DevButtons kind="mock-terminal" ref_={pending.gateway_ref} />
                </div>
              ) : null}
              <Button variant="soft" size="lg" className="mt-6" onClick={stopPending}>
                {t("back")}
              </Button>
            </Center>
          ) : null}

          {view === "thanks" && order ? (
            <Center>
              <motion.span initial={{ scale: 0.4 }} animate={{ scale: 1 }} transition={spring} className="mx-auto grid h-20 w-20 place-items-center rounded-full bg-ok text-white">
                <Check size={40} strokeWidth={3} />
              </motion.span>
              <h1 className="mt-6 text-[40px] font-bold tracking-tight">{w("thanks", "Thank you!")}</h1>
              <p className="mt-1 text-xl text-muted">{w("paidThanks", "Your bill is paid. We hope to see you again.")}</p>
              <div className="mx-auto mt-8 w-full max-w-[520px] text-left">
                <Rate device={device} order={order} lang={lang} first />
              </div>
              <Button variant="primary" size="xl" className="mt-8 w-full max-w-[520px]" onClick={reset}>
                {w("done", "Done")}
              </Button>
            </Center>
          ) : null}
        </motion.div>
      </AnimatePresence>

      {options.modal}

      {/* Review: what goes to the kitchen now. */}
      <Sheet open={review} onClose={() => setReview(false)}>
        <div className="flex items-center justify-between px-8 pb-2 pt-7">
          <h2 className="text-[30px] font-bold tracking-tight">{order && tab ? w("addRound", "Add to your order") : w("review", "Review order")}</h2>
          <button aria-label="Close" onClick={() => setReview(false)} className="grid h-12 w-12 place-items-center rounded-full bg-ink/[.06]">
            <X size={22} />
          </button>
        </div>
        <div className="min-h-0 flex-1 divide-y divide-line overflow-auto px-8">
          {cart.map((c) => (
            <Line key={c.key} c={c} L={L} big onQty={(q) => setQty(c.key, q)} />
          ))}
        </div>
        <div className="border-t border-line px-8 pb-8 pt-5">
          <Totals quote={quote} fallback={total} labels={labels} L={L} />
          <Button variant="primary" size="xl" className="mt-5 h-[72px] w-full justify-between! text-xl!" disabled={!cart.length || !quote || busy} onClick={send}>
            <span>{tab ? w("sendKitchen", "Send to the kitchen") : w("placeOrder", "Place order")}</span>
            <span className="num">{money(quote?.total)}</span>
          </Button>
          {tab ? <p className="mt-3 text-center text-[15px] text-muted">{w("payLater", "You pay at the end. Order more any time.")}</p> : null}
        </div>
      </Sheet>

      {/* Ask for the bill: how the guests want to pay. */}
      <Sheet open={billSheet} onClose={() => setBillSheet(false)}>
        <div className="px-8 pb-8 pt-7">
          <h2 className="text-[30px] font-bold tracking-tight">{w("howPay", "How would you like to pay?")}</h2>
          <p className="num mt-1 text-xl text-muted">
            {t("total")} {order ? money(order.total - order.paid_total) : ""}
          </p>
          <div className="mt-4 divide-y divide-line">
            {me.payments.cash ? <Way icon={<HandCoins size={28} />} title={w("payCash", "Cash")} sub={w("payCashSub", "Your waiter brings the bill and your change")} onClick={() => askBill("cash")} /> : null}
            <Way icon={<CreditCard size={28} />} title={w("payCardWaiter", "Card")} sub={w("payCardWaiterSub", "Your waiter brings the card machine")} onClick={() => askBill("card")} />
            {me.payments.lankaqr ? <Way icon={<QrCode size={28} />} title={w("payQr", "QR payment")} sub={w("payQrSub", "Scan a code here with your banking app")} onClick={() => askBill("qr")} /> : null}
          </div>
        </div>
      </Sheet>
    </div>
  );
}

// ------------------------------------------------------------------ parts

function OrderView({ order, me, tab, waiterBrings, billCall, device, lang, L, w, labels, busy, onMore, onBill, onPay }: { order: Order; me: Me; tab: boolean; waiterBrings: boolean; billCall?: Call; device: Device; lang: Lang; L: (o: Text | undefined) => string; w: (k: string, e: string) => string; labels: { subtotal: string; discount: string; total: string }; busy: boolean; onMore: () => void; onBill: () => void; onPay: (how: "lankaqr" | "card-terminal") => void }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const h = setInterval(() => setNow(Date.now()), 15000);
    return () => clearInterval(h);
  }, []);
  const paid = order.payment_status === "paid";
  const due = order.total - order.paid_total;
  const unpaidFirst = !tab && !paid && order.status === "placed";
  const mins = order.promised_at ? Math.ceil((new Date(order.promised_at).getTime() - now) / 60000) : 0;
  const [title, sub, Icon, tone] = unpaidFirst
    ? [w("payToStart", "Please pay to start cooking"), w("payToStartSub", "The kitchen starts as soon as it's paid"), Receipt, ""]
    : order.served_at
      ? [w("enjoy", "Enjoy your meal"), w("enjoySub", "Order more any time, or ask for the bill when you're ready"), Utensils, "text-ok"]
      : order.status === "ready" || order.status === "completed"
        ? waiterBrings
          ? [w("onItsWay", "On its way"), w("onItsWaySub", "Your waiter is bringing your food"), Utensils, "text-ok"]
          : [w("readyCollect", "Ready! Collect at the counter"), `${w("showNumber", "Show your number")} ${order.token}`, Check, "text-ok"]
        : [w("cooking", "Cooking"), mins > 0 ? `${w("readyIn", "Ready in about")} ${mins} min` : w("almost", "Almost ready"), ChefHat, ""];
  const status = (s: string) => (s === "done" ? w("itemReady", "Ready") : s === "in_progress" ? w("itemCooking", "Cooking") : s === "held" ? w("itemLater", "Later") : s === "voided" ? w("itemRemoved", "Removed") : w("itemQueued", "In the queue"));
  return (
    <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
      <div className="min-h-0 flex-1 overflow-auto px-5 py-6 sm:px-8">
        <motion.div key={title} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={spring} className="flex items-center gap-4">
          <span className={`grid h-16 w-16 shrink-0 place-items-center rounded-full bg-ink/[.06] ${tone}`}>
            <Icon size={30} />
          </span>
          <div className="min-w-0">
            <h1 className={`text-[34px] font-bold leading-tight tracking-tight ${tone}`}>{title}</h1>
            <p className="text-lg text-muted">{sub}</p>
          </div>
        </motion.div>
        <div className="mt-8 divide-y divide-line border-y border-line">
          {order.items
            .filter((i) => i.parent_position === null)
            .map((i) => (
              <div key={i.id} className="flex items-center gap-4 py-4">
                <span className="num w-8 text-lg font-bold">{i.quantity}×</span>
                <div className="min-w-0 flex-1">
                  <div className="truncate text-lg font-semibold">{L(i.name)}</div>
                  {i.modifiers.length || i.notes ? <div className="truncate text-[15px] text-muted">{[...i.modifiers.map((m) => L(m.name)), i.notes].filter(Boolean).join(" · ")}</div> : null}
                </div>
                <span className={`rounded-full px-3 py-1 text-sm font-semibold ${i.kds_status === "done" ? "bg-ok-soft text-ok" : i.kds_status === "in_progress" ? "bg-ink text-canvas" : "bg-ink/[.06] text-muted"}`}>{status(i.kds_status)}</span>
                <span className="num w-24 text-right text-lg">{money(i.line_total)}</span>
              </div>
            ))}
        </div>
        {order.served_at || paid ? (
          <div className="mt-8 max-w-[560px]">
            <Rate device={device} order={order} lang={lang} first={false} />
          </div>
        ) : null}
      </div>
      <aside className="shrink-0 border-t border-line px-5 pb-6 pt-5 sm:px-8 lg:w-[380px] lg:border-l lg:border-t-0">
        <div className="flex items-baseline justify-between">
          <span className="text-muted">{w("orderNo", "Order")}</span>
          <span className="num text-2xl font-bold">{order.token}</span>
        </div>
        <div className="mt-4">
          <Totals quote={order} fallback={order.total} labels={labels} L={L} />
        </div>
        {paid ? (
          <p className="mt-4 flex items-center gap-2 font-semibold text-ok">
            <Check size={18} /> {w("paid", "Paid")}
          </p>
        ) : null}
        <div className="mt-5 flex flex-col gap-3">
          {unpaidFirst ? (
            <>
              {me.payments.lankaqr ? (
                <Button variant="primary" size="xl" disabled={busy} onClick={() => onPay("lankaqr")}>
                  <QrCode size={22} /> {w("payQrHere", "Pay by QR here")}
                </Button>
              ) : null}
              {me.payments.card === "reader" ? (
                <Button variant="primary" size="xl" disabled={busy} onClick={() => onPay("card-terminal")}>
                  <CreditCard size={22} /> {w("payCardHere", "Pay by card here")}
                </Button>
              ) : null}
              <Button variant="soft" size="xl" onClick={onBill}>
                <HandCoins size={22} /> {w("payWaiter", "Pay the waiter")}
              </Button>
            </>
          ) : (
            <>
              {tab || !paid ? (
                <Button variant="soft" size="xl" onClick={onMore}>
                  <Plus size={22} /> {w("orderMore", "Order more")}
                </Button>
              ) : null}
              {tab && !paid && due > 0 ? (
                billCall ? (
                  <div className="rounded-2xl bg-ink/[.05] p-4">
                    <div className="font-semibold">{billCall.coming ? `${billCall.coming.name} ${w("isComing", "is coming with the bill")}` : w("billComing", "Your waiter is bringing the bill")}</div>
                    <button className="mt-1 text-[15px] font-semibold text-muted underline" onClick={onBill}>
                      {w("changeWay", "Change how to pay")}
                    </button>
                  </div>
                ) : (
                  <Button variant="primary" size="xl" onClick={onBill}>
                    <Receipt size={22} /> {w("askBill", "Ask for the bill")}
                  </Button>
                )
              ) : null}
            </>
          )}
        </div>
      </aside>
    </div>
  );
}

/** The always-there call button: "Call waiter", then "Called", then "Priya is coming". */
function CallButton({ call, onCall, w, big = false }: { call?: Call; onCall: () => void; w: (k: string, e: string) => string; big?: boolean }) {
  const label = call?.coming ? `${call.coming.name} ${w("coming", "is coming")}` : call ? w("calledShort", "Waiter called") : w("callWaiter", "Call waiter");
  return (
    <Button variant={call ? "ok" : big ? "primary" : "default"} size={big ? "xl" : "lg"} className={`rounded-full ${big ? "px-10" : ""}`} onClick={onCall} data-call>
      <BellRing size={big ? 22 : 18} /> {label}
    </Button>
  );
}

function Dish({ i, n, L, sold, onAdd }: { i: MenuItem; n: number; L: (o: Text | undefined) => string; sold: string; onAdd: () => void }) {
  return (
    <motion.button data-item={L(i.name)} disabled={!i.is_available} onClick={onAdd} whileTap={{ scale: 0.975 }} className="flex flex-col text-left">
      <span className="relative block">
        <Photo src={i.image_url} name={i.name.en ?? L(i.name)} className={`aspect-[4/3] w-full rounded-2xl ${i.is_available ? "" : "opacity-40 grayscale"}`} icon={48} />
        {i.is_available ? (
          <span className="absolute bottom-2.5 right-2.5 grid h-11 min-w-11 place-items-center rounded-full bg-ink px-2 text-canvas shadow-[0_2px_10px_rgb(0_0_0/18%)]">{n ? <span className="num font-bold">{n}</span> : <Plus size={22} strokeWidth={2.4} />}</span>
        ) : (
          <span className="absolute bottom-2.5 left-2.5 rounded-full bg-surface px-3 py-1 text-sm font-semibold">{sold}</span>
        )}
      </span>
      <span className="mt-2.5 line-clamp-1 text-lg font-semibold leading-tight">{L(i.name)}</span>
      <span className="line-clamp-1 min-h-[1.4em] text-[15px] text-muted">{L(i.description)}</span>
      <span className="num mt-0.5 flex items-baseline gap-2 text-[17px]">
        <span className="font-semibold">{money(i.offer?.price ?? i.price)}</span>
        {i.offer ? <s className="text-sm text-muted">{money(i.price)}</s> : null}
      </span>
    </motion.button>
  );
}

const Center = ({ children }: { children: React.ReactNode }) => <div className="flex min-h-0 flex-1 flex-col items-center justify-center overflow-auto px-6 py-8 text-center">{children}</div>;

const Way = ({ icon, title, sub, onClick }: { icon: React.ReactNode; title: string; sub: string; onClick: () => void }) => (
  <button onClick={onClick} className="flex w-full items-center gap-5 py-5 text-left transition active:opacity-70">
    <span className="grid h-14 w-14 shrink-0 place-items-center rounded-full bg-ink/[.06]">{icon}</span>
    <span className="min-w-0 flex-1">
      <span className="block text-xl font-semibold">{title}</span>
      <span className="block text-[15px] text-muted">{sub}</span>
    </span>
  </button>
);
