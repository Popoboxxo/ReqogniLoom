/**
 * ActorDisplay (Attribut v3 WS2, #936) — the read-only counterpart of
 * `ActorPicker`.
 *
 * List views and non-editable detail panes show `owner`/`reporter` values
 * without the combobox: this renders the actor value as plain text. A resolved
 * name is used when the caller already has one (e.g. from the member
 * directory); otherwise the internal id — or the external name — is shown, so
 * an assigned actor never renders as an empty cell.
 */

import type { ActorValue } from "../../../../types";

export interface ActorDisplayProps {
  value: ActorValue | null | undefined;
  /**
   * Optional id -> display-name map. A missing entry falls back to the raw id
   * rather than hiding the assignment.
   */
  namesById?: ReadonlyMap<string, string>;
  /** Rendered when the value is unset. */
  fallback?: string;
  testId?: string;
}

export function actorDisplayText(
  value: ActorValue | null | undefined,
  namesById?: ReadonlyMap<string, string>
): string | null {
  if (!value) return null;
  if (value.kind === "external") return value.name;
  return namesById?.get(value.id) ?? value.id;
}

export function ActorDisplay({
  value,
  namesById,
  fallback = "—",
  testId,
}: ActorDisplayProps): JSX.Element {
  const text = actorDisplayText(value, namesById);
  return (
    <span data-testid={testId} title={text ?? undefined}>
      {text ?? fallback}
    </span>
  );
}

ActorDisplay.displayName = "ActorDisplay";
