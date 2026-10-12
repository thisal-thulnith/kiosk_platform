// Form pieces for the menu editor: inputs, an on/off switch, folding sections, the three-language
// fields, time windows and the sheet's footer.
import { AnimatePresence, motion } from "motion/react";
import { ChevronDown, Plus, X } from "lucide-react";
import { useState, type ReactNode } from "react";
import { Button, ease } from "../../ui/kit";
import { DAYS, LANGS, type Text, type Win } from "./model";

export const inputCls = "h-12 rounded-xl bg-surface px-4 text-[15px] text-ink outline-none ring-1 ring-line transition placeholder:text-muted/80 hover:ring-ink/25 focus:ring-2 focus:ring-accent disabled:opacity-60";

export function Field({ label, hint, children, className = "" }: { label: ReactNode; hint?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <label className={`flex min-w-0 flex-col gap-1.5 text-sm font-medium text-muted ${className}`}>
      {label}
      {children}
      {hint ? <span className="text-xs text-muted/90">{hint}</span> : null}
    </label>
  );
}

export function Input({ className = "", ...p }: React.InputHTMLAttributes<HTMLInputElement>) {
  return <input {...p} className={`${inputCls} ${/(^|\s)w-/.test(className) ? "" : "w-full"} ${className}`} />;
}

export function Check({ checked, onChange, children }: { checked: boolean; onChange: (v: boolean) => void; children: ReactNode }) {
  return (
    <label className="inline-flex cursor-pointer items-center gap-2.5 text-[15px] font-medium">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} className="h-5 w-5 accent-accent" />
      {children}
    </label>
  );
}

/** An on/off switch with its label (a real checkbox underneath). */
export function Toggle({ checked, onChange, children, hint }: { checked: boolean; onChange: (v: boolean) => void; children: ReactNode; hint?: ReactNode }) {
  return (
    <label className="flex cursor-pointer items-center justify-between gap-4 rounded-xl px-4 py-3 ring-1 ring-line transition hover:bg-canvas/60">
      <span className="min-w-0">
        <span className="block text-[15px] font-semibold">{children}</span>
        {hint ? <span className="block text-sm text-muted">{hint}</span> : null}
      </span>
      <input type="checkbox" role="switch" checked={checked} onChange={(e) => onChange(e.target.checked)} className="peer sr-only" />
      <span className={`relative h-7 w-12 shrink-0 rounded-full transition-colors peer-focus-visible:ring-2 peer-focus-visible:ring-accent peer-focus-visible:ring-offset-2 ${checked ? "bg-accent" : "bg-ink/15"}`}>
        <motion.span className="absolute top-1 h-5 w-5 rounded-full bg-surface" animate={{ left: checked ? 24 : 4 }} transition={ease} />
      </span>
    </label>
  );
}

export function Chip({ on, onClick, children, label }: { on: boolean; onClick: () => void; children: ReactNode; label?: string }) {
  return (
    <button type="button" aria-pressed={on} aria-label={label} onClick={onClick} className={`chip h-9 rounded-full px-4 text-sm font-semibold transition active:scale-95 ${on ? "active bg-accent-soft text-accent ring-1 ring-accent/30" : "bg-canvas text-ink hover:bg-line"}`}>
      {children}
    </button>
  );
}

export function Section({ title, hint, children, action }: { title: ReactNode; hint?: ReactNode; children: ReactNode; action?: ReactNode }) {
  return (
    <section className="flex flex-col gap-3">
      <div className="flex items-end justify-between gap-3">
        <div>
          <h3 className="text-base font-bold tracking-tight">{title}</h3>
          {hint ? <p className="text-sm text-muted">{hint}</p> : null}
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}

/** A section that folds away: title + a short summary of what is inside; opens smoothly. */
export function Fold({ title, summary, open, onToggle, children }: { title: ReactNode; summary?: ReactNode; open: boolean; onToggle: () => void; children: ReactNode }) {
  return (
    <section className="border-t border-line">
      <button type="button" aria-expanded={open} onClick={onToggle} className="flex w-full items-center gap-3 py-4 text-left">
        <span className="min-w-0 flex-1">
          <span className="block text-[15px] font-bold">{title}</span>
          {summary ? <span className="block truncate text-sm text-muted">{summary}</span> : null}
        </span>
        <ChevronDown size={20} className={`shrink-0 text-muted transition-transform duration-200 ${open ? "rotate-180" : ""}`} />
      </button>
      <AnimatePresence initial={false}>
        {open ? (
          <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} transition={ease} className="overflow-hidden">
            <div className="flex flex-col gap-4 px-0.5 pb-5">{children}</div>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </section>
  );
}

/** Folds where one opens at a time is too strict: keep a set of open ones. */
export function useFolds(first: string[] = []) {
  const [open, setOpen] = useState<Set<string>>(() => new Set(first));
  return {
    is: (k: string) => open.has(k),
    toggle: (k: string) => setOpen((s) => (s.has(k) ? (s.delete(k), new Set(s)) : new Set(s).add(k))),
    show: (k: string) => setOpen((s) => new Set(s).add(k)),
  };
}

/** English, Sinhala and Tamil side by side. aria-labels are "<label> en|si|ta". */
export function TextFields({ value, onChange, label = "Name", required = true, only }: { value: Text; onChange: (t: Text) => void; label?: string; required?: boolean; only?: ("en" | "si" | "ta")[] }) {
  const langs = LANGS.filter(([k]) => !only || only.includes(k));
  return (
    <div className={`grid gap-3 ${langs.length > 1 ? "sm:grid-cols-3" : ""}`}>
      {langs.map(([k, n]) => (
        <Field key={k} label={`${label} · ${n}${k === "en" && required ? " *" : ""}`}>
          <Input lang={k} aria-label={`${label} ${k}`} value={value[k] ?? ""} onChange={(e) => onChange({ ...value, [k]: e.target.value })} />
        </Field>
      ))}
    </div>
  );
}

/** Time windows (e.g. breakfast 06:00–11:00 on weekdays). None = always available. */
export function WindowsEditor({ value, onChange }: { value: Win[]; onChange: (w: Win[]) => void }) {
  const set = (i: number, w: Win) => onChange(value.map((x, j) => (j === i ? w : x)));
  return (
    <div className="flex flex-col gap-2">
      {value.length === 0 ? <p className="text-sm text-muted">Always available (no time window).</p> : null}
      {value.map((w, i) => (
        <div key={i} className="flex flex-wrap items-center gap-2 rounded-xl p-3 ring-1 ring-line">
          <div className="flex flex-wrap gap-1">
            {DAYS.map((d, di) => (
              <Chip key={d} on={w.days.includes(di)} onClick={() => set(i, { ...w, days: w.days.includes(di) ? w.days.filter((x) => x !== di) : [...w.days, di].sort() })}>
                {d}
              </Chip>
            ))}
          </div>
          <div className="flex items-center gap-2">
            <Input type="time" aria-label="From" value={w.start} onChange={(e) => set(i, { ...w, start: e.target.value })} className="w-32" />
            <span className="text-muted">to</span>
            <Input type="time" aria-label="To" value={w.end} onChange={(e) => set(i, { ...w, end: e.target.value })} className="w-32" />
          </div>
          <button type="button" aria-label="Remove time window" className="ml-auto grid h-10 w-10 place-items-center rounded-full text-muted hover:bg-bad-soft hover:text-bad" onClick={() => onChange(value.filter((_, j) => j !== i))}>
            <X size={18} />
          </button>
        </div>
      ))}
      <div>
        <Button type="button" size="sm" variant="soft" onClick={() => onChange([...value, { days: [0, 1, 2, 3, 4, 5, 6], start: "06:00", end: "11:00" }])}>
          <Plus size={16} /> Time window
        </Button>
      </div>
      <p className="text-xs text-muted">A window that ends before it starts runs past midnight (e.g. 22:00 to 02:00).</p>
    </div>
  );
}

/** Cancel + the one Save, for a Modal's `footer`. */
export function Footer({ onCancel, onSave, saving, saveLabel = "Save", note }: { onCancel: () => void; onSave: () => void; saving: boolean; saveLabel?: string; note?: ReactNode }) {
  return (
    <div className="flex items-center justify-end gap-3">
      {note ? <span className="mr-auto text-sm font-medium text-bad">{note}</span> : null}
      <Button type="button" variant="ghost" onClick={onCancel}>
        Cancel
      </Button>
      <Button type="button" variant="primary" onClick={onSave} disabled={saving} className="min-w-32">
        {saving ? "Saving…" : saveLabel}
      </Button>
    </div>
  );
}
