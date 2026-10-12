# Self-order kiosk, and connecting the hardware

Written for: installers and the product team. It covers how a self-service kiosk works end to end, and
how each piece of hardware connects: receipt printers, card terminals, cash drawers, the network and
hub, and SMS.

## 1. How the self-order kiosk works

**The guest's side:**

1. The attract screen shows the welcome photos. The guest taps and picks English, Sinhala or Tamil.
   **Easy reach** moves everything down for wheelchair users and children.
2. **Menu**: the categories for this time of day. Tiles show photos, prices, allergens, "Deal" prices
   and sold-out items. In AI mode, quick items come first when the kitchen is busy.
3. **Item**: choose options (spice level, extra cheese), "Make it a meal" (combo) and notes. After
   adding an item, the kiosk suggests what goes well with it.
4. **Rewards** (optional): enter a phone number to join or be recognised (with consent). The guest sees
   their tier price and "your usual".
5. **Review, then Confirm**: the order number appears at once (K001…).
6. **Pay**:
   - **LankaQR**: scan with any banking app, and the bank's confirmation arrives within seconds.
   - **Card**: tap or insert on the built-in reader.
   - **Pay at the cashier**: the kiosk prints the number slip with a barcode, and the order waits.
     Unpaid orders expire after a set time.
7. When paid, the order goes to the kitchen (release rule A), and the kiosk's own printer prints the
   receipt with the big order number.
8. **"Text me when it's ready"** (optional): the guest types a mobile number and gets one SMS when the
   kitchen finishes, plus a private receipt link.
9. The guest watches the **status board**: *Preparing*, then *Ready*. They collect at the counter.

The kiosk resets itself after a few idle seconds, and nothing of the last guest stays on screen,
including a half-typed phone number.

**Behind the scenes:**

| Event | Where it goes |
|---|---|
| Order confirmed | Price is recalculated on the server from the menu (never trusted from the screen); taxes applied |
| Paid | Invoice number, receipt to **this kiosk's** printer, points, SMS receipt link, kitchen release |
| Kitchen | KDS tickets by station (grill, wok, bar), with a promised time and the rush / VIP order |
| Ready | Status board, SMS "ready", cashier's "ready to hand over" list |
| Stock | Portions come off when cooking starts; at zero the item is sold out on every screen |

## 2. Receipt and kitchen printers

**Every slip goes through the cloud print queue** (or the hub's, in Hybrid), so a printer that was off
prints what it missed.

| Type | Best for | How to connect |
|---|---|---|
| **Cloud printer (Star CloudPRNT)**, e.g. Star mC-Print3 / TSP143IV | Counter and kitchen | Printer on the network. In its settings page, go to CloudPRNT → Server URL (shown in the Setup console) and set polling to 5 s. In Hybrid, the URL points at the hub, so printing works without internet. |
| **USB into a screen** | Kiosk built-in printers, a printer next to a till | Plug it into the tablet (OTG adapter on Android). Tap **Connect printer** on that screen once. The APK can also drive Bluetooth and LAN (port 9100) printers. |

**What prints where:**
- **Receipts:** printed by the printer of the screen where the guest paid (the kiosk's own printer, or
  the till's printer). If that screen has no printer, a shared counter printer prints it.
- **Order-number slips:** the kiosk's or till's printer. If there's no slip printer, the receipt
  printer prints them.
- **Kitchen tickets:** every kitchen printer, or only the items of its stations (for example, a bar
  printer prints drinks only).
- **Cash drawer:** connected to a receipt printer, and opens on cash payments.

Always finish with **Print test page**. The printer ticks itself when the page comes out.

## 3. Card terminals

| Where | Hardware | How it works |
|---|---|---|
| Kiosk | Certified built-in reader (e.g. PAX IM30) | Setup console → **Card** → reader serial → **Test reader**. The kiosk sends the amount; the bank talks to the reader; the bank's **signed** callback confirms the payment. Card numbers never reach our system. |
| Cashier / waiter | A reader, or **SoftPOS** (tap on the staff tablet itself) | Same setup. SoftPOS is allowed only on staff screens (card-scheme rule). |
| Table screens | A small certified NFC reader at the table (e.g. PAX IM15) **or** tap on the table tablet (SoftPOS) | With a reader, the guest pays alone ("Pay by card"). With tap-on-tablet, card rules need staff present: the guest sees "Paying by card? Call your waiter". The waiter either taps **Staff** + PIN on the table (waiter assist) so the tablet takes the tap, or takes it on their own handheld. |
| Waiter handheld | SoftPOS (tap on the phone) or a reader | **Card (tap on phone)** next to "Bill by LankaQR" on each table's order. |
| Bank terminal not integrated | Any countertop terminal | The cashier types the approval code (the "Card (manual approval code)" option). |

In Hybrid, the bank's confirmation arrives at the cloud and is handed to the restaurant's hub.
Terminals with their own SIM keep working when the restaurant's internet is down.

## 4. Network and hub

- **Router:** a business line plus a 4G backup if possible. Use a separate Wi-Fi for screens, never the
  guest Wi-Fi.
- **UPS:** the router, the hub and the cashier.
- **Hub (Hybrid only):** a small fanless computer next to the router.
  1. Setup console → Network → **Hub setup code**.
  2. On the box, run `kiosk hub-setup --cloud … --code … --lan-url http://<hub-ip>:8000` once.
  3. Start it with `APP_MODE=edge kiosk serve`.
  4. It shows **Online** in the console.
  5. Give it a fixed IP address.

## 5. SMS to guests

- The guest types a mobile number on the kiosk, the table screen or at the cashier. It's used for that
  order only, and never shown on any screen.
- The guest gets **"Your order K007 is ready"** and a private **receipt link** (a signed URL; nobody can
  guess another guest's receipt).
- The restaurant can switch either message off in Setup → "How this restaurant works".
- **Gateway:** today a mock that writes `sms.log`. A Sri Lankan gateway adapter (Notify.lk, Text.lk,
  Dialog or Mobitel bulk SMS) needs the account's API key and a registered sender name, and plugs into
  `kiosk.infra.sms`.
- On a hub without internet, texts wait in the queue and are sent when it's back.
