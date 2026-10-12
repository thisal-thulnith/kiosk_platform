# AI Hospitality Kiosk Platform: backend

FastAPI backend for the restaurant kiosk system: order engine, kitchen display (KDS), status
board, payments (cash, card, QR payment), cash shifts, receipts, reports, and edge ↔ cloud sync.

The same app runs in two modes:

| Mode | Where | Does |
|---|---|---|
| `edge` | Mini-PC in each venue | Takes orders, drives the KDS and status board, prints. Keeps working with no internet. |
| `cloud` | Central server | Admin, reports across venues, receives orders from edges, sends menu/tax/staff config down. |

## Quick start (no Docker)

```bash
uv sync
cp .env.example .env
uv run kiosk initdb      # creates tables (dev); production uses: uv run alembic upgrade head
uv run kiosk seed        # demo café, prints the venue id and logins
uv run kiosk serve --reload
```

Open http://localhost:8000/docs for the interactive API.

Demo logins: admin `admin@demo.lk` / `admin12345`. Staff PINs: Nimal (cashier) `1111`,
Ravi (kitchen) `2222`, Priya (waiter) `3333`, Kamala (manager) `9999`.

## Test the screens in a browser

Every screen and console has a clean address. Each restaurant has its own path (its code, e.g. `demo`):

Everything is React (built from `frontend/`) except the table screen, which is the Android app.
A table's visit runs like a real restaurant: cooking → food ready (a waiter takes it, Served) →
eating → guest feedback → paid → needs cleaning (Cleaned) → free.

| Page | Who | What |
|---|---|---|
| `/` | Every tablet | **Launcher** (the app's start page): set up once with the installer's QR or 6-digit code; after that every start opens that screen by itself |
| `/platform` | Our team | **Platform console**: create restaurants with a package, how they work, equipment, prices and quotes |
| `/demo/setup` | Our installers | **Setup console** (opened per restaurant from the Platform console): 7 guided steps; screens show which physical tablet they are on, with Identify and Reload |
| `/demo/owner` | Restaurant owner | **Owner app** (phone or laptop): sales, every person's work (orders taken, payments collected, tables visited, answer time), every table, every payment, guests' ratings and comments (also per waiter), kitchen, stock, AI, accounting |
| `/demo/menu` | Owner / installer | **Menu editor**: items in 3 languages, photos, add-ons, meals, time windows, taxes |
| `/demo/pos` | Cashier | **POS**: floor map, calls ("Coming" → pick the waiter), takeaway and table orders, cash / card / QR payment / split, open checks, bill, shift, today's payments |
| `/demo/waiter` | Waiter | **Waiter app** (phone): one task list, most urgent first: take food to a table (Served), calls, bills, tables to clean (Cleaned), guest feedback (Seen); tables, order for a table, take payment at the table, my payments |
| `/demo/kitchen` | Kitchen | **Kitchen display**: tickets by station, timers, tap to start / done, bump, fire held, recall, remake, sold out, bump-bar keys |
| `/demo/kiosk` | Guests | **Self-order kiosk** — *coming soon* (switch on with `COMING_SOON=`): 3 languages, photos, meals and add-ons, QR payment / card reader / pay at counter, tracking, "text me", one-tap "How was it?" rating, privacy reset |
| `/demo/board` | Guests | **Order status board** — *coming soon*: Preparing / Ready |
| Table screen | Guests | The Android table app, built to [docs/TABLE_APP_API.md](docs/TABLE_APP_API.md). A browser set up as a table shows how to install the app |
| `/demo/wall` | Testing | Several set-up screens side by side in one window |

Old addresses (`/screens/app.html`, `cashier.html`, `index.html`, …, from installed apps, printed QR
codes or bookmarks) redirect to the React screens. Each restaurant's colour, logo and light / dark
screens are set in the Setup console (Restaurant → Look & logo) or the Owner app, and every screen
and console uses them.

Fastest test (one computer): open the Setup console, log in (demo login is filled in), press
**Create 4 test screens and open wall**. Order on the kiosk pane and pay at the counter; take the cash
on the POS pane (Nimal, PIN 1111); the ticket appears on the kitchen pane and the number on the status
board; bump it on the kitchen: the board shows it Ready.

### A new restaurant, screens set up once

1. Open `/platform` and log in (dev login `platform@kiosk.lk` / `platform12345`, created
   by `kiosk seed`; real ones: `uv run kiosk create-platform-admin --email you@company.lk --password ...`).
2. Fill in **New restaurant** (company, first branch, code, owner email and password, package, how it
   works, equipment). Give the owner the email and password shown.
3. **Open setup console** for it. In **Screens**, add each screen. Each one has its own **screen
   code** (e.g. `K7MQ-4XPA-2R`, like a Square device code): on the tablet open the restaurant's
   address (`/demo`) and type the code, or scan the QR. It stays signed in for good; signing in on
   another tablet signs the old one out; **Reset code** signs it out. The table screen is the
   Android app, which signs in the same way ([docs/MOBILE_APP_API.md](docs/MOBILE_APP_API.md)).
4. That's it for good: the screen reopens by itself after restarts and power cuts. If the server is
   down it shows "Reconnecting…" and carries on by itself. Other devices use this computer's network
   address (`ipconfig getifaddr en0` on a Mac), e.g. `http://192.168.1.20:8000`, on the same Wi-Fi;
   add `?slot=2` to a screen address to run a second screen of the same type in one browser.

Each restaurant only sees its own branches, screens, staff, menu, orders and reports.

## Docker

```bash
docker compose -f docker/edge.compose.yml up -d    # in a venue
docker compose -f docker/cloud.compose.yml up -d   # central server
```

## How a device talks to the backend

1. Admin registers a device: `POST /v1/admin/venues/{id}/devices`. It returns a 6-digit code.
2. The device pairs: `POST /v1/devices/pair {"code"}` returns a device token. Send it as
   `X-Device-Token` on every request.
3. Staff log in on the device with a PIN: `POST /v1/staff/pin-login`. Send the result as
   `Authorization: Bearer <staff_token>` as well.
4. The device opens `ws://…/v1/ws?token=<device token>` for live events. After a reconnect,
   pass `since=<last seq>&epoch=<epoch>` to get missed events. On `{"type": "resync"}`,
   reload from REST.

## Rules built in

- **Money** is integer LKR cents everywhere.
- **Order status and payment status are separate.** Release rule A (default): the kitchen gets
  the order only after payment. Rule B: the kitchen starts at once and the order can't be handed
  over until paid. Unpaid rule-A orders expire (default 10 minutes).
- **Prices come from the database**, never from the device.
- **Tax rules are data** with effective dates and a compounding order. They are not hard-coded.
- **The payment gateway's signed callback is the source of truth.** A QR payment that arrives
  for a cancelled or expired order is accepted and refunded automatically.
- **Invoice numbers are an unbroken sequence** per venue, issued in the payment transaction.
- **Every write that devices retry takes an `Idempotency-Key` header** (order create, cash and
  card payments).
- **Voids and refunds need a manager PIN** and a reason, and go to the audit log.
- **Sync ownership:** the cloud owns menu, tax, staff and settings. The edge owns orders,
  payments, shifts and the sold-out switch. Edge → cloud uses a transactional outbox and is safe
  to resend. The cloud keeps the highest order version it has seen.

## Layout

```
src/kiosk/
  domain/     pure logic: tax engine, order state machine, menu time windows
  services/   order engine, payments, shifts, printing (flush, never commit)
  api/        routers + auth dependencies (routers commit)
  realtime/   in-process WebSocket hub with replay buffer
  sync/       outbox push, config pull, cloud ingest
  infra/      models, database, ESC/POS printers, gateway adapter
  web/ui/     the built React screens and consoles (output of frontend/, served at /static, pages at /{code}/{screen})
frontend/     React + TypeScript + Tailwind source of the POS, waiter, kitchen, kiosk and status board
migrations/   Alembic
tests/        domain, full flows, WebSocket, two-database sync
tools/        simulator, browser test of the screens
docs/         build plan, architecture diagram
```

## The React screens (frontend/)

```bash
cd frontend && npm install
npm run dev        # http://localhost:5173/static/pos/  (API and live events proxied to :8000)
npm run build      # type-check, then build into src/kiosk/web/ui (served by the backend)
```

Every screen sets itself up from the installer's link (`?pair=<code>`) or the 6-digit code, keeps its
setup for good (same device keys as before), and connects the way the restaurant runs:
**cloud** (the server it came from) or **Hybrid** (the hub on the local network first, the cloud
when the hub is down, back to the hub by itself). The badge in the corner says *Live*, *Live · Local*
or *Live · Cloud (hub down)*. Docker and CI build the screens; `src/kiosk/web/ui` is kept in the repo
so a hub can run without Node.

**On the local network (Hybrid), in real use:**
- Set tablets up from the hub's address (the Setup console's QR does this). A screen opened from the
  cloud's `https://` address cannot call the hub's `http://` address (browsers block it), so it
  moves itself to the hub's address, carrying its setup, the first time the cloud says the hub is in
  charge.
- The hub finds its own LAN address and reports it to the cloud every minute (`LAN_URL` overrides).
  If the router gives the hub a new address, screens get it from the cloud and move there by themselves.
  Still, reserve the hub's IP in the router (DHCP reservation): it saves a minute of switching.
- A page served by the hub over `http://` is not a "secure context", so the browser can't keep an
  offline copy of it. If the hub restarts, the web screen reconnects by itself, but a full reload
  during the restart fails. The Android app bundles its own screens, which avoids this.
- Each tablet sends its identity (install id, model, system, browser or app version, screen, IP) when
  it is set up and every minute. The Setup console shows it and warns when one tablet is set up as two
  screens.

## Tests

```bash
uv run pytest                                   # SQLite
TEST_POSTGRES_URL=postgresql+asyncpg://kiosk:kiosk@localhost:5432/kiosk uv run pytest tests/test_flows.py
uv run ruff check src tests && uv run mypy src
uv run python tools/screens/e2e_react.py        # every React screen and console in Chrome, end to end
uv run python tools/screens/e2e_hybrid.py       # hub + cloud with two servers; the kiosk switches Local/Cloud
```

## Not built yet

- **Real QR payment gateway adapter (e.g. LankaQR).** Only a mock exists (`infra/gateway.py`). Plug in the bank's
  or gateway's API behind the same interface. For edges, the callback must reach the cloud and
  be relayed to the edge; that relay is not built.
- **Real card terminal adapter.** The card-reader flow runs against a mock terminal; a certified
  terminal's SDK goes behind the same interface. Bank-terminal payments can be recorded with the
  approval code.
- **Sinhala/Tamil on printed slips.** Thermal printers need raster images for these scripts;
  slips print English for now.
- **Multi-instance cloud real-time.** The hub is in-process; the cloud would need Redis pub/sub
  to run several API workers.
- **Rate limiting, backups, device health alerts.**

The demo's Sinhala/Tamil menu text and tax rates (10% service charge, 18% VAT) are placeholders.
Have a native speaker check the text and a Sri Lankan tax adviser confirm the rules.

Step-by-step setup (set up once, runs every day, Android tablets): [docs/SETUP_GUIDE.md](docs/SETUP_GUIDE.md).
How every system works, one by one, from the BRD / Product Details / Full Plan, with what is built: [docs/SYSTEMS.md](docs/SYSTEMS.md). Build plan: [docs/BUILD_PLAN.md](docs/BUILD_PLAN.md).
# kiosk_platform
