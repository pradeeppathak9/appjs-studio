import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// In development the browser talks to Vite, which forwards /v1 to AppJs Studio's API (as nginx does
// in production), so the app and the API share one origin: no CORS.
const studio = process.env.STUDIO_API ?? "http://localhost:8010";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5180,
    proxy: { "/v1": { target: studio, changeOrigin: false } },
  },
  test: { environment: "jsdom" },
});
