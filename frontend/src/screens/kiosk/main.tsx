import { createRoot } from "react-dom/client";
import "../../ui/theme.css";
import { Device } from "../../lib/device";
import { DeviceGate } from "../../ui/gate";
import { ToastProvider } from "../../ui/kit";
import { UnlessComingSoon } from "../app/ComingSoon";
import { Kiosk } from "./Kiosk";

const device = new Device("kiosk");

createRoot(document.getElementById("root")!).render(
  <ToastProvider>
    <UnlessComingSoon type="kiosk" title="Self-order kiosk" line="Guests will order and pay here by themselves. Until then, orders go through the staff and table screens.">
      <DeviceGate device={device}>{(me) => <Kiosk device={device} me={me} />}</DeviceGate>
    </UnlessComingSoon>
  </ToastProvider>,
);
