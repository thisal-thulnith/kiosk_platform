// Step 6: printers. Add one (how is it connected?), follow the connect steps, print the test page.
import { appOrigin } from "../../lib/features";
import { Check as CheckIcon, Cloud, Copy, FlaskConical, HelpCircle, Plus, Power, Printer as PrinterIcon, Trash2, Usb, Wifi } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { Button, Empty, IconButton, Modal, MoreMenu, Skeleton, useToast } from "../../ui/kit";
import { Check, Choice, Code, copy, Field, Input, Lead, Row, Section, Select, Status, Steps, useAct, useLoad, useOpen, useSetup } from "./ui";

type Printer = {
  id: string;
  name: string;
  connection: "cloud" | "screen" | "network" | "file";
  roles: string[];
  stations: string[];
  device_id: string | null;
  device_name?: string | null;
  paper_mm: number;
  cash_drawer: boolean;
  is_active: boolean;
  online: boolean | null;
  tested: boolean;
  queued?: number;
  cloud_path?: string;
  address?: string;
};

const ROLE_NAMES: Record<string, string> = { receipt: "Receipts", token: "Order-number slips", kitchen: "Kitchen tickets" };
const CONNECTIONS: Record<Printer["connection"], [ReactNode, string, string]> = {
  cloud: [<Cloud key="c" size={20} />, "Cloud printer (recommended)", "Star CloudPRNT printers. Power and network only, no cable to a screen."],
  screen: [<Usb key="u" size={20} />, "Plugged into a screen (USB)", "A kiosk's built-in printer, or a USB receipt printer on a POS, kitchen or waiter screen."],
  network: [<Wifi key="n" size={20} />, "Network printer (Ethernet / Wi-Fi)", "Printed by the restaurant's hub, so receipts and kitchen tickets keep printing without internet."],
  file: [<FlaskConical key="f" size={20} />, "Test printer (saves to a file)", "For trying the system without a printer. Not on the live cloud."],
};
const HOSTS = ["cashier", "kiosk", "kds", "waiter"];

function ConnectSteps({ p }: { p: Printer }) {
  const toast = useToast();
  if (p.connection === "cloud") {
    const url = `${appOrigin()}${p.cloud_path ?? ""}`;
    return (
      <Steps>
        <li>Plug the printer into power and the restaurant's network (cable or Wi-Fi).</li>
        <li>Hold FEED while switching it on: the self-test page shows its IP address.</li>
        <li>
          On a phone or PC on the same network open <Code>http://&lt;printer IP&gt;</Code> and log in (Star default: root / public).
        </li>
        <li>
          CloudPRNT → Enable, Server URL:
          <div className="my-1.5 flex items-center gap-2 rounded-2xl bg-ink/[.035] py-1.5 pl-3 pr-1.5">
            <Code className="cloud-url min-w-0 flex-1 bg-transparent px-0">{url}</Code>
            <IconButton label="Copy" size={32} onClick={() => copy(url, toast)}>
              <Copy size={15} />
            </IconButton>
          </div>
          Polling every 5 seconds. Save and restart the printer.
        </li>
        <li>It turns Online here within a minute. Then print the test page.</li>
      </Steps>
    );
  }
  if (p.connection === "screen")
    return (
      <Steps>
        <li>Plug the printer's USB cable into {p.device_name || "the screen"} (USB-OTG adapter on Android tablets).</li>
        <li>On that screen tap “Connect printer” and choose it. The screen remembers it.</li>
        <li>Print the test page.</li>
      </Steps>
    );
  if (p.connection === "network")
    return (
      <Steps>
        <li>Plug the printer into the restaurant's network (cable is best), on the same network as the hub.</li>
        <li>Give it a fixed IP address (on the printer, or reserve it in the router), e.g. <Code>192.168.1.50</Code>.</li>
        <li>
          The hub sends each slip to <Code>{p.address ?? "its address"}</Code>. Print the test page.
        </li>
      </Steps>
    );
  return <p className="text-sm text-muted">Test printer: slips are saved as files on the server.</p>;
}

function PrinterStatus({ p }: { p: Printer }) {
  if (!p.is_active) return <Status tone="muted">Turned off</Status>;
  if (p.online === false) return <Status tone="bad">Offline</Status>;
  if (!p.tested) return <Status tone="warn">{p.online ? "Online · not tested" : "Not tested"}</Status>;
  return <Status tone="ok">{p.online ? "Online · tested" : "Tested"}</Status>;
}

export function PrintersCard() {
  const { admin, changed } = useSetup();
  const act = useAct();
  const [printers, reload] = useLoad(() => admin.get<Printer[]>(admin.v("/printers")));
  const [wizard, setWizard] = useState(false);
  const [howTo, setHowTo] = useState<Printer | null>(null);
  const todo = useOpen("printers");
  const after = async () => (await reload(), changed());
  const test = (p: Printer) => act(() => admin.api("POST", admin.v(`/printers/${p.id}/test`)), "Test page sent").then(() => setTimeout(reload, 1500));
  const confirmed = (p: Printer) => act(() => admin.api("POST", admin.v(`/printers/${p.id}/confirm`)), "Printer ticked").then(after);
  const firstUntested = printers?.find((p) => p.is_active && !p.tested)?.id;
  return (
    <Section
      id="printers-card"
      title="Printers"
      about="Receipts, order-number slips and kitchen tickets. A printer that was off prints what it missed."
      action={
        <Button variant={todo && !firstUntested ? "primary" : "default"} size="sm" onClick={() => setWizard(true)}>
          <Plus size={16} /> Add printer
        </Button>
      }
    >
      <div className="-mx-3 flex flex-col divide-y divide-line">
        {!printers ? (
          [0, 1].map((k) => <Skeleton key={k} className="mx-3 mb-2 h-14" />)
        ) : printers.length ? (
          printers.map((p) => (
            <Row key={p.id} className="printer-row flex-nowrap" data-printer={p.id}>
              <Lead tone={p.tested && p.is_active ? "ok" : "muted"}>
                <PrinterIcon size={20} />
              </Lead>
              <div className={`min-w-0 flex-1 ${p.is_active ? "" : "opacity-50"}`}>
                <div className="truncate font-semibold">{p.name}</div>
                <PrinterStatus p={p} />
                <div className="truncate text-[13px] text-muted">
                  {[CONNECTIONS[p.connection][1].replace(" (recommended)", ""), p.device_name && `on ${p.device_name}`, p.address, p.roles.map((r) => ROLE_NAMES[r] ?? r).join(", ") + (p.stations.length ? ` (${p.stations.join(", ")})` : ""), `${p.paper_mm} mm`, p.cash_drawer && "cash drawer", p.queued ? `${p.queued} waiting` : ""].filter(Boolean).join(" · ")}
                </div>
              </div>
              <div className="flex shrink-0 items-center gap-1">
                {p.is_active && !p.tested ? (
                  <Button size="sm" variant={p.id === firstUntested ? "primary" : "soft"} onClick={() => test(p)}>
                    Test page
                  </Button>
                ) : null}
                <MoreMenu
                  label={`More for ${p.name}`}
                  items={[
                    p.tested || !p.is_active ? { label: "Print test page", icon: <PrinterIcon size={18} />, onClick: () => test(p) } : null,
                    p.tested ? null : { label: "It printed", icon: <CheckIcon size={18} />, onClick: () => confirmed(p) },
                    p.connection !== "file" ? { label: "How to connect", icon: <HelpCircle size={18} />, onClick: () => setHowTo(p) } : null,
                    { label: p.is_active ? "Turn off" : "Turn on", icon: <Power size={18} />, onClick: () => act(() => admin.api("PATCH", admin.v(`/printers/${p.id}`), { is_active: !p.is_active }), p.is_active ? "Printer off" : "Printer on").then(after) },
                    { label: "Remove", icon: <Trash2 size={18} />, danger: true, onClick: () => confirm(`Remove ${p.name}?`) && act(() => admin.api("DELETE", admin.v(`/printers/${p.id}`)), "Printer removed").then(after) },
                  ]}
                />
              </div>
            </Row>
          ))
        ) : (
          <Empty icon={<PrinterIcon size={24} />}>No printers yet. Until you add one, slips are saved on the server.</Empty>
        )}
      </div>
      {wizard ? <AddPrinter onClose={() => (setWizard(false), void after())} onSaved={after} /> : null}
      <Modal open={!!howTo} onClose={() => setHowTo(null)} title={howTo ? `Connect ${howTo.name}` : ""} footer={<Button variant="primary" className="w-full" onClick={() => setHowTo(null)}>Done</Button>}>
        {howTo ? <ConnectSteps p={howTo} /> : null}
      </Modal>
    </Section>
  );
}

/** Three dots at the top of the wizard: how · details · connect. */
function WizardSteps({ at }: { at: 0 | 1 | 2 }) {
  return (
    <div className="mb-4 flex items-center gap-2 text-xs font-semibold text-muted">
      {["Connection", "Details", "Connect & test"].map((t, i) => (
        <span key={t} className="flex items-center gap-2">
          {i ? <span className="h-px w-5 bg-line" /> : null}
          <span className={`grid h-5 w-5 place-items-center rounded-full text-[11px] ${i < at ? "bg-ok-soft text-ok" : i === at ? "bg-ink text-canvas" : "bg-ink/[.06]"}`}>{i < at ? <CheckIcon size={12} strokeWidth={3} /> : i + 1}</span>
          <span className={i === at ? "text-ink" : ""}>{t}</span>
        </span>
      ))}
    </div>
  );
}

function AddPrinter({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const { admin, devices, stations } = useSetup();
  const act = useAct();
  const [connection, setConnection] = useState<Printer["connection"] | null>(null);
  const [saved, setSaved] = useState<Printer | null>(null);
  const hosts = devices.filter((d) => HOSTS.includes(d.type) && d.is_active);
  const [name, setName] = useState("");
  const [roles, setRoles] = useState<string[]>(["receipt", "token"]);
  const [picked, setPicked] = useState<string[]>([]);
  const [host, setHost] = useState(hosts[0]?.id ?? "");
  const [near, setNear] = useState("");
  const [address, setAddress] = useState("");
  const [port, setPort] = useState(9100);
  const [paper, setPaper] = useState(80);
  const [drawer, setDrawer] = useState(false);
  // Watch the new printer come online and its test page print.
  useEffect(() => {
    if (!saved) return;
    const t = setInterval(async () => {
      const all = await admin.get<Printer[]>(admin.v("/printers")).catch(() => []);
      const x = all.find((y) => y.id === saved.id);
      if (x) setSaved(x);
    }, 3000);
    return () => clearInterval(t);
  }, [saved?.id]);

  if (saved)
    return (
      <Modal
        open
        onClose={onClose}
        title={`Connect ${saved.name}`}
        footer={
          <div className="flex flex-wrap gap-2">
            {saved.connection === "screen" && saved.device_id ? (
              <MoreMenu align="left" items={[{ label: "Show “Connect printer” on the screen", icon: <Usb size={18} />, onClick: () => act(() => admin.api("POST", admin.v(`/devices/${saved.device_id}/command`), { command: "connect_printer" }), "“Connect printer” shown on the screen") }]} />
            ) : null}
            <Button className="flex-1" onClick={() => act(() => admin.api("POST", admin.v(`/printers/${saved.id}/test`)), "Test page sent")}>
              Print test page
            </Button>
            <Button variant="primary" className="flex-1" onClick={() => act(() => admin.api("POST", admin.v(`/printers/${saved.id}/confirm`)), "Printer ticked").then(onClose)}>
              It printed
            </Button>
          </div>
        }
      >
        <WizardSteps at={2} />
        <ConnectSteps p={saved} />
        <div className="mt-4 flex flex-wrap gap-x-4 gap-y-1 rounded-2xl bg-ink/[.035] px-4 py-3">
          {saved.online === null ? null : saved.online ? <Status tone="ok">Online</Status> : <Status tone="warn">Waiting for the printer…</Status>}
          {saved.tested ? <Status tone="ok">Test page printed</Status> : <Status tone="muted">Not tested yet</Status>}
        </div>
      </Modal>
    );

  if (!connection)
    return (
      <Modal open onClose={onClose} title="Add a printer">
        <WizardSteps at={0} />
        <p className="mb-3 text-[15px] text-muted">How is it connected?</p>
        <div className="flex flex-col gap-2">
          {(Object.entries(CONNECTIONS) as [Printer["connection"], [ReactNode, string, string]][]).map(([k, [ic, title, about]]) => (
            <Choice
              key={k}
              data-connection={k}
              icon={ic}
              title={title}
              about={about}
              onClick={() => {
                setConnection(k);
                setName(k === "cloud" ? "Counter printer" : "");
              }}
            />
          ))}
        </div>
      </Modal>
    );

  const kitchen = roles.includes("kitchen");
  const save = async () => {
    const p = await act(() =>
      admin.api<Printer>("POST", admin.v("/printers"), {
        name: name.trim(),
        connection,
        roles,
        stations: kitchen ? picked : [],
        device_id: connection === "screen" ? host || null : connection === "cloud" ? near || null : null,
        ...(connection === "network" ? { host: address.trim(), port } : {}),
        paper_mm: paper,
        cash_drawer: drawer,
      }),
    );
    if (p) setSaved(p), onSaved();
  };
  return (
    <Modal
      open
      onClose={onClose}
      title="Add a printer"
      footer={
        <div className="flex gap-2">
          <Button variant="ghost" onClick={() => setConnection(null)}>
            Back
          </Button>
          <Button variant="primary" className="flex-1" disabled={!name.trim() || !roles.length || (connection === "screen" && !hosts.length) || (connection === "network" && !address.trim())} onClick={save}>
            Save and connect
          </Button>
        </div>
      }
    >
      <WizardSteps at={1} />
      <div className="flex flex-col gap-4">
        <div className="flex items-center gap-2 text-sm text-muted">
          {CONNECTIONS[connection][0]} {CONNECTIONS[connection][1]}
        </div>
        <Field label="Name">
          <Input aria-label="Printer name" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Counter printer, Bar printer" />
        </Field>
        <div className="flex flex-col gap-2">
          <span className="text-sm font-medium text-muted">What it prints</span>
          <div className="flex flex-wrap gap-x-5 gap-y-2">
            {Object.entries(ROLE_NAMES).map(([k, n]) => (
              <Check key={k} data-role={k} checked={roles.includes(k)} onChange={(on) => setRoles(on ? [...roles, k] : roles.filter((r) => r !== k))}>
                {n}
              </Check>
            ))}
          </div>
          {kitchen && stations.length ? (
            <div className="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-2xl bg-ink/[.035] p-3 text-sm">
              <span className="text-muted">Stations (none = all):</span>
              {stations.map((s) => (
                <Check key={s} data-station={s} checked={picked.includes(s)} onChange={(on) => setPicked(on ? [...picked, s] : picked.filter((x) => x !== s))}>
                  {s}
                </Check>
              ))}
            </div>
          ) : null}
        </div>
        {connection === "screen" ? (
          hosts.length ? (
            <Field label="Plugged into">
              <Select aria-label="Screen it is plugged into" value={host} onChange={(e) => setHost(e.target.value)}>
                {hosts.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.name} ({d.type})
                  </option>
                ))}
              </Select>
            </Field>
          ) : (
            <p className="text-sm font-medium text-bad">Add a POS, kiosk, kitchen or waiter screen first.</p>
          )
        ) : null}
        {connection === "network" ? (
          <div className="grid gap-3 sm:grid-cols-[1fr_120px]">
            <Field label="IP address">
              <Input aria-label="Printer address" inputMode="decimal" value={address} onChange={(e) => setAddress(e.target.value)} placeholder="e.g. 192.168.1.50" />
            </Field>
            <Field label="Port">
              <Input aria-label="Printer port" inputMode="numeric" value={port} onChange={(e) => setPort(Number(e.target.value.replace(/\D/g, "")) || 9100)} />
            </Field>
          </div>
        ) : null}
        {connection === "cloud" ? (
          <Field label="Prints receipts and number slips for">
            <Select aria-label="Prints for" value={near} onChange={(e) => setNear(e.target.value)}>
              <option value="">All screens (shared printer)</option>
              {hosts.map((d) => (
                <option key={d.id} value={d.id}>
                  Only {d.name} ({d.type})
                </option>
              ))}
            </Select>
          </Field>
        ) : null}
        <div className="grid items-end gap-3 sm:grid-cols-[140px_1fr]">
          <Field label="Paper">
            <Select aria-label="Paper width" value={paper} onChange={(e) => setPaper(Number(e.target.value))}>
              <option value={80}>80 mm</option>
              <option value={58}>58 mm</option>
            </Select>
          </Field>
          <Check checked={drawer} onChange={setDrawer} aria-label="Cash drawer" className="h-12">
            Cash drawer on it (opens for cash)
          </Check>
        </div>
      </div>
    </Modal>
  );
}
