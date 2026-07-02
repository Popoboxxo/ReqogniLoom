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
    port: 5173,
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
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    // Include test files
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
    // Resolve stubs for packages that are installed in Docker but not locally
    alias: {
      // fabric@6 is installed via Docker/npm install — stub it for local unit tests
      fabric: resolve(__dirname, "./src/__mocks__/fabric.ts"),
    },
  },
});
