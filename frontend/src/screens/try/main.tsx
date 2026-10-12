// The public demo (/try on a demo server): every screen of the demo restaurant one tap away, with the
// staff PINs and logins shown. Each tap signs in a fresh screen and opens it in a new tab, so a table,
// the kitchen and the waiter app can sit side by side and show an order moving live.
import { motion } from "motion/react";
import { BookOpen, ChefHat, Check, Copy, LayoutGrid, Monitor, Settings2, Smartphone, Store, Tablet, Tv, UtensilsCrossed, type LucideIcon } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import "../../ui/theme.css";
import { request } from "../../lib/net";
import { screenAddress } from "../../lib/screens";
import { store } from "../../lib/store";
import { ProductMark } from "../../ui/adminGate";
import { spring, ToastProvider, useToast } from "../../ui/kit";

type Info = {
  venue: { code: string; name: string };
  style: "sit_down" | "quick" | "custom";
  tables: string[];
  staff: { name: string; role: string; pin: string }[];
  owner: { email: string; password: string };
  team: { email: string; password: string };
};
type Opened = { device_token: string; device: { id: string; type: string; venue_code: string; table_ref: string | null } };
// Where each screen keeps its key in this browser (the same keys the screens read).
const PAGE: Record<string, string> = { cashier: "cashier", waiter: "waiter", kds: "kds", kiosk: "kiosk", status: "status", table: "table" };

function Try() {
  const toast = useToast();
  const [info, setInfo] = useState<Info | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  useEffect(() => {
    document.documentElement.dataset.theme = "light";
    request<Info>("GET", "/v1/demo").then(setInfo).catch((e) => toast((e as Error).message, "bad"));
  }, []);

  /** A fresh screen of this type, signed in, in a new tab (its own slot, so many can run at once). */
  const open = async (type: string, table?: string) => {
    const win = window.open("about:blank", "_blank"); // opened on the tap itself, so it isn't blocked
    setBusy(type + (table ?? ""));
    try {
      const r = await request<Opened>("POST", "/v1/demo/screen", { body: { type, table_ref: table ?? null } });
      const slot = (table ?? type).toLowerCase() + "-" + r.device.id.slice(0, 4);
      store.set(`kiosk:dev:${PAGE[type]}:${slot}`, { token: r.device_token, device: r.device });
      const url = screenAddress(type, slot, r.device.venue_code);
      if (win) win.location.href = url;
      else location.href = url;
    } catch (e) {
      win?.close();
      toast((e as Error).message, "bad");
    } finally {
      setBusy(null);
    }
  };
  const style = async (s: "sit_down" | "quick") => {
    await request("POST", "/v1/demo/style", { body: { style: s } }).catch((e) => toast((e as Error).message, "bad"));
    setInfo((i) => (i ? { ...i, style: s } : i));
    toast("Every open screen follows now", "ok");
  };
  const pin = (role: string) => info?.staff.find((s) => s.role === role);
  const code = info?.venue.code ?? "demo";

  return (
    <div className="min-h-full bg-canvas text-ink">
      <header className="border-b border-line bg-surface">
        <div className="mx-auto flex h-16 max-w-6xl items-center gap-3 px-4 sm:px-6">
          <ProductMark size={34} />
          <span className="text-[17px] font-bold tracking-tight">Kiosk Platform</span>
          <span className="rounded-full bg-accent-soft px-2.5 py-0.5 text-xs font-bold text-accent">Demo</span>
          <span className="flex-1" />
          <span className="hidden text-sm text-muted sm:inline">{info?.venue.name}</span>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-4 pb-16 pt-8 sm:px-6">
        <motion.section initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={spring}>
          <h1 className="text-[32px] font-bold leading-tight tracking-[-0.02em] sm:text-[40px]">Try every screen</h1>
          <p className="mt-2 max-w-[62ch] text-[17px] text-muted">Each one opens in a new tab. Put a table, the kitchen and the waiter app side by side: an order on the table shows up in the kitchen at once, and every step comes back to the table live.</p>
        </motion.section>

        <section className="mt-8 rounded-2xl bg-surface p-5 ring-1 ring-line sm:p-6">
          <h2 className="font-bold">How the restaurant works</h2>
          <p className="mt-0.5 text-sm text-muted">Switch any time; open screens change with it.</p>
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <Style on={info?.style === "sit_down"} title="Sit-down restaurant" sub="Order in rounds · the waiter brings the food · pay at the end (cash, card or QR)" onClick={() => style("sit_down")} />
            <Style on={info?.style === "quick"} title="Quick service" sub="Pay first (QR, card or at the counter) · the kitchen starts · collect at the counter" onClick={() => style("quick")} />
          </div>
        </section>

        <Group title="Guests" sub="What guests use: the tablet on each table.">
          <div className="grid grid-cols-3 gap-3 sm:grid-cols-6">
            {(info?.tables ?? []).map((t) => (
              <button key={t} data-try={`table-${t}`} disabled={!!busy} onClick={() => open("table", t)} className="flex h-24 flex-col items-center justify-center gap-1.5 rounded-2xl bg-surface ring-1 ring-line transition hover:ring-ink/30 active:scale-[.98] disabled:opacity-60">
                <Tablet size={22} className="text-muted" />
                <span className="font-bold">Table {t}</span>
              </button>
            ))}
          </div>
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            <Card icon={Monitor} title="Self-order kiosk" sub="Order and pay without staff" onClick={() => open("kiosk")} busy={busy === "kiosk"} />
            <Card icon={Tv} title="Order status board" sub="Order numbers on a TV: cooking, ready" onClick={() => open("status")} busy={busy === "status"} />
          </div>
        </Group>

        <Group title="Staff" sub="Each person logs in on the screen with their own PIN.">
          <div className="grid gap-3 sm:grid-cols-3">
            <Card icon={Store} title="POS" sub="Counter till: orders, cash, card, receipts" pin={pin("cashier")} onClick={() => open("cashier")} busy={busy === "cashier"} />
            <Card icon={Smartphone} title="Waiter app" sub="Tables, calls, bills, food to serve" pin={pin("waiter")} onClick={() => open("waiter")} busy={busy === "waiter"} />
            <Card icon={ChefHat} title="Kitchen display" sub="Tickets, cooking times, ready" onClick={() => open("kds")} busy={busy === "kds"} note="No PIN needed" />
          </div>
          {pin("manager") ? <p className="mt-3 text-sm text-muted">Manager PIN for refunds and voids: {pin("manager")?.name} · <b className="num text-ink">{pin("manager")?.pin}</b></p> : null}
        </Group>

        <Group title="Management" sub="Web consoles. The demo logins are filled in for you.">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Card icon={LayoutGrid} title="Owner app" sub="Sales, staff, tables, feedback" login={info?.owner} href={`/${code}/owner`} />
            <Card icon={BookOpen} title="Menu editor" sub="Dishes, prices, photos, sold out" login={info?.owner} href={`/${code}/menu`} />
            <Card icon={Settings2} title="Setup console" sub="Screens, printers, payments, go live" login={info?.team} href={`/${code}/setup`} />
            <Card icon={UtensilsCrossed} title="Platform" sub="Every restaurant and its package" login={info?.team} href="/platform" />
          </div>
        </Group>

        <section className="mt-10 rounded-2xl bg-surface p-5 ring-1 ring-line sm:p-6">
          <h2 className="font-bold">A two-minute walkthrough</h2>
          <ol className="mt-3 grid gap-2 text-[15px] text-ink/85 sm:grid-cols-2">
            {[
              "Open Table T1, the Kitchen display and the Waiter app.",
              "On the table, add two dishes and send them to the kitchen.",
              "In the kitchen, tap the dishes, then Bump: the table shows On its way.",
              "In the waiter app (Priya, 3333), mark it served. The table says Enjoy your meal.",
              "On the table, Ask for the bill and choose Cash.",
              "In the waiter app, take the payment. The table thanks the guests; the waiter sees Needs cleaning.",
            ].map((s, k) => (
              <li key={k} className="flex gap-3">
                <span className="num grid h-6 w-6 shrink-0 place-items-center rounded-full bg-ink text-xs font-bold text-white">{k + 1}</span>
                {s}
              </li>
            ))}
          </ol>
          <p className="mt-4 text-sm text-muted">This is a demo: payments are pretend (tap “Simulate payment” on a QR or card screen), and everything resets every night.</p>
        </section>
      </main>
    </div>
  );
}

function Group({ title, sub, children }: { title: string; sub: string; children: ReactNode }) {
  return (
    <section className="mt-10">
      <h2 className="text-xl font-bold tracking-tight">{title}</h2>
      <p className="mb-4 mt-0.5 text-[15px] text-muted">{sub}</p>
      {children}
    </section>
  );
}

function Style({ on, title, sub, onClick }: { on: boolean; title: string; sub: string; onClick: () => void }) {
  return (
    <button onClick={onClick} aria-pressed={on} className={`flex items-start gap-3 rounded-xl p-4 text-left ring-1 transition ${on ? "bg-accent-soft ring-accent" : "ring-line hover:ring-ink/30"}`}>
      <span className={`mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-full ${on ? "bg-accent text-white" : "ring-1 ring-line"}`}>{on ? <Check size={13} strokeWidth={3} /> : null}</span>
      <span>
        <span className="block font-semibold">{title}</span>
        <span className="block text-sm text-muted">{sub}</span>
      </span>
    </button>
  );
}

function Card({ icon: Icon, title, sub, onClick, href, busy, pin, login, note }: { icon: LucideIcon; title: string; sub: string; onClick?: () => void; href?: string; busy?: boolean; pin?: { name: string; pin: string }; login?: { email: string; password: string }; note?: string }) {
  const toast = useToast();
  const body = (
    <>
      <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-canvas">
        <Icon size={21} />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block font-semibold">{busy ? "Opening…" : title}</span>
        <span className="block text-sm text-muted">{sub}</span>
      </span>
    </>
  );
  const cls = "flex w-full items-center gap-3.5 p-4 text-left transition active:scale-[.99]";
  return (
    <div className="flex flex-col overflow-hidden rounded-2xl bg-surface ring-1 ring-line transition hover:ring-ink/30">
      {href ? (
        <a href={href} target="_blank" rel="noopener" className={cls}>
          {body}
        </a>
      ) : (
        <button disabled={busy} onClick={onClick} className={cls}>
          {body}
        </button>
      )}
      {pin || login || note ? (
        <div className="flex items-center gap-2 border-t border-line bg-subtle px-4 py-2.5 text-[13px] text-muted">
          {pin ? (
            <span>
              Log in as <b className="text-ink">{pin.name}</b> · PIN <b className="num text-ink">{pin.pin}</b>
            </span>
          ) : login ? (
            <>
              <span className="min-w-0 flex-1 truncate">
                <b className="text-ink">{login.email}</b> · {login.password}
              </span>
              <button aria-label="Copy password" onClick={() => navigator.clipboard?.writeText(login.password).then(() => toast("Password copied", "ok"))} className="grid h-7 w-7 place-items-center rounded-lg hover:bg-line">
                <Copy size={14} />
              </button>
            </>
          ) : (
            note
          )}
        </div>
      ) : null}
    </div>
  );
}

createRoot(document.getElementById("root")!).render(
  <ToastProvider>
    <Try />
  </ToastProvider>,
);
