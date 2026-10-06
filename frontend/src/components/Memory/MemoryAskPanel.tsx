/**
 * ARCH-L1-001 ReactFrontend — MemoryAskPanel ("Frag das Gedächtnis",
 * RFC #1002 #1155 Aspekt 1).
 *
 * Consumer of `POST /workspaces/{ws}/memory/ask/`: one free-text question in,
 * one natural-language answer out. Mounted twice:
 *   - `MemoryPage` — workspace scope, or the artifact scope once an artifact is
 *     selected there (that is what the endpoint's optional `artifact_id` is for);
 *   - `ArtifactMemoryPanel` — one artifact's scope.
 *
 * F9 shapes the whole result area. `degraded` and an empty answer are rendered
 * as two mutually exclusive states, never folded into one "no result" message:
 * "the engine could not answer" is a problem the user can act on (backend down,
 * unknown scope — `detail` names the cause), "the memory has nothing to say"
 * is not. A transport failure of the request itself is a third, separate state
 * (`error`), because it never produced an answer object at all.
 */

import { useCallback, useState } from "react";
import { useTranslation } from "react-i18next";
import { extractApiErrorMessage } from "../../api/client";
import {
  memoryApi,
  MEMORY_REASONING_LEVELS,
  type MemoryAnswer,
  type MemoryReasoningLevel,
} from "../../api/memory";
import type { UUID } from "../../types";
import { formatMemoryDate } from "./memory-format";
import styles from "./MemoryAskPanel.module.css";

/** i18n key per reasoning level, so the dropdown labels stay translatable. */
const REASONING_LABEL_KEYS: Record<MemoryReasoningLevel, string> = {
  minimal: "memory.ask.reasoning.minimal",
  low: "memory.ask.reasoning.low",
  medium: "memory.ask.reasoning.medium",
  high: "memory.ask.reasoning.high",
  max: "memory.ask.reasoning.max",
};

export interface MemoryAskPanelProps {
  /** Workspace the question is routed through (the endpoint's path segment). */
  workspaceId: UUID;
  /**
   * When set, the question targets this artifact's memory instead of the
   * workspace's. The backend resolves the owning workspace itself, but the
   * path segment stays required, so an artifact mount always names both.
   */
  artifactId?: UUID;
  /** `data-testid` prefix; every mount stays individually addressable for E2E. */
  testIdPrefix?: string;
}

export function MemoryAskPanel({
  workspaceId,
  artifactId,
  testIdPrefix = "memory-ask",
}: MemoryAskPanelProps): JSX.Element {
  const { t } = useTranslation();

  const [query, setQuery] = useState("");
  // "" is the explicit "let the backend decide" choice, i.e. the field is
  // omitted from the request rather than sent as an empty level.
  const [reasoningLevel, setReasoningLevel] = useState<MemoryReasoningLevel | "">("");
  const [answer, setAnswer] = useState<MemoryAnswer | null>(null);
  const [isAsking, setIsAsking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [validationError, setValidationError] = useState<string | null>(null);

  const canSubmit = !isAsking && query.trim().length > 0;

  const handleAsk = useCallback(async (): Promise<void> => {
    const trimmed = query.trim();
    if (!trimmed) {
      // Reachable through the Ctrl+Enter shortcut while the button is disabled:
      // the key press reports why instead of doing nothing.
      setValidationError(t("memory.ask.queryRequired"));
      return;
    }
    setValidationError(null);
    setError(null);
    // A previous answer must never read as the answer to the new question.
    setAnswer(null);
    setIsAsking(true);
    try {
      const result = await memoryApi.ask(workspaceId, {
        query: trimmed,
        artifactId,
        reasoningLevel: reasoningLevel || undefined,
      });
      setAnswer(result);
    } catch (err: unknown) {
      setError(extractApiErrorMessage(err) ?? t("memory.ask.error"));
    } finally {
      setIsAsking(false);
    }
  }, [query, reasoningLevel, workspaceId, artifactId, t]);

  return (
    <section
      className={styles.panel}
      data-testid={`${testIdPrefix}-panel`}
      aria-label={t("memory.ask.heading")}
    >
      <h3 className={styles.heading}>{t("memory.ask.heading")}</h3>
      <p className={styles.hint}>{t("memory.ask.hint")}</p>

      <label className={styles.field}>
        {t("memory.ask.queryLabel")}
        <textarea
          data-testid={`${testIdPrefix}-input`}
          className={styles.textarea}
          rows={2}
          value={query}
          placeholder={t("memory.ask.queryPlaceholder")}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
              e.preventDefault();
              void handleAsk();
            }
          }}
        />
      </label>

      <div className={styles.controls}>
        <label className={styles.field}>
          {t("memory.ask.reasoningLabel")}
          <select
            data-testid={`${testIdPrefix}-reasoning`}
            className={styles.select}
            value={reasoningLevel}
            onChange={(e) =>
              setReasoningLevel(e.target.value as MemoryReasoningLevel | "")
            }
          >
            <option value="">{t("memory.ask.reasoningDefault")}</option>
            {MEMORY_REASONING_LEVELS.map((level) => (
              <option key={level} value={level}>
                {t(REASONING_LABEL_KEYS[level])}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          className="btn-primary"
          data-testid={`${testIdPrefix}-submit`}
          disabled={!canSubmit}
          onClick={() => void handleAsk()}
        >
          {isAsking ? "…" : t("memory.ask.submit")}
        </button>
      </div>
      <p className={styles.shortcutHint}>{t("memory.ask.keyboardHint")}</p>

      {validationError && (
        <p
          role="alert"
          data-testid={`${testIdPrefix}-validation`}
          className={styles.error}
        >
          {validationError}
        </p>
      )}
      {error && (
        <p role="alert" data-testid={`${testIdPrefix}-error`} className={styles.error}>
          {error}
        </p>
      )}
      {isAsking && (
        <p role="status" data-testid={`${testIdPrefix}-loading`} className={styles.loading}>
          {t("loading")}
        </p>
      )}

      {answer && (
        <div className={styles.result} data-testid={`${testIdPrefix}-result`}>
          {answer.degraded ? (
            <p
              role="status"
              data-testid={`${testIdPrefix}-degraded`}
              className={styles.degraded}
            >
              {t("memory.ask.degraded")}
            </p>
          ) : answer.answer ? (
            <p className={styles.answerText} data-testid={`${testIdPrefix}-answer`}>
              {answer.answer}
            </p>
          ) : (
            <p data-testid={`${testIdPrefix}-empty`} className={styles.empty}>
              {t("memory.ask.empty")}
            </p>
          )}

          {answer.detail && (
            <p data-testid={`${testIdPrefix}-detail`} className={styles.detail}>
              {t("memory.ask.detail", { detail: answer.detail })}
            </p>
          )}

          <p className={styles.meta}>
            <span data-testid={`${testIdPrefix}-backend`}>
              {t("memory.ask.backend", { backend: answer.backend })}
            </span>
            <span data-testid={`${testIdPrefix}-generated-at`}>
              {t("memory.ask.generatedAt", {
                date: formatMemoryDate(answer.generated_at),
              })}
            </span>
            {answer.derivation_status && (
              <span data-testid={`${testIdPrefix}-derivation`}>
                {t("memory.ask.derivation", { status: answer.derivation_status })}
              </span>
            )}
          </p>
        </div>
      )}
    </section>
  );
}
