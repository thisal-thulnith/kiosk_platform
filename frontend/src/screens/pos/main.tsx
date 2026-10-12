import { createRoot } from "react-dom/client";
import "../../ui/theme.css";
import { Device } from "../../lib/device";
import { DeviceGate } from "../../ui/gate";
import { ToastProvider } from "../../ui/kit";
import { Pos } from "./Pos";

const device = new Device("cashier"); // same setup as the older cashier screen

createRoot(document.getElementById("root")!).render(
  <ToastProvider>
    <DeviceGate device={device} staffRoles={["cashier", "manager", "owner"]} staffTitle="POS login">
      {(me, logout) => <Pos device={device} me={me} logout={logout} />}
    </DeviceGate>
  </ToastProvider>,
);
