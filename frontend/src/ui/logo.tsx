// The restaurant's logo. Without an uploaded logo: a clean mark in the restaurant's colour (never
// letters), so every screen still looks finished.
import { UserRound, UtensilsCrossed } from "lucide-react";

export function Logo({ url, name, size = 44, className = "" }: { url?: string | null; name: string; size?: number; className?: string }) {
  return url ? (
    <img src={url} alt={name} width={size} height={size} className={`shrink-0 rounded-xl bg-surface object-contain ${className}`} style={{ width: size, height: size }} />
  ) : (
    <span aria-label={name} className={`grid shrink-0 place-items-center rounded-xl bg-brand text-on-brand ${className}`} style={{ width: size, height: size }}>
      <UtensilsCrossed size={Math.round(size * 0.5)} strokeWidth={2.25} />
    </span>
  );
}

/** A person (staff member): a quiet round icon, not their initials. */
export function Avatar({ size = 40, active = false, className = "" }: { size?: number; active?: boolean; className?: string }) {
  return (
    <span className={`grid shrink-0 place-items-center rounded-full ${active ? "bg-ink text-canvas" : "bg-ink/[.06] text-ink/60"} ${className}`} style={{ width: size, height: size }}>
      <UserRound size={Math.round(size * 0.5)} strokeWidth={2} />
    </span>
  );
}
