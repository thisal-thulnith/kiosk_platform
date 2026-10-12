// Live events from the server (WebSocket), with catch-up after a reconnect, hub <-> cloud switching
// and a heartbeat. onEvent gets {type, data}; "resync" means: reload everything.
import type { Device } from "./device";
import { net } from "./net";

export type LiveEvent = { type: string; data?: any; seq?: number };
export type LiveStatus = "connecting" | "online" | "offline" | "unpaired";

export function connectLive(device: Device, onEvent: (e: LiveEvent) => void, onStatus: (s: LiveStatus) => void): () => void {
  let since: number | null = null;
  let epoch: string | null = null;
  let helloSeq = 0;
  let ws: WebSocket | null = null;
  let backoff = 1000;
  let failed = 0;
  let closed = false;
  let ping: ReturnType<typeof setInterval> | undefined;

  const open = () => {
    const base = net.base() ? new URL(net.base()) : location;
    const proto = base.protocol === "https:" ? "wss" : "ws";
    const q = new URLSearchParams({ token: device.token ?? "" });
    if (since !== null && epoch) {
      q.set("since", String(since));
      q.set("epoch", epoch);
    }
    onStatus("connecting");
    let opened = false;
    ws = new WebSocket(`${proto}://${base.host}/v1/ws?${q}`);
    ws.onopen = () => {
      opened = true;
      ping = setInterval(() => ws?.readyState === 1 && ws.send(JSON.stringify({ type: "ping" })), 25000);
    };
    ws.onmessage = (m) => {
      let msg: any;
      try {
        msg = JSON.parse(m.data);
      } catch {
        return;
      }
      if (msg.type === "hello") {
        backoff = 1000;
        failed = 0;
        onStatus("online");
        helloSeq = msg.seq;
        const first = since === null;
        epoch = msg.epoch;
        if (first) {
          since = msg.seq;
          onEvent({ type: "resync" });
        }
        return;
      }
      if (msg.type === "pong") return;
      if (msg.type === "resync") {
        epoch = msg.epoch;
        since = helloSeq;
        onEvent({ type: "resync" });
        return;
      }
      if (typeof msg.seq === "number") since = msg.seq;
      if (msg.type === "device.command" && msg.data?.device_id === device.me?.device.id) {
        if (msg.data.command === "reload") location.reload();
        if (msg.data.command === "identify") window.dispatchEvent(new CustomEvent("kiosk:identify"));
        return onEvent({ type: "device.command", data: msg.data });
      }
      onEvent(msg);
    };
    ws.onclose = (ev) => {
      clearInterval(ping);
      if (closed) return;
      if (ev.code === 4401) {
        onStatus("unpaired");
        setTimeout(() => location.reload(), 3000);
        return;
      }
      if (ev.code === 4409) {
        const moved = net.goToHub();
        onStatus("connecting");
        setTimeout(open, moved ? 300 : backoff);
        backoff = Math.min(backoff * 2, 15000);
        return;
      }
      if (!opened && ++failed >= 2 && net.bases.length > 1) {
        net.next();
        failed = 0;
      }
      onStatus("offline");
      setTimeout(open, backoff);
      backoff = Math.min(backoff * 2, 15000);
    };
  };
  open();

  void device.heartbeat().catch(() => {});
  const beat = setInterval(() => device.heartbeat().catch(() => {}), 60000);
  // Working through the cloud because the hub was down? Go back to the hub as soon as it answers.
  const probe = setInterval(() => {
    const hub = net.hubIndex();
    if (hub < 0 || net.kind() === "hub") return;
    fetch(`${net.bases[hub]}/v1/health`, { cache: "no-store" })
      .then((r) => {
        if (r.ok) {
          net.use(hub);
          ws?.close();
        }
      })
      .catch(() => {});
  }, 10000);

  return () => {
    closed = true;
    clearInterval(beat);
    clearInterval(probe);
    clearInterval(ping);
    ws?.close();
  };
}
