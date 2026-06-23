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
  });

export { i18n };
