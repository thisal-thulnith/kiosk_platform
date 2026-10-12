# Tablet app (APK) plan

Written for: the team that will build and install our Android app on table screens, kiosks, cashier
POS, kitchen displays and boards. The server side it talks to is already built and tested; the exact
API contract is in [DEVICE_APP.md](DEVICE_APP.md).

## 1. What the app is

**One app for every screen.** The setup code decides what a tablet becomes: Table T5, Kiosk 1, Grill
kitchen, Cashier 1, status board or menu board. We never build a separate "table app" and "kitchen
app".

```
┌────────────── Android APK (Kotlin) ───────────────┐
│  Native shell                                     │
│   • first-run setup: scan QR / type server + code │
│   • secure key store (Android Keystore)           │
│   • kiosk lock (Lock Task), start on boot         │
│   • printers: USB, Bluetooth, LAN 9100            │
│   • card reader / SoftPOS SDK from the bank       │
│   • offline shell: the screen files are bundled   │
│  ┌──────────────── WebView ────────────────────┐  │
│  │ our screen pages (table, kiosk, cashier,    │  │
│  │ kds, status, board, waiter): the same code  │  │
│  │ we test in the browser today                │  │
│  └─────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────┘
          │ local network (Hybrid)       │ internet
          ▼                              ▼
   restaurant hub  ◄────── sync ──────►  cloud
```

Why a WebView wrapper rather than rewriting every screen natively:
- The screens are already built and tested, with 5 browser suites and 91 API tests.
- One codebase for web and APK.
- Updates reach every tablet without a Play Store release.

The native side only does what a browser can't do well: locking the tablet, safe key storage,
printers, card SDKs, and starting on boot.

## 2. First run: set up once, for life

1. Our MDM (Esper / Scalefusion / Android Enterprise) installs the APK and locks the tablet to it.
2. The app opens on **Set up this screen**. The installer either:
   - scans the QR code shown in the Setup console, which contains the server address and the one-time
     code; or
   - types the server address and the 6-digit code.
3. The app calls `POST /v1/devices/pair` and receives the screen's **device key**.
   - The key goes into Android Keystore (encrypted, tied to the tablet).
   - The key never expires.
4. The app reads `GET /v1/devices/me`: its type, its name, its restaurant, and the network block
   (`hub_url`, `cloud_url`, `mode`). It opens that screen.
5. From then on, power on means straight to the screen, with no login and no setup.

**Changing things later is done from the admin, never on the tablet.** Rename a screen, move a table
number, change a kitchen station or printer: the change reaches the tablet live.

**Replacing a broken tablet:** press **Re-pair** in the Setup console, then scan the new code on the
new tablet. The old tablet's key stops working at once.

The setup is forgotten only when the server answers `401 device_not_set_up` (the screen was re-paired
or disabled). Network errors never unpair it.

## 3. Offline and Hybrid

| Where the tablet is | What happens |
|---|---|
| **Cloud restaurant**, internet down | The screen keeps its pages (bundled) and last menu, and shows "Offline — retrying". Orders need the internet. |
| **Hybrid restaurant** (hub box), internet down | Nothing changes for guests and kitchen: tablets talk to the hub over the local Wi-Fi. LankaQR switches off (it needs the bank); cash and card terminals with their own SIM work. |
| Hybrid, hub broken | Tablets switch to the cloud by themselves ("Cloud (hub down)"). Numbers come from 500 up, so nothing clashes. |
| Hub back | Tablets return to the hub within about 10 seconds. The hub first copies everything the cloud did. |

The switching logic already runs inside the screen code:
- `net` in core.js tries the hub first, then the cloud;
- it follows the server's `use_hub` answer (HTTP 409) and WebSocket close code 4409;
- it checks the hub every 10 seconds while working through the cloud.

The APK gets all of this for free. Its only extra job is to allow the WebView to reach the hub's LAN
address.

## 4. Admin configuration at setup time

All of it is set in the **Setup console** (installation team) and delivered to the tablet by
`/v1/devices/me`, config sync and live events:

| Screen | Configured in the console |
|---|---|
| Table | Table number; which menu categories it shows; open tab or pay first; card: none (card rules) |
| Kiosk | Menu categories; card reader serial; its own receipt printer; welcome photos; Easy reach |
| Cashier POS | Card reader or SoftPOS; receipt printer and cash drawer; staff PINs |
| Kitchen (KDS) | Station (grill, wok, bar…) or all; kitchen printer; bump bar |
| Status board / menu board | Page timing, photos |
| All | Name, hub or cloud, remote reload / identify, disable |

## 5. Printers and payment hardware in the APK

The web version prints with WebUSB. The APK adds one JavaScript bridge, and the screens use it
automatically:

```js
window.KioskNative = {
  printEscPos(base64, printer) { ... },   // USB, Bluetooth or LAN (port 9100); Promise
};
```

Card payments:
- **Kiosk:** a built-in certified reader (for example a PAX IM30), driven by the bank's
  semi-integrated SDK. The bank's signed callback confirms the payment, as it does today.
- **Cashier or waiter:** a reader, or SoftPOS (tap on the tablet itself), which is allowed only on
  staff screens.

## 6. Security

- A device key per tablet, kept in the Keystore. Every API call and live connection needs it.
- Screen pages are bundled in the APK, so there is no public URL to browse.
- Wrong setup codes are limited (10 per 5 minutes per network).
- Hidden settings (hold the top-left corner) need a manager PIN. "Forget setup" needs an installer
  login.
- The Android side: the tablet is locked to the app (Lock Task), with no status bar, no settings and
  no other apps; USB debugging is off; the MDM can wipe or lock a lost tablet.
- HTTPS to the cloud. On the hub's local network, the hub uses its own certificate (pinned by the
  APK), or plain HTTP inside the restaurant's screen-only Wi-Fi.

## 7. Updates

- **Screen pages:** versioned. The APK downloads a new bundle from the cloud, and keeps the previous
  one to roll back if the new one fails to start.
- **APK itself:** through the MDM, at night, in stages (1 restaurant, then 10%, then all).
- **Hub box:** a Docker image, updated by us remotely at night.

## 8. Build plan for the APK

| Step | What | Done when |
|---|---|---|
| 1 | Kotlin shell + WebView loading the bundled pages; first-run QR / code setup; Keystore | A tablet sets up with one code and survives reboots |
| 2 | Kiosk mode: Lock Task, start on boot, keep awake, brightness, hide system bars | Guests can't leave the app |
| 3 | `KioskNative.printEscPos` for USB, Bluetooth and LAN printers | Test page prints from the Setup console |
| 4 | Offline bundle and update channel with rollback | Airplane mode still shows the screen; bad update rolls back |
| 5 | Bank SDK: kiosk reader and SoftPOS | Test payment of Rs 10 approved and refunded |
| 6 | MDM enrolment, remote restart, lost-tablet wipe | A new tablet is ready in 10 minutes out of the box |
| 7 | Field test in one restaurant for 2 weeks | No manual restarts needed |
