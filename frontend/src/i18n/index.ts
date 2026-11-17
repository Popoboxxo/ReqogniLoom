/**
 * ARCH-L1-001 ReactFrontend — i18n initialization.
 *
 * Configures react-i18next with DE/EN language resources (REQ-L1-016).
 * Default language: browser language, fallback to English.
 *
 * TODO(COMP-RF-001): Extend translation keys as features are implemented.
 *   Each missing key in production is a build error (lint rule per ARCH-L1-002).
 */
import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import en from "./locales/en.json";
import de from "./locales/de.json";

/** Shape of the dev-only i18next options below (subset of `InitOptions`). */
export interface MissingKeyDiagnostics {
  saveMissing?: boolean;
  missingKeyHandler?: (
    lngs: readonly string[],
    _ns: string,
    key: string
  ) => void;
}

/**
 * FE-005: build the missing-key diagnostics options from an explicit flag.
 *
 * i18next consults `missingKeyHandler` only when `saveMissing` is enabled, so
 * both options are gated together. Kept as a pure factory so the dev/prod
 * branches are testable — Vite inlines `import.meta.env.DEV` at transform time,
 * so a test cannot flip that flag at runtime. The known 19/1223 ratchet
 * baselines stay untouched; source-scan ratchets remain the enforcement path.
 */
export function createMissingKeyDiagnostics(
  isDev: boolean
): MissingKeyDiagnostics {
  if (!isDev) return {};
  return {
    saveMissing: true,
    missingKeyHandler: (
      lngs: readonly string[],
      _ns: string,
      key: string
    ): void => {
      console.warn(
        `[i18n] Missing translation key "${key}" (${lngs.join(", ")})`
      );
    },
  };
}

i18n
  .use(initReactI18next)
  .init({
    resources: {
      en: { translation: en },
      de: { translation: de },
    },
    lng: navigator.language.startsWith("de") ? "de" : "en",
    fallbackLng: "en",
    interpolation: {
      escapeValue: false, // React already escapes values
    },
    ...createMissingKeyDiagnostics(import.meta.env.DEV),
  });

export { i18n };
