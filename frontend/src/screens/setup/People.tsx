// Step 2: menu (in the menu editor) and staff with their PINs.
import { ArrowUpRight, KeyRound, Plus, Power, UtensilsCrossed, Users } from "lucide-react";
import { useState } from "react";
import { consoleUrl } from "../../lib/screens";
import { Button, Card, Empty, Modal, MoreMenu, Skeleton } from "../../ui/kit";
import { Avatar } from "../../ui/logo";
import { Field, Input, Lead, LINK_MD, LINK_PRIMARY, Row, Section, Select, Status, useAct, useLoad, useOpen, useSetup } from "./ui";

type Staff = { id: string; name: string; role: string; is_active: boolean };
const ROLES = ["cashier", "waiter", "kitchen", "manager"];

export function MenuLinkCard() {
  const { admin } = useSetup();
  const todo = useOpen("menu", "taxes");
  return (
    <Card className="flex flex-wrap items-center gap-4">
      <Lead tone={todo ? "muted" : "ok"}>
        <UtensilsCrossed size={20} />
      </Lead>
      <div className="min-w-[200px] flex-1">
        <h2 className="text-lg font-bold tracking-tight">Menu, prices and taxes</h2>
        <p className="text-sm text-muted">Items with photos in 3 languages, kitchen stations, add-ons, service charge and VAT.</p>
      </div>
      <a className={todo ? LINK_PRIMARY : LINK_MD} href={`${consoleUrl("menu", admin.venue?.code)}?as=installer`}>
        Open the menu editor <ArrowUpRight size={18} />
      </a>
    </Card>
  );
}

export function StaffCard() {
  const { admin, changed } = useSetup();
  const act = useAct();
  const [staff, reload] = useLoad(() => admin.get<Staff[]>(admin.v("/staff")));
  const [adding, setAdding] = useState(false);
  const [pinFor, setPinFor] = useState<Staff | null>(null);
  // The menu comes first: only one brand-coloured button on this step.
  const staffTodo = useOpen("staff");
  const menuTodo = useOpen("menu", "taxes");
  const todo = staffTodo && !menuTodo;
  return (
    <Section
      title="Staff & PINs"
      about="Staff log in on the POS, waiter and kitchen screens with their PIN. At least one manager."
      action={
        <Button size="sm" variant={todo ? "primary" : "default"} onClick={() => setAdding(true)}>
          <Plus size={16} /> Add staff
        </Button>
      }
    >
      <div className="-mx-3 flex flex-col divide-y divide-line">
        {!staff ? (
          [0, 1].map((k) => <Skeleton key={k} className="mx-3 mb-2 h-12" />)
        ) : staff.length ? (
          staff.map((st) => (
            <Row key={st.id} className="flex-nowrap">
              <Avatar className={st.is_active ? "" : "opacity-50"} />
              <div className={`min-w-0 flex-1 ${st.is_active ? "" : "opacity-50"}`}>
                <div className="truncate font-semibold">{st.name}</div>
                <div className="text-sm capitalize text-muted">{st.is_active ? st.role : <Status tone="muted">{`${st.role} · off`}</Status>}</div>
              </div>
              <MoreMenu
                label={`More for ${st.name}`}
                items={[
                  { label: "Change PIN", icon: <KeyRound size={18} />, onClick: () => setPinFor(st) },
                  { label: st.is_active ? "Turn off" : "Turn on", icon: <Power size={18} />, danger: st.is_active, onClick: () => act(() => admin.api("PATCH", admin.v(`/staff/${st.id}`), { is_active: !st.is_active }), st.is_active ? `${st.name} turned off` : `${st.name} turned on`).then(() => (reload(), changed())) },
                ]}
              />
            </Row>
          ))
        ) : (
          <Empty icon={<Users size={24} />}>No staff yet.</Empty>
        )}
      </div>
      {adding ? <AddStaff onClose={() => setAdding(false)} onAdded={() => (void reload(), changed())} /> : null}
      {pinFor ? <PinModal staff={pinFor} onClose={() => setPinFor(null)} /> : null}
    </Section>
  );
}

function AddStaff({ onClose, onAdded }: { onClose: () => void; onAdded: () => void }) {
  const { admin } = useSetup();
  const act = useAct();
  const [name, setName] = useState("");
  const [role, setRole] = useState("cashier");
  const [pin, setPin] = useState("");
  const add = async () => {
    const r = await act(() => admin.api("POST", admin.v("/staff"), { name: name.trim(), role, pin: pin.trim() }), `${name.trim()} added`);
    if (r) onAdded(), onClose();
  };
  return (
    <Modal
      open
      onClose={onClose}
      title="Add staff"
      footer={
        <Button type="submit" form="add-staff" variant="primary" size="lg" className="w-full" disabled={!name.trim() || pin.length < 4}>
          Add
        </Button>
      }
    >
      <form
        id="add-staff"
        className="flex flex-col gap-4"
        onSubmit={(e) => {
          e.preventDefault();
          void add();
        }}
      >
        <Field label="Name">
          <Input autoFocus aria-label="Staff name" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Nimal" />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Role">
            <Select aria-label="Role" value={role} onChange={(e) => setRole(e.target.value)} className="capitalize">
              {ROLES.map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="PIN">
            <Input aria-label="PIN" inputMode="numeric" value={pin} onChange={(e) => setPin(e.target.value.replace(/\D/g, ""))} maxLength={8} placeholder="4–8 digits" className="num tracking-[.2em]" />
          </Field>
        </div>
      </form>
    </Modal>
  );
}

function PinModal({ staff, onClose }: { staff: Staff; onClose: () => void }) {
  const { admin } = useSetup();
  const act = useAct();
  const [pin, setPin] = useState("");
  return (
    <Modal
      open
      onClose={onClose}
      title={`New PIN for ${staff.name}`}
      footer={
        <Button type="submit" form="pin-form" variant="primary" size="lg" className="w-full" disabled={pin.length < 4}>
          Save PIN
        </Button>
      }
    >
      <form
        id="pin-form"
        onSubmit={async (e) => {
          e.preventDefault();
          if (await act(() => admin.api("PATCH", admin.v(`/staff/${staff.id}`), { pin }), "PIN changed")) onClose();
        }}
      >
        <Field label="PIN (4–8 digits)">
          <Input autoFocus aria-label="New PIN" inputMode="numeric" maxLength={8} value={pin} onChange={(e) => setPin(e.target.value.replace(/\D/g, ""))} className="num h-16 text-center text-3xl tracking-[.4em]" />
        </Field>
      </form>
    </Modal>
  );
}
