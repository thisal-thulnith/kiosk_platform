import { useEffect, useRef, useState } from "react";
import type { Device } from "../lib/device";
import { connectLive, type LiveEvent, type LiveStatus } from "../lib/live";
import { net } from "../lib/net";

/** Live events for this screen; the handler always sees the latest state (ref). */
export function useLive(device: Device, handler: (e: LiveEvent) => void): { status: LiveStatus; via: string } {
  const ref = useRef(handler);
  ref.current = handler;
  const [status, setStatus] = useState<LiveStatus>("connecting");
  const [via, setVia] = useState<string>(net.kind());
  useEffect(() => {
    const off = net.onChange((k) => setVia(k));
    const close = connectLive(device, (e) => ref.current(e), setStatus);
    return () => {
      off();
      close();
    };
  }, [device]);
  return { status, via };
}

/** Lock a shared staff screen after `minutes` without a touch. */
export function useIdleLock(minutes: number, onLock: () => void): void {
  useEffect(() => {
    let t: ReturnType<typeof setTimeout>;
    const arm = () => {
      clearTimeout(t);
      t = setTimeout(onLock, minutes * 60 * 1000);
    };
    arm();
    ["pointerdown", "keydown"].forEach((ev) => document.addEventListener(ev, arm, { passive: true }));
    return () => {
      clearTimeout(t);
      ["pointerdown", "keydown"].forEach((ev) => document.removeEventListener(ev, arm));
    };
  }, [minutes, onLock]);
}
