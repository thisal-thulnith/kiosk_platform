// Money: every payment of a day, the accounting downloads, and checking the bank's settlement file.
import { AlertTriangle, CheckCircle2, Download, FileUp, Landmark, Receipt, ReceiptText, UsersRound } from "lucide-react";
import { useRef, useState, type ReactNode } from "react";
import { money, toCents } from "../../lib/format";
import { Badge, Button, Card, Empty, Field, Input, SectionTitle, Segmented, Skeleton, SkeletonList, useToast } from "../../ui/kit";
import { Bars, CHANNEL, CountUp, Kpi, KpiSkeleton, KpiStrip, METHOD, Panel, Rows, SubNav, TableHead, clockOf, presets, rs, tableRow } from "./bits";
import { useReport, type Ctx, type SubProps } from "./Owner";

type View = "payments" | "accounting" | "bank";

export function MoneyPage({ ctx, sub, setSub }: { ctx: Ctx } & SubProps) {
  const view: View = sub === "accounting" || sub === "bank" ? sub : "payments";
  return (
    <div className="flex flex-col gap-4">
      <SubNav<View>
        label="Money view"
        value={view}
        onChange={setSub}
        options={[
          ["payments", "Payments"],
          ["accounting", "Accounting"],
          ["bank", "Bank check"],
        ]}
      />
      {view === "payments" ? <Payments ctx={ctx} /> : view === "accounting" ? <Accounting ctx={ctx} /> : <Bank ctx={ctx} />}
    </div>
  );
}

// ------------------------------------------------------------------ payments

type LedgerLine = { id: string; ref: string; at: string; kind: string; method: string; amount: number; token: string; table: string | null; channel: string; collected_by: string | null; device: string | null; outside_ref: string | null; invoice: string | null; reason: string | null };
type LedgerRep = { day: string; lines: LedgerLine[]; total: number; count: number; by_method: Record<string, number>; by_staff: Record<string, number> };
const PAY_COLS = "5rem minmax(0,1fr) minmax(0,1fr) minmax(0,1fr) minmax(0,1.2fr) minmax(0,1.6fr) minmax(0,1fr)";

function Payments({ ctx }: { ctx: Ctx }) {
  const toast = useToast();
  const tz = ctx.admin.venue?.timezone || "Asia/Colombo";
  const [day, setDay] = useState(presets(tz).today.from);
  const [method, setMethod] = useState("all");
  const [r] = useReport<LedgerRep>(ctx, `/reports/payments?day=${day}${method !== "all" ? `&method=${method}` : ""}`, false);
  const csv = () => ctx.admin.download(ctx.admin.v(`/reports/payments.csv?day=${day}`), `payments-${day}.csv`).catch((e) => toast(e.message, "bad"));
  const row = tableRow(PAY_COLS);
  const methods = r ? [...new Set(["cash", "card", "lankaqr", ...Object.keys(r.by_method)])] : [];
  const where = (l: LedgerLine) => (l.table ? `Table ${l.table}` : (CHANNEL[l.channel] ?? l.channel));
  return (
    <>
      <div className="flex flex-wrap items-center gap-2">
        <div className="w-44">
          <Input aria-label="Day" type="date" value={day} onChange={(e) => e.target.value && setDay(e.target.value)} className="h-10!" />
        </div>
        <Segmented
          className="[&>button]:h-8"
          value={method}
          onChange={setMethod}
          options={[
            ["all", "All"],
            ["cash", "Cash"],
            ["card", "Card"],
            ["lankaqr", "QR"],
          ]}
        />
        <span className="flex-1" />
        <Button variant="ghost" size="sm" onClick={csv} aria-label="Download CSV">
          <Download size={16} /> <span className="max-sm:hidden">Download CSV</span>
        </Button>
      </div>
      {!r ? (
        <>
          <KpiSkeleton />
          <SkeletonList rows={5} />
        </>
      ) : (
        <>
          <KpiStrip cols={methods.length > 3 ? 5 : 4}>
            <Kpi label="Taken" value={<CountUp value={r.total} format={rs} />} hint={`${r.count} payments`} />
            {methods.slice(0, 4).map((m) => (
              <Kpi key={m} label={METHOD[m] ?? m} value={rs(r.by_method[m] ?? 0)} hint={r.total ? `${Math.round((100 * (r.by_method[m] ?? 0)) / r.total)}% of the day` : "nothing yet"} />
            ))}
          </KpiStrip>
          <div className="grid items-start gap-4 2xl:grid-cols-[minmax(0,1fr)_400px]">
            <Panel title="Every payment" hint={`${r.lines.length} on ${new Date(`${day}T12:00`).toLocaleDateString([], { weekday: "long", day: "numeric", month: "long" })}`}>
              <TableHead cols={PAY_COLS} left={2}>
                <span>Time</span>
                <span>Order</span>
                <span>Where</span>
                <span>Paid by</span>
                <span>Taken by</span>
                <span>Reference</span>
                <span>Amount</span>
              </TableHead>
              {r.lines.length ? null : <Empty icon={<Receipt size={24} />}>No payments on this day.</Empty>}
              {r.lines.map((l) => {
                const refs = [l.device, l.invoice, l.outside_ref ? `bank ${l.outside_ref}` : null, `#${l.ref}`, l.reason].filter(Boolean).join(" · ");
                return (
                  <div key={l.id} style={row.style} className={`flex items-center gap-3 border-t border-line px-4 py-3 sm:px-5 ${row.cls}`}>
                    <span className="num hidden text-sm text-muted lg:block">{clockOf(l.at)}</span>
                    <span className="min-w-0 flex-1">
                      <span className="flex items-center gap-2 font-semibold">
                        {l.token}
                        <span className="lg:hidden">
                          <Badge tone={l.kind === "refund" ? "bad" : "muted"}>{l.kind === "refund" ? "Refund" : (METHOD[l.method] ?? l.method)}</Badge>
                        </span>
                      </span>
                      <span className="block truncate text-sm text-muted lg:hidden">
                        {clockOf(l.at)} · {where(l)} · {[l.collected_by ?? "—", refs].join(" · ")}
                      </span>
                    </span>
                    <span className="hidden truncate text-right text-[15px] lg:block">{where(l)}</span>
                    <span className="hidden text-right lg:block">
                      <Badge tone={l.kind === "refund" ? "bad" : "muted"}>{l.kind === "refund" ? "Refund" : (METHOD[l.method] ?? l.method)}</Badge>
                    </span>
                    <span className="hidden truncate text-right text-[15px] lg:block">{l.collected_by ?? "—"}</span>
                    <span className="hidden truncate text-right text-sm text-muted lg:block" title={refs}>
                      {refs}
                    </span>
                    <span className={`num shrink-0 whitespace-nowrap text-right font-bold ${l.amount < 0 ? "text-bad" : ""}`}>{money(l.amount)}</span>
                  </div>
                );
              })}
            </Panel>
            <div className="grid items-start gap-4 lg:grid-cols-2 2xl:grid-cols-1">
              <Card>
                <SectionTitle title="Who took the money" />
                <Bars rows={Object.entries(r.by_staff)} format={money} />
              </Card>
              <Card>
                <SectionTitle title="How guests paid" />
                <Bars rows={Object.entries(r.by_method).map(([m, v]) => [METHOD[m] ?? m, v])} format={money} />
              </Card>
            </div>
          </div>
        </>
      )}
    </>
  );
}

// ------------------------------------------------------------------ accounting

function Accounting({ ctx }: { ctx: Ctx }) {
  const toast = useToast();
  const p = presets(ctx.admin.venue?.timezone || "Asia/Colombo");
  const [from, setFrom] = useState(p.month.from);
  const [to, setTo] = useState(p.today.to);
  const dl = (path: string, name: string) => ctx.admin.download(ctx.admin.v(path), name).catch((e) => toast((e as Error).message, "bad"));
  const files: [string, string, ReactNode, () => void, boolean][] = [
    ["Tax ledger", "One row per invoice, with service charge, VAT and SSCL in their own columns. For your accountant and IRD (RAMIS) returns.", <Landmark size={20} />, () => dl(`/reports/tax-ledger.csv?from=${from}&to=${to}`, `tax-ledger-${from}-${to}.csv`), true],
    ["All orders", "Every order with its items, channel, table and payment.", <ReceiptText size={20} />, () => dl(`/reports/orders.csv?from=${from}&to=${to}`, `orders-${from}-${to}.csv`), false],
    ["Staff", "Each person's orders, payments, table visits and answer times.", <UsersRound size={20} />, () => dl(`/reports/staff.csv?from=${from}&to=${to}`, `staff-${from}-${to}.csv`), false],
  ];
  return (
    <div className="flex flex-col gap-4">
      <Card className="flex flex-wrap items-end gap-3">
        <div className="mr-auto min-w-0">
          <h2 className="text-lg font-bold tracking-[-0.01em]">Accounting downloads</h2>
          <p className="text-sm text-muted">Pick the days, then download a file (CSV, opens in Excel).</p>
        </div>
        <Field label="From" className="w-[calc(50%-6px)] sm:w-44">
          <Input aria-label="From" type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
        </Field>
        <Field label="To" className="w-[calc(50%-6px)] sm:w-44">
          <Input aria-label="To" type="date" value={to} onChange={(e) => setTo(e.target.value)} />
        </Field>
      </Card>
      <div className="grid gap-4 md:grid-cols-3">
        {files.map(([title, text, icon, go, main]) => (
          <Card key={title} className="flex flex-col gap-4">
            <span className="grid h-11 w-11 place-items-center rounded-xl bg-canvas text-ink/70">{icon}</span>
            <div className="flex-1">
              <h3 className="text-base font-bold">{title}</h3>
              <p className="mt-1 text-sm text-muted">{text}</p>
            </div>
            <Button variant={main ? "primary" : "default"} onClick={go}>
              <Download size={18} /> {title} (CSV)
            </Button>
          </Card>
        ))}
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ bank check

type Rec = { day: string; by_method: Record<string, { charges: number; refunds: number; net: number }>; attention: { method: string; amount: number; issue: string }[] };
type Match = { all_clear: boolean; matched: unknown[]; amount_mismatch: { reference: string; ours: number; bank: number }[]; missing_in_bank: { reference: string; ours: number; method: string }[]; unknown_in_bank: { reference: string; amount: number }[] };

function Bank({ ctx }: { ctx: Ctx }) {
  const toast = useToast();
  const [rec] = useReport<Rec>(ctx, "/reports/reconciliation", false);
  const [match, setMatch] = useState<Match | null>(null);
  const file = useRef<HTMLInputElement>(null);
  const upload = async (f: File | undefined) => {
    if (!f || !rec) return;
    // Columns: reference, amount (rupees). A header row is skipped by itself.
    const rows = (await f.text())
      .split(/\r?\n/)
      .map((line) => line.split(",").map((x) => x.trim().replace(/^"|"$/g, "")))
      .filter((c) => c.length >= 2 && c[0] && !isNaN(parseFloat(c[1])))
      .map(([reference, amount]) => ({ reference, amount: toCents(amount) }));
    try {
      setMatch(await ctx.admin.api<Match>("POST", ctx.admin.v("/reports/reconciliation/match"), { day: rec.day, rows }));
    } catch (e) {
      toast((e as Error).message, "bad");
    } finally {
      if (file.current) file.current.value = "";
    }
  };
  if (!rec) return <Skeleton className="h-72 rounded-2xl" />;
  const problems = match ? [...match.amount_mismatch.map((x) => `Amount differs: ${x.reference} ours ${money(x.ours)} bank ${money(x.bank)}`), ...match.missing_in_bank.map((x) => `Not in bank file: ${x.reference} ${money(x.ours)} (${METHOD[x.method] ?? x.method})`), ...match.unknown_in_bank.map((x) => `Unknown to us: ${x.reference} ${money(x.amount)}`)] : [];
  return (
    <div className="grid items-start gap-4 md:grid-cols-2">
      <Card>
        <SectionTitle title="What we took" hint={rec.day} />
        <Rows rows={Object.entries(rec.by_method).map(([k, v]) => [METHOD[k] ?? k, v.refunds ? `${money(v.net)} (${money(v.charges)} − ${money(v.refunds)})` : money(v.net)])} />
        <div className="mt-4">
          {rec.attention.length ? (
            rec.attention.map((a, i) => (
              <p key={i} className="flex items-start gap-2 rounded-2xl bg-warn-soft px-3 py-2 text-sm font-medium text-warn">
                <AlertTriangle size={16} className="mt-0.5 shrink-0" /> {METHOD[a.method] ?? a.method} {money(a.amount)}: {a.issue}
              </p>
            ))
          ) : (
            <p className="flex items-center gap-2 text-sm text-muted">
              <CheckCircle2 size={16} className="text-ok" /> Nothing needs attention.
            </p>
          )}
        </div>
      </Card>
      <Card>
        <SectionTitle title="Check against the bank" hint="The bank's or provider's settlement file (CSV: reference, amount)." />
        <input ref={file} aria-label="Bank settlement CSV" type="file" accept=".csv,text/csv" onChange={(e) => upload(e.target.files?.[0])} className="hidden" />
        <Button variant="primary" onClick={() => file.current?.click()}>
          <FileUp size={18} /> Choose settlement file
        </Button>
        {match ? (
          <div className="mt-4 flex flex-col gap-2 text-sm">
            <Badge tone={match.all_clear ? "ok" : "bad"} className="self-start text-[13px]">
              {match.all_clear ? `All ${match.matched.length} payments match the bank` : "Differences found"}
            </Badge>
            <Rows
              rows={[
                ["Matched", match.matched.length],
                ["Amount differs", match.amount_mismatch.length],
                ["Not in bank file", match.missing_in_bank.length],
                ["Unknown to us", match.unknown_in_bank.length],
              ]}
            />
            {problems.map((t) => (
              <p key={t} className="text-bad">
                {t}
              </p>
            ))}
          </div>
        ) : null}
      </Card>
    </div>
  );
}
