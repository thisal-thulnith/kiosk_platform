import { createRoot } from "react-dom/client";
import "../../ui/theme.css";
import { Device } from "../../lib/device";
import { DeviceGate } from "../../ui/gate";
import { ToastProvider } from "../../ui/kit";
import { Kds } from "./Kds";

const device = new Device("kds");

createRoot(document.getElementById("root")!).render(
  <ToastProvider>
    <DeviceGate device={device}>{(me) => <Kds device={device} me={me} />}</DeviceGate>
  </ToastProvider>,
);
