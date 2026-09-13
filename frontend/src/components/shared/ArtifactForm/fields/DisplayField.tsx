/**
 * <DisplayField> (Attribut v3 WS3, #937) — the read-only counterpart of the
 * definition-driven editable field.
 *
 * A field whose attribute carries at least one non-default display property
 * (`copyable`/`reveal`/`mask`/`display_format`, see `hasConfiguredDisplay`) is
 * rendered through the generic `<RevealValue>` engine instead of a disabled
 * control, so those properties actually take effect. An attribute without
 * special properties never reaches this component and keeps rendering through
 * its ordinary control — the "no big bang" default in the WS3 brief.
 */

import { useTranslation } from "react-i18next";

import { RevealValue } from "../../RevealValue";
import { attributeLabel, FieldShell, helpText } from "./FieldShell";
import { formatAttributeValue, resolveDisplayProps } from "./display-properties";
import type { AttributeSpec } from "../../../../api/attribute-definitions";

export interface DisplayFieldProps {
  attribute: AttributeSpec;
  value: unknown;
  errors?: string[];
  testId: string;
}

export function DisplayField({
  attribute,
  value,
  errors,
  testId,
}: DisplayFieldProps): JSX.Element {
  const { i18n } = useTranslation();
  const display = resolveDisplayProps(attribute);
  const formatted = formatAttributeValue(attribute, value, i18n.language);
  // The display path renders no labelable control, so the label is associated
  // via `aria-labelledby` on the value; help/error are wired the same way the
  // editable fields wire them through `ariaProps` (FieldShell.tsx).
  const describedBy =
    [
      helpText(attribute, i18n.language) ? `${testId}-help` : null,
      errors?.length ? `${testId}-error` : null,
    ]
      .filter(Boolean)
      .join(" ") || undefined;
  return (
    <FieldShell
      attribute={attribute}
      language={i18n.language}
      errors={errors}
      testId={testId}
      associateLabel={false}
    >
      <RevealValue
        value={formatted.text}
        chips={display.displayFormat === "chips" ? formatted.chips : null}
        displayFormat={display.displayFormat}
        reveal={display.reveal}
        mask={display.mask}
        copyable={display.copyable}
        label={attributeLabel(attribute, i18n.language)}
        ariaLabelledBy={`${testId}-label`}
        ariaDescribedBy={describedBy}
        testId={testId}
      />
    </FieldShell>
  );
}

DisplayField.displayName = "DisplayField";
