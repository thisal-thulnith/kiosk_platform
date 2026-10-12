// Admin sessions for the consoles. One login screen; two kinds of people:
//   "admin"     - the restaurant (owner / manager): Owner app and Menu editor, own restaurants only
//   "installer" - our installation and support team (platform login): Platform and Setup consoles.
// Same storage keys as the older pages, so a login there carries over.
import { request } from "./net";
import { codeInAddress } from "./screens";
import { store } from "./store";

export type Venue = { id: string; name: string; code: string; tenant_name?: string; timezone: string; settings: Record<string, any>; plan?: any; [k: string]: any };
const KEYS = { admin: "kiosk:admin", installer: "kiosk:platform" } as const;
export type AdminKind = keyof typeof KEYS;
export type LoginStep = { need: "done"; kind: AdminKind } | { need: "otp" } | { need: "setup"; setup_token: string; secret: string; uri: string };
type LoginReply = { access_token?: string; kind?: AdminKind; need?: string; [k: string]: any };
/** Where each kind of account works: our team's Platform console, or the restaurant's Owner app. */
export const HOME: Record<AdminKind, string> = { installer: "/platform", admin: "/owner" };

export class Admin {
  readonly key: string;
  token: string | null;
  venues: Venue[] = [];
  venue: Venue | null = null;

  constructor(readonly kind: AdminKind) {
    this.key = KEYS[kind];
    const saved = store.get<string | { token: string }>(this.key, sessionStorage);
    this.token = (typeof saved === "string" ? saved : saved?.token) ?? null;
  }
  headers(): Record<string, string> {
    return this.token ? { Authorization: `Bearer ${this.token}` } : {};
  }
  async api<T = any>(method: string, path: string, body?: unknown): Promise<T> {
    try {
      return await request<T>(method, path, { body, headers: this.headers() });
    } catch (e: any) {
      if (e?.status === 401) {
        this.logout();
        location.reload();
      }
      throw e;
    }
  }
  get<T = any>(path: string): Promise<T> {
    return this.api<T>("GET", path);
  }
  /** Path under the chosen restaurant: /v1/admin/venues/{id}{path}. */
  v(path = ""): string {
    return `/v1/admin/venues/${this.venue?.id}${path}`;
  }
  /** One login for everyone: the account says which console it opens (`kind`). Team accounts may be
   *  asked for their phone code first, or to set it up. */
  async login(email: string, password: string, otp?: string): Promise<LoginStep> {
    return this.signedIn(await request<LoginReply>("POST", "/v1/auth/login", { body: { email, password, otp } }));
  }
  async finishTwoStep(setupToken: string, otp: string): Promise<LoginStep> {
    return this.signedIn(await request<LoginReply>("POST", "/v1/auth/two-step", { body: { setup_token: setupToken, otp } }));
  }
  private signedIn(res: LoginReply): LoginStep {
    if (!res.access_token || !res.kind) return res as LoginStep;
    const key = KEYS[res.kind];
    store.set(key, res.kind === "installer" ? res.access_token : { token: res.access_token }, sessionStorage);
    if (res.kind === this.kind) this.token = res.access_token;
    return { need: "done", kind: res.kind };
  }
  logout(): void {
    this.token = null;
    store.set(this.key, null, sessionStorage);
  }
  async loadVenues(): Promise<Venue[]> {
    this.venues = await this.get<Venue[]>("/v1/admin/venues");
    // The restaurant is in the address (/demo/owner); ?venue=<id> still works for old links.
    const code = codeInAddress();
    const wanted = new URLSearchParams(location.search).get("venue") ?? this.venues.find((v) => v.code.toLowerCase() === code)?.id;
    if (wanted) store.set("kiosk:admin:venue", wanted);
    const saved = store.get<string>("kiosk:admin:venue");
    this.venue = this.venues.find((v) => v.id === saved) ?? this.venues[0] ?? null;
    if (this.venue) {
      const page = location.pathname.split("/").filter(Boolean).pop() ?? "owner";
      const url = new URL(location.href);
      url.searchParams.delete("venue");
      url.pathname = `/${this.venue.code.toLowerCase()}/${page}`;
      if (url.href !== location.href) history.replaceState(history.state, "", url);
    }
    return this.venues;
  }
  chooseVenue(id: string): void {
    store.set("kiosk:admin:venue", id);
    const v = this.venues.find((x) => x.id === id);
    const page = location.pathname.split("/").filter(Boolean).pop() ?? "owner";
    const url = new URL(location.href);
    url.searchParams.delete("venue");
    if (v) url.pathname = `/${v.code.toLowerCase()}/${page}`;
    location.href = url.toString();
  }
  /** Download a CSV (or any file) that needs the login header. */
  async download(path: string, filename: string): Promise<void> {
    const res = await fetch(path, { headers: this.headers() });
    if (!res.ok) throw new Error(`Download failed (${res.status})`);
    const url = URL.createObjectURL(await res.blob());
    const a = Object.assign(document.createElement("a"), { href: url, download: filename });
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
  }
}
