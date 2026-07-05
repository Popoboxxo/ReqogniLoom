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

interface MarkdownPreviewProps {
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
}

export function MarkdownPreview({
  value,
  onChange,
  disabled = false,
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
    a: ({ node, href, children, ...props }: any) => {
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
      <div
        style={{
          display: "flex",
          gap: "0.5rem",
          marginBottom: "0.5rem",
          alignItems: "center",
        }}
      >
        <button
          type="button"
          data-testid="md-edit-btn"
          onClick={() => setIsPreview(false)}
          style={{
            fontWeight: !isPreview ? "bold" : "normal",
            cursor: "pointer",
          }}
        >
          {t("editor.editMode")}
        </button>
        <button
          type="button"
          data-testid="md-preview-btn"
          onClick={() => setIsPreview(true)}
          style={{
            fontWeight: isPreview ? "bold" : "normal",
            cursor: "pointer",
          }}
        >
          {t("editor.previewMode")}
        </button>
      </div>

      {isPreview ? (
        <div
          style={{
            border: "1px solid var(--color-border)",
            borderRadius: "4px",
            padding: "0.75rem",
            minHeight: "120px",
            background: "var(--color-surface-raised)",
            color: "var(--color-text)",
          }}
        >
          <ReactMarkdown components={components}>{processedValue}</ReactMarkdown>
        </div>
      ) : (
        <textarea
          value={value}
          onChange={(e) => onChange(e.target.value)}
          disabled={disabled}
          rows={6}
          style={{
            width: "100%",
            padding: "0.5rem",
            fontSize: "0.95rem",
            fontFamily: "monospace",
            border: "1px solid var(--color-border)",
            borderRadius: "4px",
            boxSizing: "border-box",
            resize: "vertical",
            background: "var(--color-surface-raised)",
            color: "var(--color-text)",
          }}
          placeholder={t("editor.descriptionPlaceholder")}
        />
      )}
    </div>
  );
}
