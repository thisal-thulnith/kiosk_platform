// Today's payments: every payment traceable (time, order, how, who, where, reference, invoice).
import { AnimatePresence, motion } from "motion/react";
import { Banknote, CreditCard, QrCode, ReceiptText, Undo2, Wallet, type LucideIcon } from "lucide-react";
import { useEffect, useState } from "react";
import type { Device } from "../lib/device";
import { clock, money } from "../lib/format";
import type { Ledger } from "../lib/types";
import { Badge, Empty, Skeleton, SkeletonList, ease } from "./kit";

const METHOD: Record<string, string> = { cash: "Cash", card: "Card", lankaqr: "QR", pos: "Their POS" };
const METHOD_ICON: Record<string, LucideIcon> = { cash: Banknote, card: CreditCard, lankaqr: QrCode, pos: ReceiptText };

export function LedgerView({ device, mine = false, refreshKey }: { device: Device; mine?: boolean; refreshKey?: number }) {
  const [data, setData] = useState<Ledger | null | undefined>(undefined);
  useEffect(() => {
    device.get<Ledger>(`/v1/payments${mine ? "?mine=true" : ""}`).then(setData).catch(() => setData((d) => d ?? null));
  }, [device, mine, refreshKey]);
  if (data === undefined)
    return (
      <div className="flex flex-col gap-4">
        <Skeleton className="h-24" />
        <SkeletonList rows={4} />
      </div>
    );
  if (data === null) return <Empty icon={<Wallet size={24} />}>Could not load payments right now.</Empty>;
  const methods = Object.entries(data.by_method);
  return (
    <div className="flex flex-col gap-4">
      <div className="border-b border-line pb-4">
        <div className="text-sm font-medium text-muted">Taken today</div>
        <div className="flex flex-wrap items-baseline gap-x-3">
          <span className="num text-[32px] font-bold tracking-tight">{money(data.total)}</span>
          <span className="text-sm text-muted">
            {data.count} payment{data.count === 1 ? "" : "s"}
          </span>
        </div>
        {methods.length ? (
          <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-sm">
            {methods.map(([m, v]) => (
              <span key={m} className="text-muted">
                {METHOD[m] ?? m} <span className="num font-semibold text-ink">{money(v)}</span>
              </span>
            ))}
          </div>
        ) : null}
      </div>
      {data.lines.length ? (
        <div className="-mt-2 flex flex-col">
          <AnimatePresence initial={false}>
            {data.lines.map((x) => (
              <motion.div key={x.id} layout initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }} transition={ease} data-ref={x.ref} className="flex items-center gap-3 border-b border-line py-3 last:border-0">
                <MethodIcon method={x.method} refund={x.kind === "refund"} />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="truncate font-semibold">{mine ? `${x.token} · ${x.table ? `Table ${x.table}` : x.channel}` : (x.collected_by ?? "Not recorded")}</span>
                    <Badge tone={x.kind === "refund" ? "bad" : x.status === "succeeded" ? "muted" : x.status === "pending" ? "warn" : "muted"}>{x.kind === "refund" ? "Refund" : x.status === "succeeded" ? METHOD[x.method] ?? x.method : x.status}</Badge>
                  </div>
                  <div className="truncate text-sm text-muted">
                    <span className="num">{clock(x.at)}</span>
                    {mine ? "" : ` · ${x.token} · ${x.table ? `Table ${x.table}` : x.channel}`}
                    {x.device ? ` · ${x.device}` : ""}
                    {x.outside_ref ? ` · ref ${x.outside_ref}` : ""}
                    {x.invoice ? ` · ${x.invoice}` : ""} · #{x.ref}
                  </div>
                </div>
                <span className={`num shrink-0 font-bold ${x.amount < 0 ? "text-bad" : ""}`}>{money(x.amount)}</span>
              </motion.div>
            ))}
          </AnimatePresence>
        </div>
      ) : (
        <Empty icon={<Wallet size={24} />}>No payments yet today.</Empty>
      )}
    </div>
  );
}

function MethodIcon({ method, refund }: { method: string; refund: boolean }) {
  const Icon = refund ? Undo2 : (METHOD_ICON[method] ?? Wallet);
  return (
    <span className={`grid h-11 w-11 shrink-0 place-items-center rounded-full ${refund ? "bg-bad-soft text-bad" : "bg-ink/[.06] text-ink/70"}`}>
      <Icon size={19} />
    </span>
  );
}
