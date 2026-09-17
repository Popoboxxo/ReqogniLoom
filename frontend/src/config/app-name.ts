/**
 * ARCH-L1-001 ReactFrontend — central product display name.
 *
 * Single source of truth for the product's display name shown in the UI
 * (page title, login screen, sidebar branding, i18n interpolation, ...).
 *
 * Configurable via the `VITE_APP_NAME` build-time environment variable
 * (see `frontend/.env` or Docker build args). Falls back to "ReqogniLoom"
 * when unset, so a future rename only requires changing this default or
 * setting the env var — no more hunting for hardcoded strings.
 */
export const APP_NAME: string = import.meta.env.VITE_APP_NAME ?? "ReqogniLoom";
