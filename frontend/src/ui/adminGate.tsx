// Login for the consoles, then the restaurant picker. One login screen for everyone (a dark ink panel
// with the product, the form beside it); the account decides which console opens. Our team's
// accounts add a phone code (2-step).
// Demo logins from `kiosk seed` are filled in on a development server only.
import { motion } from "motion/react";
import { ChevronDown, ShieldCheck, Store, Tablet } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { QRCodeSVG } from "qrcode.react";
import { Admin, HOME, type AdminKind, type LoginStep } from "../lib/admin";
import { features } from "../lib/features";
import { applyBrand, brandOf } from "../lib/brand";
import { Appear, Button, Card, Field, Input, Skeleton, spring } from "./kit";
import { Logo } from "./logo";

const DEMO: Record<AdminKind, [string, string]> = { installer: ["platform@kiosk.lk", "platform12345"], admin: ["admin@demo.lk", "admin12345"] };

export function AdminGate({ kind, title, needVenue = true, children }: { kind: AdminKind; title: string; needVenue?: boolean; children: (admin: Admin) => ReactNode }) {
  const [admin] = useState(() => new Admin(kind));
  const [state, setState] = useState<"login" | "loading" | "ready" | "error">(admin.token ? "loading" : "login");
  const [err, setErr] = useState("");
  useEffect(() => {
    document.title = title;
  }, [title]);
  const load = async () => {
    setState("loading");
    try {
      await features(); // addresses for links and QR codes (restaurant vs admin address)
      if (needVenue) {
        await admin.loadVenues();
        if (!admin.venue) throw new Error("This account has no restaurants yet.");
        const brand = brandOf(admin.venue.settings);
        applyBrand(brand, false); // the console wears the restaurant's colours
      }
      setState("ready");
    } catch (e) {
      setErr((e as Error).message);
      setState(admin.token ? "error" : "login");
    }
  };
  useEffect(() => {
    if (admin.token) void load();
  }, []);
  if (state === "ready") return <>{children(admin)}</>;
  if (state === "loading") return <ConsoleSkeleton />;
  if (state === "error")
    return (
      <div className="grid min-h-full place-items-center bg-canvas p-6">
        <Appear>
          <Card className="w-full max-w-sm p-8 text-center">
            <p className="font-semibold text-bad">{err}</p>
            <Button className="mt-5" onClick={() => (admin.logout(), location.reload())}>
              Log in again
            </Button>
          </Card>
        </Appear>
      </div>
    );
  // The account decides the console: the other kind opens its own (a restaurant owner who logged in
  // on the Platform address goes to the Owner app, and our team the other way).
  return <Login admin={admin} err={err} onDone={(k) => (k === kind ? void load() : location.assign(HOME[k]))} />;
}

/** Grey shapes of a console (rail, top bar, cards) while it loads. */
function ConsoleSkeleton() {
  return (
    <div className="flex h-full bg-canvas" aria-busy="true">
      <aside className="hidden w-[76px] shrink-0 flex-col gap-3 border-r border-line bg-surface p-4 md:flex xl:w-[248px]">
        <Skeleton className="h-9 w-9 rounded-xl" />
        <div className="mt-4 flex flex-col gap-2">
          {Array.from({ length: 6 }, (_, i) => (
            <Skeleton key={i} className="h-9 rounded-xl" />
          ))}
        </div>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex h-16 items-center gap-3 border-b border-line bg-surface px-4 sm:px-6">
          <Skeleton className="h-5 w-48 rounded-full" />
        </div>
        <div className="grid gap-4 p-4 sm:p-6 lg:grid-cols-2">
          <Skeleton className="h-56 rounded-2xl" />
          <Skeleton className="h-56 rounded-2xl" />
          <Skeleton className="h-36 rounded-2xl lg:col-span-2" />
        </div>
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ the login (everyone)

/** Password, then (our team) the phone code, or its one-time setup from a QR code. */
function LoginForm({ admin, err: first, onDone }: { admin: Admin; err: string; onDone: (kind: AdminKind) => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [otp, setOtp] = useState("");
  const [step, setStep] = useState<LoginStep | null>(null);
  const [ready, setReady] = useState(false);
  useEffect(() => {
    void features().then((f) => {
      setReady(true);
      if (!f.demo) return;
      setEmail((e) => e || DEMO[admin.kind][0]);
      setPassword((p) => p || DEMO[admin.kind][1]);
    });
  }, []);
  const [err, setErr] = useState(first);
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    setBusy(true);
    setErr("");
    try {
      const next = step?.need === "setup" ? await admin.finishTwoStep(step.setup_token, otp) : await admin.login(email, password, step?.need === "otp" ? otp : undefined);
      if (next.need === "done") return onDone(next.kind);
      setOtp("");
      setStep(next);
    } catch (x) {
      setErr((x as Error).message);
      setOtp("");
    } finally {
      setBusy(false);
    }
  };
  const code = step && step.need !== "done";
  return (
    <form
      className="flex flex-col gap-4"
      onSubmit={(e) => {
        e.preventDefault();
        void submit();
      }}
    >
      {!code ? (
        <>
          <Field label="Email">
            <Input aria-label="Email" type="email" autoComplete="username" placeholder="name@company.lk" value={email} onChange={(e) => setEmail(e.target.value)} />
          </Field>
          <Field label="Password">
            <Input aria-label="Password" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
          </Field>
        </>
      ) : (
        <>
          {step.need === "setup" ? <TwoStepSetup secret={step.secret} uri={step.uri} /> : <p className="text-[15px] text-muted">Open your authenticator app and type the 6-digit code for {email}.</p>}
          <Field label="Code">
            <Input aria-label="Code" autoFocus inputMode="numeric" autoComplete="one-time-code" maxLength={7} placeholder="123 456" value={otp} onChange={(e) => setOtp(e.target.value.replace(/[^0-9 ]/g, ""))} className="text-center text-2xl font-semibold tracking-[.3em]" />
          </Field>
        </>
      )}
      {err ? (
        <p role="alert" className="flex items-center gap-2 rounded-xl bg-bad-soft px-3.5 py-2.5 text-sm font-medium text-bad">
          <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-bad" />
          {err}
        </p>
      ) : null}
      <Button variant="primary" size="lg" type="submit" disabled={busy || !ready || (code ? otp.replace(/ /g, "").length !== 6 : !email || !password)} className="mt-2 w-full">
        {step?.need === "setup" ? "Turn on and log in" : code ? "Continue" : "Log in"}
      </Button>
      {code ? (
        <button type="button" className="text-sm font-semibold text-muted hover:text-ink" onClick={() => (setStep(null), setOtp(""), setErr(""))}>
          Back
        </button>
      ) : null}
    </form>
  );
}

/** First login of a team account: add it to an authenticator app from the QR code. */
function TwoStepSetup({ secret, uri }: { secret: string; uri: string }) {
  return (
    <div className="flex flex-col gap-4">
      <p className="text-[15px] text-muted">Team accounts need a phone code. Scan this with Google Authenticator, Microsoft Authenticator or 1Password, then type the code it shows.</p>
      <div className="flex items-center gap-4 rounded-2xl border border-line p-4">
        <span className="shrink-0 rounded-xl bg-white p-2">
          <QRCodeSVG value={uri} size={132} />
        </span>
        <div className="min-w-0 text-[13px] text-muted">
          Can't scan? Enter this key:
          <div className="mt-1 break-all font-mono text-[13px] font-semibold text-ink">{secret.match(/.{1,4}/g)?.join(" ")}</div>
        </div>
      </div>
    </div>
  );
}

/** Logins are always light (a restaurant may have chosen dark screens for its guests). */
function useLight() {
  useEffect(() => {
    document.documentElement.dataset.theme = "light";
  }, []);
}

/** The product's own mark: a white tile with the blue grid (never a restaurant's logo). */
export function ProductMark({ size = 36 }: { size?: number }) {
  return (
    <span className="grid shrink-0 place-items-center rounded-xl bg-[#0866ff] text-white" style={{ width: size, height: size }} aria-hidden>
      <svg viewBox="0 0 24 24" width={size * 0.56} height={size * 0.56} fill="currentColor">
        <rect x="3" y="3" width="8" height="8" rx="2" />
        <rect x="13" y="3" width="8" height="8" rx="2" opacity=".55" />
        <rect x="3" y="13" width="8" height="8" rx="2" opacity=".55" />
        <rect x="13" y="13" width="8" height="8" rx="2" />
      </svg>
    </span>
  );
}

const LINES: [typeof Store, string][] = [
  [Store, "Sales, menu, staff and tables of your restaurant"],
  [Tablet, "Every screen signed in with a short code"],
  [ShieldCheck, "Your data kept private to your restaurant"],
];

/** The one login screen: a dark ink panel with the product, and the form. Every account uses it;
 *  after login the account opens its own console (our team: Platform, a restaurant: Owner app). */
function Login({ admin, err, onDone }: { admin: Admin; err: string; onDone: (kind: AdminKind) => void }) {
  useLight();
  return (
    <div className="login flex min-h-full flex-col bg-surface md:flex-row">
      {/* The ink panel: a band on top on phones, the left half on bigger screens. */}
      <section className="relative overflow-hidden bg-[#1c2b33] text-white md:flex md:w-[46%] md:max-w-[760px] md:flex-col">
        <Pattern />
        <div className="relative flex items-center gap-3 px-6 pt-6 sm:px-10 md:pt-10">
          <ProductMark />
          <span className="text-[17px] font-bold tracking-tight">Kiosk Platform</span>
        </div>
        <div className="relative px-6 pb-8 pt-8 sm:px-10 md:my-auto md:pb-10">
          <h2 className="max-w-[15ch] text-[28px] font-bold leading-[1.1] tracking-[-0.02em] sm:text-[34px] lg:text-[44px]">Run your restaurant from anywhere</h2>
          <ul className="mt-8 hidden flex-col gap-4 md:flex">
            {LINES.map(([Icon, line]) => (
              <li key={line} className="flex items-center gap-3.5 text-[15px] text-white/80">
                <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-white/[.08] text-white">
                  <Icon size={19} />
                </span>
                {line}
              </li>
            ))}
          </ul>
        </div>
        <div className="relative hidden px-10 pb-8 text-[13px] text-white/45 md:block">For restaurant owners and managers, and our team</div>
      </section>

      {/* The form. */}
      <section className="flex flex-1 items-start justify-center px-6 py-10 sm:px-10 md:items-center">
        <motion.div className="w-full max-w-[400px]" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={spring}>
          <h1 className="text-[28px] font-bold leading-tight tracking-tight sm:text-[32px]">Log in</h1>
          <p className="mb-8 mt-1 text-[15px] text-muted">With the email and password you were given.</p>
          <LoginForm admin={admin} err={err} onDone={onDone} />
        </motion.div>
      </section>
    </div>
  );
}

/** A quiet geometric pattern on the ink panel: a fine dot grid and a few large rings. */
function Pattern() {
  return (
    <svg aria-hidden className="pointer-events-none absolute inset-0 h-full w-full" preserveAspectRatio="xMidYMid slice">
      <defs>
        <pattern id="team-dots" width="24" height="24" patternUnits="userSpaceOnUse">
          <circle cx="2" cy="2" r="1" fill="white" opacity=".09" />
        </pattern>
        <linearGradient id="team-fade" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="white" stopOpacity="1" />
          <stop offset="1" stopColor="white" stopOpacity="0" />
        </linearGradient>
        <mask id="team-mask">
          <rect width="100%" height="100%" fill="url(#team-fade)" />
        </mask>
      </defs>
      <rect width="100%" height="100%" fill="url(#team-dots)" mask="url(#team-mask)" />
      <g fill="none" stroke="white" strokeOpacity=".07" strokeWidth="1.5">
        <circle cx="100%" cy="100%" r="180" />
        <circle cx="100%" cy="100%" r="300" />
        <circle cx="100%" cy="100%" r="420" />
      </g>
      <circle cx="100%" cy="100%" r="180" fill="#0866ff" fillOpacity=".14" />
    </svg>
  );
}

/** Restaurant picker for the console header (nothing when the login has one restaurant). */
export function VenuePicker({ admin }: { admin: Admin }) {
  if (admin.venues.length < 2) return null;
  return (
    <span className="relative inline-flex">
      <select
        aria-label="Venue"
        value={admin.venue?.id}
        onChange={(e) => admin.chooseVenue(e.target.value)}
        className="h-10 max-w-[15rem] appearance-none truncate rounded-full border-0 bg-ink/[.05] pl-4 pr-9 text-sm font-semibold text-ink outline-none transition hover:bg-ink/[.08] focus:bg-surface focus:ring-2 focus:ring-accent"
      >
        {admin.venues.map((v) => (
          <option key={v.id} value={v.id}>
            {v.name} ({v.code}){v.tenant_name && v.tenant_name !== v.name ? ` · ${v.tenant_name}` : ""}
          </option>
        ))}
      </select>
      <ChevronDown size={16} className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-muted" />
    </span>
  );
}

// ------------------------------------------------------------------ the consoles' shared header

/** A link in the console header (Menu, Owner app…): quiet until hovered. */
export const HEADER_LINK = "inline-flex h-10 items-center gap-1.5 rounded-full px-3.5 text-sm font-semibold text-muted transition hover:bg-ink/[.05] hover:text-ink active:scale-[.97]";

/** Header for every console (white bar, hairline below): logo mark + name, a few links, then optional tabs. */
export function ConsoleHeader({ title, sub, logo, actions, children, width = "max-w-6xl" }: { title: ReactNode; sub?: ReactNode; logo: { url?: string | null; name: string }; actions?: ReactNode; children?: ReactNode; width?: string }) {
  return (
    <header className="sticky top-0 z-30 border-b border-line bg-surface">
      <div className={`mx-auto flex ${width} min-h-16 flex-wrap items-center gap-3 px-4 py-2.5 sm:px-6`}>
        <Logo url={logo.url} name={logo.name} size={36} />
        <div className="min-w-[140px] flex-1">
          <div className="truncate text-base font-bold leading-tight tracking-tight">{title}</div>
          {sub ? <div className="truncate text-[13px] text-muted">{sub}</div> : null}
        </div>
        <div className="flex flex-wrap items-center gap-1">{actions}</div>
      </div>
      {children ? <div className={`mx-auto ${width} px-4 pb-2 sm:px-6`}>{children}</div> : null}
    </header>
  );
}

/** Pill tabs, the current one in the selection blue (v4), scrolling sideways on a phone. */
export function PillTabs<T extends string>({ value, onChange, tabs, label }: { value: T; onChange: (v: T) => void; tabs: [T, ReactNode][]; label: string }) {
  return (
    <nav aria-label={label} className="-mx-1 flex gap-1 overflow-x-auto px-1 py-1 [scrollbar-width:none]">
      {tabs.map(([k, name]) => (
        <button key={k} onClick={() => onChange(k)} aria-current={value === k ? "page" : undefined} className={`relative h-10 shrink-0 rounded-full px-4 text-sm font-semibold transition-colors ${value === k ? "text-accent" : "text-muted hover:bg-ink/[.04] hover:text-ink"}`}>
          {value === k ? <motion.span layoutId={`pill-${label}`} transition={spring} className="absolute inset-0 rounded-full bg-accent-soft" /> : null}
          <span className="relative inline-flex items-center gap-1.5">{name}</span>
        </button>
      ))}
    </nav>
  );
}
