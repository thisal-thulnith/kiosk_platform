# Screen app contract (web today, Android APK later)

Written for: whoever builds the Android app (APK) for our tablets and kiosks.

Every screen (table, kiosk, cashier, kitchen, status board, menu board, waiter) runs the same web app
from the server. The APK wraps that app and adds what a browser can't do well: starting on boot,
locking the tablet to the app, storing the screen's token safely, and printing to any printer. The
server does not need to know whether a screen is the browser or the APK.

## 1. Setup: server address + one code

The installer adds the screen in the **Setup console** (installation team login only). The console
shows:

- the **server address**, e.g. `https://cloud.example.lk`
- a **6-digit setup code**: secret, single use, valid for 10 minutes
- a **QR code** containing both: `https://cloud.example.lk/?pair=123456`

On first start the app asks for the setup: scan the QR code, or type the server address and the code.
It then calls:

```
POST {server}/v1/devices/pair          {"code": "123456"}
→ 200 {"device_token": "...", "device": {"id", "type", "name", "venue_id", "station", "table_ref"}}
```

The code decides everything: the restaurant, the screen type, the table number or the kitchen
station. The app opens its own built-in table screen (other types open `{server}/{code}/<pos|waiter|kitchen|kiosk|board>`).
In the browser, the launcher `/` does this.

## 2. Never logs out

- The device token does not expire. Send it on every call as `X-Device-Token: <token>` (and on the
  WebSocket as `?token=`).
- On network or server errors, keep retrying. The web app shows "Reconnecting…" and carries on by
  itself.
- Only one answer means "forget the setup": **HTTP 401 with error code `device_not_set_up`**, or a
  WebSocket close code **4401** followed by that error. This happens when the installer re-paired the
  slot (a replacement tablet) or disabled it. Then show the setup screen again. Never unpair on any
  other error.
- The web app stores the token in `localStorage` under `kiosk:dev:<type>:<slot>`. The APK should keep
  it in Android secure storage and give it to the WebView at start. Staff PIN sessions (cashier,
  waiter) are separate and short-lived, and they don't affect the device token.
- Hidden settings (hold the top-left corner for 3 seconds) need a manager PIN. "Set up again" needs
  an installer login.

## 2b. Hub or cloud (Hybrid restaurants)

`GET /v1/devices/me` includes where to talk to:

```json
"network": {"mode": "hybrid", "hub_url": "http://192.168.1.20:8000", "cloud_url": "https://cloud.example.lk", "served_by": "hub"}
```

- `mode: "cloud"`: use the cloud only.
- `mode: "hybrid"`: use `hub_url` first (it works when the internet is down), and `cloud_url` if
  the hub can't be reached.
- While the hub is alive, the cloud answers screens with **HTTP 409 `use_hub`** and closes WebSockets
  with **4409**. Go back to the hub.
- While working through the cloud, check `GET {hub_url}/v1/health` every 10 s and return to the hub
  when it answers.
- Setting up a screen on the hub works too: the hub passes the one-time code to the cloud (it needs
  the internet once).
- Staff PIN sessions belong to the server that issued them. After a switch, staff may need to enter
  their PIN again.

The web app does all of this in `net` (core.js), so the APK gets it for free.

## 3. What the screen talks to

| Call | Purpose |
|---|---|
| `GET /v1/devices/me` | Who am I: device, venue, modules, which payment methods are on, card reader mode |
| `WS /v1/ws?token=` | Live events (`hello`, `resync`, order / menu / kds events, `device.command`, `print.job`) |
| `POST /v1/devices/heartbeat` | Every 60 s, for "last seen" in the console |
| `device.command` event | `reload`, `identify`, `connect_printer` sent from the Setup console |
| `POST /v1/orders/{id}/notify` | The guest's mobile, for "ready" and receipt texts (that order only) |

## 4. Printing (the APK's main native job)

Printers are set up in the Setup console. A printer that belongs to a screen (a kiosk's built-in
printer, a USB printer on a till) gets its jobs through that screen:

```
event  print.job {"job_id"}             (on topic device:<this screen>)
GET    /v1/print/printers               printers that belong to this screen
GET    /v1/print/jobs                   waiting jobs, with escpos_b64 (ESC/POS bytes) and text
POST   /v1/print/jobs/{id}/result       {"ok": true} or {"ok": false, "error": "paper out"}
```

The web app prints with WebUSB. If the APK injects this object, the web app uses it instead, so
Bluetooth and network (port 9100) printers work too, with no change on the server:

```js
window.KioskNative = {
  printEscPos(base64, printer) { /* send bytes; return a Promise that rejects on failure */ },
};
```

Cloud printers (Star CloudPRNT) don't need the app at all: they fetch their jobs from
`/v1/cloudprnt/<secret>` themselves.

## 5. What the APK must also do

- Start on boot and stay in the foreground (kiosk / lock-task mode, managed with an MDM).
- Keep the screen awake. The web app already asks for a wake lock.
- Allow the camera for QR setup, and the microphone later for voice ordering.
- Payments: card readers and SoftPOS plug in through the bank's SDK. The server side is already there
  (`/v1/orders/{id}/payments/card-terminal` plus the signed processor callback).
