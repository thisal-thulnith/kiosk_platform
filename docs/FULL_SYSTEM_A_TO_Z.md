# The full system, A to Z

Written for: our whole team (sales, installers, support, developers), to understand how everything fits
together. Details live in [NEW_RESTAURANT_A_TO_Z.md](NEW_RESTAURANT_A_TO_Z.md) (step-by-step install),
[KIOSK_AND_DEVICES.md](KIOSK_AND_DEVICES.md) (kiosk and hardware), [APK_PLAN.md](APK_PLAN.md) (tablet
app) and [DEVICE_APP.md](DEVICE_APP.md) (screen API).

---

## 1. The big picture

```
                         ┌──────────────────── CLOUD ────────────────────┐
  Our team ─────────────►│ Platform console (admin panel): restaurants,  │
  (platform login)       │   packages, flows, equipment, prices          │
                         │ Setup console (per restaurant): screens,      │
                         │   hardware, printers, payments, POS, hub      │
  Restaurant owner ─────►│ Owner dashboard + Menu editor                 │
  (restaurant login)     │ Bank / card processor callbacks, SMS gateway  │
                         └──────────────▲───────────────────▲────────────┘
                                        │ sync (Hybrid)     │ internet (Cloud)
                  ┌─────────────────────┴──────┐            │
                  │ HUB (Hybrid only): small   │            │
                  │ box next to the router     │            │
                  └──────────▲─────────────────┘            │
      restaurant Wi-Fi       │                              │
  ┌─────────┬─────────┬──────┴──┬─────────┬─────────┬──────┴───┬──────────┐
  │ Tables  │ Kiosks  │ Cashier │ Kitchen │ Status  │ Menu     │ Waiter   │
  │ (8")    │ (all-in-│ POS     │ (KDS)   │ board   │ board    │ handheld │
  │         │  one)   │         │         │ (TV)    │ (55")    │          │
  └─────────┴─────────┴─────────┴─────────┴─────────┴──────────┴──────────┘
     printers (cloud or USB) · card readers · cash drawers · scanners
     the restaurant's own POS (optional, connected by the POS bridge)
```

- **One software**, three places:
  - the **cloud** (all restaurants);
  - the **hub** (one per Hybrid restaurant);
  - the **screens** (one app; the setup code decides what each screen is).
- **Multi-tenant**: each restaurant sees only its own data. Branches share an owner, loyalty members and
  reports.
- **Who uses what:**
  - our team: the Platform console and Setup console;
  - the restaurant: the Owner dashboard, the Menu editor, and the screens (staff use PINs).

## 2. How one order travels

1. A guest orders on a **table screen** or **kiosk** (or staff on the **cashier POS** or **waiter
   handheld**).
2. The **server prices it** from the menu (never trusts the screen). It applies member discounts, AI
   deals, then service charge, VAT and SSCL, and gives the order a number (K007).
3. **Payment**:
   - LankaQR or card: the bank's **signed callback** is the only proof.
   - Cash at the cashier.
   - Or the restaurant's own POS says "paid" through the POS bridge.
   - Tables can also run an **open tab** and pay at the end.
4. **Kitchen**:
   - The order is released to the **KDS**: tickets by station, rush and VIP first, with a promised
     time.
   - Held items wait for "fire".
   - Stock portions come off; at zero the item is **sold out on every screen**.
   - Optional kitchen ticket printer.
5. **Ready**:
   - The **status board** shows the number, and the **cashier** sees "ready to hand over".
   - The **waiter** gets it to serve.
   - The guest gets the **SMS** if they left a number.
6. **Receipt** prints **where the guest paid** (the kiosk's own printer, or the till's). There is an
   invoice number, points earned, and a receipt link by SMS.
7. The **owner** sees it live: sales, taxes, late orders, remakes and voids, the tax ledger for IRD,
   and bank reconciliation.

## 3. Choosing how a restaurant works: flows with required parts

In the Platform console, when creating the restaurant, tick **how it works**. Each flow brings its
screens, modules, equipment and settings. Anything it depends on is **added and locked (🔒)**:

| Flow | Brings | Also requires (added automatically) |
|---|---|---|
| Self-order kiosks | Kiosk, KDS, status board; kitchen starts after payment; guests pick up | A kiosk printer per kiosk, router |
| Order at the table | Table screens, KDS | A cashier to pay at, **unless** the restaurant keeps its own POS |
| Open tab | Tables pay at the end | Order at the table |
| Counter POS (ours) | Cashier, KDS | A receipt printer, cash drawer and scanner per cashier |
| Waiter service | Waiter handheld; waiters serve | Order at the table (and so a cashier) |
| Keep their current POS | POS bridge (R-BRIDGE) | Replaces our cashier for tables |
| Order-ready display | Status board | — |
| Menu board | 55" board | — |
| Kitchen ticket printer | Kitchen printer, prints every ticket | — |
| Works without internet | Hub, network mode Hybrid | A UPS |
| Texts to guests | SMS ready + receipt | — |

Packs 1–3 accept only flows their tier can add. Anything else means **Pack 4 Custom**. The rules live
in `kiosk.domain.modules` (`FLOWS`, `NEEDS`) and are tested.

## 4. Setting up a new restaurant (summary; full steps in NEW_RESTAURANT_A_TO_Z.md)

1. **Survey**: tables, counters, stations, internet, power, existing POS.
2. **Platform console**: create the restaurant with package, **flows**, equipment and owner login. The
   screen slots are created (Table T1…, Kiosk 1, Kitchen 1…).
3. **Setup console (office)**:
   - business details, menu (with PLU codes if they have a POS), taxes, staff PINs;
   - payments: methods, LankaQR merchant, test connection;
   - Hybrid: hub setup code, then `kiosk hub-setup`;
   - POS bridge (if they keep their POS).
4. **Tablets**: the MDM installs and locks the APK.
5. **Installation day**, in this order: network, then screens (code or QR per slot), then **Hardware**
   per screen (all-in-one kiosk, POS terminal…), card readers (test), printers (test page), equipment
   ticks, a test order through every path, the Hybrid internet-off test, and the go-live checklist
   all green.
6. **Training**, then **go live**. From then on, power on means every screen opens by itself.

## 5. Connecting the hardware

### All-in-one kiosk (built-in printer, card reader, QR scanner)
1. Mount it, connect power (on the UPS line if possible) and the screen Wi-Fi or LAN.
2. Open the app, then scan the QR code from its **Kiosk** slot. It opens as that kiosk.
3. Setup console → **Hardware** on the kiosk → **All-in-one kiosk** → type the reader's serial → Save.
   This sets up:
   - its **built-in printer** (receipts + order-number slips, only for this kiosk);
   - the **card reader**;
   - the scanner.
4. Finish the "Still to do" list:
   - on the kiosk, tap **Connect printer**, then **Print test page**;
   - **Test reader**.

### Cashier POS terminal (built-in printer, drawer port, scanner, customer display)
Same steps: Hardware → **POS terminal**. The built-in printer gets the cash drawer. Card: a reader
serial, or SoftPOS (tap on the tablet) under **Card**.

### Other hardware

| Hardware | Connection |
|---|---|
| Separate receipt or kitchen printer | **Cloud printer** (Star CloudPRNT: paste the URL shown into the printer's settings page) or **USB into a screen** (tap Connect printer). Receipts print where the guest paid; kitchen printers can take only some stations. |
| Card terminal not integrated | The cashier types the approval code. |
| Router and UPS | Tick them in **Equipment**. Use a separate screen Wi-Fi. The UPS powers the router, hub and cashier. |
| Hub (Hybrid) | Network → Hub setup code → `kiosk hub-setup`. It shows **Online**, and cloud printers then point at the hub. |

## 6. Connecting the restaurant's current POS (POS bridge)

For a restaurant that wants to **keep its till and accounts**:

1. Package: tick **Keep the restaurant's current POS** (module R-BRIDGE). Table guests then pay at
   their POS, so our cashier screen isn't required.
2. Setup console → **Restaurant's own POS**:
   - **POS name and order address**: their URL that receives orders.
   - **Secret**: we sign every event with it.
   - **Events to send**: created, round added, paid, cancelled, voided, and optionally released,
     ready, completed.
   - **Send test**: shows what their POS answered.
   - **Create API key**: give it to the POS company once. Their POS calls our API with
     `X-Pos-Key`.
   - **Import their menu**: a CSV export with `plu, name, price, category`. It can also be pushed by
     their POS at any time.
3. **How it works live:**

```
Our kiosk / table  ──order.created──►  their POS (signed JSON with PLU codes, token, table, totals)
                                        their cashier rings it up and takes the money
their POS  ──POST /v1/pos/orders/{id}/paid {reference, method}──►  us
                                        kitchen starts · receipt prints · points · SMS
their POS  ──PUT /v1/pos/menu──►  us    prices, names and availability follow their POS (by PLU)
their POS  ──GET /v1/pos/orders?since=…─►  us   (catch up after any downtime)
```

4. **Safety:**
   - Each event carries `X-Kiosk-Signature` (HMAC-SHA256 of the body) and `X-Kiosk-Delivery` (so
     their POS ignores repeats).
   - Events are retried with backoff until their POS answers 2xx.
   - The same POS receipt sent twice is recorded once.
5. **If they would rather use ours**: tick **Counter POS (ours)**. That's our cashier screen, and the
   full native POS (R-POS) is the add-on. R-BRIDGE and R-POS can't both be chosen.

## 7. Online and offline

| Restaurant | Internet down | Hub down |
|---|---|---|
| Cloud | Screens say "Offline — retrying"; no new orders until it's back | — |
| Hybrid | **Everything keeps working** through the hub; LankaQR off; cash and SIM card terminals work; everything syncs when it's back, exactly once | Screens switch to the cloud by themselves (numbers from 500); the hub catches up and takes over again |

There is **one writer at a time**, so there's never a conflict. The hybrid test runs a real cloud and
a real hub (`tools/screens/e2e_hybrid.py`).

## 8. Security, in one list

- **Screens:** a device key per tablet (never expires; revoked by Re-pair or Disable).
- **Staff:** PINs with lockout. **Owner:** email and password. **Our team:** platform login. Wrong
  codes and passwords are rate-limited.
- **Setup:** only our team can set up screens, printers, payments, POS and the hub.
- **Payments:** only bank-signed callbacks count, and card numbers never reach us. Merchant keys are
  stored encrypted (`DATA_KEY`).
- **Sync and integrations:**
  - hub ↔ cloud uses a sync key;
  - the POS uses a key plus signed events;
  - printers use a secret URL;
  - SMS receipt links are signed.
- **Guest privacy:** each guest's phone number is used for that order only and never shown on screens.
  Loyalty needs consent, with export and forget. The kiosk resets so nothing of the last guest stays.

## 9. What is still simulated, and what's next

| Now | Next |
|---|---|
| Mock LankaQR gateway, mock card processor, mock SMS | Bank and gateway adapters (same interfaces), a Sri Lankan SMS gateway |
| Screens in the browser (HTML) | The Android APK wrapping them ([APK_PLAN.md](APK_PLAN.md)) |
| POS bridge tested against a simulated POS | A pilot with a real POS vendor's API |
| — | Voice ordering, hotel systems, support tools |
