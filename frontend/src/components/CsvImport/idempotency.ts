/**
 * ReqIF idempotency scope ids (ADR-014 §3).
 *
 * `crypto.randomUUID` only exists in secure contexts (HTTPS/localhost); on a
 * plain-HTTP origin it is `undefined` and calling it would abort the file
 * selection. Falls back to an RFC4122 v4 UUID from `getRandomValues` and finally
 * to the `Date.now()`/`Math.random()` id style used by `canvas-geometry.ts`.
 */

export function generateIdempotencyUuid(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  if (typeof crypto !== "undefined" && typeof crypto.getRandomValues === "function") {
    const bytes = crypto.getRandomValues(new Uint8Array(16));
    // RFC4122 v4: version 4 in byte 6, variant 10xx in byte 8.
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    const hex = Array.from(bytes, (b): string => b.toString(16).padStart(2, "0"));
    return (
      `${hex.slice(0, 4).join("")}-${hex.slice(4, 6).join("")}-` +
      `${hex.slice(6, 8).join("")}-${hex.slice(8, 10).join("")}-${hex.slice(10, 16).join("")}`
    );
  }
  // `Math.random()` may return exactly 0, whose base-36 form is "0" — `.slice(2)`
  // then yields an empty suffix and the id degrades to `reqif-<ts>-`, breaking the
  // `^reqif-\d+-[0-9a-z]+$` contract. Retry once, then pin a non-empty token.
  const rand = Math.random().toString(36).slice(2) || Math.random().toString(36).slice(2) || "0";
  return `${Date.now()}-${rand}`;
}
