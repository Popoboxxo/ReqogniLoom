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
    allowedHosts: process.env.VITE_ALLOWED_HOSTS === 'true' ? true : (process.env.VITE_ALLOWED_HOSTS ? process.env.VITE_ALLOWED_HOSTS.split(',') : true),
    proxy: {
      // Proxy API requests to Django backend during development.
      // Defaults to the Docker Compose service hostname; override via
      // VITE_API_BASE_URL when "backend" isn't resolvable (e.g. bare-process
      // CI runners where Django listens on localhost).
      "/api": {
        target: process.env.VITE_API_BASE_URL || "http://backend:8000",
        changeOrigin: true,
      },
      "/mcp": {
        target: process.env.VITE_API_BASE_URL || "http://backend:8000",
        changeOrigin: true,
      },
      // bluepencil review-layer sidecar (issue #972). Same-origin in dev, so no
      // CORS is needed. The sidecar's base path is /bluepencil/api — the full
      // path is forwarded unchanged (no rewrite). Override the target via
      // BLUEPENCIL_URL when "bluepencil" isn't resolvable.
      "/bluepencil/api": {
        target: process.env.BLUEPENCIL_URL || "http://bluepencil:8787",
        changeOrigin: true,
      },
    },
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    // Include test files (see TESTING_CONVENTIONS.md for layout rules)
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
    // Resolve stubs for packages that are installed in Docker but not locally
    alias: {
      // fabric@6 is installed via Docker/npm install — stub it for local unit tests
      fabric: resolve(__dirname, "./src/__mocks__/fabric.ts"),
    },
  },
});
