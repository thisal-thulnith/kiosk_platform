// Step 5: payments (ways to pay, the restaurant's QR payment merchant account, a test of every card
// reader) and the bridge to the restaurant's own POS, if they keep their till.
// The API calls QR payment "lankaqr"; people see "QR payment".
import { Banknote, Check as CheckIcon, CreditCard, FileUp, History, KeyRound, QrCode, Store } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { clock, toCents } from "../../lib/format";
import { Button, Modal, MoreMenu, useToast } from "../../ui/kit";
import { Check, copy, Field, Input, Lead, Loading, Row, Section, Select, say, Status, useAct, useLoad, useSetup, WarnLine } from "./ui";

type PaySetup = {
  methods: { cash: boolean; lankaqr: boolean; card: boolean };
  lankaqr: { provider: string | null; merchant_id: string; secret_hint: string | null; live: boolean; status: "not_set" | "not_tested" | "ok" | "failed"; last_error?: string | null };
  providers: { code: string; name: string; needs: string[] }[];
  card_screens: { device_id: string; name: string; mode: "reader" | "softpos"; terminal_id?: string; tested_at?: string | null; test_error?: string | null }[];
};
const QR_STATUS: Record<PaySetup["lankaqr"]["status"], ["muted" | "warn" | "ok" | "bad", string]> = {
  not_set: ["muted", "Not set up"],
  not_tested: ["warn", "Not tested"],
  ok: ["ok", "Connection OK"],
  failed: ["bad", "Test failed"],
};
const METHODS: [keyof PaySetup["methods"], string, ReactNode][] = [
  ["cash", "Cash", <Banknote key="c" size={20} />],
  ["lankaqr", "QR payment", <QrCode key="q" size={20} />],
  ["card", "Card", <CreditCard key="k" size={20} />],
];

export function PaymentsCard() {
  const { admin, changed } = useSetup();
  const act = useAct();
  const toast = useToast();
  const [s, reload, err] = useLoad(() => admin.get<PaySetup>(admin.v("/payment-setup")));
  const [methods, setMethods] = useState<PaySetup["methods"] | null>(null);
  const [provider, setProvider] = useState("mock");
  const [merchant, setMerchant] = useState("");
  const [secret, setSecret] = useState("");
  const [live, setLive] = useState(false);
  const [loaded, setLoaded] = useState(false);
  useEffect(() => {
    if (!s || loaded) return;
    setLoaded(true);
    setMethods(s.methods);
    setProvider(s.lankaqr.provider || "mock");
    setMerchant(s.lankaqr.merchant_id || "");
    setLive(s.lankaqr.live);
  }, [s]);
  if (!s || !methods) return <Loading id="payments-card" title="Ways to pay" err={err} />;
  const after = async () => (await reload(), changed());
  const [tone, label] = QR_STATUS[s.lankaqr.status];
  const dirty = (Object.keys(methods) as (keyof PaySetup["methods"])[]).some((k) => methods[k] !== s.methods[k]);
  const qrDirty = provider !== (s.lankaqr.provider || "mock") || merchant !== (s.lankaqr.merchant_id || "") || !!secret || live !== s.lankaqr.live;
  const testNext = !qrDirty && (s.lankaqr.status === "not_tested" || s.lankaqr.status === "failed");

  return (
    <>
      <Section
        id="payments-card"
        title="Ways to pay"
        action={
          dirty ? (
            <Button size="sm" variant="primary" onClick={() => act(() => admin.api("PUT", admin.v("/payment-setup/methods"), methods), "Ways to pay saved. Screens update now.").then((r) => r && after())}>
              Save ways to pay
            </Button>
          ) : null
        }
      >
        <div className="grid grid-cols-3 gap-2">
          {METHODS.map(([k, n, ic]) => (
            <label key={k} className={`relative flex cursor-pointer flex-col items-start gap-2 rounded-2xl p-3.5 ring-1 transition active:scale-[.98] has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-ink ${methods[k] ? "bg-surface ring-ink/25" : "bg-ink/[.025] ring-transparent text-muted hover:ring-line"}`}>
              <input type="checkbox" className="peer sr-only" data-method={k} aria-label={n} checked={methods[k]} onChange={(e) => setMethods({ ...methods, [k]: e.target.checked })} />
              <span className={`absolute right-3 top-3 grid h-5 w-5 place-items-center rounded-full transition ${methods[k] ? "bg-ok text-white" : "ring-2 ring-inset ring-line"}`}>{methods[k] ? <CheckIcon size={13} strokeWidth={3} /> : null}</span>
              <span className={`grid h-9 w-9 place-items-center rounded-full ${methods[k] ? "bg-ink/[.06] text-ink" : "bg-ink/[.04]"}`}>{ic}</span>
              <span className="font-semibold">{n}</span>
              <span className="-mt-2 text-xs text-muted">{methods[k] ? "On" : "Off"}</span>
            </label>
          ))}
        </div>
      </Section>

      <Section title="QR payment account" badge={<Status tone={tone}>{label}</Status>} about="The restaurant's own merchant account. Keys are stored encrypted, never sent to screens.">
        {s.lankaqr.status === "failed" && s.lankaqr.last_error ? <WarnLine tone="bad">{say(s.lankaqr.last_error)}</WarnLine> : null}
        <Field label="Provider">
          <Select aria-label="Provider" value={provider} onChange={(e) => setProvider(e.target.value)}>
            {s.providers.map((p) => (
              <option key={p.code} value={p.code}>
                {p.name}
              </option>
            ))}
          </Select>
        </Field>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Merchant ID">
            <Input aria-label="Merchant ID" value={merchant} onChange={(e) => setMerchant(e.target.value)} placeholder="From the bank / gateway" />
          </Field>
          <Field label="API key">
            <Input aria-label="API key" type="password" autoComplete="new-password" value={secret} onChange={(e) => setSecret(e.target.value)} placeholder={s.lankaqr.secret_hint ? `Saved ••••${s.lankaqr.secret_hint}` : "From the gateway"} />
          </Field>
        </div>
        <Check checked={live} onChange={setLive} aria-label="Live payments">
          Live payments <span className="text-muted">(off = test mode)</span>
        </Check>
        <div className="flex flex-wrap gap-2">
          <Button variant={qrDirty ? "primary" : "default"} onClick={() => act(() => admin.api("PUT", admin.v("/payment-setup/lankaqr"), { provider, merchant_id: merchant.trim(), secret: secret || null, live }), "QR payment details saved").then((r) => r && (setSecret(""), after()))}>
            Save details
          </Button>
          <Button
            variant={testNext ? "primary" : "default"}
            onClick={async () => {
              const r = await act(() => admin.api<PaySetup["lankaqr"]>("POST", admin.v("/payment-setup/lankaqr/test")));
              if (!r) return;
              toast(r.status === "ok" ? "QR payment connection OK" : `Test failed: ${say(r.last_error)}`, r.status === "ok" ? "ok" : "bad");
              await after();
            }}
          >
            Test connection
          </Button>
        </div>
      </Section>

      <Section title="Card readers" about={s.card_screens.length ? "Test each one with a small payment." : "No screen takes cards yet. In Screens use ⋯ → Card payments."}>
        {s.card_screens.length ? (
          <div className="-mx-3 flex flex-col divide-y divide-line">
            {s.card_screens.map((c) => (
              <Row key={c.device_id} className="flex-nowrap">
                <Lead tone={c.tested_at ? "ok" : "muted"}>
                  <CreditCard size={20} />
                </Lead>
                <div className="min-w-0 flex-1">
                  <div className="truncate font-semibold">{c.name}</div>
                  <div className="flex flex-wrap items-center gap-x-2">
                    {c.tested_at ? <Status tone="ok">Tested</Status> : c.test_error ? <Status tone="bad">{say(c.test_error)}</Status> : <Status tone="warn">Not tested</Status>}
                    <span className="text-sm text-muted">· {c.mode === "reader" ? `Reader ${c.terminal_id ?? ""}` : "Tap on phone"}</span>
                  </div>
                </div>
                <Button
                  size="sm"
                  variant="soft"
                  onClick={async () => {
                    const r = await act(() => admin.api<{ ok: boolean; error?: string }>("POST", admin.v(`/devices/${c.device_id}/card-test`)));
                    if (!r) return;
                    toast(r.ok ? `${c.name}: reader OK` : say(r.error), r.ok ? "ok" : "bad");
                    await after();
                  }}
                >
                  {c.mode === "reader" ? "Test reader" : "Test"}
                </Button>
              </Row>
            ))}
          </div>
        ) : null}
      </Section>
    </>
  );
}

// ------------------------------------------------------------------ the restaurant's own POS

type PosLink = { connected: boolean; pos_name?: string; url?: string; has_secret?: boolean; has_key?: boolean; events: string[]; all_events: string[]; last_error?: string | null; last_ok_at?: string | null };
type Delivery = { at: string; event: string; token?: string; status: string; response_code?: number; error?: string };

export function PosCard() {
  const { admin, changed } = useSetup();
  const act = useAct();
  const toast = useToast();
  const file = useRef<HTMLInputElement>(null);
  const [data, reload, err] = useLoad(async () => {
    const [link, sent] = await Promise.all([admin.get<PosLink>(admin.v("/pos")), admin.get<Delivery[]>(admin.v("/pos/deliveries")).catch(() => [])]);
    return { link, sent };
  });
  const [form, setForm] = useState<{ name: string; url: string; secret: string; events: string[] } | null>(null);
  const [key, setKey] = useState<string | null>(null);
  const [log, setLog] = useState(false);
  const [open, setOpen] = useState(false);
  useEffect(() => {
    if (data && !form) setForm({ name: data.link.pos_name ?? "", url: data.link.url ?? "", secret: "", events: data.link.events });
  }, [data]);
  if (!data || !form) return <Loading id="pos-card" title="Restaurant's own POS" err={err} />;
  const { link, sent } = data;
  if (!link.connected && !open)
    return (
      <div id="pos-card" className="flex items-center gap-3 rounded-2xl bg-surface px-5 py-4 ring-1 ring-line">
        <Lead>
          <Store size={20} />
        </Lead>
        <div className="min-w-0 flex-1">
          <div className="font-semibold">Restaurant's own POS</div>
          <div className="text-sm text-muted">Only if they keep their till. Orders go to it and it takes the payment.</div>
        </div>
        <Button size="sm" onClick={() => setOpen(true)}>
          Connect
        </Button>
      </div>
    );
  const dirty = form.name !== (link.pos_name ?? "") || form.url !== (link.url ?? "") || !!form.secret || form.events.join() !== link.events.join();
  const importCsv = async (f: File) => {
    // Columns: plu, name, price (rupees), category. A header row is skipped.
    const items = (await f.text())
      .split(/\r?\n/)
      .map((line) => line.split(",").map((x) => x.trim().replace(/^"|"$/g, "")))
      .filter((c) => c.length >= 3 && c[0] && !isNaN(parseFloat(c[2])))
      .map(([plu, name, price, category]) => ({ plu, name, price: toCents(price), category: category || "Menu" }));
    const r = await act(() => admin.api<{ added: number; updated: number }>("POST", admin.v("/pos/menu-import"), { items }));
    if (r) toast(`Menu from the POS: ${r.added} added, ${r.updated} updated`, "ok"), changed();
  };
  const newKey = async () => {
    if (link.has_key && !confirm("Make a new API key? The old key stops working.")) return;
    const r = await act(() => admin.api<{ key: string }>("POST", admin.v("/pos/key")));
    if (r) setKey(r.key), reload();
  };
  return (
    <Section
      id="pos-card"
      title="Restaurant's own POS"
      badge={link.connected ? link.last_error ? <Status tone="bad">Last send failed</Status> : link.last_ok_at ? <Status tone="ok">Connected</Status> : <Status tone="warn">Not tested</Status> : <Status tone="muted">Not connected</Status>}
      about="Only if they keep their till: orders go to it, it takes the payment, and the menu comes in by PLU."
      action={
        <MoreMenu
          label="More POS actions"
          items={[
            { label: link.has_key ? "New API key" : "Create API key", icon: <KeyRound size={18} />, onClick: newKey },
            { label: "Import the POS menu (CSV)", icon: <FileUp size={18} />, onClick: () => file.current?.click() },
            sent.length ? { label: log ? "Hide last events" : "Last events sent", icon: <History size={18} />, onClick: () => setLog((x) => !x) } : null,
          ]}
        />
      }
    >
      <input
        ref={file}
        type="file"
        className="sr-only"
        accept=".csv,text/csv"
        aria-label="POS menu export (CSV)"
        onChange={(e) => {
          const f = e.target.files?.[0];
          e.target.value = "";
          if (f) void importCsv(f);
        }}
      />
      <div className="grid gap-3 sm:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
        <Field label="POS">
          <Input aria-label="POS name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="e.g. Tillpoint" />
        </Field>
        <Field label="Order address">
          <Input aria-label="POS order address" value={form.url} onChange={(e) => setForm({ ...form, url: e.target.value })} placeholder="https://…/kiosk-orders" />
        </Field>
      </div>
      <Field label="Secret">
        <Input aria-label="POS secret" type="password" autoComplete="new-password" value={form.secret} onChange={(e) => setForm({ ...form, secret: e.target.value })} placeholder={link.has_secret ? "Saved (type to replace)" : "Shared secret for signatures"} />
      </Field>
      <div className="flex flex-col gap-2">
        <span className="text-sm font-medium text-muted">Send these events</span>
        <div className="flex flex-wrap gap-x-5 gap-y-2">
          {link.all_events.map((e) => (
            <Check key={e} data-event={e} checked={form.events.includes(e)} onChange={(on) => setForm({ ...form, events: on ? [...form.events, e] : form.events.filter((x) => x !== e) })}>
              {e.replace("order.", "").replace("_", " ")}
            </Check>
          ))}
        </div>
      </div>
      <div className="flex flex-wrap gap-2">
        <Button
          variant={dirty ? "primary" : "default"}
          onClick={async () => {
            const r = await act(() => admin.api("PUT", admin.v("/pos"), { pos_name: form.name.trim(), url: form.url.trim() || null, secret: form.secret || null, events: form.events }), "POS connection saved");
            if (r) setForm({ ...form, secret: "" }), await reload(), changed();
          }}
        >
          Save
        </Button>
        <Button
          onClick={async () => {
            const r = await act(() => admin.api<{ ok: boolean; response_code?: number; error?: string }>("POST", admin.v("/pos/test")));
            if (!r) return;
            toast(r.ok ? "The POS answered OK" : `POS answered ${r.response_code || "nothing"}: ${r.error || ""}`, r.ok ? "ok" : "bad");
            await reload();
          }}
        >
          Send test
        </Button>
      </div>
      {log && sent.length ? (
        <div className="flex flex-col gap-1 rounded-2xl bg-ink/[.035] p-3">
          {sent.slice(0, 10).map((d, i) => (
            <div key={i} className="flex items-center gap-2 text-[13px] text-muted">
              {d.status === "ok" || d.status === "sent" ? <CheckIcon size={14} className="text-ok" /> : <span className="h-1.5 w-1.5 rounded-full bg-bad" />}
              {`${clock(d.at)} · ${d.event}${d.token ? ` ${d.token}` : ""} · ${d.status}${d.response_code ? ` (${d.response_code})` : ""}${d.error ? ` · ${d.error}` : ""}`}
            </div>
          ))}
        </div>
      ) : null}
      <Modal
        open={!!key}
        onClose={() => setKey(null)}
        title="POS API key"
        footer={
          <div className="flex gap-2">
            <Button className="flex-1" onClick={() => key && copy(key, toast)}>
              Copy
            </Button>
            <Button variant="primary" className="flex-1" onClick={() => setKey(null)}>
              Done
            </Button>
          </div>
        }
      >
        <p className="text-[15px] text-muted">Give this to the POS company once. It calls our API with the header X-Pos-Key. A new key replaces this one.</p>
        <pre className="pos-key mt-3 whitespace-pre-wrap break-all rounded-2xl bg-ink/[.035] p-4 font-mono text-sm">{key}</pre>
        <p className="mt-2 text-xs text-muted">CSV menu columns: plu, name, price (rupees), category.</p>
      </Modal>
    </Section>
  );
}
