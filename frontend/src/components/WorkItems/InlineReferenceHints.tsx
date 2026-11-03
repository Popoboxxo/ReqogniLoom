/**
 * ARCH-L1-001 ReactFrontend — inline-reference / DOC-P7 hints (Plan F F3-T9).
 *
 * The stored markdown carries `[[glossary:<uuid>@<rev>]]` tokens (ENT-F3 = a);
 * `glossary/references/resolve/` answers whether each token still points at a
 * live term. An unresolved token is the UI-side half of `DOC-P7` (dead inline
 * reference, I-5) — the anchor register itself has no REST read route in this
 * task, so the hint is derived from the same resolver the editor uses.
 *
 * Read-only: never writes, never blocks. A resolution failure degrades to no
 * hint rather than to an error banner in front of the content.
 */

import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { glossaryApi } from "../../api/glossary";
import type { GlossaryReferenceResolution } from "../../types";
import styles from "./WorkItems.module.css";

const REFERENCE_PRESENCE =
  /\[\[\s*glossary:[0-9a-fA-F-]{36}(?:@\d+)?\s*\]\]/;

export interface InlineReferenceHintsProps {
  text: string;
  workspaceId?: string;
  testId?: string;
}

export function InlineReferenceHints({
  text,
  workspaceId,
  testId = "inline-reference-hints",
}: InlineReferenceHintsProps): JSX.Element | null {
  const { t } = useTranslation();
  const hasTokens = REFERENCE_PRESENCE.test(text ?? "");
  const [references, setReferences] = useState<GlossaryReferenceResolution[]>(
    []
  );
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!hasTokens || !workspaceId) {
      setReferences([]);
      setFailed(false);
      return;
    }
    let cancelled = false;
    setFailed(false);
    glossaryApi
      .resolveReferences(workspaceId, text)
      .then((payload) => {
        if (!cancelled) setReferences(payload.references);
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [hasTokens, text, workspaceId]);

  const unresolved = useMemo(
    () => references.filter((reference) => !reference.resolved),
    [references]
  );

  if (!hasTokens) return null;
  if (failed) return null;

  return (
    <div className={styles.section} data-testid={testId}>
      <p className={styles.hint} data-testid={`${testId}-count`}>
        {t("work_items.references.count", { count: references.length })}
      </p>
      {unresolved.length > 0 && (
        <p
          role="status"
          className={styles.hintWarning}
          data-testid={`${testId}-dead`}
        >
          {t("work_items.references.dead", { count: unresolved.length })}
        </p>
      )}
    </div>
  );
}
