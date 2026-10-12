// Package picker: package + tier + add-ons (or custom modules), how the restaurant works (flows),
// extra screens and equipment, with the quote from the price list.
// Whatever the chosen screens and flows need is added by the server and shown locked here, with the
// reason (a kiosk needs a kiosk printer, a cashier a receipt printer and a cash drawer...).
// Screens that are not offered yet (GET /v1/features: self-order kiosk, status board) show "Coming
// soon" and can't be chosen; a plan that already has them keeps them.
// `show` picks the part on screen ("package" or "equipment"); both stay mounted so the choice is kept.
import { AnimatePresence, motion } from "motion/react";
import { Check, ChevronDown, Lock, Minus, Plus } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import type { Admin } from "../../lib/admin";
import { useComingSoon } from "../../lib/features";
import { money } from "../../lib/format";
import { Badge, IconButton, Skeleton } from "../../ui/kit";
import { cap, HIDDEN_MODULES, inputCls, isCustom, say, SCREEN_LABEL, type Catalog, type Plan, type PlanValue, type Quote } from "./catalog";

const DEFAULT_MODULES: Record<string, string[]> = { custom: ["R-CORE", "R-KDS", "R-PAY"], hotel: ["H-CORE", "R-PAY"] };
const LOCKED_MODULES: Record<string, string[]> = { custom: ["R-CORE", "R-KDS"], hotel: ["H-CORE"] };

type State = { pack: string; tier: string; add: string[]; modules: string[]; extra: Record<string, number>; hw: Record<string, number>; flows: string[] };

function initialState(catalog: Catalog, initial: Plan | null | undefined): State {
  const pack = initial?.pack && catalog.packs[initial.pack] ? initial.pack : "pack2";
  const s: State = {
    pack,
    tier: initial?.tier || "starter",
    add: [],
    modules: initial?.modules?.length ? [...initial.modules] : DEFAULT_MODULES[pack] ?? DEFAULT_MODULES.custom,
    extra: {},
    hw: { ...(initial?.hardware ?? {}) },
    flows: [...(initial?.flows ?? [])],
  };
  if (!initial) return s;
  const base = initial.tier ? catalog.packs[pack]?.tiers[initial.tier] : undefined;
  if (base) {
    s.add = initial.modules.filter((m) => !base.modules.includes(m));
    for (const [k, n] of Object.entries(initial.screens ?? {})) {
      const more = n - (base.screens[k] || 0);
      if (more > 0) s.extra[k] = more;
    }
  } else if (isCustom(pack)) {
    s.extra = { ...(initial.screens ?? {}) };
  }
  return s;
}

function Part({ title, hint, children, right }: { title: string; hint?: string; children: ReactNode; right?: ReactNode }) {
  return (
    <div>
      <div className="mb-2.5 flex items-end justify-between gap-3">
        <div>
          <div className="text-[15px] font-semibold">{title}</div>
          {hint ? <div className="text-sm text-muted">{hint}</div> : null}
        </div>
        {right}
      </div>
      {children}
    </div>
  );
}

/** A small number with − / + (the input stays a real number input for typing and the tests). */
function Stepper({ value, min = 0, onChange, input, noMore = false }: { value: number; min?: number; onChange: (n: number) => void; input: React.InputHTMLAttributes<HTMLInputElement>; noMore?: boolean }) {
  return (
    <div className="flex shrink-0 items-center gap-1">
      <IconButton type="button" label="One less" size={34} disabled={value <= min} onClick={() => onChange(Math.max(min, value - 1))}>
        <Minus size={15} />
      </IconButton>
      <input type="number" min={min} max={noMore ? value : undefined} readOnly={noMore} {...input} className="num h-10 w-14 rounded-xl bg-transparent text-center text-[15px] font-semibold outline-none ring-1 ring-transparent transition focus:ring-ink [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none" />
      <IconButton type="button" label="One more" size={34} disabled={noMore} onClick={() => onChange(value + 1)}>
        <Plus size={15} />
      </IconButton>
    </div>
  );
}

export function PlanPicker({ admin, catalog, initial, onChange, onQuote, show = "all" }: { admin: Admin; catalog: Catalog; initial?: Plan | null; onChange: (v: PlanValue) => void; onQuote?: (q: Quote | null) => void; show?: "all" | "package" | "equipment" | "none" }) {
  const [s, setS] = useState<State>(() => initialState(catalog, initial));
  const set = (patch: Partial<State>) => setS((old) => ({ ...old, ...patch }));
  const [quote, setQuote] = useState<Quote | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [hwDraft, setHwDraft] = useState<Record<string, string>>({});
  const [more, setMore] = useState(false);
  const [lines, setLines] = useState(false);
  const seq = useRef(0);
  const soon = useComingSoon();
  /** A flow (or package) that brings a screen type which is not offered yet. */
  const soonIn = (screens: Record<string, number>) => Object.keys(screens).some((t) => soon.includes(t));
  /** A package whose screens are, apart from the kitchen display, all coming soon (Pack 1 · Self-Serve). */
  const soonPack = (k: string) => {
    const tiers = Object.values(catalog.packs[k]?.tiers ?? {});
    return tiers.length > 0 && tiers.every((t) => Object.keys(t.screens).filter((x) => x !== "kds").every((x) => soon.includes(x)));
  };

  const pack = catalog.packs[s.pack];
  const custom = isCustom(s.pack);
  const hotel = s.pack === "hotel";
  const tier = custom ? null : pack.tiers[s.tier] ?? Object.values(pack.tiers)[0];
  const flowInfo = useMemo(() => Object.fromEntries(catalog.flows.map((f) => [f.code, f])), [catalog]);

  // A flow is offered if this tier can carry its modules (and those of the flows it needs).
  const available = useMemo(() => {
    const allowed = tier ? new Set([...tier.modules, ...tier.addons]) : null;
    const ok = (code: string, depth = 0): boolean => {
      const f = flowInfo[code];
      if (!f) return false;
      if (allowed && f.modules.some((m) => !allowed.has(m))) return false;
      return depth > 4 || f.needs.every((n) => ok(n, depth + 1));
    };
    return Object.fromEntries(catalog.flows.map((f) => [f.code, ok(f.code)]));
  }, [tier, flowInfo, catalog]);

  const flows = s.flows.filter((c) => available[c]);
  const neededBy: Record<string, string[]> = {};
  for (const c of flows) for (const n of flowInfo[c]?.needs ?? []) (neededBy[n] ||= []).push(flowInfo[c].name);

  const value: PlanValue = useMemo(() => {
    const screens = Object.fromEntries(Object.entries(s.extra).filter(([, n]) => n > 0));
    const hardware = Object.fromEntries(Object.entries(s.hw).filter(([, n]) => n > 0));
    return custom ? { pack: s.pack, modules: s.modules, screens, hardware, flows } : { pack: s.pack, tier: s.tier, add: s.add, screens, hardware, flows };
  }, [s, custom, flows.join(",")]);
  const key = JSON.stringify(value);

  useEffect(() => {
    onChange(value);
    const my = ++seq.current;
    setBusy(true);
    const t = setTimeout(async () => {
      try {
        const q = await admin.api<Quote>("POST", "/v1/platform/quote", value);
        if (my !== seq.current) return;
        setQuote(q);
        onQuote?.(q);
        setErr("");
      } catch (x) {
        if (my === seq.current) setErr((x as Error).message);
      } finally {
        if (my === seq.current) setBusy(false);
      }
    }, 200);
    return () => clearTimeout(t);
  }, [key]);

  const toggle = (list: string[], code: string, on: boolean) => (on ? [...new Set([...list, code])] : list.filter((x) => x !== code));

  const choices = (custom ? catalog.modules.filter((m) => m.hotel === hotel || m.code === "R-PAY") : catalog.modules.filter((m) => tier!.addons.includes(m.code))).filter((m) => !HIDDEN_MODULES.includes(m.code));
  const chosen = custom ? s.modules : s.add;
  const locked = custom ? LOCKED_MODULES[s.pack] ?? [] : [];
  const screenKinds = hotel ? ["room", "kds"] : ["table", "kiosk", "cashier", "kds", "waiter", "status"];

  const plan = quote?.plan;
  const need = Object.fromEntries((plan?.requirements ?? []).map((r) => [r.item, r]));
  const anyMore = catalog.flows.some((f) => f.group === "more" && (flows.includes(f.code) || neededBy[f.code]));
  const showMore = more || anyMore;

  const flowCard = (f: (typeof catalog.flows)[number]) => {
    const by = neededBy[f.code];
    const mine = flows.includes(f.code);
    const can = available[f.code];
    const on = can && (mine || !!by);
    const later = soonIn(f.screens) && !on;
    return (
      <label
        key={f.code}
        data-flow={f.code}
        title={f.about}
        data-coming-soon={later || undefined}
        className={`flow-choice relative flex items-start gap-3 rounded-2xl p-3.5 transition ${on ? "on bg-surface ring-2 ring-ink" : later ? "bg-canvas ring-1 ring-line" : "bg-surface ring-1 ring-line hover:bg-ink/[.02]"} ${later ? "coming-soon cursor-not-allowed" : can ? "cursor-pointer active:scale-[.99]" : "cursor-not-allowed opacity-45"}`}
      >
        <input type="checkbox" className="peer sr-only" checked={on} disabled={!can || later || (!!by && !mine)} onChange={(e) => set({ flows: toggle(s.flows, f.code, e.target.checked) })} />
        <span className={`mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-md transition peer-focus-visible:ring-2 peer-focus-visible:ring-ink ${on ? "bg-ink text-canvas" : "ring-2 ring-inset ring-line"}`}>{on ? by && !mine ? <Lock size={11} strokeWidth={3} /> : <Check size={13} strokeWidth={3} /> : null}</span>
        <span className="flex min-w-0 flex-1 flex-col gap-0.5">
          <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <strong className={`text-[15px] font-semibold leading-tight ${later ? "text-muted" : ""}`}>{f.name}</strong>
            {later ? <Badge>Coming soon</Badge> : null}
          </span>
          <span className={`text-[13px] leading-snug ${by ? "font-medium text-ink" : "text-muted"} ${later ? "opacity-70" : ""}`}>{later ? say(f.about) : !can ? "Not in this tier. Use Pack 4 · Custom" : by ? `Needed by ${by.join(", ")}` : say(f.about)}</span>
        </span>
      </label>
    );
  };

  const packagePart = (
    <div className="flex flex-col gap-6">
      <div className="grid grid-cols-2 gap-3">
        <label className="text-sm font-medium text-muted">
          Package
          <select
            aria-label="Package"
            className={`${inputCls} mt-1.5`}
            value={s.pack}
            onChange={(e) => {
              const p = e.target.value;
              set({ pack: p, add: [], extra: {}, modules: DEFAULT_MODULES[p] ?? s.modules, tier: catalog.packs[p].tiers[s.tier] ? s.tier : "starter" });
            }}
          >
            {Object.entries(catalog.packs).map(([k, p]) => (
              <option key={k} value={k} disabled={soonPack(k) && k !== s.pack}>
                {p.name}
                {soonPack(k) ? " (coming soon)" : ""}
              </option>
            ))}
          </select>
        </label>
        {tier ? (
          <label className="text-sm font-medium text-muted">
            Tier
            <select aria-label="Tier" className={`${inputCls} mt-1.5`} value={s.tier} onChange={(e) => set({ tier: e.target.value, add: [] })}>
              {Object.keys(pack.tiers).map((t) => (
                <option key={t} value={t}>
                  {cap(t)}
                </option>
              ))}
            </select>
          </label>
        ) : (
          <p className="self-end pb-3 text-sm text-muted">{hotel ? "Hotel: choose the modules below." : "Custom: choose every module and screen below."}</p>
        )}
      </div>

      {catalog.flows.length ? (
        <Part title="How does this restaurant work?" hint="Each choice brings the screens, equipment and settings it needs.">
          <div className="flows flex flex-col gap-2">
            <div className="flow-grid grid gap-2 sm:grid-cols-2">{catalog.flows.filter((f) => (f.group || "core") === "core").map(flowCard)}</div>
            <button type="button" onClick={() => setMore((m) => !m)} className="inline-flex items-center gap-1 self-start rounded-full px-1 py-1.5 text-sm font-semibold text-muted transition hover:text-ink">
              <ChevronDown size={16} className={`transition ${showMore ? "rotate-180" : ""}`} /> {showMore ? "Fewer options" : "More options"}
            </button>
            <AnimatePresence initial={false}>
              {showMore ? (
                <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.22 }} className="overflow-hidden">
                  <div className="flow-grid grid gap-2 p-px sm:grid-cols-2">{catalog.flows.filter((f) => f.group === "more").map(flowCard)}</div>
                </motion.div>
              ) : null}
            </AnimatePresence>
          </div>
        </Part>
      ) : null}

      {choices.length ? (
        <Part title={custom ? "Modules" : "Add-ons"} hint={custom ? "Every module this restaurant pays for." : tier ? `On top of ${cap(s.tier)}: ${tier.modules.join(", ")}` : undefined}>
          <div className="flex flex-wrap gap-2">
            {choices.map((m) => {
              const on = chosen.includes(m.code);
              const lock = locked.includes(m.code);
              const later = !on && !!m.device_type && soon.includes(m.device_type);
              return (
                <label key={m.code} data-module={m.code} title={say(m.name)} className={`flex min-h-10 items-center gap-2 rounded-full px-3.5 py-1.5 text-sm ring-1 transition ${on || lock ? "bg-ink/[.06] ring-ink" : later ? "bg-canvas ring-line" : "bg-surface ring-line hover:bg-ink/[.02]"} ${lock || later ? "cursor-default" : "cursor-pointer"}`}>
                  <input type="checkbox" className="h-4 w-4 accent-ink" checked={on || lock} disabled={lock || later} onChange={(e) => (custom ? set({ modules: toggle(s.modules, m.code, e.target.checked) }) : set({ add: toggle(s.add, m.code, e.target.checked) }))} />
                  <span className="font-semibold">{m.code}</span>
                  <span className="text-muted">{say(m.name)}</span>
                  {lock ? <Lock size={13} className="text-muted" /> : null}
                  {later ? <span className="text-xs font-semibold text-muted">· Coming soon</span> : null}
                </label>
              );
            })}
          </div>
        </Part>
      ) : null}

      <Part title={custom ? "Screens" : "Extra screens"} hint={custom ? undefined : "On top of what the tier includes."}>
        <div className="-mx-2 grid sm:grid-cols-2">
          {screenKinds.map((k) => {
            const later = soon.includes(k);
            const n = s.extra[k] || 0;
            return (
              <div key={k} className="flex min-h-[52px] items-center gap-3 rounded-2xl px-2 py-1.5" data-coming-soon={later || undefined}>
                <span className={`min-w-0 flex-1 truncate text-[15px] ${later ? "text-muted" : ""}`}>{SCREEN_LABEL[k]}</span>
                {later && !n ? (
                  <Badge className="mr-1 shrink-0">Coming soon</Badge>
                ) : (
                  <Stepper
                    noMore={later}
                    value={n}
                    onChange={(v) => set({ extra: { ...s.extra, [k]: v } })}
                    input={{ "data-screen": k, "aria-label": SCREEN_LABEL[k], value: n, onChange: (e) => set({ extra: { ...s.extra, [k]: Math.max(0, Number(e.target.value) || 0) } }) } as React.InputHTMLAttributes<HTMLInputElement>}
                  />
                )}
              </div>
            );
          })}
        </div>
      </Part>
    </div>
  );

  const equipmentPart = (
    <div className={`flex flex-col gap-6 transition ${busy && quote ? "opacity-70" : ""}`}>
      {err ? (
        <p className="flex items-center gap-2 text-sm font-medium text-bad">
          <span className="h-1.5 w-1.5 rounded-full bg-bad" />
          {err}
        </p>
      ) : null}
      {!plan ? (
        err ? null : (
          <div className="flex flex-col gap-2">
            <Skeleton className="h-12" />
            <Skeleton className="h-12" />
            <Skeleton className="h-12 w-2/3" />
          </div>
        )
      ) : (
        <>
          {plan.warnings.length ? (
            <div className="flex flex-col gap-1">
              {plan.warnings.map((w) => (
                <p key={w} className="flex items-start gap-2 text-sm font-medium text-warn">
                  <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-warn" />
                  {say(w)}
                </p>
              ))}
            </div>
          ) : null}
          <Part title="Equipment to install" hint="Locked items are needed by the screens you chose.">
            <div className="equipment -mx-2 flex flex-col">
              {Object.entries(catalog.hardware).map(([k, name]) => {
                const min = need[k]?.min || 0;
                const n = plan.hardware[k] || 0;
                const shown = hwDraft[k] ?? String(n);
                const commit = (raw: string) => {
                  setHwDraft((d) => ({ ...d, [k]: raw }));
                  set({ hw: { ...s.hw, [k]: Math.max(min, Number(raw) || 0) } });
                };
                return (
                  <div key={k} className="flex items-center gap-3 rounded-2xl px-2 py-1.5" title={need[k]?.reasons.join(". ") || ""}>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-1.5 text-[15px]">
                        {name}
                        {min ? <Lock size={13} className="shrink-0 text-muted" /> : null}
                      </div>
                      {min ? <div className="truncate text-[13px] text-muted">{need[k].reasons.join(". ")}</div> : null}
                    </div>
                    <Stepper
                      value={Number(shown) || 0}
                      min={min}
                      onChange={(v) => (setHwDraft(({ [k]: _d, ...rest }) => rest), set({ hw: { ...s.hw, [k]: Math.max(min, v) } }))}
                      input={{
                        "data-hw": k,
                        "aria-label": name,
                        value: shown,
                        onChange: (e) => commit(e.target.value),
                        onInput: (e) => commit((e.target as HTMLInputElement).value),
                        onBlur: () => setHwDraft(({ [k]: _drop, ...rest }) => rest),
                      } as React.InputHTMLAttributes<HTMLInputElement>}
                    />
                  </div>
                );
              })}
            </div>
          </Part>

          {quote ? (
            <div className="rounded-2xl bg-ink/[.035] p-4">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <div className="text-sm text-muted">Monthly</div>
                  <div className="num text-2xl font-bold tracking-tight">{money(quote.monthly_total)}</div>
                </div>
                <div>
                  <div className="text-sm text-muted">One-time</div>
                  <div className="num text-2xl font-bold tracking-tight">{money(quote.once_total)}</div>
                </div>
              </div>
              {quote.missing_prices.length ? <p className="mt-2 text-xs text-muted">{quote.missing_prices.length} items have no price yet (see the price list).</p> : null}
              <button type="button" onClick={() => setLines((x) => !x)} className="mt-2 inline-flex items-center gap-1 text-sm font-semibold text-muted transition hover:text-ink">
                <ChevronDown size={16} className={`transition ${lines ? "rotate-180" : ""}`} /> Quote, line by line
              </button>
              {lines ? (
                <table className="mt-2 w-full text-sm">
                  <thead>
                    <tr className="text-left text-xs text-muted">
                      <th className="py-1 font-medium">Item</th>
                      <th className="py-1 text-right font-medium">Qty</th>
                      <th className="py-1 text-right font-medium">Monthly</th>
                      <th className="py-1 text-right font-medium">One-time</th>
                    </tr>
                  </thead>
                  <tbody>
                    {quote.lines.map((l) => (
                      <tr key={l.item} className="border-t border-line">
                        <td className="py-1.5">
                          {say(l.item.startsWith("screen:") ? SCREEN_LABEL[l.item.slice(7)] ?? l.name : l.name)}
                          {quote.missing_prices.includes(l.item) ? <span className="ml-1 text-xs text-muted">· no price</span> : null}
                        </td>
                        <td className="num py-1.5 text-right">{l.qty}</td>
                        <td className="num py-1.5 text-right">{money(l.monthly)}</td>
                        <td className="num py-1.5 text-right">{money(l.once)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : null}
            </div>
          ) : null}
        </>
      )}
    </div>
  );

  return (
    <div className="flex flex-col gap-6">
      <div className={show === "all" || show === "package" ? "" : "hidden"}>{packagePart}</div>
      <div className={show === "all" || show === "equipment" ? "" : "hidden"}>{equipmentPart}</div>
    </div>
  );
}
