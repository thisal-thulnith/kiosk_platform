// Where API calls go. A cloud restaurant: the server this page came from. A hybrid restaurant: its
// hub on the local network first (works without internet), the cloud when the hub can't be reached.
// The server says which to use: /v1/devices/me -> network, "409 use_hub", WebSocket close 4409.

export type Network = { mode: "cloud" | "hybrid"; hub_url: string | null; cloud_url: string | null; served_by: "cloud" | "hub" };
type Kind = "hub" | "cloud" | "this";

class Net {
  bases: string[] = [""];
  kinds: Kind[] = ["this"];
  i = 0;
  mode: Network["mode"] = "cloud";
  /** Hub address this page can't call (an https page can't call an http hub): move the screen there. */
  hubElsewhere: string | null = null;
  onHandoff: ((hub: string) => void) | null = null;
  /** The hub didn't answer but the cloud says it is running: its address may have changed. */
  onStale: (() => void) | null = null;
  hubFailedAt = 0;
  private staleAt = 0;
  private listeners = new Set<(k: Kind) => void>();

  base(): string {
    return this.bases[this.i] ?? "";
  }
  kind(): Kind {
    return this.kinds[this.i] ?? "this";
  }
  onChange(fn: (k: Kind) => void): () => void {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }
  use(i: number): void {
    if (i < 0 || i === this.i || !this.bases.length) return;
    this.i = i % this.bases.length;
    this.listeners.forEach((fn) => fn(this.kind()));
  }
  next(): void {
    this.use((this.i + 1) % this.bases.length);
  }
  hubIndex(): number {
    return this.kinds.indexOf("hub");
  }
  /** The cloud says the hub is in charge. Use it, or move this screen to the hub's address. */
  hubLooksMoved(): void {
    const now = Date.now();
    if (now - this.hubFailedAt > 60000 || now - this.staleAt < 30000) return;
    this.staleAt = now;
    this.onStale?.();
  }
  goToHub(): boolean {
    if (this.hubIndex() >= 0) {
      this.use(this.hubIndex());
      return true;
    }
    if (this.hubElsewhere && this.onHandoff) this.onHandoff(this.hubElsewhere);
    return false;
  }
  configure(n: Network | undefined | null): void {
    if (!n) return;
    this.mode = n.mode;
    const here = location.origin;
    const norm = (u: string | null) => (u ? u.replace(/\/$/, "") : null);
    const list: [Kind, string | null][] = n.mode === "hybrid" ? [["hub", norm(n.hub_url)], ["cloud", norm(n.cloud_url)]] : [["cloud", norm(n.cloud_url)]];
    const bases: string[] = [];
    const kinds: Kind[] = [];
    this.hubElsewhere = null;
    for (const [kind, url] of list) {
      // Browsers block http calls from an https page (mixed content), e.g. cloud page -> LAN hub.
      if (kind === "hub" && url && url !== here && location.protocol === "https:" && url.startsWith("http:")) {
        this.hubElsewhere = url;
        continue;
      }
      const b = !url || url === here ? (n.served_by === kind || !url ? "" : null) : url;
      if (b === null || bases.includes(b)) continue;
      bases.push(b);
      kinds.push(kind);
    }
    if (!bases.length) return;
    this.bases = bases;
    this.kinds = kinds;
    this.i = 0;
  }
}

export const net = new Net();

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message);
  }
}

export type RequestOpts = { body?: unknown; headers?: Record<string, string>; idem?: string };

export async function request<T = unknown>(method: string, path: string, opts: RequestOpts = {}, tries = 0): Promise<T> {
  const headers: Record<string, string> = { ...(opts.headers ?? {}) };
  if (opts.body !== undefined) headers["Content-Type"] = "application/json";
  if (opts.idem) headers["Idempotency-Key"] = opts.idem;
  let res: Response;
  try {
    res = await fetch(net.base() + path, { method, headers, body: opts.body === undefined ? undefined : JSON.stringify(opts.body) });
  } catch {
    if (net.kind() === "hub" || (net.kind() === "this" && net.mode === "hybrid")) net.hubFailedAt = Date.now();
    if (tries < net.bases.length - 1) {
      net.next(); // hub unreachable: try the cloud (or back)
      return request<T>(method, path, opts, tries + 1);
    }
    throw new ApiError(0, "network", "Cannot reach the server. Check the network.");
  }
  if (res.status === 409) {
    const peek = await res.clone().json().catch(() => null);
    if (peek?.error?.code === "use_hub") {
      if (net.hubFailedAt && tries > 0) net.hubLooksMoved();
      else if (net.goToHub() && tries < net.bases.length - 1) return request<T>(method, path, opts, tries + 1);
    }
  }
  const text = await res.text();
  let data: any = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = text;
  }
  if (!res.ok) {
    const err = data?.error ?? {};
    throw new ApiError(res.status, err.code ?? `http_${res.status}`, err.message ?? res.statusText);
  }
  return data as T;
}

export const newKey = (): string => (crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`);
