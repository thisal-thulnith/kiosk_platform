import { useState } from "react";
import type { Admin } from "../../lib/admin";
import { Modal, useToast } from "../../ui/kit";
import { cleanText, type AdminCategory } from "./model";
import { Field, Footer, Input, Section, TextFields, Toggle, WindowsEditor } from "./parts";

export function CategoryEditor({ admin, cat, nextSort, onClose, onSaved }: { admin: Admin; cat: AdminCategory | null; nextSort: number; onClose: () => void; onSaved: (c: AdminCategory) => void }) {
  const toast = useToast();
  const [name, setName] = useState(cat?.name ?? {});
  const [sort, setSort] = useState(String(cat?.sort ?? nextSort));
  const [active, setActive] = useState(cat ? cat.is_active : true);
  const [windows, setWindows] = useState(cat?.windows ?? []);
  const [saving, setSaving] = useState(false);
  const save = async () => {
    if (!name.en?.trim()) return toast("Give the category an English name.", "bad");
    setSaving(true);
    try {
      const body = { name: cleanText(name), sort: Number(sort) || 0, is_active: active, windows };
      const saved = await (cat ? admin.api<AdminCategory>("PUT", admin.v(`/menu/categories/${cat.id}`), body) : admin.api<AdminCategory>("POST", admin.v("/menu/categories"), body));
      onSaved(saved);
    } catch (x) {
      toast((x as Error).message, "bad", 6000);
      setSaving(false);
    }
  };
  return (
    <Modal open wide onClose={onClose} title={cat ? cat.name.en || "Edit category" : "New category"} footer={<Footer onCancel={onClose} onSave={save} saving={saving} />}>
      <div className="flex flex-col gap-5">
        <TextFields value={name} onChange={setName} />
        <div className="grid items-end gap-3 sm:grid-cols-[1fr_120px]">
          <Toggle checked={active} onChange={setActive} hint={active ? "Guests see it" : "Hidden on every screen"}>
            Shown on screens
          </Toggle>
          <Field label="Order">
            <Input type="number" aria-label="Sort" value={sort} onChange={(e) => setSort(e.target.value)} />
          </Field>
        </div>
        <Section title="When is it served?" hint="Outside its time windows the category is hidden on the kiosk, tables and POS.">
          <WindowsEditor value={windows} onChange={setWindows} />
        </Section>
      </div>
    </Modal>
  );
}
