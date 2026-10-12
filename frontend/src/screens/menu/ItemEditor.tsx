// One dish in a sheet: the common things first (photo, name, price, category, on the menu), the rest
// folded away (languages, add-ons, meal parts, suggestions, times, allergens, station and tax).
import { useMemo, useRef, useState } from "react";
import type { Admin } from "../../lib/admin";
import { money, toCents } from "../../lib/format";
import { net } from "../../lib/net";
import { Dish } from "../../ui/food";
import { Camera, Plus, X } from "lucide-react";
import { Badge, Button, Modal, useToast } from "../../ui/kit";
import { ALLERGENS, cleanText, newKey, rupees, TAX_CATEGORIES, windowLabel, type AdminCategory, type AdminItem, type Text } from "./model";
import { Chip, Field, Fold, Footer, Input, inputCls, TextFields, Toggle, useFolds, WindowsEditor } from "./parts";

type ModDraft = { key: string; id?: string; name: Text; price: string; sort: number; is_active: boolean };
type GroupDraft = { key: string; id?: string; name: Text; min: string; max: string; sort: number; mods: ModDraft[] };
type SlotDraft = { key: string; name: Text; item_ids: string[]; up: Record<string, string> };
type FoldKey = "lang" | "addons" | "combo" | "suggest" | "times" | "allergens" | "more";

const toGroups = (item: AdminItem | null): GroupDraft[] =>
  (item?.modifier_groups ?? []).map((g) => ({
    key: newKey(),
    id: g.id,
    name: g.name,
    min: String(g.min_select),
    max: String(g.max_select),
    sort: g.sort ?? 0,
    mods: g.modifiers.map((m) => ({ key: newKey(), id: m.id, name: m.name, price: rupees(m.price_delta), sort: m.sort ?? 0, is_active: m.is_active ?? true })),
  }));
const toSlots = (item: AdminItem | null): SlotDraft[] =>
  (item?.combo_slots ?? []).map((s) => ({ key: newKey(), name: s.name, item_ids: s.item_ids, up: Object.fromEntries(Object.entries(s.upcharges ?? {}).map(([k, v]) => [k, rupees(v)])) }));

export function ItemEditor({ admin, item, cats, items, defaultCat, onClose, onSaved }: { admin: Admin; item: AdminItem | null; cats: AdminCategory[]; items: AdminItem[]; defaultCat: string | null; onClose: () => void; onSaved: (categoryId: string) => void }) {
  const toast = useToast();
  const stations = useMemo(() => [...new Set(["kitchen", ...items.map((i) => i.station).filter((s) => s && s !== "none")])], [items]);
  const taxCats = useMemo(() => [...new Set([...TAX_CATEGORIES, ...items.map((i) => i.tax_category).filter(Boolean)])], [items]);
  const [name, setName] = useState<Text>(item?.name ?? {});
  const [desc, setDesc] = useState<Text>(item?.description ?? {});
  const [price, setPrice] = useState(rupees(item?.price ?? 0));
  const [categoryId, setCategoryId] = useState(item?.category_id ?? defaultCat ?? cats[0]?.id ?? "");
  const [station, setStation] = useState(item?.station ?? stations.find((s) => s !== "kitchen") ?? "kitchen");
  const [taxCat, setTaxCat] = useState(item?.tax_category ?? "food");
  const [plu, setPlu] = useState(item?.external_code ?? "");
  const [prep, setPrep] = useState(item?.prep_minutes ? String(item.prep_minutes) : "");
  const [sort, setSort] = useState(String(item?.sort ?? 0));
  const [active, setActive] = useState(item ? item.is_active : true);
  const [allergens, setAllergens] = useState<string[]>(item?.allergens ?? []);
  const [image, setImage] = useState<string | null>(item?.image_url ?? null);
  const [uploading, setUploading] = useState(false);
  const [windows, setWindows] = useState(item?.windows ?? []);
  const [groups, setGroups] = useState<GroupDraft[]>(() => toGroups(item));
  const [slots, setSlots] = useState<SlotDraft[]>(() => toSlots(item));
  const [suggest, setSuggest] = useState<string[]>(item?.suggest_ids ?? []);
  const [saving, setSaving] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const upload = async (f: File | undefined) => {
    if (!f) return;
    if (f.size > 5 * 1024 * 1024) return toast("The photo must be 5 MB or smaller.", "bad");
    setUploading(true);
    try {
      const res = await fetch(net.base() + admin.v("/media"), { method: "POST", headers: { ...admin.headers(), "Content-Type": f.type }, body: f });
      const data = await res.json().catch(() => null);
      if (!res.ok) throw new Error(data?.error?.message || "Upload failed");
      setImage(data.url);
      toast("Photo uploaded", "ok");
    } catch (x) {
      toast((x as Error).message, "bad", 6000);
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const folds = useFolds();
  const save = async () => {
    const fail = (msg: string, f?: FoldKey) => (f && folds.show(f), toast(msg, "bad", 6000));
    if (!name.en?.trim()) return fail("Give the item an English name.");
    if (!categoryId) return fail("Pick a category.");
    if (prep && !(Number(prep) >= 1 && Number(prep) <= 240)) return fail("Cooking time must be 1 to 240 minutes.", "more");
    for (const g of groups) {
      if (!g.name.en?.trim()) return fail("Every add-on group needs an English name.", "addons");
      if ((Number(g.min) || 0) > (Number(g.max) || 1)) return fail(`“${g.name.en}”: the minimum is above the maximum.`, "addons");
      if (g.mods.some((m) => !m.name.en?.trim())) return fail(`“${g.name.en}”: every option needs an English name.`, "addons");
    }
    for (const s of slots) {
      if (!s.name.en?.trim()) return fail("Every meal part needs an English name.", "combo");
      if (!s.item_ids.length) return fail(`Meal part “${s.name.en}”: pick at least one item.`, "combo");
    }
    const body = {
      category_id: categoryId,
      name: cleanText(name),
      description: cleanText(desc),
      price: toCents(price || "0"),
      station: station.trim() || "kitchen",
      prep_minutes: prep ? Number(prep) : null,
      external_code: plu.trim() || null,
      tax_category: taxCat.trim() || "food",
      allergens,
      image_url: image,
      windows,
      sort: Number(sort) || 0,
      is_active: active,
      modifier_groups: groups.map((g, gi) => ({
        ...(g.id ? { id: g.id } : {}),
        name: cleanText(g.name),
        min_select: Number(g.min) || 0,
        max_select: Number(g.max) || 1,
        sort: gi,
        modifiers: g.mods.map((m, mi) => ({ ...(m.id ? { id: m.id } : {}), name: cleanText(m.name), price_delta: toCents(m.price || "0"), sort: mi, is_active: m.is_active })),
      })),
      combo_slots: slots.map((s) => ({
        name: cleanText(s.name),
        item_ids: s.item_ids,
        upcharges: Object.fromEntries(s.item_ids.map((id) => [id, toCents(s.up[id] || "0")]).filter(([, v]) => (v as number) > 0)),
      })),
      suggest_ids: suggest.slice(0, 6),
    };
    setSaving(true);
    try {
      if (item) await admin.api("PUT", admin.v(`/menu/items/${item.id}`), body);
      else await admin.api("POST", admin.v("/menu/items"), body);
      onSaved(categoryId);
    } catch (x) {
      toast((x as Error).message, "bad", 6000);
      setSaving(false);
    }
  };

  const catName = cats.find((c) => c.id === categoryId)?.name.en;
  const langs = [name.si ? null : "Sinhala", name.ta ? null : "Tamil"].filter(Boolean);
  const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

  return (
    <Modal open wide onClose={onClose} title={item ? item.name.en || "Edit item" : "New item"} footer={<Footer onCancel={onClose} onSave={save} saving={saving || uploading} saveLabel="Save item" />}>
      <datalist id="menu-stations">
        {stations.map((s) => (
          <option key={s} value={s} />
        ))}
      </datalist>
      <datalist id="menu-taxcats">
        {taxCats.map((s) => (
          <option key={s} value={s} />
        ))}
      </datalist>

      <div className="grid gap-5 pb-5 sm:grid-cols-[220px_minmax(0,1fr)]">
        <div className="flex flex-col gap-2">
          <input ref={fileRef} type="file" accept="image/jpeg,image/png,image/webp" aria-label="Photo" className="hidden" onChange={(e) => upload(e.target.files?.[0])} />
          <button type="button" onClick={() => fileRef.current?.click()} disabled={uploading} className="group relative block w-full overflow-hidden rounded-xl" aria-label={image ? "Change photo" : "Upload photo"}>
            <Dish src={image} name={name.en || ""} hint={catName} size={200} className={`aspect-[4/3] h-auto! w-full! rounded-xl! max-sm:aspect-[16/9] ${uploading ? "animate-pulse" : ""}`} />
            <span className="absolute bottom-2 right-2 inline-flex h-9 items-center gap-1.5 rounded-full bg-surface px-3 text-sm font-semibold text-ink shadow-soft transition group-hover:bg-ink group-hover:text-white">
              <Camera size={16} /> {uploading ? "Uploading…" : image ? "Change" : "Add photo"}
            </span>
          </button>
          {image ? (
            <button type="button" className="self-start text-sm font-medium text-muted hover:text-bad" onClick={() => setImage(null)}>
              Remove photo
            </button>
          ) : null}
        </div>
        <div className="flex min-w-0 flex-col gap-3">
          <TextFields value={name} onChange={setName} only={["en"]} />
          <div className="grid grid-cols-2 gap-3">
            <Field label="Price (Rs)">
              <Input aria-label="Price Rs" type="number" step="0.01" min={0} value={price} onChange={(e) => setPrice(e.target.value)} className="num text-lg font-bold" />
            </Field>
            <Field label="Category">
              <select aria-label="Category" className={`${inputCls} w-full`} value={categoryId} onChange={(e) => setCategoryId(e.target.value)}>
                {cats.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name.en}
                  </option>
                ))}
              </select>
            </Field>
          </div>
          <Toggle checked={active} onChange={setActive} hint={item && !item.is_available ? "Sold out today (staff set this on the POS or kitchen screen)" : active ? "Guests can order it" : "Hidden on every screen"}>
            On the menu
          </Toggle>
        </div>
      </div>

      <Fold title="Languages & description" summary={langs.length ? `${langs.join(" and ")} name missing` : desc.en ? "All names · has a description" : "All names"} open={folds.is("lang")} onToggle={() => folds.toggle("lang")}>
        <TextFields value={name} onChange={setName} only={["si", "ta"]} />
        <TextFields label="Description" value={desc} onChange={setDesc} required={false} />
        <span className="-mt-2 text-xs text-muted">Optional. Shown under the name on the kiosk and table screens.</span>
      </Fold>
      <Fold title="Add-ons" summary={groups.length ? groups.map((g) => g.name.en || "New group").join(", ") : "Size, spice level, extras — none yet"} open={folds.is("addons")} onToggle={() => folds.toggle("addons")}>
        <AddonsTab groups={groups} setGroups={setGroups} />
      </Fold>
      <Fold title="Meal (combo)" summary={slots.length ? `${plural(slots.length, "part")}: ${slots.map((s) => s.name.en || "New part").join(", ")}` : "A normal item — not a meal"} open={folds.is("combo")} onToggle={() => folds.toggle("combo")}>
        <ComboTab slots={slots} setSlots={setSlots} items={items} cats={cats} selfId={item?.id} />
      </Fold>
      <Fold title="Goes well with" summary={suggest.length ? `${suggest.length} of 6 suggestions` : "No suggestions"} open={folds.is("suggest")} onToggle={() => folds.toggle("suggest")}>
        <SuggestTab value={suggest} onChange={setSuggest} items={items} cats={cats} selfId={item?.id} />
      </Fold>
      <Fold title="When it's served" summary={windows.length ? windows.map(windowLabel).join(", ") : "Whenever its category is served"} open={folds.is("times")} onToggle={() => folds.toggle("times")}>
        <WindowsEditor value={windows} onChange={setWindows} />
      </Fold>
      <Fold title="Allergens" summary={allergens.length ? allergens.join(", ") : "None marked"} open={folds.is("allergens")} onToggle={() => folds.toggle("allergens")}>
        <p className="-mt-2 text-sm text-muted">Shown to guests and printed on kitchen tickets.</p>
        <div className="flex flex-wrap gap-2">
          {ALLERGENS.map((a) => (
            <Chip key={a} on={allergens.includes(a)} onClick={() => setAllergens((l) => (l.includes(a) ? l.filter((x) => x !== a) : [...l, a]))}>
              {a}
            </Chip>
          ))}
        </div>
      </Fold>
      <Fold title="Kitchen, tax & more" summary={`${station || "kitchen"} station · ${taxCat || "food"} tax${prep ? ` · ${prep} min` : ""}${plu ? ` · PLU ${plu}` : ""}`} open={folds.is("more")} onToggle={() => folds.toggle("more")}>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Kitchen station" hint="Which kitchen screen and printer gets it.">
            <Input aria-label="Station" list="menu-stations" value={station} onChange={(e) => setStation(e.target.value)} />
          </Field>
          <Field label="Tax category" hint="Taxes and charges apply by this.">
            <Input aria-label="Tax category" list="menu-taxcats" value={taxCat} onChange={(e) => setTaxCat(e.target.value)} />
          </Field>
          <Field label="Cooking time (minutes)" hint="Empty = the restaurant default.">
            <Input aria-label="Prep minutes" type="number" min={1} max={240} placeholder="default" value={prep} onChange={(e) => setPrep(e.target.value)} />
          </Field>
          <Field label="Order in category">
            <Input aria-label="Sort" type="number" value={sort} onChange={(e) => setSort(e.target.value)} />
          </Field>
          <Field label="POS code (PLU)" hint="Only if the restaurant's own POS is connected.">
            <Input aria-label="POS code (PLU)" placeholder="optional" maxLength={40} value={plu} onChange={(e) => setPlu(e.target.value)} />
          </Field>
        </div>
      </Fold>
    </Modal>
  );
}

function AddonsTab({ groups, setGroups }: { groups: GroupDraft[]; setGroups: React.Dispatch<React.SetStateAction<GroupDraft[]>> }) {
  const setG = (key: string, fn: (g: GroupDraft) => GroupDraft) => setGroups((l) => l.map((g) => (g.key === key ? fn(g) : g)));
  const setM = (gk: string, mk: string, fn: (m: ModDraft) => ModDraft) => setG(gk, (g) => ({ ...g, mods: g.mods.map((m) => (m.key === mk ? fn(m) : m)) }));
  return (
    <>
      <p className="-mt-2 text-sm text-muted">Choices the guest makes for this item. An option can cost extra.</p>
      {groups.map((g) => {
        const min = Number(g.min) || 0;
        const max = Number(g.max) || 1;
        return (
          <div key={g.key} className="flex flex-col gap-3 rounded-xl p-4 ring-1 ring-line">
            <div className="grid gap-2 sm:grid-cols-3">
              <Input aria-label="Group name" placeholder="Group, e.g. Spice level *" value={g.name.en ?? ""} onChange={(e) => setG(g.key, (x) => ({ ...x, name: { ...x.name, en: e.target.value } }))} />
              <Input aria-label="Group name si" lang="si" placeholder="සිංහල" value={g.name.si ?? ""} onChange={(e) => setG(g.key, (x) => ({ ...x, name: { ...x.name, si: e.target.value } }))} />
              <Input aria-label="Group name ta" lang="ta" placeholder="தமிழ்" value={g.name.ta ?? ""} onChange={(e) => setG(g.key, (x) => ({ ...x, name: { ...x.name, ta: e.target.value } }))} />
            </div>
            <div className="flex flex-wrap items-center gap-2 text-sm font-medium text-muted">
              Guest chooses
              <Input aria-label="Min" type="number" min={0} className="w-20" value={g.min} onChange={(e) => setG(g.key, (x) => ({ ...x, min: e.target.value }))} />
              to
              <Input aria-label="Max" type="number" min={1} className="w-20" value={g.max} onChange={(e) => setG(g.key, (x) => ({ ...x, max: e.target.value }))} />
              <span className={min > max ? "text-bad" : ""}>{min > max ? "Minimum is above maximum" : min === 0 ? "(optional)" : "(required)"}</span>
              <Button type="button" size="sm" variant="ghost" className="ml-auto hover:text-bad" onClick={() => setGroups((l) => l.filter((x) => x.key !== g.key))}>
                Remove group
              </Button>
            </div>
            <div className="flex flex-col gap-2">
              {g.mods.map((m) => (
                <div key={m.key} className="grid grid-cols-[1fr_1fr_1fr_120px_auto] items-center gap-2 max-sm:grid-cols-2">
                  <Input aria-label="Option name" placeholder="Option *" value={m.name.en ?? ""} onChange={(e) => setM(g.key, m.key, (x) => ({ ...x, name: { ...x.name, en: e.target.value } }))} />
                  <Input aria-label="Option name si" lang="si" placeholder="සිංහල" value={m.name.si ?? ""} onChange={(e) => setM(g.key, m.key, (x) => ({ ...x, name: { ...x.name, si: e.target.value } }))} />
                  <Input aria-label="Option name ta" lang="ta" placeholder="தமிழ்" value={m.name.ta ?? ""} onChange={(e) => setM(g.key, m.key, (x) => ({ ...x, name: { ...x.name, ta: e.target.value } }))} />
                  <Input aria-label="Extra Rs" type="number" step="0.01" title="Extra Rs" value={m.price} onChange={(e) => setM(g.key, m.key, (x) => ({ ...x, price: e.target.value }))} />
                  <button type="button" aria-label="Remove option" className="grid h-10 w-10 place-items-center rounded-full text-muted hover:bg-bad-soft hover:text-bad" onClick={() => setG(g.key, (x) => ({ ...x, mods: x.mods.filter((y) => y.key !== m.key) }))}>
                    <X size={18} />
                  </button>
                </div>
              ))}
              {g.mods.length ? <span className="text-xs text-muted">Last box: extra price in Rs (0 = no extra).</span> : null}
              <div>
                <Button type="button" size="sm" onClick={() => setG(g.key, (x) => ({ ...x, mods: [...x.mods, { key: newKey(), name: {}, price: "0.00", sort: x.mods.length, is_active: true }] }))}>
                  <Plus size={16} /> Option
                </Button>
              </div>
            </div>
          </div>
        );
      })}
      <div>
        <Button type="button" variant="soft" onClick={() => setGroups((l) => [...l, { key: newKey(), name: {}, min: "0", max: "1", sort: l.length, mods: [] }])}>
          <Plus size={18} /> Add-on group
        </Button>
      </div>
    </>
  );
}

function ItemPicker({ items, cats, children }: { items: AdminItem[]; cats: AdminCategory[]; children: (i: AdminItem) => React.ReactNode }) {
  const [q, setQ] = useState("");
  const catName = Object.fromEntries(cats.map((c) => [c.id, c.name.en ?? ""]));
  const shown = items.filter((i) => !q || `${i.name.en} ${catName[i.category_id]}`.toLowerCase().includes(q.toLowerCase()));
  return (
    <div className="flex flex-col gap-2">
      {items.length > 8 ? <Input aria-label="Find item" placeholder="Find an item…" value={q} onChange={(e) => setQ(e.target.value)} className="h-10" /> : null}
      <div className="flex max-h-72 flex-col overflow-auto rounded-xl bg-surface ring-1 ring-line">
        {shown.map((i) => (
          <div key={i.id} className="flex min-h-12 items-center gap-3 border-b border-line px-3 py-1.5 last:border-0">
            {children(i)}
          </div>
        ))}
        {shown.length ? null : <p className="p-3 text-sm text-muted">No items.</p>}
      </div>
    </div>
  );
}

function ComboTab({ slots, setSlots, items, cats, selfId }: { slots: SlotDraft[]; setSlots: React.Dispatch<React.SetStateAction<SlotDraft[]>>; items: AdminItem[]; cats: AdminCategory[]; selfId?: string }) {
  const candidates = items.filter((i) => i.id !== selfId && !i.combo_slots.length);
  const catName = Object.fromEntries(cats.map((c) => [c.id, c.name.en ?? ""]));
  const setS = (key: string, fn: (s: SlotDraft) => SlotDraft) => setSlots((l) => l.map((s) => (s.key === key ? fn(s) : s)));
  return (
    <>
      <p className="-mt-2 text-sm text-muted">A meal has its own price (above). The guest picks one item for each part; each part is cooked at its own station. Leave empty for a normal item.</p>
      {slots.map((s) => (
        <div key={s.key} className="flex flex-col gap-3 rounded-xl p-4 ring-1 ring-line">
          <div className="grid gap-2 sm:grid-cols-[1fr_1fr_1fr_auto]">
            <Input aria-label="Part name" placeholder="Part, e.g. Drink *" value={s.name.en ?? ""} onChange={(e) => setS(s.key, (x) => ({ ...x, name: { ...x.name, en: e.target.value } }))} />
            <Input aria-label="Part name si" lang="si" placeholder="සිංහල" value={s.name.si ?? ""} onChange={(e) => setS(s.key, (x) => ({ ...x, name: { ...x.name, si: e.target.value } }))} />
            <Input aria-label="Part name ta" lang="ta" placeholder="தமிழ்" value={s.name.ta ?? ""} onChange={(e) => setS(s.key, (x) => ({ ...x, name: { ...x.name, ta: e.target.value } }))} />
            <Button type="button" size="sm" variant="ghost" className="self-center hover:text-bad" onClick={() => setSlots((l) => l.filter((x) => x.key !== s.key))}>
              Remove part
            </Button>
          </div>
          <div className="text-sm text-muted">
            Guest picks one of: <span className="text-ink">{s.item_ids.length} picked</span> · add an extra price for bigger choices (e.g. a large drink)
          </div>
          <ItemPicker items={candidates} cats={cats}>
            {(i) => {
              const on = s.item_ids.includes(i.id);
              return (
                <>
                  <input type="checkbox" aria-label={`Pick ${i.name.en}`} className="h-5 w-5 accent-accent" checked={on} onChange={(e) => setS(s.key, (x) => ({ ...x, item_ids: e.target.checked ? [...x.item_ids, i.id] : x.item_ids.filter((y) => y !== i.id) }))} />
                  <span className="min-w-0 flex-1 text-[15px] font-semibold">
                    {i.name.en} <span className="font-semibold text-muted">· {catName[i.category_id]} · {i.station}</span>
                  </span>
                  {on ? (
                    <label className="flex items-center gap-1.5 whitespace-nowrap text-sm font-bold text-muted">
                      + Rs
                      <Input aria-label="Upcharge" type="number" step="0.01" min={0} className="h-9 w-28" value={s.up[i.id] ?? "0.00"} onChange={(e) => setS(s.key, (x) => ({ ...x, up: { ...x.up, [i.id]: e.target.value } }))} />
                    </label>
                  ) : null}
                </>
              );
            }}
          </ItemPicker>
        </div>
      ))}
      <div>
        <Button type="button" variant="soft" onClick={() => setSlots((l) => [...l, { key: newKey(), name: {}, item_ids: [], up: {} }])}>
          <Plus size={18} /> Meal part
        </Button>
      </div>
    </>
  );
}

function SuggestTab({ value, onChange, items, cats, selfId }: { value: string[]; onChange: (v: string[]) => void; items: AdminItem[]; cats: AdminCategory[]; selfId?: string }) {
  const full = value.length >= 6;
  return (
    <>
      <p className="-mt-2 flex items-start justify-between gap-3 text-sm text-muted">
        After a guest adds this item, the kiosk and table screens suggest these. Items in a meal get a “Make it a meal” offer by themselves.
        <Badge tone={full ? "warn" : "muted"}>{value.length} / 6</Badge>
      </p>
      <ItemPicker items={items.filter((i) => i.id !== selfId)} cats={cats}>
        {(i) => {
          const on = value.includes(i.id);
          return (
            <label className="flex flex-1 cursor-pointer items-center gap-3">
              <input type="checkbox" aria-label={`Suggest ${i.name.en}`} className="h-5 w-5 accent-accent" checked={on} disabled={!on && full} onChange={(e) => onChange(e.target.checked ? [...value, i.id] : value.filter((x) => x !== i.id))} />
              <span className={`flex-1 text-[15px] font-semibold ${!on && full ? "text-muted" : ""}`}>{i.name.en}</span>
              <span className="num text-sm font-bold text-muted">{money(i.price)}</span>
            </label>
          );
        }}
      </ItemPicker>
    </>
  );
}
