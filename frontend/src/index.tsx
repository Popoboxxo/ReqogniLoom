/**
 * ARCH-L1-001 ReactFrontend — Application entry point.
 *
 * Initializes i18n (react-i18next, DE/EN — REQ-L1-016) and renders the
 * root App component into the DOM.
 */
import React, { StrictMode } from "react";
import ReactDOM from "react-dom/client";
// Self-hosted font files (replaces the Google Fonts @import previously in
// global.css, which was blocked in restricted/air-gapped network
// environments — see issue #234). Only the weights actually used by the
// design tokens are imported.
//
// IBM Plex family (UI concept ch. 9): Sans for body/headings, Mono for
// identifiers/diffs/JSON, Sans Condensed for badges and table headers.
import "@fontsource/ibm-plex-sans/400.css";
import "@fontsource/ibm-plex-sans/500.css";
import "@fontsource/ibm-plex-sans/600.css";
import "@fontsource/ibm-plex-mono/400.css";
import "@fontsource/ibm-plex-sans-condensed/500.css";
// Inter is kept at the two weights CanvasEditor still renders directly onto
// the HTML canvas (ch. 12 diagram nodes are out of scope for this task).
import "@fontsource/inter/400.css";
import "@fontsource/inter/600.css";
import "./styles/tokens.css";
import "./styles/global.css";
import "./i18n/index";
import { App } from "./App";
import { APP_NAME } from "./config/app-name";

// Force React to be globally available to prevent esbuild from stripping the import
// and to satisfy any old JSX transforms or third-party libraries.
(window as unknown as { React: typeof React }).React = React;

// Override the static fallback title (index.html) with the configured product name.
document.title = APP_NAME;

const rootElement = document.getElementById("root");
if (!rootElement) {
  throw new Error("Root element #root not found in DOM.");
}

ReactDOM.createRoot(rootElement).render(
  <StrictMode>
    <App />
  </StrictMode>
);
