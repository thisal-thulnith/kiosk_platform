// Order status board (optional wall screen): numbers being prepared, and numbers ready to collect.
// A number glides from "Preparing" over to "Ready for pickup" when the kitchen finishes it.
import { AnimatePresence, LayoutGroup, motion } from "motion/react";
import { ChefHat, PackageCheck } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import type { Device } from "../../lib/device";
import { clock } from "../../lib/format";
import { chime } from "../../lib/sound";
import type { Me } from "../../lib/types";
import { useLive } from "../../ui/hooks";
import { LivePill } from "../../ui/kit";
import { Logo } from "../../ui/logo";

type Row = { token: string; table_ref: string | null };
const glide = { type: "spring", stiffness: 260, damping: 30, mass: 0.9 } as const;

export function StatusBoard({ device, me }: { device: Device; me: Me }) {
  const [board, setBoard] = useState<{ preparing: Row[]; ready: Row[] }>({ preparing: [], ready: [] });
  const seen = useRef(new Set<string>());
  const load = useCallback(async () => {
    const b = await device.get<{ preparing: Row[]; ready: Row[] }>("/v1/status-board");
    const fresh = b.ready.filter((r) => !seen.current.has(r.token));
    if (fresh.length && seen.current.size) chime([880, 1320]);
    b.ready.forEach((r) => seen.current.add(r.token));
    setBoard(b);
  }, [device]);
  useEffect(() => {
    void load();
    const t = setInterval(load, 20000);
    return () => clearInterval(t);
  }, []);
  const live = useLive(device, () => void load());
  const [now, setNow] = useState(() => new Date().toISOString());
  useEffect(() => {
    const t = setInterval(() => setNow(new Date().toISOString()), 15000);
    return () => clearInterval(t);
  }, []);
  // Dark on the whole page (messages too), whatever the restaurant's theme.
  useEffect(() => {
    const root = document.documentElement;
    Object.entries(DARK).forEach(([k, v]) => root.style.setProperty(k, String(v)));
  }, []);
  return (
    <div className="flex h-full flex-col overflow-hidden bg-canvas text-ink" style={DARK}>
      <header className="flex items-center gap-[1.2vw] border-b border-line px-[3vw] py-[1.5vw]">
        <Logo url={me.venue.brand?.logo_url} name={me.venue.name} size={Math.max(48, Math.round(innerWidth * 0.036))} />
        <span className="min-w-0 flex-1 truncate text-[2.2vw] font-bold tracking-tight">{me.venue.name}</span>
        <span className="num text-[1.9vw] font-semibold text-muted">{clock(now)}</span>
        <LivePill status={live.status} via={live.via} />
      </header>
      <LayoutGroup>
        <div className="grid min-h-0 flex-1 grid-cols-[1fr_1.45fr] divide-x divide-line">
          <section className="flex min-h-0 flex-col overflow-hidden px-[3vw] py-[2.4vw]">
            <h2 className="mb-[2vw] flex items-center gap-[0.9vw] text-[2.4vw] font-bold tracking-tight">
              <ChefHat className="h-[2.3vw] w-[2.3vw] text-muted" strokeWidth={2} />
              Preparing
              <span className="num ml-auto text-[1.8vw] font-semibold text-muted">{board.preparing.length || ""}</span>
            </h2>
            <div className="grid grid-cols-3 content-start gap-[1vw]">
              <AnimatePresence mode="popLayout">
                {board.preparing.map((r) => (
                  <motion.span
                    key={r.token}
                    layoutId={`t-${r.token}`}
                    initial={{ opacity: 0, scale: 0.8 }}
                    animate={{ opacity: 1, scale: 1 }}
                    exit={{ opacity: 0, scale: 0.8 }}
                    transition={glide}
                    className="num rounded-[1vw] bg-surface py-[1.1vw] text-center text-[3.1vw] font-semibold leading-none tracking-tight text-ink/75"
                  >
                    {r.token}
                  </motion.span>
                ))}
              </AnimatePresence>
            </div>
            <AnimatePresence>
              {!board.preparing.length ? (
                <motion.p key="none" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="text-[1.6vw] text-muted">
                  Nothing cooking right now
                </motion.p>
              ) : null}
            </AnimatePresence>
          </section>
          <section className="flex min-h-0 flex-col overflow-hidden px-[3vw] py-[2.4vw]">
            <h2 className="mb-[2vw] flex items-center gap-[0.9vw] text-[2.4vw] font-bold tracking-tight">
              <span className="relative grid h-[2.3vw] w-[2.3vw] place-items-center">
                <span className="absolute h-[1.1vw] w-[1.1vw] animate-ping rounded-full bg-ok/60" />
                <span className="relative h-[1.1vw] w-[1.1vw] rounded-full bg-ok" />
              </span>
              Ready for pickup
              <span className="num ml-auto text-[1.8vw] font-semibold text-muted">{board.ready.length || ""}</span>
            </h2>
            <div className="grid grid-cols-3 content-start gap-[1.2vw]">
              <AnimatePresence mode="popLayout">
                {board.ready.map((r) => (
                  <motion.span
                    key={r.token}
                    layoutId={`t-${r.token}`}
                    initial={{ opacity: 0, scale: 0.6 }}
                    animate={{ opacity: 1, scale: 1 }}
                    exit={{ opacity: 0, scale: 0.85 }}
                    transition={glide}
                    className="num rounded-[1.2vw] bg-ink py-[1.6vw] text-center text-[4.6vw] font-bold leading-none tracking-tight text-canvas"
                  >
                    {r.token}
                  </motion.span>
                ))}
              </AnimatePresence>
            </div>
            <AnimatePresence>
              {!board.ready.length ? (
                <motion.div key="none" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="grid flex-1 place-items-center text-ink/15">
                  <PackageCheck className="h-[7vw] w-[7vw]" strokeWidth={1.3} />
                </motion.div>
              ) : null}
            </AnimatePresence>
          </section>
        </div>
      </LayoutGroup>
    </div>
  );
}

// A wall screen: dark, calm, readable from across the room, whatever the restaurant's theme.
const DARK = {
  "--color-canvas": "#000000",
  "--color-surface": "#161616",
  "--color-ink": "#ffffff",
  "--color-muted": "#a6a6a6",
  "--color-line": "#2a2a2a",
  "--color-ok": "#22c55e",
  "--color-warn": "#f59e0b",
  "--color-ok-soft": "color-mix(in oklab, #22c55e 20%, #161616)",
  "--color-warn-soft": "color-mix(in oklab, #f59e0b 22%, #161616)",
  "--color-bad-soft": "color-mix(in oklab, #ef4444 22%, #161616)",
} as React.CSSProperties;
