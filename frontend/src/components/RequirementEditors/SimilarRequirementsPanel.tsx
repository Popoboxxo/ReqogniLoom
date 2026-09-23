/**
 * ARCH-L1-001 ReactFrontend — SimilarRequirementsPanel (COMP-RF-003)
 *
 * req_id: REQ-L2-VS-004 (semantic similarity search)
 *
 * Renders a "Find Similar" action for a requirement and, on demand, a list of
 * the most semantically similar requirements (cosine similarity over pgvector
 * embeddings). Handles the backend degradation cases:
 *   - 200 with an empty list: ambiguous by design. It can mean no embedding
 *     could be produced (the backend now generates a missing embedding lazily
 *     per issue #847 and degrades to an empty result instead of failing), but
 *     it can just as well mean the search ran and found nothing similar. Both
 *     render as the ordinary "no similar requirements" empty state.
 *   - 400 VALIDATION_ERROR: defensive-only. The backend no longer returns this
 *     for a missing embedding (#847); the branch is kept so an older backend
 *     cannot surface as a generic error.
 *   - 503 SERVICE_UNAVAILABLE: pgvector is not available.
 */

import { useCallback, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { requirementsApi } from '../../api/requirements';
import { extractErrorMessage } from '../../api/client';
import type { ApiError, SimilarRequirement, UUID } from '../../types';
import styles from './SimilarRequirementsPanel.module.css';

interface SimilarRequirementsPanelProps {
  requirementId: UUID;
  /** Navigate to another requirement when a hit is clicked. */
  onSelect: (id: UUID) => void;
}

type PanelState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'no-embedding' }
  | { status: 'unavailable' }
  | { status: 'error'; message: string }
  | { status: 'ready'; results: SimilarRequirement[] };

export function SimilarRequirementsPanel({
  requirementId,
  onSelect,
}: SimilarRequirementsPanelProps): JSX.Element {
  const { t } = useTranslation();
  const [state, setState] = useState<PanelState>({ status: 'idle' });

  const handleFindSimilar = useCallback(async (): Promise<void> => {
    setState({ status: 'loading' });
    try {
      const results = await requirementsApi.getSimilarRequirements(requirementId, 10);
      setState({ status: 'ready', results });
    } catch (err: unknown) {
      const code = (err as Partial<ApiError>)?.error?.code;
      if (code === 'VALIDATION_ERROR') {
        setState({ status: 'no-embedding' });
      } else if (code === 'SERVICE_UNAVAILABLE') {
        setState({ status: 'unavailable' });
      } else {
        setState({ status: 'error', message: extractErrorMessage(err) });
      }
    }
  }, [requirementId]);

  return (
    <section
      data-testid="similar-requirements-panel"
      className={styles.panel}
    >
      <div className={styles.header}>
        <h4 className={styles.heading}>
          {t('requirements.similar.heading', 'Similar Requirements')}
        </h4>
        {/* Issue #926 (part 2): the hand-rolled inline-styled primary button
            moved onto the canonical `btn-primary` class, so its height/radius
            match every other button (the `:disabled` opacity/cursor come from
            the shared `.btn-primary:disabled` rule). */}
        <button
          type="button"
          className="btn-primary"
          data-testid="find-similar-btn"
          onClick={() => void handleFindSimilar()}
          disabled={state.status === 'loading'}
        >
          {state.status === 'loading'
            ? t('loading', 'Loading…')
            : t('requirements.similar.findButton', 'Find Similar')}
        </button>
      </div>

      {/* Defensive-only since issue #847: the backend generates a missing
          embedding lazily and degrades to an empty 'ready' result, so this
          400 VALIDATION_ERROR branch is no longer expected to be reached. */}
      {state.status === 'no-embedding' && (
        <p
          data-testid="similar-no-embedding"
          className={styles.mutedText}
        >
          {t(
            'requirements.similar.noEmbedding',
            'No embedding available — similarity search not possible.'
          )}
        </p>
      )}

      {state.status === 'unavailable' && (
        <p
          data-testid="similar-unavailable"
          className={styles.mutedText}
        >
          {t(
            'requirements.similar.unavailable',
            'Similarity search is temporarily unavailable.'
          )}
        </p>
      )}

      {state.status === 'error' && (
        <p
          role="alert"
          data-testid="similar-error"
          className={styles.errorText}
        >
          {state.message}
        </p>
      )}

      {state.status === 'ready' && state.results.length === 0 && (
        <p
          data-testid="similar-empty"
          className={styles.mutedText}
        >
          {t('requirements.similar.empty', 'No similar requirements found.')}
        </p>
      )}

      {state.status === 'ready' && state.results.length > 0 && (
        <ul
          data-testid="similar-results"
          className={styles.results}
        >
          {state.results.map((hit) => (
            <li key={hit.id}>
              <button
                data-testid={`similar-result-${hit.id}`}
                onClick={() => onSelect(hit.id)}
                className={styles.resultButton}
              >
                <span className={styles.resultName}>
                  {hit.uid ? `${hit.uid} · ` : ''}
                  {hit.title}
                </span>
                <span className={styles.resultMeta}>
                  {`${Math.round(hit.similarity_score * 100)}%`}
                  {hit.status ? ` · ${hit.status}` : ''}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
