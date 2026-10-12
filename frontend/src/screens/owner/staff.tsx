// Staff: every person's work (money collected, tables visited, how fast they answered, guests' rating)
// with a detail sheet, every table, and guest feedback. Reports: /reports/staff and /reports/feedback.
import { ChevronRight, Download, Star } from "lucide-react";
import { useState } from "react";
import { money } from "../../lib/format";
import { Avatar } from "../../ui/logo";
import { Badge, Button, Card, Empty, Modal, SectionTitle, SkeletonList, useToast } from "../../ui/kit";
import { Bars, Kpi, rs, KpiSkeleton, KpiStrip, METHOD, Panel, Rows, SubNav, TableHead, secs, tableRow, toneText } from "./bits";
import { FeedbackView, RatingValue, useFeedback, type FeedbackReport } from "./feedback";
import { useReport, type Ctx, type SubProps } from "./Owner";

type Person = {
  staff_id: string | null;
  name: string;
  role: string;
  orders_taken: number;
  rounds_added: number;
  items_ordered: number;
  value_ordered: number;
  payments: { count: number; amount: number; by_method: Record<string, number> };
  calls: { answered: number; avg_answer_seconds: number | null; slowest_answer_seconds: number | null; avg_to_done_seconds: number | null };
  served: { count: number; avg_seconds: number | null };
  table_visits: number;
  tables: string[];
  voids: number;
  cancels: number;
  shifts: { count: number; variance: number };
};
type TableRow = { table_ref: string; orders: number; revenue: number; calls: number; waiters: string[]; avg_answer_seconds: number | null; average_bill: number };
type StaffReport = { staff: Person[]; tables: TableRow[]; calls: { count: number; unanswered: number; avg_answer_seconds: number | null } };

const speed = (s: number | null) => (s === null || s <= 60 ? undefined : s <= 180 ? "warn" : "bad");

type Rated = FeedbackReport["by_waiter"];

export function StaffPage({ ctx, sub, setSub }: { ctx: Ctx } & SubProps) {
  const [r] = useReport<StaffReport>(ctx, "/reports/staff");
  const [fb, , fbFailed] = useFeedback(ctx);
  const view = sub === "tables" || sub === "feedback" ? sub : "people";
  const toast = useToast();
  const csv = () => ctx.admin.download(ctx.admin.v(`/reports/staff.csv?from=${ctx.range.from}&to=${ctx.range.to}`), `staff-${ctx.range.from}-${ctx.range.to}.csv`).catch((e) => toast((e as Error).message, "bad"));
  return (
    <div className="flex flex-col gap-4">
      <SubNav
        label="Staff view"
        value={view}
        onChange={setSub}
        options={[
          ["people", "People"],
          ["tables", "Tables"],
          ["feedback", "Feedback"],
        ]}
        right={
          view === "feedback" ? null : (
            <Button variant="ghost" size="sm" onClick={csv} aria-label="Download CSV">
              <Download size={16} /> <span className="max-sm:hidden">Download CSV</span>
            </Button>
          )
        }
      />
      {view === "feedback" ? (
        <FeedbackView f={fb} failed={fbFailed} />
      ) : !r ? (
        <>
          <KpiSkeleton />
          <SkeletonList rows={5} />
        </>
      ) : view === "people" ? (
        <People r={r} rated={fb?.by_waiter ?? {}} />
      ) : (
        <Tables t={r.tables} />
      )}
    </div>
  );
}

const PEOPLE_COLS = "minmax(0,2.4fr) repeat(4,minmax(0,1fr)) minmax(0,1.2fr) 18px";

function People({ r, rated }: { r: StaffReport; rated: Rated }) {
  const [open, setOpen] = useState<Person | null>(null);
  const people = [...r.staff].sort((a, b) => Number(!a.staff_id) - Number(!b.staff_id) || b.payments.amount - a.payments.amount);
  const byGuests = r.staff.find((p) => !p.staff_id)?.orders_taken ?? 0;
  const row = tableRow(PEOPLE_COLS);
  const staff = people.filter((p) => p.staff_id);
  return (
    <>
      <KpiStrip>
        <Kpi label="Guest calls" value={r.calls.count} hint={r.calls.unanswered ? `${r.calls.unanswered} not answered` : "all answered"} tone={r.calls.unanswered ? "warn" : undefined} />
        <Kpi label="Time to answer" value={secs(r.calls.avg_answer_seconds)} hint="average" tone={speed(r.calls.avg_answer_seconds)} />
        <Kpi label="Orders by staff" value={staff.reduce((n, p) => n + p.orders_taken, 0)} hint={`${byGuests} by guests themselves`} />
        <Kpi label="Table visits" value={r.staff.reduce((n, p) => n + p.table_visits, 0)} hint="calls + food taken" />
      </KpiStrip>
      <div className="grid items-start gap-4 2xl:grid-cols-[minmax(0,1fr)_400px]">
        <Panel title="Every person" hint={`${staff.length} on the team · tap a person for the detail`}>
          <TableHead cols={PEOPLE_COLS}>
            <span>Person</span>
            <span>Visits</span>
            <span>Answers in</span>
            <span>Orders</span>
            <span>Rating</span>
            <span>Collected</span>
            <span />
          </TableHead>
          {people.length ? null : <Empty>Nothing yet in this period.</Empty>}
          {people.map((p) => {
            const rt = rated[p.name];
            return (
              <div key={p.staff_id ?? "guest"} data-staff={p.name} className="border-t border-line">
                <button onClick={() => setOpen(p)} style={row.style} className={`flex w-full items-center gap-3.5 px-4 py-3 text-left transition hover:bg-canvas/70 active:bg-canvas sm:px-5 ${row.cls}`}>
                  <span className="flex min-w-0 flex-1 items-center gap-3">
                    <Avatar size={40} />
                    <span className="min-w-0">
                      <span className="block truncate text-[15px] font-semibold">{p.name}</span>
                      <span className="block truncate text-sm text-muted">
                        <span className="capitalize">{p.role}</span>
                        <span className="lg:hidden">
                          {" "}
                          · {p.table_visits} {p.table_visits === 1 ? "visit" : "visits"} · <span className={toneText(speed(p.calls.avg_answer_seconds))}>{secs(p.calls.avg_answer_seconds)}</span>
                        </span>
                      </span>
                    </span>
                  </span>
                  <Cell>{p.table_visits}</Cell>
                  <Cell className={toneText(speed(p.calls.avg_answer_seconds))}>{secs(p.calls.avg_answer_seconds)}</Cell>
                  <Cell>{p.orders_taken}</Cell>
                  <Cell>{rt ? <RatingValue value={rt.average} size={13} /> : <span className="text-muted">—</span>}</Cell>
                  <span className="shrink-0 text-right">
                    <span className="num block font-bold">{money(p.payments.amount)}</span>
                    <span className="block text-xs text-muted lg:hidden">
                      {rt ? (
                        <span className="inline-flex items-center gap-0.5">
                          {rt.average.toFixed(1)} <Star size={10} strokeWidth={0} className="fill-ink" /> ·{" "}
                        </span>
                      ) : null}
                      collected
                    </span>
                  </span>
                  <ChevronRight size={18} className="hidden shrink-0 text-muted lg:block" />
                </button>
              </div>
            );
          })}
        </Panel>
        <div className="grid items-start gap-4 lg:grid-cols-2 2xl:grid-cols-1">
          <Card>
            <SectionTitle title="Money collected" />
            <Bars rows={staff.filter((p) => p.payments.amount).map((p) => [p.name, p.payments.amount])} format={money} />
          </Card>
          <Card>
            <SectionTitle title="Time to answer a call" hint="average; under a minute is good" />
            <Bars rows={staff.filter((p) => p.calls.avg_answer_seconds !== null).map((p) => [p.name, p.calls.avg_answer_seconds ?? 0])} format={secs} />
          </Card>
        </div>
      </div>
      <Modal open={!!open} onClose={() => setOpen(null)} title={open ? <PersonTitle p={open} /> : null} footer={<Button className="w-full" onClick={() => setOpen(null)}>Done</Button>}>
        {open ? <PersonDetail p={open} rated={rated[open.name]} /> : null}
      </Modal>
    </>
  );
}

/** A number cell of a table row (tablets and up only). */
const Cell = ({ children, className = "" }: { children: React.ReactNode; className?: string }) => <span className={`num hidden whitespace-nowrap text-right text-[15px] font-semibold lg:block ${className}`}>{children}</span>;

function PersonTitle({ p }: { p: Person }) {
  return (
    <span className="flex items-center gap-3">
      <Avatar size={44} />
      <span>
        <span className="block leading-tight">{p.name}</span>
        <span className="block text-sm font-medium capitalize text-muted">{p.role}</span>
      </span>
    </span>
  );
}

function PersonDetail({ p, rated }: { p: Person; rated?: Rated[string] }) {
  return (
    <div className="flex flex-col gap-6">
      <div className={`grid gap-px overflow-hidden rounded-2xl bg-line shadow-soft ${rated ? "grid-cols-2 sm:grid-cols-4" : "grid-cols-3"}`}>
        <Mini label="Collected" value={money(p.payments.amount)} />
        <Mini label="Visits" value={p.table_visits} />
        <Mini label="Answers in" value={secs(p.calls.avg_answer_seconds)} tone={speed(p.calls.avg_answer_seconds)} />
        {rated ? <Mini label={`Rating · ${rated.count}`} value={<RatingValue value={rated.average} size={14} />} tone={rated.average < 3.5 ? "bad" : undefined} /> : null}
      </div>
      <Group title="Going to tables">
        <Rows
          rows={[
            ["Calls answered", p.calls.answered],
            ["Average time to answer", secs(p.calls.avg_answer_seconds)],
            ["Slowest answer", secs(p.calls.slowest_answer_seconds)],
            ["Time at the table (to done)", secs(p.calls.avg_to_done_seconds)],
            ["Food taken to tables", p.served.count],
            ["Ready → on the table", secs(p.served.avg_seconds)],
            ["Tables", p.tables.join(", ") || "—"],
          ]}
        />
      </Group>
      <Group title="Payments collected">
        <Rows
          rows={[
            ["Payments", p.payments.count],
            ...Object.entries(p.payments.by_method).map(([m, v]) => [METHOD[m] ?? m, money(v)] as [string, string]),
            ["Total", money(p.payments.amount)],
            ["Cash shifts", p.shifts.count],
            ["Cash difference", <span className={p.shifts.variance ? "text-warn" : ""}>{money(p.shifts.variance)}</span>],
          ]}
        />
      </Group>
      <Group title="Orders">
        <Rows
          rows={[
            ["Orders taken", p.orders_taken],
            ["Extra rounds added", p.rounds_added],
            ["Items ordered", p.items_ordered],
            ["Value of their orders", money(p.value_ordered)],
            ["Voids", p.voids],
            ["Cancelled", p.cancels],
          ]}
        />
      </Group>
    </div>
  );
}

const Mini = ({ label, value, tone }: { label: string; value: React.ReactNode; tone?: "ok" | "warn" | "bad" }) => (
  <div className="min-w-0 bg-surface px-3.5 py-3">
    <div className="truncate text-xs font-medium text-muted">{label}</div>
    <div className={`num mt-0.5 truncate text-lg font-bold tracking-tight ${toneText(tone)}`}>{value}</div>
  </div>
);
const Group = ({ title, children }: { title: string; children: React.ReactNode }) => (
  <section>
    <h3 className="mb-2 text-base font-bold tracking-tight">{title}</h3>
    {children}
  </section>
);

const TABLE_COLS = "minmax(0,1fr) repeat(4,minmax(0,1fr)) minmax(0,1.6fr) minmax(0,1.1fr) 18px";

function Tables({ t }: { t: TableRow[] }) {
  const [open, setOpen] = useState<TableRow | null>(null);
  const rows = [...t].sort((a, b) => b.revenue - a.revenue);
  const best = rows[0];
  const row = tableRow(TABLE_COLS);
  return (
    <>
      <KpiStrip>
        <Kpi label="Tables used" value={t.filter((x) => x.orders).length} />
        <Kpi label="Table orders" value={t.reduce((n, x) => n + x.orders, 0)} />
        <Kpi label="Table sales" value={rs(t.reduce((n, x) => n + x.revenue, 0))} />
        <Kpi label="Best table" value={best ? best.table_ref.toUpperCase() : "—"} hint={best ? money(best.revenue) : undefined} />
      </KpiStrip>
      <div className="grid items-start gap-4 2xl:grid-cols-[minmax(0,1fr)_400px]">
        <Panel title="Every table" hint="Most sales first">
          <TableHead cols={TABLE_COLS}>
            <span>Table</span>
            <span>Orders</span>
            <span>Avg bill</span>
            <span>Calls</span>
            <span>Answers in</span>
            <span>Waiters</span>
            <span>Sales</span>
            <span />
          </TableHead>
          {rows.length ? null : <Empty>No table orders in this period.</Empty>}
          {rows.map((x) => (
            <button key={x.table_ref} data-table={x.table_ref} onClick={() => setOpen(x)} style={row.style} className={`flex w-full items-center gap-3.5 border-t border-line px-4 py-3 text-left transition hover:bg-canvas/70 sm:px-5 ${row.cls}`}>
              <span className="flex min-w-0 flex-1 items-center gap-3">
                <span className="num grid h-10 min-w-10 shrink-0 place-items-center rounded-xl bg-canvas px-2 text-sm font-bold text-ink">{x.table_ref.toUpperCase()}</span>
                <span className="min-w-0 lg:hidden">
                  <span className="block truncate font-semibold">
                    {x.orders} {x.orders === 1 ? "order" : "orders"} · avg {money(x.average_bill)}
                  </span>
                  <span className="block truncate text-sm text-muted">
                    {x.calls} {x.calls === 1 ? "call" : "calls"}
                    {x.avg_answer_seconds !== null ? ` · answered in ${secs(x.avg_answer_seconds)}` : ""} · {x.waiters.join(", ") || "no waiter"}
                  </span>
                </span>
              </span>
              <Cell>{x.orders}</Cell>
              <Cell>{money(x.average_bill)}</Cell>
              <Cell>{x.calls}</Cell>
              <Cell className={toneText(speed(x.avg_answer_seconds))}>{secs(x.avg_answer_seconds)}</Cell>
              <span className="hidden truncate text-right text-sm text-muted lg:block">{x.waiters.join(", ") || "—"}</span>
              <span className="num shrink-0 whitespace-nowrap text-right font-bold">{money(x.revenue)}</span>
              <ChevronRight size={18} className="hidden shrink-0 text-muted lg:block" />
            </button>
          ))}
        </Panel>
        <div className="grid items-start gap-4 lg:grid-cols-2 2xl:grid-cols-1">
          <Card>
            <SectionTitle title="Sales by table" />
            <Bars rows={rows.slice(0, 8).map((x) => [x.table_ref.toUpperCase(), x.revenue])} format={money} />
          </Card>
          <Card>
            <SectionTitle title="Guest calls by table" />
            <Bars rows={[...rows].sort((a, b) => b.calls - a.calls).filter((x) => x.calls).slice(0, 8).map((x) => [x.table_ref.toUpperCase(), x.calls])} format={String} />
          </Card>
        </div>
      </div>
      <Modal open={!!open} onClose={() => setOpen(null)} title={open ? `Table ${open.table_ref.toUpperCase()}` : null}>
        {open ? (
          <Rows
            rows={[
              ["Sales", money(open.revenue)],
              ["Orders", open.orders],
              ["Average bill", money(open.average_bill)],
              ["Guest calls", open.calls],
              ["Time to answer", <span className={toneText(speed(open.avg_answer_seconds))}>{secs(open.avg_answer_seconds)}</span>],
              ["Waiters", open.waiters.length ? open.waiters.map((w) => <Badge key={w} className="ml-1">{w}</Badge>) : "—"],
            ]}
          />
        ) : null}
      </Modal>
    </>
  );
}
