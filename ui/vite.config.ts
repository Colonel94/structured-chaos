import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The review SPA is the engine's first client, not its container (CLAUDE.md §4).
export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
  },
});
