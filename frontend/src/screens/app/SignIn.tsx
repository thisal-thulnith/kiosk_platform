// Screen sign-in, like Square device codes: the restaurant's address (/demo) + the screen's own code
// (K7MQ-4XPA-2R, from the Setup console). Used by the start page (/, /demo) and by every screen page
// that has no key yet (ui/gate.tsx). The old 6-digit one-time setup code still works in the same box.
import { AnimatePresence, motion } from "motion/react";
import { Globe, KeyRound, RefreshCw, ScanLine } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { cleanScreenCode, type SignedIn } from "../../lib/device";
import { features } from "../../lib/features";
import { ApiError } from "../../lib/net";
import { codeInAddress } from "../../lib/screens";
import { store } from "../../lib/store";
import type { Brand } from "../../lib/brand";
import { Button, spring } from "../../ui/kit";
import { Logo } from "../../ui/logo";

const LAST_VENUE = "kiosk:signin:venue";
const NOT_A_RESTAURANT = new Set(["static", "screens", "app", "platform", "setup", "owner", "menu", "wall", "pos", "waiter", "kitchen", "kiosk", "board", "table"]);

/** "K7MQ4XPA2R" -> "K7MQ-4XPA-2R" (a dash only once the next part has started). */
export function formatScreenCode(raw: string): string {
  const c = cleanScreenCode(raw).slice(0, 10);
  return [c.slice(0, 4), c.slice(4, 8), c.slice(8)].filter(Boolean).join("-");
}

const isOldCode = (c: string) => /^\d{6}$/.test(c);

/**
 * The restaurant this address belongs to: /demo (start page) or /demo/pos (a screen) -> "demo".
 * ?restaurant=demo works too (dev pages live under /static/...).
 */
export function venueInAddress(): string | null {
  const q = new URLSearchParams(location.search).get("restaurant");
  if (q) return q.toLowerCase();
  const parts = location.pathname.split("/").filter(Boolean);
  const first = parts.length === 1 ? parts[0].toLowerCase() : codeInAddress();
  return first && /^[a-z0-9-]{2,20}$/.test(first) && !NOT_A_RESTAURANT.has(first) ? first : null;
}

/** A short, clear sentence for a failed sign-in. */
export function signInError(x: unknown): string {
  const e = x as ApiError;
  if (e?.status === 429) return "Too many tries. Wait a minute, then try again.";
  if (e?.status === 404 && e.code !== "bad_screen_code") return "This server can't sign screens in with a screen code yet.";
  if (e?.code === "validation_error") return "Type the 10-character screen code.";
  return e?.message || "Could not sign in. Try again.";
}

/** One big box for the screen code, formatted XXXX-XXXX-XX as you type. */
export function ScreenCodeInput({ value, onChange, autoFocus = true }: { value: string; onChange: (v: string) => void; autoFocus?: boolean }) {
  return (
    <input
      name="code"
      aria-label="Screen code"
      placeholder="XXXX-XXXX-XX"
      autoFocus={autoFocus}
      autoCapitalize="characters"
      autoCorrect="off"
      autoComplete="off"
      spellCheck={false}
      enterKeyHint="go"
      maxLength={12}
      value={value}
      style={{ outline: "none" }} // the ring is the focus mark
      onChange={(e) => onChange(formatScreenCode(e.target.value))}
      className="h-[76px] w-full rounded-2xl bg-surface px-3 text-center font-mono text-[28px] font-bold uppercase tracking-[.1em] text-ink outline-none ring-1 ring-line transition placeholder:font-semibold placeholder:text-ink/20 hover:ring-ink/25 focus:ring-2 focus:ring-accent min-[400px]:text-[32px] min-[400px]:tracking-[.14em]"
    />
  );
}

type Props = {
  /** The restaurant from the address; null asks for it too. */
  venue: string | null;
  initialCode?: string;
  initialError?: string;
  /** Sign in with the screen code; the caller stores the key. */
  signIn: (venue: string, code: string) => Promise<SignedIn>;
  /** The old 6-digit one-time setup code (still accepted in the same box). */
  pair: (code: string) => Promise<SignedIn>;
  onSignedIn: (res: SignedIn) => void | Promise<void>;
};

/** Restaurant (only when the address doesn't say) + screen code + "Sign in". */
export function SignInForm({ venue, initialCode = "", initialError = "", signIn, pair, onSignedIn }: Props) {
  const [place, setPlace] = useState(() => venue ?? store.get<string>(LAST_VENUE) ?? "");
  const [code, setCode] = useState(() => formatScreenCode(initialCode));
  const [err, setErr] = useState(initialError);
  const [busy, setBusy] = useState(false);
  const host = location.host;

  const submit = async (form: HTMLFormElement) => {
    // Read the fields themselves: autofill, scanners and setup tools may fill them without typing.
    const data = new FormData(form);
    const typed = cleanScreenCode(String(data.get("code") ?? code));
    const where = (venue ?? String(data.get("venue") ?? place)).trim().toLowerCase().replace(/^.*\//, "");
    if (!isOldCode(typed) && typed.length !== 10) return setErr("Type the 10-character screen code.");
    if (!isOldCode(typed) && !where) return setErr("Type the restaurant's address.");
    setBusy(true);
    setErr("");
    try {
      const res = isOldCode(typed) ? await pair(typed) : await signIn(where, typed);
      if (!venue) store.set(LAST_VENUE, where);
      await onSignedIn(res);
    } catch (x) {
      setErr(signInError(x));
    } finally {
      setBusy(false);
    }
  };

  return (
    <form
      className="flex flex-col gap-4"
      onSubmit={(e) => {
        e.preventDefault();
        void submit(e.currentTarget);
      }}
    >
      {venue ? (
        <div className="mx-auto -mt-1 mb-1 inline-flex max-w-full items-center gap-1.5 rounded-full bg-canvas px-3 py-1.5 text-sm font-medium text-muted" data-venue={venue}>
          <Globe size={14} className="shrink-0" />
          <span className="truncate">
            {host}/<span className="font-semibold text-ink">{venue}</span>
          </span>
        </div>
      ) : (
        <label className="flex flex-col gap-1.5 text-left text-sm font-medium text-muted">
          Restaurant
          <span className="flex h-14 items-center rounded-2xl bg-surface pl-4 ring-1 ring-line transition hover:ring-ink/25 focus-within:ring-2 focus-within:ring-accent">
            <span className="shrink-0 text-[15px] text-muted">{host}/</span>
            <input
              name="venue"
              aria-label="Restaurant"
              autoFocus={!place}
              placeholder="your-restaurant"
              autoCapitalize="none"
              autoCorrect="off"
              spellCheck={false}
              value={place}
              style={{ outline: "none" }} // the box's ring is the focus mark
              onChange={(e) => (setPlace(e.target.value.replace(/\s/g, "").toLowerCase()), setErr(""))}
              className="h-full min-w-0 flex-1 bg-transparent pr-4 text-[17px] font-semibold text-ink outline-none placeholder:font-normal placeholder:text-ink/30"
            />
          </span>
        </label>
      )}
      <label className="flex flex-col gap-1.5 text-left text-sm font-medium text-muted">
        {venue ? <span className="sr-only">Screen code</span> : "Screen code"}
        <ScreenCodeInput value={code} autoFocus={!!venue || !!place} onChange={(v) => (setCode(v), setErr(""))} />
      </label>
      <AnimatePresence initial={false}>
        {err ? (
          <motion.p role="alert" initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }} className="rounded-xl bg-bad-soft px-4 py-3 text-center text-sm font-semibold text-bad">
            {err}
          </motion.p>
        ) : null}
      </AnimatePresence>
      <Button variant="primary" size="lg" type="submit" disabled={busy} className="mt-1 w-full">
        {busy ? "Signing in…" : "Sign in"}
      </Button>
    </form>
  );
}

/** The face of a screen sign-in. With the steps (the start page and screens without a key): a dark
 *  panel that explains setting up a tablet once, the form beside it (under it on phones). Without:
 *  one white card in the middle. Used by the start page (/, /demo) and by ui/gate.tsx. */
export function SignInFace({ title, sub, children, hint = true, name, logo }: { title: ReactNode; sub?: ReactNode; children: ReactNode; hint?: boolean; name?: string | null; logo?: string | null }) {
  const brand = store.get<Brand>("kiosk:brand");
  const shown = name ?? brand?.name ?? null;
  const [admin, setAdmin] = useState<string | null>(null);
  useEffect(() => {
    void features().then((f) => setAdmin(f.admin_url ?? null));
  }, []);
  const card = (
    <motion.div className="w-full max-w-[440px]" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={spring}>
      <div className="rounded-3xl bg-surface p-6 shadow-soft sm:p-8">
        <div className="flex flex-col items-center text-center">
          <Logo url={logo ?? brand?.logo_url} name={shown ?? "Restaurant"} size={56} />
          {shown ? <div className="mt-3 text-[15px] font-semibold text-muted">{shown}</div> : null}
          <h1 className={`${shown ? "mt-1" : "mt-5"} text-[26px] font-bold leading-tight tracking-tight sm:text-[28px]`}>{title}</h1>
          {sub ? <p className="mt-1.5 text-[15px] text-muted">{sub}</p> : null}
        </div>
        <div className="mt-7">{children}</div>
      </div>
      {admin ? (
        <p className="mt-5 text-center text-sm text-muted">
          Owner or manager?{" "}
          <a className="font-semibold text-accent hover:underline" href={admin}>
            Log in at {admin.replace(/^https?:\/\//, "")}
          </a>
        </p>
      ) : null}
    </motion.div>
  );
  if (!hint) return <div className="flex min-h-full flex-col items-center justify-center bg-canvas px-4 py-8 sm:p-8">{card}</div>;
  return (
    <div className="flex min-h-full flex-col bg-canvas md:flex-row">
      <SetupOnce />
      <div className="flex flex-1 flex-col items-center justify-center px-4 py-8 sm:p-8">{card}</div>
    </div>
  );
}

const STEPS: [typeof KeyRound, string, string][] = [
  [KeyRound, "Get the codes", "Whoever set up your restaurant adds this screen in the Setup console (Screens → Add screen). It shows the restaurant, a screen code and a QR."],
  [ScanLine, "Sign in once", "Type the restaurant and the screen code here, or scan the QR with this tablet's camera."],
  [RefreshCw, "Done for good", "It opens by itself after restarts and power cuts. Staff then log in with their own PIN."],
];

/** Setting up a tablet, in three steps: a dark panel on the left (on top on phones). */
function SetupOnce() {
  return (
    <section aria-label="How to set up this screen" className="relative bg-[#1c2b33] px-6 py-8 text-white sm:px-10 md:flex md:w-[42%] md:max-w-[620px] md:flex-col md:justify-center md:py-12">
      <h2 className="text-[26px] font-bold leading-tight tracking-[-0.02em] lg:text-[34px]">Set up this screen once</h2>
      <p className="mt-2 max-w-[42ch] text-[15px] text-white/70">POS, waiter, kitchen or table: the code decides what this tablet becomes.</p>
      <ol className="mt-7 hidden flex-col gap-6 md:flex">
        {STEPS.map(([Icon, head, line], i) => (
          <li key={head} className="flex gap-4">
            <span className="relative grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-white/[.08]">
              <Icon size={20} />
              <span className="num absolute -right-1.5 -top-1.5 grid h-5 w-5 place-items-center rounded-full bg-[#0866ff] text-[11px] font-bold">{i + 1}</span>
            </span>
            <span>
              <span className="block font-semibold">{head}</span>
              <span className="mt-0.5 block text-[15px] leading-snug text-white/70">{line}</span>
            </span>
          </li>
        ))}
      </ol>
    </section>
  );
}
