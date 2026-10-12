// Guest calls (call waiter, wants the bill, kiosk help). "Coming" names who goes: on a waiter's own
// phone it is that waiter; on the POS you pick the waiter. Everyone, and the guest, sees the name.
// One calm row per table: one button, the rest in "⋯". A bill says how the guest will pay.
import { BellRing, Check, ChevronRight, HandHelping, Printer, ReceiptText } from "lucide-react";
import { useEffect, useState } from "react";
import type { Device } from "../lib/device";
import { ago, money } from "../lib/format";
import type { ServiceRequest, Staff } from "../lib/types";
import { Button, Modal, MoreMenu, Skeleton, useToast } from "./kit";
import { Avatar } from "./logo";
import { PAY_WITH } from "./payment";

export const KIND: Record<string, string> = {
  call_waiter: "Calling staff",
  request_bill: "Wants the bill",
  help: "Needs help",
};

const PHRASE: Record<string, string> = {
  call_waiter: "is calling",
  request_bill: "wants the bill",
  help: "needs help",
};
const ICON: Record<string, typeof BellRing> = {
  call_waiter: BellRing,
  request_bill: ReceiptText,
  help: HandHelping,
};

/** One call: "Table T5 · Wants the bill", who is coming, one button. */
export function CallRow({ device, req, pickWaiter, onChanged }: { device: Device; req: ServiceRequest; pickWaiter: boolean; onChanged: () => void }) {
  return <CallBanner device={device} calls={[req]} pickWaiter={pickWaiter} onChanged={onChanged} where />;
}

/** Calls grouped by place (one row per table), oldest first. */
export function byPlace(calls: ServiceRequest[]): ServiceRequest[][] {
  const m = new Map<string, ServiceRequest[]>();
  for (const c of calls.filter((x) => x.status !== "done")) m.set(c.table_ref ?? c.where, [...(m.get(c.table_ref ?? c.where) ?? []), c]);
  return [...m.values()];
}

/** All open calls of one place in one row: "T5 wants the bill · Cash · Rs 2,466", who is coming, one
 *  button. A bill on a waiter's phone: Print bill, then Take payment. On the POS: Coming (pick who). */
export function CallBanner({
  device,
  calls,
  pickWaiter,
  onChanged,
  where = false,
  className = "",
  onOpen,
  onBill,
  onPrint,
  due,
  holder,
  moneyOff = false,
  infoOnly = false,
}: {
  device: Device;
  calls: ServiceRequest[];
  pickWaiter: boolean;
  onChanged: () => void;
  where?: boolean;
  className?: string;
  onOpen?: () => void;
  onBill?: () => void;
  onPrint?: () => Promise<unknown>;
  due?: number;
  holder?: string | null;
  moneyOff?: boolean;
  /** A bill shown where its buttons are elsewhere (a table's page): no button, only "⋯". */
  infoOnly?: boolean;
}) {
  const toast = useToast();
  const [choose, setChoose] = useState(false);
  const [printed, setPrinted] = useState(false);
  const live = calls.filter((c) => c.status !== "done");
  if (!live.length) return null;
  const waiting = live.filter((c) => !c.coming);
  const names = [...new Set(live.map((c) => c.coming?.name).filter(Boolean))] as string[];
  const first = live[0];
  const billReq = live.find((c) => c.kind === "request_bill");
  const Icon = ICON[billReq?.kind ?? first.kind] ?? BellRing;
  const open = waiting.length > 0;

  const ack = async (list: ServiceRequest[], staff_id?: string, quiet = false) => {
    try {
      let name: string | null | undefined;
      for (const c of list) name = (await device.post<ServiceRequest>(`/v1/service-requests/${c.id}/ack`, staff_id ? { staff_id } : {})).coming?.name;
      if (!quiet) toast(`${name ?? "Someone"} is going to ${first.where}`, "ok");
      onChanged();
    } catch (x) {
      toast((x as Error).message, "bad");
    }
  };
  const done = async () => {
    for (const c of live) await device.post(`/v1/service-requests/${c.id}/done`).catch((x) => toast((x as Error).message, "bad"));
    onChanged();
  };
  const coming = () => (pickWaiter ? setChoose(true) : ack(waiting));
  const print = async () => {
    if (!onPrint) return;
    if (open && !pickWaiter) void ack(waiting, undefined, true); // printing it means: I'm taking this bill
    const r = await onPrint();
    if (r !== null) setPrinted(true);
  };

  const place = first.table_ref ?? first.where;
  const bill = !!billReq && !!onBill;
  const Tag = onOpen ? "button" : "span";
  // The most specific thing they want ("wants the bill" says more than "is calling").
  const top = ["request_bill", "help", "call_waiter"].find((k) => live.some((c) => c.kind === k)) ?? first.kind;
  const phrase = PHRASE[top] ?? (KIND[top] ?? top).toLowerCase();
  const how = billReq?.pay_with ? PAY_WITH[billReq.pay_with] : null;
  const head = [where ? `${place} ${phrase}` : (KIND[top] ?? top), how].filter(Boolean).join(" · ");
  const amount = billReq && due ? <span className="num font-semibold text-ink">{money(due)} · </span> : null;
  const btn = "min-w-24 rounded-full";

  // One button: what to do next for this call.
  let action: React.ReactNode;
  if (billReq && infoOnly) action = null;
  else if (bill && !pickWaiter && !printed && onPrint)
    action = (
      <Button variant="default" className={btn} onClick={print}>
        Print bill
      </Button>
    );
  else if (bill && (!open || !pickWaiter))
    action = (
      <Button variant="default" className={btn} disabled={moneyOff || !!holder} onClick={onBill}>
        Take payment
      </Button>
    );
  else if (open)
    action = (
      <Button variant="default" className={btn} onClick={coming}>
        Coming
      </Button>
    );
  else
    action = (
      <Button variant="soft" className={btn} onClick={done}>
        <Check size={15} /> Done
      </Button>
    );

  return (
    <div data-call={first.id} className={`@container flex flex-wrap items-center gap-x-3 gap-y-2 px-3 py-3 ${className}`}>
      {/* A bill says more (how, how much, who): on a narrow row its button goes on the line below. */}
      <Tag {...(onOpen ? { onClick: onOpen } : {})} className={`flex min-w-[10rem] flex-1 items-center gap-3 text-left ${billReq && action ? "@max-[440px]:basis-full" : ""}`}>
        <span className={`grid h-10 w-10 shrink-0 place-items-center rounded-full ${open ? "bg-bad-soft text-bad" : "bg-ink/[.06] text-ink/60"}`} aria-hidden>
          <Icon size={19} strokeWidth={2} />
        </span>
        <span className="min-w-0 flex-1">
          <span className="block font-semibold leading-snug">{head}</span>
          <span className="block truncate text-sm text-muted">
            {amount}
            {holder && billReq ? <span className="font-semibold text-warn">Being paid by {holder}</span> : names.length ? <span className="font-semibold text-ok">{names.join(" & ")} is coming</span> : `Waiting ${ago(first.created_at).replace(" ago", "")}`}
          </span>
        </span>
      </Tag>
      <div className="ml-auto flex shrink-0 items-center gap-1">
        {action}
        <MoreMenu
          items={[
            bill && onPrint && (printed || pickWaiter) ? { label: "Print bill", icon: <Printer size={17} />, onClick: () => void onPrint() } : null,
            bill && !pickWaiter && !printed && !infoOnly ? { label: "Take payment", onClick: onBill! } : null,
            open || bill ? { label: "Done", icon: <Check size={17} />, onClick: done } : null,
            !open && pickWaiter ? { label: "Change who", onClick: () => setChoose(true) } : null,
            !open && !pickWaiter && !bill ? { label: "I'm going", onClick: () => ack(live) } : null,
          ]}
        />
      </div>
      {choose ? <WaiterPicker device={device} onPick={(s) => (setChoose(false), ack(open ? waiting : live, s.id))} onClose={() => setChoose(false)} /> : null}
    </div>
  );
}

export function WaiterPicker({ device, onPick, onClose }: { device: Device; onPick: (s: Staff) => void; onClose: () => void }) {
  const [staff, setStaff] = useState<Staff[] | null>(null);
  useEffect(() => {
    device
      .get<Staff[]>("/v1/staff")
      .then(setStaff)
      .catch(() => setStaff([]));
  }, [device]);
  const order = (s: Staff) => (s.role === "waiter" ? 0 : s.role === "manager" ? 1 : 2);
  return (
    <Modal open onClose={onClose} title="Who is going?">
      <div className="-mx-3 flex flex-col divide-y divide-line">
        {staff === null
          ? Array.from({ length: 4 }, (_, i) => <Skeleton key={i} className="mx-3 my-2 h-12" />)
          : [...staff]
              .sort((a, b) => order(a) - order(b))
              .map((s) => (
                <button key={s.id} onClick={() => onPick(s)} className="flex items-center gap-3 rounded-xl px-3 py-3 text-left transition hover:bg-ink/[.035] active:scale-[.99]">
                  <Avatar size={42} />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-semibold">{s.name}</span>
                    <span className="block text-sm capitalize text-muted">{s.role}</span>
                  </span>
                  <ChevronRight size={18} className="text-muted" />
                </button>
              ))}
      </div>
    </Modal>
  );
}
