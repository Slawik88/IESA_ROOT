import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { resolve } from "path";

// Билд → ../PredvestnikBot/web (статика, которую отдаёт FastAPI)
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": resolve(__dirname, "src") },
  },
  build: {
    outDir: resolve(__dirname, "..", "PredvestnikBot", "web"),
    emptyOutDir: true,
  },
  server: {
    // Прокси API-запросов на бэкенд при локальной разработке
    proxy: {
      "/api": {
        target: "http://localhost:8081",
        changeOrigin: true,
      },
    },
  },
});
