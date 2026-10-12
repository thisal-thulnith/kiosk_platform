// "How am I doing?": the sales number against the period before, a few small numbers, sales by hour,
// the best sellers, what is happening right now, and how the service went.
import { ArrowDownRight, ArrowUpRight, BellRing, ChefHat, MonitorSmartphone, ReceiptText } from "lucide-react";
import { useState, type ReactNode } from "react";
import { money } from "../../lib/format";
import { Dish } from "../../ui/food";
import { Card, Segmented, SectionTitle, Skeleton, Status } from "../../ui/kit";
import { Bars, CHANNEL, Columns, CountUp, Kpi, KpiSkeleton, KpiStrip, METHOD, Rows, presets, rs, previous, rangeText, secs, toneText } from "./bits";
import { GuestVoice, RatingValue, useFeedback } from "./feedback";
import { useReport, type Ctx } from "./Owner";

export type Sales = {
  orders: number;
  gross_total: number;
  average_bill: number;
  by_channel: Record<string, { orders: number; total: number }>;
  by_hour: Record<string, { orders: number; total: number }>;
  payments: Record<string, { charges: number; refunds: number }>;
  top_items: { name: string; quantity: number; revenue: number }[];
  tax_by_code: Record<string, number>;
  avg_prep_seconds: number | null;
  status_counts: Record<string, number>;
};
type Ops = {
  orders: number;
  late: { count: number; of: number; percent: number };
  voids: { count: number; value: number; reasons: Record<string, number> };
  refunds: { count: number; value: number };
  remakes: { count: number; by_reason: Record<string, number> };
  completion_by_channel: Record<string, { started: number; paid: number; cancelled_or_expired: number }>;
  guest_calls: { count: number; answered: number; avg_answer_seconds: number | null };
  upsell: { items: number; revenue: number };
  combos_sold: number;
};
type Load = { level: string; open_tickets: number; score_minutes: number };
type Dev = { is_active: boolean; paired: boolean; connected: boolean };
const REASON: Record<string, string> = { burnt: "Burnt", dropped: "Dropped", wrong_item: "Wrong item", guest_complaint: "Guest complaint", quality: "Quality", other: "Other" };
const LEVEL: Record<string, [string, "ok" | "warn" | "bad"]> = { normal: ["Calm", "ok"], busy: ["Busy", "warn"], overloaded: ["Very busy", "bad"] };
const openOf = (s: Sales) => (s.status_counts.placed ?? 0) + (s.status_counts.in_kitchen ?? 0) + (s.status_counts.ready ?? 0);

export function TodayPage({ ctx, open }: { ctx: Ctx; open: (where: string) => void }) {
  const tz = ctx.admin.venue?.timezone || "Asia/Colombo";
  const today = presets(tz).today;
  const isToday = ctx.range.from === today.from && ctx.range.to === today.to;
  const prev = previous(ctx.range);
  const [s] = useReport<Sales>(ctx, "/reports/sales");
  const [before] = useReport<Sales>(ctx, "/reports/sales", prev);
  const [now] = useReport<Sales>(ctx, isToday ? null : "/reports/sales", today);
  const [ops] = useReport<Ops>(ctx, "/reports/operations");
  const [load] = useReport<Load>(ctx, "/reports/kitchen-load", false);
  const [devs] = useReport<Dev[]>(ctx, "/devices", false);
  const [fb] = useFeedback(ctx);

  if (!s)
    return (
      <div className="flex flex-col gap-4" aria-busy="true">
        <KpiSkeleton n={6} />
        <div className="grid gap-4 lg:grid-cols-3">
          <Skeleton className="h-[380px] rounded-2xl lg:col-span-2" />
          <Skeleton className="h-[380px] rounded-2xl" />
        </div>
        <div className="grid gap-4 lg:grid-cols-2 2xl:grid-cols-4">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-72 rounded-2xl" />
          ))}
        </div>
      </div>
    );

  const live = devs?.filter((d) => d.is_active) ?? [];
  const online = live.filter((d) => d.connected).length;
  const lvl = load ? (LEVEL[load.level] ?? [load.level, "warn"]) : null;
  const late = ops?.late.percent ?? null;
  const was = before?.gross_total ?? null;
  const change = was === null ? null : was > 0 ? Math.round(((s.gross_total - was) / was) * 100) : null;

  return (
    <div className="flex flex-col gap-4">
      <KpiStrip cols={6}>
        <Kpi
          label="Sales"
          value={<CountUp value={s.gross_total} format={rs} />}
          hint={
            <>
              {change !== null ? (
                <span className={`inline-flex items-center font-semibold ${change >= 0 ? "text-ok" : "text-bad"}`}>
                  {change >= 0 ? <ArrowUpRight size={14} /> : <ArrowDownRight size={14} />}
                  {change >= 0 ? "+" : ""}
                  {change}%
                </span>
              ) : null}
              <span className="truncate">{was === null ? "comparing…" : `vs ${prev.label}`}</span>
            </>
          }
        />
        <Kpi label="Paid orders" value={<CountUp value={s.orders} />} hint={before ? `${before.orders} ${prev.label}` : undefined} />
        <Kpi label="Average bill" value={<CountUp value={s.average_bill} format={rs} />} hint={before ? `${money(before.average_bill)} ${prev.label}` : undefined} />
        <Kpi label="Kitchen time" value={secs(s.avg_prep_seconds)} hint="average per order" />
        <Kpi label="Late orders" value={late === null ? "—" : `${late}%`} hint={ops ? `${ops.late.count} of ${ops.late.of}` : undefined} tone={late === null ? undefined : late > 15 ? "bad" : late > 5 ? "warn" : undefined} />
        {fb ? (
          <Kpi label="Guests' rating" value={<RatingValue value={fb.average} />} hint={fb.count ? `${fb.count} ${fb.count === 1 ? "rating" : "ratings"} · ${fb.low} low` : "no ratings yet"} tone={fb.average !== null && fb.average < 3.5 ? "bad" : undefined} />
        ) : (
          <Kpi label="Guest calls" value={ops ? `${ops.guest_calls.answered} / ${ops.guest_calls.count}` : "—"} hint={ops ? `answered · avg ${secs(ops.guest_calls.avg_answer_seconds)}` : undefined} />
        )}
      </KpiStrip>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="flex min-w-0 flex-col lg:col-span-2">
          <SectionTitle
            title="Sales by hour"
            hint={rangeText(ctx.range)}
            right={
              was !== null ? (
                <span className="hidden text-right text-sm sm:block">
                  <span className="block text-muted">{prev.label.charAt(0).toUpperCase() + prev.label.slice(1)}</span>
                  <span className="num block font-semibold">{money(was)}</span>
                </span>
              ) : null
            }
          />
          <div className="mt-auto">
            <Columns rows={Object.entries(s.by_hour).map(([h, v]) => [h, v.total])} format={money} />
          </div>
        </Card>
        <Card className="flex flex-col">
          <div className="mb-1 flex items-center justify-between">
            <h2 className="text-lg font-bold tracking-[-0.01em]">Right now</h2>
            <Status tone="ok" pulse>
              Live
            </Status>
          </div>
          <div className="flex flex-1 flex-col justify-around">
            <NowRow icon={<ReceiptText size={20} />} label="Open orders" value={isToday ? openOf(s) : now ? openOf(now) : "—"} hint="placed, cooking or ready" />
            <NowRow icon={<ChefHat size={20} />} label="Kitchen" value={lvl ? <span className={toneText(lvl[1])}>{lvl[0]}</span> : "—"} hint={load ? `${load.open_tickets} tickets · about ${Math.round(load.score_minutes)} min of work` : undefined} />
            <NowRow icon={<BellRing size={20} />} label="Guest calls" value={ops ? `${ops.guest_calls.answered} / ${ops.guest_calls.count}` : "—"} hint={ops ? `answered · avg ${secs(ops.guest_calls.avg_answer_seconds)}` : undefined} />
            <NowRow
              icon={<MonitorSmartphone size={20} />}
              label="Screens online"
              value={devs ? <span className={live.some((d) => d.paired && !d.connected) ? "text-warn" : ""}>{`${online} / ${live.length}`}</span> : "—"}
              hint={devs ? (online === live.length ? "all connected" : `${live.length - online} offline`) : undefined}
            />
          </div>
        </Card>
      </div>

      <div className="grid items-start gap-4 md:grid-cols-2 2xl:grid-cols-4">
        <Card>
          <SectionTitle title="Top items" hint="by number sold" />
          <TopItems items={s.top_items} />
        </Card>
        <Breakdown s={s} />
        <Service ops={ops} />
        {fb ? <GuestVoice f={fb} onAll={() => open("staff/feedback")} /> : null}
      </div>
    </div>
  );
}

function NowRow({ icon, label, value, hint }: { icon: ReactNode; label: string; value: ReactNode; hint?: ReactNode }) {
  return (
    <div className="flex items-center gap-3 border-t border-line py-3 first:border-0">
      <span className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-canvas text-ink/70">{icon}</span>
      <span className="min-w-0 flex-1">
        <span className="block text-[15px] font-semibold">{label}</span>
        {hint ? <span className="block truncate text-[13px] text-muted">{hint}</span> : null}
      </span>
      <span className="num text-xl font-bold tracking-tight">{value}</span>
    </div>
  );
}

function TopItems({ items }: { items: Sales["top_items"] }) {
  if (!items.length) return <p className="py-10 text-center text-muted">No sales yet</p>;
  const max = Math.max(1, ...items.map((x) => x.quantity));
  return (
    <div className="flex flex-col">
      {items.slice(0, 6).map((x) => (
        <div key={x.name} className="flex items-center gap-3 border-t border-line py-2.5 first:border-0 first:pt-0">
          <Dish name={x.name} size={44} />
          <span className="min-w-0 flex-1">
            <span className="flex items-baseline justify-between gap-2">
              <span className="truncate font-semibold">{x.name}</span>
              <span className="num shrink-0 text-sm font-semibold">{money(x.revenue)}</span>
            </span>
            <span className="mt-1.5 flex items-center gap-2">
              <span className="h-1 flex-1 overflow-hidden rounded-full bg-ink/[.06]">
                <span className="block h-full rounded-full bg-accent transition-[width] duration-700" style={{ width: `${(100 * x.quantity) / max}%` }} />
              </span>
              <span className="num w-14 shrink-0 text-right text-xs text-muted">{x.quantity} sold</span>
            </span>
          </span>
        </div>
      ))}
    </div>
  );
}

/** Where orders came from, how guests paid, and the service charge and taxes — one card, three views. */
function Breakdown({ s }: { s: Sales }) {
  const [view, setView] = useState<"channel" | "paid" | "tax">("channel");
  return (
    <Card>
      <SectionTitle title="Breakdown" />
      <Segmented
        value={view}
        onChange={setView}
        className="mb-4 [&>button]:h-9 [&>button]:text-sm"
        options={[
          ["channel", "Where from"],
          ["paid", "How paid"],
          ["tax", "Taxes"],
        ]}
      />
      {view === "channel" ? (
        <Bars rows={Object.entries(s.by_channel).map(([k, v]) => [`${CHANNEL[k] ?? k} · ${v.orders}`, v.total])} format={money} />
      ) : view === "paid" ? (
        Object.keys(s.payments).length ? (
          <Rows rows={Object.entries(s.payments).map(([k, v]) => [METHOD[k] ?? k, v.refunds ? `${money(v.charges - v.refunds)} (−${money(v.refunds)} refunds)` : money(v.charges)])} />
        ) : (
          <p className="py-6 text-center text-muted">No payments yet</p>
        )
      ) : Object.keys(s.tax_by_code).length ? (
        <Rows rows={Object.entries(s.tax_by_code).map(([k, v]) => [k, money(v)])} />
      ) : (
        <p className="py-6 text-center text-muted">No taxes or charges yet</p>
      )}
    </Card>
  );
}

function Service({ ops }: { ops: Ops | null }) {
  const [more, setMore] = useState(false);
  if (!ops) return <Skeleton className="h-72 rounded-2xl" />;
  const dropped = Object.values(ops.completion_by_channel).reduce((n, v) => n + v.cancelled_or_expired, 0);
  const started = Object.values(ops.completion_by_channel).reduce((n, v) => n + v.started, 0);
  return (
    <Card>
      <SectionTitle
        title="Kitchen & service"
        right={
          <button onClick={() => setMore((m) => !m)} className="text-sm font-semibold text-accent hover:underline">
            {more ? "Less" : "More"}
          </button>
        }
      />
      <Rows
        rows={[
          ["Guest calls answered", `${ops.guest_calls.answered} / ${ops.guest_calls.count} · avg ${secs(ops.guest_calls.avg_answer_seconds)}`],
          ["Orders dropped (not paid)", `${dropped} of ${started}`],
          ["Voided · refunded", `${ops.voids.count} (${money(ops.voids.value)}) · ${ops.refunds.count} (${money(ops.refunds.value)})`],
          ["Meals sold · from suggestions", `${ops.combos_sold} · ${ops.upsell.items} (${money(ops.upsell.revenue)})`],
        ]}
      />
      {more ? (
        <div className="mt-4 flex flex-col gap-4">
          <div>
            <div className="mb-1 text-sm font-semibold">Finished or dropped, by channel</div>
            <Rows rows={Object.entries(ops.completion_by_channel).map(([c, v]) => [CHANNEL[c] ?? c, `${v.paid} paid · ${v.cancelled_or_expired} dropped · ${v.started} started`])} />
          </div>
          {ops.remakes.count ? (
            <div>
              <div className="mb-1 text-sm font-semibold">Remakes</div>
              <Rows rows={Object.entries(ops.remakes.by_reason).map(([r, n]) => [REASON[r] ?? r, n])} />
            </div>
          ) : null}
          {Object.keys(ops.voids.reasons).length ? (
            <div>
              <div className="mb-1 text-sm font-semibold">Void reasons</div>
              <Rows rows={Object.entries(ops.voids.reasons).map(([r, n]) => [r || "—", n])} />
            </div>
          ) : null}
        </div>
      ) : null}
    </Card>
  );
}
