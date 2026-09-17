/**
 * ARCH-L1-001 ReactFrontend — <ArtifactId> (UI concept ch. 12.4).
 *
 * The identifier is the *name* of an artifact, not a metadatum (ch. 2). It
 * therefore gets one canonical representation that is identical in lists,
 * trees, trace panels and detail headers — mono, selectable in one gesture,
 * and copyable by click **or double-click** with a visible confirmation.
 *
 * Attribut v3 WS3 (#937): the rendering itself now lives in the generic
 * `<RevealValue>` display engine; this component is the artifact-specific
 * preset of it — mono, copyable, and neutral (colour encodes workflow status
 * and nothing else, ch. 3.3, so an identifier never carries a hue of its own).
 *
 * `mask` is forwarded but defaults to `"none"`: the call sites pass the
 * semantic `uid` (e.g. "SYS-REQ-001") as `value` and the already-shortened
 * UUID prefix as `fallback`, so applying `mask="short"` here would truncate
 * human-readable identifiers and break the "identifier is the name" contract.
 * The generic attribute renderer applies `mask="short"` where the raw value is
 * the opaque UUID (spec section 5).
 */

import { useTranslation } from "react-i18next";

import type { AttributeMask, AttributeReveal } from "../../api/attribute-definitions";
import { RevealValue } from "./RevealValue";

export interface ArtifactIdProps {
  /**
   * The semantic identifier (`uid`). When absent, `fallback` is rendered
   * instead — artifacts without an assigned uid still need a stable handle.
   */
  value?: string | null;
  /** Shown when `value` is empty, e.g. the first 8 chars of the UUID. */
  fallback?: string | null;
  /** Copy the *full* value to the clipboard, if it differs from the label. */
  copyValue?: string | null;
  /** Suppresses the copy interaction — used inside already-clickable rows. */
  readOnly?: boolean;
  /** Optional label shortening (spec section 5); default keeps the label. */
  mask?: AttributeMask;
  /** Optional reveal mode; default `"always"` keeps the id visible. */
  reveal?: AttributeReveal;
  testId?: string;
}

export function ArtifactId({
  value,
  fallback,
  copyValue,
  readOnly = false,
  mask = "none",
  reveal = "always",
  testId = "artifact-id",
}: ArtifactIdProps): JSX.Element | null {
  const { t } = useTranslation();
  return (
    <RevealValue
      value={value}
      fallback={fallback}
      copyValue={copyValue}
      readOnly={readOnly}
      mask={mask}
      reveal={reveal}
      copyable
      displayFormat="mono"
      label={t("artifactId.term", "Bezeichner")}
      testId={testId}
    />
  );
}
