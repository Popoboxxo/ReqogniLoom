/**
 * ARCH-L1-001 ReactFrontend — Application entry point.
 *
 * Initializes i18n (react-i18next, DE/EN — REQ-L1-016) and renders the
 * root App component into the DOM.
 */
import ReactDOM from "react-dom/client";
import "./styles/tokens.css";
import "./styles/global.css";
import "./i18n/index";
import { App } from "./App";

const rootElement = document.getElementById("root");
if (!rootElement) {
  throw new Error("Root element #root not found in DOM.");
}

ReactDOM.createRoot(rootElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
