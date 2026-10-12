// The price list the quotes are worked out from: per screen and per module, monthly and one-time.
import { useEffect, useState } from "react";
import type { Admin } from "../../lib/admin";
import { toCents } from "../../lib/format";
import { Button, Card, SkeletonList, useToast } from "../../ui/kit";
import { inputCls, PRICED_SCREENS, say, SCREEN_LABEL, type Catalog } from "./catalog";

type Prices = Record<string, { monthly: number; once: number }>;
const rs = (cents: number | undefined) => ((cents ?? 0) / 100).toFixed(2);

export function PriceList({ admin, catalog }: { admin: Admin; catalog: Catalog }) {
  const toast = useToast();
  const [rows, setRows] = useState<Record<string, { monthly: string; once: string }> | null>(null);
  const [saved, setSaved] = useState("");
  const [busy, setBusy] = useState(false);
  const items: [string, string][] = [
    ...PRICED_SCREENS.map((k): [string, string] => [`screen:${k}`, SCREEN_LABEL[k] ?? k]),
    ...catalog.modules.map((m): [string, string] => [`module:${m.code}`, `${m.code} · ${say(m.name)}`]),
  ];

  useEffect(() => {
    admin
      .get<Prices>("/v1/platform/prices")
      .then((p) => {
        const r = Object.fromEntries(items.map(([item]) => [item, { monthly: rs(p[item]?.monthly), once: rs(p[item]?.once) }]));
        setRows(r);
        setSaved(JSON.stringify(r));
      })
      .catch((x: Error) => toast(x.message, "bad"));
  }, []);
  const dirty = !!rows && JSON.stringify(rows) !== saved;

  const save = async () => {
    if (!rows) return;
    setBusy(true);
    try {
      await admin.api(
        "PUT",
        "/v1/platform/prices",
        items.map(([item]) => ({ item, monthly: toCents(rows[item].monthly || "0"), once: toCents(rows[item].once || "0") })),
      );
      setSaved(JSON.stringify(rows));
      toast("Price list saved", "ok");
    } catch (x) {
      toast((x as Error).message, "bad");
    } finally {
      setBusy(false);
    }
  };

  const group = (prefix: string, title: string) => (
    <Card className="p-0!">
      <table className="w-full">
        <thead>
          <tr className="border-b border-line text-left text-xs text-muted">
            <th className="py-3 pl-5 text-[15px] font-bold text-ink">{title}</th>
            <th className="w-32 py-3 pr-1.5 text-right font-medium">Monthly Rs</th>
            <th className="w-32 py-3 pr-5 text-right font-medium">One-time Rs</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {items
            .filter(([item]) => item.startsWith(prefix))
            .map(([item, label]) => (
              <tr key={item}>
                <td className="py-2 pl-5 pr-2 text-[15px]">
                  {label.includes(" · ") ? (
                    <>
                      {label.split(" · ").slice(1).join(" · ")} <span className="ml-1 text-xs font-medium text-muted">{label.split(" · ")[0]}</span>
                    </>
                  ) : (
                    label
                  )}
                </td>
                {(["monthly", "once"] as const).map((f) => (
                  <td key={f} className={`w-32 py-2 pl-1.5 ${f === "once" ? "pr-5" : ""}`}>
                    <input
                      type="number"
                      min={0}
                      step="0.01"
                      aria-label={`${item} ${f === "once" ? "one-time" : "monthly"}`}
                      className={`${inputCls} num h-10! text-right`}
                      value={rows![item][f]}
                      onChange={(e) => setRows((r) => ({ ...r!, [item]: { ...r![item], [f]: e.target.value } }))}
                    />
                  </td>
                ))}
              </tr>
            ))}
        </tbody>
      </table>
    </Card>
  );

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <p className="mr-auto max-w-2xl text-[15px] text-muted">In rupees. Monthly is the software per screen or module; one-time is hardware and setup. Every quote uses it.</p>
        <Button variant={dirty ? "primary" : "default"} disabled={busy || !dirty} onClick={save}>
          Save prices
        </Button>
      </div>
      {!rows ? (
        <SkeletonList rows={6} />
      ) : (
        <div className="grid items-start gap-4 xl:grid-cols-2">
          {group("screen:", "Screens")}
          {group("module:", "Modules")}
        </div>
      )}
      <p className="text-xs text-muted">Equipment (printers, router, UPS…) has no price here yet; quotes list it as “no price”.</p>
    </div>
  );
}
