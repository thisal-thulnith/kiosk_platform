// Table states: one word and one dot each, the same on the POS and the waiter app. Calm, flat tiles:
// white with a hairline, the table's name big, its state as a dot + word (a calling table's dot pulses
// and its word is red: the one thing that needs someone right now).
import { AnimatePresence, motion } from "motion/react";
import { Check, ConciergeBell, MessageSquareText, Sparkles, Star } from "lucide-react";
import type { Device } from "../lib/device";
import { ago, money } from "../lib/format";
import type { Feedback, ServiceRequest, TableInfo, TableState } from "../lib/types";
import { byPlace, CallBanner } from "./calls";
import { Button, ease } from "./kit";

export const TABLE_STATE: Record<TableState, { label: string; cls: string; dot: string; text: string }> = {
  calling: { label: "Calling", cls: "bg-surface shadow-soft", dot: "bg-bad", text: "text-bad" },
  bill: { label: "Wants the bill", cls: "bg-surface shadow-soft", dot: "bg-warn", text: "text-warn" },
  ready: { label: "Food ready", cls: "bg-surface shadow-soft", dot: "bg-ok", text: "text-ok" },
  waiting_payment: { label: "Waiting payment", cls: "bg-surface shadow-soft", dot: "bg-warn", text: "text-warn" },
  cooking: { label: "Cooking", cls: "bg-surface shadow-soft", dot: "bg-info", text: "text-info" },
  eating: { label: "Eating", cls: "bg-surface shadow-soft", dot: "bg-ink", text: "text-ink" },
  cleaning: { label: "Needs cleaning", cls: "bg-surface shadow-soft", dot: "bg-warn", text: "text-warn" },
  free: { label: "Free", cls: "bg-surface shadow-soft", dot: "bg-ink/20", text: "text-muted" },
  closed: { label: "Closed", cls: "bg-transparent border border-dashed border-ink/15", dot: "bg-ink/15", text: "text-muted" },
};

/** The small dot + word of a table's state. */
export function TableDot({ state, className = "" }: { state: TableState; className?: string }) {
  const s = TABLE_STATE[state] ?? TABLE_STATE.free;
  const live = state === "calling" || state === "ready";
  return (
    <span className={`inline-flex items-center gap-1.5 text-[13px] ${state === "calling" ? "font-semibold text-bad" : "font-medium text-muted"} ${className}`}>
      <span className={`relative h-2 w-2 shrink-0 rounded-full ${s.dot}`}>{live ? <span className={`absolute inset-0 animate-ping rounded-full ${s.dot} opacity-60`} /> : null}</span>
      {s.label}
    </span>
  );
}

/** The quiet third line of a tile: who is paying, who is coming, what is owed, or how long they're there. */
function tileNote(t: TableInfo, holder?: string | null): React.ReactNode {
  if (holder) return <span className="font-semibold text-warn">Being paid by {holder}</span>;
  const coming = t.requests.find((r) => r.coming)?.coming;
  if (coming) return <span className="font-semibold text-ok">{coming} is coming</span>;
  if (t.to_serve?.length) return <span className="font-semibold text-ink">{t.to_serve.length === 1 ? `Take out ${t.to_serve[0].token}` : `${t.to_serve.length} to take out`}</span>;
  if (t.open_total) return <span className="num font-semibold text-ink">{money(t.open_total)}</span>;
  if (t.state === "eating" && t.occupied_since) return <span>Seated {ago(t.occupied_since).replace(" ago", "")}</span>;
  return null;
}

export function TableGrid({ tables, onOpen, size = "md", holder }: { tables: TableInfo[]; onOpen: (ref: string) => void; size?: "md" | "lg"; holder?: (ref: string) => string | null }) {
  return (
    <div className={`grid gap-2.5 ${size === "lg" ? "grid-cols-[repeat(auto-fill,minmax(150px,1fr))]" : "grid-cols-[repeat(auto-fill,minmax(112px,1fr))]"}`}>
      {tables.map((t) => {
        const s = TABLE_STATE[t.state] ?? TABLE_STATE.free;
        return (
          <button
            key={t.table_ref}
            data-table={t.table_ref}
            onClick={() => onOpen(t.table_ref)}
            className={`flex flex-col items-start gap-1 rounded-2xl p-3.5 text-left transition duration-150 hover:brightness-[.98] active:scale-[.98] ${size === "lg" ? "min-h-26" : "min-h-23"} ${s.cls}`}
          >
            <span className={`font-bold leading-none tracking-tight ${size === "lg" ? "text-[26px]" : "text-[22px]"} ${t.state === "closed" ? "text-muted" : ""}`}>{t.table_ref}</span>
            <TableDot state={t.state} className="mt-1" />
            <span className="mt-auto min-h-4 w-full truncate text-xs text-muted">{tileNote(t, holder?.(t.table_ref))}</span>
          </button>
        );
      })}
    </div>
  );
}

export function StateLegend() {
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1.5">
      {(["calling", "bill", "ready", "cooking", "eating", "cleaning", "free"] as TableState[]).map((k) => (
        <TableDot key={k} state={k} />
      ))}
    </div>
  );
}

// ------------------------------------------------------------------ guest feedback

export const FEEDBACK_TAG: Record<string, string> = { food: "Good food", service: "Great service", speed: "Fast", value: "Good value", clean: "Clean", slow: "Took long", cold: "Food was cold", wrong_order: "Wrong order" };

/** Five small stars, the given number filled (black; red for a low rating). */
export function Stars({ rating, low = false, size = 14 }: { rating: number; low?: boolean; size?: number }) {
  return (
    <span className="inline-flex items-center gap-0.5" aria-label={`${rating} of 5`}>
      {[1, 2, 3, 4, 5].map((n) => (
        <Star key={n} size={size} strokeWidth={2} className={n <= rating ? (low ? "fill-bad text-bad" : "fill-ink text-ink") : "fill-ink/10 text-transparent"} />
      ))}
    </span>
  );
}

/** What the guests said, in words: their comment, or the tags they picked. */
export const feedbackWords = (f: Feedback): string => f.comment?.trim() || f.tags.map((t) => FEEDBACK_TAG[t] ?? t).join(", ") || (f.low ? "Not happy" : "No comment");

/** "ready in ~6 min" from the kitchen's promised time (or nothing when the kitchen gave none). */
export function readyIn(promised: string | null | undefined): string | null {
  if (!promised) return null;
  const m = Math.round((new Date(promised).getTime() - Date.now()) / 60000);
  return m <= 0 ? "ready any minute" : `ready in ~${m} min`;
}

// ------------------------------------------------------------------ the task list (what needs someone)

type Act = (fn: () => Promise<unknown>, ok?: string) => Promise<void>;

/** One task: a round icon, what to do, a quiet line, one button. Tapping the text opens the table. */
export function TaskRow({ icon, tone = "muted", title, sub, action, onOpen, ...p }: { icon: React.ReactNode; tone?: "bad" | "ok" | "warn" | "muted" | "info"; title: React.ReactNode; sub?: React.ReactNode; action?: React.ReactNode; onOpen?: () => void } & Omit<React.HTMLAttributes<HTMLDivElement>, "title">) {
  const tint = { bad: "bg-bad-soft text-bad", ok: "bg-ok-soft text-ok", warn: "bg-warn-soft text-warn", info: "bg-info-soft text-info", muted: "bg-ink/[.06] text-ink/60" }[tone];
  const body = (
    <>
      <span className={`grid h-10 w-10 shrink-0 place-items-center rounded-full ${tint}`} aria-hidden>
        {icon}
      </span>
      <span className="min-w-0 flex-1">
        <span className="line-clamp-2 block font-semibold leading-snug">{title}</span>
        {sub ? <span className="block truncate text-sm text-muted">{sub}</span> : null}
      </span>
    </>
  );
  return (
    <motion.div layout initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, x: -24 }} transition={ease} className="flex flex-wrap items-center gap-x-3 gap-y-2 px-3 py-3" {...(p as object)}>
      {onOpen ? (
        <button onClick={onOpen} className="flex min-w-[10rem] flex-1 items-center gap-3 text-left">
          {body}
        </button>
      ) : (
        <span className="flex min-w-[10rem] flex-1 items-center gap-3">{body}</span>
      )}
      {action ? <div className="ml-auto flex shrink-0 items-center gap-1">{action}</div> : null}
    </motion.div>
  );
}

/** Everything that needs someone now, most urgent first: unhappy guests, calls, food to take to a
 *  table, tables to clean, then other new feedback. Used by the waiter's home and the POS. */
export function VisitTasks({ device, tables, calls, feedback, pickWaiter, act, onChanged, onOpen, onBill, onPrint, holder, moneyOff = false, foodNote, before, empty, className = "" }: { foodNote?: (orderId: string) => string | undefined; className?: string; device: Device; tables: TableInfo[]; calls: ServiceRequest[]; feedback: Feedback[]; pickWaiter: boolean; act: Act; onChanged: () => void; onOpen?: (ref: string) => void; onBill?: (ref: string) => void; onPrint?: (ref: string) => Promise<unknown>; holder?: (ref: string) => string | null; moneyOff?: boolean; before?: React.ReactNode[]; empty?: React.ReactNode }) {
  const unseen = feedback.filter((f) => !f.seen);
  const low = unseen.filter((f) => f.low);
  const good = unseen.filter((f) => !f.low);
  const food = tables.flatMap((t) => (t.to_serve ?? []).map((o) => ({ ...o, table: t.table_ref })));
  const clean = tables.filter((t) => t.needs_cleaning && t.state === "cleaning");
  const groups = byPlace(calls);
  const seen = (f: Feedback) => act(() => device.post(`/v1/feedback/${f.id}/seen`), "Marked as seen");
  const fbRow = (f: Feedback) => (
    <TaskRow
      key={`f-${f.id}`}
      data-feedback={f.id}
      icon={<MessageSquareText size={19} />}
      tone={f.low ? "bad" : "muted"}
      title={
        <span className="inline-flex items-center gap-2">
          {f.table_ref ?? "Kiosk"} <Stars rating={f.rating} low={f.low} />
        </span>
      }
      sub={`“${feedbackWords(f)}” · ${ago(f.created_at)}`}
      onOpen={f.table_ref && onOpen ? () => onOpen(f.table_ref!) : undefined}
      action={
        <Button variant={f.low ? "default" : "ghost"} className="min-w-20 rounded-full" onClick={() => seen(f)}>
          Seen
        </Button>
      }
    />
  );
  const count = low.length + groups.length + food.length + clean.length + good.length + (before?.length ?? 0);
  if (!count) return <>{empty}</>;
  return (
    <div className={`flex flex-col divide-y divide-line ${className}`}>
      <AnimatePresence initial={false}>
        {low.map(fbRow)}
        {groups.map((g) => (
          <motion.div key={`c-${g[0].table_ref ?? g[0].where}`} layout initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, x: -24 }} transition={ease}>
            <CallBanner
              device={device}
              calls={g}
              where
              pickWaiter={pickWaiter}
              onChanged={onChanged}
              onOpen={g[0].table_ref && onOpen ? () => onOpen(g[0].table_ref!) : undefined}
              onBill={g[0].table_ref && onBill ? () => onBill(g[0].table_ref!) : undefined}
              onPrint={g[0].table_ref && onPrint ? () => onPrint(g[0].table_ref!) : undefined}
              due={tables.find((t) => t.table_ref === g[0].table_ref)?.open_total}
              holder={g[0].table_ref ? holder?.(g[0].table_ref) : null}
              moneyOff={moneyOff}
            />
          </motion.div>
        ))}
        {food.map((o) => (
          <TaskRow
            key={`s-${o.id}`}
            data-serve={o.token}
            icon={<ConciergeBell size={19} />}
            tone="ok"
            title={`Take food to ${o.table}`}
            sub={foodNote?.(o.id) ? `${o.token} · ${foodNote(o.id)}` : `Order ${o.token} is ready in the kitchen`}
            onOpen={onOpen ? () => onOpen(o.table) : undefined}
            action={
              <Button variant="default" className="min-w-24 rounded-full" onClick={() => act(() => device.post(`/v1/orders/${o.id}/served`), `${o.table} served`)}>
                <Check size={15} /> Served
              </Button>
            }
          />
        ))}
        {clean.map((t) => (
          <TaskRow
            key={`w-${t.table_ref}`}
            data-clean={t.table_ref}
            icon={<Sparkles size={19} />}
            tone="warn"
            title={`Clean ${t.table_ref}`}
            sub="Guests left · reset it for the next guests"
            onOpen={onOpen ? () => onOpen(t.table_ref) : undefined}
            action={
              <Button variant="default" className="min-w-24 rounded-full" onClick={() => act(() => device.post(`/v1/tables/${encodeURIComponent(t.table_ref)}/cleaned`), `${t.table_ref} is free`)}>
                Cleaned
              </Button>
            }
          />
        ))}
        {before}
        {good.map(fbRow)}
      </AnimatePresence>
    </div>
  );
}
