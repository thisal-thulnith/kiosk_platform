# Design guide: clean and simple (v4)

Written for: anyone building or changing a screen in `frontend/`. Every screen follows these rules so
the whole platform feels like one simple product.

## The look (v4: Meta Business Suite meets Uber)

- **Ink, not black.** Text and main buttons use the soft blue-black ink `#1C2B33`. Secondary text
  is `#65676B`. The page is light grey `#F0F2F5` and panels are white (`bg-surface`), separated by
  `shadow-soft` (a 1 px edge) or thin lines (`border-line`).
- **One blue for "this one".** `accent` (`#0866FF`) marks the selected nav item, the selected tab,
  links and focus (`bg-accent-soft text-accent` for a selected row). The main button is ink
  (`Button variant="primary"`). Green (`ok`) means paid / done, red (`bad`) a problem.
- **The restaurant's colour** (`brand`) is for its logo and the guests' screens (kiosk / table), and
  the occasional small highlight — never staff chrome.
- **Full screen.** Consoles use `ui/shell.tsx` `AppShell`: a left rail (labels on desktop, icons on
  tablets), bottom tabs on phones, a top bar with the page title and actions. Content fills the width
  (`PageGrid` 1 → 2 → 3 columns); only forms keep a readable width.
- **Type:** Figtree. Page titles `text-2xl`/`text-3xl font-bold`, section titles `text-lg font-bold`,
  body 15 px. Big numbers `font-bold tabular-nums`.
- **Dishes:** rectangular rounded photos; without a photo, `ui/food.tsx` `<Dish>` draws a soft tint
  with a fine line icon. **No emoji, no letter avatars, no initials** (`Logo`, `Avatar`).
- **Corners:** cards `rounded-2xl`, buttons and inputs `rounded-xl`, chips and tabs `rounded-full`.
- **Inputs:** white with a thin line, blue focus ring (`inputCls`).
- **Logins** each have their own face in the same family: our team (dark ink split screen), a
  restaurant owner (the restaurant's logo and colour), a screen sign-in (one big code box), staff
  (a phone-style PIN pad).

## The five rules

1. **One main action per view.** Exactly one `Button variant="primary"` (ink) is visible per view
   or panel (use `"ok"` green only to confirm a payment). Everything else is
   `default`, `soft` or `ghost`. Rare actions go into `<MoreMenu>` (the "⋯" button).
2. **Show less.** If something is not needed for the next step, hide it until asked (a "⋯" menu, a
   detail sheet, "Show more"). No help paragraphs where a clear label works. Tabs: at most 5 (use
   grouping). A row of buttons: at most 2 visible plus "⋯".
3. **Calm colour.** Backgrounds `bg-canvas` or white, panels `bg-surface` with a hairline, no
   coloured borders around cards. The brand colour only as an accent for the current selection. State colours
   (`ok`, `warn`, `bad`, `info`) only as small dots, badges or soft tints (`bg-*-soft`) — never big
   blocks, except the one thing that truly needs attention right now.
4. **Smooth.** Windows and sheets slide (`Modal`), tabs slide (`Segmented`), new views fade in
   (`Appear`), lists animate in/out (`motion` `AnimatePresence` + `layout`), presses shrink slightly.
   Loading shows `Skeleton`s, never "Loading…". Everything respects "reduce motion" (handled by
   `ToastProvider`'s `MotionConfig` and theme.css).
5. **One icon style.** Icons come from `lucide-react` (stroke 2, size 18–22). No emoji anywhere.

## Building blocks (`ui/kit.tsx`)

| Use | For |
|---|---|
| `Button` variants `primary` (ink) / `brand` (restaurant colour, rare) / `ok` / `default` / `soft` / `ghost` / `danger`, sizes `sm` `md` `lg` `xl` | actions |
| `IconButton label=…` | icon-only actions (always with a label) |
| `MoreMenu items=[{label, onClick, icon?, danger?}]` | the quiet actions |
| `Card` | a panel (`rounded-2xl bg-surface shadow-soft p-5`) |
| `AppShell`, `PageGrid` (`ui/shell.tsx`) | the full-screen console frame and its content grid |
| `SectionTitle title hint right` | heading of a section |
| `ListRow lead title sub trail onClick` | any list (orders, screens, staff, payments) |
| `Badge tone`, `Status tone pulse` | small state labels / dots |
| `Segmented` | tabs (sliding highlight) |
| `Modal title footer` | windows (bottom sheet on phones); put the main button in `footer` |
| `Field label hint` + `Input` / `inputCls` | forms |
| `Empty icon action` | nothing here yet |
| `Skeleton`, `SkeletonList` | loading |
| `Appear` | fade-in of a view |
| `useToast()` | short messages (shown at the top, never over the bottom buttons) |
| `LivePill` | connection state |

Also: `ui/logo.tsx` `<Logo>` (restaurant logo or a clean mark) and `<Avatar>` (a person icon),
`ui/food.tsx` `<Dish>` (dish photo or a neutral line-icon tile; `round` for small thumbnails), `ui/ordering.tsx` (`MenuGrid`, `CartLines`, `CartSummary`), `lib/brand.ts` (the
restaurant's colour, logo and light / dark theme, already applied by the screen gate and the console
gate).

## Type and spacing

- Font: Figtree. Weights: `font-semibold` for labels and buttons, `font-bold` for headings and
  numbers; `font-black` only for very large numbers (order number, total on a kiosk).
- Sizes: page title `text-2xl font-bold tracking-tight`, section `text-lg font-bold`, body 15 px,
  small `text-sm text-muted`.
- Spacing: panels `p-5`, gaps `gap-3`/`gap-4`, pages `p-4 sm:p-6`; generous white space.
- Corners: cards `rounded-2xl`, controls `rounded-xl`, pills `rounded-full`.
- Touch targets ≥ 44 px (staff), ≥ 56 px (kiosk guests).

## Colour tokens

`canvas` `surface` `ink` `muted` `line`, `accent` `accent-soft` (selection, links, focus), `brand` `brand-dark` (brand text on light) `brand-soft`
`on-brand` (text on brand), `ok` `warn` `bad` `info` + `-soft`. Never hard-code a brand colour; never
`bg-white` / `text-white` on themed surfaces (`text-white` is fine on `bg-ok` / `bg-bad`). Kitchen
display and status board are always dark.

## Addresses

Every restaurant has its own path: `/{code}/pos`, `/{code}/waiter`, `/{code}/kitchen`,
`/{code}/kiosk`, `/{code}/board`, `/{code}/owner`, `/{code}/menu`, `/{code}/setup`. Our console is
`/platform`, a tablet's start page is `/`. Build links with `lib/screens.ts` (`screenAddress`,
`consoleUrl`), never by hand.

## The table visit (what staff screens show)

calling · wants the bill · **food ready → take it to the table** · waiting payment · cooking ·
**eating** · **needs cleaning** · free (· closed). Waiters work from one task list: take food to a
table (Served), answer calls, bring the bill, clean a table (Cleaned), read new guest feedback (low
ratings first, "Seen").
