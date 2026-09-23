/**
 * ARCH-L1-001 ReactFrontend — SimilarIcdsPanel (COMP-RF-001)
 *
 * req_id: REQ-L2-VS-004 (semantic similarity search)
 *
 * Renders a "Find Similar" action for an ICD and, on demand, a list of the
 * most semantically similar ICDs (cosine similarity over pgvector embeddings
 * of the current version). Mirrors SimilarRequirementsPanel and handles the
 * two backend degradation cases explicitly:
 *   - 400 VALIDATION_ERROR: the ICD has no embedding yet.
 *   - 503 SERVICE_UNAVAILABLE: pgvector is not available.
 */

import { useCallback, useState } from "react";
import { useTranslation } from "react-i18next";
import { icdsApi } from "../../api/icds";
import type { ApiError, SimilarIcd, UUID } from "../../types";
import styles from "./SimilarIcdsPanel.module.css";

interface SimilarIcdsPanelProps {
  icdId: UUID;
  /** Navigate to another ICD when a hit is clicked. */
  onSelect: (id: UUID) => void;
}

type PanelState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "no-embedding" }
  | { status: "unavailable" }
  | { status: "error"; message: string }
  | { status: "ready"; results: SimilarIcd[] };

function extractMessage(err: unknown): string {
  const e = err as { error?: { message?: string } };
  return e?.error?.message ?? String(err);
}

export function SimilarIcdsPanel({
  icdId,
  onSelect,
}: SimilarIcdsPanelProps): JSX.Element {
  const { t } = useTranslation();
  const [state, setState] = useState<PanelState>({ status: "idle" });

  const handleFindSimilar = useCallback(async (): Promise<void> => {
    setState({ status: "loading" });
    try {
      const results = await icdsApi.getSimilar(icdId, 10);
      setState({ status: "ready", results });
    } catch (err: unknown) {
      const code = (err as Partial<ApiError>)?.error?.code;
      if (code === "VALIDATION_ERROR") {
        setState({ status: "no-embedding" });
      } else if (code === "SERVICE_UNAVAILABLE") {
        setState({ status: "unavailable" });
      } else {
        setState({ status: "error", message: extractMessage(err) });
      }
    }
  }, [icdId]);

  return (
    <section data-testid="similar-icds-panel" className={styles.panel}>
      <div className={styles.header}>
        <h4 className={styles.heading}>
          {t("icds.similar.heading", "Similar ICDs")}
        </h4>
        <button
          type="button"
          className={styles.findButton}
          data-testid="find-similar-icds-btn"
          onClick={() => void handleFindSimilar()}
          disabled={state.status === "loading"}
        >
          {state.status === "loading"
            ? t("loading", "Loading…")
            : t("icds.similar.findButton", "Find Similar")}
        </button>
      </div>

      {state.status === "no-embedding" && (
        <p
          data-testid="similar-icds-no-embedding"
          className={styles.mutedText}
        >
          {t(
            "icds.similar.noEmbedding",
            "No embedding available — similarity search not possible."
          )}
        </p>
      )}

      {state.status === "unavailable" && (
        <p
          data-testid="similar-icds-unavailable"
          className={styles.mutedText}
        >
          {t(
            "icds.similar.unavailable",
            "Similarity search is temporarily unavailable."
          )}
        </p>
      )}

      {state.status === "error" && (
        <p
          role="alert"
          data-testid="similar-icds-error"
          className={styles.errorText}
        >
          {state.message}
        </p>
      )}

      {state.status === "ready" && state.results.length === 0 && (
        <p
          data-testid="similar-icds-empty"
          className={styles.mutedText}
        >
          {t("icds.similar.empty", "No similar ICDs found.")}
        </p>
      )}

      {state.status === "ready" && state.results.length > 0 && (
        <ul
          data-testid="similar-icds-results"
          className={styles.results}
        >
          {state.results.map((hit) => (
            <li key={hit.icd_id}>
              <button
                type="button"
                data-testid={`similar-icd-result-${hit.icd_id}`}
                onClick={() => onSelect(hit.icd_id)}
                className={styles.resultButton}
              >
                <span className={styles.resultName}>
                  {hit.name}
                  {hit.interface_type ? ` · ${hit.interface_type}` : ""}
                </span>
                <span className={styles.resultMeta}>
                  {`${Math.round(hit.similarity_score * 100)}%`}
                  {` · v${hit.version_number}`}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
