// The page a screen type shows while it is not offered yet (GET /v1/features -> coming_soon).
// Used by the self-order kiosk and the order status board; their code stays, ready to switch on.
import { motion } from "motion/react";
import { useEffect, useState, type ReactNode } from "react";
import type { Brand } from "../../lib/brand";
import { features } from "../../lib/features";
import { store } from "../../lib/store";
import { spring } from "../../ui/kit";
import { Logo } from "../../ui/logo";

/** `title` is the screen's name ("Self-order kiosk"); the page says "Self-order kiosk — coming soon". */
export function ComingSoon({ title, line }: { title: string; line: string }) {
  const brand = store.get<Brand>("kiosk:brand");
  return (
    <div className="grid min-h-full place-items-center bg-canvas p-4 sm:p-6" data-coming-soon>
      <motion.div className="flex w-full max-w-lg flex-col items-center rounded-3xl bg-surface px-6 py-10 text-center shadow-soft sm:px-10 sm:py-14" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={spring}>
        <Logo url={brand?.logo_url} name={brand?.name ?? "Restaurant"} size={64} />
        <h1 className="mt-7 text-[28px] font-bold leading-tight tracking-tight sm:text-[32px]">
          {title} <span className="whitespace-nowrap">— coming soon</span>
        </h1>
        <p className="mt-2 max-w-md text-[17px] text-muted">{line}</p>
      </motion.div>
    </div>
  );
}

/** Shows the coming-soon page when `type` is not offered yet, else the screen (after one check). */
export function UnlessComingSoon({ type, title, line, children }: { type: string; title: string; line: string; children: ReactNode }) {
  const [soon, setSoon] = useState<boolean | null>(null);
  useEffect(() => void features().then((f) => setSoon(f.coming_soon.includes(type))), [type]);
  if (soon === null) return <div className="min-h-full bg-canvas" aria-busy="true" />;
  return soon ? <ComingSoon title={title} line={line} /> : <>{children}</>;
}
