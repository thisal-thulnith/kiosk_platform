// Taxes and charges (service charge, VAT, SSCL…): applied in order to every bill, one line each.
import { useState } from "react";
import type { Admin } from "../../lib/admin";
import { Badge, Empty, Modal, useToast } from "../../ui/kit";
import { cleanText, localDate, TAX_CATEGORIES, tzOffset, type TaxRule } from "./model";
import { Chip, Field, Footer, Input, TextFields, Toggle } from "./parts";

const COLS = "minmax(0,0.8fr) minmax(0,2fr) minmax(0,0.7fr) minmax(0,1.6fr) minmax(0,1.6fr) minmax(0,0.8fr)";

export function TaxList({ admin, rules, onEdit }: { admin: Admin; rules: TaxRule[]; onEdit: (r: TaxRule | null) => void }) {
  const tz = admin.venue?.timezone || "Asia/Colombo";
  const sorted = [...rules].sort((a, b) => a.sequence - b.sequence);
  const grid = { "--cols": COLS } as React.CSSProperties;
  const row = "lg:grid lg:grid-cols-(--cols) lg:items-center lg:gap-4";
  return (
    <section className="overflow-hidden rounded-2xl bg-surface shadow-soft">
      <div className="px-4 pb-3 pt-4 sm:px-5 sm:pt-5">
        <h2 className="text-lg font-bold tracking-[-0.01em]">Added to every bill</h2>
        <p className="text-sm text-muted">In this order, each on its own line of the bill. Tap one to change it.</p>
      </div>
      <div style={grid} className="hidden grid-cols-(--cols) items-center gap-4 border-t border-line bg-canvas/60 px-5 py-2 text-xs font-semibold uppercase tracking-wide text-muted lg:grid">
        <span>Code</span>
        <span>Name</span>
        <span className="text-right">Rate</span>
        <span>Charged on</span>
        <span>Dates</span>
        <span className="text-right">Status</span>
      </div>
      {sorted.length ? null : <Empty>No taxes or charges yet.</Empty>}
      {sorted.map((r) => {
        const on = `${r.compound ? "Price + earlier charges" : "Item price"} · ${r.applies_to.includes("*") ? "everything" : r.applies_to.join(", ")}`;
        const dates = `from ${localDate(r.effective_from, tz)}${r.effective_to ? ` until ${localDate(r.effective_to, tz)}` : ""}`;
        return (
          <button key={r.id} onClick={() => onEdit(r)} style={grid} className={`list-row flex w-full items-center gap-3 border-t border-line px-4 py-3 text-left transition hover:bg-canvas/70 sm:px-5 ${row}`}>
            <span className="num grid h-10 min-w-14 shrink-0 place-items-center justify-self-start rounded-xl bg-canvas px-3 text-sm font-bold text-ink">{r.code}</span>
            <span className="min-w-0 flex-1">
              <span className="block truncate font-semibold">
                {r.name.en} <span className="num font-normal text-muted lg:hidden">· {r.rate_bp / 100}%</span>
              </span>
              <span className="block truncate text-sm text-muted lg:hidden">
                {on} · {dates}
              </span>
            </span>
            <span className="num hidden text-right text-[15px] font-bold lg:block">{r.rate_bp / 100}%</span>
            <span className="hidden truncate text-sm text-muted lg:block">{on}</span>
            <span className="hidden truncate text-sm text-muted lg:block">{dates}</span>
            <span className="shrink-0 text-right">
              <Badge tone={r.is_active ? "ok" : "muted"}>{r.is_active ? "Active" : "Off"}</Badge>
            </span>
          </button>
        );
      })}
    </section>
  );
}

export function TaxRuleEditor({ admin, rule, rules, taxCats, onClose, onSaved }: { admin: Admin; rule: TaxRule | null; rules: TaxRule[]; taxCats: string[]; onClose: () => void; onSaved: () => void }) {
  const toast = useToast();
  const tz = admin.venue?.timezone || "Asia/Colombo";
  const [code, setCode] = useState(rule?.code ?? "");
  const [name, setName] = useState(rule?.name ?? {});
  const [rate, setRate] = useState(rule ? String(rule.rate_bp / 100) : "");
  const [seq, setSeq] = useState(String(rule?.sequence ?? rules.length + 1));
  const [applies, setApplies] = useState<string[]>(rule?.applies_to ?? ["*"]);
  const [compound, setCompound] = useState(rule?.compound ?? false);
  const [active, setActive] = useState(rule ? rule.is_active : true);
  const [from, setFrom] = useState(localDate(rule?.effective_from ?? new Date().toISOString(), tz));
  const [to, setTo] = useState(rule?.effective_to ? localDate(rule.effective_to, tz) : "");
  const [saving, setSaving] = useState(false);
  const all = applies.includes("*");
  const cats = [...new Set([...TAX_CATEGORIES, ...taxCats, ...applies.filter((a) => a !== "*")])];
  const toggle = (c: string) => setApplies((a) => (a.includes(c) ? a.filter((x) => x !== c) : [...a.filter((x) => x !== "*"), c]));

  const save = async () => {
    const r = Number(rate);
    if (!code.trim()) return toast("Give the rule a short code (e.g. SC, VAT).", "bad");
    if (!name.en?.trim()) return toast("Give the rule an English name. Guests see it on the bill.", "bad");
    if (rate === "" || !(r >= 0 && r <= 100)) return toast("The rate must be between 0 and 100 %.", "bad");
    if (!from) return toast("Pick the date it starts.", "bad");
    if (to && to <= from) return toast("The end date must be after the start date.", "bad");
    if (!applies.length) return toast("Pick what it applies to.", "bad");
    setSaving(true);
    try {
      const off = tzOffset(tz);
      const body = {
        code: code.trim().toUpperCase(),
        name: cleanText(name),
        rate_bp: Math.round(r * 100),
        sequence: Number(seq) || 0,
        applies_to: applies,
        compound,
        is_active: active,
        effective_from: `${from}T00:00:00${off}`,
        effective_to: to ? `${to}T00:00:00${off}` : null,
      };
      if (rule) await admin.api("PUT", admin.v(`/tax-rules/${rule.id}`), body);
      else await admin.api("POST", admin.v("/tax-rules"), body);
      onSaved();
    } catch (x) {
      toast((x as Error).message, "bad", 6000);
      setSaving(false);
    }
  };

  return (
    <Modal open wide onClose={onClose} title={rule ? `Edit ${rule.code}` : "New tax or charge"} footer={<Footer onCancel={onClose} onSave={save} saving={saving} />}>
      <div className="flex flex-col gap-5">
        <p className="rounded-xl bg-warn-soft px-4 py-3 text-sm font-medium text-warn">Check rates and how they stack with your tax adviser. To change a rate, end the old rule and add a new one, so past bills stay explainable.</p>
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label="Code *">
            <Input aria-label="Code" placeholder="SC, VAT, SSCL…" value={code} onChange={(e) => setCode(e.target.value)} maxLength={40} />
          </Field>
          <Field label="Rate % *">
            <Input aria-label="Rate %" type="number" step="0.01" min={0} max={100} value={rate} onChange={(e) => setRate(e.target.value)} />
          </Field>
          <Field label="Order (applied in this order)">
            <Input aria-label="Order" type="number" value={seq} onChange={(e) => setSeq(e.target.value)} />
          </Field>
        </div>
        <TextFields value={name} onChange={setName} />
        <div className="flex flex-col gap-2">
          <span className="text-sm font-medium text-muted">Applies to</span>
          <div role="group" aria-label="Applies to" className="flex flex-wrap gap-2">
            <Chip on={all} onClick={() => setApplies(["*"])}>
              Everything
            </Chip>
            {cats.map((c) => (
              <Chip key={c} on={!all && applies.includes(c)} onClick={() => toggle(c)}>
                {c}
              </Chip>
            ))}
          </div>
          <span className="text-xs text-muted">Each item has a tax category (food, beverage…). Pick “Everything” or only some categories.</span>
        </div>
        <Toggle checked={compound} onChange={setCompound} hint="Compound: charged on the price plus the charges before it.">
          On top of earlier charges
        </Toggle>
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label="From *">
            <Input aria-label="From" type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
          </Field>
          <Field label="Until (optional)">
            <Input aria-label="Until" type="date" value={to} onChange={(e) => setTo(e.target.value)} />
          </Field>
          <div className="flex items-end">
            <div className="w-full">
              <Toggle checked={active} onChange={setActive}>
                Active
              </Toggle>
            </div>
          </div>
        </div>
      </div>
    </Modal>
  );
}
