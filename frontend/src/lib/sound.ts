let ctx: AudioContext | null = null;
export function unlockSound(): void {
  try {
    ctx ??= new AudioContext();
    if (ctx.state === "suspended") void ctx.resume();
  } catch {
    /* no audio */
  }
}
// Short tones: calls [990,740,990], new order [740,990], ready [880,1320], problem [440,330].
export function chime(notes: number[] = [880, 1320]): void {
  try {
    ctx ??= new AudioContext();
    let t = ctx.currentTime;
    for (const f of notes) {
      const o = ctx.createOscillator();
      const g = ctx.createGain();
      o.frequency.value = f;
      g.gain.setValueAtTime(0.18, t);
      g.gain.exponentialRampToValueAtTime(0.001, t + 0.22);
      o.connect(g).connect(ctx.destination);
      o.start(t);
      o.stop(t + 0.24);
      t += 0.18;
    }
  } catch {
    /* no audio */
  }
}
