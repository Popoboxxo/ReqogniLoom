/**
 * The one definition of "this attribute is effectively required" — shared by
 * `components/shared/ArtifactForm/fields/FieldShell` (the renderer) and
 * `hooks/useFieldContract` (the create-dialog resolver), which used to carry
 * two copies of the same expression.
 *
 * Two flags feed it:
 *
 *   `required`     — the attribute definition's own flag.
 *   `is_required`  — the #1192 approval-gate overlay (`ArtifactForm` copies it
 *                    from `/attribute-schema/`).
 *
 * The resolved-definition endpoint (`…/attribute-defaults/<type>/`) does NOT
 * emit `is_required` today, so in the create-dialog resolver the second operand
 * only has an effect if an overlay supplies it. It is kept here rather than
 * dropped so the two call sites cannot drift apart again.
 *
 * Deliberately a plain function in `utils/` (no React, no barrel import): the
 * create dialogs must not pull the whole `ArtifactForm` renderer into their
 * module graph just to ask this question.
 */

/** The subset of an attribute spec this predicate reads. */
export interface RequiredFlags {
  required?: boolean;
  is_required?: boolean;
}

export function isEffectiveRequired(flags: RequiredFlags): boolean {
  return flags.required === true || flags.is_required === true;
}
