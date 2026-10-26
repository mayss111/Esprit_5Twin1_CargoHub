import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const cibleApi = process.env.VITE_PROXY_TARGET || "http://127.0.0.1:8000";

// Le SPA appelle l'API Django via ce proxy (évite les erreurs CORS en local).
export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    proxy: {
      "/api": { target: cibleApi, changeOrigin: true },
      "/media": { target: cibleApi, changeOrigin: true },
    },
  },
});
