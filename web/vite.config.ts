import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// During `npm run dev` the Vite server proxies /api to the backend. Point it at
// a locally-run backend (default) or the Pi by setting VITE_API_TARGET, e.g.
//   VITE_API_TARGET=http://[IP_RASPBERRY]:8080 npm run dev
const apiTarget = process.env.VITE_API_TARGET ?? "http://localhost:8080";

export default defineConfig({
  // Relative base so the build works when served from the backend at "/".
  base: "./",
  plugins: [react()],
  server: {
    proxy: {
      "/api": { target: apiTarget, changeOrigin: true },
    },
  },
});
