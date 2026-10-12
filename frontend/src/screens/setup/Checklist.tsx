// Step 7: the go-live checklist. A ring shows how far the install is; every open item has a
// "Fix it" link to the step that fixes it. Open items first, done items quietly ticked below.
import { motion } from "motion/react";
import { ArrowRight, Check, PartyPopper } from "lucide-react";
import { Card, ease } from "../../ui/kit";
import { Loading, say, useSetup, type CheckItem } from "./ui";

function Ring({ done, total }: { done: number; total: number }) {
  const r = 34;
  const c = 2 * Math.PI * r;
  const pct = done / Math.max(1, total);
  return (
    <div className="relative grid h-[88px] w-[88px] shrink-0 place-items-center">
      <svg viewBox="0 0 80 80" className="absolute inset-0 -rotate-90" aria-hidden>
        <circle cx="40" cy="40" r={r} fill="none" strokeWidth="7" className="stroke-ink/[.07]" />
        <motion.circle cx="40" cy="40" r={r} fill="none" strokeWidth="7" strokeLinecap="round" className="stroke-ok" strokeDasharray={c} initial={false} animate={{ strokeDashoffset: c * (1 - pct) }} transition={{ ...ease, duration: 0.6 }} />
      </svg>
      <span className="num text-xl font-bold">
        {done}
        <span className="text-sm font-medium text-muted">/{total}</span>
      </span>
    </div>
  );
}

export function ChecklistCard({ onJump }: { onJump: (key: string) => void }) {
  const { checklist: c } = useSetup();
  if (!c) return <Loading id="checklist-card" title="Go-live checklist" />;
  const open = c.items.filter((i) => !i.done);
  const done = c.items.filter((i) => i.done);
  return (
    <div id="checklist-card" className="grid items-start gap-4 lg:grid-cols-[minmax(280px,360px)_minmax(0,1fr)]">
      <Card className="flex flex-col gap-5 lg:sticky lg:top-0">
        <div className="flex items-center gap-5 lg:flex-col lg:items-start">
          <Ring done={c.done} total={c.total} />
          <div className="min-w-0">
            <h2 className="flex items-center gap-2 text-xl font-bold tracking-tight">
              {c.ready ? (
                <>
                  Ready to go live <PartyPopper size={20} className="text-ok" />
                </>
              ) : (
                `${open.length} ${open.length === 1 ? "thing" : "things"} left`
              )}
            </h2>
            <p className="text-[15px] text-muted">{c.ready ? "Every check is ticked. Hand the restaurant over to the owner." : "Fix each one, then run a real test order."}</p>
          </div>
        </div>
        {done.length ? (
          <div className="flex flex-col border-t border-line pt-3">
            <span className="mb-1 text-xs font-semibold text-muted">Done</span>
            {done.map((i) => (
              <Item key={i.key} i={i} onJump={onJump} />
            ))}
          </div>
        ) : null}
      </Card>
      <Card className="flex flex-col gap-2">
        <h3 className="text-lg font-bold tracking-tight">{open.length ? "To do" : "All done"}</h3>
        {open.length ? (
          <div className="-mx-2 flex flex-col divide-y divide-line">
            {open.map((i) => (
              <Item key={i.key} i={i} onJump={onJump} />
            ))}
          </div>
        ) : (
          <p className="text-[15px] text-muted">Nothing left to fix.</p>
        )}
      </Card>
    </div>
  );
}

function Item({ i, onJump }: { i: CheckItem; onJump: (key: string) => void }) {
  if (i.done)
    return (
      <div data-key={i.key} className="check-row done flex items-center gap-3 py-2">
        <span aria-hidden className="check-mark grid h-7 w-7 shrink-0 place-items-center rounded-full bg-ok-soft text-ok">
          <Check size={15} strokeWidth={3} />
        </span>
        <span className="min-w-0 flex-1 text-[15px] text-muted">{say(i.title)}</span>
      </div>
    );
  return (
    <button data-key={i.key} onClick={() => onJump(i.key)} title="Go to this step" className="check-row clickable group flex w-full items-center gap-3 px-3 py-3.5 text-left transition hover:bg-ink/[.02] active:scale-[.995]">
      <span aria-hidden className="check-mark h-7 w-7 shrink-0 rounded-full ring-2 ring-inset ring-line" />
      <span className="min-w-0 flex-1">
        <strong className="block font-semibold">{say(i.title)}</strong>
        <span className="line-clamp-2 text-sm text-muted" title={say(i.detail)}>
          {say(i.detail)}
        </span>
      </span>
      <span className="inline-flex shrink-0 items-center gap-1 text-sm font-semibold text-ink">
        Fix it <ArrowRight size={16} className="transition group-hover:translate-x-0.5" />
      </span>
    </button>
  );
}
