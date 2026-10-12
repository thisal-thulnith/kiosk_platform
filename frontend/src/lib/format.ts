export const money = (cents: number | null | undefined): string =>
  `Rs ${((cents ?? 0) / 100).toLocaleString("en-LK", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
export const toCents = (rupees: string): number => Math.round(parseFloat(String(rupees).replace(/,/g, "")) * 100) || 0;
export const en = (o: { en?: string } | null | undefined): string => (o && (o.en ?? Object.values(o)[0])) || "";
export const clock = (iso: string | null | undefined): string => (iso ? new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "");
export function ago(iso: string | null | undefined): string {
  if (!iso) return "";
  const m = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 60000));
  return m < 1 ? "just now" : m < 60 ? `${m} min ago` : `${Math.floor(m / 60)} h ${m % 60} min ago`;
}
