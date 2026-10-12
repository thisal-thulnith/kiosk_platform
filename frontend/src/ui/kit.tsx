// The building blocks every screen uses. Simple and calm: one main action per view, the rest quiet;
// big touch targets; soft motion that follows the system's "reduce motion" setting.
import { AnimatePresence, motion, MotionConfig } from "motion/react";
import { MoreHorizontal, X } from "lucide-react";
import { createContext, useCallback, useContext, useEffect, useId, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { net } from "../lib/net";

export const spring = { type: "spring", stiffness: 420, damping: 36, mass: 0.8 } as const;
export const ease = { duration: 0.22, ease: [0.22, 1, 0.36, 1] } as const;

// ------------------------------------------------------------------ buttons

type Variant = "primary" | "brand" | "default" | "ok" | "danger" | "ghost" | "dark" | "soft";
// Uber / PickMe style: the main action is black; the restaurant's colour is an accent, not a fill.
const VARIANT: Record<Variant, string> = {
  primary: "bg-ink text-white hover:bg-ink/90",
  dark: "bg-ink text-white hover:bg-ink/90",
  brand: "bg-brand text-on-brand hover:bg-brand-dark",
  default: "bg-surface text-ink ring-1 ring-line hover:bg-canvas",
  soft: "bg-canvas text-ink hover:bg-line",
  ok: "bg-ok text-white hover:brightness-95",
  danger: "bg-bad-soft text-bad hover:bg-bad hover:text-white",
  ghost: "bg-transparent text-ink/70 hover:text-ink hover:bg-ink/[.05]",
};
const SIZE = { sm: "h-9 px-3.5 text-sm rounded-lg gap-1.5", md: "h-11 px-4 text-[15px] rounded-xl gap-2", lg: "h-14 px-6 text-base rounded-xl gap-2", xl: "h-16 px-8 text-lg rounded-2xl gap-2.5" };

export function Button({ variant = "default", size = "md", className = "", ...p }: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: keyof typeof SIZE }) {
  return <button {...p} className={`inline-flex select-none items-center justify-center font-semibold transition duration-150 active:scale-[.97] disabled:pointer-events-none disabled:opacity-40 disabled:shadow-none ${VARIANT[variant]} ${SIZE[size]} ${className}`} />;
}

/** A round icon-only button (with a label for screen readers and tooltips). */
export function IconButton({ label, children, variant = "soft", size = 40, className = "", ...p }: React.ButtonHTMLAttributes<HTMLButtonElement> & { label: string; variant?: Variant; size?: number }) {
  return (
    <button {...p} aria-label={label} title={label} className={`inline-grid shrink-0 place-items-center rounded-full transition active:scale-95 disabled:opacity-40 ${VARIANT[variant]} ${className}`} style={{ width: size, height: size }}>
      {children}
    </button>
  );
}

// ------------------------------------------------------------------ small things

type Tone = "ok" | "warn" | "bad" | "info" | "muted" | "brand";
const TONE: Record<Tone, string> = {
  ok: "bg-ok-soft text-ok",
  warn: "bg-warn-soft text-warn",
  bad: "bg-bad-soft text-bad",
  info: "bg-info-soft text-info",
  muted: "bg-ink/[.06] text-muted",
  brand: "bg-brand-soft text-brand-dark",
};
export function Badge({ tone = "muted", children, className = "" }: { tone?: Tone; children: ReactNode; className?: string }) {
  return <span className={`inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-semibold ${TONE[tone]} ${className}`}>{children}</span>;
}

/** A small dot + word for a state ("Online", "Calling"). */
export function Status({ tone = "muted", children, pulse = false }: { tone?: Tone; children: ReactNode; pulse?: boolean }) {
  const dot = { ok: "bg-ok", warn: "bg-warn", bad: "bg-bad", info: "bg-info", muted: "bg-muted", brand: "bg-brand" }[tone];
  return (
    <span className="inline-flex items-center gap-1.5 text-sm font-medium text-muted">
      <span className={`relative h-2 w-2 rounded-full ${dot}`}>{pulse ? <span className={`absolute inset-0 animate-ping rounded-full ${dot} opacity-60`} /> : null}</span>
      {children}
    </span>
  );
}

export function Card({ children, className = "", ...p }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div {...p} className={`rounded-2xl bg-surface p-5 shadow-soft ${className}`}>
      {children}
    </div>
  );
}

/** Title row of a section: title, optional hint, optional right side. */
export function SectionTitle({ title, hint, right, className = "" }: { title: ReactNode; hint?: ReactNode; right?: ReactNode; className?: string }) {
  return (
    <div className={`mb-3 flex items-end justify-between gap-3 ${className}`}>
      <div className="min-w-0">
        <h2 className="text-lg font-bold tracking-[-0.01em]">{title}</h2>
        {hint ? <p className="text-sm text-muted">{hint}</p> : null}
      </div>
      {right}
    </div>
  );
}

/** One row of a list: leading picture/icon, title + subtitle, trailing value/actions. */
export function ListRow({ lead, title, sub, trail, onClick, className = "", ...p }: { lead?: ReactNode; title: ReactNode; sub?: ReactNode; trail?: ReactNode; onClick?: () => void; className?: string } & Omit<React.HTMLAttributes<HTMLDivElement>, "title" | "onClick">) {
  const body = (
    <>
      {lead ? <span className="shrink-0">{lead}</span> : null}
      <span className="min-w-0 flex-1 text-left">
        <span className="block truncate font-semibold">{title}</span>
        {sub ? <span className="block truncate text-sm text-muted">{sub}</span> : null}
      </span>
      {trail ? <span className="flex shrink-0 items-center gap-2">{trail}</span> : null}
    </>
  );
  const cls = `flex w-full items-center gap-3 rounded-xl px-3 py-3 ${onClick ? "transition hover:bg-ink/[.035] active:scale-[.995]" : ""} ${className}`;
  return onClick ? (
    <div {...p} role="button" tabIndex={0} onClick={onClick} onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && onClick()} className={`${cls} cursor-pointer`}>
      {body}
    </div>
  ) : (
    <div {...p} className={cls}>
      {body}
    </div>
  );
}

export function Empty({ children, icon, action }: { children: ReactNode; icon?: ReactNode; action?: ReactNode }) {
  return (
    <div className="grid place-items-center gap-2 px-4 py-10 text-center text-muted">
      {icon ? <span className="grid h-14 w-14 place-items-center rounded-full bg-ink/[.04] text-muted">{icon}</span> : null}
      <div className="max-w-xs text-[15px]">{children}</div>
      {action}
    </div>
  );
}

/** Grey placeholders while something loads (instead of "Loading…"). */
export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded-xl bg-ink/[.06] ${className}`} />;
}
export function SkeletonList({ rows = 4 }: { rows?: number }) {
  return (
    <div className="flex flex-col gap-3">
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton key={i} className="h-16" />
      ))}
    </div>
  );
}

/** Fade + rise in when a view appears. */
export function Appear({ children, className = "", delay = 0 }: { children: ReactNode; className?: string; delay?: number }) {
  return (
    <motion.div className={className} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ ...ease, delay }}>
      {children}
    </motion.div>
  );
}

// ------------------------------------------------------------------ inputs

export const inputCls = "h-12 w-full rounded-xl bg-surface px-4 text-[15px] text-ink outline-none ring-1 ring-line transition placeholder:text-muted hover:ring-ink/25 focus:ring-2 focus:ring-accent";

export function Field({ label, hint, children, className = "" }: { label: ReactNode; hint?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <label className={`block ${className}`}>
      <span className="mb-1.5 block text-sm font-medium text-muted">{label}</span>
      {children}
      {hint ? <span className="mt-1 block text-xs text-muted">{hint}</span> : null}
    </label>
  );
}

export function Input({ className = "", ...p }: React.InputHTMLAttributes<HTMLInputElement>) {
  return <input {...p} className={`${inputCls} ${className}`} />;
}

// ------------------------------------------------------------------ tabs

/** Pill tabs with a sliding highlight. */
export function Segmented<T extends string>({ value, onChange, options, className = "" }: { value: T; onChange: (v: T) => void; options: [T, ReactNode][]; className?: string }) {
  const id = useId();
  return (
    <div className={`inline-flex max-w-full overflow-x-auto rounded-full bg-line/70 p-1 [scrollbar-width:none] ${className}`}>
      {options.map(([v, label]) => (
        <button key={v} onClick={() => onChange(v)} className={`relative h-10 shrink-0 rounded-full px-4 text-[15px] font-semibold transition-colors ${value === v ? "text-ink" : "text-muted hover:text-ink"}`}>
          {value === v ? <motion.span layoutId={`seg-${id}`} transition={spring} className="absolute inset-0 rounded-full bg-surface shadow-soft" /> : null}
          <span className="relative inline-flex items-center gap-1.5">{label}</span>
        </button>
      ))}
    </div>
  );
}

// ------------------------------------------------------------------ windows

/** A window: slides up from the bottom on phones, pops in the middle on bigger screens. */
export function Modal({ open, onClose, children, wide = false, title, footer }: { open: boolean; onClose: () => void; children: ReactNode; wide?: boolean; title?: ReactNode; footer?: ReactNode }) {
  useEffect(() => {
    if (!open) return;
    const k = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", k);
    return () => document.removeEventListener("keydown", k);
  }, [open, onClose]);
  return createPortal(
    <AnimatePresence>
      {open ? (
        <motion.div key="m" className="fixed inset-0 z-50 flex items-end justify-center bg-[#15120d]/35 backdrop-blur-[3px] sm:items-center sm:p-6" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.18 }} onClick={(e) => e.target === e.currentTarget && onClose()}>
          <motion.div
            role="dialog"
            aria-modal="true"
            data-modal
            initial={{ y: 40, opacity: 0, scale: 0.98 }}
            animate={{ y: 0, opacity: 1, scale: 1 }}
            exit={{ y: 30, opacity: 0, scale: 0.98 }}
            transition={spring}
            className={`flex max-h-[92vh] w-full flex-col overflow-hidden rounded-t-3xl bg-surface shadow-2xl sm:rounded-3xl ${wide ? "sm:max-w-3xl" : "sm:max-w-lg"}`}
          >
            <div className="mx-auto mt-2.5 h-1.5 w-10 shrink-0 rounded-full bg-ink/10 sm:hidden" />
            {title ? (
              <div className="flex shrink-0 items-center justify-between gap-3 px-6 pb-2 pt-4 sm:pt-6">
                <h2 className="text-xl font-bold tracking-[-0.015em]">{title}</h2>
                <IconButton label="Close" onClick={onClose} size={36}>
                  <X size={18} />
                </IconButton>
              </div>
            ) : null}
            <div className={`min-h-0 flex-1 overflow-auto px-6 pb-6 ${title ? "pt-2" : "pt-6"}`}>{children}</div>
            {footer ? <div className="shrink-0 border-t border-line bg-surface px-6 py-4">{footer}</div> : null}
          </motion.div>
        </motion.div>
      ) : null}
    </AnimatePresence>,
    document.body,
  );
}

/** "⋯ More": the quiet actions of a row or page, out of the way until needed. */
export function MoreMenu({ items, label = "More", align = "right" }: { items: ({ label: ReactNode; onClick: () => void; icon?: ReactNode; danger?: boolean } | null | false)[]; label?: string; align?: "left" | "right" }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => !ref.current?.contains(e.target as Node) && setOpen(false);
    document.addEventListener("pointerdown", close);
    return () => document.removeEventListener("pointerdown", close);
  }, [open]);
  const list = items.filter(Boolean) as { label: ReactNode; onClick: () => void; icon?: ReactNode; danger?: boolean }[];
  if (!list.length) return null;
  return (
    <div ref={ref} className="relative">
      <IconButton label={label} variant="ghost" onClick={() => setOpen((o) => !o)}>
        <MoreHorizontal size={20} />
      </IconButton>
      <AnimatePresence>
        {open ? (
          <motion.div
            initial={{ opacity: 0, y: -6, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -4, scale: 0.98 }}
            transition={{ duration: 0.14 }}
            className={`absolute top-11 z-40 min-w-[200px] overflow-hidden rounded-xl bg-surface p-1.5 shadow-[0_8px_28px_rgb(0_0_0/16%)] ring-1 ring-line ${align === "right" ? "right-0" : "left-0"}`}
          >
            {list.map((it, i) => (
              <button key={i} onClick={() => (setOpen(false), it.onClick())} className={`flex w-full items-center gap-2.5 rounded-lg px-3 py-2.5 text-left text-[15px] font-medium transition hover:bg-ink/[.05] ${it.danger ? "text-bad" : "text-ink"}`}>
                {it.icon ? <span className="text-muted">{it.icon}</span> : null}
                {it.label}
              </button>
            ))}
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  );
}

// ------------------------------------------------------------------ messages

type Toast = { id: number; text: string; tone: "ok" | "bad" | "info" };
const ToastCtx = createContext<(text: string, tone?: Toast["tone"], ms?: number) => void>(() => {});
export const useToast = () => useContext(ToastCtx);

/** Messages appear at the top (never over the buttons at the bottom), one or two at a time. */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const push = useCallback((text: string, tone: Toast["tone"] = "info", ms = 3500) => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t.filter((x) => x.text !== text).slice(-1), { id, text, tone }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), ms);
  }, []);
  return (
    <MotionConfig reducedMotion="user">
      <ToastCtx.Provider value={push}>
        {children}
        <div className="pointer-events-none fixed inset-x-0 top-3 z-[60] flex flex-col items-center gap-2 px-4">
          <AnimatePresence initial={false}>
            {toasts.map((t) => (
              <motion.div
                key={t.id}
                role="status"
                layout
                initial={{ opacity: 0, y: -16, scale: 0.96 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, y: -10, scale: 0.98 }}
                transition={spring}
                className="pointer-events-auto flex max-w-md items-center gap-2.5 rounded-xl bg-ink py-3 pl-3.5 pr-5 text-[15px] font-medium text-canvas shadow-[0_8px_24px_rgb(0_0_0/20%)]"
              >
                <span className={`h-2 w-2 shrink-0 rounded-full ${t.tone === "ok" ? "bg-ok" : t.tone === "bad" ? "bg-bad" : "bg-brand"}`} />
                {t.text}
              </motion.div>
            ))}
          </AnimatePresence>
        </div>
      </ToastCtx.Provider>
    </MotionConfig>
  );
}

// ------------------------------------------------------------------ connection

export function LivePill({ status, via }: { status: string; via: string }) {
  const hybrid = net.mode === "hybrid"; // a cloud-only restaurant just shows "Live"
  const label = status === "online" ? (hybrid ? (via === "hub" ? "Live · Local" : "Live · Cloud (hub down)") : "Live") : status === "offline" ? "Offline · retrying" : status === "unpaired" ? "Not set up" : "Connecting…";
  const tone = status === "online" ? (via === "cloud" && hybrid ? "warn" : "ok") : status === "connecting" ? "muted" : "bad";
  return (
    <span className="inline-flex h-8 items-center gap-1.5 rounded-full bg-ink/[.05] px-3 text-[13px] font-medium text-ink/70">
      <span className={`h-2 w-2 rounded-full ${tone === "ok" ? "bg-ok" : tone === "warn" ? "bg-warn" : tone === "bad" ? "bg-bad" : "bg-muted"}`} />
      <span data-via={via}>{label}</span>
    </span>
  );
}
