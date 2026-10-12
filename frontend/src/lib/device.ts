// A set-up screen: its device key (kept for good, same storage as the older screens, so tablets
// set up there keep working) and the staff PIN session (per browser tab, cleared on lock).
import { applyBrand } from "./brand";
import { clientInfo } from "./client";
import { net, request, type RequestOpts } from "./net";
import { store } from "./store";
import type { Me } from "./types";

/** What sign-in (screen code) and pairing (old 6-digit code) return. */
export type SignedIn = {
  device_token: string;
  device: { id: string; type: string; name: string; venue_id?: string; venue_code?: string; station?: string | null; table_ref?: string | null };
  replaced_another_device?: boolean;
};

/** A screen code as typed: letters and digits only, upper case ("k7mq-4xpa 2r" -> "K7MQ4XPA2R"). */
export const cleanScreenCode = (code: string): string => code.toUpperCase().replace(/[^0-9A-Z]/g, "");

/** Sign a device in with its restaurant's address part ("demo") and its screen code. Stores nothing. */
export function signInRequest(venue: string, code: string): Promise<SignedIn> {
  return request<SignedIn>("POST", "/v1/devices/sign-in", { body: { venue: venue.trim().toLowerCase(), code: cleanScreenCode(code), client: clientInfo() } });
}

export class Device {
  readonly key: string;
  readonly slot: string;
  token: string | null;
  staffToken: string | null;
  me: Me | null = null;

  constructor(readonly page: string) {
    this.slot = new URLSearchParams(location.search).get("slot") || "main";
    this.key = `kiosk:dev:${page}:${this.slot}`;
    this.token = store.get<{ token: string }>(this.key)?.token ?? null;
    this.staffToken = store.get<string>(`${this.key}:staff`, sessionStorage);
    // Opened from the cloud address but the restaurant runs on its hub: carry this setup over to the
    // hub's address on the local network (the launcher there stores it and opens the same screen).
    net.onHandoff = (hub) => {
      const saved = store.get<{ token: string; device: unknown }>(this.key);
      if (!saved?.token) return;
      const move = btoa(JSON.stringify({ device_token: saved.token, device: saved.device, slot: this.slot }));
      location.href = `${hub}/#move=${encodeURIComponent(move)}`;
    };
    // The hub got a new address on the network: ask the cloud for it, then go there.
    net.onStale = () => {
      this.get<Me>("/v1/devices/me")
        .then((m) => {
          const hub = m.network.hub_url?.replace(/\/$/, "");
          // This page came from the hub's old address: open it from the new one. Otherwise just use it.
          const pageOnOldHub = net.hubIndex() >= 0 && net.bases[net.hubIndex()] === "";
          if (hub && hub !== location.origin && pageOnOldHub) net.onHandoff?.(hub);
          else net.configure(m.network);
        })
        .catch(() => {});
    };
  }

  headers(): Record<string, string> {
    const h: Record<string, string> = {};
    if (this.token) h["X-Device-Token"] = this.token;
    if (this.staffToken) h["Authorization"] = `Bearer ${this.staffToken}`;
    return h;
  }

  api<T = any>(method: string, path: string, opts: RequestOpts = {}): Promise<T> {
    return request<T>(method, path, { ...opts, headers: { ...this.headers(), ...(opts.headers ?? {}) } });
  }
  get<T = any>(path: string): Promise<T> {
    return this.api<T>("GET", path);
  }
  post<T = any>(path: string, body: unknown = {}, idem?: string): Promise<T> {
    return this.api<T>("POST", path, { body, idem });
  }
  put<T = any>(path: string, body: unknown): Promise<T> {
    return this.api<T>("PUT", path, { body });
  }

  async pair(code: string): Promise<SignedIn> {
    const res = await request<SignedIn>("POST", "/v1/devices/pair", { body: { code: code.trim(), client: clientInfo() } });
    this.keep(res);
    return res;
  }
  /** Sign in with the restaurant's address part ("demo") and the screen code (K7MQ-4XPA-2R). */
  async signIn(venue: string, code: string): Promise<SignedIn> {
    const res = await signInRequest(venue, code);
    this.keep(res);
    return res;
  }
  private keep(res: SignedIn): void {
    this.token = res.device_token;
    store.set(this.key, { token: res.device_token, device: res.device });
  }
  unpair(): void {
    store.set(this.key, null);
    this.setStaff(null);
    this.token = null;
  }
  setStaff(token: string | null): void {
    this.staffToken = token;
    store.set(`${this.key}:staff`, token, sessionStorage);
  }
  heartbeat(): Promise<unknown> {
    return this.post("/v1/devices/heartbeat", { client: clientInfo() });
  }
  async loadMe(): Promise<Me> {
    this.me = await this.get<Me>("/v1/devices/me");
    net.configure(this.me.network);
    applyBrand(this.me.venue.brand);
    return this.me;
  }
}
