/**
 * Layout flow editor (Attribut v3 WS4 #938, spec section 7).
 *
 * Edits the definition-level `section_flow` and each section's
 * `attribute_flow` with the same local-buffered-state model the rest of the
 * attribute editor uses: every change lands in the page's state, marks the
 * page dirty and travels on the normal Save PUT. Nothing here calls the API.
 *
 * The editor always works on the EFFECTIVE flow (`orderedSectionTokens` /
 * `effectiveAttributeFlowTokens`): a definition without a stored flow is
 * normalized to the order-derived default (no spacers) the moment the editor
 * is shown, so every token it displays points at a real section/attribute and
 * reordering never loses an item.
 */

import { useTranslation } from "react-i18next";
import { ChevronDown, ChevronUp, Trash2 } from "lucide-react";

import type {
  AttributeSpan,
  AttributeSpec,
  LayoutToken,
  SectionSpec,
  SpacerSize,
} from "../../api/attribute-definitions";
import styles from "./AttributeEditor.module.css";
import { sectionNames } from "./attribute-edits";
import {
  ATTRIBUTE_SPANS,
  SPACER_SIZES,
  effectiveAttributeFlowTokens,
  moveToken,
  orderedSectionTokens,
  removeToken,
  replaceToken,
} from "../shared/ArtifactForm/layout-flow";

export interface LayoutFlowEditorProps {
  attributes: AttributeSpec[];
  sections: SectionSpec[];
  /** The stored definition-level flow, or `undefined` when the definition has
   * none (the editor shows the derived default but the page keeps the
   * distinction so a save without a layout edit omits the key entirely). */
  sectionFlow: LayoutToken[] | undefined;
  /** Editor-local empty sections (created but not yet holding a field). */
  emptySections: string[];
  readOnly: boolean;
  onSectionFlowChange: (next: LayoutToken[]) => void;
  onAttributeFlowChange: (sectionName: string, next: LayoutToken[]) => void;
}

export function LayoutFlowEditor({
  attributes,
  sections,
  sectionFlow,
  emptySections,
  readOnly,
  onSectionFlowChange,
  onAttributeFlowChange,
}: LayoutFlowEditorProps): JSX.Element {
  const { t } = useTranslation();

  const populated = sectionNames(attributes);
  const allSections = [
    ...populated,
    ...emptySections.filter((name) => !populated.includes(name)),
  ];
  const normalizedSectionFlow = orderedSectionTokens(sectionFlow, allSections);

  const sectionSpecByName = new Map<string, SectionSpec>();
  for (const section of sections) sectionSpecByName.set(section.name, section);

  const changeSectionToken = (index: number, token: LayoutToken): void => {
    onSectionFlowChange(replaceToken(normalizedSectionFlow, index, token));
  };

  const moveSectionToken = (index: number, toIndex: number): void => {
    if (toIndex < 0 || toIndex >= normalizedSectionFlow.length) return;
    onSectionFlowChange(moveToken(normalizedSectionFlow, index, toIndex));
  };

  return (
    <section className={styles.layoutEditor} data-testid="attribute-layout-editor">
      <h3 className={styles.layoutHeading}>{t("attributes.layout.title")}</h3>

      <div className={styles.flowBlock}>
        <h4 className={styles.flowHeading}>{t("attributes.layout.sectionFlow")}</h4>
        <ol className={styles.flowList} data-testid="section-flow-list">
          {normalizedSectionFlow.map((token, index) => (
            <li
              key={`${token.kind}-${index}`}
              className={styles.flowToken}
              data-testid={`section-flow-token-${index}`}
            >
              {token.kind === "section" ? (
                <span>{t(`sections.${token.name}`, { defaultValue: token.name })}</span>
              ) : token.kind === "spacer" ? (
                <select
                  className={styles.control}
                  data-testid={`section-flow-token-${index}-size`}
                  value={token.size}
                  disabled={readOnly}
                  aria-label={t("attributes.layout.spacerSize")}
                  onChange={(event) =>
                    changeSectionToken(index, {
                      kind: "spacer",
                      size: event.target.value as SpacerSize,
                    })
                  }
                >
                  {SPACER_SIZES.map((size) => (
                    <option key={size} value={size}>
                      {t(`attributes.layout.spacer.${size}`)}
                    </option>
                  ))}
                </select>
              ) : null}
              <span className={styles.badges}>
                <button
                  type="button"
                  disabled={readOnly || index === 0}
                  data-testid={`section-flow-token-${index}-up`}
                  aria-label={t("attributes.layout.moveUp")}
                  onClick={() => moveSectionToken(index, index - 1)}
                >
                  <ChevronUp aria-hidden="true" size={14} />
                </button>
                <button
                  type="button"
                  disabled={readOnly || index === normalizedSectionFlow.length - 1}
                  data-testid={`section-flow-token-${index}-down`}
                  aria-label={t("attributes.layout.moveDown")}
                  onClick={() => moveSectionToken(index, index + 1)}
                >
                  <ChevronDown aria-hidden="true" size={14} />
                </button>
                {token.kind === "spacer" ? (
                  <button
                    type="button"
                    disabled={readOnly}
                    data-testid={`section-flow-token-${index}-remove`}
                    aria-label={t("attributes.layout.remove")}
                    onClick={() =>
                      onSectionFlowChange(removeToken(normalizedSectionFlow, index))
                    }
                  >
                    <Trash2 aria-hidden="true" size={14} />
                  </button>
                ) : null}
              </span>
            </li>
          ))}
        </ol>
        <button
          type="button"
          disabled={readOnly}
          data-testid="section-flow-add-spacer"
          onClick={() =>
            onSectionFlowChange([...normalizedSectionFlow, { kind: "spacer", size: "md" }])
          }
        >
          {t("attributes.layout.addSpacer")}
        </button>
      </div>

      {populated.map((name) => {
        const sectionAttributes = attributes
          .filter((attribute) => attribute.section === name)
          .sort((a, b) => a.order - b.order);
        const tokens = effectiveAttributeFlowTokens(
          sectionSpecByName.get(name),
          sectionAttributes
        );
        const changeToken = (index: number, token: LayoutToken): void =>
          onAttributeFlowChange(name, replaceToken(tokens, index, token));
        const moveTokenTo = (index: number, toIndex: number): void => {
          if (toIndex < 0 || toIndex >= tokens.length) return;
          onAttributeFlowChange(name, moveToken(tokens, index, toIndex));
        };
        return (
          <div
            key={name}
            className={styles.flowBlock}
            data-testid={`attribute-flow-${name}`}
          >
            <h4 className={styles.flowHeading}>
              {t(`sections.${name}`, { defaultValue: name })}
            </h4>
            <ol className={styles.flowList}>
              {tokens.map((token, index) => (
                <li
                  key={`${token.kind}-${index}`}
                  className={styles.flowToken}
                  data-testid={`attribute-flow-${name}-token-${index}`}
                >
                  {token.kind === "attribute" ? (
                    <>
                      <span>
                        {(() => {
                          const attribute = sectionAttributes.find(
                            (candidate) => candidate.name === token.name
                          );
                          return attribute?.label.en || token.name;
                        })()}
                      </span>
                      <select
                        className={styles.control}
                        data-testid={`attribute-flow-${name}-token-${index}-span`}
                        value={token.span ?? "full"}
                        disabled={readOnly}
                        aria-label={t("attributes.layout.span")}
                        onChange={(event) =>
                          changeToken(index, {
                            kind: "attribute",
                            name: token.name,
                            span: event.target.value as AttributeSpan,
                          })
                        }
                      >
                        {ATTRIBUTE_SPANS.map((span) => (
                          <option key={span} value={span}>
                            {t(`attributes.layout.span_${span}`)}
                          </option>
                        ))}
                      </select>
                    </>
                  ) : token.kind === "spacer" ? (
                    <select
                      className={styles.control}
                      data-testid={`attribute-flow-${name}-token-${index}-size`}
                      value={token.size}
                      disabled={readOnly}
                      aria-label={t("attributes.layout.spacerSize")}
                      onChange={(event) =>
                        changeToken(index, {
                          kind: "spacer",
                          size: event.target.value as SpacerSize,
                        })
                      }
                    >
                      {SPACER_SIZES.map((size) => (
                        <option key={size} value={size}>
                          {t(`attributes.layout.spacer.${size}`)}
                        </option>
                      ))}
                    </select>
                  ) : null}
                  <span className={styles.badges}>
                    <button
                      type="button"
                      disabled={readOnly || index === 0}
                      data-testid={`attribute-flow-${name}-token-${index}-up`}
                      aria-label={t("attributes.layout.moveUp")}
                      onClick={() => moveTokenTo(index, index - 1)}
                    >
                      <ChevronUp aria-hidden="true" size={14} />
                    </button>
                    <button
                      type="button"
                      disabled={readOnly || index === tokens.length - 1}
                      data-testid={`attribute-flow-${name}-token-${index}-down`}
                      aria-label={t("attributes.layout.moveDown")}
                      onClick={() => moveTokenTo(index, index + 1)}
                    >
                      <ChevronDown aria-hidden="true" size={14} />
                    </button>
                    {token.kind === "spacer" ? (
                      <button
                        type="button"
                        disabled={readOnly}
                        data-testid={`attribute-flow-${name}-token-${index}-remove`}
                        aria-label={t("attributes.layout.remove")}
                        onClick={() =>
                          onAttributeFlowChange(name, removeToken(tokens, index))
                        }
                      >
                        <Trash2 aria-hidden="true" size={14} />
                      </button>
                    ) : null}
                  </span>
                </li>
              ))}
            </ol>
            <button
              type="button"
              disabled={readOnly}
              data-testid={`attribute-flow-${name}-add-spacer`}
              onClick={() =>
                onAttributeFlowChange(name, [...tokens, { kind: "spacer", size: "md" }])
              }
            >
              {t("attributes.layout.addSpacer")}
            </button>
          </div>
        );
      })}
    </section>
  );
}
