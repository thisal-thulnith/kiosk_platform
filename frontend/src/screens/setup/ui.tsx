// Small building blocks for the Setup console: form fields, card headers, a status dot, and the
// shared context (login, screens, network, checklist) every step's cards read from.
import { Check as CheckIcon } from "lucide-react";
import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import type { Admin } from "../../lib/admin";
import { Card, inputCls, Skeleton, Status as KitStatus, useToast } from "../../ui/kit";

// ------------------------------------------------------------------ data shapes (what the API returns)

export type Client = { install_id?: string; app?: "web" | "android"; app_version?: string; model?: string; os?: string; browser?: string; screen?: string; page?: string; ip?: string; paired_at?: string };
export type DeviceRow = {
  id: string;
  type: string;
  name: string;
  station: string | null;
  table_ref: string | null;
  paired: boolean;
  is_active: boolean;
  last_seen_at: string | null;
  connected: boolean;
  card: { mode: "reader" | "softpos"; terminal_id?: string } | null;
  hardware: { model: string; name: string } | null;
  menu_categories: string[];
  client?: Client | null;
  same_tablet_as?: string[];
  /** Sign-in: the restaurant's address + this code, e.g. "K7MQ-4XPA-2R" (like a Square device code). */
  screen_code?: string;
  pairing_code?: string;
  pairing_expires_at?: string;
};
export type Hub = { alive: boolean; catching_up?: boolean; lan_url: string | null; last_seen_at: string | null; pending: number; open_orders?: number; software?: string };
export type NetworkInfo = { mode: "cloud" | "hybrid"; hub: Hub | null; setup_code_active?: boolean; in_charge: "hub" | "cloud" };
export type CheckItem = { key: string; title: string; done: boolean; detail: string; where: string };
export type Checklist = { ready: boolean; done: number; total: number; items: CheckItem[] };
export type Code = { code: string; expires: string };

// ------------------------------------------------------------------ context

export type SetupState = {
  admin: Admin;
  devices: DeviceRow[];
  stations: string[];
  network: NetworkInfo | null;
  setNetwork: (n: NetworkInfo) => void;
  checklist: Checklist | null;
  codes: Record<string, Code>;
  rememberCode: (id: string, c: Code) => void;
  refreshDevices: () => Promise<void>;
  /** Something changed that the go-live checklist counts: reload it (and the cards that poll). */
  changed: () => void;
  /** Goes up every few seconds and after each change: cards reload on it. */
  tick: number;
  /** The old 6-digit one-time setup code (fallback). */
  showCode: (d: DeviceRow, code: string, expires?: string) => void;
  /** How to sign a tablet in on this screen: its screen code, the address and the QR. */
  showSignIn: (d: DeviceRow) => void;
};
export const SetupCtx = createContext<SetupState>(null as unknown as SetupState);
export const useSetup = () => useContext(SetupCtx);

/** Is this go-live check (by key) still open? */
export function useOpen(...keys: string[]): boolean {
  const { checklist } = useSetup();
  return !!checklist?.items.some((i) => keys.includes(i.key) && !i.done);
}

/** The API says "LankaQR"; the people in the restaurant know it as QR payment. */
export const say = (s: string | null | undefined): string => (s ?? "").replace(/LankaQR/g, "QR payment").replace(/SoftPOS/g, "tap on phone");

/** Run an action, toast the result; returns null when it failed. */
export function useAct() {
  const toast = useToast();
  return useCallback(
    async <T,>(fn: () => Promise<T>, ok?: string | null): Promise<T | null> => {
      try {
        const r = await fn();
        if (ok) toast(ok, "ok");
        return r;
      } catch (x) {
        toast(say((x as Error).message), "bad", 6000);
        return null;
      }
    },
    [toast],
  );
}

/** Load something from the API, again on every `tick` (skipped while a dialog is open). */
export function useLoad<T>(fn: () => Promise<T>, deps: unknown[] = []): [T | null, () => Promise<void>, string] {
  const { tick } = useSetup();
  const [data, setData] = useState<T | null>(null);
  const [err, setErr] = useState("");
  const fnRef = useRef(fn);
  fnRef.current = fn;
  const load = useCallback(async () => {
    try {
      setData(await fnRef.current());
      setErr("");
    } catch (x) {
      setErr(say((x as Error).message));
    }
  }, []);
  const first = useRef(true);
  useEffect(() => {
    if (!first.current && document.querySelector("[role=dialog]")) return;
    first.current = false;
    void load();
  }, [tick, ...deps]);
  return [data, load, err];
}

// ------------------------------------------------------------------ layout

/** A card with a title row: title (+ small badge) on the left, the action on the right. */
export function Section({ id, title, badge, action, about, children, className = "" }: { id?: string; title: ReactNode; badge?: ReactNode; action?: ReactNode; about?: ReactNode; children?: ReactNode; className?: string }) {
  return (
    <Card id={id} className={`flex flex-col gap-4 ${className}`}>
      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <h2 className="flex flex-wrap items-center gap-2 text-lg font-bold tracking-tight">
            {title}
            {badge}
          </h2>
          {about ? <p className="mt-0.5 text-sm text-muted">{about}</p> : null}
        </div>
        {action ? <div className="shrink-0">{action}</div> : null}
      </div>
      {children}
    </Card>
  );
}

/** A card that is still loading (or failed to load). */
export function Loading({ id, title, err }: { id?: string; title: ReactNode; err?: string }) {
  return (
    <Section id={id} title={title} about={err || undefined}>
      {err ? null : (
        <div className="flex flex-col gap-2">
          <Skeleton className="h-12" />
          <Skeleton className="h-12 w-2/3" />
        </div>
      )}
    </Section>
  );
}

/** A quiet list row (inside a card; the list draws hairlines between rows). */
export function Row({ children, className = "", ...p }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div {...p} className={`flex flex-wrap items-center gap-3 px-3 py-3.5 transition hover:bg-ink/[.02] ${className}`}>
      {children}
    </div>
  );
}

/** Round icon at the start of a row. */
export function Lead({ children, tone = "muted" }: { children: ReactNode; tone?: "muted" | "ok" | "brand" }) {
  const c = { muted: "bg-ink/[.05] text-ink/70", ok: "bg-ok-soft text-ok", brand: "bg-ink text-canvas" }[tone];
  return <span className={`grid h-10 w-10 shrink-0 place-items-center rounded-full ${c}`}>{children}</span>;
}

/** A small warning line with a dot, inside a row. */
export function WarnLine({ children, tone = "warn" }: { children: ReactNode; tone?: "warn" | "bad" }) {
  return (
    <span role="alert" className={`flex items-start gap-1.5 text-sm font-medium ${tone === "bad" ? "text-bad" : "text-warn"}`}>
      <span className={`mt-[7px] h-1.5 w-1.5 shrink-0 rounded-full ${tone === "bad" ? "bg-bad" : "bg-warn"}`} />
      {children}
    </span>
  );
}

const INPUT = `${inputCls} disabled:bg-canvas`;
/** Links that look like the kit's Buttons (sm / md, default and primary). */
export const LINK_SM = "inline-flex h-9 items-center justify-center gap-1.5 rounded-lg bg-surface px-3.5 text-sm font-semibold text-ink ring-1 ring-line transition hover:bg-ink/[.03] active:scale-[.97]";
export const LINK_MD = "inline-flex h-11 items-center justify-center gap-2 rounded-xl bg-surface px-4 text-[15px] font-semibold text-ink ring-1 ring-line transition hover:bg-ink/[.03] active:scale-[.97]";
export const LINK_PRIMARY = "inline-flex h-11 items-center justify-center gap-2 rounded-xl bg-ink px-5 text-[15px] font-semibold text-canvas transition hover:opacity-85 active:scale-[.97]";

export function Field({ label, children, className = "" }: { label: ReactNode; children: ReactNode; className?: string }) {
  return (
    <label className={`flex min-w-0 flex-col gap-1.5 text-sm font-medium text-muted ${className}`}>
      {label}
      {children}
    </label>
  );
}

export function Input({ className = "", ...p }: React.InputHTMLAttributes<HTMLInputElement>) {
  return <input {...p} className={`${INPUT} ${className}`} />;
}

export function Select({ className = "", ...p }: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return <select {...p} className={`${INPUT} ${className}`} />;
}

export function Check({ checked, onChange, children, className = "", ...p }: { checked: boolean; onChange: (v: boolean) => void; children: ReactNode; className?: string } & Omit<React.InputHTMLAttributes<HTMLInputElement>, "onChange" | "checked">) {
  return (
    <label className={`inline-flex cursor-pointer items-center gap-2.5 text-[15px] font-medium ${className}`}>
      <input type="checkbox" {...p} checked={checked} onChange={(e) => onChange(e.target.checked)} className="h-5 w-5 shrink-0 accent-ink" />
      {children}
    </label>
  );
}

export function Dot({ tone }: { tone: "ok" | "bad" | "warn" | "muted" }) {
  const c = { ok: "bg-ok", bad: "bg-bad", warn: "bg-warn", muted: "bg-muted/50" }[tone];
  return <span aria-hidden className={`inline-block h-2 w-2 shrink-0 rounded-full ${c}`} />;
}

/** A dot + word ("Online", "Not tested"). */
export function Status({ tone, children }: { tone: "ok" | "warn" | "bad" | "info" | "muted"; children: ReactNode }) {
  return <KitStatus tone={tone}>{children}</KitStatus>;
}

/** A numbered how-to list. */
export function Steps({ children }: { children: ReactNode }) {
  return <ol className="flex list-decimal flex-col gap-2 pl-5 text-[15px] marker:font-semibold marker:text-muted">{children}</ol>;
}

export function Code({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <code className={`rounded-lg bg-ink/[.05] px-1.5 py-0.5 font-mono text-[13px] break-all ${className}`}>{children}</code>;
}

/** A tappable choice (connection type, hardware model). */
export function Choice({ on, icon, title, about, onClick, ...p }: { on?: boolean; icon: ReactNode; title: ReactNode; about?: ReactNode; onClick: () => void } & Omit<React.ButtonHTMLAttributes<HTMLButtonElement>, "title" | "onClick">) {
  return (
    <button {...p} type="button" onClick={onClick} className={`choice flex w-full items-center gap-3 rounded-2xl p-3.5 text-left transition active:scale-[.99] ${on ? "on bg-surface ring-2 ring-ink" : "bg-surface ring-1 ring-line hover:bg-ink/[.02]"}`}>
      <span className={`grid h-10 w-10 shrink-0 place-items-center rounded-full ${on ? "bg-ink text-canvas" : "bg-ink/[.05] text-ink/70"}`}>{icon}</span>
      <span className="flex min-w-0 flex-1 flex-col">
        <strong className="text-[15px] font-semibold">{title}</strong>
        {about ? <span className="text-sm text-muted">{about}</span> : null}
      </span>
      {on ? <CheckIcon size={18} strokeWidth={2.5} className="shrink-0 text-ink" /> : null}
    </button>
  );
}

export const copy = (text: string, toast: (t: string, tone?: "ok" | "bad" | "info") => void) =>
  navigator.clipboard?.writeText(text).then(
    () => toast("Copied", "ok"),
    () => toast("Could not copy", "bad"),
  );
