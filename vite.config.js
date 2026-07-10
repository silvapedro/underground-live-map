import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Vite root is src/ so index.html there is the entry point.
// The existing repo-root index.html (Leaflet map) is unaffected.
export default defineConfig({
  root: "src",
  plugins: [react()],
  build: {
    outDir: "../dist",
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    proxy: {
      // Forward /api/* to the FastAPI backend during development.
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
