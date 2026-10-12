// Before a screen shows: it must be signed in (the restaurant's address + its screen code, once) and,
// for staff screens, someone must log in with their PIN. Network problems retry by themselves; only "device_not_set_up" forgets the setup.
import { AnimatePresence, motion, useAnimate } from "motion/react";
import { Delete, MonitorSmartphone, WifiOff } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { keepStorage } from "../lib/client";
import { Device, type SignedIn } from "../lib/device";
import { SignInFace, SignInForm, signInError, venueInAddress } from "../screens/app/SignIn";
import { LAUNCH_KEY, SCREEN_SLUG, screenAddress, showCodeInAddress } from "../lib/screens";
import { store } from "../lib/store";
import { ApiError } from "../lib/net";
import type { Me, Staff } from "../lib/types";
import { spring } from "./kit";
import { Avatar, Logo } from "./logo";
import type { Brand } from "../lib/brand";

// Offline shell: the screen files still open from cache if the server restarts or the network drops.
if ("serviceWorker" in navigator && location.protocol !== "file:") navigator.serviceWorker.register("/sw.js").catch(() => {});

function Centered({ children }: { children: ReactNode }) {
  return (
    <div className="relative flex min-h-full items-center justify-center overflow-hidden bg-canvas p-4 sm:p-6">
      <motion.div className="relative flex w-full justify-center" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={spring}>
        {children}
      </motion.div>
    </div>
  );
}

/** The restaurant's logo when this screen already knows it (remembered brand), else a plain mark. */
function Mark({ name = "Kiosk", url, size = 60 }: { name?: string; url?: string | null; size?: number }) {
  return <Logo url={url ?? store.get<Brand>("kiosk:brand")?.logo_url} name={name} size={size} className="mx-auto" />;
}

const Spinner = () => <span className="mx-auto block h-8 w-8 animate-spin rounded-full border-[3px] border-ink/10 border-t-accent" />;

/** Signed in, but the code belongs to another kind of screen: keep it for that screen and open it. */
function openOtherScreen(device: Device, res: SignedIn): boolean {
  if (res.device.type === device.page) return false;
  device.unpair();
  store.set(`kiosk:dev:${res.device.type}:${device.slot}`, { token: res.device_token, device: res.device });
  const url = screenAddress(res.device.type, device.slot, res.device.venue_code);
  store.set(LAUNCH_KEY, url);
  location.replace(url);
  return true;
}

/** No key yet (or signed out): the restaurant comes from the address, so only the screen code is needed. */
function SignInScreen({ device, note, error, onDone }: { device: Device; note?: string; error?: string; onDone: () => void }) {
  const venue = venueInAddress();
  return (
    <SignInFace title="Sign in this screen" sub={note || (venue ? "Type the screen code from the Setup console." : "Type the restaurant and the screen code.")}>
      <SignInForm
        venue={venue}
        initialError={error}
        signIn={(v, c) => device.signIn(v, c)}
        pair={(c) => device.pair(c)}
        onSignedIn={(res) => {
          if (!openOtherScreen(device, res)) onDone();
        }}
      />
    </SignInFace>
  );
}

export function PinPad({ device, title, roles, onDone, me }: { device: Device; title: string; roles: string[]; onDone: (s: Staff) => void; me?: Me | null }) {
  const [staff, setStaff] = useState<Staff[]>([]);
  const [who, setWho] = useState<Staff | null>(null);
  const [pin, setPin] = useState("");
  const [err, setErr] = useState("");
  const [dots, animateDots] = useAnimate();
  useEffect(() => {
    device.get<Staff[]>("/v1/staff").then((list) => {
      setStaff(list);
      setWho(list.find((s) => roles.includes(s.role)) ?? list[0] ?? null);
    });
  }, [device]);
  const submit = async (p = pin) => {
    if (!who) return;
    try {
      const res = await device.post<{ staff_token: string; staff: Staff }>("/v1/staff/pin-login", { staff_id: who.id, pin: p });
      device.setStaff(res.staff_token);
      onDone(res.staff);
    } catch (x) {
      setErr((x as Error).message);
      setPin("");
      if (dots.current) void animateDots(dots.current, { x: [0, -12, 10, -8, 6, 0] }, { duration: 0.4 });
    }
  };
  const press = (k: string) => (setErr(""), setPin((p) => (p + k).slice(0, 8)));
  useEffect(() => {
    const k = (e: KeyboardEvent) => {
      if (/^\d$/.test(e.key)) press(e.key);
      else if (e.key === "Backspace") setPin((p) => p.slice(0, -1));
      else if (e.key === "Enter") void submit();
    };
    document.addEventListener("keydown", k);
    return () => document.removeEventListener("keydown", k);
  });
  const count = Math.max(4, pin.length);
  return (
    <div className="flex min-h-full flex-col items-center justify-center bg-canvas px-4 py-6 [@media(max-height:560px)]:py-3">
      <motion.div className="flex w-full max-w-[400px] flex-col items-center [@media(max-height:560px)]:max-w-[760px] [@media(max-height:560px)]:flex-row [@media(max-height:560px)]:justify-center [@media(max-height:560px)]:gap-10" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={spring}>
        <div className="flex min-w-0 flex-col items-center [@media(max-height:560px)]:flex-1">
          <div className="flex items-center gap-3">
            <Logo url={me?.venue.brand?.logo_url ?? store.get<Brand>("kiosk:brand")?.logo_url} name={me?.venue.name ?? "Restaurant"} size={40} />
            <div className="min-w-0 text-left">
              <h1 className="truncate text-xl font-bold leading-tight tracking-tight">{title}</h1>
              {me ? <p className="truncate text-sm text-muted">{me.venue.name}</p> : null}
            </div>
          </div>

          {/* Who is logging in: a person icon and the name (never initials), like a phone's user switcher. */}
          <div className="mt-6 flex max-w-full gap-2 overflow-x-auto px-1 py-1 [scrollbar-width:none]">
            {staff.map((s) => {
              const on = who?.id === s.id;
              return (
                <button key={s.id} onClick={() => (setWho(s), setPin(""), setErr(""))} aria-pressed={on} className="relative flex w-[78px] shrink-0 flex-col items-center gap-1.5 rounded-2xl px-1 py-2.5 transition-colors">
                  {on ? <motion.span layoutId="pin-who" transition={spring} className="absolute inset-0 rounded-2xl bg-accent-soft" /> : null}
                  <Avatar size={48} className={`relative transition-colors ${on ? "bg-accent! text-white!" : "bg-surface! shadow-soft"}`} />
                  <span className={`relative w-full truncate text-center text-sm font-semibold ${on ? "text-accent" : "text-ink"}`}>{s.name}</span>
                  <span className="relative -mt-1.5 w-full truncate text-center text-xs capitalize text-muted">{s.role}</span>
                </button>
              );
            })}
          </div>

          <div ref={dots} className="mt-6 flex h-5 items-center justify-center gap-4 [@media(max-height:560px)]:mt-4" aria-label={`${pin.length} digits`}>
            {Array.from({ length: count }, (_, k) => (
              <motion.span key={k} animate={{ scale: k < pin.length ? 1.15 : 1 }} transition={spring} className={`h-3.5 w-3.5 rounded-full transition-colors ${k < pin.length ? "bg-ink" : err ? "bg-bad/30" : "bg-ink/15"}`} />
            ))}
          </div>
          <p className={`mt-2 h-5 text-center text-sm font-semibold text-bad ${err ? "" : "invisible"}`}>{err || "·"}</p>
        </div>

        {/* A phone's keypad: big round keys, OK in ink. */}
        <div className="mt-3 grid shrink-0 grid-cols-3 gap-x-6 gap-y-3.5 [@media(max-height:560px)]:mt-0 [@media(max-height:560px)]:gap-x-4 [@media(max-height:560px)]:gap-y-2">
          {["1", "2", "3", "4", "5", "6", "7", "8", "9", "⌫", "0", "OK"].map((k) => (
            <button
              key={k}
              aria-label={k === "⌫" ? "Delete" : undefined}
              onClick={() => (k === "⌫" ? setPin((p) => p.slice(0, -1)) : k === "OK" ? void submit() : press(k))}
              className={`grid h-[76px] w-[76px] place-items-center rounded-full transition active:scale-90 [@media(max-height:560px)]:h-14 [@media(max-height:560px)]:w-14 ${k === "OK" ? "bg-ink text-lg font-semibold text-surface hover:bg-ink/90" : k === "⌫" ? "text-muted hover:text-ink active:bg-ink/[.06]" : "bg-surface text-[30px] font-medium text-ink shadow-soft hover:bg-surface/70 active:bg-line [@media(max-height:560px)]:text-2xl"}`}
            >
              {k === "⌫" ? <Delete size={26} /> : k}
            </button>
          ))}
        </div>
      </motion.div>
    </div>
  );
}

/** Runs the setup / reconnect / staff-login steps, then renders the screen with `me`. */
export function DeviceGate({ device, staffRoles, staffTitle, children }: { device: Device; staffRoles?: string[]; staffTitle?: string; children: (me: Me, logout: () => void) => ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [state, setState] = useState<"loading" | "setup" | "retry" | "pin" | "ready">("loading");
  const [msg, setMsg] = useState("");
  const [note, setNote] = useState("");
  const [signInErr, setSignInErr] = useState("");
  const load = async (): Promise<void> => {
    // A link / QR carries ?code=<screen code> (the restaurant is in the address) or the old
    // ?pair=<6-digit code>: sign in at once, then drop it from the address.
    const url = new URL(location.href);
    const screenCode = url.searchParams.get("code");
    const old = url.searchParams.get("pair");
    const venue = venueInAddress();
    if (old || (screenCode && venue)) {
      url.searchParams.delete("pair");
      url.searchParams.delete("code");
      history.replaceState(null, "", url);
      try {
        const res = old ? await device.pair(old) : await device.signIn(venue!, screenCode!);
        if (openOtherScreen(device, res)) return;
      } catch (x) {
        setSignInErr(signInError(x));
      }
    }
    if (!device.token) return setState("setup");
    try {
      const m = await device.loadMe();
      setMe(m);
      // Next time the tablet starts, the launcher opens this screen by itself.
      store.set(LAUNCH_KEY, screenAddress(m.device.type, device.slot, m.venue.code));
      showCodeInAddress(m.venue.code, SCREEN_SLUG[m.device.type] ?? m.device.type); // /demo/pos
      keepStorage();
      setState(staffRoles && !m.staff ? "pin" : "ready");
    } catch (x) {
      const e = x as ApiError;
      if (e.code === "device_not_set_up") {
        // Signed in somewhere else, its code was reset, or the screen was removed.
        device.unpair();
        setNote("This screen was signed out. Type its screen code to sign in again.");
        return setState("setup");
      }
      if (e.status === 401 && device.staffToken) {
        device.setStaff(null);
        return load();
      }
      setMsg(e.message);
      setState("retry");
      setTimeout(load, 5000);
    }
  };
  useEffect(() => {
    void load();
  }, []);
  if (state === "setup") return <SignInScreen device={device} note={note} error={signInErr} onDone={() => (setNote(""), setSignInErr(""), void load())} />;
  if (state === "retry")
    return (
      <Centered>
        <div className="w-full max-w-sm text-center">
          <div className="rounded-3xl bg-surface p-8 shadow-soft">
            <span className="relative mx-auto grid h-16 w-16 place-items-center rounded-full bg-canvas text-ink">
              <span className="absolute inset-0 animate-ping rounded-full bg-accent/10" />
              <WifiOff size={26} className="relative" />
            </span>
            <h1 className="mt-6 text-[26px] font-bold tracking-tight">Reconnecting…</h1>
            <p className="mx-auto mt-1 max-w-xs text-muted">This screen continues by itself.</p>
            {msg ? <p className="mt-6 border-t border-line pt-4 text-sm text-muted">{msg}</p> : null}
          </div>
        </div>
      </Centered>
    );
  if (state === "pin") return <PinPad device={device} me={me} title={staffTitle ?? "Staff login"} roles={staffRoles ?? []} onDone={() => load()} />;
  if (state !== "ready" || !me)
    return (
      <Centered>
        <div className="flex flex-col items-center gap-5" aria-busy="true">
          <motion.span animate={{ scale: [1, 1.06, 1], opacity: [1, 0.8, 1] }} transition={{ duration: 1.6, repeat: Infinity, ease: "easeInOut" }}>
            <Mark />
          </motion.span>
          <Spinner />
        </div>
      </Centered>
    );
  return (
    <>
      {children(me, () => (device.setStaff(null), location.reload()))}
      <Identify name={me.device.name} venue={me.venue.name} />
    </>
  );
}

/** "Identify" from the Setup console: this screen shows its name in big letters for 8 seconds. */
function Identify({ name, venue }: { name: string; venue: string }) {
  const [on, setOn] = useState(false);
  useEffect(() => {
    let t: ReturnType<typeof setTimeout>;
    const show = () => (setOn(true), clearTimeout(t), (t = setTimeout(() => setOn(false), 8000)));
    window.addEventListener("kiosk:identify", show);
    return () => (window.removeEventListener("kiosk:identify", show), clearTimeout(t));
  }, []);
  return (
    <AnimatePresence>
      {on ? (
        <motion.div key="id" data-identify className="fixed inset-0 z-[100] grid place-items-center bg-[#18191a] p-8 text-center text-[#e4e6eb]" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.25 }} onClick={() => setOn(false)}>
          <motion.div className="flex flex-col items-center" initial={{ scale: 0.85, y: 20 }} animate={{ scale: 1, y: 0 }} transition={spring}>
            <span className="inline-flex items-center gap-2 rounded-full bg-[#2d88ff]/20 px-5 py-2 text-xl font-semibold text-[#6cb1ff]">
              <MonitorSmartphone size={22} /> This screen
            </span>
            <div className="mt-8 text-[9vw] font-black leading-none tracking-tight">{name}</div>
            <div className="mt-6 text-3xl font-medium text-[#b0b3b8]">{venue}</div>
          </motion.div>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}
