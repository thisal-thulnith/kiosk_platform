// Step 1: the restaurant. Look & logo, package, business details on receipts, how it works,
// welcome photos, branches.
import { Building2, ImagePlus, Plus, X } from "lucide-react";
import { useState } from "react";
import { net } from "../../lib/net";
import { store } from "../../lib/store";
import { BrandEditor } from "../../ui/brandEditor";
import { Button, Modal, Skeleton, useToast } from "../../ui/kit";
import { Check, Field, Input, Lead, Section, Select, say, useAct, useLoad, useSetup } from "./ui";

const PACK_NAMES: Record<string, string> = { pack1: "Pack 1 · Self-Serve", pack2: "Pack 2 · Counter + Table", pack3: "Pack 3 · Hybrid Pro", custom: "Pack 4 · Custom", hotel: "Hotel · Custom" };
const KIND_NAMES: Record<string, string> = { table: "Tables", kiosk: "Kiosks", cashier: "Cashiers", kds: "Kitchen", status: "Status boards", waiter: "Waiters", board: "Menu boards", room: "Rooms" };

type Usage = Record<string, { used: number; set_up: number; limit: number | null }>;

/** Look & logo: the restaurant's colour, logo and light / dark screens. */
export function BrandCard() {
  const { admin, changed } = useSetup();
  return <BrandEditor admin={admin} onSaved={changed} />;
}

export function PlanCard() {
  const { admin } = useSetup();
  const [res] = useLoad(() => admin.get<{ plan: { pack: string; tier?: string } | null; usage: Usage }>(admin.v("/plan")));
  if (!res)
    return (
      <Section title="Package">
        <Skeleton className="h-16" />
      </Section>
    );
  const plan = res.plan;
  return (
    <Section title="Package" about={plan ? `${PACK_NAMES[plan.pack] ?? plan.pack}${plan.tier ? ` · ${plan.tier[0].toUpperCase()}${plan.tier.slice(1)}` : ""}` : "Unrestricted (demo)"}>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        {Object.entries(res.usage).map(([k, u]) => {
          const full = u.limit !== null && u.used >= u.limit;
          return (
            <div key={k} className="rounded-2xl bg-ink/[.035] px-3.5 py-2.5">
              <div className="flex items-center gap-1.5 text-xs font-medium text-muted">
                {full ? <span className="h-1.5 w-1.5 rounded-full bg-warn" /> : null}
                {KIND_NAMES[k] ?? k}
              </div>
              <div className="num text-lg font-bold">
                {u.used}
                {u.limit === null ? "" : <span className="text-sm font-medium text-muted"> / {u.limit}</span>}
              </div>
              <div className="text-xs text-muted">{u.set_up} set up</div>
            </div>
          );
        })}
      </div>
      {plan ? <p className="text-xs text-muted">More screens or flows: Platform console → Change package.</p> : null}
    </Section>
  );
}

export function BusinessCard() {
  const { admin, changed } = useSetup();
  const act = useAct();
  const st = admin.venue?.settings ?? {};
  const [saved, setSaved] = useState({ legal: st.legal_name ?? "", vat: st.vat_number ?? "", footer: st.receipt_footer ?? "" });
  const [legal, setLegal] = useState<string>(saved.legal);
  const [vat, setVat] = useState<string>(saved.vat);
  const [footer, setFooter] = useState<string>(saved.footer);
  const dirty = legal !== saved.legal || vat !== saved.vat || footer !== saved.footer;
  const save = async () => {
    const v = await act(() => admin.api("PATCH", admin.v(""), { settings: { legal_name: legal.trim(), vat_number: vat.trim(), receipt_footer: footer.trim() } }), "Business details saved. Receipts print them from now on.");
    if (v) (admin.venue = v), setSaved({ legal, vat, footer }), changed();
  };
  return (
    <Section title="Business details" about="Printed on every receipt. With a VAT number it says “Tax invoice”.">
      <Field label="Legal name">
        <Input aria-label="Legal name" value={legal} onChange={(e) => setLegal(e.target.value)} placeholder="Company name on invoices" />
      </Field>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="VAT registration number">
          <Input aria-label="VAT number" value={vat} onChange={(e) => setVat(e.target.value)} placeholder="e.g. 123456789-7000" />
        </Field>
        <Field label="Receipt footer">
          <Input aria-label="Receipt footer" value={footer} onChange={(e) => setFooter(e.target.value)} placeholder="Thank you!" />
        </Field>
      </div>
      <Button className="self-start" variant={dirty ? "primary" : "default"} disabled={!dirty} onClick={save}>
        Save
      </Button>
    </Section>
  );
}

type Opt = [string, string];
const SELECTS: [string, string, Opt[]][] = [
  ["Tables", "table_access", [["open", "Guests can order from a table screen any time"], ["staff_opens", "Staff open each table on the POS (empty tables are locked)"]]],
  ["When do table guests pay?", "dine_in_mode", [["tab", "After eating: one check per table, the waiter brings the bill"], ["pay_first", "Before eating: pay with each order (QR payment, card or at the POS)"]]],
  ["Ready food", "serve_mode", [["self_pickup", "Guests pick up (status board shows Ready)"], ["waiter", "Waiters serve at the table"]]],
  ["Cashier & kiosk orders", "release_rule", [["A", "Kitchen starts after payment (safest)"], ["B", "Kitchen starts at once, hand over only when paid"]]],
];
const YES_NO: [string, string, string][] = [
  ["Text guests when the order is ready", "sms_ready", "Yes, if they leave their mobile number"],
  ["Text guests a receipt link", "sms_receipt", "Yes, after payment"],
];
const NUMS: [string, string, number, number][] = [
  ["Unpaid orders expire after (minutes)", "unpaid_expiry_minutes", 1, 120],
  ["Cooks on a normal shift", "kitchen_cooks", 1, 50],
  ["Default cooking time (minutes)", "default_prep_minutes", 1, 120],
];

export function SettingsCard() {
  const { admin } = useSetup();
  const act = useAct();
  const [s, setS] = useState<Record<string, any>>(() => ({ ...(admin.venue?.settings ?? {}) }));
  const [dirty, setDirty] = useState(false);
  const set = (k: string, v: unknown) => (setS((x) => ({ ...x, [k]: v })), setDirty(true));
  const save = async () => {
    const keys = [...SELECTS.map((x) => x[1]), ...YES_NO.map((x) => x[1]), ...NUMS.map((x) => x[1])];
    const settings = Object.fromEntries(keys.map((k) => [k, s[k]]));
    const v = await act(() => admin.api("PATCH", admin.v(""), { settings }), "Settings saved. Screens use them on their next order.");
    if (v) (admin.venue = v), setDirty(false);
  };
  return (
    <Section title="How this restaurant works">
      <div className="grid gap-3">
        {SELECTS.map(([label, key, opts]) => (
          <Field key={key} label={label}>
            <Select data-key={key} value={s[key] ?? opts[0][0]} onChange={(e) => set(key, e.target.value)}>
              {opts.map(([v, n]) => (
                <option key={v} value={v}>
                  {n}
                </option>
              ))}
            </Select>
          </Field>
        ))}
        {YES_NO.map(([label, key, yes]) => (
            <Field key={key} label={label}>
              <Select data-key={key} value={s[key] === false ? "false" : "true"} onChange={(e) => set(key, e.target.value === "true")}>
                <option value="true">{yes}</option>
                <option value="false">No</option>
              </Select>
            </Field>
        ))}
      </div>
      <div className="flex flex-col gap-2">
        {NUMS.map(([label, key, min, max]) => (
          <label key={key} className="flex items-center gap-3 text-[15px]">
            <span className="flex-1 text-muted">{label}</span>
            <Input data-key={key} aria-label={label} type="number" min={min} max={max} value={s[key] ?? ""} onChange={(e) => set(key, Number(e.target.value))} className="num h-11 w-24 text-right" />
          </label>
        ))}
      </div>
      <Button className="self-start" variant={dirty ? "primary" : "default"} disabled={!dirty} onClick={save}>
        Save settings
      </Button>
    </Section>
  );
}

export function PhotosCard() {
  const { admin } = useSetup();
  const toast = useToast();
  const act = useAct();
  const [photos, setPhotos] = useState<string[]>(() => [...(admin.venue?.settings?.attract_images ?? [])]);
  const [busy, setBusy] = useState(false);
  const save = async (next: string[]) => {
    setPhotos(next);
    const v = await act(() => admin.api("PATCH", admin.v(""), { settings: { attract_images: next } }), "Welcome photos saved. Screens show them after a reload.");
    if (v) admin.venue = v;
  };
  const upload = async (f: File) => {
    setBusy(true);
    try {
      const res = await fetch(net.base() + admin.v("/media"), { method: "POST", headers: { ...admin.headers(), "Content-Type": f.type }, body: f });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) return toast(data?.error?.message ?? "Upload failed", "bad");
      await save([...photos, data.url]);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Section title="Welcome screen photos" about="Shown on kiosks and tables while nobody is ordering.">
      <div className="grid grid-cols-3 gap-2">
        {photos.map((url, i) => (
          <div key={url + i} className="group relative aspect-[4/3]">
            <img src={url} alt="" className="h-full w-full rounded-2xl object-cover" />
            <button aria-label="Remove photo" className="absolute right-1.5 top-1.5 grid h-7 w-7 place-items-center rounded-full bg-surface/90 text-ink shadow-soft transition active:scale-95" onClick={() => save(photos.filter((_, j) => j !== i))}>
              <X size={15} />
            </button>
          </div>
        ))}
        <label className={`grid aspect-[4/3] cursor-pointer place-items-center rounded-2xl bg-ink/[.035] text-muted transition hover:bg-ink/[.06] hover:text-ink ${busy ? "animate-pulse" : ""}`}>
          <span className="flex flex-col items-center gap-1 text-sm font-semibold">
            <ImagePlus size={22} />
            {busy ? "Uploading…" : "Add a photo"}
          </span>
          <input
            type="file"
            className="sr-only"
            accept="image/jpeg,image/png,image/webp"
            aria-label="Welcome photo"
            onChange={(e) => {
              const f = e.target.files?.[0];
              e.target.value = "";
              if (f) void upload(f);
            }}
          />
        </label>
      </div>
    </Section>
  );
}

export function BranchCard() {
  const { admin } = useSetup();
  const act = useAct();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const [sample, setSample] = useState(false);
  const add = async () => {
    const v = await act<{ id: string; name: string }>(() => admin.api("POST", "/v1/admin/venues", { name: name.trim(), code: code.trim(), sample_menu: sample, same_restaurant_as: admin.venue?.id }), `${name.trim()} added`);
    if (!v) return;
    store.set("kiosk:admin:venue", v.id);
    const url = new URL(location.href);
    url.searchParams.delete("venue");
    url.searchParams.delete("step");
    setTimeout(() => (location.href = url.toString()), 600);
  };
  return (
    <div className="flex items-center gap-3 rounded-2xl bg-surface px-5 py-4 ring-1 ring-line">
      <Lead>
        <Building2 size={20} />
      </Lead>
      <div className="min-w-0 flex-1">
        <div className="font-semibold">Another branch?</div>
        <div className="text-sm text-muted">{say("Same company, its own screens, staff, menu and reports.")}</div>
      </div>
      <Button size="sm" onClick={() => setOpen(true)}>
        <Plus size={16} /> Add branch
      </Button>
      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title="Add a branch"
        footer={
          <Button variant="primary" size="lg" className="w-full" disabled={!name.trim() || !code.trim()} onClick={add}>
            Add branch
          </Button>
        }
      >
        <div className="flex flex-col gap-4">
          <div className="grid gap-3 sm:grid-cols-[1fr_160px]">
            <Field label="Branch name">
              <Input aria-label="Branch name" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Kandy" />
            </Field>
            <Field label="Code">
              <Input aria-label="Branch code" value={code} onChange={(e) => setCode(e.target.value.toUpperCase())} placeholder="e.g. KANDY" />
            </Field>
          </div>
          <Check checked={sample} onChange={setSample}>
            Copy the sample menu
          </Check>
        </div>
      </Modal>
    </div>
  );
}
