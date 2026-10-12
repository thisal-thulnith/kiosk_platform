// Small JSON storage helpers. Storage can be missing or full (private mode, kiosk browsers).
export const store = {
  get<T = any>(key: string, area: Storage = localStorage): T | null {
    try {
      const v = area.getItem(key);
      return v ? (JSON.parse(v) as T) : null;
    } catch {
      return null;
    }
  },
  set(key: string, value: unknown, area: Storage = localStorage): void {
    try {
      if (value === null || value === undefined) area.removeItem(key);
      else area.setItem(key, JSON.stringify(value));
    } catch {
      /* ignore */
    }
  },
};
