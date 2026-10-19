/**
 * Section-area renderer of the definition-driven artifact form.
 *
 * Extracted from `ArtifactForm.tsx` (Phase 5b decomposition, FE-01 / F-01).
 * Draws the 12-column sections grid from the prepared `SectionEntry` list —
 * the SAME `layout-flow.ts` engine the renderer always used. Layout only; the
 * form state, the definition and the save/error routing stay in
 * `useArtifactFormState` + `ArtifactForm.tsx`.
 */

import { useId } from "react";
import { useTranslation } from "react-i18next";
import { ChevronDown, ChevronRight } from "lucide-react";

import type {
  AttributeSpec,
  SectionSpec,
} from "../../../api/attribute-definitions";
import type { WorkflowArtifactType } from "../../../api/workflow-transitions";
import styles from "./ArtifactForm.module.css";
import {
  resolveAttributeFlow,
  sectionLayoutColumns,
  spacerColumns,
  spanClassSuffix,
} from "./layout-flow";
import type {
  ArtifactFormValues,
  FormSection,
  SectionEntry,
} from "./artifact-form-types";
import { renderAttribute } from "./renderAttribute";

export interface ArtifactSectionsProps {
  sectionEntries: SectionEntry[];
  sectionMeta: Map<string, SectionSpec>;
  specByName: Map<string, AttributeSpec>;
  formValues: ArtifactFormValues;
  fieldErrors: Record<string, string[]>;
  isCreateMode: boolean;
  isReadOnly: boolean;
  saving: boolean;
  artifactId: string | null;
  workflowArtifactType?: WorkflowArtifactType;
  fieldTestIds?: Record<string, string>;
  isSectionOpen: (section: FormSection) => boolean;
  onToggleSection: (section: FormSection, open: boolean) => void;
  update: (attribute: AttributeSpec, next: unknown) => void;
}

export function ArtifactSections({
  sectionEntries,
  sectionMeta,
  specByName,
  formValues,
  fieldErrors,
  isCreateMode,
  isReadOnly,
  saving,
  artifactId,
  workflowArtifactType,
  fieldTestIds,
  isSectionOpen,
  onToggleSection,
  update,
}: ArtifactSectionsProps): JSX.Element {
  const { t, i18n } = useTranslation();
  // Phase 6 (H-2, WCAG SC 1.3.1/2.4.6): a stable per-form id base so the
  // section's accessible name (`aria-labelledby`) and its disclosure control
  // (`aria-controls`) reference real, collision-free ids even if two artifact
  // forms are mounted in the same document.
  const idBase = useId();

  const spanClass = (columns: number): string =>
    styles[`span${spanClassSuffix(columns)}`] ?? styles.span12;

  return (
    <div className={styles.sectionsGrid} data-testid="artifact-sections-grid">
      {sectionEntries.map((entry, entryIndex) => {
        if (entry.kind === "spacer") {
          return (
            <div
              key={`section-spacer-${entryIndex}`}
              className={`${styles.spacerToken} ${spanClass(spacerColumns(entry.size))}`}
              data-columns={spacerColumns(entry.size)}
              aria-hidden="true"
              data-testid={`artifact-section-spacer-${entryIndex}`}
            />
          );
        }
        const { section, layout } = entry;
        const open = isSectionOpen(section);
        // H-2 (a11y): the section is a named region. Its accessible name comes
        // from the stable label text (`sectionLabelId`), NOT from the disclosure
        // control: F-03/N4 (SC 1.3.1/2.4.6) — pointing `aria-labelledby` at the
        // toggle made the region's name the toggle's `aria-label` ("Abschnitt X
        // einklappen/erweitern"), i.e. an *action* that also flipped with the
        // expanded state. The interactive control keeps its own id
        // (`sectionToggleId`) as the `aria-controls` origin; the body panel id is
        // only referenced while that panel actually exists (N3 — a collapsed
        // section renders no body, and an `aria-controls` pointing at a missing
        // id is a dangling IDREF).
        const sectionLabelId = `${idBase}-section-label-${section.name}`;
        const sectionToggleId = `${idBase}-section-toggle-${section.name}`;
        const sectionBodyId = `${idBase}-section-body-${section.name}`;
        const fieldEntries = resolveAttributeFlow(
          sectionMeta.get(section.name),
          section.attributes
        );
        return (
          <section
            key={section.name}
            aria-labelledby={sectionLabelId}
            data-testid={`artifact-section-${section.name}`}
            data-layout={layout}
            data-columns={sectionLayoutColumns(layout)}
            className={`${styles.section} ${spanClass(sectionLayoutColumns(layout))}`}
          >
            {isCreateMode ? (
              // Create mode: sections cannot collapse (a required field hidden
              // behind a collapsed header would block the save invisibly), so
              // the header is a plain heading — a dead disclosure button would
              // otherwise be the focus trap's first Tab stop ahead of the
              // form's content (create-dialog focus contract, #800 class).
              <h3 className={styles.sectionHeading}>
                <span
                  id={sectionLabelId}
                  className={styles.sectionHeader}
                  data-testid={`artifact-section-toggle-${section.name}`}
                  aria-current="false"
                >
                  {t(`sections.${section.name}`, { defaultValue: section.name })}
                </span>
              </h3>
            ) : (
              <h3 className={styles.sectionHeading}>
                <button
                  type="button"
                  id={sectionToggleId}
                  className={`btn-ghost ${styles.sectionHeader}`}
                  data-testid={`artifact-section-toggle-${section.name}`}
                  aria-expanded={open}
                  aria-controls={open ? sectionBodyId : undefined}
                  aria-label={t(
                    open ? "artifactForm.collapseSection" : "artifactForm.expandSection",
                    { section: t(`sections.${section.name}`, { defaultValue: section.name }) }
                  )}
                  onClick={() => onToggleSection(section, open)}
                >
                  <span id={sectionLabelId}>{t(`sections.${section.name}`, { defaultValue: section.name })}</span>
                  {open ? (
                    <ChevronDown aria-hidden="true" size={16} />
                  ) : (
                    <ChevronRight aria-hidden="true" size={16} />
                  )}
                </button>
              </h3>
            )}

            {open ? (
              <div
                id={sectionBodyId}
                className={styles.sectionBody}
                data-testid={`artifact-section-body-${section.name}`}
              >
                {fieldEntries.map((fieldEntry, fieldIndex) => {
                  if (fieldEntry.kind === "spacer") {
                    return (
                      <div
                        key={`field-spacer-${fieldIndex}`}
                        className={`${styles.spacerToken} ${spanClass(fieldEntry.columns)}`}
                        data-columns={fieldEntry.columns}
                        aria-hidden="true"
                        data-testid={`artifact-field-spacer-${section.name}-${fieldIndex}`}
                      />
                    );
                  }
                  const rendered = renderAttribute({
                    attribute: fieldEntry.attribute,
                    values: formValues,
                    fieldErrors,
                    specByName,
                    disabled:
                      isReadOnly ||
                      saving ||
                      // A workflow-owned attribute is editable through the
                      // WorkflowStatusEditor's own transition menu, not through
                      // the generic editable-control path — `editable ===
                      // "workflow"` must therefore NOT count as "not editable"
                      // here, or the status editor renders without its trigger
                      // (E2E: workflow-transition-trigger missing).
                      (fieldEntry.attribute.editable !== true &&
                        fieldEntry.attribute.editable !== "workflow"),
                    // Distinct from `disabled`: a save in flight must not switch
                    // a configured field from its editable control to the
                    // read-only display (that would flash the value format).
                    displayOnly: isReadOnly || fieldEntry.attribute.editable !== true,
                    language: i18n.language,
                    systemUnsetLabel: t("artifactForm.systemValueUnavailable"),
                    artifactId,
                    workflowArtifactType,
                    unsupportedLabel: t("artifactForm.unsupportedWidget", {
                      widget: fieldEntry.attribute.widget_key ?? "",
                    }),
                    update,
                    // The adapter's create-dialog automation selectors (#583):
                    // E2E drives the definition-driven path through the same
                    // legacy testids the fallback form has always exposed.
                    testId: fieldTestIds?.[fieldEntry.attribute.name] ?? `artifact-field-${fieldEntry.attribute.name}`,
                  });
                  if (!rendered) return null;
                  return (
                    <div
                      key={fieldEntry.attribute.name}
                      className={`${styles.fieldCell} ${spanClass(fieldEntry.columns)}`}
                      data-columns={fieldEntry.columns}
                      data-testid={`artifact-field-cell-${fieldEntry.attribute.name}`}
                    >
                      {rendered}
                    </div>
                  );
                })}
              </div>
            ) : null}
          </section>
        );
      })}
    </div>
  );
}
