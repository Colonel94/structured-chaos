import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
// Fluent-inspired light theme (DESIGN.md §2, redesign 2026-08-24): the interface speaks in Segoe UI /
// system-sans — the Power Platform / Dynamics 365 voice — and only genuine MACHINE DATA (case ids,
// confidence %, timestamps, JSON) is set in a mono. IBM Plex Mono is self-hosted (Fontsource, Latin-basic,
// no CDN — works air-gapped/on-prem) for that machine voice; the Sans/Serif families were dropped with the
// dark "Instrument" direction.
import "@fontsource/ibm-plex-mono/latin-400.css";
import "@fontsource/ibm-plex-mono/latin-500.css";
import App from "./App";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
