// Platform console (our team): create restaurants with a package, see all of them, price list, quotes.
import { createRoot } from "react-dom/client";
import "../../ui/theme.css";
import { AdminGate } from "../../ui/adminGate";
import { applyBrand, DEFAULT_BRAND } from "../../lib/brand";
import { ToastProvider } from "../../ui/kit";
import { Platform } from "./Platform";

// Our own console: always our colours, never the last restaurant opened on this computer.
applyBrand(DEFAULT_BRAND, false);

createRoot(document.getElementById("root")!).render(
  <ToastProvider>
    <AdminGate kind="installer" title="Platform console" needVenue={false}>
      {(admin) => <Platform admin={admin} />}
    </AdminGate>
  </ToastProvider>,
);
