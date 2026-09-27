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

/**
 * Resolve a key the way i18next resolves a `count`-bearing call: the `_one`
 * form for exactly 1, `_other` for anything else, then `{{count}}`
 * interpolation.
 *
 * Needed because the project's own `i18n-parity.test.ts` documents that the
 * source scanner is plural-blind, so locale files carry the bare key *and*
 * both plural forms. A test that reads the bare key therefore never sees the
 * string a real i18next instance renders for count 1 — which is exactly the
 * string a screen reader is announced for an unread count of one.
 */
export function resolveLocaleKeyCount(key: string, count: number): string | undefined {
  const plural = `${key}_${count === 1 ? "one" : "other"}`;
  return resolveLocaleKey(plural) ?? resolveLocaleKey(key)?.replace(/\{\{count\}\}/g, String(count));
}
