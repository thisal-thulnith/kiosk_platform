// The tablet's start page (installed app / kiosk browser home) and a restaurant's own address (/demo).
// First time: sign in with the screen code from the Setup console (at / also the restaurant), or
// scan its QR (/demo?code=K7MQ-4XPA-2R). Every time after - restarts, power cuts, updates - it opens
// that screen by itself. Also takes over a setup moved here from the cloud address (#move=), and the
// old 6-digit setup links (?pair=123456).
import { AnimatePresence, motion } from "motion/react";
import { ChefHat, ChevronDown, ChevronRight, Monitor, Smartphone, Store, Tablet, Tv } from "lucide-react";
import { useEffect, useState } from "react";
import { clientInfo, keepStorage } from "../../lib/client";
import { signInRequest, type SignedIn } from "../../lib/device";
import { request } from "../../lib/net";
import { LAUNCH_KEY, SCREEN_NAME, SCREEN_URL, screenAddress } from "../../lib/screens";
import { store } from "../../lib/store";
import { Button } from "../../ui/kit";
import { Logo } from "../../ui/logo";
import { SignInFace, SignInForm, signInError, venueInAddress } from "./SignIn";

type SetUp = { type: string; slot: string; name: string; url: string; venue: string | null };

// Storage page per device type (same keys as every screen uses: kiosk:dev:<page>:<slot>).
const PAGE: Record<string, string> = { cashier: "cashier", waiter: "waiter", kds: "kds", kiosk: "kiosk", status: "status", table: "table", board: "board" };

function setUpHere(): SetUp[] {
  const out: SetUp[] = [];
  try {
    for (let i = 0; i < localStorage.length; i++) {
      const k = localStorage.key(i) ?? "";
      const m = k.match(/^kiosk:dev:([a-z]+):([^:]+)$/);
      const v = m ? store.get<{ token?: string; device?: { type?: string; name?: string; venue_code?: string } }>(k) : null;
      if (!m || !v?.token) continue;
      const type = v.device?.type ?? m[1];
      const venue = v.device?.venue_code?.toLowerCase() ?? null;
      out.push({ type, slot: m[2], name: v.device?.name ?? SCREEN_NAME[type] ?? type, url: screenAddress(type, m[2], venue), venue });
    }
  } catch {
    /* no storage: show the sign-in */
  }
  return out;
}

/** Keep the device's key where its screen looks for it, and open that screen next time by itself. */
function remember(res: SignedIn, slot = "main"): string {
  store.set(`kiosk:dev:${PAGE[res.device.type] ?? res.device.type}:${slot}`, { token: res.device_token, device: res.device });
  const url = screenAddress(res.device.type, slot, res.device.venue_code);
  store.set(LAUNCH_KEY, url);
  keepStorage();
  return url;
}

const pairRequest = (code: string) => request<SignedIn>("POST", "/v1/devices/pair", { body: { code, client: clientInfo() } });

export function Launcher() {
  const params = new URLSearchParams(location.search);
  // /demo (the restaurant's own address): only the screen code is needed. /: the restaurant too.
  const venue = venueInAddress();
  const [mode, setMode] = useState<"busy" | "signin" | "choose">("busy");
  const [err, setErr] = useState("");
  const [code, setCode] = useState("");
  const [more, setMore] = useState(false);
  const list = setUpHere();
  const clean = () => history.replaceState(null, "", location.pathname);
  const open = (res: SignedIn) => location.replace(remember(res));

  /** A code from the address (QR / link): sign in at once; if it fails, show the form with the error. */
  const auto = async (run: () => Promise<SignedIn>, typed = "") => {
    try {
      open(await run());
    } catch (e) {
      clean();
      setCode(typed);
      setErr(signInError(e));
      setMode("signin");
    }
  };

  useEffect(() => {
    // 1. Moved here from the cloud address (the restaurant's hub runs the screens on its network).
    const move = location.hash.match(/^#move=(.+)$/)?.[1];
    if (move) {
      try {
        const m = JSON.parse(atob(decodeURIComponent(move))) as SignedIn & { slot?: string };
        clean();
        return location.replace(remember(m, m.slot));
      } catch {
        /* fall through */
      }
    }
    // 2. Scanned the Setup console's QR: /demo?code=K7MQ-4XPA-2R (or an old 6-digit link: ?pair=).
    const screenCode = params.get("code");
    if (screenCode && venue) return void auto(() => signInRequest(venue, screenCode), screenCode);
    const old = params.get("pair");
    if (old) return void auto(() => pairRequest(old));
    if (screenCode) {
      // A code without the restaurant (opened at /): ask for the restaurant, keep the code.
      clean();
      setCode(screenCode);
      return setMode("signin");
    }
    if (params.has("choose")) return setMode("choose");
    // 3. Already signed in: open it again by itself (at /demo only this restaurant's screens).
    const here = venue ? list.filter((s) => !s.venue || s.venue === venue) : list;
    const last = store.get<string>(LAUNCH_KEY);
    const lastUrl = last ? new URL(last, location.origin).pathname + new URL(last, location.origin).search : null;
    const match = here.find((s) => s.url === lastUrl) ?? (here.length === 1 ? here[0] : null);
    if (match) return location.replace(match.url);
    setMode(here.length ? "choose" : "signin");
  }, []);

  if (mode === "busy") return <Splash />;
  if (mode === "signin")
    return (
      <SignInFace title="Sign in this screen" sub={venue ? "Type the screen code from the Setup console." : "Type the restaurant and the screen code."}>
        <SignInForm venue={venue} initialCode={code} initialError={err} signIn={signInRequest} pair={pairRequest} onSignedIn={open} />
        {list.length ? (
          <Button variant="ghost" size="sm" className="mx-auto mt-4 flex" onClick={() => setMode("choose")}>
            Screens already signed in here <ChevronRight size={16} />
          </Button>
        ) : null}
      </SignInFace>
    );
  return (
    <SignInFace title="Which screen?" sub="Signed in on this tablet" hint={false}>
      {list.length ? (
        <div className="-mx-2 flex flex-col">
          {list.map((s) => {
            const Icon = ICON[s.type] ?? Monitor;
            return (
              <a key={`${s.type}:${s.slot}`} href={s.url} onClick={() => store.set(LAUNCH_KEY, s.url)} className="flex items-center gap-3.5 rounded-xl px-2 py-3 transition hover:bg-canvas active:scale-[.99]">
                <span className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-canvas text-ink">
                  <Icon size={20} />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-semibold">{s.name}</span>
                  <span className="block text-sm text-muted">
                    {SCREEN_NAME[s.type] ?? s.type}
                    {s.venue ? ` · /${s.venue}` : ""}
                  </span>
                </span>
                <ChevronRight size={18} className="text-muted" />
              </a>
            );
          })}
        </div>
      ) : null}
      <Button variant={list.length ? "soft" : "primary"} className="mt-5 w-full" size="lg" onClick={() => (setErr(""), setMode("signin"))}>
        Sign in another screen
      </Button>
      <button className="mx-auto mt-4 flex items-center gap-1 text-sm font-semibold text-muted hover:text-ink" onClick={() => setMore((m) => !m)}>
        More <ChevronDown size={16} className={`transition ${more ? "rotate-180" : ""}`} />
      </button>
      <AnimatePresence initial={false}>
        {more ? (
          <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }} className="overflow-hidden">
            <p className="mt-5 text-xs font-semibold uppercase tracking-wider text-muted">Open a screen page directly (testing)</p>
            <div className="mt-2 grid grid-cols-2 gap-2">
              {Object.entries(SCREEN_URL)
                .filter(([t]) => t !== "board")
                .map(([t, url]) => (
                  <a key={t} href={url} className="rounded-xl bg-canvas p-3 text-center text-sm font-semibold transition hover:bg-line">
                    {SCREEN_NAME[t]}
                  </a>
                ))}
            </div>
            <div className="mt-5 flex flex-wrap justify-center gap-x-5 gap-y-1 border-t border-line pt-4 text-sm font-semibold text-accent">
              <a className="hover:underline" href="/owner">Owner app</a>
              <a className="hover:underline" href="/menu">Menu editor</a>
              <a className="hover:underline" href="/setup">Setup console</a>
              <a className="hover:underline" href="/platform">Platform console</a>
            </div>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </SignInFace>
  );
}

const ICON: Record<string, typeof Monitor> = { cashier: Store, waiter: Smartphone, kds: ChefHat, kiosk: Monitor, status: Tv, table: Tablet, board: Tv };

const Splash = () => (
  <div className="grid min-h-full place-items-center bg-canvas" aria-busy="true">
    <motion.span animate={{ scale: [1, 1.06, 1], opacity: [1, 0.75, 1] }} transition={{ duration: 1.6, repeat: Infinity, ease: "easeInOut" }}>
      <Logo name="Kiosk" size={64} />
    </motion.span>
  </div>
);
