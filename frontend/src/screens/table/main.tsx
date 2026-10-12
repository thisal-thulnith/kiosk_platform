// The table screen in a browser (demos, or a restaurant without the Android table app yet). The
// Android app follows the same flow natively (docs/ANDROID_APP_GUIDE.md, Part D).
import { createRoot } from "react-dom/client";
import "../../ui/theme.css";
import { Device } from "../../lib/device";
import { DeviceGate } from "../../ui/gate";
import { ToastProvider } from "../../ui/kit";
import { Table } from "./Table";

const device = new Device("table");

createRoot(document.getElementById("root")!).render(
  <ToastProvider>
    <DeviceGate device={device}>{(me) => <Table device={device} me={me} />}</DeviceGate>
  </ToastProvider>,
);
