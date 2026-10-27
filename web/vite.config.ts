import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The SPA fetches relative /api/* paths; in dev Vite proxies them to the FastAPI
// server on :8000, so there is no CORS hop and prod can serve both from one origin.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
});
