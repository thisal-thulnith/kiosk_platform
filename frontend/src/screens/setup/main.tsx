import { createRoot } from "react-dom/client";
import "../../ui/theme.css";
import { AdminGate } from "../../ui/adminGate";
import { ToastProvider } from "../../ui/kit";
import { Setup } from "./Setup";

// Installation team only (platform login), never the restaurant.
createRoot(document.getElementById("root")!).render(
  <ToastProvider>
    <AdminGate kind="installer" title="Setup console">
      {(admin) => <Setup admin={admin} />}
    </AdminGate>
  </ToastProvider>,
);
