/**
 * ARCH-L1-001 ReactFrontend — SimilarRequirementsPanel (COMP-RF-003)
 *
 * req_id: REQ-L2-VS-004 (semantic similarity search)
 *
 * Renders a "Find Similar" action for a requirement and, on demand, a list of
 * the most semantically similar requirements (cosine similarity over pgvector
 * embeddings). Handles the two backend degradation cases explicitly:
 *   - 400 VALIDATION_ERROR: the requirement has no embedding yet.
 *   - 503 SERVICE_UNAVAILABLE: pgvector is not available.
 */

import { useCallback, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { requirementsApi } from '../../api/requirements';
import { extractErrorMessage } from '../../api/client';
import type { ApiError, SimilarRequirement, UUID } from '../../types';

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
      style={{
        marginTop: 'var(--space-4)',
        padding: 'var(--space-3)',
        background: 'var(--color-surface-raised)',
        border: '1px solid var(--color-border)',
        borderRadius: 'var(--radius-md)',
      }}
    >
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          gap: 'var(--space-2)',
          marginBottom: 'var(--space-2)',
        }}
      >
        <h4
          style={{
            fontSize: 'var(--font-size-md)',
            fontWeight: 600,
            margin: 0,
            color: 'var(--color-text)',
          }}
        >
          {t('requirements.similar.heading', 'Similar Requirements')}
        </h4>
        <button
          data-testid="find-similar-btn"
          onClick={() => void handleFindSimilar()}
          disabled={state.status === 'loading'}
          style={{
            background: 'var(--color-primary)',
            color: 'white',
            border: 'none',
            borderRadius: 'var(--radius-md)',
            padding: 'var(--space-2) var(--space-4)',
            fontSize: 'var(--font-size-sm)',
            cursor: state.status === 'loading' ? 'not-allowed' : 'pointer',
            opacity: state.status === 'loading' ? 0.6 : 1,
            fontWeight: 600,
          }}
        >
          {state.status === 'loading'
            ? t('loading', 'Loading…')
            : t('requirements.similar.findButton', 'Find Similar')}
        </button>
      </div>

      {state.status === 'no-embedding' && (
        <p
          data-testid="similar-no-embedding"
          style={{ color: 'var(--color-text-muted)', fontSize: 'var(--font-size-sm)', margin: 0 }}
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
          style={{ color: 'var(--color-text-muted)', fontSize: 'var(--font-size-sm)', margin: 0 }}
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
          style={{ color: 'var(--color-danger)', fontSize: 'var(--font-size-sm)', margin: 0 }}
        >
          {state.message}
        </p>
      )}

      {state.status === 'ready' && state.results.length === 0 && (
        <p
          data-testid="similar-empty"
          style={{ color: 'var(--color-text-muted)', fontSize: 'var(--font-size-sm)', margin: 0 }}
        >
          {t('requirements.similar.empty', 'No similar requirements found.')}
        </p>
      )}

      {state.status === 'ready' && state.results.length > 0 && (
        <ul
          data-testid="similar-results"
          style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: 'var(--space-1)' }}
        >
          {state.results.map((hit) => (
            <li key={hit.id}>
              <button
                data-testid={`similar-result-${hit.id}`}
                onClick={() => onSelect(hit.id)}
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  gap: 'var(--space-2)',
                  width: '100%',
                  textAlign: 'left',
                  background: 'var(--color-surface)',
                  color: 'var(--color-text)',
                  border: '1px solid var(--color-border)',
                  borderRadius: 'var(--radius-md)',
                  padding: 'var(--space-2) var(--space-3)',
                  fontSize: 'var(--font-size-sm)',
                  cursor: 'pointer',
                }}
              >
                <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {hit.uid ? `${hit.uid} · ` : ''}
                  {hit.title}
                </span>
                <span
                  style={{
                    flexShrink: 0,
                    color: 'var(--color-text-muted)',
                    fontVariantNumeric: 'tabular-nums',
                  }}
                >
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
