import styles from "../ArtifactForm.module.css";
import { TagInput } from "../../tag-input";
import type { WidgetProps } from "../widget-registry";

/**
 * `Issue.tags` editor (Task 20 review round, F-1 fix). `tags` is a JSONField
 * (`_attribute_type` in bootstrap_attribute_definitions.py returns None for
 * it — no basic renderer), so it is registered as a widget rather than a
 * plain field, same pattern as `steps_editor` for `TestCase.steps`. Wraps the
 * existing `TagInput` component (REQ-010) instead of writing a new one.
 */
export function TagInputWidget({
  attribute,
  values,
  onChange,
  disabled,
  errors,
  testId,
}: WidgetProps): JSX.Element {
  const field = attribute.fields[0] ?? "tags";
  const raw = values[field];
  const tags: string[] = Array.isArray(raw)
    ? raw.filter((entry): entry is string => typeof entry === "string")
    : [];

  return (
    <div className={styles.widget} data-testid={testId}>
      <TagInput
        tags={tags}
        onChange={(next) => onChange(field, next)}
        disabled={disabled}
        data-testid={`${testId}-tags`}
      />
      {(errors?.[field] ?? []).map((message) => (
        <span key={message} className={styles.errors} role="alert">
          {message}
        </span>
      ))}
    </div>
  );
}
