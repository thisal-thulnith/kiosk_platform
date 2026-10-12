// Platform console, for our team: every restaurant with its setup progress (open its setup console,
// change its package), a 4-step wizard for a new restaurant with a live summary, and the price list
// the quotes come from.
import { appOrigin } from "../../lib/features";
import { AnimatePresence, motion } from "motion/react";
import { ArrowLeft, ArrowRight, ArrowUpRight, Check, CircleCheck, Copy, KeyRound, Link2, LogOut, Package, Plus, RefreshCw, Search, Store, Tablet, Tags } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import type { Admin } from "../../lib/admin";
import { money } from "../../lib/format";
import { ProductMark } from "../../ui/adminGate";
import { AppShell } from "../../ui/shell";
import { Appear, Badge, Button, Card, ease, Empty, Field, IconButton, Modal, MoreMenu, Skeleton, Status, useToast } from "../../ui/kit";
import { consoleUrl } from "../../lib/screens";
import { inputCls, planLabel, randomPassword, SCREEN_LABEL, type Catalog, type PlanValue, type Quote, type Tenant, type TenantVenue } from "./catalog";
import { PlanPicker } from "./PlanPicker";
import { PriceList } from "./PriceList";

const SETUP = (venueId: string, code?: string) => (code ? `/${code.toLowerCase()}/setup` : `/setup?venue=${encodeURIComponent(venueId)}`);
/** The Owner app: /{code}/owner for one restaurant, /owner (pick one after login) otherwise. */
const OWNER_APP = (code?: string) => consoleUrl("owner", code);

type View = "restaurants" | "prices" | "new";

export function Platform({ admin }: { admin: Admin }) {
  const toast = useToast();
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [tenants, setTenants] = useState<Tenant[] | null>(null);
  const [err, setErr] = useState("");
  const [view, setView] = useState<View>("restaurants");
  const [q, setQ] = useState("");

  const refresh = useCallback(async () => {
    try {
      setTenants(await admin.get<Tenant[]>("/v1/platform/tenants"));
    } catch (x) {
      toast((x as Error).message, "bad");
    }
  }, [admin, toast]);

  useEffect(() => {
    admin
      .get<Catalog>("/v1/platform/catalog")
      .then(setCatalog)
      .catch((x: Error) => setErr(x.message));
    void refresh();
    const t = setInterval(refresh, 10000);
    return () => clearInterval(t);
  }, []);

  const go = (v: string) => (setView(v as View), document.querySelector("main")?.scrollTo({ top: 0 }));
  const count = tenants?.reduce((n, t) => n + t.venues.length, 0);
  const TITLE: Record<View, ReactNode> = {
    restaurants: (
      <>
        Restaurants{count !== undefined ? <span className="num ml-2 text-base font-semibold text-muted">{count}</span> : null}
      </>
    ),
    new: "New restaurant",
    prices: "Price list",
  };

  return (
    <AppShell
      name="Kiosk Platform"
      sub="Platform console"
      mark={<ProductMark />}
      nav={[
        { key: "restaurants", label: "Restaurants", icon: Store },
        { key: "new", label: "New restaurant", icon: Plus },
        { key: "prices", label: "Price list", icon: Tags },
      ]}
      active={view}
      onNav={go}
      title={TITLE[view]}
      actions={
        view === "restaurants" && tenants && tenants.length > 3 ? (
          <label className="relative block w-full sm:w-72">
            <Search size={18} className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-muted" />
            <input aria-label="Find a restaurant" placeholder="Find a restaurant" value={q} onChange={(e) => setQ(e.target.value)} className={`${inputCls} h-10 pl-10`} />
          </label>
        ) : null
      }
      account={
        <div className="flex shrink-0 items-center gap-1">
          {view === "restaurants" ? (
            <span className="hidden md:inline-flex">
              <Button variant="primary" onClick={() => go("new")}>
                <Plus size={18} /> New restaurant
              </Button>
            </span>
          ) : null}
          <MoreMenu
            items={[
              { label: "Owner app", icon: <ArrowUpRight size={18} />, onClick: () => window.open(OWNER_APP(), "_blank", "noreferrer") },
              { label: "Log out", icon: <LogOut size={18} />, onClick: () => (admin.logout(), location.reload()) },
            ]}
          />
        </div>
      }
    >
      <div className="mx-auto w-full max-w-[1680px]">
        {err ? (
          <Card className="font-semibold text-bad">{err}</Card>
        ) : !catalog ? (
          <div className="flex flex-col gap-3">
            <Skeleton className="h-24 rounded-2xl" />
            <Skeleton className="h-64 rounded-2xl" />
          </div>
        ) : view === "new" ? (
          <NewRestaurant admin={admin} catalog={catalog} onCreated={refresh} onBack={() => go("restaurants")} />
        ) : view === "prices" ? (
          <Appear>
            <PriceList admin={admin} catalog={catalog} />
          </Appear>
        ) : (
          <Appear>
            <Restaurants admin={admin} catalog={catalog} tenants={tenants} q={q} refresh={refresh} onNew={() => go("new")} />
          </Appear>
        )}
      </div>
    </AppShell>
  );
}

// ------------------------------------------------------------------ new restaurant: a 4-step wizard

type Created = { tenant: Tenant; email: string; password: string; pin: string };
type Vals = Record<string, string>;

const PARTS: [string, string][] = [
  ["Restaurant", "The company and its first branch."],
  ["Owner login", "The owner uses this for the Owner app. Give it to them once it is created."],
  ["Package", "The package, and how this restaurant works."],
  ["Equipment & price", "What gets installed, and the quote."],
];

function NewRestaurant({ admin, catalog, onCreated, onBack }: { admin: Admin; catalog: Catalog; onCreated: () => void; onBack: () => void }) {
  const plan = useRef<PlanValue | null>(null);
  const form = useRef<HTMLFormElement>(null);
  const [step, setStep] = useState(0);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<Created | null>(null);
  const [formKey, setFormKey] = useState(0);
  const [vals, setVals] = useState<Vals>({});
  const [quote, setQuote] = useState<Quote | null>(null);
  const password = useMemo(randomPassword, [formKey]);

  const read = () => {
    if (!form.current) return;
    const f = new FormData(form.current);
    setVals(Object.fromEntries([...f.entries()].map(([k, v]) => [k, String(v)])));
  };
  useEffect(read, [formKey]);

  /** The inputs of one step are valid (shows the browser's hint on the first one that isn't). */
  const valid = (n: number) => {
    const els = form.current?.querySelectorAll<HTMLInputElement>(`[data-part="${n}"] input`) ?? [];
    for (const el of els) if (!el.checkValidity()) return setStep(n), setTimeout(() => el.reportValidity(), 50), false;
    return true;
  };
  const next = () => valid(step) && setStep((s) => Math.min(PARTS.length - 1, s + 1));

  // Inputs are read from the form on submit (uncontrolled), so scripted fills in the browser checks work.
  const submit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (step < PARTS.length - 1) return next(); // Enter in a field moves on
    for (let n = 0; n < PARTS.length; n++) if (!valid(n)) return;
    setErr("");
    const f = new FormData(e.currentTarget);
    const val = (k: string) => String(f.get(k) ?? "").trim();
    const body: Record<string, unknown> = {
      company_name: val("company_name"),
      venue_name: val("venue_name"),
      venue_code: val("venue_code").toUpperCase(),
      timezone: val("timezone") || "Asia/Colombo",
      owner_email: val("owner_email"),
      owner_password: val("owner_password"),
      sample_menu: f.get("sample_menu") === "on",
      plan: plan.current,
    };
    const pin = val("manager_pin");
    if (pin) body.manager_pin = pin;
    setBusy(true);
    try {
      const t = await admin.api<Tenant>("POST", "/v1/platform/tenants", body);
      setDone({ tenant: t, email: String(body.owner_email).toLowerCase(), password: String(body.owner_password), pin });
      setFormKey((k) => k + 1);
      setStep(0);
      onCreated();
      document.querySelector("main")?.scrollTo({ top: 0, behavior: "smooth" });
    } catch (x) {
      setErr((x as Error).message);
    } finally {
      setBusy(false);
    }
  };

  if (done) return <Handover created={done} onClose={() => setDone(null)} onBack={onBack} />;

  const last = step === PARTS.length - 1;
  return (
    <Appear className="mx-auto w-full max-w-[1280px]">
      <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_340px] 2xl:grid-cols-[minmax(0,1fr)_380px]">
        <Card className="overflow-hidden p-0!">
          <form key={formKey} ref={form} noValidate onSubmit={submit} onInput={read} onChange={read}>
            <div className="border-b border-line px-6 pb-5 pt-5">
              <WizardSteps at={step} onPick={(n) => (n < step || [...Array(n).keys()].every(valid)) && setStep(n)} />
            </div>

            <div className="px-6 py-6">
              <AnimatePresence mode="wait" initial={false}>
                <motion.div key={step} initial={{ opacity: 0, x: 12 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -12 }} transition={ease} className="mb-5">
                  <h2 className="text-lg font-bold tracking-tight">{PARTS[step][0]}</h2>
                  <p className="text-sm text-muted">{PARTS[step][1]}</p>
                </motion.div>
              </AnimatePresence>

              <div data-part="0" className={`form-part flex flex-col gap-4 ${step === 0 ? "" : "hidden"}`}>
                <Field label="Company / brand">
                  <input name="company_name" required minLength={2} placeholder="Ocean Grill (Pvt) Ltd" className={inputCls} />
                </Field>
                <div className="grid gap-4 sm:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
                  <Field label="First branch name">
                    <input name="venue_name" required minLength={2} placeholder="Ocean Grill Galle" className={inputCls} />
                  </Field>
                  <Field label="Branch code" hint="On invoices. 2–20 letters, numbers or -">
                    <input name="venue_code" required placeholder="OCEAN" pattern="[A-Za-z0-9\-]{2,20}" className={`${inputCls} uppercase`} />
                  </Field>
                </div>
                <Field label="Time zone">
                  <input name="timezone" defaultValue="Asia/Colombo" className={inputCls} />
                </Field>
              </div>

              <div data-part="1" className={`form-part flex flex-col gap-4 ${step === 1 ? "" : "hidden"}`}>
                <Field label="Owner email (their login)">
                  <input name="owner_email" type="email" required placeholder="owner@oceangrill.lk" className={inputCls} />
                </Field>
                <div className="grid gap-4 sm:grid-cols-2">
                  <Field label="Owner password" hint="At least 8 characters. Made up for you.">
                    <PasswordInput initial={password} onNew={read} />
                  </Field>
                  <Field label="First manager PIN" hint="For the POS. 4–8 digits, or empty.">
                    <input name="manager_pin" inputMode="numeric" defaultValue="1234" pattern="\d{4,8}" className={`${inputCls} num tracking-[.2em]`} />
                  </Field>
                </div>
                <label className="flex cursor-pointer items-center gap-3 rounded-2xl px-1 py-2 text-[15px] font-medium">
                  <input name="sample_menu" type="checkbox" defaultChecked className="h-5 w-5 accent-ink" />
                  Start with the sample menu and service charge / VAT rules
                </label>
              </div>

              {/* Steps 3 and 4 are one picker (one state), showing its two parts in turn. */}
              <PlanPicker admin={admin} catalog={catalog} show={step === 2 ? "package" : step === 3 ? "equipment" : "none"} onChange={(v) => (plan.current = v)} onQuote={setQuote} />

              {err && last ? (
                <p role="alert" className="mt-5 flex items-center gap-2 text-sm font-medium text-bad">
                  <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-bad" />
                  {err}
                </p>
              ) : null}
            </div>

            <div className="flex items-center gap-2 border-t border-line px-6 py-4">
              {step > 0 ? (
                <Button type="button" variant="ghost" onClick={() => setStep(step - 1)}>
                  <ArrowLeft size={18} /> Back
                </Button>
              ) : null}
              <span className="ml-auto text-sm text-muted">
                {step + 1} of {PARTS.length}
              </span>
              {last ? (
                <Button key="create" variant="primary" size="lg" type="submit" disabled={busy}>
                  {busy ? "Creating…" : "Create restaurant"}
                </Button>
              ) : (
                <Button key="next" variant="primary" size="lg" type="button" onClick={next}>
                  Next: {PARTS[step + 1][0]} <ArrowRight size={18} />
                </Button>
              )}
            </div>
          </form>
        </Card>
        <Summary vals={vals} quote={quote} catalog={catalog} />
      </div>
    </Appear>
  );
}

/** The made-up owner password, with a button for a new one. */
function PasswordInput({ initial, onNew }: { initial: string; onNew: () => void }) {
  const ref = useRef<HTMLInputElement>(null);
  return (
    <span className="relative block">
      <input ref={ref} name="owner_password" required minLength={8} defaultValue={initial} className={`${inputCls} pr-12 font-mono`} />
      <span className="absolute right-1.5 top-1/2 -translate-y-1/2">
        <IconButton
          type="button"
          label="Make up a new password"
          variant="ghost"
          size={36}
          onClick={() => {
            if (ref.current) ref.current.value = randomPassword();
            onNew();
          }}
        >
          <RefreshCw size={16} />
        </IconButton>
      </span>
    </span>
  );
}

function WizardSteps({ at, onPick }: { at: number; onPick: (n: number) => void }) {
  return (
    <ol className="grid grid-cols-4 gap-2">
      {PARTS.map(([t], i) => (
        <li key={t}>
          <button type="button" onClick={() => onPick(i)} className="group flex w-full flex-col gap-2 text-left">
            <span className="h-1 overflow-hidden rounded-full bg-ink/[.07]">
              <motion.span className="block h-full rounded-full bg-accent" initial={false} animate={{ width: i <= at ? "100%" : "0%" }} transition={ease} />
            </span>
            <span className={`flex items-center gap-1.5 text-sm font-semibold transition ${i === at ? "text-ink" : i < at ? "text-ink/70" : "text-muted group-hover:text-ink"}`}>
              {i < at ? <Check size={14} strokeWidth={3} className="text-ok" /> : <span className="num text-muted">{i + 1}</span>}
              <span className={`truncate ${i === at ? "" : "hidden sm:inline"}`}>{t}</span>
            </span>
          </button>
        </li>
      ))}
    </ol>
  );
}

/** What is being created, updated as the form is filled in. */
function Summary({ vals, quote, catalog }: { vals: Vals; quote: Quote | null; catalog: Catalog }) {
  const name = vals.venue_name || vals.company_name || "";
  const plan = quote?.plan;
  const screens = plan ? Object.entries(plan.screens).filter(([, n]) => n > 0) : [];
  const flows = plan ? plan.flows.map((c) => catalog.flows.find((f) => f.code === c)?.name ?? c) : [];
  const kit = plan ? Object.values(plan.hardware).reduce((a, b) => a + b, 0) : 0;
  const Line = ({ k, children }: { k: string; children: ReactNode }) => (
    <div className="flex flex-col gap-0.5 border-t border-line py-3 first:border-0">
      <span className="text-xs font-medium text-muted">{k}</span>
      <span className="text-[15px]">{children}</span>
    </div>
  );
  const dash = <span className="text-muted">—</span>;
  return (
    <Card className="summary flex flex-col lg:sticky lg:top-0">
      <div className="flex items-center gap-3 pb-3">
        <span aria-hidden className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-ink/[.05] text-ink/60">
          <Store size={20} />
        </span>
        <div className="min-w-0">
          <div className="truncate font-bold">{name || <span className="text-muted">New restaurant</span>}</div>
          <div className="flex items-center gap-1.5 text-sm text-muted">
            {vals.venue_code ? <Badge>{vals.venue_code.toUpperCase()}</Badge> : null}
            <span className="truncate">{vals.company_name && vals.company_name !== name ? vals.company_name : vals.timezone}</span>
          </div>
        </div>
      </div>
      <Line k="Owner login">{vals.owner_email || dash}</Line>
      <Line k="Package">{plan ? planLabel(plan, catalog) : dash}</Line>
      {flows.length ? <Line k="How it works">{flows.join(", ")}</Line> : null}
      <Line k="Screens">
        {screens.length
          ? screens.map(([k, n]) => (
              <span key={k} className="flex justify-between gap-2">
                <span>{SCREEN_LABEL[k] ?? k}</span>
                <span className="num font-semibold">{n}</span>
              </span>
            ))
          : dash}
      </Line>
      {kit ? <Line k="Equipment">{kit} items</Line> : null}
      <div className="mt-1 grid grid-cols-2 gap-3 rounded-xl bg-ink/[.035] p-3.5">
        <div>
          <div className="text-xs text-muted">Monthly</div>
          <div className="num text-lg font-bold">{quote ? money(quote.monthly_total) : "—"}</div>
        </div>
        <div>
          <div className="text-xs text-muted">One-time</div>
          <div className="num text-lg font-bold">{quote ? money(quote.once_total) : "—"}</div>
        </div>
      </div>
    </Card>
  );
}

function Handover({ created, onClose, onBack }: { created: Created; onClose: () => void; onBack: () => void }) {
  const toast = useToast();
  const { tenant, email, password, pin } = created;
  const v = tenant.venues[0];
  const origin = appOrigin(); // the restaurant's address (the owner app), not our admin one
  const lines = [
    `${tenant.name}${v ? ` · ${v.name} (${v.code})` : ""}`,
    `Owner app: ${origin}${OWNER_APP(v?.code)}`,
    `Email: ${email}`,
    `Password: ${password}`,
    ...(pin ? [`Manager PIN for the POS: ${pin}`] : []),
  ];
  const Row = ({ k, children }: { k: string; children: ReactNode }) => (
    <div className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5 border-t border-line py-2.5 first:border-0">
      <span className="w-44 shrink-0 text-sm text-muted">{k}</span>
      <code className="font-mono text-[15px] font-semibold break-all">{children}</code>
    </div>
  );
  return (
    <Appear className="mx-auto w-full max-w-xl">
      <Card className="card handover p-8">
        <div className="flex flex-col items-center text-center">
          <motion.span initial={{ scale: 0.6, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} transition={{ type: "spring", stiffness: 380, damping: 22 }} className="grid h-14 w-14 place-items-center rounded-full bg-ok-soft text-ok">
            <CircleCheck size={30} />
          </motion.span>
          <h2 className="mt-4 text-2xl font-bold tracking-tight">{tenant.name} is ready</h2>
          <p className="mt-1 text-[15px] text-muted">Give the owner these. Next, our installer sets up each screen in the setup console.</p>
        </div>
        <div className="mt-6 rounded-xl bg-ink/[.035] px-4 py-1.5">
          <Row k="Owner app">
            {origin}
            {OWNER_APP(v?.code)}
          </Row>
          <Row k="Email">{email}</Row>
          <Row k="Password">{password}</Row>
          {pin ? <Row k="Manager PIN for the POS">{pin}</Row> : null}
        </div>
        <div className="mt-6 flex flex-col gap-2 sm:flex-row">
          <Button
            className="flex-1"
            onClick={() =>
              navigator.clipboard?.writeText(lines.join("\n")).then(
                () => toast("Copied", "ok"),
                () => toast("Could not copy. Select the text instead.", "bad"),
              )
            }
          >
            <Copy size={18} /> Copy for the owner
          </Button>
          {v ? (
            <a href={SETUP(v.id, v.code)} className="inline-flex h-11 flex-1 items-center justify-center gap-2 rounded-xl bg-ink px-5 font-semibold text-canvas transition hover:opacity-85 active:scale-[.97]">
              Open setup console <ArrowRight size={18} />
            </a>
          ) : null}
        </div>
        <div className="mt-3 flex justify-center gap-2">
          <Button variant="ghost" size="sm" onClick={onBack}>
            All restaurants
          </Button>
          <Button variant="ghost" size="sm" onClick={onClose}>
            Create another
          </Button>
        </div>
      </Card>
    </Appear>
  );
}

// ------------------------------------------------------------------ restaurant list

/** Desktop columns of the restaurant table (rows become cards on phones and tablets). */
const COLS = "lg:grid lg:grid-cols-[minmax(0,2.4fr)_minmax(0,1.5fr)_minmax(0,1.1fr)_minmax(0,1.2fr)_auto] lg:items-center lg:gap-5";

function Restaurants({ admin, catalog, tenants, q, refresh, onNew }: { admin: Admin; catalog: Catalog; tenants: Tenant[] | null; q: string; refresh: () => void; onNew: () => void }) {
  const [editing, setEditing] = useState<TenantVenue | null>(null);
  const [logins, setLogins] = useState<Tenant | null>(null);
  const toast = useToast();
  const needle = q.trim().toLowerCase();
  const shown = (tenants ?? []).filter(
    (t) => !needle || t.name.toLowerCase().includes(needle) || t.venues.some((v) => v.name.toLowerCase().includes(needle) || v.code.toLowerCase().includes(needle)) || t.admins.some((a) => a.email.includes(needle)),
  );
  const venues = (tenants ?? []).flatMap((t) => t.venues);
  const screens = venues.reduce((n, v) => n + v.screens, 0);
  const online = venues.reduce((n, v) => n + v.screens_online, 0);
  const ready = venues.filter((v) => v.setup?.ready).length;
  return (
    <section className="flex flex-col gap-5">
      {tenants ? (
        <div className="grid grid-cols-3 gap-3 sm:gap-4">
          <Stat icon={<Store size={18} />} label="Restaurants" value={venues.length} />
          <Stat icon={<Tablet size={18} />} label="Screens online" value={`${online}`} of={screens} />
          <Stat icon={<CircleCheck size={18} />} label="Ready to go live" value={ready} of={venues.length} />
        </div>
      ) : null}
      {!tenants ? (
        <div className="flex flex-col gap-3">
          <Skeleton className="h-24 rounded-2xl" />
          <Skeleton className="h-48 rounded-2xl" />
        </div>
      ) : !shown.length ? (
        <Card>
          <Empty icon={<Store size={24} />} action={tenants.length ? null : <Button variant="primary" onClick={onNew}><Plus size={18} /> New restaurant</Button>}>
            {tenants.length ? "No restaurant matches." : "No restaurants yet. Create the first one."}
          </Empty>
        </Card>
      ) : (
        <div className="restaurant-table flex flex-col gap-3 lg:gap-0 lg:divide-y lg:divide-line lg:rounded-2xl lg:bg-surface lg:shadow-soft">
          <div className={`hidden px-5 py-3 text-xs font-semibold text-muted ${COLS}`}>
            <span>Restaurant</span>
            <span>Package</span>
            <span>Screens</span>
            <span>Setup</span>
            <span className="w-[214px]" />
          </div>
          <AnimatePresence initial={false}>
            {shown.map((t) => (
              <motion.div
                key={t.id}
                data-tenant={t.id}
                className="card relative overflow-visible rounded-2xl bg-surface shadow-soft has-[.z-40]:z-20 lg:rounded-none lg:shadow-none"
                layout="position"
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                transition={ease}
              >
                <div className="flex items-center gap-2 border-b border-line py-2 pl-5 pr-3 lg:border-0 lg:bg-canvas/60">
                  <span className="min-w-0 flex-1 truncate text-[13px] font-semibold text-muted">{t.name}</span>
                  <span className="hidden text-xs text-muted sm:inline">since {new Date(t.created_at).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" })}</span>
                  <MoreMenu label={`More for ${t.name}`} items={[{ label: `Logins (${t.admins.length})`, icon: <KeyRound size={18} />, onClick: () => setLogins(t) }]} />
                </div>
                <div className="flex flex-col divide-y divide-line">
                  {t.venues.map((v) => (
                    <VenueRow key={v.id} v={v} catalog={catalog} onPlan={() => setEditing(v)} onCopy={() => navigator.clipboard?.writeText(location.origin + SETUP(v.id, v.code)).then(() => toast("Setup link copied", "ok"))} />
                  ))}
                </div>
              </motion.div>
            ))}
          </AnimatePresence>
        </div>
      )}
      {editing ? <ChangePlan admin={admin} catalog={catalog} venue={editing} onClose={() => setEditing(null)} onSaved={refresh} /> : null}
      <Modal open={!!logins} onClose={() => setLogins(null)} title={logins ? `Logins · ${logins.name}` : ""} footer={<Button variant="primary" className="w-full" onClick={() => setLogins(null)}>Done</Button>}>
        <div className="flex flex-col">
          {logins?.admins.length ? (
            logins.admins.map((a) => (
              <div key={a.email} className="flex items-center gap-3 border-t border-line py-3 first:border-0">
                <div className="min-w-0 flex-1">
                  <div className="truncate font-semibold">{a.email}</div>
                  <div className="text-sm capitalize text-muted">{a.role}</div>
                </div>
                <Status tone={a.is_active ? "ok" : "muted"}>{a.is_active ? "Active" : "Off"}</Status>
              </div>
            ))
          ) : (
            <p className="text-muted">No logins.</p>
          )}
        </div>
      </Modal>
    </section>
  );
}

/** A big number with its label (top of the restaurant list). */
function Stat({ icon, label, value, of }: { icon: ReactNode; label: string; value: ReactNode; of?: number }) {
  return (
    <Card className="flex min-w-0 flex-col gap-2 p-4 sm:flex-row sm:items-center sm:gap-4 sm:p-5">
      <span className="hidden h-11 w-11 shrink-0 place-items-center rounded-xl bg-accent-soft text-accent sm:grid">{icon}</span>
      <div className="min-w-0">
        <div className="num text-2xl font-bold leading-tight tracking-tight sm:text-[28px]">
          {value}
          {of !== undefined ? <span className="text-base font-semibold text-muted"> / {of}</span> : null}
        </div>
        <div className="text-[13px] leading-tight text-muted sm:truncate sm:text-sm">{label}</div>
      </div>
    </Card>
  );
}

function VenueRow({ v, catalog, onPlan, onCopy }: { v: TenantVenue; catalog: Catalog; onPlan: () => void; onCopy: () => void }) {
  const done = v.setup?.done ?? 0;
  const total = v.setup?.total ?? 0;
  const ready = !!v.setup?.ready;
  return (
    <div className={`venue-row flex flex-col gap-3 px-5 py-4 transition hover:bg-ink/[.015] ${COLS}`} data-venue={v.id}>
      <div className="flex min-w-0 items-center gap-3">
        <span aria-hidden className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-ink/[.05] text-ink/60">
          <Store size={20} />
        </span>
        <div className="min-w-0">
          <strong className="block truncate text-[16px] font-semibold">{v.name}</strong>
          <span className="flex items-center gap-1.5 text-sm text-muted">
            <Badge>{v.code}</Badge>
            <span className="truncate">{v.timezone}</span>
          </span>
        </div>
      </div>
      <div className="flex min-w-0 flex-wrap items-center gap-x-4 gap-y-1 text-sm lg:contents">
        <span className="min-w-0 truncate text-muted lg:text-[15px] lg:text-ink">{planLabel(v.plan, catalog)}</span>
        <Status tone={v.screens_online ? "ok" : "muted"}>
          <span>
            <span className="num">
              {v.screens_online} of {v.screens}
            </span>{" "}
            <span className="lg:hidden">screens </span>online
          </span>
        </Status>
      </div>
      <div className="flex min-w-0 flex-col gap-1.5" title={ready ? "Ready to go live" : `Setup ${done} of ${total}`}>
        <span className="flex items-center gap-1.5 text-sm font-medium">
          {ready ? (
            <>
              <Check size={15} strokeWidth={3} className="text-ok" /> Ready to go live
            </>
          ) : (
            <span className="text-muted">
              Setup <span className="num font-semibold text-ink">{done}</span> of {total || "?"}
            </span>
          )}
        </span>
        <span className="h-1.5 max-w-[220px] overflow-hidden rounded-full bg-ink/[.07]">
          <span className={`block h-full rounded-full ${ready ? "bg-ok" : "bg-accent"}`} style={{ width: `${(done / Math.max(1, total)) * 100}%` }} />
        </span>
      </div>
      <div className="flex shrink-0 items-center gap-1 lg:w-[214px] lg:justify-end">
        <a href={SETUP(v.id, v.code)} className="inline-flex h-10 flex-1 items-center justify-center gap-1.5 rounded-xl bg-surface px-4 text-sm font-semibold text-ink ring-1 ring-line transition hover:bg-ink/[.03] active:scale-[.97] lg:flex-none">
          Open setup console <ArrowUpRight size={16} />
        </a>
        <MoreMenu
          label={`More for ${v.name}`}
          items={[
            { label: "Change package", icon: <Package size={18} />, onClick: onPlan },
            { label: "Copy setup link", icon: <Link2 size={18} />, onClick: onCopy },
            { label: "Owner app", icon: <ArrowUpRight size={18} />, onClick: () => window.open(OWNER_APP(v.code), "_blank", "noreferrer") },
          ]}
        />
      </div>
    </div>
  );
}

function ChangePlan({ admin, catalog, venue, onClose, onSaved }: { admin: Admin; catalog: Catalog; venue: TenantVenue; onClose: () => void; onSaved: () => void }) {
  const toast = useToast();
  const plan = useRef<PlanValue | null>(null);
  const [slots, setSlots] = useState(true);
  const [busy, setBusy] = useState(false);
  const save = async () => {
    if (!plan.current) return;
    setBusy(true);
    try {
      const r = await admin.api<{ slots_created: string[] }>("PUT", `/v1/platform/venues/${venue.id}/plan`, { ...plan.current, create_slots: slots });
      toast(r.slots_created.length ? `Package saved. New screen slots: ${r.slots_created.join(", ")}` : "Package saved", "ok", 6000);
      onClose();
      onSaved();
    } catch (x) {
      toast((x as Error).message, "bad", 6000);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal
      open
      wide
      onClose={onClose}
      title={`Package · ${venue.name}`}
      footer={
        <div className="flex flex-wrap items-center gap-3">
          <label className="mr-auto flex items-center gap-2.5 text-sm font-medium">
            <input type="checkbox" className="h-5 w-5 accent-ink" checked={slots} onChange={(e) => setSlots(e.target.checked)} />
            Create missing screen slots
          </label>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="primary" disabled={busy} onClick={save}>
            Save package
          </Button>
        </div>
      }
    >
      <p className="mb-5 text-sm text-muted">Now: {planLabel(venue.plan, catalog)}. A new package applies its flows' settings and can add screen slots; it never removes screens.</p>
      <PlanPicker admin={admin} catalog={catalog} initial={venue.plan} onChange={(v) => (plan.current = v)} />
    </Modal>
  );
}
