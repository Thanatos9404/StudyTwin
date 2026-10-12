import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// Dev: `npm run dev` proxies the FastAPI backend on :8765. Build output is served by FastAPI at "/".
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5391,
    proxy: { "/api": "http://127.0.0.1:8765", "/media": "http://127.0.0.1:8765" },
  },
  build: { outDir: "dist", chunkSizeWarningLimit: 1200 },
});
