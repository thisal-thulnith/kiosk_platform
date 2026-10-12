// Taking a payment, safely: cash (change worked out), the card reader, QR, or the bank's own card
// machine (its approval code), and splitting the bill (POS).
// Money can't go wrong:
//  - one payment at a time: opening this window holds the bill for you (renewed every minute, freed
//    when you close it); someone else holding it sees "Nimal is taking this payment right now";
//  - every money call carries one key; a retry of the same attempt reuses it (never charged twice);
//  - a network error first checks the server ("Checking the payment…") before allowing a retry;
//  - while the live connection is down, the money buttons pause.
import { AnimatePresence, motion } from "motion/react";
import { Banknote, Check, ChevronLeft, ChevronRight, CreditCard, Loader2, QrCode, ReceiptText, UserRound, WifiOff, type LucideIcon } from "lucide-react";
import { QRCodeSVG } from "qrcode.react";
import { useEffect, useRef, useState } from "react";
import type { Device } from "../lib/device";
import { money, toCents } from "../lib/format";
import { ApiError, net, newKey } from "../lib/net";
import type { Me, Order, Payment, PaymentHold, PayResult, PayWith } from "../lib/types";
import { Button, ease, inputCls, Modal, Segmented, useToast } from "./kit";

const NOTES = [50000, 100000, 200000, 500000];
type Step = "choose" | "cash" | "card" | "qr" | "manual";
type Kind = "cash" | "card" | "terminal" | "qr";
const note = (cents: number) => `Rs ${(cents / 100).toLocaleString("en-LK")}`;

/** How the guest said they will pay (on their bill request). */
export const PAY_WITH: Record<PayWith, string> = { cash: "Cash", card: "Card", qr: "QR" };

/** What happened, for the "Paid" window: the change to give and where the receipt printed. */
export type Receipt = { order: Order; method: string; amount: number; change: number | null; printedAt: string[] | null };

/** The name of whoever else is taking this payment right now (null: nobody, or it is me). */
export function heldByOther(o: { payment_hold?: PaymentHold | null } | null | undefined, me: Me): string | null {
  const h = o?.payment_hold;
  if (!h || new Date(h.until).getTime() < Date.now()) return null;
  if (h.staff_id && h.staff_id === me.staff?.id) return null;
  return h.name || "Someone";
}

/** Show the "No connection" bar: offline, or still connecting after a few seconds (not at start-up). */
export function useNoConnection(status: string): boolean {
  const [late, setLate] = useState(false);
  useEffect(() => {
    if (status === "online") return setLate(false);
    const t = setTimeout(() => setLate(true), status === "connecting" ? 4000 : 800);
    return () => clearTimeout(t);
  }, [status]);
  return status !== "online" && late;
}

/** The one clear bar while the live connection is down. */
export function OfflineBar({ className = "" }: { className?: string }) {
  return (
    <div role="alert" className={`flex items-center justify-center gap-2 bg-bad px-4 py-2 text-center text-sm font-semibold text-white ${className}`}>
      <WifiOff size={16} className="shrink-0" /> No connection — payments paused
    </div>
  );
}

export function PaymentModal({ device, me, order: start, online, onClose, onPaid, split = false }: { device: Device; me: Me; order: Order; online: boolean; onClose: () => void; onPaid: (r: Receipt) => void; split?: boolean }) {
  const toast = useToast();
  const [order, setOrder] = useState(start);
  const due = order.total - order.paid_total;
  const [share, setShare] = useState<number | null>(null);
  const amount = Math.min(share ?? due, due);
  const [step, setStep] = useState<Step>("choose");
  const [tendered, setTendered] = useState((due / 100).toFixed(2));
  const [pending, setPending] = useState<Payment | null>(null);
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  // The payment hold: "wait" until the server says it is ours, "ok", or who else is taking it.
  const [hold, setHold] = useState<"wait" | "ok" | { other: string }>("wait");
  // After a network error: checking the server, it was not paid (retry allowed), or still unreachable.
  const [check, setCheck] = useState<null | "checking" | "unpaid" | "unreachable">(null);
  const idem = useRef(newKey()); // one key per payment attempt; a retry of the same attempt reuses it
  const attempt = useRef<{ kind: Kind; before: number; run: () => Promise<void> } | null>(null);
  const held = useRef(false);
  const paid = useRef(false);
  const body = share && share < due ? { amount: share } : {};
  const ready = online && hold === "ok" && !check && !busy;

  // Hold the bill while this window is open (renewed every minute), free it when closed unpaid.
  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const path = `/v1/orders/${start.id}/payment-hold`;
    const take = async () => {
      let next = 60_000;
      try {
        await device.post<Order>(path);
        held.current = true;
        if (alive) setHold("ok");
      } catch (x) {
        const e = x as ApiError;
        if (e.code === "being_paid") {
          next = 10_000; // look again soon: they may finish or give up
          if (alive) setHold({ other: e.message });
        } else if (e.code === "already_paid") {
          if (alive) setHold({ other: "This bill is already paid" });
        } else if (alive) {
          setHold((h) => (h === "wait" ? "ok" : h)); // older server or a network blip: the server still checks every payment
          if (e.status === 0) next = 10_000;
        }
      }
      if (alive) timer = setTimeout(take, next);
    };
    void take();
    return () => {
      alive = false;
      clearTimeout(timer);
      if (held.current && !paid.current) device.api("DELETE", path).catch(() => {});
    };
  }, [start.id]);

  const finish = (r: PayResult, method: string, change: number | null) => {
    idem.current = newKey();
    attempt.current = null;
    setCheck(null);
    if (r.order.payment_status === "paid") paid.current = true;
    onPaid({ order: r.order, method, amount: r.payment?.amount ?? amount, change, printedAt: r.printed_at ?? null });
  };

  // Card and QR: wait for the bank's confirmation.
  useEffect(() => {
    if (!pending) return;
    const iv = setInterval(async () => {
      const o = await device.get<Order>(`/v1/orders/${order.id}`).catch(() => null);
      const p = o?.payments.find((x) => x.id === pending.id);
      if (o && p?.status === "succeeded") {
        clearInterval(iv);
        finish({ payment: p, order: o }, pending.method, null);
      } else if (p && ["failed", "cancelled"].includes(p.status)) {
        clearInterval(iv);
        toast(p.status === "failed" ? "Declined. Try again or another way" : "Cancelled", "bad");
        setPending(null);
        setStep("choose");
      }
    }, 1500);
    return () => clearInterval(iv);
  }, [pending]);

  /** After a network error: did the money go through? Only then allow a retry (with the same key). */
  const verify = async () => {
    const a = attempt.current;
    if (!a) return setCheck(null);
    setCheck("checking");
    try {
      const o = await device.get<Order>(`/v1/orders/${order.id}`);
      setOrder(o);
      const charges = o.payments.filter((p) => p.kind === "charge").sort((x, y) => y.created_at.localeCompare(x.created_at));
      const got = charges.find((p) => p.status === "succeeded");
      if (o.paid_total > a.before || o.payment_status === "paid") {
        toast("It went through: paid", "ok");
        return finish({ payment: got ?? charges[0], order: o }, got?.method ?? a.kind, got?.change_given ?? null);
      }
      const wait = charges.find((p) => p.status === "pending");
      if (wait && (a.kind === "terminal" || a.kind === "qr")) {
        setCheck(null);
        setPending(wait);
        setStep(a.kind === "qr" ? "qr" : "card");
        return;
      }
      setCheck("unpaid");
    } catch {
      setCheck("unreachable");
    }
  };
  // Back online while we could not check: check now.
  useEffect(() => {
    if (online && check === "unreachable") void verify();
  }, [online]);

  /** Run one money call. A network error means "we don't know yet": check before anything else. */
  const pay = async (kind: Kind, call: () => Promise<void>) => {
    const before = order.paid_total;
    const run = async () => {
      setBusy(true);
      setCheck(null);
      try {
        await call();
      } catch (x) {
        const e = x as ApiError;
        if (e.status === 0) {
          attempt.current = { kind, before, run };
          await verify();
        } else if (e.code === "being_paid") {
          setHold({ other: e.message });
        } else {
          idem.current = newKey(); // the server said no: nothing was taken, a new attempt gets a new key
          toast(e.message, "bad", 6000);
        }
      } finally {
        setBusy(false);
      }
    };
    attempt.current = { kind, before, run };
    await run();
  };

  const cancelPending = async () => {
    if (!pending) return setStep("choose");
    try {
      await device.post(`/v1/orders/${order.id}/payments/${pending.id}/cancel`);
      setPending(null);
      setStep("choose");
      idem.current = newKey();
    } catch (x) {
      toast((x as Error).message, "bad");
    }
  };
  const back = () => {
    idem.current = newKey(); // a new choice is a new attempt
    setStep("choose");
  };
  const t = toCents(tendered);
  const parts = share === null ? "1" : (["2", "3", "4"].find((n) => Math.ceil(due / +n) === share) ?? "1");

  const payCash = () =>
    pay("cash", async () => {
      const r = await device.post<PayResult>(`/v1/orders/${order.id}/payments/cash`, { tendered: t, ...body }, idem.current);
      finish(r, "cash", r.payment?.change_given ?? t - amount);
    });
  const payManual = () =>
    pay("card", async () => {
      const r = await device.post<PayResult>(`/v1/orders/${order.id}/payments/card`, { approval_code: code.trim(), ...body }, idem.current);
      finish(r, "card", null);
    });
  const startTerminal = () =>
    pay("terminal", async () => {
      const r = await device.post<PayResult>(`/v1/orders/${order.id}/payments/card-terminal`, body, idem.current);
      setPending(r.payment);
      setStep("card");
    });
  const startQr = () =>
    pay("qr", async () => {
      const r = await device.post<PayResult>(`/v1/orders/${order.id}/payments/lankaqr`, body);
      setPending(r.payment);
      setStep("qr");
    });

  const blocked = typeof hold === "object" ? hold.other : null;
  const footer = blocked ? (
    <Button size="xl" className="w-full" onClick={onClose}>
      Close
    </Button>
  ) : check ? undefined : step === "cash" ? (
    <Button variant="ok" size="xl" className="w-full" disabled={!ready || t < amount} onClick={payCash}>
      {busy ? <Loader2 size={20} className="animate-spin" /> : null} Cash received
    </Button>
  ) : step === "manual" ? (
    <Button variant="ok" size="xl" className="w-full" disabled={!ready || !code.trim()} onClick={payManual}>
      {busy ? <Loader2 size={20} className="animate-spin" /> : null} Card paid · {money(amount)}
    </Button>
  ) : undefined;

  return (
    <Modal open onClose={onClose} title={order.table_ref ? `Table ${order.table_ref}` : order.token} footer={footer}>
      {!online ? <OfflineBar className="-mx-6 -mt-2 mb-4" /> : null}
      {blocked ? (
        <div className="grid justify-items-center gap-3 py-6 text-center" data-being-paid>
          <span className="grid h-16 w-16 place-items-center rounded-full bg-warn-soft text-warn">
            <UserRound size={28} />
          </span>
          <p className="text-xl font-bold leading-snug">{blocked}</p>
          <p className="max-w-xs text-muted">Only one person takes a payment at a time. This opens up when they finish or close it.</p>
        </div>
      ) : check ? (
        <CheckState check={check} onRetry={() => void attempt.current?.run()} onCheck={() => void verify()} onOther={() => (setCheck(null), (attempt.current = null), back())} online={online} />
      ) : (
        <>
          {step === "choose" || step === "cash" || step === "manual" ? (
            <div className="mb-4 flex flex-col items-center gap-3 border-b border-line pb-5 text-center">
              <div>
                <div className="text-sm font-medium text-muted">{share && share < due ? `Paying now · of ${money(due)}` : "To pay"}</div>
                <div className="num text-[44px] font-bold leading-tight tracking-tight">{money(amount)}</div>
              </div>
              {split && step === "choose" ? (
                <Segmented
                  value={parts}
                  onChange={(n) => (setShare(n === "1" ? null : Math.ceil(due / +n)), (idem.current = newKey()))}
                  options={[
                    ["1", "Full"],
                    ["2", "Split 2"],
                    ["3", "Split 3"],
                    ["4", "Split 4"],
                  ]}
                />
              ) : null}
            </div>
          ) : null}

          <AnimatePresence mode="wait" initial={false}>
            <motion.div key={step} initial={{ opacity: 0, x: 12 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -12 }} transition={ease}>
              {step === "choose" ? (
                <div className="-mx-2 flex flex-col divide-y divide-line">
                  {me.payments.cash ? <PayWay icon={Banknote} title="Cash" sub="Change is worked out for you" disabled={!ready} onClick={() => (setTendered((amount / 100).toFixed(2)), setStep("cash"))} /> : null}
                  {me.payments.card ? <PayWay icon={CreditCard} title={me.payments.card === "softpos" ? "Card: tap on this device" : "Card reader"} sub="Tap, insert or swipe" disabled={!ready} onClick={startTerminal} /> : null}
                  {me.payments.lankaqr ? <PayWay icon={QrCode} title="QR payment" sub="The guest scans with a banking app" disabled={!ready} onClick={startQr} /> : null}
                  <PayWay icon={ReceiptText} title="Bank card machine" sub="Paid on the bank's machine: type its approval code" disabled={!ready} onClick={() => setStep("manual")} />
                </div>
              ) : null}

              {step === "cash" ? (
                <div className="grid gap-4">
                  <label className="block">
                    <span className="mb-1.5 block text-sm font-medium text-muted">Received from the guest</span>
                    <input aria-label="Cash received" inputMode="decimal" value={tendered} onChange={(e) => setTendered(e.target.value)} onFocus={(e) => e.target.select()} className={`${inputCls} num h-16! text-right text-3xl! font-bold`} />
                  </label>
                  <div className="flex flex-wrap gap-2 [&>button]:min-w-[5.5rem] [&>button]:flex-1">
                    <Button variant="soft" className="rounded-full" onClick={() => setTendered((amount / 100).toFixed(2))}>
                      Exact
                    </Button>
                    {NOTES.filter((n) => n >= amount)
                      .slice(0, 3)
                      .map((n) => (
                        <Button key={n} variant="soft" className="num rounded-full px-2" onClick={() => setTendered((n / 100).toFixed(2))}>
                          {note(n)}
                        </Button>
                      ))}
                  </div>
                  <div className="flex items-center justify-between rounded-xl bg-ok-soft px-4 py-3.5">
                    <span className="font-semibold text-ok">Change to give</span>
                    <motion.span key={t} initial={{ opacity: 0.4, y: -4 }} animate={{ opacity: 1, y: 0 }} transition={ease} className={`num text-2xl font-bold ${t >= amount ? "text-ok" : "text-muted"}`}>
                      {t >= amount ? money(t - amount) : "Not enough"}
                    </motion.span>
                  </div>
                  <BackLink onClick={back}>Other way to pay</BackLink>
                </div>
              ) : null}

              {step === "card" ? (
                <Waiting icon={CreditCard} text={me.payments.card === "softpos" ? "The guest holds the card to the back of this device…" : "The guest taps or inserts the card on the reader…"} amount={pending?.amount ?? amount}>
                  {pending?.gateway_ref ? <DevButtons kind="mock-terminal" ref_={pending.gateway_ref} /> : null}
                  <Button onClick={cancelPending}>Cancel</Button>
                </Waiting>
              ) : null}

              {step === "qr" && pending ? (
                <Waiting
                  icon={null}
                  text="The guest scans with a banking app. This closes by itself when paid."
                  amount={pending.amount}
                  top={
                    <div className="rounded-2xl bg-white p-4 ring-1 ring-line">
                      <QRCodeSVG value={pending.qr_payload ?? ""} size={200} />
                    </div>
                  }
                >
                  {pending.gateway_ref ? <DevButtons kind="mock-gateway" ref_={pending.gateway_ref} /> : null}
                  <Button onClick={cancelPending}>Cancel</Button>
                </Waiting>
              ) : null}

              {step === "manual" ? (
                <div className="grid gap-4">
                  <label className="block">
                    <span className="mb-1.5 block text-sm font-medium text-muted">Approval code on the bank machine's slip</span>
                    <input aria-label="Approval code" value={code} onChange={(e) => setCode(e.target.value)} autoFocus className={`${inputCls} h-14! text-xl! font-bold tracking-wider`} />
                  </label>
                  <BackLink onClick={back}>Other way to pay</BackLink>
                </div>
              ) : null}
            </motion.div>
          </AnimatePresence>
        </>
      )}
    </Modal>
  );
}

/** After a network error: checking, not paid (try again with the same key), or can't check yet. */
function CheckState({ check, online, onRetry, onCheck, onOther }: { check: "checking" | "unpaid" | "unreachable"; online: boolean; onRetry: () => void; onCheck: () => void; onOther: () => void }) {
  return (
    <div className="grid justify-items-center gap-3 py-6 text-center" data-check={check}>
      {check === "checking" ? (
        <>
          <Loader2 size={40} className="animate-spin text-muted" />
          <p className="text-xl font-bold">Checking the payment…</p>
          <p className="max-w-xs text-muted">The connection dropped. Asking the server whether it went through.</p>
        </>
      ) : check === "unpaid" ? (
        <>
          <p className="text-xl font-bold">Not paid yet</p>
          <p className="max-w-xs text-muted">The server has no payment for this. It is safe to try again.</p>
          <div className="mt-2 flex flex-wrap justify-center gap-2">
            <Button variant="primary" size="lg" disabled={!online} onClick={onRetry}>
              Try again
            </Button>
            <Button size="lg" onClick={onOther}>
              Other way
            </Button>
          </div>
        </>
      ) : (
        <>
          <WifiOff size={36} className="text-bad" />
          <p className="text-xl font-bold">Can't check the payment yet</p>
          <p className="max-w-xs text-muted">Don't take the money again. This checks by itself when the connection is back.</p>
          <Button size="lg" className="mt-2" onClick={onCheck}>
            Check again
          </Button>
        </>
      )}
    </div>
  );
}

/** "Paid": the change in big numbers and where the receipt is printing. Main button: Done (or the next bill). */
export function PaidSheet({ receipt, onClose, onNext }: { receipt: Receipt; onClose: () => void; onNext?: () => void }) {
  const left = receipt.order.total - receipt.order.paid_total;
  const next = left > 0 && onNext;
  useEffect(() => {
    if (next) return;
    const t = setTimeout(onClose, 60_000);
    return () => clearTimeout(t);
  }, [receipt]);
  const where = receipt.printedAt;
  return (
    <Modal
      open
      onClose={onClose}
      title={receipt.order.table_ref ? `Table ${receipt.order.table_ref}` : receipt.order.token}
      footer={
        next ? (
          <Button variant="primary" size="xl" className="w-full" onClick={onNext}>
            Next payment · {money(left)}
          </Button>
        ) : (
          <Button variant="primary" size="xl" className="w-full" onClick={onClose}>
            Done
          </Button>
        )
      }
    >
      <div className="grid justify-items-center gap-2 py-2 text-center" data-paid={receipt.order.token}>
        <motion.span initial={{ scale: 0.6, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} transition={ease} className="grid h-14 w-14 place-items-center rounded-full bg-ok text-white">
          <Check size={30} strokeWidth={3} />
        </motion.span>
        <p className="text-lg font-bold">
          Paid <span className="num">{money(receipt.amount)}</span>
        </p>
        {receipt.method === "cash" && receipt.change !== null ? (
          receipt.change > 0 ? (
            <div className="mt-2 w-full rounded-2xl bg-ok-soft px-4 py-4 text-ok">
              <div className="text-base font-semibold">Give</div>
              <div className="num text-5xl font-black tracking-tight">{money(receipt.change)}</div>
              <div className="text-base font-semibold">change</div>
            </div>
          ) : (
            <p className="text-muted">No change to give</p>
          )
        ) : null}
        {where ? <p className="mt-2 text-[15px] text-muted">{where.length ? `Receipt printing at ${where.join(" and ")}` : "No receipt printer is set up"}</p> : null}
        {left > 0 ? (
          <p className="text-[15px] font-semibold">
            <span className="num">{money(left)}</span> still to pay
          </p>
        ) : null}
      </div>
    </Modal>
  );
}

function BackLink({ children, onClick }: { children: React.ReactNode; onClick: () => void }) {
  return (
    <Button variant="ghost" size="sm" className="justify-self-center" onClick={onClick}>
      <ChevronLeft size={16} /> {children}
    </Button>
  );
}

function PayWay({ icon: Icon, title, sub, onClick, disabled = false }: { icon: LucideIcon; title: string; sub: string; onClick: () => void; disabled?: boolean }) {
  return (
    <button disabled={disabled} onClick={onClick} className="group flex min-h-16 items-center gap-4 rounded-xl px-2 py-3 text-left transition hover:bg-ink/[.03] active:scale-[.99] disabled:opacity-40">
      <span className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-ink/[.06] text-ink">
        <Icon size={20} strokeWidth={2} />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block text-base font-semibold">{title}</span>
        <span className="block text-sm leading-snug text-muted">{sub}</span>
      </span>
      <ChevronRight size={20} className="shrink-0 text-muted transition group-hover:translate-x-0.5" />
    </button>
  );
}

function Waiting({ icon: Icon, text, amount, top, children }: { icon: LucideIcon | null; text: string; amount: number; top?: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="grid justify-items-center gap-4 py-2 text-center">
      {top ??
        (Icon ? (
          <div className="pulse-ring grid h-24 w-24 place-items-center rounded-full bg-ink text-canvas">
            <Icon size={40} strokeWidth={1.75} />
          </div>
        ) : null)}
      <p className="num text-3xl font-bold">{money(amount)}</p>
      <p className="max-w-xs text-muted">{text}</p>
      <div className="flex flex-wrap justify-center gap-2">{children}</div>
    </div>
  );
}

/** Test environments only: pretend the bank answered. */
export function DevButtons({ kind, ref_ }: { kind: "mock-terminal" | "mock-gateway"; ref_: string }) {
  const hit = (outcome: string) => fetch(`${net.base()}/v1/dev/${kind}/${encodeURIComponent(ref_)}/${outcome}`, { method: "POST" });
  return (
    <div className="flex gap-2">
      <Button size="sm" variant="soft" onClick={() => hit("succeeded")}>
        Simulate {kind === "mock-terminal" ? "tap" : "payment"} (test)
      </Button>
      <Button size="sm" variant="ghost" onClick={() => hit("failed")}>
        Simulate decline
      </Button>
    </div>
  );
}
