/**
 * ARCH-L1-001 ReactFrontend — Application entry point.
 *
 * Initializes i18n (react-i18next, DE/EN — REQ-L1-016) and renders the
 * root App component into the DOM.
 */
import React, { StrictMode } from "react";
import ReactDOM from "react-dom/client";
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
