// The full-screen frame of every console (Owner, Menu, Setup, Platform), like Meta Business Suite:
// a navigation rail on the left (labels on desktop, icons on tablets), bottom tabs on phones, and a
// top bar with the page title and its actions. The content fills the rest of the screen.
import { motion } from "motion/react";
import type { LucideIcon } from "lucide-react";
import { useEffect, useRef, type ReactNode } from "react";
import { Logo } from "./logo";
import { spring } from "./kit";

export type NavItem = {
  key: string;
  label: string;
  icon: LucideIcon;
  badge?: number | string | null;
  /** Optional: extra classes on this item's buttons (rail and phone tabs), e.g. hooks for tests. */
  className?: string;
  /** Optional: a quiet trailing mark on the full rail (instead of the red badge), e.g. a done tick. */
  trail?: ReactNode;
  /** Optional: a small state dot on the icon (icon rail and phone tabs). */
  dot?: "ok" | "warn" | "bad" | null;
};
const DOT = { ok: "bg-ok", warn: "bg-warn", bad: "bg-bad" } as const;

export function AppShell({
  name,
  sub,
  logo,
  mark,
  nav,
  active,
  onNav,
  title,
  actions,
  account,
  footer,
  scrollTabs = false,
  children,
}: {
  name: string; // restaurant or product name, top of the rail
  sub?: string; // e.g. "Owner" / "Setup console"
  logo?: string | null;
  /** Optional: a mark of its own instead of the restaurant logo (our Platform console). */
  mark?: ReactNode;
  nav: NavItem[];
  active: string;
  onNav: (key: string) => void;
  title: ReactNode; // the page title in the top bar
  actions?: ReactNode; // the page's buttons, right of the title
  account?: ReactNode; // venue picker, ⋯ menu… (top right)
  footer?: ReactNode; // bottom of the rail (e.g. "Live" status)
  /** Phones: all items as sideways-scrolling tabs (default: the first five). */
  scrollTabs?: boolean;
  children: ReactNode;
}) {
  const tabs = useRef<HTMLElement>(null);
  useEffect(() => {
    // Scrolling phone tabs: keep the current one in view.
    if (!scrollTabs || !tabs.current) return;
    const el = tabs.current.querySelector<HTMLElement>("[aria-current=page]");
    if (el) tabs.current.scrollTo({ left: el.offsetLeft - (tabs.current.clientWidth - el.clientWidth) / 2, behavior: "smooth" });
  }, [active, scrollTabs]);
  return (
    <div className="flex h-full min-h-0 bg-canvas">
      {/* Rail: full on desktop, icons only on tablets, hidden on phones. */}
      <aside className="hidden w-[76px] shrink-0 flex-col border-r border-line bg-surface md:flex xl:w-[248px]">
        <div className="flex h-16 items-center gap-3 px-4 xl:px-5">
          {mark ?? <Logo url={logo} name={name} size={36} />}
          <div className="hidden min-w-0 xl:block">
            <div className="truncate text-[15px] font-bold leading-tight">{name}</div>
            {sub ? <div className="truncate text-xs text-muted">{sub}</div> : null}
          </div>
        </div>
        <nav className="flex flex-1 flex-col gap-0.5 overflow-y-auto px-3 py-2" aria-label="Sections">
          {nav.map((n) => {
            const on = n.key === active;
            return (
              <button key={n.key} data-nav={n.key} onClick={() => onNav(n.key)} title={n.label} aria-current={on ? "page" : undefined} className={`${n.className ?? ""} group relative flex h-11 items-center gap-3 rounded-xl px-3 text-[15px] font-semibold transition-colors ${on ? "text-accent" : "text-ink/80 hover:bg-canvas"} justify-center xl:justify-start`}>
                {on ? <motion.span layoutId="shell-nav" transition={spring} className="absolute inset-0 rounded-xl bg-accent-soft" /> : null}
                <n.icon size={20} strokeWidth={on ? 2.4 : 2} className="relative shrink-0" />
                <span className="relative hidden truncate xl:inline">{n.label}</span>
                {n.trail ? <span className="relative ml-auto hidden shrink-0 xl:inline-flex">{n.trail}</span> : null}
                {n.badge && !n.trail ? <span className="relative ml-auto hidden min-w-5 rounded-full bg-bad px-1.5 text-center text-xs font-bold leading-5 text-white xl:inline">{n.badge}</span> : null}
                {n.badge || n.dot ? <span className={`absolute right-2 top-2 h-2 w-2 rounded-full xl:hidden ${n.dot ? DOT[n.dot] : "bg-bad"}`} /> : null}
              </button>
            );
          })}
        </nav>
        {footer ? <div className="hidden border-t border-line px-5 py-3 xl:block">{footer}</div> : null}
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 flex min-h-16 items-center gap-3 border-b border-line bg-surface/95 px-4 backdrop-blur sm:px-6">
          <span className="md:hidden">
            {mark ?? <Logo url={logo} name={name} size={32} />}
          </span>
          <div className="min-w-0 flex-1">
            <h1 className="truncate text-lg font-bold tracking-[-0.01em] sm:text-xl">{title}</h1>
          </div>
          {actions ? <div className="hidden items-center gap-2 sm:flex">{actions}</div> : null}
          {account}
        </header>
        <main className="relative min-h-0 flex-1 overflow-y-auto px-4 pb-24 pt-5 sm:px-6 md:pb-8">
          {actions ? <div className="mb-4 flex flex-wrap items-center gap-2 sm:hidden">{actions}</div> : null}
          {children}
        </main>
        {/* Phones: bottom tabs. */}
        <nav ref={tabs} className={`fixed inset-x-0 bottom-0 z-30 flex border-t ${scrollTabs ? "overflow-x-auto [scrollbar-width:none]" : ""} border-line bg-surface/95 pb-[env(safe-area-inset-bottom,0px)] backdrop-blur md:hidden`} aria-label="Sections">
          {(scrollTabs ? nav : nav.slice(0, 5)).map((n) => {
            const on = n.key === active;
            return (
              <button key={n.key} data-nav={n.key} onClick={() => onNav(n.key)} aria-current={on ? "page" : undefined} className={`${n.className ?? ""} relative flex h-16 flex-1 ${scrollTabs ? "min-w-[76px] shrink-0" : ""} flex-col items-center justify-center gap-1 text-[11px] font-semibold ${on ? "text-accent" : "text-muted"}`}>
                <n.icon size={22} strokeWidth={on ? 2.4 : 2} />
                <span className="max-w-full truncate px-1">{n.label}</span>
                {n.badge || n.dot ? <span className={`absolute right-[calc(50%-18px)] top-2 h-2 w-2 rounded-full ${n.dot ? DOT[n.dot] : "bg-bad"}`} /> : null}
              </button>
            );
          })}
        </nav>
      </div>
    </div>
  );
}

/** A page's content grid: fills the width; cards flow into 1 / 2 / 3 columns. */
export function PageGrid({ children, cols = 3, className = "" }: { children: ReactNode; cols?: 2 | 3 | 4; className?: string }) {
  const c = { 2: "lg:grid-cols-2", 3: "lg:grid-cols-2 2xl:grid-cols-3", 4: "sm:grid-cols-2 xl:grid-cols-4" }[cols];
  return <div className={`grid gap-4 ${c} ${className}`}>{children}</div>;
}
