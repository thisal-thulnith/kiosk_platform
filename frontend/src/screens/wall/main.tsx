// Test wall: several set-up screens side by side in one window (made by the Setup console's
// "Create 4 test screens").
import { ExternalLink } from "lucide-react";
import { createRoot } from "react-dom/client";
import "../../ui/theme.css";
import { codeInAddress, consoleUrl } from "../../lib/screens";
import { store } from "../../lib/store";

const panes = store.get<{ label: string; url: string }[]>("kiosk:wall") ?? [];

createRoot(document.getElementById("root")!).render(
  <div className="flex h-full flex-col bg-black">
    <header className="flex flex-wrap items-center gap-3 px-4 py-2.5 text-white">
      <strong>Test wall</strong>
      <span className="text-sm text-white/60">Order on the kiosk, watch the kitchen and the board.</span>
      <span className="flex-1" />
      <a className="text-sm font-bold text-white hover:underline" href={consoleUrl("setup", codeInAddress())} target="_blank" rel="noreferrer">
        Setup console
      </a>
      <a className="text-sm font-bold text-white hover:underline" href={consoleUrl("owner", codeInAddress())} target="_blank" rel="noreferrer">
        Owner app
      </a>
    </header>
    {panes.length ? (
      <div className="grid flex-1 grid-cols-1 gap-2 p-2 md:grid-cols-2 md:grid-rows-2">
        {panes.map((p) => (
          <div key={p.url} className="flex min-h-[70vh] flex-col overflow-hidden rounded-xl bg-[#141414] ring-1 ring-white/10 md:min-h-0">
            <div className="flex justify-between px-3 py-1.5 text-xs font-semibold text-white/60">
              <span>{p.label}</span>
              <a href={p.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-white/80 hover:text-white">
                Open <ExternalLink size={12} />
              </a>
            </div>
            <iframe src={p.url} title={p.label} allow="autoplay" className="w-full flex-1 border-0 bg-canvas" />
          </div>
        ))}
      </div>
    ) : (
      <p className="p-8 text-white">No test screens yet. Open the Setup console and press “Create 4 test screens”.</p>
    )}
  </div>,
);
