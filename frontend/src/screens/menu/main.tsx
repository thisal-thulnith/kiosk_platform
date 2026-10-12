import { createRoot } from "react-dom/client";
import "../../ui/theme.css";
import { AdminGate } from "../../ui/adminGate";
import { ToastProvider } from "../../ui/kit";
import { MenuEditor } from "./MenuEditor";

// The restaurant edits its own menu; our installers open it from the Setup console (?as=installer&venue=<id>).
const kind = new URLSearchParams(location.search).get("as") === "installer" ? "installer" : "admin";

createRoot(document.getElementById("root")!).render(
  <ToastProvider>
    <AdminGate kind={kind} title="Menu editor">
      {(admin) => <MenuEditor admin={admin} />}
    </AdminGate>
  </ToastProvider>,
);
