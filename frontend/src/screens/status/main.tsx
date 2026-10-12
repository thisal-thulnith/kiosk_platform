import { createRoot } from "react-dom/client";
import "../../ui/theme.css";
import { Device } from "../../lib/device";
import { DeviceGate } from "../../ui/gate";
import { ToastProvider } from "../../ui/kit";
import { UnlessComingSoon } from "../app/ComingSoon";
import { StatusBoard } from "./StatusBoard";

const device = new Device("status");

createRoot(document.getElementById("root")!).render(
  <ToastProvider>
    <UnlessComingSoon type="status" title="Order status board" line="This screen will show which orders are being prepared and which are ready to collect.">
      <DeviceGate device={device}>{(me) => <StatusBoard device={device} me={me} />}</DeviceGate>
    </UnlessComingSoon>
  </ToastProvider>,
);
