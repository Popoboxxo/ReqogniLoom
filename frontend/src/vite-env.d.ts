/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Product display name shown in the UI (see src/config/app-name.ts). */
  readonly VITE_APP_NAME?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
