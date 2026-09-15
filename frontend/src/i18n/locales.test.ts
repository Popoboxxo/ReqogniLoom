import { describe, expect, it } from "vitest";

import { NOTIFICATION_PREFERENCE_KINDS } from "../api/notification-preferences";
import de from "./locales/de.json";
import en from "./locales/en.json";

const COMMENT_KEYS = [
  "ariaLabel",
  "heading",
  "empty",
  "placeholder",
  "inputLabel",
  "submit",
  "resolve",
  "delete",
  "deleteTitle",
  "deleteMessage",
  "unknownAuthor",
  "loadFailed",
  "createFailed",
  "resolveFailed",
  "deleteFailed",
];

const NOTIFICATION_KEYS = ["ariaLabel", "label", "empty", "markAllRead"];

// Keys the NotificationsSection component calls as
// `t("notificationPreferences.<key>", "<English fallback>")`. The four
// trigger labels (`assigned`, `comment_added`, `transition_pending`,
// `suspect_flagged`) duplicate the kind vocabulary owned by
// `notification-preferences.ts` — that duplication is guarded separately
// below via the imported `NOTIFICATION_PREFERENCE_KINDS`.
const NOTIFICATION_PREFERENCE_KEYS = [
  "title",
  "hint",
  "assigned",
  "comment_added",
  "transition_pending",
  "suspect_flagged",
  "error",
  "loading",
];

describe.each([
  ["de", de as Record<string, unknown>],
  ["en", en as Record<string, unknown>],
])("%s locale", (_name, locale) => {
  it("has a nested comments namespace", () => {
    expect(typeof locale.comments).toBe("object");
  });

  it.each(COMMENT_KEYS)("has comments.%s", (key) => {
    expect((locale.comments as Record<string, string>)[key]).toBeTruthy();
  });

  it.each(NOTIFICATION_KEYS)("has notifications.%s", (key) => {
    expect((locale.notifications as Record<string, string>)[key]).toBeTruthy();
  });

  it.each(NOTIFICATION_PREFERENCE_KEYS)("has notificationPreferences.%s", (key) => {
    expect((locale.notificationPreferences as Record<string, string>)[key]).toBeTruthy();
  });

  it("has a locale entry for every notification preference kind", () => {
    // Drift guard: the kind vocabulary lives in notification-preferences.ts
    // and is rendered through the component's exhaustive switch. Reading it
    // from the module (rather than re-typing the four literals) means a new
    // kind cannot be added without either a matching locale entry here or a
    // red test — the exact silent divergence this suite exists to catch.
    const block = locale.notificationPreferences as Record<string, string>;
    for (const kind of NOTIFICATION_PREFERENCE_KINDS) {
      expect(
        block[kind],
        `notificationPreferences.${kind} (kind from notification-preferences.ts)`
      ).toBeTruthy();
    }
  });

  it("uses no flat dotted keys in these namespaces", () => {
    // keySeparator is "."; a literal "comments.heading" key never resolves.
    expect(Object.keys(locale).some((k) => k.startsWith("comments."))).toBe(false);
    expect(Object.keys(locale).some((k) => k.startsWith("notifications."))).toBe(false);
    expect(Object.keys(locale).some((k) => k.startsWith("notificationPreferences."))).toBe(false);
  });
});
