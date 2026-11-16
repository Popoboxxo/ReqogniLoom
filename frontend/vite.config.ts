import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";
import { resolve } from "path";
import {
  PWA_NAVIGATION_DENYLIST,
  PWA_PRECACHE_GLOBS,
} from "./src/config/pwa-config";

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [
    react(),
    // Plan M2: generate a Workbox service worker for the app shell only.
    // The manifest itself is static in public/ (E5), so `manifest: false`.
    VitePWA({
      strategies: "generateSW",
      registerType: "prompt",
      injectRegister: null,
      manifest: false,
      workbox: {
        globPatterns: [...PWA_PRECACHE_GLOBS],
        navigateFallback: "/index.html",
        navigateFallbackDenylist: PWA_NAVIGATION_DENYLIST,
        cleanupOutdatedCaches: true,
        runtimeCaching: [
          // Explicit network-only rule for authenticated surfaces. The
          // denylist above is the second line of defence for navigations.
          {
            // Inlined on purpose: Workbox serialises this predicate into
            // the generated worker, where imported names do not exist.
            urlPattern: ({ url }: { url: URL }) =>
              url.pathname.startsWith("/api/") || url.pathname.startsWith("/mcp/"),
            handler: "NetworkOnly",
          },
          {
            urlPattern: ({ url }: { url: URL }) => url.pathname.startsWith("/assets/"),
            handler: "CacheFirst",
            options: {
              cacheName: "reqlo-assets",
              expiration: { maxEntries: 100, maxAgeSeconds: 60 * 60 * 24 * 365 },
            },
          },
          {
            urlPattern: ({ url }: { url: URL }) =>
              url.pathname.startsWith("/icons/") || url.pathname === "/manifest.webmanifest",
            handler: "StaleWhileRevalidate",
            options: { cacheName: "reqlo-static", expiration: { maxEntries: 20 } },
          },
        ],
      },
    }),
  ],
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
    },
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    // Include test files (see TESTING_CONVENTIONS.md for layout rules).
    // `scripts/**/*.test.mjs` covers the Node-side analysis scripts that live
    // outside the `src` program (e.g. component-hotspot analysis, #598 S2).
    include: ["src/**/*.{test,spec}.{ts,tsx}", "scripts/**/*.test.mjs"],
    // #1117: writes a per-failure JSON artifact so a flaky failure can be named
    // and compared next run instead of just counted. Passed as a string path on
    // purpose: a TypeScript import here would pull this node-only module into
    // the browser build program, which has no node types, and it is excluded
    // from the build by tsconfig.build.json. Vitest resolves a string reporter
    // spec against the project root, which is stable for local and container
    // runs alike. The default reporter stays; this only adds a parallel sink.
    reporters: ["default", "./src/test/flaky-artifact-reporter.ts"],
    // Resolve stubs for packages that are installed in Docker but not locally
    alias: {
      // fabric@6 is installed via Docker/npm install — stub it for local unit tests
      fabric: resolve(__dirname, "./src/__mocks__/fabric.ts"),
      // M2: the PWA virtual module exists only in the Vite build; Vitest
      // gets a deterministic stub so components can be unit-tested.
      "virtual:pwa-register": resolve(__dirname, "./src/test/mocks/pwa-register.ts"),
    },
  },
});
