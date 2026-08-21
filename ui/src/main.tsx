import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
// IBM Plex, self-hosted woff2 (Fontsource), Latin-basic subset only — no CDN, works air-gapped/on-prem.
// The type system carries meaning (DESIGN.md §2): Sans = the interface, Mono = the machine, Serif = the
// human's verbatim words. Only the weights the design uses are loaded.
import "@fontsource/ibm-plex-sans/latin-400.css";
import "@fontsource/ibm-plex-sans/latin-500.css";
import "@fontsource/ibm-plex-sans/latin-600.css";
import "@fontsource/ibm-plex-mono/latin-400.css";
import "@fontsource/ibm-plex-mono/latin-500.css";
import "@fontsource/ibm-plex-serif/latin-400.css";
import "@fontsource/ibm-plex-serif/latin-400-italic.css";
import App from "./App";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
