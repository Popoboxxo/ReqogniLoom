/**
 * ARCH-L1-001 ReactFrontend — Markdown Preview Toggle.
 *
 * leaf_id: COMP-RF-003 (RequirementEditors)
 * req_id:  REQ-L3-RF003-001 (Inline-Editing — Markdown Preview toggleable)
 */

import React, { useState } from "react";
import ReactMarkdown from "react-markdown";
import { useTranslation } from "react-i18next";

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
            border: "1px solid #ccc",
            borderRadius: "4px",
            padding: "0.75rem",
            minHeight: "120px",
            background: "#fafafa",
          }}
        >
          <ReactMarkdown>{value || "*" + t("editor.empty") + "*"}</ReactMarkdown>
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
            border: "1px solid #ccc",
            borderRadius: "4px",
            boxSizing: "border-box",
            resize: "vertical",
          }}
          placeholder={t("editor.descriptionPlaceholder")}
        />
      )}
    </div>
  );
}
