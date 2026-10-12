import { createRoot } from "react-dom/client";
import "../../ui/theme.css";
import { AdminGate } from "../../ui/adminGate";
import { ToastProvider } from "../../ui/kit";
import { Owner } from "./Owner";

// The owner logs in with the restaurant's email; our support team can open it with ?as=installer.
const kind = new URLSearchParams(location.search).get("as") === "installer" ? "installer" : "admin";

createRoot(document.getElementById("root")!).render(
  <ToastProvider>
    <AdminGate kind={kind} title="Owner app">
      {(admin) => <Owner admin={admin} />}
    </AdminGate>
  </ToastProvider>,
);
