# Setting up a new restaurant, A to Z

Written for: our sales, installation and support team. It follows the screens exactly: the
**Platform console** form has 4 parts, and the **Setup console** has 7 steps. How it all works behind
the scenes is in [FULL_SYSTEM_A_TO_Z.md](FULL_SYSTEM_A_TO_Z.md).

## A. Sales visit: decide what the restaurant needs

Note the tables, counters, kiosks wanted, kitchen stations, internet line, power, and whether they keep
their current POS. Then choose **how it works** (ticked in part 3 of the form):

| The restaurant wants… | Tick |
|---|---|
| Guests order and pay alone at a kiosk | **Self-order kiosks** |
| A screen on every table | **Order at the table** (+ **Open tab** if guests pay at the end) |
| Staff take orders at the counter on our till | **Counter POS (ours)** |
| Waiters with handhelds | **Waiter service** |
| To keep their current till | **Keep the restaurant's current POS** |
| A "Preparing / Ready" wall screen, a menu board | **Order-ready display** / **Menu board** |
| Paper tickets in the kitchen too | **Kitchen ticket printer** |
| Never to stop when the internet drops | **Works without internet (Hybrid)** |
| To text guests "your order is ready" | **Texts to guests** |

Whatever a choice needs is added and locked (🔒) with the reason. You don't have to remember it.

## B. Platform console: create the restaurant (5 minutes)

`/platform`, team login, **New restaurant**:

1. **The restaurant**: company, first branch, branch code (on invoices), time zone.
2. **The owner's login**: email, password (one is suggested), first manager PIN, sample menu.
3. **Package and how it works**: package and tier, the flows, add-ons, extra screens and equipment.
   The preview shows everything and the price.
4. **Create**: the restaurant, the owner login and every screen slot (Table T1…Tn, Kiosk 1,
   Kitchen 1…).

Give the owner their login (Owner dashboard and Menu editor). The Setup console stays with us. Then
press **Open setup console** on the restaurant's row.

## C. Setup console: 7 steps

It opens on the first unfinished step. Each step says what to do and gets a ✓ when done.

1. **Restaurant** (office): check the package; business details (legal name, VAT number, footer);
   how it works; welcome photos; branches.
2. **Menu & staff** (office): the menu editor (categories and times, 3 languages, photos, prices,
   stations, allergens, add-ons, meals, PLU codes), taxes, and staff with PINs.
3. **Network & equipment** (on site, first):
   - router with a separate screen Wi-Fi, and a UPS;
   - Hybrid: **Hub setup code**, then `kiosk hub-setup` on the hub, until it shows **Online**;
   - tick the router and UPS.
4. **Screens** (on site): for each tablet, **Setup code**, then scan or type on the tablet, then
   **Hardware** (all-in-one kiosk, POS terminal, kitchen screen), then the station for kitchen screens.
5. **Payments**:
   - ways to pay;
   - LankaQR merchant, then **Test connection**;
   - **Test reader** on each card screen (tables: a reader, or tap-on-tablet with a waiter);
   - the restaurant's own POS: address, secret, **Send test**, API key, menu CSV.
6. **Printers** (on site): tap **Connect printer** on screens with built-in printers; **+ Add printer**
   for the others (cloud URL or USB); what each prints; then **Print test page**.
7. **Test & go live**:
   - one real order through every path;
   - Hybrid: pull the internet cable and order once more;
   - every line green means **Ready to go live**. Press any red line and the console opens the step
     that fixes it.

## D. Training, daily use, support

The full user guide for every screen and every person is in the PDF manual
(`docs/Kiosk-Platform-Manual.pdf`) and in [FULL_SYSTEM_A_TO_Z.md](FULL_SYSTEM_A_TO_Z.md).
