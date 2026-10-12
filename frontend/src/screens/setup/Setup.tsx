// Setup console (installation team): a calm guided install in 7 steps, full screen in the console
// frame (ui/shell.tsx). The steps are the navigation (left rail, bottom tabs on phones); done steps
// are quietly ticked and the console opens on the first open step. Each step shows only what the
// installer needs right then; its cards fill the width.
import { consoleUrl } from "../../lib/screens";
import { AnimatePresence, motion } from "motion/react";
import { ArrowLeft, ArrowRight, Check, CreditCard, LayoutGrid, LayoutList, LogOut, Printer, Rocket, Store, Tablet, UtensilsCrossed, Users, Wifi, type LucideIcon } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import type { Admin } from "../../lib/admin";
import { HEADER_LINK, VenuePicker } from "../../ui/adminGate";
import { AppShell, type NavItem } from "../../ui/shell";
import { Badge, Button, ease, MoreMenu } from "../../ui/kit";
import { ChecklistCard } from "./Checklist";
import { EquipmentCard, NetworkCard } from "./Network";
import { PaymentsCard, PosCard } from "./Payments";
import { MenuLinkCard, StaffCard } from "./People";
import { PrintersCard } from "./Printers";
import { BranchCard, BrandCard, BusinessCard, PhotosCard, PlanCard, SettingsCard } from "./Restaurant";
import { CodeModal, QuickTestCard, ScreensCard, SignInModal } from "./Screens";
import { SetupCtx, type Checklist, type Code, type DeviceRow, type NetworkInfo, type SetupState } from "./ui";

type Step = { key: string; title: string; what: string; checks: string[]; cards: ReactNode[]; wide?: boolean; pill?: string; icon: LucideIcon };

export function Setup({ admin }: { admin: Admin }) {
  const [devices, setDevices] = useState<DeviceRow[]>([]);
  const [stations, setStations] = useState<string[]>([]);
  const [network, setNetwork] = useState<NetworkInfo | null>(null);
  const [checklist, setChecklist] = useState<Checklist | null>(null);
  const [codes, setCodes] = useState<Record<string, Code>>({});
  const [tick, setTick] = useState(0);
  const [code, setCode] = useState<{ d: DeviceRow; code: string; expires?: string } | null>(null);
  const [signIn, setSignIn] = useState<DeviceRow | null>(null);

  const refreshDevices = useCallback(async () => {
    try {
      setDevices(await admin.get<DeviceRow[]>(admin.v("/devices")));
    } catch {
      /* next poll */
    }
  }, [admin]);
  const loadChecklist = useCallback(() => admin.get<Checklist>(admin.v("/setup-checklist")).then(setChecklist, () => {}), [admin]);
  const changed = useCallback(() => {
    void loadChecklist();
    setTick((t) => t + 1);
  }, [loadChecklist]);

  useEffect(() => {
    void refreshDevices();
    void loadChecklist();
    admin.get<{ station: string }[]>(admin.v("/menu/items")).then((items) => setStations([...new Set(items.map((i) => i.station).filter(Boolean))].sort()), () => {});
    const fast = setInterval(refreshDevices, 4000);
    // Printers, the hub and the checklist change as screens and printers come online.
    const slow = setInterval(() => {
      if (document.querySelector("[role=dialog]")) return;
      void loadChecklist();
      setTick((t) => t + 1);
    }, 8000);
    return () => (clearInterval(fast), clearInterval(slow));
  }, []);

  const ctx: SetupState = {
    admin,
    devices,
    stations,
    network,
    setNetwork,
    checklist,
    codes,
    rememberCode: useCallback((id: string, c: Code) => setCodes((x) => ({ ...x, [id]: c })), []),
    refreshDevices,
    changed,
    tick,
    showCode: useCallback((d: DeviceRow, c: string, expires?: string) => setCode({ d, code: c, expires }), []),
    showSignIn: useCallback((d: DeviceRow) => setSignIn(d), []),
  };

  const hasBridge = !admin.venue?.plan?.modules || admin.venue.plan.modules.includes("R-BRIDGE");
  const STEPS: Step[] = useMemo(
    () => [
      { key: "restaurant", title: "Restaurant", icon: Store, what: "Check the package and fill in the business details.", checks: ["business"], cards: [<BrandCard key="brand" />, <PlanCard key="plan" />, <BusinessCard key="biz" />, <SettingsCard key="set" />, <PhotosCard key="photos" />, <BranchCard key="branch" />] },
      { key: "menu", title: "Menu & staff", icon: Users, what: "Put the menu in and give every staff member a PIN.", checks: ["menu", "taxes", "staff"], cards: [<MenuLinkCard key="menu" />, <StaffCard key="staff" />] },
      { key: "network", title: "Network & equipment", pill: "Network", icon: Wifi, what: "Cloud or hybrid, and tick the equipment that is in place.", checks: ["network", "equipment"], cards: [<NetworkCard key="net" />, <EquipmentCard key="kit" />] },
      { key: "screens", title: "Screens", icon: Tablet, what: "Sign each tablet in with its screen code.", checks: ["screens", "kiosks"], wide: true, cards: [<ScreensCard key="list" />, <QuickTestCard key="quick" />] },
      { key: "payments", title: "Payments", icon: CreditCard, what: "Ways to pay, the QR payment account, and a test of every card reader.", checks: ["payments", "card_readers"], cards: [<PaymentsCard key="pay" />, hasBridge ? <PosCard key="pos" /> : null] },
      { key: "printers", title: "Printers", icon: Printer, what: "Add each printer, connect it and print the test page.", checks: ["printers"], wide: true, cards: [<PrintersCard key="printers" />] },
      { key: "golive", title: "Test & go live", pill: "Go live", icon: Rocket, what: "Run one real order through every path. When everything is ticked, the restaurant is ready.", checks: ["test_order"], wide: true, cards: [<ChecklistCard key="golive" onJump={(k) => jumpTo(k)} />] },
    ],
    [hasBridge],
  );

  const params = new URLSearchParams(location.search);
  const [showAll, setShowAll] = useState(params.get("view") === "all");
  const [current, setCurrent] = useState(() => (STEPS.some((s) => s.key === params.get("step")) ? params.get("step")! : "restaurant"));
  const jumped = useRef(!!params.get("step") || showAll); // open on the first unfinished step, once

  const stepDone = (st: Step) => {
    if (!checklist) return false;
    if (st.key === "golive") return checklist.ready;
    const mine = checklist.items.filter((i) => st.checks.includes(i.key));
    return mine.length > 0 && mine.every((i) => i.done);
  };
  const openCount = (st: Step) => (checklist ? checklist.items.filter((i) => st.checks.includes(i.key) && !i.done).length : 0);

  const show = (key: string, all = false) => {
    setCurrent(key);
    setShowAll(all);
    const url = new URL(location.href);
    url.searchParams.delete("venue");
    if (all) url.searchParams.set("view", "all"), url.searchParams.delete("step");
    else url.searchParams.set("step", key), url.searchParams.delete("view");
    history.replaceState(null, "", url);
    document.querySelector("main")?.scrollTo({ top: 0 });
  };
  function jumpTo(key: string) {
    show(STEPS.find((st) => st.checks.includes(key))?.key ?? "golive");
  }
  useEffect(() => {
    if (jumped.current || !checklist) return;
    jumped.current = true;
    const first = STEPS.find((st) => !stepDone(st));
    setCurrent(first?.key ?? "golive");
  }, [checklist]);

  const i = STEPS.findIndex((s) => s.key === current);
  const st = STEPS[i];
  const done = stepDone(st);
  const open = openCount(st);
  const next = STEPS[i + 1];

  const pct = checklist ? Math.round((checklist.done / Math.max(1, checklist.total)) * 100) : 0;
  const nav: NavItem[] = STEPS.map((s) => {
    const isDone = stepDone(s);
    const left = openCount(s);
    const on = !showAll && s.key === current;
    return {
      key: s.key,
      label: s.pill ?? s.title,
      icon: s.icon,
      className: `step-pill ${on ? "active" : ""} ${isDone ? "done" : "todo"}`,
      dot: isDone ? "ok" : null,
      trail: isDone ? (
        <span aria-label="Done" className="grid h-5 w-5 place-items-center rounded-full bg-ok-soft text-ok">
          <Check size={12} strokeWidth={3.2} />
        </span>
      ) : left ? (
        <span className="text-xs font-medium text-muted">{left} to do</span>
      ) : null,
    };
  });
  const venue = admin.venue;

  return (
    <SetupCtx.Provider value={ctx}>
      <AppShell
        name={venue?.name ?? "Setup"}
        sub="Setup console"
        logo={venue?.settings?.logo_url}
        nav={nav}
        active={showAll ? "" : current}
        onNav={(k) => show(k)}
        scrollTabs
        title={
          showAll ? (
            "Everything"
          ) : (
            <span className="flex min-w-0 items-center gap-2.5">
              <span className="truncate">{st.title}</span>
              {done ? (
                <Badge tone="ok">
                  <Check size={13} strokeWidth={3} /> Done
                </Badge>
              ) : open ? (
                <Badge>{open} to do</Badge>
              ) : null}
            </span>
          )
        }
        account={
          <div className="flex shrink-0 items-center gap-1">
            <VenuePicker admin={admin} />
            <span className="hidden items-center gap-1 md:flex">
              <a className={HEADER_LINK} href={`${consoleUrl("menu", venue?.code)}?as=installer`}>
                <UtensilsCrossed size={16} /> Menu
              </a>
              <a className={HEADER_LINK} href="/platform">
                <LayoutGrid size={16} /> Platform
              </a>
            </span>
            <MoreMenu
              items={[
                { label: "Menu editor", icon: <UtensilsCrossed size={18} />, onClick: () => (location.href = `${consoleUrl("menu", venue?.code)}?as=installer`) },
                { label: "Platform console", icon: <LayoutGrid size={18} />, onClick: () => (location.href = "/platform") },
                showAll ? { label: "Back to the steps", icon: <ArrowLeft size={18} />, onClick: () => show(current) } : { label: "Show everything", icon: <LayoutList size={18} />, onClick: () => show(current, true) },
                { label: "Log out", icon: <LogOut size={18} />, onClick: () => (admin.logout(), location.reload()) },
              ]}
            />
          </div>
        }
        footer={
          <div title={checklist ? `${checklist.done} of ${checklist.total} checks done` : undefined}>
            <div className="flex items-baseline justify-between text-[13px]">
              <span className="font-semibold">Ready to go live</span>
              <span className="num text-muted">{checklist ? `${checklist.done} of ${checklist.total}` : ""}</span>
            </div>
            <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-ink/[.06]">
              <motion.div className="h-full rounded-full bg-ok" initial={false} animate={{ width: `${pct}%` }} transition={ease} />
            </div>
          </div>
        }
      >
        <div className="mx-auto flex w-full max-w-[1680px] flex-col gap-5">
          {showAll ? (
            <>
              <div className="flex flex-wrap items-center gap-3">
                <p className="mr-auto text-[15px] text-muted">Every step on one page.</p>
                <Button variant="ghost" onClick={() => show(current)}>
                  <ArrowLeft size={18} /> Back to the steps
                </Button>
              </div>
              {STEPS.map((s, n) => (
                <section key={s.key} className="flex flex-col gap-3">
                  <h2 className="mt-3 text-sm font-semibold text-muted">
                    {n + 1}. {s.title}
                  </h2>
                  <Grid wide={s.wide}>{s.cards}</Grid>
                </section>
              ))}
            </>
          ) : (
            <AnimatePresence mode="wait" initial={false}>
              <motion.div key={st.key} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -4 }} transition={ease} className="flex flex-col gap-5">
                <div className="step-head flex flex-wrap items-baseline gap-x-3 gap-y-1">
                  <span className="text-sm font-semibold text-accent">
                    Step {i + 1} of {STEPS.length}
                  </span>
                  <p className="text-[15px] text-muted">{st.what}</p>
                </div>
                <Grid wide={st.wide}>{st.cards}</Grid>
                <div className="flex items-center gap-2 border-t border-line pt-4">
                  {i > 0 ? (
                    <Button variant="ghost" onClick={() => show(STEPS[i - 1].key)}>
                      <ArrowLeft size={18} /> {STEPS[i - 1].pill ?? STEPS[i - 1].title}
                    </Button>
                  ) : null}
                  {next ? (
                    <Button variant={done ? "primary" : "default"} className="ml-auto" onClick={() => show(next.key)}>
                      Next: {next.pill ?? next.title} <ArrowRight size={18} />
                    </Button>
                  ) : null}
                </div>
              </motion.div>
            </AnimatePresence>
          )}
        </div>
      </AppShell>
      {signIn ? <SignInModal d={devices.find((x) => x.id === signIn.id) ?? signIn} onClose={() => setSignIn(null)} /> : null}
      {code ? <CodeModal d={code.d} code={code.code} expires={code.expires} onClose={() => setCode(null)} /> : null}
    </SetupCtx.Provider>
  );
}

/** Cards flow into balanced columns that fill the width (1 → 2 → 3); list steps get a full-width
 * main card. Columns (not a grid) so short cards never leave ragged gaps; the look editor spans all. */
function Grid({ children, wide }: { children: ReactNode[]; wide?: boolean }) {
  const cards = children.filter(Boolean);
  if (wide || cards.length < 2) return <div className="step-grid flex flex-col gap-4">{cards}</div>;
  const cols = cards.length >= 5 ? "xl:columns-2 min-[1760px]:columns-3" : "lg:columns-2";
  return <div className={`step-grid gap-4 ${cols} [&>*]:mb-4 [&>*]:break-inside-avoid [&>.brand-editor]:[column-span:all]`}>{cards}</div>;
}
