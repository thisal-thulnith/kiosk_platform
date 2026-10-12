// Self-service kiosk: welcome → menu → review → pay (QR, card reader, or at the counter) →
// track until ready. Nothing of a guest stays: idle screens reset, and the track view clears itself.
// Steps slide sideways (forward / back); every step keeps its content in the middle of the screen.
import { AnimatePresence, motion, useAnimate } from "motion/react";
import { ArrowRight, ChevronLeft, ChevronRight, Clock, CreditCard, HandCoins, Plus, QrCode, RotateCcw, ShoppingBag, X } from "lucide-react";
import { QRCodeSVG } from "qrcode.react";
import { useCallback, useEffect, useRef, useState } from "react";
import type { Device } from "../../lib/device";
import { en, money } from "../../lib/format";
import { newKey, ApiError } from "../../lib/net";
import { chime, unlockSound } from "../../lib/sound";
import { store } from "../../lib/store";
import type { Me, Menu, MenuItem, Order, Payment, Text } from "../../lib/types";
import T from "../../lib/i18n.json";
import { useLive } from "../../ui/hooks";
import { dishIcon } from "../../ui/food";
import { Button, IconButton, LivePill, spring, useToast } from "../../ui/kit";
import { Logo } from "../../ui/logo";
import { DevButtons } from "../../ui/payment";
import { type CartLine, cartTotal, toApiLines } from "../../ui/ordering";
import { type Lang, LANG_NAMES, Line, Photo, Sheet, Step, Totals, Track, Waiting, Welcome, useKioskOptions } from "./parts";

type View = "welcome" | "menu" | "review" | "pay" | "qr" | "card" | "counter" | "track";
type Quote = { subtotal: number; discount_total: number; tax_total: number; total: number; tax_lines: { name: Text; amount: number }[] };
const IDLE_MENU = 75; // seconds without a touch before "Still there?"
const IDLE_TRACK = 30; // the track view clears itself (privacy)
const STEP: Record<View, number> = { welcome: 0, menu: 1, review: 2, pay: 3, qr: 4, card: 4, counter: 4, track: 5 };
const slide = {
  enter: (d: number) => ({ opacity: 0, x: d * 80 }),
  center: { opacity: 1, x: 0 },
  exit: (d: number) => ({ opacity: 0, x: d * -80 }),
};

export function Kiosk({ device, me }: { device: Device; me: Me }) {
  const toast = useToast();
  const [lang, setLang] = useState<Lang>("en");
  const t = (k: keyof typeof T.en) => (T[lang] as Record<string, string>)[k] ?? T.en[k];
  const L = (o: Text | undefined) => (o && (o[lang] || o.en)) || "";
  const [view, setView] = useState<View>("welcome");
  const [menu, setMenu] = useState<Menu | null>(null);
  const [cat, setCat] = useState<string | null>(null);
  const [cart, setCart] = useState<CartLine[]>([]);
  const [quote, setQuote] = useState<Quote | null>(null);
  const [order, setOrder] = useState<Order | null>(null);
  const [pending, setPending] = useState<Payment | null>(null);
  const [busy, setBusy] = useState(false);
  const [still, setStill] = useState(false);
  const idem = useRef<string | null>(null);
  const orderKey = `${device.key}:order`;
  const options = useKioskOptions(menu, L, t);
  const langs = (me.venue.languages.filter((l) => l in LANG_NAMES) as Lang[]) || ["en"];

  const loadMenu = useCallback(() => device.get<Menu>("/v1/menu").then(setMenu), [device]);
  const reset = useCallback(() => {
    store.set(orderKey, null);
    setCart([]), setQuote(null), setOrder(null), setPending(null), setStill(false), setLang("en"), setView("welcome");
  }, [orderKey]);

  // Follow the order: paid moves on, cancelled / expired goes back to the start.
  const follow = useCallback(
    (o: Order) => {
      setOrder(o);
      if (["cancelled", "expired", "voided"].includes(o.status)) {
        toast(o.status === "expired" ? t("expired") : t("cancelled"), "bad", 6000);
        return reset();
      }
      const paid = o.payment_status === "paid" || o.status !== "placed";
      setView((v) => {
        if (paid && ["pay", "qr", "card", "counter"].includes(v)) {
          if (v !== "counter") toast(t("paid"), "ok");
          return "track";
        }
        if (v === "card") {
          const p = o.payments.find((x) => x.id === pending?.id);
          if (p?.status === "failed") return toast(t("cardDeclined"), "bad", 6000), setPending(null), "pay";
        }
        return v;
      });
    },
    [pending, lang],
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
    // A reload in the middle of an order picks it up again.
    const saved = store.get<string>(orderKey);
    if (saved) device.get<Order>(`/v1/orders/${saved}`).then((o) => (setOrder(o), setView(o.payment_status === "paid" || o.status !== "placed" ? "track" : "pay"))).catch(() => store.set(orderKey, null));
  }, []);
  const live = useLive(device, (ev) => {
    if (ev.type.startsWith("menu.")) void loadMenu();
    const o = ev.data?.order as Order | undefined;
    if (o && o.id === order?.id) {
      if (ev.type === "order.ready") chime([880, 1320, 1760]);
      follow(o);
    }
    if (ev.type === "venue.settings") location.reload();
  });
  // Card / QR: also poll, in case an event was missed.
  useEffect(() => {
    if (!["qr", "card", "counter", "track"].includes(view)) return;
    const p = setInterval(refresh, view === "track" ? 8000 : 2000);
    return () => clearInterval(p);
  }, [view, refresh]);

  // Price the cart on the server (never trust prices here).
  useEffect(() => {
    if (!cart.length) return setQuote(null);
    const h = setTimeout(() => device.post<Quote>("/v1/orders/quote", { items: toApiLines(cart, false) }).then(setQuote).catch((e) => toast(e.message, "bad")), 150);
    return () => clearTimeout(h);
  }, [cart]);

  // Idle: ask "Still there?" on the menu, clear the track view quietly.
  useEffect(() => {
    if (view === "welcome") return;
    let timer: ReturnType<typeof setTimeout>;
    const arm = () => {
      clearTimeout(timer);
      if (view === "track") timer = setTimeout(reset, IDLE_TRACK * 1000);
      else if (["menu", "review", "pay"].includes(view)) timer = setTimeout(() => setStill(true), IDLE_MENU * 1000);
    };
    arm();
    document.addEventListener("pointerdown", arm);
    return () => (clearTimeout(timer), document.removeEventListener("pointerdown", arm));
  }, [view]);
  useEffect(() => {
    if (!still) return;
    const h = setTimeout(async () => {
      if (order && order.payment_status === "unpaid" && order.status === "placed") await device.post(`/v1/orders/${order.id}/cancel`, { reason: "Guest left the kiosk" }).catch(() => {});
      reset();
    }, 20000);
    return () => clearTimeout(h);
  }, [still]);

  const add = async (i: MenuItem) => {
    const c = await options.ask(i);
    if (!c) return;
    setCart((lines) => {
      const sig = (x: Omit<CartLine, "key" | "qty" | "hold">) => [x.item.id, x.mods.map((m) => m.id).sort().join(), x.notes, x.combo?.choices.join()].join("|");
      const same = lines.find((x) => sig(x) === sig(c));
      return same ? lines.map((x) => (x === same ? { ...x, qty: Math.min(99, x.qty + 1) } : x)) : [...lines, { ...c, key: newKey(), qty: 1, hold: false }];
    });
  };
  const place = async () => {
    setBusy(true);
    idem.current ||= newKey();
    try {
      const o = await device.post<Order>("/v1/orders", { items: toApiLines(cart, false) }, idem.current);
      idem.current = null;
      store.set(orderKey, o.id);
      setOrder(o), setCart([]), setView("pay");
    } catch (e) {
      idem.current = null;
      toast((e as Error).message, "bad", 7000);
      void loadMenu();
    } finally {
      setBusy(false);
    }
  };
  const pay = async (how: "lankaqr" | "card" | "counter") => {
    if (!order) return;
    setBusy(true);
    try {
      if (how === "counter") {
        setView("counter");
        void device.post(`/v1/orders/${order.id}/print/token`).catch(() => {}); // slip with the number
      } else {
        const path = how === "lankaqr" ? "lankaqr" : "card-terminal";
        const r = await device.post<{ payment: Payment; order: Order }>(`/v1/orders/${order.id}/payments/${path}`, {}, newKey());
        setPending(r.payment), setOrder(r.order), setView(how === "lankaqr" ? "qr" : "card");
      }
    } catch (e) {
      toast(e instanceof ApiError && e.code === "lankaqr_unavailable" ? t("qrUnavailable") : (e as Error).message, "bad", 6000);
    } finally {
      setBusy(false);
    }
  };
  const stopPending = async () => {
    if (order && pending) await device.post(`/v1/orders/${order.id}/payments/${pending.id}/cancel`).catch(() => {});
    setPending(null), setView("pay");
  };
  const cancelOrder = async () => {
    if (order) await device.post(`/v1/orders/${order.id}/cancel`, { reason: "Cancelled by guest on screen" }).catch(() => {});
    toast(t("cancelled"));
    reset();
  };

  const count = cart.reduce((n, c) => n + c.qty, 0);
  const cats = menu?.categories ?? [];
  const current = cats.find((c) => c.id === cat) ?? cats[0];
  const scroller = useRef<HTMLElement>(null);
  const lock = useRef(0);
  const goTo = (id: string) => {
    const el = scroller.current?.querySelector<HTMLElement>(`[data-cat="${id}"]`);
    lock.current = Date.now() + 800; // the tiles stay on the chosen one while it scrolls there
    setCat(id);
    scroller.current?.scrollTo({ top: el ? el.offsetTop : 0, behavior: "smooth" });
  };
  const spy = () => {
    const box = scroller.current;
    if (!box || Date.now() < lock.current) return;
    const secs = [...box.querySelectorAll<HTMLElement>("[data-cat]")];
    const at = secs.filter((el) => el.offsetTop <= box.scrollTop + 160).pop() ?? secs[0];
    if (at && at.dataset.cat !== current?.id) setCat(at.dataset.cat!);
  };
  const inCart = (id: string) => cart.reduce((n, c) => n + (c.item.id === id ? c.qty : 0), 0);
  const setQty = (key: string, q: number) => setCart((ls) => (q ? ls.map((x) => (x.key === key ? { ...x, qty: Math.min(99, q) } : x)) : ls.filter((x) => x.key !== key)));
  const total = quote?.total ?? cartTotal(cart);
  const itemsLabel = `${count} ${count === 1 && lang === "en" ? "item" : t("items")}`;
  const labels = { subtotal: t("subtotal"), discount: lang === "en" ? "Discount" : t("off"), total: t("total") };

  // Which way the next step slides: forward goes left, back goes right.
  const nav = useRef({ view, dir: 1 });
  if (nav.current.view !== view) nav.current = { view, dir: STEP[view] >= STEP[nav.current.view] ? 1 : -1 };
  const dir = nav.current.dir;

  // The cart bar gives a small bounce each time something is added.
  const [bar, animateBar] = useAnimate();
  const lastCount = useRef(count);
  useEffect(() => {
    if (count > lastCount.current && bar.current) void animateBar(bar.current, { scale: [1, 1.035, 1] }, { duration: 0.38, ease: "easeOut" });
    lastCount.current = count;
  }, [count]);

  return (
    <div className="flex h-full flex-col overflow-hidden bg-surface text-ink" onPointerDown={unlockSound}>
      <AnimatePresence mode="wait" initial={false}>
        {view === "welcome" ? (
          <motion.div key="welcome" className="h-full" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0, scale: 1.01 }} transition={{ duration: 0.25 }}>
            <Welcome me={me} langs={langs} t={t} onStart={(l) => (setLang(l), setView("menu"))} attract={me.venue.attract_images} dishes={cats.flatMap((c) => c.items)} />
          </motion.div>
        ) : (
          <motion.div key="flow" className="flex min-h-0 flex-1 flex-col" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.25 }}>
            <header className="flex shrink-0 items-center gap-4 px-10 pb-4 pt-7">
              <Logo url={me.venue.brand?.logo_url} name={me.venue.name} size={52} />
              <span className="min-w-0 truncate text-[26px] font-bold tracking-tight">{me.venue.name}</span>
              <span className="flex-1" />
              {view === "menu" && langs.length > 1 ? (
                <div className="flex rounded-full bg-ink/[.06] p-1">
                  {langs.map((l) => (
                    <button key={l} onClick={() => setLang(l)} className={`relative h-12 rounded-full px-5 text-[17px] font-semibold transition-colors ${l === lang ? "text-canvas" : "text-ink/60"}`}>
                      {l === lang ? <motion.span layoutId="kiosk-lang" transition={spring} className="absolute inset-0 rounded-full bg-ink" /> : null}
                      <span className="relative">{LANG_NAMES[l]}</span>
                    </button>
                  ))}
                </div>
              ) : null}
              {view === "menu" && count ? (
                <IconButton label="Start over" size={56} onClick={reset}>
                  <RotateCcw size={22} />
                </IconButton>
              ) : null}
              <LivePill status={live.status} via={live.via} />
            </header>

            <AnimatePresence mode="wait" initial={false} custom={dir}>
              <motion.div key={view} custom={dir} variants={slide} initial="enter" animate="center" exit="exit" transition={{ x: spring, opacity: { duration: 0.18 } }} className="relative flex min-h-0 flex-1 flex-col">
                {view === "menu" && menu ? (
                  <div className="flex min-h-0 flex-1">
                    <div className="flex min-h-0 flex-1 flex-col">
                      <nav className="flex shrink-0 gap-3 overflow-x-auto border-b border-line px-10 pb-5 pt-2 [scrollbar-width:none]">
                        {cats.map((c) => {
                          const on = c.id === current?.id;
                          const Icon = dishIcon(en(c.name), en(c.items[0]?.name));
                          return (
                            <motion.button key={c.id} whileTap={{ scale: 0.96 }} onClick={() => goTo(c.id)} className={`relative inline-flex h-16 shrink-0 items-center gap-2.5 rounded-full px-7 text-xl font-semibold transition-colors ${on ? "text-canvas" : "bg-ink/[.06] text-ink"}`}>
                              {on ? <motion.span layoutId="kiosk-cat" transition={spring} className="absolute inset-0 rounded-full bg-ink" /> : null}
                              <Icon size={22} strokeWidth={1.9} className="relative" />
                              <span className="relative">{L(c.name)}</span>
                            </motion.button>
                          );
                        })}
                      </nav>
                      {/* Every category in one smooth scroll; the pills above follow where the guest is. */}
                      <main ref={scroller} onScroll={spy} className={`relative min-h-0 flex-1 overflow-auto px-10 landscape:pb-10 ${count ? "pb-44" : "pb-10"}`}>
                        {cats.map((c) => (
                          <div key={c.id} data-cat={c.id} className="pt-8">
                            <h2 className="text-[34px] font-bold tracking-tight">{L(c.name)}</h2>
                            <div className="grid grid-cols-[repeat(auto-fill,minmax(280px,1fr))] gap-x-6 gap-y-10 pb-4 pt-5">
                              {c.items.map((i) => (
                                <DishCard key={i.id} i={i} n={inCart(i.id)} L={L} t={t} onAdd={() => add(i)} />
                              ))}
                            </div>
                          </div>
                        ))}
                      </main>
                    </div>

                    {/* Landscape kiosks: the order sits on the right, like a "Your order" panel. */}
                    <aside className="hidden w-[460px] shrink-0 flex-col border-l border-line bg-surface px-8 pb-8 pt-2 landscape:flex">
                      <h2 className="flex items-baseline justify-between gap-3 text-[28px] font-bold tracking-tight">
                        {t("cart")}
                        {count ? <span className="num text-lg font-medium text-muted">{itemsLabel}</span> : null}
                      </h2>
                      <div className="mt-2 flex min-h-0 flex-1 flex-col divide-y divide-line overflow-auto">
                        <AnimatePresence initial={false} mode="popLayout">
                          {cart.map((c) => (
                            <motion.div key={c.key} layout initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, x: 40 }} transition={spring}>
                              <Line c={c} L={L} onQty={(q) => setQty(c.key, q)} />
                            </motion.div>
                          ))}
                        </AnimatePresence>
                        {!cart.length ? (
                          <div className="grid flex-1 place-items-center text-center text-muted">
                            <span className="flex flex-col items-center gap-4 text-xl">
                              <span className="grid h-20 w-20 place-items-center rounded-full bg-ink/[.05] text-ink/40">
                                <ShoppingBag size={32} strokeWidth={1.6} />
                              </span>
                              {t("empty")}
                            </span>
                          </div>
                        ) : null}
                      </div>
                      {cart.length ? (
                        <div className="border-t border-line pt-5">
                          <Totals quote={quote} fallback={total} labels={labels} L={L} />
                        </div>
                      ) : null}
                      <Button variant="primary" size="xl" className="mt-5 h-[76px] justify-between! px-7! text-xl!" disabled={!count} onClick={() => setView("review")}>
                        <span>{t("review")}</span>
                        {count ? <span className="num">{money(total)}</span> : <ArrowRight size={24} />}
                      </Button>
                    </aside>

                    <AnimatePresence>
                      {count ? (
                        <motion.div key="bar" initial={{ y: 160, opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ y: 160, opacity: 0 }} transition={spring} className="absolute inset-x-10 bottom-9 landscape:hidden">
                          <button ref={bar} onClick={() => setView("review")} className="flex h-[96px] w-full items-center gap-5 rounded-2xl bg-ink px-7 text-canvas shadow-[0_10px_30px_rgb(0_0_0/22%)] transition active:scale-[.99]">
                            <span className="num relative grid h-12 min-w-12 place-items-center overflow-hidden rounded-full bg-canvas/15 px-3 text-xl font-bold">
                              <AnimatePresence mode="popLayout" initial={false}>
                                <motion.span key={count} initial={{ y: -20, opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ y: 20, opacity: 0 }} transition={spring}>
                                  {count}
                                </motion.span>
                              </AnimatePresence>
                            </span>
                            <span className="flex-1 text-left text-[26px] font-semibold">{t("review")}</span>
                            <span className="num text-[26px] font-bold">{money(total)}</span>
                          </button>
                        </motion.div>
                      ) : null}
                    </AnimatePresence>
                  </div>
                ) : null}

                {view === "review" ? (
                  <Step
                    top
                    foot={
                      <>
                        <Button variant="soft" size="xl" className="h-20 px-8" onClick={() => setView("menu")}>
                          <ChevronLeft size={26} />
                          {t("back")}
                        </Button>
                        <Button variant="primary" size="xl" className="h-20 flex-1 justify-between! px-9! text-2xl!" disabled={!cart.length || !quote || busy} onClick={place}>
                          <span>{t("confirm")}</span>
                          <span className="num">{money(quote?.total)}</span>
                        </Button>
                      </>
                    }
                  >
                    <div className="flex flex-1 flex-col landscape:grid landscape:grid-cols-[1.5fr_1fr] landscape:items-start landscape:gap-14">
                      <div>
                        <div className="flex items-baseline justify-between gap-4">
                          <h1 className="text-[48px] font-bold tracking-tight">{t("cart")}</h1>
                          <span className="num text-2xl text-muted">{itemsLabel}</span>
                        </div>
                        <div className="mt-4 divide-y divide-line border-y border-line">
                          <AnimatePresence initial={false} mode="popLayout">
                            {cart.map((c) => (
                              <motion.div key={c.key} layout exit={{ opacity: 0, x: -60 }} transition={spring}>
                                <Line c={c} L={L} big onQty={(q) => setQty(c.key, q)} />
                              </motion.div>
                            ))}
                          </AnimatePresence>
                          {!cart.length ? <p className="py-14 text-center text-xl text-muted">{t("empty")}</p> : null}
                        </div>
                      </div>
                      <motion.div layout className="mt-auto pt-10 landscape:mt-0 landscape:rounded-2xl landscape:bg-ink/[.035] landscape:p-8">
                        <Totals quote={quote} fallback={total} labels={labels} L={L} big />
                      </motion.div>
                    </div>
                  </Step>
                ) : null}

                {view === "pay" && order ? (
                  <Step
                    foot={
                      <Button variant="ghost" size="xl" className="text-bad! hover:bg-bad-soft!" onClick={cancelOrder}>
                        <X size={24} />
                        {t("cancel")}
                      </Button>
                    }
                  >
                    <div className="flex items-end justify-between gap-6 border-b border-line pb-8">
                      <div>
                        <div className="text-2xl text-muted">{t("yourNumber")}</div>
                        <div className="num mt-1 text-[96px] font-black leading-none tracking-[-0.04em]" data-token={order.token} aria-label={t("yourNumber")}>
                          {order.token}
                        </div>
                      </div>
                      <div className="text-right">
                        <div className="text-2xl text-muted">{t("total")}</div>
                        <div className="num mt-1 text-[48px] font-bold leading-none tracking-tight">{money(order.total - order.paid_total)}</div>
                      </div>
                    </div>
                    <h1 className="mb-3 mt-12 text-[44px] font-bold leading-tight tracking-tight">{t("payHow")}</h1>
                    <div className="divide-y divide-line">
                      {me.payments.lankaqr ? <Way icon={<QrCode size={34} strokeWidth={1.8} />} title={t("payHere")} sub={t("payHereSub")} onClick={() => pay("lankaqr")} disabled={busy} /> : null}
                      {me.payments.card === "reader" ? <Way icon={<CreditCard size={34} strokeWidth={1.8} />} title={t("payCard")} sub={t("payCardSub")} onClick={() => pay("card")} disabled={busy} /> : null}
                      <Way icon={<HandCoins size={34} strokeWidth={1.8} />} title={t("payCashier")} sub={t("payCashierSub")} onClick={() => pay("counter")} disabled={busy} />
                    </div>
                  </Step>
                ) : null}

                {view === "qr" && order && pending ? (
                  <Step foot={<BackButton label={t("back")} onClick={stopPending} />}>
                    <h1 className="text-center text-[44px] font-bold tracking-tight">{t("scan")}</h1>
                    <p className="num mt-1 text-center text-[56px] font-bold tracking-tight">{money(pending.amount)}</p>
                    <motion.div initial={{ scale: 0.94, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} transition={{ ...spring, delay: 0.1 }} className="mx-auto mt-10 rounded-3xl bg-white p-8 ring-1 ring-line">
                      <QRCodeSVG value={pending.qr_payload ?? ""} size={440} style={{ width: "min(440px, 40vh)", height: "auto" }} />
                    </motion.div>
                    <Waiting text={t("waiting")} />
                    {pending.gateway_ref ? (
                      <div className="mt-4 flex justify-center">
                        <DevButtons kind="mock-gateway" ref_={pending.gateway_ref} />
                      </div>
                    ) : null}
                  </Step>
                ) : null}

                {view === "card" && order && pending ? (
                  <Step foot={<BackButton label={t("back")} onClick={stopPending} />}>
                    <div className="relative mx-auto mb-12 grid h-56 w-56 place-items-center">
                      <motion.span className="absolute inset-0 rounded-full bg-ink/[.05]" animate={{ scale: [1, 1.1, 1], opacity: [1, 0.5, 1] }} transition={{ duration: 2, repeat: Infinity, ease: "easeInOut" }} />
                      <span className="absolute inset-8 rounded-full bg-ink/[.06]" />
                      <CreditCard size={84} className="relative" strokeWidth={1.5} />
                    </div>
                    <h1 className="text-center text-[44px] font-bold tracking-tight">{t("tapCard")}</h1>
                    <p className="num mt-1 text-center text-[56px] font-bold tracking-tight">{money(pending.amount)}</p>
                    <Waiting text={t("cardWaiting")} />
                    {pending.gateway_ref ? (
                      <div className="mt-4 flex justify-center">
                        <DevButtons kind="mock-terminal" ref_={pending.gateway_ref} />
                      </div>
                    ) : null}
                  </Step>
                ) : null}

                {view === "counter" && order ? (
                  <Step
                    foot={
                      <Button size="xl" variant="primary" className="h-20 w-full max-w-[640px] text-2xl!" onClick={reset}>
                        {t("newOrder")}
                      </Button>
                    }
                  >
                    <motion.div initial={{ scale: 0.96, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} transition={{ ...spring, delay: 0.08 }} className="mx-auto w-full max-w-[640px] text-center">
                      <span className="mx-auto grid h-20 w-20 place-items-center rounded-full bg-ink/[.06]">
                        <HandCoins size={36} strokeWidth={1.8} />
                      </span>
                      <p className="mt-6 text-[36px] font-bold leading-tight tracking-tight">{t("showNumber")}</p>
                      <div className="num mt-4 text-[220px] font-black leading-none tracking-[-0.05em] landscape:text-[170px]" data-token={order.token} aria-label={t("yourNumber")}>
                        {order.token}
                      </div>
                      <div className="mt-10 flex items-baseline justify-between border-t border-line pt-7">
                        <span className="text-2xl text-muted">{t("total")}</span>
                        <span className="num text-[52px] font-bold tracking-tight">{money(order.total - order.paid_total)}</span>
                      </div>
                      <div className="mt-6 inline-flex items-center gap-2 rounded-full bg-ink/[.06] px-5 py-2.5 text-lg font-medium text-ink/70">
                        <Clock size={20} />
                        {t("expires")} 15 {t("minutes")}
                      </div>
                    </motion.div>
                  </Step>
                ) : null}

                {view === "track" && order ? <Track device={device} order={order} t={t} lang={lang} onDone={reset} /> : null}
              </motion.div>
            </AnimatePresence>
          </motion.div>
        )}
      </AnimatePresence>
      {options.modal}
      <Sheet open={still} onClose={() => setStill(false)}>
        <div className="px-10 pb-10 pt-10">
          <h2 className="text-[40px] font-bold tracking-tight">{t("stillThere")}</h2>
          <Button variant="primary" size="xl" className="mt-8 h-20 w-full text-2xl!" onClick={() => setStill(false)}>
            {t("continue")}
          </Button>
        </div>
      </Sheet>
    </div>
  );
}

type TFn = (k: keyof typeof T.en) => string;

/** A dish card, Uber Eats style: a big rectangular photo with a round black "+", then the name, one
 *  line of description and the price. The "+" shows how many are in the order. */
function DishCard({ i, n, L, t, onAdd }: { i: MenuItem; n: number; L: (o: Text | undefined) => string; t: TFn; onAdd: () => void }) {
  const meta = [i.combo_slots.length ? t("meal") : "", L(i.description) || i.allergens.join(" · ")].filter(Boolean).join(" · ");
  return (
    <motion.button data-item={L(i.name)} disabled={!i.is_available} onClick={onAdd} whileTap={{ scale: 0.975 }} className="group flex flex-col text-left">
      <span className="relative block">
        <Photo src={i.image_url} name={i.name.en ?? L(i.name)} className={`aspect-[4/3] w-full rounded-2xl ${i.is_available ? "" : "opacity-40 grayscale"}`} icon={64} />
        {i.offer ? <span className="absolute left-3 top-3 rounded-full bg-ok px-3 py-1 text-[15px] font-semibold text-white">{t("deal")}</span> : null}
        {i.is_available ? (
          <span className="absolute bottom-3 right-3 grid h-14 min-w-14 place-items-center rounded-full bg-ink px-3 text-canvas shadow-[0_2px_10px_rgb(0_0_0/18%)]">
            <AnimatePresence mode="popLayout" initial={false}>
              {n ? (
                <motion.span key={n} initial={{ scale: 0.4, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} exit={{ scale: 0.4, opacity: 0 }} transition={{ type: "spring", stiffness: 600, damping: 22 }} className="num text-xl font-bold">
                  {n}
                </motion.span>
              ) : (
                <motion.span key="plus" initial={{ scale: 0.4, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} exit={{ scale: 0.4, opacity: 0 }}>
                  <Plus size={28} strokeWidth={2.4} />
                </motion.span>
              )}
            </AnimatePresence>
          </span>
        ) : (
          <span className="absolute bottom-3 left-3 rounded-full bg-surface px-3.5 py-1.5 text-base font-semibold text-ink">{t("soldOut")}</span>
        )}
      </span>
      <span className="mt-3.5 line-clamp-1 text-[22px] font-semibold leading-tight">{L(i.name)}</span>
      <span className="mt-1 line-clamp-1 min-h-[1.5em] text-lg text-muted">{meta}</span>
      <span className="num mt-1 flex items-baseline gap-2 text-xl">
        <span className="font-semibold">{money(i.offer?.price ?? i.price)}</span>
        {i.offer ? <s className="text-base text-muted">{money(i.price)}</s> : null}
      </span>
    </motion.button>
  );
}

/** A way to pay: one list row with an icon, title, one line and a chevron. */
const Way = ({ icon, title, sub, onClick, disabled }: { icon: React.ReactNode; title: string; sub: string; onClick: () => void; disabled?: boolean }) => (
  <motion.button whileTap={{ scale: 0.99 }} disabled={disabled} onClick={onClick} className="flex w-full items-center gap-6 py-7 text-left transition active:opacity-70 disabled:opacity-50">
    <span className="grid h-20 w-20 shrink-0 place-items-center rounded-full bg-ink/[.06]">{icon}</span>
    <span className="min-w-0 flex-1">
      <span className="block text-[28px] font-semibold leading-tight tracking-tight">{title}</span>
      <span className="mt-1 block text-xl leading-snug text-muted">{sub}</span>
    </span>
    <ChevronRight size={30} className="shrink-0 text-ink/40" />
  </motion.button>
);

const BackButton = ({ label, onClick }: { label: string; onClick: () => void }) => (
  <Button variant="soft" size="xl" className="h-20 px-10" onClick={onClick}>
    <ChevronLeft size={26} />
    {label}
  </Button>
);
