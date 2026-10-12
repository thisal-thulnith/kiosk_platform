// The bill for a table, on screen (to show the guest) and printed (to bring to the table).
import { Printer } from "lucide-react";
import type { Device } from "../lib/device";
import { en, money } from "../lib/format";
import type { Bill } from "../lib/types";
import { Button, Modal, useToast } from "./kit";

function Row({ label, value, muted = false }: { label: string; value: string; muted?: boolean }) {
  return (
    <div className={`flex justify-between gap-4 ${muted ? "text-sm text-muted" : ""}`}>
      <span>{label}</span>
      <span className="num">{value}</span>
    </div>
  );
}

/** "Bill printed at Counter printer": where to pick it up (an empty list: no printer is set up). */
export const printedWhere = (what: string, at: string[] | undefined): string =>
  at === undefined ? `${what} printed` : at.length ? `${what} printed at ${at.join(" and ")}` : `No printer is set up for the ${what.toLowerCase()}`;

/** Print the bill (the waiter's printer, or the counter's) and say where to pick it up. */
export const printBill = (device: Device, tableRef: string, toast: ReturnType<typeof useToast>): Promise<string[] | null> =>
  device.post<Bill>(`/v1/tables/${encodeURIComponent(tableRef)}/bill`).then(
    (b) => (toast(printedWhere("Bill", b.printed_at), b.printed_at && !b.printed_at.length ? "bad" : "ok", 7000), b.printed_at ?? []),
    (x) => (toast((x as Error).message, "bad"), null),
  );

export function BillModal({ device, bill, onClose, onPay, payDisabled = false }: { device: Device; bill: Bill; onClose: () => void; onPay?: () => void; payDisabled?: boolean }) {
  const toast = useToast();
  return (
    <Modal
      open
      onClose={onClose}
      title={`Bill · Table ${bill.table_ref}`}
      footer={
        <div className="flex gap-2">
          <Button size="lg" className={onPay ? "" : "flex-1"} onClick={() => printBill(device, bill.table_ref, toast)}>
            <Printer size={18} /> Print bill
          </Button>
          {onPay ? (
            <Button variant="primary" size="lg" className="flex-1" disabled={payDisabled} onClick={onPay}>
              Take payment
            </Button>
          ) : null}
        </div>
      }
    >
      <div className="flex flex-col gap-1.5">
        {bill.lines.map((l, i) =>
          l.part ? (
            <div key={i} className="-mt-1 pl-5 text-sm text-muted">
              + {en(l.name)}
            </div>
          ) : (
            <Row key={i} label={`${l.quantity} × ${en(l.name)}`} value={money(l.line_total)} />
          ),
        )}
        <div className="my-2 border-t border-line" />
        <Row label="Subtotal" value={money(bill.subtotal)} muted />
        {bill.discount_total ? <Row label="Discount" value={`− ${money(bill.discount_total)}`} muted /> : null}
        <Row label="Service charge and taxes" value={money(bill.tax_total)} muted />
        {bill.paid_total ? <Row label="Already paid" value={`− ${money(bill.paid_total)}`} muted /> : null}
        <div className="mt-3 flex items-baseline justify-between border-t border-line pt-3">
          <span className="text-[17px] font-bold">To pay</span>
          <span className="num text-2xl font-bold">{money(bill.due)}</span>
        </div>
      </div>
    </Modal>
  );
}
