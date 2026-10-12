import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// One page per screen, served by the API server (cloud or the restaurant's hub) under /screens/ui/.
const SCREENS = ["app", "try", "table", "wall", "pos", "waiter", "kds", "kiosk", "status", "owner", "setup", "platform", "menu"];
const here = (p: string) => new URL(p, import.meta.url).pathname;

export default defineConfig({
  base: "/static/",
  plugins: [react(), tailwindcss()],
  build: {
    outDir: here("../src/kiosk/web/ui"),
    emptyOutDir: true,
    rollupOptions: { input: Object.fromEntries(SCREENS.map((s) => [s, here(`./${s}/index.html`)])) },
  },
  server: { proxy: { "/v1": { target: "http://127.0.0.1:8000", ws: true }, "/media": "http://127.0.0.1:8000" } },
});
