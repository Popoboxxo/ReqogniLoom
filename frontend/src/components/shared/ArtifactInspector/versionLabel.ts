/**
 * ONE source of truth for a version row's display label (issue #272, C-L9).
 *
 * The backend's synthetic version 0 is labelled in English
 * ("Creation baseline" — `application/artifact_diff_service.py`), but that
 * string is an API field, not UI text: the client translates it. The additive
 * `is_creation_baseline` flag identifies the row; comparing the English label
 * itself is exactly the drift this helper exists to prevent.
 *
 * Both renderers MUST use this helper — `ArtifactDiff`'s From/To dropdowns
 * (API shape `ArtifactVersion`, snake_case flag) and `VersionPanel`'s row list
 * (inspector shape `VersionRef`, camelCase flag) — so they cannot diverge.
 */

/**
 * `isCreationBaseline` is `boolean | undefined` on purpose: the flag is
 * optional in both wire and inspector shapes (older backends omit it, and the
 * absent case must fall through to the raw label).
 */
export function versionLabel(
  label: string,
  isCreationBaseline: boolean | undefined,
  t: (key: string) => string,
): string {
  return isCreationBaseline === true
    ? t("sidebar.version.creationBaseline")
    : label;
}
