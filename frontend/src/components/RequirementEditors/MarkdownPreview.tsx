/**
 * ARCH-L1-001 ReactFrontend — Markdown Preview Toggle.
 *
 * leaf_id: COMP-RF-003 (RequirementEditors)
 * req_id:  REQ-L3-RF003-001 (Inline-Editing — Markdown Preview toggleable)
 */

import { useState, useEffect, useMemo } from "react";
import ReactMarkdown from "react-markdown";
import { useTranslation } from "react-i18next";
import { useWorkspace } from "../../context/WorkspaceContext";
import { glossaryApi } from "../../api/glossary";
import { GlossaryTooltip } from "./GlossaryTooltip";
import type { GlossaryTerm } from "../../types";
import styles from "./MarkdownPreview.module.css";

interface MarkdownPreviewProps {
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
  /**
   * Id applied to the underlying `<textarea>` so a caller's `<label htmlFor>`
   * resolves to a real form control (WCAG 1.3.1 / 4.1.2). Without it, the
   * label and the textarea are visually adjacent but programmatically
   * unrelated to assistive tech.
   */
  id?: string;
  /** Accessible name fallback when no external `<label htmlFor>` is used. */
  ariaLabel?: string;
}

export function MarkdownPreview({
  value,
  onChange,
  disabled = false,
  id,
  ariaLabel,
}: MarkdownPreviewProps): JSX.Element {
  const { t } = useTranslation();
  const [isPreview, setIsPreview] = useState(false);
  const { activeWorkspace } = useWorkspace();
  const [terms, setTerms] = useState<GlossaryTerm[]>([]);

  useEffect(() => {
    if (isPreview && activeWorkspace?.id) {
      glossaryApi.list(activeWorkspace.id).then(setTerms).catch(console.error);
    }
  }, [isPreview, activeWorkspace?.id]);

  const termsMap = useMemo(() => {
    const map = new Map<string, GlossaryTerm>();
    terms.forEach((t) => map.set(t.term.toLowerCase(), t));
    return map;
  }, [terms]);

  // Pre-process markdown to replace @Term with [Term](glossary:term_id)
  const processedValue = useMemo(() => {
    if (!value) return "*" + t("editor.empty") + "*";
    
    // Replace @Word (including German umlauts)
    return value.replace(/@([a-zA-ZäöüßÄÖÜ0-9_-]+)/g, (match, word) => {
      const term = termsMap.get(word.toLowerCase());
      if (term) {
        return `[${word}](glossary:${term.id})`;
      }
      return match;
    });
  }, [value, termsMap, t]);

  const components = {
    a: ({ node: _node, href, children, ...props }: JSX.IntrinsicElements["a"] & { node?: unknown }) => {
      if (href && href.startsWith("glossary:")) {
        const termId = href.split("glossary:")[1];
        const termData = terms.find((t) => t.id === termId);
        if (termData) {
          return <GlossaryTooltip termText={String(children)} termData={termData} />;
        }
      }
      return (
        <a href={href} {...props}>
          {children}
        </a>
      );
    },
  };

  return (
    <div>
      <div role="tablist" className={styles.tablist}>
        <button
          type="button"
          role="tab"
          className="btn-tab"
          aria-selected={!isPreview}
          data-testid="md-edit-btn"
          onClick={() => setIsPreview(false)}
        >
          {t("editor.editMode")}
        </button>
        <button
          type="button"
          role="tab"
          className="btn-tab"
          aria-selected={isPreview}
          data-testid="md-preview-btn"
          onClick={() => setIsPreview(true)}
        >
          {t("editor.previewMode")}
        </button>
      </div>

      {isPreview ? (
        <div className={styles.previewBox}>
          <ReactMarkdown components={components}>{processedValue}</ReactMarkdown>
        </div>
      ) : (
        <textarea
          id={id}
          aria-label={id ? undefined : ariaLabel}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          disabled={disabled}
          rows={6}
          className={styles.textarea}
          placeholder={t("editor.descriptionPlaceholder")}
        />
      )}
    </div>
  );
}
