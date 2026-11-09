import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import MarketingApp from "./features/marketing/MarketingApp";
import "./styles.css";

const siteRole = (import.meta.env.VITE_SITE_ROLE || "app").trim().toLowerCase();
const RootApp = siteRole === "marketing" ? MarketingApp : App;

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <RootApp />
  </StrictMode>,
);
