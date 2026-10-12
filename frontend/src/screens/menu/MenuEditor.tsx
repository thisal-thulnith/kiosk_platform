// Menu editor for the restaurant (owner / manager) and our installers: categories, dishes and the
// tax & service-charge rules, in the full-screen console frame (ui/shell AppShell). Every save reaches
// all screens at once.
import { consoleUrl } from "../../lib/screens";
import { useCallback, useEffect, useMemo, useState } from "react";
import type { Admin } from "../../lib/admin";
import { money } from "../../lib/format";
import { VenuePicker } from "../../ui/adminGate";
import { Dish } from "../../ui/food";
import { AppShell, type NavItem } from "../../ui/shell";
import { motion } from "motion/react";
import { ArrowLeft, LogOut, Pencil, Percent, Plus, Search, Store, UtensilsCrossed } from "lucide-react";
import { Appear, Badge, Button, Card, Empty, MoreMenu, Skeleton, Status, spring, useToast } from "../../ui/kit";
import { CategoryEditor } from "./CategoryEditor";
import { ItemEditor } from "./ItemEditor";
import { SAVED, windowLabel, type AdminCategory, type AdminItem, type TaxRule } from "./model";
import { Input } from "./parts";
import { TaxList, TaxRuleEditor } from "./TaxRules";

type View = "menu" | "tax";
type Editing = { kind: "item"; item: AdminItem | null } | { kind: "cat"; cat: AdminCategory | null } | { kind: "rule"; rule: TaxRule | null } | null;
const NAV: (NavItem & { key: View })[] = [
  { key: "menu", label: "Dishes", icon: UtensilsCrossed },
  { key: "tax", label: "Taxes & charges", icon: Percent },
];

export function MenuEditor({ admin }: { admin: Admin }) {
  const toast = useToast();
  const [cats, setCats] = useState<AdminCategory[]>([]);
  const [items, setItems] = useState<AdminItem[]>([]);
  const [rules, setRules] = useState<TaxRule[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [catId, setCatId] = useState<string | null>(null);
  const [view, setView] = useState<View>(() => (location.hash === "#tax" ? "tax" : "menu"));
  const [editing, setEditing] = useState<Editing>(null);
  const [q, setQ] = useState("");
  const installer = admin.kind === "installer";
  const venue = admin.venue;
  useEffect(() => history.replaceState(null, "", view === "tax" ? "#tax" : location.pathname + location.search), [view]);

  const load = useCallback(async () => {
    try {
      const [c, i, r] = await Promise.all([admin.get<AdminCategory[]>(admin.v("/menu/categories")), admin.get<AdminItem[]>(admin.v("/menu/items")), admin.get<TaxRule[]>(admin.v("/tax-rules"))]);
      setCats(c);
      setItems(i);
      setRules(r);
      setCatId((cur) => (c.some((x) => x.id === cur) ? cur : (c[0]?.id ?? null)));
      setLoaded(true);
    } catch (x) {
      toast((x as Error).message, "bad", 6000);
    }
  }, [admin]);
  useEffect(() => void load(), [load]);

  const saved = async (pickCat?: string) => {
    setEditing(null);
    if (pickCat) setCatId(pickCat);
    await load();
    toast(SAVED, "ok");
  };

  const cat = cats.find((c) => c.id === catId) ?? null;
  const count = useMemo(() => Object.fromEntries(cats.map((c) => [c.id, items.filter((i) => i.category_id === c.id).length])), [cats, items]);
  const search = q.trim().toLowerCase();
  const shown = (search ? items.filter((i) => Object.values(i.name).some((n) => n?.toLowerCase().includes(search)) || (i.external_code ?? "").toLowerCase().includes(search)) : items.filter((i) => i.category_id === catId)).sort((a, b) => a.sort - b.sort);
  const missing = items.filter((i) => !i.name.si || !i.name.ta).length;
  const back = installer ? "Setup console" : "Owner app";
  const backUrl = consoleUrl(installer ? "setup" : "owner", venue?.code);

  const newItem = () => setEditing({ kind: "item", item: null });
  const newCat = () => setEditing({ kind: "cat", cat: null });
  const pickCat = (id: string) => (setCatId(id), setQ(""), document.querySelector("main")?.scrollTo({ top: 0 }));

  const actions =
    view === "menu" ? (
      <>
        <label className="relative w-full min-w-0 flex-1 sm:w-64 sm:flex-none lg:w-80">
          <Search size={18} className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-muted" />
          <Input aria-label="Find a dish" placeholder="Find a dish" value={q} onChange={(e) => setQ(e.target.value)} className="h-11! rounded-full! bg-surface! pl-11 shadow-soft ring-0! focus:ring-2! sm:bg-canvas! sm:shadow-none sm:focus:bg-surface!" />
        </label>
        <Button variant="primary" disabled={!cats.length} onClick={newItem}>
          <Plus size={18} /> New dish
        </Button>
      </>
    ) : (
      <Button variant="primary" onClick={() => setEditing({ kind: "rule", rule: null })}>
        <Plus size={18} /> New tax or charge
      </Button>
    );

  return (
    <AppShell
      name={venue?.name ?? "Menu"}
      sub={installer ? "Menu editor · installation team" : "Menu editor"}
      logo={venue?.settings?.logo_url}
      nav={NAV}
      active={view}
      onNav={(k) => setView(k as View)}
      title={view === "tax" ? "Taxes & charges" : search ? "Search results" : "Dishes"}
      actions={actions}
      account={
        <div className="flex items-center gap-1">
          {installer ? (
            <span className="hidden lg:inline-flex">
              <Badge tone="info">Installation team</Badge>
            </span>
          ) : null}
          <span className="hidden sm:inline-flex">
            <VenuePicker admin={admin} />
          </span>
          <MoreMenu
            items={[
              ...admin.venues.filter((v) => v.id !== venue?.id).map((v) => ({ label: `Open ${v.name}`, icon: <Store size={18} />, onClick: () => admin.chooseVenue(v.id) })),
              { label: back, icon: <ArrowLeft size={18} />, onClick: () => (location.href = backUrl) },
              { label: "Log out", icon: <LogOut size={18} />, onClick: () => (admin.logout(), location.reload()) },
            ]}
          />
        </div>
      }
      footer={loaded ? missing ? <Status tone="warn">{missing} need a Sinhala or Tamil name</Status> : <Status tone="ok">Every name in 3 languages</Status> : null}
    >
      <div className="mx-auto w-full max-w-[1800px]">
        {!loaded ? (
          <div className="grid gap-6 md:grid-cols-[232px_minmax(0,1fr)] xl:grid-cols-[260px_minmax(0,1fr)]">
            <Skeleton className="hidden h-96 rounded-2xl md:block" />
            <div className="grid grid-cols-2 gap-4 pt-16 sm:grid-cols-[repeat(auto-fill,minmax(210px,1fr))]">
              {Array.from({ length: 8 }, (_, i) => (
                <Skeleton key={i} className="aspect-[4/4] rounded-2xl" />
              ))}
            </div>
          </div>
        ) : view === "tax" ? (
          <Appear>
            <TaxList admin={admin} rules={rules} onEdit={(rule) => setEditing({ kind: "rule", rule })} />
          </Appear>
        ) : (
          <div className="grid items-start gap-4 md:grid-cols-[232px_minmax(0,1fr)] md:gap-6 xl:grid-cols-[260px_minmax(0,1fr)]">
            {/* Phones: categories as chips that scroll sideways. */}
            <div className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1 [scrollbar-width:none] md:hidden">
              {cats.map((c) => {
                const on = c.id === catId && !search;
                return (
                  <button key={c.id} onClick={() => pickCat(c.id)} className={`cat-row ${on ? "on" : ""} flex h-10 shrink-0 items-center gap-1.5 rounded-full px-4 text-[15px] font-semibold transition active:scale-[.97] ${on ? "bg-accent-soft text-accent ring-1 ring-accent/25" : "bg-surface text-ink shadow-soft"} ${c.is_active ? "" : "opacity-60"}`}>
                    {c.name.en} <span className={`num text-sm ${on ? "opacity-70" : "text-muted"}`}>{count[c.id] ?? 0}</span>
                  </button>
                );
              })}
              <button onClick={newCat} aria-label="New category" className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-surface text-ink shadow-soft">
                <Plus size={20} />
              </button>
            </div>
            {/* Tablets and up: a categories column, like a second navigation. */}
            <nav aria-label="Categories" className="sticky top-0 hidden max-h-[calc(100dvh-8rem)] flex-col overflow-y-auto rounded-2xl bg-surface p-2 shadow-soft md:flex">
              <div className="flex items-center justify-between px-3 pb-1.5 pt-2">
                <h2 className="text-[13px] font-semibold uppercase tracking-wide text-muted">Categories</h2>
                <span className="num text-[13px] text-muted">{items.length} dishes</span>
              </div>
              {cats.length ? null : <p className="px-3 py-2 text-sm text-muted">No categories yet. Add the first one (e.g. Mains, Drinks).</p>}
              {cats.map((c) => {
                const on = c.id === catId && !search;
                return (
                  <button key={c.id} onClick={() => pickCat(c.id)} className={`cat-row ${on ? "on" : ""} relative flex items-center gap-3 rounded-xl px-3 py-2.5 text-left transition-colors ${on ? "text-accent" : "hover:bg-canvas"} ${c.is_active ? "" : "opacity-60"}`}>
                    {on ? <motion.span layoutId="cat-on" transition={spring} className="absolute inset-0 rounded-xl bg-accent-soft" /> : null}
                    <span className="relative min-w-0 flex-1">
                      <span className="block truncate text-[15px] font-semibold">{c.name.en}</span>
                      <span className={`block truncate text-xs ${on ? "text-accent/80" : "text-muted"}`}>{!c.is_active ? "Hidden" : c.windows.length ? c.windows.map(windowLabel).join(", ") : "All day"}</span>
                    </span>
                    <span className={`num relative text-sm ${on ? "font-semibold" : "text-muted"}`}>{count[c.id] ?? 0}</span>
                  </button>
                );
              })}
              <div className="mt-1 border-t border-line pt-1">
                <Button variant="ghost" size="sm" className="w-full justify-start px-3" onClick={newCat}>
                  <Plus size={16} /> New category
                </Button>
              </div>
            </nav>

            <section className="flex min-w-0 flex-col gap-4">
              <div className="flex min-h-11 items-center gap-3">
                <div className="min-w-0 flex-1">
                  {search ? (
                    <>
                      <h2 className="text-xl font-bold tracking-[-0.01em]">“{q.trim()}”</h2>
                      <span className="text-sm text-muted">
                        {shown.length} {shown.length === 1 ? "dish" : "dishes"} found
                      </span>
                    </>
                  ) : cat ? (
                    <>
                      <h2 className="flex items-center gap-2 truncate text-xl font-bold tracking-[-0.01em]">
                        {cat.name.en}
                        {!cat.is_active ? <Badge>Hidden</Badge> : null}
                      </h2>
                      <span className="text-sm text-muted">
                        {shown.length} {shown.length === 1 ? "dish" : "dishes"}
                        {cat.windows.length ? ` · served ${cat.windows.map(windowLabel).join(", ")}` : " · all day"}
                      </span>
                    </>
                  ) : (
                    <h2 className="text-xl font-bold text-muted">Create a category first</h2>
                  )}
                </div>
                {missing ? (
                  <span className="hidden items-center gap-1.5 text-sm text-muted lg:inline-flex xl:hidden" title="Items missing a Sinhala or Tamil name">
                    <span className="h-2 w-2 rounded-full bg-warn" /> {missing} need a Sinhala or Tamil name
                  </span>
                ) : null}
                {cat && !search ? (
                  <Button variant="default" size="sm" onClick={() => setEditing({ kind: "cat", cat })}>
                    <Pencil size={16} /> <span className="max-sm:hidden">Edit category</span>
                  </Button>
                ) : null}
              </div>
              {shown.length ? (
                <div key={search ? "search" : catId} className="menu-grid grid grid-cols-2 gap-3 sm:grid-cols-[repeat(auto-fill,minmax(210px,1fr))] sm:gap-4">
                  {shown.map((i, n) => (
                    <motion.div key={i.id} className="flex" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.22, delay: Math.min(n, 12) * 0.02 }}>
                      <ItemTile item={i} catName={cats.find((c) => c.id === i.category_id)?.name.en} showCat={!!search} onClick={() => setEditing({ kind: "item", item: i })} />
                    </motion.div>
                  ))}
                </div>
              ) : (
                <Card>
                  <Empty icon={<UtensilsCrossed size={24} />} action={cat && !search ? <Button onClick={newItem}><Plus size={16} /> Add a dish</Button> : !cats.length ? <Button onClick={newCat}><Plus size={16} /> New category</Button> : null}>
                    {search ? "No dish matches." : cat ? "No dishes in this category yet." : "Add a category, then its dishes."}
                  </Empty>
                </Card>
              )}
            </section>
          </div>
        )}
      </div>

      {editing?.kind === "item" ? <ItemEditor admin={admin} item={editing.item} cats={cats} items={items} defaultCat={catId} onClose={() => setEditing(null)} onSaved={(c) => saved(c)} /> : null}
      {editing?.kind === "cat" ? <CategoryEditor admin={admin} cat={editing.cat} nextSort={cats.length + 1} onClose={() => setEditing(null)} onSaved={(c) => saved(c.id)} /> : null}
      {editing?.kind === "rule" ? <TaxRuleEditor admin={admin} rule={editing.rule} rules={rules} taxCats={items.map((i) => i.tax_category)} onClose={() => setEditing(null)} onSaved={() => saved()} /> : null}
    </AppShell>
  );
}

/** One dish, Uber Eats style: a white card with the rectangular photo on top, then name, price and a short line. */
function ItemTile({ item: i, catName, showCat, onClick }: { item: AdminItem; catName?: string; showCat: boolean; onClick: () => void }) {
  const meta = [showCat ? catName : null, i.combo_slots.length ? "Meal" : null, i.modifier_groups.length ? `${i.modifier_groups.length} add-on${i.modifier_groups.length > 1 ? "s" : ""}` : null, i.windows.length ? i.windows.map(windowLabel).join(", ") : null].filter(Boolean).join(" · ");
  const missing = !i.name.si || !i.name.ta;
  return (
    <button onClick={onClick} data-item={i.name.en} className={`tile group flex w-full min-w-0 flex-col overflow-hidden rounded-2xl bg-surface text-left shadow-soft transition hover:shadow-lift active:scale-[.98] ${i.is_active ? "" : "opacity-60"}`}>
      <span className="relative block w-full overflow-hidden">
        <Dish src={i.image_url} name={i.name.en ?? ""} hint={catName} size={160} className="aspect-[4/3] h-auto! w-full! rounded-none! transition duration-300 group-hover:scale-[1.03]" />
        <span className="absolute left-2.5 top-2.5 flex flex-col items-start gap-1">
          {!i.is_available ? <Badge tone="bad" className="bg-surface!">Sold out</Badge> : null}
          {!i.is_active ? <Badge className="bg-surface! text-ink!">Hidden</Badge> : null}
        </span>
        <span className="absolute right-2.5 top-2.5 grid h-8 w-8 place-items-center rounded-full bg-surface/95 text-ink opacity-0 shadow-soft transition group-hover:opacity-100 group-focus-visible:opacity-100" aria-hidden>
          <Pencil size={14} />
        </span>
      </span>
      <span className="flex flex-1 flex-col px-3.5 pb-3.5 pt-3">
        <span className="flex items-start gap-1.5">
          <span className="line-clamp-2 min-w-0 flex-1 text-[15px] font-semibold leading-snug">{i.name.en}</span>
          {missing ? <span title="Missing a Sinhala or Tamil name" className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-warn" /> : null}
        </span>
        <span className="num mt-1 text-[15px] font-bold">{money(i.price)}</span>
        {meta || i.station ? <span className="mt-0.5 truncate text-[13px] text-muted">{meta || i.station}</span> : null}
      </span>
    </button>
  );
}
