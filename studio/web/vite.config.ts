import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The API runs on localhost:${API_PORT} (docker compose publishes 8010).
// changeOrigin must stay false: the API checks that Origin matches Host on cookie-authenticated writes.
const api = `http://localhost:${process.env.API_PORT ?? "8010"}`;

export default defineConfig({
  plugins: [react()],
  // One bundle is fine for an internal console (Mantine is most of it).
  build: { chunkSizeWarningLimit: 1000 },
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      "/v1": { target: api, changeOrigin: false },
      "/healthz": { target: api, changeOrigin: false },
    },
  },
  preview: {
    port: 4173,
    proxy: {
      "/v1": { target: api, changeOrigin: false },
      "/healthz": { target: api, changeOrigin: false },
    },
  },
});
