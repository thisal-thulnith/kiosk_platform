// Owner app: how the restaurant is doing, live, on the owner's phone or laptop. A full-screen console
// (ui/shell AppShell) with five places: Today (sales, kitchen, service), Staff (people, tables,
// feedback), Money (payments, accounting, bank check), Menu & stock, and Settings (look, screens, AI, guests).
import { consoleUrl } from "../../lib/screens";
import { motion } from "motion/react";
import { BarChart3, LogOut, Settings, ShoppingBasket, Store, UsersRound, UtensilsCrossed, Wallet } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import type { Admin } from "../../lib/admin";
import { VenuePicker } from "../../ui/adminGate";
import { MoreMenu, Status, useToast } from "../../ui/kit";
import { AppShell, type NavItem } from "../../ui/shell";
import { RangePicker, presets, rangeText, type Range } from "./bits";
import { MoneyPage } from "./money";
import { SettingsPage, StockPage } from "./more";
import { StaffPage } from "./staff";
import { TodayPage } from "./today";

type Tab = "today" | "staff" | "money" | "stock" | "settings";
const NAV: (NavItem & { key: Tab })[] = [
  { key: "today", label: "Today", icon: BarChart3 },
  { key: "staff", label: "Staff", icon: UsersRound },
  { key: "money", label: "Money", icon: Wallet },
  { key: "stock", label: "Menu & stock", icon: ShoppingBasket },
  { key: "settings", label: "Settings", icon: Settings },
];
/** Old links (#payments, #look…) still open the right place. */
const OLD: Record<string, string> = { sales: "today", service: "today", tables: "staff/tables", payments: "money/payments", accounting: "money/accounting", look: "settings/look", screens: "settings/screens", ai: "settings/ai", guests: "settings/guests" };

export type Ctx = { admin: Admin; range: Range; tick: number };
export type SubProps = { sub: string; setSub: (s: string) => void };

export function Owner({ admin }: { admin: Admin }) {
  const venue = admin.venue!;
  const tz = venue.timezone || "Asia/Colombo";
  const [where, setWhere] = useState(() => {
    const h = location.hash.slice(1);
    const w = OLD[h] ?? h;
    return NAV.some((t) => t.key === w.split("/")[0]) ? w : "today";
  });
  const [tab, sub = ""] = where.split("/") as [Tab, string?];
  const [range, setRange] = useState<Range>(presets(tz).today);
  const [tick, setTick] = useState(0);
  const [updated, setUpdated] = useState(new Date());
  const [, redraw] = useState(0); // the rail's logo follows a saved look
  useEffect(() => {
    const h = setInterval(() => (setTick((t) => t + 1), setUpdated(new Date())), 20000);
    return () => clearInterval(h);
  }, []);
  useEffect(() => history.replaceState(null, "", `#${where}`), [where]);
  const open = (w: string) => (setWhere(w), document.querySelector("main")?.scrollTo({ top: 0 }));
  const ctx: Ctx = { admin, range, tick };
  const subProps: SubProps = { sub, setSub: (s) => setWhere(`${tab}/${s}`) };
  const picker = <RangePicker tz={tz} value={range} onChange={setRange} />;
  const menuUrl = consoleUrl("menu", venue.code);
  const isToday = range.from === presets(tz).today.from && range.to === presets(tz).today.to;

  const title =
    tab === "today" ? (
      <>
        {rangeText(range)}
        {isToday ? <span className="ml-2.5 hidden text-[15px] font-medium text-muted lg:inline">{new Date().toLocaleDateString([], { weekday: "long", day: "numeric", month: "long" })}</span> : null}
      </>
    ) : (
      NAV.find((n) => n.key === tab)!.label
    );
  const actions =
    tab === "today" ? (
      picker
    ) : tab === "staff" ? (
      picker
    ) : tab === "stock" ? (
      <a href={menuUrl} className="inline-flex h-11 items-center gap-2 rounded-xl bg-surface px-4 text-[15px] font-semibold text-ink ring-1 ring-line transition hover:bg-canvas active:scale-[.97]">
        <UtensilsCrossed size={18} /> Open menu editor
      </a>
    ) : null;

  return (
    <AppShell
      name={venue.name}
      sub="Owner"
      logo={venue.settings?.logo_url}
      nav={NAV}
      active={tab}
      onNav={(k) => open(k)}
      title={title}
      actions={actions}
      account={
        <div className="flex items-center gap-1">
          <span className="hidden sm:inline-flex">
            <VenuePicker admin={admin} />
          </span>
          <MoreMenu
            items={[
              ...admin.venues.filter((v) => v.id !== venue.id).map((v) => ({ label: `Open ${v.name}`, icon: <Store size={18} />, onClick: () => admin.chooseVenue(v.id) })),
              { label: "Menu editor", icon: <UtensilsCrossed size={18} />, onClick: () => (location.href = menuUrl) },
              { label: "Log out", icon: <LogOut size={18} />, onClick: () => (admin.logout(), location.reload()) },
            ]}
          />
        </div>
      }
      footer={
        <Status tone="ok" pulse>
          Live · updated {updated.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
        </Status>
      }
    >
      <motion.div key={tab} className="mx-auto w-full max-w-[1800px]" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.24, ease: [0.22, 1, 0.36, 1] }}>
        {tab === "today" ? <TodayPage ctx={ctx} open={open} /> : null}
        {tab === "staff" ? <StaffPage ctx={ctx} {...subProps} /> : null}
        {tab === "money" ? <MoneyPage ctx={ctx} {...subProps} /> : null}
        {tab === "stock" ? <StockPage {...ctx} /> : null}
        {tab === "settings" ? <SettingsPage ctx={ctx} {...subProps} onLook={() => redraw((n) => n + 1)} /> : null}
      </motion.div>
    </AppShell>
  );
}

/** Load a report for the page; reloads with the period and every 20 seconds. `ranged` may be a fixed period.
 *  `quiet`: a report that may not exist on this server (no error message; the page just leaves it out). */
export function useReport<T>(ctx: Ctx, path: string | null, ranged: boolean | Range = true, quiet = false): [T | null, () => void, boolean] {
  const toast = useToast();
  const [data, setData] = useState<T | null>(null);
  const [failed, setFailed] = useState(false);
  const r = ranged === true ? ctx.range : ranged || null;
  const q = r ? `${path?.includes("?") ? "&" : "?"}from=${r.from}&to=${r.to}` : "";
  const load = useCallback(() => {
    if (!path) return;
    ctx.admin
      .get<T>(ctx.admin.v(path) + q)
      .then((d) => (setData(d), setFailed(false)))
      .catch((e) => (setFailed(true), quiet || toast((e as Error).message, "bad")));
  }, [path, q]);
  useEffect(() => setData(null), [path, q]); // a new period shows skeletons, not the old numbers
  useEffect(load, [load, ctx.tick]);
  return [data, load, failed];
}
