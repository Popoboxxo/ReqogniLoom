import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { resolveArtifactRef, type ArtifactRef } from "../../../../api/artifactRefs";
import styles from "../ArtifactForm.module.css";
import { FieldShell, ariaProps, type FieldProps } from "./FieldShell";

/**
 * Picks another artifact by id.
 *
 * DEVIATION from the plan brief: the brief called
 * `resolveArtifactRefs(activeWorkspace.id)` expecting an `ArtifactRef[]` with
 * `id`/`displayId` fields to populate a `<select>` of candidates. The real
 * `api/artifactRefs` module (Task 15, reviewed clean, byte-identical to its
 * own brief) has no such capability: `resolveArtifactRefs` takes a list of
 * ALREADY-KNOWN artifact ids and resolves each to a `{ title, route }` pair
 * for trace-link display — it cannot enumerate "every pickable artifact in
 * this workspace", and no other frontend module does either (the closest
 * precedent, `CreateTraceLinkDialog`, hand-assembles that list by calling six
 * separate per-type `list()` endpoints, a materially bigger feature than one
 * field renderer). `AttributeSpec` also carries no target-item-type for a
 * `reference` attribute (`fields` is validated as widget-only in
 * `backend/attribute_definitions/schema.py`), so there is no type to search
 * within even if a listing endpoint existed.
 *
 * Renders as a raw-id input instead, with an async-resolved title/route
 * preview for the currently selected value via the real (single-id)
 * `resolveArtifactRef` — that helper's actual contract *is* "resolve one
 * already-known id", which this usage matches.
 *
 * ponytail: id-typing is a real UX ceiling; upgrade to a search/autocomplete
 * once a cross-type artifact search endpoint exists (relevant for whoever
 * wires `reference` attributes into a real form in Task 18 / rollout waves
 * 19-25).
 */
export function ReferencePicker({
  attribute,
  value,
  onChange,
  disabled,
  errors,
  testId,
}: FieldProps<string | null>): JSX.Element {
  const { i18n, t } = useTranslation();
  const [resolved, setResolved] = useState<ArtifactRef | null>(null);

  useEffect(() => {
    let cancelled = false;
    if (!value) {
      setResolved(null);
      return undefined;
    }
    resolveArtifactRef(value).then((ref) => {
      if (!cancelled) setResolved(ref);
    });
    return () => {
      cancelled = true;
    };
  }, [value]);

  return (
    <FieldShell
      attribute={attribute}
      language={i18n.language}
      errors={errors}
      testId={testId}
    >
      <input
        id={testId}
        data-testid={testId}
        className={`${styles.control} ${errors?.length ? styles.controlInvalid : ""}`}
        type="text"
        value={value ?? ""}
        disabled={disabled}
        placeholder={t("artifactForm.referenceIdPlaceholder")}
        onChange={(event) => onChange(event.target.value || null)}
        {...ariaProps(attribute, testId, errors)}
      />
      {value && resolved?.route ? (
        <span className={styles.help} data-testid={`${testId}-preview`}>
          {resolved.title}
        </span>
      ) : null}
    </FieldShell>
  );
}
