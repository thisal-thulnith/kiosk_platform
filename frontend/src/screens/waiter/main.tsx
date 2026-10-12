import { createRoot } from "react-dom/client";
import "../../ui/theme.css";
import { Device } from "../../lib/device";
import { DeviceGate } from "../../ui/gate";
import { ToastProvider } from "../../ui/kit";
import { Waiter } from "./Waiter";

const device = new Device("waiter");

createRoot(document.getElementById("root")!).render(
  <ToastProvider>
    <DeviceGate device={device} staffRoles={["waiter", "manager"]} staffTitle="Waiter login">
      {(me, logout) => <Waiter device={device} me={me} logout={logout} />}
    </DeviceGate>
  </ToastProvider>,
);
