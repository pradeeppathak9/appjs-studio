import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The console calls the API directly (VITE_API_URL, see src/config.ts); the backend allows
// http://localhost:3000 through CORS, so the dev server keeps that port.
export default defineConfig({
  plugins: [react()],
  // The legacy pages import react-router-dom; react-router 7+ is the same package under one name.
  resolve: { alias: { "react-router-dom": "react-router" } },
  build: { chunkSizeWarningLimit: 1000 },
  server: { port: 3000, strictPort: true },
  preview: { port: 3000 },
});
