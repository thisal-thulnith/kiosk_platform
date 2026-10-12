# How every system works (from the BRD, Product Details and Full Plan)

Sources, read in full: the three BRD versions (`AI_Kiosk_System_Sri_Lanka_BRD*.pdf`), `AI-Kiosk-Product-Details.pdf`
(8 pages) and `ai-kiosk-full-plan (1).pdf` (30 pages). Each system below says what the documents require,
how it works step by step, and what is built in this repository today.

Status: ✅ built · 🟡 partly · ❌ not yet.

## Build progress

Built one by one in the order below. Each system has API tests (`uv run pytest`) and a browser check in
`tools/screens/e2e_react.py` (React screens) and `e2e_hybrid.py`.

| # | System | Status | What exists now |
|---|---|---|---|
| 1 | Packages and modules | ✅ | R-/H- module catalogue, Pack 1/2/3 tiers from the Product Details, Custom and Hotel, builder rules, screen limits, automatic screen slots (Table T1…Tn), price list and quotes, package picker in the Platform console, usage in the Setup console |
| 3 | Menu and pricing manager | ✅ | Menu editor (3 languages, photos, prices, stations, allergens, cooking time, time windows, add-ons, combos), per-screen categories, sold-out alert for placed orders |
| 4 | Order engine | ✅ | Priority (rush / VIP), promised times, hold & fire, dine-in open tabs (rounds), waiter serve |
| 5 | Tax and invoices | ✅ | SSCL as a rule, tax editor, tax ledger CSV (one column per charge), VAT number and legal name on receipts |
| 6 | Payments | ✅ (mock gateways) | LankaQR, card reader / SoftPOS, cash, split bill, reconciliation against the bank settlement file, table lock, barcode |
| 7 | Table screen | ✅ | Pay first or open tab, order more / pay the bill, call waiter, request bill, waiter assist (staff PIN on the table), Android portrait layout |
| 9 | Cashier | ✅ | Split bill, rush / VIP, fire next course, hold, guest calls, card reader |
| 10 | Waiter handheld | ✅ | Table map, order for a table with hold & fire, ready to serve, guest calls, bill by LankaQR |
| 11 | Kitchen display | ✅ | Priority order, due times, held items and fire, remake with reason, void / change alerts, kitchen load, bump-bar keys |
| 14 | Owner dashboard | ✅ | Sales, late orders, kitchen load, completion by channel, voids / refunds / remakes, guest-call times, reconciliation, accounting downloads |
| 8 | Self-order kiosk | ✅ | "Goes well with" suggestions, "Make it a meal", upsell tracking, Easy reach (low-reach, big text), welcome photos, help button, idle reset, card reader |
| 13 | Overhead menu board | ✅ | 55-inch board screen: pages by category, photos, 3 languages, prices, live sold out, meal tags |
| 16 | Device manager | ✅ (MDM later) | Remote reload and identify, offline-since and top-priority warnings for kitchen and cashier screens, one-time setup, auto-reconnect |
| 2, 17 | Operating modes and AI engine | ✅ levels 0–3 | Manual / AI switch with levels, insights for the owner, learned upsell, best sellers by time of day, quick items and longer waits when the kitchen is busy, decision log with reasons, one-tap back to Manual, prices never changed |
| 19, 26 | Loyalty and data protection | ✅ | Phone-number members with consent text stored, points on payment (reversed on refund), tiers with automatic discounts before service charge and taxes, "your usual", owner export and forget (PDPA), shared across branches, never across restaurants |
| 20 | Inventory and AI level 4 | ✅ | Stock in portions per tracked item; sales come off when cooking starts, and a void puts uncooked portions back; auto sold-out at zero and back after a delivery; low-stock alerts on the KDS and cashier; waste and counts from the KDS; deliveries, counts, use-by times and the moves log for the owner; guests cannot order more than is left. AI level 4 (needs R-INV) proposes discounts only, within the owner's cap (at most 50%), on perishable stock near its use-by time; the owner approves by default; deal prices show on the kiosk, table and board and are charged by the server; Manual mode ends every deal |
| 27a | Install setup: payments, printers, go-live checklist | ✅ | Payment methods on or off per restaurant (enforced by the server, hidden on screens); LankaQR merchant ID and key stored encrypted, with Test connection; Test reader per card screen. Printers as records with roles (receipt, number slip, kitchen per station) and a cash drawer, all through a cloud print queue: **cloud printers** (Star CloudPRNT, polled by the printer itself, no local server) or a **USB printer on a cashier, kitchen or waiter screen** (WebUSB, auto-reconnect, prints what it missed), with an add wizard, connect steps, test page that ticks itself, and failure alerts. The go-live checklist has 9 checks |
| 27b | Installer-only setup, one-code screens, equipment | ✅ | The Platform console (admin panel) adds restaurants, and each has its own Setup console ("Open setup console", setup progress n/11). The Setup console uses the installation team's platform login only; restaurants keep the Owner dashboard and Menu editor. Screens are set up with one secret code or a QR code (server address + code) on the app start page: the code decides the screen type. Screens never log out, and only re-pairing or disabling in the console ends a setup (`device_not_set_up`). Hidden settings need a manager PIN, and forgetting the setup needs an installer login. Equipment chosen with the package has required dependencies (kiosk → status board and kiosk printer, cashier → receipt printer and cash drawer, table → cashier, waiter → tables, any screen → router), is priced in the quote, and is tracked in the Setup console (counted from printers and readers; router and UPS ticked on site). Kiosks can have their own printer (receipts and number slips print where the guest paid) and have their own checklist item. Contract for the future APK: docs/DEVICE_APP.md |
| 28 | Hybrid offline (hub + cloud), keys, SMS | ✅ | Cloud or Hybrid per restaurant. A **hub** (same software in edge mode, `kiosk hub-setup` with a one-time code from the console) serves the restaurant's screens over the local network and syncs both ways. Config (menu, staff, screens' key hashes, printers, stock settings, deals) flows cloud → hub; orders, invoices, shifts, stock moves and sold-out switches flow hub → cloud through the outbox; the cloud's change feed flows back. There is one writer at a time: while the hub is alive, the cloud answers screens `use_hub` and hands bank and card confirmations to the hub; when the hub is down, the cloud takes over (numbers from 500, invoices in a C series); the hub catches up before taking charge again. Screens switch Local ↔ Cloud by themselves (`net` in core.js) and show it. The Network card and checklist show hub status. Keys: wrong-code and wrong-password limits, API docs off in production, CORS for hub pages. **SMS**: "your order is ready" and a signed receipt link to the guest's mobile (that order only), queued and retried, switchable per restaurant; the kiosk resets after the order screen so nothing of the last guest stays. Tested with two real servers: `tools/screens/e2e_hybrid.py` |
| 29 | Service flows, all-in-one hardware, POS bridge | ✅ | **Flows** chosen with the package (self-order kiosks, table ordering, open tab, counter POS, waiter service, keep their current POS, order-ready display, menu board, kitchen printer, offline Hybrid, guest SMS). Each brings its screens, modules, equipment and settings; flows it depends on are locked in (waiter → table → cashier, unless their own POS is the cashier; hub → UPS). **Hardware models** per screen (all-in-one kiosk, POS terminal, kitchen screen): one choice creates the built-in printer, reader and scanner and lists what's left to do. **POS bridge** (R-BRIDGE): signed order events to their POS with retries; their POS marks orders paid (kitchen, receipt, points follow), pulls orders, and pushes its menu by PLU; installer card with test, API key, CSV menu import and event log; PLU field in the menu editor. Guide: [FULL_SYSTEM_A_TO_Z.md](FULL_SYSTEM_A_TO_Z.md) |
| 30 | Five screens, table lock, POS runs the floor | ✅ | The product is scoped to **Table, Self-order kiosk, POS, KDS and the optional Order status board** (waiter handhelds and menu boards are no longer offered; tiers no longer force a status board). **Staff open each table** (table_access): an empty table only shows "Call staff"; the POS opens it (answering the call), closing needs everything paid and clears the table; a paid tab closes its table. The **POS Tables view** shows every table's state and what it owes, its orders (take payment) and calls; every call, new order and ready order rings on the POS with the table number |
| 18, 21–25, 27 | Remaining | Next | Voice, hotel (room kiosk, requests, staff app, folio, PMS), support tools, the Android APK itself ([APK_PLAN.md](APK_PLAN.md)), a real SMS gateway and bank adapters |

## The product in one paragraph

A **permanent, venue-provided screen network** (not QR menus on guests' phones) for restaurants and hotels,
on **one cloud back end**. Screens: 8-inch rugged **table / bedside screens with a microphone**, big
**self-order kiosks**, **cashier** screens, **kitchen displays**, 55-inch **overhead menu boards**, wall
**order status boards**, **waiter handhelds**, **hotel room kiosks** and a **staff mobile app**. Every venue
runs in **Manual mode** or **AI Autonomous mode**, switched by the administrator. It is sold as **packages**
(Pack 1 Self-Serve, Pack 2 Counter + Table, Pack 3 Hybrid, Pack 4 Custom, Hotel custom-only), always with a
KDS, delivered **turnkey** (hardware, network, install, training, support), and charged as **SaaS per active
screen** plus hardware sale or lease and integration fees.

---

## A. Foundation

### 1. Packages and modules
**Documents:** Pack 1 Self-Serve (Starter 3 / Standard 5 / Premium 7 screens); Pack 2 Counter + Table
(Starter 1 cashier + 1 status + 1 KDS + 6 tables; Standard + 2 KDS, 12 tables, 1 handheld; Premium 2 cashiers,
overhead board, 20 tables, 2 handhelds); Pack 3 Hybrid = Pack 1 + 2 on one system; Pack 4 Custom from modules
R-CORE, R-KDS (both required), R-STATUS, R-SELF, R-CASH, R-TABLE, R-WAITER, R-BOARD, R-PAY, R-VOICE, R-AI,
R-LOYAL, R-INV, R-BRIDGE / R-POS (only one), R-MULTI, R-ANALYTICS. Builder rules: R-STATUS recommended with
R-SELF or R-CASH; R-AI needs about 2 months of sales data or starts in "suggest only". Hotel: base H-CORE
plus H-DINE, H-HK, H-MAINT, H-SPA, H-CONC, H-LOYAL, H-FOLIO, H-INFO, H-FEED, H-KDS, H-PMS/H-BRIDGE, H-OPS, H-AI.
Add extra tables, kiosks, KDS or boards one by one. Monthly fee per active screen.

**How it works:** platform admin picks a pack and tier (or ticks modules) → the venue gets those modules
switched on and a set of screen slots (e.g. 12 tables) → screens beyond the paid count are refused → the
quote is the sum of modules and screens.

**Built:** ✅ platform console creates restaurants and branches. ❌ modules, tiers, screen limits, builder
rules, quote. **Change:** `modules`, `plans` (pack × tier presets), `subscriptions`, `addons`, a
`require_module()` check on every feature, screen-count limits per type, quote generator.

### 2. Operating modes: Manual and AI Autonomous
**Documents:** toggled at any time by the property administrator "via a secured command interface".
*Manual:* static menus and prices, availability flagged by staff, orders go straight to the KDS first in, first
out, ledgers and inventory driven only by manager input. *AI:* re-orders menus and highlights by weather,
season, kitchen backlog and margin; upsells; slows ordering by raising shown wait times or suggesting fast
items when the kitchen is overloaded; adapts prices to clear perishable stock; sends business alerts. Guardrails
(Full Plan): price caps set by the owner, manager approval option, one-tap back to Manual, the cart price is the
price paid, every AI action logged, allergens / emergency / refunds never depend on AI. Rollout ladder
Level 0 Manual → 1 suggests to staff → 2 upsell to guests → 3 changes menu order and promotions → 4 prices
within caps.

**Built:** ✅ everything today behaves as Manual mode. ❌ the mode switch and all AI behaviour.
**Change:** `venue.settings.mode` + `ai_level` (0–4) set by the owner with password, shown on every screen;
an AI "policy" service that screens ask for layout, highlights, wait time and suggestions; `ai_actions` log;
price caps enforced in `price_cart`.

### 3. Menu and pricing manager
**Documents:** categories, items, photos, add-ons, **combos**, breakfast / lunch / dinner menus,
out-of-stock switch; "change once, updates every screen"; 3-language text checked by a person; allergen tags
entered by the venue; out-of-stock from the KDS removes the item everywhere and **already placed orders get a
staff alert**; multi-branch: central menu and prices (R-MULTI).

**Built:** ✅ categories, items, modifiers (add-ons), 3 languages, time windows, allergens, sold-out on all
screens instantly, admin menu API. 🟡 photos (URL field only). ❌ combos, admin menu editor screen, image upload,
staff alert for placed orders when an item runs out, central menu for branches.

### 4. Order engine
**Documents:** one pipeline for every channel (kiosk, cashier, table, waiter, room); every order has an ID,
status and history; Hybrid: one kitchen queue sorted **by priority and promised time**; edit freely before the
kitchen starts, after that only staff with PIN and a reason; "pay at cashier" release rule A (kitchen after
payment, default) or B (kitchen at once, UNPAID, no hand-over until paid); unpaid orders expire (e.g. 10 min).

**Built:** ✅ one pipeline, IDs, event history, versions, rule A/B, expiry, edit rules, voids with manager PIN
and reason, idempotent retries. ❌ priority (dine-in / takeaway / rush / VIP) and promised times; dine-in
"pay after" (rounds on one open bill).

### 5. Tax and invoices
**Documents:** itemised bill with **10% service charge, VAT and SSCL** shown before checkout (CAA price
transparency); tax rules editable with effective dates, confirmed by a tax adviser; sequential invoice
numbers; records cannot be edited after payment; exports that map to **IRD RAMIS** layouts.

**Built:** ✅ editable tax rules with effective dates and compounding, SC and VAT shown on every screen,
gapless invoice numbers, invoice snapshots, paid orders locked. 🟡 SSCL (the engine supports it; add the rule
once the adviser confirms the treatment). ❌ RAMIS export format.

### 6. Payments
**Documents:** transaction-unique **dynamic LankaQR** on the screen through a CBSL-approved, PCI-DSS gateway;
the gateway callback is the source of truth; **automatic account reconciliation**; card terminal option;
"Pay Cash at Counter" **locks the table profile** and prints a **scannable barcode check**; cashier scans it
and takes cash; split bill; refunds with manager PIN and reason; a QR payment for a cancelled order is refunded;
card data never stored.

**Built:** ✅ LankaQR flow (mock gateway), late-payment auto refund, cash with drawer and shift variance, card
by approval code, **card reader / SoftPOS flow (mock terminal, tested)**, refunds with manager PIN, order lookup
by scanned order ID, token or table, **table lock** while a pay-at-cashier order waits (server-enforced), **barcode**
on the table screen and the kiosk slip, **tap-card** on kiosk and cashier screens. ❌ real gateway,
reconciliation report, split bill.

---

## B. Restaurant screens

### 7. Table screen (Pack 2, R-TABLE)
**Documents:** 8-inch rugged screen fixed to the table, directional mic, locked kiosk mode, mapped to a table
zone. Flow: (1) guest picks English / Sinhala / Tamil (tourist languages by auto-translation) → (2) taps or
**speaks** the order → it goes straight to the KDS → (3) itemised bill with SC, VAT, SSCL → (4a) **Pay here**:
dynamic LankaQR (or card), paid → kitchen → status board Ready → receipt → screen resets; (4b) **Pay at
cashier**: order number + barcode, table locked, cashier scans and takes cash → kitchen. Also: "Your order is
ready" with sound, **call waiter / request bill** button, **waiter assist** (hidden Staff button + PIN to add,
edit or void items, apply discounts, start the bill; every change logged; guest confirms the final list),
self pick-up by default or waiter serve, split bill.

**Built:** ✅ languages, menu, add-ons, cart with SC/VAT, confirm step, LankaQR, pay-at-cashier number with
expiry countdown, barcode, table lock, **call waiter / request bill** (live on the cashier), portrait layout with an
order sheet for 8-inch Android tablets, live tracking, Ready alert with sound, one-time setup, auto-open app,
password-locked settings. ❌ voice, tourist auto-translation, waiter assist mode, split bill, pay-after open bill, card on table (by design: card networks don't allow SoftPOS on
unattended screens; use LankaQR or the waiter's handheld).

### 8. Self-order kiosk (Pack 1, R-SELF)
**Documents:** 24–32 inch portrait; flow language → tap or speak → **add-on suggestions** → bill → LankaQR /
card / cash slip → order number → KDS → status board → pickup; max 3 taps to the first item; **"Call for help"**
button that alerts staff; auto-reset after 60–90 s with a warning; language switch always visible;
lower-placement / wheelchair-height option; tap-to-talk voice; about 1 kiosk per 40–60 peak-hour orders.

**Built:** ✅ language, menu, cart, bill, LankaQR, **tap card on the built-in reader**, pay-at-counter slip with
barcode, order number, tracking, **Help button**, 60 s idle + 15 s warning reset, one-time setup. ❌ add-on
suggestions and combos, accessibility (low-reach) layout, voice, attract media.

### 9. Cashier screen (Pack 2, R-CASH)
**Documents:** 15–22 inch touchscreen with receipt printer, cash drawer and barcode scanner; takeaway orders;
takes cash from "pay at cashier" guests (scan slip or search by table / order number); only the cashier handles
cash, with a shift report; two cashier stations at peak; sees order status.

**Built:** ✅ all of the above (PIN login, shift open/close with variance, takeaway, cash/card/QR, queue of
pay-at-cashier orders, lookup by scan/token/table, hand-over, sold-out switch, receipts, void for managers,
**Guest calls** panel with Coming / Done, **charge on card reader or tap on tablet**). ❌ split bill.

### 10. Waiter assist and handheld (R-WAITER)
**Documents:** 6–8 inch handheld per waiter; waiter can order for a table, edit or void with PIN, serve food
when "waiter serve" is on (KDS/expo marks Ready → waiter app alerts the waiter); every change logged.

**Built:** ✅ `waiter` device type, orders API accepts waiter orders with a table. ❌ waiter screen, "ready to
serve" alerts, waiter serve setting, assist mode on the table screen.

### 11. Kitchen display (KDS, always included)
**Documents:** one queue from all channels; split by station (grill, fry, wok, cold, dessert, beverage,
packing); timer colours green / yellow / red; tap Start and Done, order Ready when all parts are done → status
board updates itself; **expo / packing** screen checks all parts before the number is called; modifiers and
notes clear, allergens bold; **priority** (dine-in, takeaway, rush, VIP); bump, recall, **hold and fire**;
adjustable sound; "total to cook now" counts; **cancel / edit alerts** (ticket flashes); works offline on the
local network; **waste / remake reasons**; data for AI: prep time per item/station/hour, **congestion score =
open tickets × average prep time ÷ cooks**, late rate. Optional physical bump bar; kitchen printer backup.

**Built:** ✅ queue, stations, timer colours, start/done, auto Ready, bump, recall, allergens and notes, counts,
sound, sold-out from the KDS, prep timestamps, printer backup setting. 🟡 expo (a KDS without a station sees
all). ❌ priority, hold and fire, flashing edit/cancel alerts, remake reasons, congestion score, bump-bar keys,
hotel room number and delivery time on tickets.

### 12. Order status board (R-STATUS)
**Documents:** 43–55 inch wall screen, "Preparing" and "Ready for pickup", updates by itself from the KDS.

**Built:** ✅ trilingual board, live updates, chime and flash when a number is ready.

### 13. Overhead menu board (R-BOARD)
**Documents:** 55-inch commercial displays above the counter, like global fast-food chains; categories change
by time and by **central AI directives**; optional advertising of supplier brands.

**Built:** ❌ **Change:** new device type `board`, a board screen showing categories and prices by daypart and
stock, driven by the AI policy in AI mode.

---

## C. Management

### 14. Owner dashboard and reports
**Documents:** Manual / AI switch, menu and price edits, staff roles, device health, live sales; reports by hour
and item, prep time, late orders, payment mix, voids and refunds, accounting export; AI business alerts; KPIs:
order time, kiosk completion rate, help-button rate, prep time, late %, remake %, average bill, upsell
acceptance, orders per peak hour; hotel request times and SLA %.

**Built:** ✅ live sales, channels, payments, top items, tax, statuses, screens online, CSV export, audit log.
❌ mode switch, menu editor, late-order and void reports, kiosk funnel and upsell KPIs, alerts, mobile owner app.

### 15. Staff roles and PIN
**Documents:** cashier, waiter, kitchen, manager, owner; every change logged with a name.
**Built:** ✅ roles, PIN login with lockout, staff management in the Setup console, audit log.

### 16. Edge server, offline and device manager
**Documents:** a local **edge server in every package** keeps ordering and kitchen screens running when the
internet drops, and syncs later; LankaQR shows "temporarily unavailable, please pay at counter"; card terminal
offline mode; UPS on edge server, router and KDS; cellular backup router. Device manager: locked kiosk mode,
remote restart, remote update, **alert when a screen goes offline**, tamper alerts, remote lock.

**Built:** ✅ edge mode with outbox sync and config pull, LankaQR unavailable message, screens remember their
setup and reconnect by themselves, keep-awake, online/last-seen per screen. ❌ remote restart/lock/update,
offline alerts, tamper alerts, MDM. **Decision needed:** the documents put an edge server in every package;
you later asked for cloud-only. Recommended: cloud-first, edge server as the included offline guarantee for
packages that promise it.

---

## D. Intelligence and guest profile

### 17. AI engine (R-AI)
**Documents:** upsell agent (RAG over menu + order history), congestion agent (rules + forecast), dynamic menu
pacing (high-margin pairings, kitchen load), weather/time cross-selling, perishable-stock pricing within caps,
dynamic overhead boards, owner insights ("fries sell 40% more when it rains"), a guardrail layer checking every
output before it reaches a screen.
**Built:** ❌ (the KDS timestamps it needs are already recorded).

### 18. Voice and languages (R-VOICE)
**Documents:** tap-to-talk, never always listening; Sinhala, Tamil, English plus international languages;
spoken requests translated into the property's admin language; touch stays primary, voice is a bonus; in rooms
the mic works only when tapped, with a visible mute switch.
**Built:** ✅ 3-language UI. ❌ voice, tourist languages.

### 19. Loyalty and guest profile (R-LOYAL, H-LOYAL)
**Documents:** phone number or physical token; tiers, points, automatic tier discounts; remembered preferences;
consent required; identity data never used for AI training.
**Built:** ❌

### 20. Inventory (R-INV)
**Documents:** stock tracking, automatic out-of-stock, inventory forecasting (AI).
**Built:** ❌ (manual sold-out switch only).

---

## E. Hotel (custom only)

### 21. Room kiosk (H-CORE)
8-inch bedside/desk screen, wired power, locked kiosk mode, guest language, hotel info (H-INFO), privacy
(mic only when tapped, mute switch, no recording by default). **Built:** ❌

### 22. Request router and staff app (H-HK, H-MAINT, H-CONC, H-SPA, H-AI)
Guest asks by touch or voice → AI classifies (food, housekeeping, maintenance, spa, concierge) → finds the staff
member by **floor quadrant, shift and workload** → task on their phone → accepted → in progress → done → guest
sees status. Each request type has a target time (e.g. towels 10 min); missed → escalate to supervisor; nobody
accepts → reassign or alert reception; **emergency button alerts security and reception without AI**; low
feedback ratings alert the duty manager (H-FEED). **Built:** ❌

### 23. In-room dining and hotel KDS (H-DINE, H-KDS)
Order now or scheduled → bill with SC and taxes → "charge to room" (optional PIN) → KDS ticket with room,
floor and target delivery time → runner app: pickup → delivering → delivered → guest rates. **Built:** ❌
(the order engine and KDS are reusable; add channel `room`, `due_at`, runner status).

### 24. Room tab and folio (H-FOLIO)
Guests authenticate with a **dynamic room PIN** and add restaurant bills or spa bookings to the room tab;
charges post instantly to the property folio; the guest sees the running total. **Built:** ❌

### 25. PMS / POS integration (H-PMS, H-BRIDGE, R-BRIDGE, R-POS)
Either connect to the existing PMS/POS (Opera, IDS Next, Micros) by tokenised API to sync rooms, guest
profiles, room-charge posting, menus and inventory, or use our own native POS and PMS suite. Start with one or
two systems, charge an integration fee. **Built:** 🟡 our own POS core exists; ❌ PMS and bridges.

---

## F. Compliance and delivery

### 26. Compliance
PDPA No. 9 of 2022 (minimum data, consent for loyalty and voice, tokenised anonymous AI data, delete on request,
data protection contact); IRD RAMIS exports; CBSL / LankaPay approved gateways, no raw card data; CAA price
transparency (the cart price is the price paid); food safety (venue enters allergens); hotel guest privacy.
**Built:** ✅ no card data by design, minimal personal data, clear SC/VAT lines, cart price = paid price.
❌ RAMIS export, consent and deletion flows (needed with loyalty and voice).

### 27. Turnkey delivery and support
Free site survey (power, Wi-Fi, layout, mounting) → quote (package, tier, hardware sale or lease, monthly plan) →
install (screens, printers, network, UPS, menu setup and photos, payment and printer tests) → training → go-live
support on site → remote monitoring, spare swap (about 10% spares), Standard or Premium (24/7, 24 h swap) support;
KDS or cashier down is top priority. **Built:** ✅ platform console, one-time screen setup, test wall, browser
tests. ❌ installer checklist, support dashboard, hardware register.

---

## Build order (follows the Full Plan roadmap)

| Phase | Systems | Result |
|---|---|---|
| 1. Core + KDS + Cashier MVP | 1 (modules, limits), 3 (menu editor, photos, combos), 4 (priority), 5 (SSCL, RAMIS export), 6 (real LankaQR, reconciliation, barcode slip, table lock, tap-card buttons), 9, 11 (expo, priority, hold/fire, edit alerts), 12, 14 (reports), 16 (edge server decision, offline alerts) | Pack 2 without tables can run |
| 2. Pack 2 pilot | 7 (call waiter, request bill, waiter assist, split bill, open bill), 10 (waiter screen and serve alerts) | Pilot in 1–2 restaurants, measure KPIs |
| 3. Pack 1 and 3 | 8 (upsell, help button, accessibility, attract), 13 (overhead board), 18 (voice on kiosk), custom builder + quote | Self-serve and Hybrid sites |
| 4. Hotel pilot | 21–25 | One boutique hotel, one PMS bridge |
| 5. AI and scale | 2 (mode switch, ladder), 17, 19, 20, multi-branch central menu, MDM | AI Autonomous mode with guardrails |
