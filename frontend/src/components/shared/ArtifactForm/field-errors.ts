/**
 * Turns a rejected save into per-attribute error messages.
 *
 * The backend has TWO representations of the same failure and this module
 * prefers the structured one:
 *
 * 1. `error.details` — `[{ field, errors: string[] }]`, built by
 *    `rest_api/mixins/workflow_transitions.py::_validate_attribute_definition`
 *    and passed straight through `rest_api/error_envelope.py`. Unambiguous.
 * 2. `error.message` — the same data flattened by
 *    `attribute_definitions/field_validation.py::FieldValidationError` as
 *    `"; ".join(f"{name}: {', '.join(msgs)}")`, i.e.
 *    `"<name>: <msg>, <msg>; <name>: <msg>"`. Lossy: a message that itself
 *    contains `", "` or `"; "` cannot be told apart from a separator.
 *
 * `parseFieldErrors` reverses (2) and is kept as the fallback for any caller
 * that only has the flattened string. A message that does not match falls
 * through as `{}` on purpose: the caller then shows it in the form-level
 * banner, so a changed envelope degrades to "shown once at the top" instead of
 * "silently swallowed".
 */

export function parseFieldErrors(message: string): Record<string, string[]> {
  const out: Record<string, string[]> = {};
  for (const chunk of message.split("; ")) {
    const separator = chunk.indexOf(": ");
    if (separator <= 0) continue;
    const name = chunk.slice(0, separator).trim();
    // A name is an attribute identifier, never a sentence.
    if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(name)) continue;
    const messages = chunk
      .slice(separator + 2)
      .split(", ")
      .map((m) => m.trim())
      .filter(Boolean);
    if (messages.length) out[name] = messages;
  }
  return out;
}

interface ErrorDetail {
  field?: unknown;
  errors?: unknown;
}

/**
 * Reads `error.details` off a rejected `apiClient` call, falling back to
 * parsing the flattened `message`. Returns `{}` when neither yields a field
 * mapping — the caller then treats the failure as form-level.
 *
 * The thrown value is the PARSED RESPONSE BODY itself (`api/client.ts`'s
 * `apiFetch` does `throw body` on a non-ok response), i.e. `{ error: { code,
 * message, details } }`. It is NOT an axios error — there is no `.response`
 * and no `.data` anywhere in this client, and `instanceof Error` is false.
 *
 * Reading `details` is not a nicety here, it is the only correct path:
 * `extractErrorMessage` prefers `details[0].errors[0]` over `error.message`,
 * so for a multi-field validation failure the message string it hands back is
 * a single bare message like `"is required"` with the attribute name already
 * stripped — `parseFieldErrors` could never recover the mapping from it.
 */
export function fieldErrorsFromException(
  exc: unknown,
  message: string
): Record<string, string[]> {
  const details = (exc as { error?: { details?: unknown } } | null)?.error?.details;
  if (Array.isArray(details)) {
    const out: Record<string, string[]> = {};
    for (const entry of details as ErrorDetail[]) {
      if (typeof entry?.field !== "string" || !Array.isArray(entry.errors)) continue;
      const messages = entry.errors.map((m) => String(m)).filter(Boolean);
      if (messages.length) out[entry.field] = messages;
    }
    if (Object.keys(out).length) return out;
  }
  return parseFieldErrors(message);
}
