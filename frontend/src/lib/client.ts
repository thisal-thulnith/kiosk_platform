// Which physical tablet this is. Made once per install and sent when the screen is set up and with
// every heartbeat, so the Setup console shows "SM-X205 · Android 14 · Chrome 128 · 192.168.1.33".
// The Android app sets window.KioskNative.deviceInfo() (Android ID, model, app version) instead.
import { newKey } from "./net";
import { store } from "./store";

export type ClientInfo = { install_id: string; app: string; app_version?: string; model?: string; os?: string; browser?: string; screen: string; page: string };

declare global {
  interface Window {
    KioskNative?: { deviceInfo?: () => string; printEscPos?: (b64: string) => void };
  }
}

const KEY = "kiosk:install";

export function installId(): string {
  let id = store.get<string>(KEY);
  if (!id) {
    id = newKey();
    store.set(KEY, id);
  }
  return id;
}

function fromUserAgent(): Pick<ClientInfo, "model" | "os" | "browser"> {
  const ua = navigator.userAgent;
  const android = ua.match(/Android ([\d.]+);\s*([^;)]+)?/);
  const ios = ua.match(/(iPad|iPhone).*OS ([\d_]+)/);
  const os = android ? `Android ${android[1]}` : ios ? `iOS ${ios[2].replace(/_/g, ".")}` : /Windows NT/.test(ua) ? "Windows" : /Mac OS X/.test(ua) ? "macOS" : /Linux/.test(ua) ? "Linux" : undefined;
  const model = android?.[2]?.replace(/ Build.*/, "").trim() || ios?.[1] || undefined;
  const b = ua.match(/(Edg|SamsungBrowser|Firefox|Chrome|Version)\/([\d]+)/);
  const name = b ? { Edg: "Edge", SamsungBrowser: "Samsung Internet", Version: "Safari" }[b[1]] ?? b[1] : undefined;
  return { os, model: model === "K" ? undefined : model, browser: name ? `${name} ${b![2]}` : undefined };
}

export function clientInfo(): ClientInfo {
  const base: ClientInfo = {
    install_id: installId(),
    app: "web",
    ...fromUserAgent(),
    screen: `${Math.round(screen.width * devicePixelRatio)}x${Math.round(screen.height * devicePixelRatio)}`,
    page: location.pathname,
  };
  try {
    const native = window.KioskNative?.deviceInfo?.();
    if (native) return { ...base, app: "android", ...JSON.parse(native) };
  } catch {
    /* the web values are fine */
  }
  return base;
}

/** Ask the browser not to clear this site's storage (the setup lives there). */
export function keepStorage(): void {
  navigator.storage?.persist?.().catch(() => {});
}
