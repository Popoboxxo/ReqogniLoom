import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "path";

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 3000,
    proxy: {
      // Proxy API requests to Django backend during development
      "/api": {
        target: "http://backend:8000",
        changeOrigin: true,
      },
      "/mcp": {
        target: "http://backend:8000",
        changeOrigin: true,
      },
    },
  },
});
