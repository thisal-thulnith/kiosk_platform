# Build plan: cloud-first, multi-tenant AI Hospitality Kiosk Platform

This plan takes the system from what exists today to the full product described in the BRD, the
Product Details and the Full Plan (Pack 1, 2, 3, Custom, Hotel, AI mode). It is ordered so that each
phase ends with something you can install in a real restaurant.

## 0. Where we are today

| Area | Status |
|---|---|
| Order engine, order and payment status, release rules A/B, unpaid expiry | Built and tested |
| Tax engine (editable rules, effective dates, compounding, SSCL-ready) | Built |
| Payments: cash, card (manual approval code), LankaQR (mock gateway), late-QR auto refund | Built, gateway is a mock |
| Gapless invoice numbers, cash shifts with variance, receipts (ESC/POS) | Built |
| KDS API (stations, start/done, bump, recall, to-cook counts), status board API | Built |
| Real-time WebSocket hub with replay after reconnect | Built (in-process, one server) |
| Device pairing (6-digit code), staff PIN login with lockout, audit log, idempotency | Built |
| Edge ↔ cloud sync (outbox up, config down) | Built, becomes optional |
| **Test screens** in `src/kiosk/web/`: Setup console, cashier, KDS, status board, table, kiosk, owner dashboard, test wall | **New: working HTML for testing** |
| Platform console + API: create restaurants (tenant, first branch, owner login, sample menu), list all | **Built** |
| Tenant isolation (restaurants never see each other's venues, screens, staff, menu, orders, reports) | **Built and tested** |
| Owners add branches and staff PINs; screens set up once with the owner/manager password | **Built** |
| Unattended screens: remembered setup, auto-reconnect after outages, keep-awake, password-locked settings | **Built** (test screens) |
| Packs/modules, device slots from tiers, QR pairing, users + memberships per branch, invitations | To build |

## 1. Target architecture (cloud-first)

```
 CLOUD (AWS Mumbai or Singapore; ~30-60 ms from Colombo)
 ┌──────────────────────────────────────────────────────────────────────────────┐
 │  API servers (2+, same FastAPI app)  ──  Redis (live events + replay)         │
 │  PostgreSQL (shared schema, tenant_id, row-level security)  ·  S3 (images)     │
 │  Platform console · Admin portal · Owner app · LankaQR callback · Print queue  │
 └───────────▲─────────────────────▲────────────────────────────▲────────────────┘
             │ HTTPS + WebSocket   │                            │ HTTPS (CloudPRNT)
 ┌── VENUE ──┴─────────────────────┴────────────────────────────┴───────────────┐
 │ Router: fibre + 4G failover, on UPS · separate Wi-Fi for screens               │
 │ Cashier · KDS · Status board · Table screens · Kiosk · Overhead board · Printers│
 │ (optional mini-PC "offline guarantee" for remote resorts / food courts)        │
 └────────────────────────────────────────────────────────────────────────────────┘
```

Rules that do not change: money is integer LKR cents, prices come from the server, tax rules are data,
the gateway callback decides if a QR payment succeeded, invoice numbers have no gaps, retried writes
carry an `Idempotency-Key`.

## 2. How everything connects

### 2.1 Setting up a restaurant (you, once per client)

1. **Platform console → New restaurant.** Pick Pack 1/2/3 and a tier, or Custom modules. This creates
   the tenant, venue, enabled modules, stations, tables (T1…Tn) and **device slots** (e.g. Pack 2
   Standard: 1 cashier, 2 KDS, 1 status board, 12 tables, 1 waiter handheld).
2. **Owner invite** by SMS/WhatsApp. The owner sets a password. One login works for the admin portal
   and the owner app.
3. **Menu**: your team enters it, or imports Excel / a photo of the paper menu (AI reads it).
4. **Staging at your office**: every screen is put in kiosk mode and paired to its slot by scanning a QR.
5. **On site**: plug in, the screens connect to the cloud, calibrate, run the test order, go live.

### 2.2 Pairing a screen

- Today (built): Setup console creates a device → 6-digit code → type it on the screen
  (`/`) → the screen gets a device token and keeps it.
- Target: the screen shows a QR → the installer scans it with the admin app → picks the slot → done.
  "Replace" moves a slot to a new tablet with the same profile and calibration.

### 2.3 One order, end to end (what the test screens already do)

```
Table / Kiosk / Cashier ──POST /v1/orders──▶ server prices it from the DB, token T001
        │                                         │ (rule A: waits for payment)
        ├─ LankaQR on screen ──gateway callback──▶│ paid → released to kitchen
        └─ "Pay at cashier" → cashier takes cash ▶│
                                                  ├──ws──▶ KDS: ticket for its station
                                                  ├──ws──▶ Status board: T001 Preparing
  KDS bump ─────────────────────────────────────▶ │ READY
                                                  ├──ws──▶ Status board: T001 Ready (+chime)
                                                  ├──ws──▶ Table screen: "Your order is ready"
  Cashier "Hand over" ──────────────────────────▶ │ COMPLETED → owner dashboard sales
```

Every change goes through one function (`services/orders.changed`) that writes the event log, bumps
the version, writes the outbox and sends the live event after commit.

## 3. Changes, by area

### 3.1 Cloud-first backend

| Change | Files | Notes |
|---|---|---|
| Run background jobs (expire unpaid orders) in the cloud for all venues, with a lock so only one server runs them | `main.py`, `jobs.py` | Today they run only in edge mode |
| Move the live-event hub to **Redis Streams** (one stream per venue) | `realtime/hub.py` | Keeps seq/epoch replay; works across servers |
| Print queue with **CloudPRNT/Epson SDP** printers, plus cashier-device print bridge | `infra/printing.py`, new `print_jobs` table | ESC/POS rendering stays the same |
| `lankaqr_available()` checks gateway health, not edge sync | `sync/state.py` | |
| **Real LankaQR gateway** adapter behind the existing `Gateway` protocol | `infra/gateway.py` | Start merchant onboarding now (weeks of paperwork) |
| Keep `sync/` for venues that buy the optional mini-PC | `sync/*` | No change needed |
| Postgres in production, Alembic migrations for every schema change | `migrations/` | |

### 3.2 Multi-tenant platform and setup

| Change | New tables / endpoints |
|---|---|
| Platform staff (you) with 2-step login | `platform_users`; `/v1/platform/*` |
| One account for owners/managers across web + app | `users`, `memberships(user, tenant, venue|all, role)`, `invitations`, `refresh_tokens`, `otp_codes` |
| Modules = the R-codes from the Product Details (R-CORE, R-KDS, R-TABLE…) | `modules`, `plans` (pack + tier presets), `subscriptions`, `tenant_addons`; `require_feature()` dependency |
| Device slots from the chosen tier | `devices` gains `slot`, `profile_id`, `table_id`, `station_code`, `printer_id`, `display` (calibration), `app_version` |
| Venue setup records | `stations`, `dining_areas`, `tables`, `printers`, `device_profiles` |
| QR pairing, device-initiated | `device_claims`; `POST /devices/claim-request`, `POST /admin/devices/claim`, `GET /devices/claim-status` |
| Tenant isolation | Scoped dependency on every route + Postgres RLS + a test that every admin route rejects another tenant's ids |
| Hardware register and support dashboard | `hardware_assets`, `device_health`, `support_sessions` |

The test screens already use `GET /v1/admin/venues` (added now) to pick a venue.

### 3.3 Menu and staff

| Change | Tables |
|---|---|
| Master menu per restaurant group with branch overrides (price, visible, sold out, sort, channel price) | `menu_overrides`, `menu_item_venues` |
| Cashier "quick edit" (press and hold an item → price / sold out) with permission check | uses `menu_overrides` |
| Scheduled prices, price history, bulk price change | `scheduled_prices`, `price_history` |
| Editable roles made of permissions (`menu.edit_price`, `order.void`, …); manager PIN override | `roles`, `staff.role_id` |
| Combos and upsell rules (kiosk + table) | `combos`, `combo_slots`, `upsell_rules` |
| Menu import: CSV and AI photo reader | `/v1/admin/venues/{id}/menu/import` |

### 3.4 Ordering features from the requirement documents

| Feature | Screen | Backend |
|---|---|---|
| Open tab for dine-in (rounds, pay at the end), split bill | Table, cashier | `tabs` or order groups; payments per share |
| Call waiter / request bill | Table | `service_requests` + live event to cashier/waiter |
| Waiter assist mode (hidden staff button + PIN on the table screen) | Table | existing staff PIN login on the table device |
| Barcode on the pay-at-cashier screen and kiosk slip; scanner on the cashier | Table, kiosk, cashier | `/orders/lookup` already accepts the order id |
| KDS: priority, hold and fire, expo/packing screen, remake reasons, edit alerts | KDS | fields on `order_items`, new events |
| Overhead menu board (new device type `board`) | Board | menu + promotions feed |
| Help button on kiosk | Kiosk | `service_requests` |
| Cashier offline safe mode (cash only, provisional receipt, print over LAN, upload later) | Cashier | idempotency already handles re-sends; invoice numbering rule to confirm with a tax adviser |

### 3.5 Owner app, hotel, AI

- **Owner app**: live sales across branches, alerts (big refund, cash short, KDS offline, late
  orders), approvals, sold-out switch. `/v1/owner/*` endpoints on top of `memberships`.
- **Hotel** (after the restaurant pilot): rooms, room kiosk, service request and task engine with
  target times and escalation, staff mobile app, folio posting, one PMS bridge, emergency button that
  never depends on AI.
- **AI mode** ladder from the Full Plan: L1 suggestions to staff → L2 upsell to guests → L3 promote
  fast items when the kitchen is busy (congestion score from KDS timestamps, already recorded) → L4
  prices within owner limits. Every level: guardrail check, audit log, one-tap kill switch. Voice is an
  extra, touch stays primary.

## 4. Frontend

| Now (test) | Production |
|---|---|
| Plain HTML + JS modules in `src/kiosk/web/`, served at `/screens` | **One React + TypeScript "device shell"** that renders the right screen for the device type after pairing |
| Tokens in browser storage | Same, inside a locked kiosk shell (Fully Kiosk Browser for the pilot, own Capacitor wrapper later for card terminal SDK and printing) |
| Setup console + owner page for admins | Admin portal (web) and owner app (PWA first, React Native later) |

The test screens are the reference for the production screens: same API calls, same flows.

## 5. Phases

| Phase | Weeks | Deliverable | Done when |
|---|---|---|---|
| 1. Cloud core + platform | 1–5 | Redis hub, cloud jobs, platform console API, users/memberships, modules/packs, device slots, stations/tables/printers, QR pairing | A Pack 2 Starter restaurant is created in 5 minutes and 10 screens pair in 10 minutes |
| 2. Core screens | 6–13 | Production cashier, KDS, status board; real LankaQR; print queue; master menu + quick edit; permissions | A full takeaway day runs with real QR payments |
| 3. Pack 2 dine-in + pilot | 14–22 | Table screen, waiter assist, open tab, split bill, call waiter, owner app v1, cashier offline mode | Two pilot restaurants run for 4 weeks; measure prep time, errors, average bill |
| 4. Pack 1 & 3 + operations | 23–32 | Self-order kiosk, combos/upsell, overhead board, package builder + quote, MDM, support dashboard | First Pack 1 site live; support team sees every client's device health |
| 5. Hotel pilot | 33–44 | Room kiosk, request routing, staff app, folio, one PMS bridge | One boutique hotel live |
| 6. AI mode | 45+ | Ladder L1→L4 with guardrails, voice, hotel request router | Owners can turn each level on and off |

## 6. Testing

- **Unit + API tests**: `uv run pytest` (domain, full flows, WebSocket, two-database sync).
- **Browser test of all screens**: `tools/screens/e2e_react.py` clicks through the whole flow in headless
  Chrome and saves screenshots. See the README for how to run it.
- **Manual 3-screen test**: see "Test the screens in a browser" in the README.
- Before the pilot: 2 weeks of 4G/fibre outage logging at the pilot site, a load test with the
  simulator (`tools/simulator/run.py`) at 3× the venue's peak.

## 7. Decisions still needed

1. Dine-in payment default: pay first (rule A), open tab, or per venue.
2. Payment gateway partner for LankaQR (start the merchant agreement now).
3. Offline invoice numbering rule (provisional receipt vs. number range), with a tax adviser.
4. Hardware: sell, lease, or both.
5. Pilot restaurant and its layout.
