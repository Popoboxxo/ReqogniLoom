/**
 * F4.3 — baseline tag constraints, shared by the detail editor
 * (`BaselineTagsEditor`) and the create dialog (`BaselinesView`).
 *
 * Single source of truth for the client-side mirror of
 * `backend/application/baseline_facade.py`:
 *
 *   - `_TAG_PATTERN = re.compile(r"^[\w][\w .:+#/-]*$")` — Python's `\w` is
 *     Unicode-aware, so the JS mirror cannot use `\w` (which is ASCII-only in
 *     JavaScript) without rejecting labels the backend accepts. `\w` is
 *     `[\p{L}\p{N}_]` under Unicode semantics, hence the `u`-flagged pattern
 *     below. "Prüfung", "Übergabe" and "Straße-2" are valid on both sides.
 *   - `MAX_TAGS_PER_BASELINE = 20`
 *   - `MAX_TAG_LENGTH = 64` (`BaselineTag.label` is `CharField(max_length=64)`)
 *
 * The backend stays the authority: this only spares the user a round-trip for
 * the obvious mistakes.
 */

/** Mirrors `MAX_TAGS_PER_BASELINE` in `backend/application/baseline_facade.py`. */
export const MAX_TAGS = 20;

/** Mirrors `MAX_TAG_LENGTH` in `backend/application/baseline_facade.py`. */
export const MAX_TAG_LENGTH = 64;

/**
 * Mirrors `_TAG_PATTERN` in `backend/application/baseline_facade.py`.
 *
 * The first character must be a letter, a digit or `_`; the tail additionally
 * allows a space, `.`, `:`, `+`, `#`, `/` and `-`. `#42` is therefore invalid
 * (`#` is tail-only) while `v1.0`, `C++`, `area/ui` and `rc:2` are valid.
 */
export const TAG_PATTERN = /^[\p{L}\p{N}_][\p{L}\p{N}_ .:+#/-]*$/u;

/** The one client-side validity check both call sites use. */
export function isValidTagLabel(label: string): boolean {
  return label.length <= MAX_TAG_LENGTH && TAG_PATTERN.test(label);
}

/**
 * Case-insensitive **set** comparison — not order-sensitive.
 *
 * The backend stores and returns labels case-insensitively sorted (unique
 * constraint `uq_bl_tag_baseline_label_ci`), while a local draft keeps the
 * user's insertion order. Comparing the draft to the persisted list
 * order-sensitively left `dirty` permanently true after a save (the save
 * button stayed enabled and never settled).
 */
export function sameTagSet(a: readonly string[], b: readonly string[]): boolean {
  if (a.length !== b.length) return false;
  const left = new Set(a.map((label) => label.toLowerCase()));
  const right = new Set(b.map((label) => label.toLowerCase()));
  if (left.size !== right.size) return false;
  for (const key of left) {
    if (!right.has(key)) return false;
  }
  return true;
}
