// Step 3: the network (cloud only, or hybrid with a hub on the restaurant's own network) and the
// equipment the package includes (router, UPS, printers, drawers, readers).
import { appOrigin } from "../../lib/features";
import { Check, Copy, Minus, Plus, Server } from "lucide-react";
import { useState } from "react";
import { ago, clock } from "../../lib/format";
import { Button, IconButton, Modal, Segmented, Skeleton, useToast } from "../../ui/kit";
import { Code, copy, Lead, Loading, Row, Section, Status, useAct, useLoad, useSetup, type NetworkInfo } from "./ui";

export function NetworkCard() {
  const { admin, setNetwork, changed } = useSetup();
  const act = useAct();
  const toast = useToast();
  const [n, reload, err] = useLoad(async () => {
    const r = await admin.get<NetworkInfo>(admin.v("/network"));
    setNetwork(r);
    return r;
  });
  const [code, setCode] = useState<{ code: string; expires_at: string; cloud_url?: string } | null>(null);
  if (!n) return <Loading id="network-card" title="Network" err={err} />;
  const hub = n.hub;
  const setMode = async (mode: "cloud" | "hybrid") => {
    if (mode === n.mode) return;
    await act(() => admin.api("PUT", admin.v("/network"), { mode }), mode === "hybrid" ? "Hybrid: screens use the hub first" : "Cloud: screens use the cloud");
    await reload();
    changed();
  };
  const getCode = async () => {
    if (hub && !confirm("Replace the hub? The old hub stops syncing once the new one connects.")) return;
    const r = await act(() => admin.api<{ code: string; expires_at: string; cloud_url?: string }>("POST", admin.v("/hub/setup-code")));
    if (r) setCode(r);
  };
  const command = code ? `kiosk hub-setup --cloud ${code.cloud_url || appOrigin()} --code ${code.code} --lan-url http://<hub-ip>:8000` : "";
  const needHub = n.mode === "hybrid" && !hub;
  return (
    <Section id="network-card" title="Network" about={n.mode === "hybrid" ? "Screens use the hub on the local network, so the kitchen keeps working without internet." : "Screens use the internet only."}>
      <Segmented
        className="self-start"
        value={n.mode}
        onChange={setMode}
        options={[
          ["cloud", "Cloud"],
          ["hybrid", "Hybrid (hub)"],
        ]}
      />
      {hub || n.mode === "hybrid" ? (
        <Row className="hub-row -mx-3">
          <Lead tone={hub?.alive ? "ok" : "muted"}>
            <Server size={20} />
          </Lead>
          <div className="min-w-0 flex-1">
            <div className="font-semibold">Hub</div>
            {hub ? (
              <>
                <div className="flex flex-wrap items-center gap-x-2">
                  {hub.alive ? <Status tone="ok">{n.in_charge === "hub" ? "Online · in charge" : "Online"}</Status> : hub.catching_up ? <Status tone="warn">Catching up</Status> : <Status tone="bad">Not heard from</Status>}
                  <span className="text-sm text-muted">· seen {hub.last_seen_at ? ago(hub.last_seen_at) : "never"}</span>
                </div>
                <div className="truncate text-[13px] text-muted">{[hub.lan_url || "address not set", `${hub.pending} waiting to send`, `${hub.open_orders ?? 0} open orders`, hub.software].filter(Boolean).join(" · ")}</div>
              </>
            ) : (
              <Status tone="warn">Not connected yet</Status>
            )}
          </div>
          <Button size="sm" variant={needHub ? "primary" : "soft"} onClick={getCode}>
            {hub ? "Replace hub" : "Hub setup code"}
          </Button>
        </Row>
      ) : null}
      <Modal open={!!code} onClose={() => setCode(null)} title="Connect the hub" footer={<Button variant="primary" className="w-full" onClick={() => setCode(null)}>Done</Button>}>
        {code ? (
          <div className="flex flex-col gap-4">
            <p className="text-[15px] text-muted">On the hub box (next to the router, on the UPS), run this once:</p>
            <div className="flex items-start gap-2 rounded-2xl bg-ink/[.035] p-3">
              <pre className="hub-command min-w-0 flex-1 whitespace-pre-wrap break-all font-mono text-[13px]">{command}</pre>
              <IconButton label="Copy command" onClick={() => copy(command, toast)} size={36}>
                <Copy size={16} />
              </IconButton>
            </div>
            <div className="setup-code hub-code num text-center text-5xl font-black tracking-[.2em]" data-code={code.code}>
              {code.code}
            </div>
            <p className="text-center text-sm text-muted">Works once, until {clock(code.expires_at)}. Start the hub; it shows Online here within a minute.</p>
          </div>
        ) : null}
      </Modal>
    </Section>
  );
}

type Equipment = { item: string; name: string; planned: number; installed: number; manual: boolean; required_because: string[] };

export function EquipmentCard() {
  const { admin, changed } = useSetup();
  const act = useAct();
  const [kit, reload] = useLoad(() => admin.get<Equipment[]>(admin.v("/equipment")));
  const set = async (e: Equipment, count: number) => {
    if (await act(() => admin.api("PUT", admin.v("/equipment"), { item: e.item, count }))) await reload(), changed();
  };
  const left = (kit ?? []).filter((e) => e.installed < e.planned).length;
  return (
    <Section id="equipment-card" title="Equipment" about={kit ? (left ? `${left} still to install. Printers, drawers and readers count by themselves.` : "Everything in the package is installed.") : undefined}>
      <div className="-mx-3 flex flex-col divide-y divide-line">
        {!kit
          ? [0, 1, 2].map((k) => <Skeleton key={k} className="mx-3 mb-2 h-12" />)
          : kit.map((e) => {
              const done = e.installed >= e.planned;
              return (
                <Row key={e.item} className="equipment-row flex-nowrap" data-item={e.item}>
                  <span className={`grid h-7 w-7 shrink-0 place-items-center rounded-full ${done ? "bg-ok-soft text-ok" : "ring-2 ring-inset ring-line"}`}>{done ? <Check size={15} strokeWidth={3} /> : null}</span>
                  <div className="min-w-0 flex-1">
                    <div className="font-semibold">{e.name}</div>
                    {e.required_because.length ? <div className="truncate text-sm text-muted">{e.required_because[0]}</div> : null}
                  </div>
                  <span className="num shrink-0 text-[15px] font-semibold">
                    {e.installed}
                    <span className="text-muted"> / {e.planned}</span>
                  </span>
                  {e.manual ? (
                    <div className="flex shrink-0 items-center gap-1">
                      <IconButton label={`One less ${e.name}`} size={36} disabled={e.installed === 0} onClick={() => set(e, e.installed - 1)}>
                        <Minus size={16} />
                      </IconButton>
                      <IconButton label={`Installed one ${e.name}`} size={36} variant={done ? "soft" : "dark"} onClick={() => set(e, e.installed + 1)}>
                        <Plus size={16} />
                      </IconButton>
                    </div>
                  ) : (
                    <span className="w-[76px] shrink-0 text-right text-xs text-muted">automatic</span>
                  )}
                </Row>
              );
            })}
      </div>
    </Section>
  );
}

export function LanHint() {
  if (!["localhost", "127.0.0.1"].includes(location.hostname)) return null;
  return (
    <p className="rounded-2xl bg-info-soft px-4 py-3 text-sm text-info">
      Other devices can't open “localhost”. Use this computer's network address, e.g. <Code>http://192.168.1.20:8000</Code> (find it with <Code>ipconfig getifaddr en0</Code>).
    </p>
  );
}
