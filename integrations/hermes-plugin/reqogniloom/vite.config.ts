import { defineConfig } from "vite";
import { resolve } from "path";

const __dirname = import.meta.dirname;

// Issue #599: the Hermes desktop app now loads plugins as a single ESM file
// (`dist/plugin.js`) that may only import `@hermes/plugin-sdk`, `react` and
// `react/jsx-runtime` -- no IIFE, no `window.__hermesPlugins` global
// registration footer (that was the old, no-longer-loadable contract).
export default defineConfig({
  build: {
    lib: {
      entry: resolve(__dirname, "src/activate.ts"),
      formats: ["es"],
      fileName: () => "plugin.js",
    },
    rollupOptions: {
      // react/jsx-runtime must be external too, not just react -- see
      // scripts/verify-build.mjs's module docstring for the incident this
      // guards against (an inlined CJS jsx-runtime shim reading
      // `process.env` at load time, which has no polyfill in the plugin
      // host and threw before activate() ever ran).
      external: ["@hermes/plugin-sdk", "react", "react/jsx-runtime"],
    },
    outDir: "dist",
    emptyOutDir: true,
    minify: false,
  },
});
