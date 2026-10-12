# Setup guide: set up once, then it runs every day by itself

See also: [FULL_SYSTEM_A_TO_Z.md](FULL_SYSTEM_A_TO_Z.md) (how everything fits together), [NEW_RESTAURANT_A_TO_Z.md](NEW_RESTAURANT_A_TO_Z.md) (the full checklist, sales to support),
[KIOSK_AND_DEVICES.md](KIOSK_AND_DEVICES.md) (kiosk flow, printers, card terminals, network, SMS),
[APK_PLAN.md](APK_PLAN.md) (the tablet app) and [DEVICE_APP.md](DEVICE_APP.md) (its API contract).

Who does what:

| Step | Who | How often |
|---|---|---|
| 1. Platform ready (cloud, HTTPS, your login) | You | Once |
| 2. Create the restaurant with its package and equipment | You (Platform console = admin panel) | Once per restaurant |
| 3. Menu, staff PINs, payments, printers, equipment | Your installation team (that restaurant's Setup console) | Once, then when things change |
| 4. Prepare each Android screen | Your installer | Once per screen |
| 5. On-site setup of each screen | Your installer | Once per screen (about 1 minute) |
| 6. Daily use | Restaurant staff | Nothing to set up. Cashier logs in with a PIN |

The **Setup console is for our team only** (platform login). The restaurant gets the **Owner dashboard**
and the **Menu editor** with its own email and password, and never sees the screen setup.

---

## 1. Platform (once)

- Run the server in the cloud behind **HTTPS** (for example `https://app.yourcompany.lk`).
  **Android only installs the app and keeps the offline copy on HTTPS.** A plain `http://192.168…` address
  works for trying screens in a browser, but it cannot be installed as an app.
- Create your team's logins: `uv run kiosk create-platform-admin --email you@yourcompany.lk --password ...`

## 2. Create the restaurant (once per restaurant)

Open `https://…/platform` (the admin panel) → **New restaurant**: company, first branch and
its code, owner email and password, first manager PIN, optionally the sample menu, and the **package**.

**Equipment**: pick the screens (tables, self-order kiosks, kitchen displays, cashier POS, status board,
menu board, waiter handhelds) and the hardware (router, receipt printers, cash drawers, kiosk printers,
kitchen printer, card readers, UPS). Whatever a choice depends on is added and locked (🔒), with the reason:

| If you choose | It also needs |
|---|---|
| Any screen | A router (the restaurant's network for the screens) |
| Self-order kiosk | An order status board, and a kiosk printer per kiosk |
| Table screens | A cashier (guests can pay the bill at the counter) |
| Waiter handheld | Table screens |
| Cashier | A receipt printer and a cash drawer per cashier |

Each restaurant in the list shows **Setup n / 11** and an **Open setup console** button that opens its own
Setup console. More branches: in that Setup console, under **Add a branch**.

## 3. Restaurant data (once, then when it changes)

In that restaurant's Setup console (installation team login):

- **Staff & PINs**: cashiers, waiters, kitchen, managers.
- **Menu and tax rules**: through the admin API today (menu editor screen is in the plan).
- **Card payments per screen**: press **Card** next to a screen:
  - kiosk: *Built-in card reader* + the reader's serial number;
  - cashier / waiter: a reader, or *Tap on this tablet* (SoftPOS);
  - tables: none (card rules don't allow tap-on-tablet without staff; guests use LankaQR or the cashier).

## 4. Prepare each Android screen (once, at your office)

Use one of these. For the pilot, **Option A** is recommended.

### Option A: Fully Kiosk Browser (recommended for pilots)
1. Install **Fully Kiosk Browser** on the tablet (Play Store) and buy the PLUS licence for kiosk features.
2. Settings:
   - **Start URL**: `https://app.yourcompany.lk/`
   - **Launch on boot**: on. **Kiosk mode** (lock the tablet to this app): on, with a PIN only your team knows.
   - **Keep screen on**, fixed brightness, **hide status bar and navigation bar**.
   - **Reload on network reconnect**: on. **Clear cache on start**: *off* (this would erase the screen's setup).
   - Disable the camera, microphone (until voice ordering), and pull-to-refresh.
3. Android settings: turn off battery optimisation for Fully Kiosk, set automatic updates to Wi-Fi only at night,
   connect to the **screens Wi-Fi** (not the guest Wi-Fi).

### Option B: Chrome "Install app" (no extra licence)
1. Open `https://app.yourcompany.lk/` in Chrome → menu → **Install app**.
2. Android settings → Security → **App pinning**: pin the installed app so guests can't leave it.
3. Limitation: Android does not start a web app by itself after a reboot; staff tap the icon once.

### Option C: our own Android app (later)
A small wrapper app (Capacitor) set as the tablet's home screen, managed with an MDM (Scalefusion or Esper):
starts on boot, remote restart and updates, and it is where a bank's SoftPOS / card-reader kit plugs in.

## 5. On-site setup of each screen (once, about a minute)

1. In the Setup console, press **Setup code** next to the screen's slot (the package created the slots: Table
   T1…Tn, Kiosk 1, Kitchen 1…), or add a screen. It shows the **server address**, a **6-digit code** (secret,
   single use, 10 minutes) and a **QR code** with both.
2. The tablet boots → the app opens on **Set up this screen** → scan the QR code, or type the code → **Connect**.
   The code decides what it is (Table T5, Kiosk 1, Grill kitchen…). There is no restaurant password on the
   tablet.
3. The screen opens by itself. From now on it starts straight to its screen after every restart or power cut,
   and never logs out. Only **Re-pair** or **Disable** in the console ends it (for example, a replacement
   tablet).
4. Leave it running for a minute before unplugging, so the browser saves the setup. Then run one test order
   through every path: table → pay → kitchen → status board → cashier.

The app's contract (for the future Android APK) is in [DEVICE_APP.md](DEVICE_APP.md).

## 5b. Payments, printers and the go-live checklist (once, in the Setup console)

Work top to bottom in **Setup console → Payments, Printers, Go-live checklist**. Nothing here needs a
computer on site: printers and payments talk to the cloud.

**Payments**
1. *Ways to pay*: tick Cash, LankaQR and Card for this restaurant. Screens hide what is off, and the server
   refuses it too.
2. *LankaQR merchant account*: choose the provider, enter the restaurant's **Merchant ID** and **API key** from
   the bank or gateway. Keep *Live payments* off while testing. Press **Test connection** until it shows
   *Connection OK*. The key is stored encrypted (`DATA_KEY`) and never sent to any screen.
3. *Card readers*: give each kiosk its reader with the screen's **Card** button (reader serial), then press
   **Test reader** in the Payments card.

**Printers**: press **+ Add printer** and pick how it is connected.

| Connection | Use it for | How to connect |
|---|---|---|
| **Cloud printer** (recommended) | Star mC-Print3, TSP143IV, or any CloudPRNT printer, at the counter or in the kitchen | Power and network only. Open the printer's settings page (its IP address is on the self-test page: hold FEED while switching on), CloudPRNT → Server URL: paste the URL the wizard shows, polling 5 s, save and restart. It turns **Online** by itself. |
| **Plugged into a screen (USB)** | Any ESC/POS USB receipt printer next to a cashier, kitchen or waiter screen | Plug the USB cable into the screen (OTG adapter on Android). Tap **Connect printer** on that screen once and choose the printer. Chrome remembers it after restarts. |
| Test printer | Trying the system without hardware | Slips are saved as files on the server (not allowed in production). |

For each printer choose what it prints: **receipts**, **order-number slips** (if none is chosen, the receipt
printer prints them), **kitchen tickets** for all stations or only some (for example a bar printer that prints
only drinks), plus paper width and whether a **cash drawer** is plugged into it. Then press **Print test page**.
Cloud and screen printers tick themselves when the page comes out, and for any other printer press
**It printed ✓**. Every slip goes through the cloud print queue, so a printer that was off or out of paper
prints what it missed when it is back. Failures show on the cashier and kitchen screens.

**Go-live checklist**: all green before you hand over. It covers business details, menu, taxes, staff PINs,
screens set up and online, payments tested, card readers tested, printers tested, and one real test order.

## 6. Every day after that

- **Power on → the app opens straight to its screen.** No setup, no login on tables, kiosks, kitchen or boards.
- **Cashier**: staff PIN → open the cash shift. It locks itself after 5 idle minutes. Close the shift at night.
- If the internet or server drops, screens show *Reconnecting…* and carry on by themselves when it is back.
- Menu, prices and sold-out changes appear on every screen within a second.

## Changing a screen later

- **Hold the top-left corner for 3 seconds** (or Ctrl+Shift+S on a keyboard) → enter the owner/manager
  password → rename, change the table number, full screen, reload, or *Set up again*.
- **Broken tablet**: set up the new one and pick the old screen's name. The old tablet stops working at once and
  the new one keeps the same table, station and card setup.
- **Disable a stolen tablet**: Setup console → *Disable* (or *Re-pair*).

## Troubleshooting

| What you see | Why | Fix |
|---|---|---|
| "Set up this screen" again on a tablet that was set up | The browser's storage was cleared (cache cleared, app data wiped, or unplugged right after setup) | Log in and pick the same screen; it takes over the old slot |
| "Reconnecting…" | No internet or the server is down | Wait; it retries by itself. Check the router / 4G backup |
| Card reader button missing on the kiosk | No reader configured for this screen | Setup console → *Card* |
| Table screen says an order is waiting for payment | The table is locked until the pay-at-cashier order is paid, cancelled or expires | Pay at the cashier (scan the barcode or type the table number) |
| App can't be installed | The page is on plain http | Use the HTTPS address |
