# Plan: a real POS, simple and safe

Written for: the owner of this project and anyone building on it. What changes, why, in what order.

## 1. Screen sign-in: restaurant address + screen code (like Square device codes)

**Today:** a 6-digit setup code that expires after 10 minutes, so setting up feels like work.

**New:**
- Every screen (table, POS, waiter, kitchen) has its own **screen code**, e.g. `K7MQ-4XPA-2R`
  (10 characters, no look-alike letters). The installer sees it in the Setup console.
- To sign a device in: open the restaurant's address (`https://app…/demo`, or type it in the table
  app) and enter the screen code. That's it, for good: the device keeps its own key and stays
  signed in through restarts and updates.
- Safe because:
  - a code only works at **its** restaurant's address and only for **its** screen;
  - signing in on another tablet **signs the old one out**, and the console shows which tablet holds
    the screen;
  - wrong codes are rate-limited per network address;
  - the installer can **reset** a code at any time, which also signs the device out.
- Staff still log in with their PIN for money and orders, and screens lock after a few idle
  minutes. That is the right security for staff; it is not "setting up again".
- The QR code in the Setup console holds the same address + code, so scanning it is the fastest way.

## 2. Paying at the table, the way restaurants do it

- **The guest:** taps **Ask for the bill** on the table app and says how: **cash**, **card** or
  **QR**.
- **The waiter's task list:** "T5 wants the bill · Cash · Rs 2,466". The waiter taps **Print bill**.
  It prints on the waiter's printer, or on the POS printer if the waiter has none, and the app says
  which ("Printed at the counter").
- **Taking the money:**
  - **Cash:** the waiter collects it and types what was given; the change is shown in big numbers.
    The receipt prints at the same printer, with the change on it, and the waiter brings back the
    change and the receipt.
  - **Card:** the waiter takes the card machine to the table. With an integrated reader the app waits
    for the tap; with the bank's own machine the waiter types the approval code.
  - **QR:** the guest scans on the table app; the waiter sees it paid.
- **The cashier sees everything live:** which tables are paying, how, who is taking it, and every
  receipt.

## 3. Money can't go wrong

- **One payment at a time per bill:** opening "Take payment" holds the bill for that person (about
  2 minutes). Anyone else sees "Nimal is taking this payment" and can't start a second one.
- **Every money action carries one key:** a retry after a network blip returns the first result and
  never charges twice.
- **When the connection drops mid-payment,** the screen first checks the server ("Checking the
  payment…") before it allows trying again.
- **While offline, money buttons pause** and a clear "No connection" bar shows. A Hybrid hub keeps
  the restaurant online locally.

## 4. Simpler POS and waiter apps, every orientation

- **Waiter:** three things only — Tasks (what to do now), Tables, Me (my payments and cash).
- **POS:** the menu, the cart and one "Needs you" list; the rest goes into "⋯".
- **Every screen works in portrait and landscape,** on phones, tablets and laptops.

## 5. Coming soon

- **Self-order kiosk and status board:** marked "Coming soon" in the Platform and Setup consoles.
  Their screens show a coming-soon page. The code stays, so they can be switched on later.

## 6. For the mobile app developer

- `docs/MOBILE_APP_API.md`: the full guide (sign-in, start-up, menu, orders, paying, calls, visit,
  feedback, live events, errors, offline / hub, printing).
- `docs/openapi.json`: every endpoint, generated from the server.

## Order

1. Screen codes (backend, Setup console, sign-in page)
2. Bill with "how will you pay", printer routing, payment hold, offline guard (backend)
3. POS + waiter: simpler and responsive, with the new pay flow
4. Kiosk and status board: coming soon
5. Mobile developer guide and OpenAPI
6. Tests for every step, then the full browser test
