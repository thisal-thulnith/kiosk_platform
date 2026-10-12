// Step 4: screens. Every screen has its own screen code (K7MQ-4XPA-2R): open the restaurant's
// address on the tablet (/demo) and type it, or scan its QR. Then tell it what hardware it is. The
// old 6-digit one-time setup code is still under "⋯". Each screen is one row: what it is, whether it is online, which tablet it is on,
// one action that fits right now, and the rest under "⋯".
import { AnimatePresence, motion } from "motion/react";
import { ChefHat, CircleHelp, Copy, Cpu, CreditCard, ExternalLink, FlaskConical, KeyRound, Link2, ListChecks, Monitor, Plus, Power, Presentation, QrCode, RefreshCw, RotateCw, Smartphone, Tablet, UtensilsCrossed, Zap } from "lucide-react";
import { QRCodeSVG } from "qrcode.react";
import { useEffect, useState, type ReactNode } from "react";
import { appOrigin, useComingSoon } from "../../lib/features";
import { ago, clock, en } from "../../lib/format";
import { screenAddress } from "../../lib/screens";
import { store } from "../../lib/store";
import { Badge, Button, Empty, IconButton, Modal, MoreMenu, Skeleton, spring, useToast } from "../../ui/kit";
import { LanHint } from "./Network";
import { Check, Choice, Code, copy, Field, Input, LINK_MD, Section, Select, say, Status, useAct, useSetup, WarnLine, type DeviceRow } from "./ui";

// The screens a restaurant uses. (Menu boards still work if a package has them.)
export const TYPES: [string, string, string][] = [
  ["table", "Table screen", "Guests order and call staff at the table"],
  ["kiosk", "Self-order kiosk", "Guests order and pay alone"],
  ["cashier", "POS (cashier)", "Orders, tables, payments"],
  ["kds", "Kitchen display", "Tickets by station"],
  ["waiter", "Waiter app", "Phone or tablet for waiters"],
  ["status", "Order status board", "Preparing / Ready wall screen"],
];
export const typeName = (t: string) => TYPES.find((x) => x[0] === t)?.[1] ?? (t === "board" ? "Menu board" : t);
const SHORT: Record<string, string> = { table: "Table", kiosk: "Kiosk", cashier: "POS", kds: "Kitchen", waiter: "Waiter", status: "Status board", board: "Menu board" };
const ICONS: Record<string, (size: number) => ReactNode> = {
  table: (s) => <UtensilsCrossed size={s} />,
  kiosk: (s) => <Tablet size={s} />,
  cashier: (s) => <CreditCard size={s} />,
  kds: (s) => <ChefHat size={s} />,
  waiter: (s) => <Smartphone size={s} />,
  status: (s) => <Monitor size={s} />,
  board: (s) => <Presentation size={s} />,
};
const icon = (t: string, size = 20) => (ICONS[t] ?? ICONS.kiosk)(size);

export const LAUNCHER = "/";

/** Where tablets of this restaurant sign in: its own address, on the hub's LAN address for hybrid. */
function useSignInAddress(): { server: string; hubUrl: string | null; address: string; venueCode: string } {
  const { admin, network } = useSetup();
  const hubUrl = network?.mode === "hybrid" && network.hub?.lan_url ? network.hub.lan_url.replace(/\/$/, "") : null;
  const server = hubUrl ?? appOrigin();
  const venueCode = (admin.venue?.code ?? "").toLowerCase();
  return { server, hubUrl, address: `${server}/${venueCode}`, venueCode };
}

/** Table screens run in the Android table app only; there is no web page to open for them. */
const APP_ONLY = (d: DeviceRow) => d.type === "table" || d.type === "board";
const WALL = "/wall";

/** A screen's clean address (/{code}/kitchen?slot=…), plus ?pair= with a one-time code to set it up here. */
export function screenUrl(d: DeviceRow, code?: string, venueCode?: string | null): string {
  const base = screenAddress(d.type in TYPE_SLUGS ? d.type : "kiosk", d.id.slice(-8), venueCode);
  return code ? withParam(base, "pair", code) : base;
}
const withParam = (url: string, k: string, v: string) => `${url}${url.includes("?") ? "&" : "?"}${k}=${encodeURIComponent(v)}`;
const TYPE_SLUGS: Record<string, true> = { cashier: true, waiter: true, kds: true, kiosk: true, status: true, table: true, board: true };

const ORDER = ["cashier", "kds", "status", "table", "kiosk", "waiter", "board"];
const CRITICAL = ["kds", "cashier"];
const CARD_TYPES = ["kiosk", "cashier", "waiter", "table"];

/** Which physical tablet: "SM-X205 · Android 14 · Chrome 128 · 1920x1200 · 192.168.1.33 · set up 2 Oct". */
export function tabletText(d: DeviceRow): string {
  const c = d.client;
  if (!c) return "";
  const date = c.paired_at ? new Date(c.paired_at).toLocaleDateString("en-GB", { day: "numeric", month: "short" }) : "";
  return [c.model, c.os, c.app === "android" ? `App ${c.app_version ?? ""}`.trim() : c.browser, c.screen, c.ip, date && `set up ${date}`].filter(Boolean).join(" · ");
}

// ------------------------------------------------------------------ how-to

function HowTo() {
  return (
    <div className="flex flex-col gap-4">
      <ol className="flex flex-col gap-3">
        {[
          ["Find its slot", "The package made Table T1…, Kiosk 1, Kitchen 1… in the list. Or add one."],
          ["Press Set up", "Its screen code and a QR code appear on this laptop."],
          ["Sign in on the tablet", <>Open the restaurant's address (<SignInAddress />) and type the screen code, or scan the QR. It opens as that screen and stays signed in.</>],
          ["Choose its hardware", "⋯ → Hardware: built-in printers and card readers are set up with it."],
        ].map(([t, about], i) => (
          <li key={i} className="flex gap-3">
            <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-ink/[.06] text-[13px] font-bold">{i + 1}</span>
            <span className="min-w-0 text-[15px]">
              <strong className="block font-semibold">{t}</strong>
              <span className="text-sm text-muted">{about}</span>
            </span>
          </li>
        ))}
      </ol>
      <p className="text-sm text-muted">To replace a broken tablet, sign the new one in with the same code: the old one is signed out. ⋯ → Reset code makes a new code and signs the tablet out. Holding a screen's top-left corner for 3 s opens its settings (manager PIN).</p>
      <LanHint />
    </div>
  );
}

function SignInAddress() {
  return <Code>{useSignInAddress().address}</Code>;
}

// ------------------------------------------------------------------ the list

export function ScreensCard() {
  const { devices, checklist } = useSetup();
  const [adding, setAdding] = useState(false);
  const [help, setHelp] = useState(false);
  const list = [...devices].sort((a, b) => ORDER.indexOf(a.type) - ORDER.indexOf(b.type) || a.name.localeCompare(b.name, undefined, { numeric: true }));
  const online = list.filter((d) => d.connected).length;
  const down = list.filter((d) => CRITICAL.includes(d.type) && d.paired && d.is_active && !d.connected);
  const twice = list.filter((d) => d.is_active && d.same_tablet_as?.length);
  // The next screen to set up gets the one brand-coloured button.
  const nextUp = list.find((d) => d.is_active && !d.paired)?.id;
  const loading = !checklist && !list.length;

  const names = (l: DeviceRow[]) => (l.length > 3 ? `${l.slice(0, 3).map((d) => d.name).join(", ")} and ${l.length - 3} more` : l.map((d) => d.name).join(", "));
  const attention = [down.length ? `${names(down)} ${down.length > 1 ? "are" : "is"} offline` : "", twice.length ? `${twice.length} screens share one tablet` : ""].filter(Boolean);

  return (
    <Section
      id="screens-card"
      title="Screens"
      about={list.length ? `${online} of ${list.length} online` : undefined}
      action={
        <div className="flex items-center gap-1">
          <IconButton label="How to set up a tablet" variant="ghost" onClick={() => setHelp(true)}>
            <CircleHelp size={20} />
          </IconButton>
          <Button size="sm" variant={list.length && !nextUp ? "primary" : "default"} onClick={() => setAdding(true)}>
            <Plus size={16} /> Add screen
          </Button>
        </div>
      }
    >
      {attention.length ? (
        <div className="screens-attention -mt-1 flex flex-wrap items-center gap-x-4 gap-y-1 rounded-xl bg-ink/[.035] px-4 py-3 text-sm">
          {attention.map((a) => (
            <WarnLine key={a} tone={down.length && a === attention[0] ? "bad" : "warn"}>
              {a}
            </WarnLine>
          ))}
          {down.length ? <span className="w-full text-muted">Check power and Wi-Fi. Orders are kept; a screen catches up when it is back.</span> : null}
        </div>
      ) : null}
      {loading ? (
        <div className="flex flex-col gap-2">
          {[0, 1, 2].map((k) => (
            <Skeleton key={k} className="h-16" />
          ))}
        </div>
      ) : list.length ? (
        <div className="screen-list grid gap-3 lg:grid-cols-2 min-[1760px]:grid-cols-3">
          <AnimatePresence initial={false}>
            {list.map((d) => (
              <motion.div key={d.id} className="relative min-w-0 has-[.z-40]:z-20" layout="position" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={spring}>
                <ScreenRow d={d} primary={d.id === nextUp} />
              </motion.div>
            ))}
          </AnimatePresence>
        </div>
      ) : (
        <Empty icon={<Tablet size={24} />} action={<Button variant="primary" onClick={() => setAdding(true)}><Plus size={18} /> Add screen</Button>}>
          No screens yet. Add one, or try the quick test below.
        </Empty>
      )}
      {adding ? <AddScreen onClose={() => setAdding(false)} /> : null}
      <Modal open={help} onClose={() => setHelp(false)} title="Set up a tablet" footer={<Button variant="primary" className="w-full" onClick={() => setHelp(false)}>Got it</Button>}>
        <HowTo />
      </Modal>
    </Section>
  );
}

function ScreenRow({ d, primary }: { d: DeviceRow; primary: boolean }) {
  const { admin, codes, rememberCode, refreshDevices, showCode, showSignIn, changed } = useSetup();
  const act = useAct();
  const toast = useToast();
  const [modal, setModal] = useState<"menu" | "hardware" | "card" | null>(null);
  const code = codes[d.id];
  const pending = code && !d.paired && new Date(code.expires).getTime() > Date.now() ? code : null;
  const critical = CRITICAL.includes(d.type);
  const where = d.type === "table" ? (d.table_ref ? `Table ${d.table_ref}` : "") : d.type === "kds" ? d.station || "all stations" : "";
  const tablet = tabletText(d);

  // The old 6-digit one-time code (fallback for older apps and links).
  const newCode = async () => {
    if (d.paired && !confirm(`Make a one-time setup code for ${d.name}? The tablet that has it now stops working once a tablet uses the code.`)) return;
    const r = await act(() => admin.api<DeviceRow>("POST", admin.v(`/devices/${d.id}/pairing-code`)));
    if (!r?.pairing_code) return;
    rememberCode(d.id, { code: r.pairing_code, expires: r.pairing_expires_at! });
    showCode(d, r.pairing_code, r.pairing_expires_at);
    await refreshDevices();
  };
  const resetCode = async () => {
    if (!confirm(`Reset the screen code for ${d.name}? The tablet on this screen will be signed out.`)) return;
    const r = await act(() => admin.api<DeviceRow>("POST", admin.v(`/devices/${d.id}/screen-code`)), d.paired ? `New code for ${d.name}. Its tablet was signed out.` : `New code for ${d.name}`);
    if (r) await refreshDevices(), changed();
  };
  const command = async (cmd: "identify" | "reload") => {
    const r = await act(() => admin.api<{ sent: boolean }>("POST", admin.v(`/devices/${d.id}/command`), { command: cmd }));
    if (r) toast(r.sent ? (cmd === "reload" ? `Reloading ${d.name}` : `${d.name} shows its name for 8 seconds`) : `${d.name} is not online`, r.sent ? "ok" : "bad");
  };
  const toggle = () => act(() => admin.api("PATCH", admin.v(`/devices/${d.id}`), { is_active: !d.is_active }), d.is_active ? `${d.name} turned off` : `${d.name} turned on`).then(() => (refreshDevices(), changed()));

  const status = !d.is_active ? (
    <Status tone="muted">Turned off</Status>
  ) : d.connected ? (
    <Status tone="ok">Online{d.last_seen_at ? ` · seen ${ago(d.last_seen_at)}` : ""}</Status>
  ) : d.paired ? (
    <Status tone={critical ? "bad" : "muted"}>Offline{d.last_seen_at ? ` · seen ${ago(d.last_seen_at)}` : ""}</Status>
  ) : (
    <Status tone="warn">Not set up yet</Status>
  );
  const extras = [d.hardware?.name.split(" (")[0], d.card ? (d.card.mode === "reader" ? `Card reader ${d.card.terminal_id ?? ""}`.trim() : "Tap on phone") : "", d.menu_categories.length ? `${d.menu_categories.length} menu categories` : ""].filter(Boolean).join(" · ");
  const detail = d.paired ? tablet || (APP_ONLY(d) ? "Runs in the table app (Android)" : "Tablet details appear once it connects with the new app") : APP_ONLY(d) ? "Runs in the table app (Android)" : "";

  // One action that fits right now; everything else is under ⋯.
  const main = !d.is_active ? null : !d.paired ? (
    pending ? (
      <button onClick={() => showCode(d, pending.code, pending.expires)} title="Show the QR code again" className="inline-flex h-9 items-center gap-2 rounded-lg bg-ink/[.06] px-3 text-ink transition hover:bg-ink/[.1] active:scale-[.97]">
        <QrCode size={16} />
        <span className="num text-[15px] font-bold tracking-[.12em]">{pending.code.replace(/(\d{3})(\d{3})/, "$1 $2")}</span>
      </button>
    ) : (
      <Button size="sm" variant={primary ? "primary" : "soft"} onClick={() => showSignIn(d)}>
        Set up
      </Button>
    )
  ) : d.connected ? (
    <Button size="sm" variant="soft" title="Show this screen's name on it in large letters" onClick={() => command("identify")}>
      Identify
    </Button>
  ) : null;

  return (
    <div className={`screen-row flex h-full items-center gap-3 rounded-xl px-3.5 py-3.5 ring-1 ring-line transition hover:bg-ink/[.02] ${d.is_active ? "" : "off"}`} data-device={d.id} data-type={d.type}>
      <span className={`relative grid h-10 w-10 shrink-0 place-items-center rounded-full bg-ink/[.05] text-ink/70 ${d.is_active ? "" : "opacity-50"}`} aria-hidden>
        {icon(d.type)}
      </span>
      <div className={`min-w-0 flex-1 ${d.is_active ? "" : "opacity-50"}`}>
        <div className="flex flex-wrap items-baseline gap-x-2">
          <strong className="text-[15px] font-semibold">{d.name}</strong>
          <span className="text-sm text-muted">
            {SHORT[d.type] ?? d.type}
            {where ? ` · ${where}` : ""}
          </span>
        </div>
        <div className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5">
          {status}
          {extras ? <span className="text-sm text-muted">· {extras}</span> : null}
        </div>
        {d.screen_code ? <ScreenCode code={d.screen_code} name={d.name} /> : null}
        {detail ? (
          <div className="tablet mt-0.5 truncate text-[13px] text-muted" title={d.client?.install_id ? `Install ${d.client.install_id}` : undefined}>
            {detail}
          </div>
        ) : null}
        {d.is_active && d.same_tablet_as?.length ? (
          <div className="mt-1">
            <WarnLine>Same tablet as {d.same_tablet_as.join(", ")}: set one up again or turn it off</WarnLine>
          </div>
        ) : null}
      </div>
      <div className="flex shrink-0 items-center gap-1">
        {main}
        <MoreMenu
          label={`More for ${d.name}`}
          items={[
            d.paired && !APP_ONLY(d) ? { label: "Open", icon: <ExternalLink size={18} />, onClick: () => window.open(screenUrl(d, undefined, admin.venue?.code), "_blank", "noreferrer") } : null,
            d.connected ? { label: "Reload", icon: <RotateCw size={18} />, onClick: () => command("reload") } : null,
            HW_MODELS[d.type] ? { label: "Hardware", icon: <Cpu size={18} />, onClick: () => setModal("hardware") } : null,
            CARD_TYPES.includes(d.type) ? { label: "Card payments", icon: <CreditCard size={18} />, onClick: () => setModal("card") } : null,
            ["kiosk", "table"].includes(d.type) ? { label: "Menu", icon: <ListChecks size={18} />, onClick: () => setModal("menu") } : null,
            d.is_active && d.screen_code ? { label: "Sign-in code and QR", icon: <QrCode size={18} />, onClick: () => showSignIn(d) } : null,
            d.screen_code ? { label: "Reset code", icon: <RefreshCw size={18} />, onClick: resetCode } : null,
            d.is_active ? { label: "One-time setup code", icon: <KeyRound size={18} />, onClick: newCode } : null,
            { label: d.is_active ? "Turn off" : "Turn on", icon: <Power size={18} />, danger: d.is_active, onClick: toggle },
          ]}
        />
      </div>
      {modal === "menu" ? <MenuModal d={d} onClose={() => setModal(null)} /> : null}
      {modal === "hardware" ? <HardwareModal d={d} onClose={() => setModal(null)} /> : null}
      {modal === "card" ? <CardModal d={d} onClose={() => setModal(null)} /> : null}
    </div>
  );
}

// ------------------------------------------------------------------ the code (and QR) for one tablet

/** The screen code in a row: quiet monospace, tap to copy. */
function ScreenCode({ code, name }: { code: string; name: string }) {
  const toast = useToast();
  return (
    <button
      type="button"
      data-screen-code={code}
      title="Copy the screen code"
      aria-label={`Copy the screen code of ${name}`}
      onClick={() => copy(code, toast)}
      className="group mt-1 inline-flex items-center gap-1.5 rounded-md text-[13px] text-muted transition hover:text-ink"
    >
      <span>Code</span>
      <span className="font-mono font-semibold tracking-wide text-ink/80 group-hover:text-ink">{code}</span>
      <Copy size={13} className="opacity-60 group-hover:opacity-100" />
    </button>
  );
}

/** How to sign a tablet in on this screen: the restaurant's address + the screen code, or the QR. */
export function SignInModal({ d, onClose }: { d: DeviceRow; onClose: () => void }) {
  const { hubUrl, address, venueCode } = useSignInAddress();
  const toast = useToast();
  const code = d.screen_code ?? "";
  const link = withParam(address, "code", code);
  return (
    <Modal
      open
      onClose={onClose}
      title={`Sign in ${d.name}`}
      footer={
        <div className="flex gap-2">
          {APP_ONLY(d) || d.paired ? null : (
            <a className={`${LINK_MD} flex-1`} href={withParam(screenUrl(d, undefined, venueCode), "code", code)} target="_blank" rel="noreferrer">
              Open here (test)
            </a>
          )}
          <Button variant="primary" className="flex-1" onClick={onClose}>
            Done
          </Button>
        </div>
      }
    >
      <div className="flex flex-col items-center gap-5 text-center">
        <p className="text-[15px] text-muted">
          Open <strong className="font-semibold text-ink">{address.replace(/^https?:\/\//, "")}</strong> on the tablet and type this code{APP_ONLY(d) ? " in the table app" : ""}, or scan the QR.
        </p>
        <div className="flex w-full items-center justify-center gap-2">
          <div className="screen-code font-mono text-[34px] font-bold tracking-[.08em] sm:text-[40px]" data-code={code}>
            {code}
          </div>
          <IconButton label="Copy the screen code" variant="ghost" onClick={() => copy(code, toast)}>
            <Copy size={18} />
          </IconButton>
        </div>
        <div className="rounded-2xl bg-white p-4 ring-1 ring-line">
          <QRCodeSVG value={link} size={184} marginSize={1} aria-label="Sign-in QR code" />
        </div>
        <div className="text-sm text-muted">
          {typeName(d.type)}
          {d.table_ref ? ` · table ${d.table_ref}` : ""}
          {d.station ? ` · ${d.station}` : ""}
          {d.paired ? " · signing in on another tablet signs the current one out" : " · works until you reset it"}
        </div>
        <div className="flex w-full items-center gap-3 rounded-2xl bg-ink/[.035] px-4 py-3 text-left">
          <div className="min-w-0 flex-1">
            <div className="text-xs font-medium text-muted">Restaurant address{hubUrl ? " (restaurant hub)" : ""}</div>
            <div className="server-url break-all text-[15px] font-semibold">{address}</div>
            {hubUrl ? <div className="text-xs text-muted">Backup: {appOrigin()}/{venueCode}</div> : null}
          </div>
          <IconButton label="Copy the sign-in link" onClick={() => copy(link, toast)}>
            <Link2 size={18} />
          </IconButton>
        </div>
      </div>
    </Modal>
  );
}

export function CodeModal({ d, code, expires, onClose }: { d: DeviceRow; code: string; expires?: string; onClose: () => void }) {
  const { admin, network } = useSetup();
  const toast = useToast();
  // Hybrid restaurants: tablets join through the hub on the restaurant's own network.
  const hubUrl = network?.mode === "hybrid" && network.hub?.lan_url ? network.hub.lan_url.replace(/\/$/, "") : null;
  const server = hubUrl ?? appOrigin();
  const link = `${server}/?pair=${code}`;
  return (
    <Modal
      open
      onClose={onClose}
      title={`Set up ${d.name}`}
      footer={
        <div className="flex gap-2">
          {APP_ONLY(d) ? null : (
            <a className={`${LINK_MD} flex-1`} href={screenUrl(d, code, admin.venue?.code)} target="_blank" rel="noreferrer">
              Open here (test)
            </a>
          )}
          <Button variant="primary" className="flex-1" onClick={onClose}>
            Done
          </Button>
        </div>
      }
    >
      <div className="flex flex-col items-center gap-4 text-center">
        <p className="text-[15px] text-muted">On the tablet, open the app and scan this code, or type the server address and the number.</p>
        <div className="rounded-2xl bg-white p-4 ring-1 ring-line">
          <QRCodeSVG value={link} size={196} marginSize={1} aria-label="Setup QR code" />
        </div>
        <div>
          <div className="setup-code num text-5xl font-black tracking-[.15em]" data-code={code}>
            {code.replace(/(\d{3})(\d{3})/, "$1 $2")}
          </div>
          <div className="mt-1 text-sm text-muted">
            Works once{expires ? `, until ${clock(expires)}` : ", for 10 minutes"} · {typeName(d.type)}
            {d.table_ref ? ` · table ${d.table_ref}` : ""}
            {d.station ? ` · ${d.station}` : ""}
          </div>
        </div>
        <div className="flex w-full items-center gap-3 rounded-2xl bg-ink/[.035] px-4 py-3 text-left">
          <div className="min-w-0 flex-1">
            <div className="text-xs font-medium text-muted">Server address{hubUrl ? " (restaurant hub)" : ""}</div>
            <div className="server-url break-all text-[15px] font-semibold">{server}</div>
            {hubUrl ? <div className="text-xs text-muted">Backup: {appOrigin()}</div> : null}
          </div>
          <IconButton label="Copy the setup link" onClick={() => copy(link, toast)}>
            <Copy size={18} />
          </IconButton>
        </div>
      </div>
    </Modal>
  );
}

// ------------------------------------------------------------------ add a screen, quick test

function AddScreen({ onClose }: { onClose: () => void }) {
  const { admin, stations, refreshDevices, showSignIn, changed } = useSetup();
  const act = useAct();
  const soon = useComingSoon();
  const [type, setType] = useState("table");
  const [name, setName] = useState("");
  const [table, setTable] = useState("");
  const [station, setStation] = useState("");
  const [busy, setBusy] = useState(false);
  const add = async () => {
    const extra: Record<string, string | null> = {};
    if (type === "table") extra.table_ref = table.trim() || null;
    if (type === "kds" && station) extra.station = station;
    setBusy(true);
    const d = await act(() => admin.api<DeviceRow>("POST", admin.v("/devices"), { type, name: name.trim() || typeName(type), ...extra }));
    setBusy(false);
    if (!d) return;
    onClose();
    if (d.screen_code) showSignIn(d);
    await refreshDevices();
    changed();
  };
  return (
    <Modal
      open
      onClose={onClose}
      title="Add a screen"
      footer={
        <Button type="submit" form="add-screen" variant="primary" size="lg" className="w-full" disabled={busy}>
          Add and show its code
        </Button>
      }
    >
      <form
        id="add-screen"
        className="flex flex-col gap-4"
        onSubmit={(e) => {
          e.preventDefault();
          void add();
        }}
      >
        <div className="grid grid-cols-2 gap-2">
          {TYPES.map(([v, label, about]) => {
            const later = soon.includes(v);
            return (
              <button
                key={v}
                type="button"
                data-type={v}
                disabled={later}
                aria-disabled={later}
                onClick={() => setType(v)}
                className={`relative flex flex-col items-start gap-2 rounded-2xl p-3.5 text-left transition ${later ? "coming-soon cursor-not-allowed bg-canvas ring-1 ring-line" : type === v ? "bg-surface ring-2 ring-ink active:scale-[.98]" : "bg-surface ring-1 ring-line hover:bg-ink/[.02] active:scale-[.98]"}`}
              >
                <span className={`grid h-9 w-9 place-items-center rounded-full ${type === v && !later ? "bg-ink text-canvas" : "bg-ink/[.05] text-ink/70"} ${later ? "opacity-50" : ""}`} aria-hidden>
                  {icon(v, 18)}
                </span>
                {later ? (
                  <Badge className="absolute right-3 top-3">Coming soon</Badge>
                ) : null}
                <span className={`min-w-0 ${later ? "opacity-50" : ""}`}>
                  <strong className="block text-[15px] font-semibold leading-tight">{label}</strong>
                  <span className="text-xs text-muted">{about}</span>
                </span>
              </button>
            );
          })}
        </div>
        {/* The same choice as a list, for keyboard users and the browser tests. */}
        <select aria-label="Screen type" value={type} onChange={(e) => setType(e.target.value)} className="sr-only">
          {TYPES.map(([v, label]) => (
            <option key={v} value={v} disabled={soon.includes(v)}>
              {label}
              {soon.includes(v) ? " (coming soon)" : ""}
            </option>
          ))}
        </select>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Name" className={type === "table" || type === "kds" ? "" : "sm:col-span-2"}>
            <Input aria-label="Name" value={name} onChange={(e) => setName(e.target.value)} placeholder={type === "table" ? "e.g. Table T5" : type === "kds" ? "e.g. Bar kitchen" : typeName(type)} />
          </Field>
          {type === "table" ? (
            <Field label="Table number">
              <Input aria-label="Table number" value={table} onChange={(e) => setTable(e.target.value)} placeholder="T5" />
            </Field>
          ) : type === "kds" ? (
            <Field label="Kitchen station">
              <Select aria-label="Station" value={station} onChange={(e) => setStation(e.target.value)}>
                <option value="">All stations (expo)</option>
                {stations.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </Select>
            </Field>
          ) : null}
        </div>
      </form>
    </Modal>
  );
}

const QUICK: [string, string, string][] = [
  ["kiosk", "Test kiosk", "a kiosk"],
  ["cashier", "Cashier", "a POS"],
  ["kds", "Kitchen (all stations)", "a kitchen display"],
  ["status", "Status board", "a status board"],
];
const listText = (l: string[]) => (l.length > 1 ? `${l.slice(0, -1).join(", ")} and ${l[l.length - 1]}` : l[0] ?? "");

export function QuickTestCard() {
  const { admin, devices, rememberCode, refreshDevices, changed } = useSetup();
  const toast = useToast();
  const soon = useComingSoon();
  const [busy, setBusy] = useState(false);
  // Screens not offered yet (coming soon) are left out of the test wall.
  const kinds = QUICK.filter(([t]) => !soon.includes(t));
  const hasWall = !!store.get("kiosk:wall");
  const run = async () => {
    // Open the window during the click itself; browsers block pop-ups opened after awaits.
    const win = window.open("", "_blank");
    setBusy(true);
    try {
      const make = async (type: string, name: string, extra: Record<string, string> = {}) => {
        const d = await admin.api<DeviceRow>("POST", admin.v("/devices"), { type, name, ...extra });
        rememberCode(d.id, { code: d.pairing_code!, expires: d.pairing_expires_at! });
        return d;
      };
      const made: DeviceRow[] = [];
      for (const [type, name] of kinds) made.push(await make(type, type === "cashier" ? `Cashier ${devices.filter((d) => d.type === "cashier").length + 1}` : name));
      store.set(
        "kiosk:wall",
        made.map((d) => ({ label: d.name, url: screenUrl(d, d.pairing_code, admin.venue?.code) })),
      );
      await refreshDevices();
      changed();
      toast(`${made.length} screens created. Opening the test wall…`, "ok");
      if (win) win.location.href = WALL;
      else location.href = WALL; // pop-ups blocked: open the wall here instead
    } catch (x) {
      win?.close();
      toast(say((x as Error).message), "bad", 6000);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="flex flex-wrap items-center gap-3 rounded-2xl bg-surface px-5 py-4 ring-1 ring-line">
      <span className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-ink/[.05] text-ink/70">
        <FlaskConical size={20} />
      </span>
      <div className="min-w-[200px] flex-1">
        <div className="font-semibold">Quick test, no tablets needed</div>
        <div className="text-sm text-muted">Creates {listText(kinds.map(([, , what]) => what))}, and opens them side by side.</div>
      </div>
      <div className="flex items-center gap-1">
        <Button size="sm" disabled={busy} onClick={run}>
          <Zap size={16} /> Create test wall
        </Button>
        {hasWall ? <MoreMenu items={[{ label: "Re-open last test wall", icon: <ExternalLink size={18} />, onClick: () => window.open(WALL, "_blank", "noreferrer") }]} /> : null}
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ per-screen dialogs

function Footer({ onClose, onSave, label = "Save" }: { onClose: () => void; onSave: () => void; label?: string }) {
  return (
    <div className="flex justify-end gap-2">
      <Button variant="ghost" onClick={onClose}>
        Cancel
      </Button>
      <Button variant="primary" onClick={onSave}>
        {label}
      </Button>
    </div>
  );
}

function MenuModal({ d, onClose }: { d: DeviceRow; onClose: () => void }) {
  const { admin, refreshDevices } = useSetup();
  const act = useAct();
  const [cats, setCats] = useState<{ id: string; name: { en?: string } }[] | null>(null);
  const [picked, setPicked] = useState(() => new Set(d.menu_categories));
  useEffect(() => void admin.get(admin.v("/menu/categories")).then(setCats, () => setCats([])), []);
  const save = async () => {
    if (await act(() => admin.api("PATCH", admin.v(`/devices/${d.id}`), { menu_categories: [...picked] }), "Saved. The screen shows it on its next menu refresh.")) onClose(), refreshDevices();
  };
  return (
    <Modal open onClose={onClose} title={`Menu on ${d.name}`} footer={<Footer onClose={onClose} onSave={save} />}>
      <p className="mb-3 text-sm text-muted">Tick what this screen shows, e.g. a drinks-only kiosk. Nothing ticked shows the full menu.</p>
      <div className="flex flex-col gap-1">
        {cats === null
          ? [0, 1, 2].map((k) => <Skeleton key={k} className="h-11" />)
          : cats.map((c) => (
              <Check
                key={c.id}
                className="rounded-xl px-2 py-2.5 hover:bg-ink/[.035]"
                checked={picked.has(c.id)}
                onChange={(on) =>
                  setPicked((s) => {
                    const n = new Set(s);
                    on ? n.add(c.id) : n.delete(c.id);
                    return n;
                  })
                }
              >
                {en(c.name)}
              </Check>
            ))}
      </div>
    </Modal>
  );
}

// What each screen can be. An all-in-one kiosk or POS terminal brings its built-in printer, card
// reader and scanner: choosing the model sets them up (then connect + test page, test reader).
const HW_MODELS: Record<string, [string, string, string, boolean][]> = {
  kiosk: [
    ["all_in_one", "All-in-one kiosk", "Built-in receipt printer, card reader and QR scanner", true],
    ["tablet_printer", "Tablet + USB receipt printer", "Order-number slips and receipts, QR payment", false],
    ["tablet", "Tablet only", "No printer: QR payment or pay at the cashier", false],
  ],
  cashier: [
    ["pos_terminal", "POS terminal", "Built-in printer, cash drawer port, scanner, customer display", false],
    ["tablet_pos", "Tablet + USB printer + cash drawer", "", false],
  ],
  kds: [
    ["kitchen_screen", "Kitchen screen", "Splash-proof, wall mount", false],
    ["kitchen_screen_printer", "Kitchen screen + ticket printer", "Prints this station's tickets too", false],
  ],
};

function HardwareModal({ d, onClose }: { d: DeviceRow; onClose: () => void }) {
  const { admin, refreshDevices, changed } = useSetup();
  const act = useAct();
  const models = HW_MODELS[d.type];
  const [chosen, setChosen] = useState(d.hardware?.model ?? models[0][0]);
  const [serial, setSerial] = useState(d.card?.terminal_id ?? "");
  const [done, setDone] = useState<{ name: string; to_do: string[] } | null>(null);
  const reader = models.find(([c]) => c === chosen)?.[3];
  if (done)
    return (
      <Modal open onClose={onClose} title={done.name.split(" (")[0]} footer={<Button variant="primary" className="w-full" onClick={onClose}>Done</Button>}>
        {done.to_do.length ? (
          <div className="flex flex-col gap-1">
            <div className="mb-1 text-sm font-medium text-muted">Still to do on {d.name}</div>
            {done.to_do.map((t) => (
              <div key={t} className="check-row flex items-center gap-3 rounded-xl px-1 py-2 text-[15px]">
                <span className="check-mark h-5 w-5 shrink-0 rounded-full ring-2 ring-line" />
                {say(t)}
              </div>
            ))}
          </div>
        ) : (
          <p>All set.</p>
        )}
        <p className="mt-3 text-sm text-muted">The built-in printer is listed in Printers, the card reader in Payments. The screen shows “Connect printer”.</p>
      </Modal>
    );
  const save = async () => {
    const r = await act(() => admin.api<{ name: string; to_do: string[] }>("PUT", admin.v(`/devices/${d.id}/hardware`), { model: chosen, card_terminal_id: serial.trim() || null }));
    if (r) setDone(r), refreshDevices(), changed();
  };
  return (
    <Modal open onClose={onClose} title={`Hardware · ${d.name}`} footer={<Footer onClose={onClose} onSave={save} />}>
      <p className="mb-3 text-sm text-muted">What is this screen? Built-in printers and readers are set up with it.</p>
      <div className="flex flex-col gap-2">
        {models.map(([code, name, about]) => (
          <Choice key={code} data-model={code} on={chosen === code} icon={icon(d.type, 18)} title={name} about={about || undefined} onClick={() => setChosen(code)} />
        ))}
      </div>
      {reader ? (
        <Field label="Card reader serial (on its label)" className="mt-4">
          <Input aria-label="Card reader serial" value={serial} onChange={(e) => setSerial(e.target.value)} placeholder="e.g. PAX-IM30-00123" />
        </Field>
      ) : null}
    </Modal>
  );
}

function CardModal({ d, onClose }: { d: DeviceRow; onClose: () => void }) {
  const { admin, refreshDevices, changed } = useSetup();
  const act = useAct();
  const staffScreen = ["cashier", "waiter"].includes(d.type);
  const [mode, setMode] = useState<string>(d.card?.mode ?? "none");
  const [tid, setTid] = useState(d.card?.terminal_id ?? "");
  const save = async () => {
    const body: Record<string, string> = { card_mode: mode };
    if (mode === "reader") body.card_terminal_id = tid.trim();
    if (await act(() => admin.api("PATCH", admin.v(`/devices/${d.id}`), body), "Card setup saved. The screen picks it up on its next reload.")) onClose(), refreshDevices(), changed();
  };
  return (
    <Modal open onClose={onClose} title={`Card payments · ${d.name}`} footer={<Footer onClose={onClose} onSave={save} />}>
      <p className="mb-4 text-sm text-muted">
        {staffScreen
          ? "Staff screens can use a card reader or tap on phone (the tablet's own NFC)."
          : d.type === "table"
            ? "Guests alone need a certified card reader. Tap on phone works only while a waiter is logged in on it."
            : "Guest screens need a certified built-in card reader."}
      </p>
      <div className="flex flex-col gap-3">
        <Field label="Card payments">
          <Select aria-label="Card payments" value={mode} onChange={(e) => setMode(e.target.value)}>
            <option value="none">No card payments on this screen</option>
            <option value="reader">Card reader (built-in or attached, e.g. PAX IM30)</option>
            {staffScreen ? <option value="softpos">Tap on phone (this tablet, staff only)</option> : null}
            {d.type === "table" ? <option value="softpos">Tap on phone, only with a waiter logged in</option> : null}
          </Select>
        </Field>
        {mode === "reader" ? (
          <Field label="Card reader serial / terminal id">
            <Input aria-label="Terminal id" value={tid} onChange={(e) => setTid(e.target.value)} placeholder="Reader serial / terminal id" />
          </Field>
        ) : null}
      </div>
    </Modal>
  );
}
