import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The review SPA is the engine's first client, not its container (CLAUDE.md §4).
// Dev proxy: `/api/*` → the FastAPI engine on :8000, so the browser talks same-origin (no CORS to
// widen). In production the built SPA is served by the engine on the same origin, so the same paths
// resolve without any client change.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": { target: "http://localhost:8000", changeOrigin: true },
      "/health": { target: "http://localhost:8000", changeOrigin: true },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
  },
});
