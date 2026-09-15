import { describe, expect, it } from "vitest";

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

  it("uses no flat dotted keys in these namespaces", () => {
    // keySeparator is "."; a literal "comments.heading" key never resolves.
    expect(Object.keys(locale).some((k) => k.startsWith("comments."))).toBe(false);
    expect(Object.keys(locale).some((k) => k.startsWith("notifications."))).toBe(false);
  });
});
