/**
 * ARCH-L1-001 ReactFrontend — Markdown Preview Toggle.
 *
 * leaf_id: COMP-RF-003 (RequirementEditors)
 * req_id:  REQ-L3-RF003-001 (Inline-Editing — Markdown Preview toggleable)
 *
 * #1266: in addition to the legacy `@Term` inline mention this editor renders
 * version-bound glossary reference tokens `[[glossary:<uuid>@<revision>]]` as
 * highlighted marks (tooltip = definition + resolved version), offers an
 * "insert glossary reference" affordance, and surfaces version drift with a
 * per-field "raise to head" bulk action. The token text stays in the stored
 * value untouched — only the preview resolves it.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown, { defaultUrlTransform } from "react-markdown";
import { useTranslation } from "react-i18next";
import { useWorkspace } from "../../context/WorkspaceContext";
import { glossaryApi } from "../../api/glossary";
import { GlossaryTooltip } from "./GlossaryTooltip";
import type {
  GlossaryReferenceResolution,
  GlossaryReferenceResolutionPayload,
  GlossaryTerm,
} from "../../types";
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
  /**
   * #1266: backing Artifact id of the field's entity. Required to create the
   * usage trace link on insert (an unsaved artifact has none yet, so insertion
   * degrades to writing the token text without a link).
   */
  artifactId?: string | null;
}

/** `[[glossary:<uuid>]]` / `[[glossary:<uuid>@<revision>]]`. */
const REFERENCE_PATTERN =
  /\[\[\s*glossary:([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})(?:@(\d+))?\s*\]\]/g;

/**
 * Non-global twin used only for the presence check: `RegExp.prototype.test`
 * on a `g`-flagged regex advances `lastIndex` between calls, which would make
 * the check alternate between true/false across renders.
 */
const REFERENCE_PRESENCE =
  /\[\[\s*glossary:[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}(?:@\d+)?\s*\]\]/;

/** Internal markdown-link scheme carrying a reference through ReactMarkdown. */
const REF_SCHEME = "glossary-ref:";

function referenceKey(globalUuid: string, revision: number | null): string {
  return `${globalUuid}@${revision ?? ""}`;
}

export function MarkdownPreview({
  value,
  onChange,
  disabled = false,
  id,
  ariaLabel,
  artifactId = null,
}: MarkdownPreviewProps): JSX.Element {
  const { t } = useTranslation();
  const [isPreview, setIsPreview] = useState(false);
  const { activeWorkspace } = useWorkspace();
  const [terms, setTerms] = useState<GlossaryTerm[]>([]);
  const [resolved, setResolved] = useState<GlossaryReferenceResolutionPayload | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  const workspaceId = activeWorkspace?.id;
  const referenceMode = activeWorkspace?.glossary_reference_mode ?? "pinned";

  // Legacy `@Term` support: terms are only needed once a preview is shown.
  useEffect(() => {
    if (isPreview && workspaceId) {
      glossaryApi.list(workspaceId).then(setTerms).catch(console.error);
    }
  }, [isPreview, workspaceId]);

  const termsMap = useMemo(() => {
    const map = new Map<string, GlossaryTerm>();
    terms.forEach((term) => map.set(term.term.toLowerCase(), term));
    return map;
  }, [terms]);

  const hasToken = REFERENCE_PRESENCE.test(value ?? "");

  // #1266: resolve reference tokens against the pinned revision / head. Only
  // fires in preview mode and only when the text actually carries a token.
  useEffect(() => {
    if (!isPreview || !workspaceId || !hasToken) {
      setResolved(null);
      return;
    }
    let cancelled = false;
    glossaryApi
      .resolveReferences(workspaceId, value)
      .then((payload) => {
        if (!cancelled) setResolved(payload);
      })
      .catch(console.error);
    return () => {
      cancelled = true;
    };
  }, [isPreview, workspaceId, hasToken, value]);

  const resolutionMap = useMemo(() => {
    const map = new Map<string, GlossaryReferenceResolution>();
    resolved?.references.forEach((ref) =>
      map.set(referenceKey(ref.global_uuid, ref.requested_revision), ref)
    );
    return map;
  }, [resolved]);

  // Pre-process markdown: `@Term` mentions and `[[glossary:…]]` tokens become
  // links the custom `a` renderer can intercept.
  const processedValue = useMemo(() => {
    if (!value) return "*" + t("editor.empty") + "*";

    const withMentions = value.replace(/@([a-zA-ZäöüßÄÖÜ0-9_-]+)/g, (match, word) => {
      const term = termsMap.get(String(word).toLowerCase());
      if (term) {
        return `[${word}](glossary:${term.id})`;
      }
      return match;
    });

    return withMentions.replace(
      REFERENCE_PATTERN,
      (_match: string, uuid: string, revision: string | undefined) => {
        const key = referenceKey(uuid, revision ? Number(revision) : null);
        const ref = resolutionMap.get(key);
        const label = (ref?.resolved ? ref.term : uuid).replace(/[[\]]/g, "");
        return `[${label}](${REF_SCHEME}${key})`;
      }
    );
  }, [value, termsMap, resolutionMap, t]);

  const components = {
    a: ({
      node: _node,
      href,
      children,
      ...props
    }: JSX.IntrinsicElements["a"] & { node?: unknown }) => {
      if (href && href.startsWith(REF_SCHEME)) {
        const key = href.slice(REF_SCHEME.length);
        const ref = resolutionMap.get(key);
        if (ref && ref.resolved) {
          return (
            <GlossaryTooltip termText={String(children)} reference={ref} />
          );
        }
        return (
          <span
            className={styles.unresolved}
            data-testid="glossary-reference-unresolved"
            title={t("markdown.reference.unresolved")}
          >
            {children}
          </span>
        );
      }
      if (href && href.startsWith("glossary:")) {
        const termId = href.split("glossary:")[1];
        const termData = terms.find((term) => term.id === termId);
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

  const insertAtCursor = useCallback(
    (token: string): void => {
      const el = textareaRef.current;
      if (!el) {
        onChange(`${value}${token}`);
        return;
      }
      const start = el.selectionStart ?? value.length;
      const end = el.selectionEnd ?? value.length;
      onChange(`${value.slice(0, start)}${token}${value.slice(end)}`);
    },
    [value, onChange]
  );

  /**
   * Insert a reference for the chosen term. When the field belongs to a saved
   * artifact the backend creates the usage trace link and returns the pinned
   * token; otherwise (create mode) the token is built locally.
   */
  const handleInsertTerm = useCallback(
    async (globalUuid: string): Promise<void> => {
      const term = terms.find((candidate) => candidate.global_uuid === globalUuid);
      if (!term) return;
      if (workspaceId && artifactId) {
        try {
          const result = await glossaryApi.insertReference(
            workspaceId,
            artifactId,
            globalUuid
          );
          insertAtCursor(result.token);
          return;
        } catch (err) {
          console.error("Failed to create glossary reference link", err);
        }
      }
      const token =
        referenceMode === "always_head" || term.version === undefined
          ? `[[glossary:${globalUuid}]]`
          : `[[glossary:${globalUuid}@${term.version}]]`;
      insertAtCursor(token);
    },
    [terms, workspaceId, artifactId, referenceMode, insertAtCursor]
  );

  const handleUpgradeToHead = useCallback(async (): Promise<void> => {
    if (!workspaceId) return;
    try {
      const result = await glossaryApi.upgradeReferencesToHead(workspaceId, value);
      if (result.upgraded > 0) onChange(result.text);
    } catch (err) {
      console.error("Failed to upgrade glossary references", err);
    }
  }, [workspaceId, value, onChange]);

  const loadTermsForInsert = useCallback(
    async (open: boolean): Promise<void> => {
      if (!open || !workspaceId || terms.length > 0) return;
      try {
        setTerms(await glossaryApi.list(workspaceId));
      } catch (err) {
        console.error(err);
      }
    },
    [workspaceId, terms.length]
  );

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
          {resolved?.has_drift ? (
            <div role="alert" className={styles.driftHint} data-testid="glossary-drift-hint">
              <span>{t("markdown.reference.driftHint")}</span>
              <button
                type="button"
                className="btn-secondary"
                data-testid="glossary-drift-upgrade"
                onClick={() => void handleUpgradeToHead()}
              >
                {t("markdown.reference.upgradeToHead")}
              </button>
            </div>
          ) : null}
          <ReactMarkdown
            components={components}
            urlTransform={(url) =>
              url.startsWith(REF_SCHEME) || url.startsWith("glossary:")
                ? url
                : defaultUrlTransform(url)
            }
          >
            {processedValue}
          </ReactMarkdown>
        </div>
      ) : (
        <>
          <div className={styles.editToolbar}>
            <label className={styles.insertLabel}>
              {t("markdown.reference.insert")}
              <select
                className="field-select"
                data-testid="md-insert-reference"
                disabled={disabled}
                value=""
                onFocus={() => void loadTermsForInsert(true)}
                onClick={() => void loadTermsForInsert(true)}
                onChange={(event) => {
                  if (event.target.value) void handleInsertTerm(event.target.value);
                }}
              >
                <option value="">{t("markdown.reference.pick")}</option>
                {terms
                  .filter((term) => term.global_uuid)
                  .map((term) => (
                    <option key={term.global_uuid} value={term.global_uuid}>
                      {term.term}
                    </option>
                  ))}
              </select>
            </label>
          </div>
          <textarea
            ref={textareaRef}
            id={id}
            aria-label={id ? undefined : ariaLabel}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            disabled={disabled}
            rows={6}
            className={styles.textarea}
            placeholder={t("editor.descriptionPlaceholder")}
          />
        </>
      )}
    </div>
  );
}
