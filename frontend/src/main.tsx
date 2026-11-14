import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { AppProviders } from "./app/AppProviders";
import AppRoutes from "./app/routes";
import "./styles.css";
import "./design-system/tokens/components.css";

const root = document.getElementById("root");
if (!root) throw new Error("Root element not found");

createRoot(root).render(
  <StrictMode>
    <AppProviders>
      <AppRoutes />
    </AppProviders>
  </StrictMode>,
);
