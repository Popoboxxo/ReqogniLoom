/**
 * Shared i18n test helpers for components that mock react-i18next.
 *
 * Resolves translation keys against the German locale (de.json) so unit
 * tests can assert on real copy without spinning up the full i18n stack.
 */
import deLocale from "../i18n/locales/de.json";

export function resolveLocaleKey(key: string): string | undefined {
  const value = key
    .split(".")
    .reduce<unknown>(
      (node, segment) =>
        node && typeof node === "object" ? (node as Record<string, unknown>)[segment] : undefined,
      deLocale
    );
  return typeof value === "string" ? value : undefined;
}
