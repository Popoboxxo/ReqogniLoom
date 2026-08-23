/**
 * ARCH-L1-001 ReactFrontend — <EmptyState> (UI concept ch. 12.7 and 13.1).
 *
 * Every view has six states — loading, empty, no-match, error, forbidden,
 * filled — and today none of them are consistently distinguished. The
 * audit's headline finding (ch. 13.3): **empty** and **no-match** look
 * identical across the codebase, even though they demand different next
 * steps. "There is nothing" wants *create*. "There is something, just not
 * under this filter" wants *reset the filter* — a "New Requirement" button
 * in the filtered case answers the wrong question with the wrong action.
 *
 * The contract, in full:
 *   - three roles: a title (what is missing), one sentence (what would
 *     exist here and why), and actions (the next step),
 *   - `loading` shows nothing for the first 300 ms (ch. 13.2) so a fast
 *     response never flashes a placeholder,
 *   - `no-match` only ever offers "reset filters" — the props for this
 *     variant have no room for a create action, by construction,
 *   - `error` renders `role="alert"` and offers "try again",
 *   - `forbidden` names the missing role and who can grant it,
 *   - `filled` renders nothing — a no-op for call sites that embed
 *     <EmptyState> unconditionally next to their real content.
 *
 * The variant discriminates the prop set at the type level: passing a
 * create action to `no-match`, or omitting `onRetry` from `error`, is a
 * compile error, not a code review comment.
 */

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import styles from "./EmptyState.module.css";

/** How long a `loading` placeholder stays invisible before it renders (ch. 13.2). */
const LOADING_REVEAL_DELAY_MS = 300;

export interface EmptyStateAction {
  label: string;
  onClick: () => void;
  testId?: string;
  /**
   * Overrides the accessible name (falls back to `label`). Use when a call
   * site's `label` text collides with another simultaneously-rendered
   * control (issue #678), e.g. a page-header "create" action and this
   * empty-state's own "create" action sharing the same visible wording.
   */
  ariaLabel?: string;
}

interface EmptyStateLoadingProps {
  variant: "loading";
  /** Accessible label for the placeholder, e.g. "Requirements werden geladen". */
  label?: string;
  testId?: string;
}

interface EmptyStateFilledProps {
  variant: "filled";
}

interface EmptyStateEmptyProps {
  variant: "empty";
  title: string;
  description: string;
  /** e.g. "Neues Requirement" and, optionally, "CSV importieren" (ch. 12.7). */
  actions?: EmptyStateAction[];
  testId?: string;
}

interface EmptyStateNoMatchProps {
  variant: "no-match";
  title?: string;
  description?: string;
  /** The only action this variant can offer — never a create action. */
  onResetFilters: () => void;
  resetFiltersLabel?: string;
  testId?: string;
}

interface EmptyStateErrorProps {
  variant: "error";
  title: string;
  description: string;
  onRetry: () => void;
  retryLabel?: string;
  testId?: string;
}

interface EmptyStateForbiddenProps {
  variant: "forbidden";
  /** The role that would be required, e.g. "Editor". */
  requiredRole: string;
  /** Who can grant it, e.g. "Wende dich an den Workspace-Administrator." */
  grantedBy: string;
  title?: string;
  testId?: string;
}

export type EmptyStateProps =
  | EmptyStateLoadingProps
  | EmptyStateFilledProps
  | EmptyStateEmptyProps
  | EmptyStateNoMatchProps
  | EmptyStateErrorProps
  | EmptyStateForbiddenProps;

function ActionButton({
  action,
  variant,
  testId,
}: {
  action: EmptyStateAction;
  variant: "primary" | "secondary";
  testId: string;
}): JSX.Element {
  return (
    <button
      type="button"
      className={variant === "primary" ? styles.primaryButton : styles.secondaryButton}
      data-testid={testId}
      aria-label={action.ariaLabel}
      onClick={action.onClick}
    >
      {action.label}
    </button>
  );
}

export function EmptyState(props: EmptyStateProps): JSX.Element | null {
  const { t } = useTranslation();
  const testId = "testId" in props ? (props.testId ?? "empty-state") : "empty-state";

  // ch. 13.2: a `loading` placeholder must not flash on fast responses.
  // It stays invisible for the first 300 ms and only then mounts.
  const [loadingVisible, setLoadingVisible] = useState(false);
  useEffect(() => {
    if (props.variant !== "loading") {
      setLoadingVisible(false);
      return undefined;
    }
    const timer = setTimeout(() => setLoadingVisible(true), LOADING_REVEAL_DELAY_MS);
    return () => clearTimeout(timer);
  }, [props.variant]);

  if (props.variant === "filled") return null;

  if (props.variant === "loading") {
    if (!loadingVisible) return null;
    return (
      <div
        className={styles.root}
        role="status"
        aria-live="polite"
        aria-label={props.label ?? t("emptyState.loading.label", "Lädt")}
        data-testid={props.testId ?? testId}
      >
        <div className={styles.skeleton} aria-hidden="true">
          <div className={`${styles.skeletonLine} ${styles.skeletonLineWide}`} />
          <div className={`${styles.skeletonLine} ${styles.skeletonLineMedium}`} />
          <div className={`${styles.skeletonLine} ${styles.skeletonLineNarrow}`} />
        </div>
      </div>
    );
  }

  if (props.variant === "empty") {
    return (
      <div className={styles.root} data-testid={props.testId ?? testId}>
        <p className={styles.title}>{props.title}</p>
        <p className={styles.description}>{props.description}</p>
        {props.actions && props.actions.length > 0 && (
          <div className={styles.actions}>
            {props.actions.map((action, index) => (
              <ActionButton
                key={action.testId ?? action.label}
                action={action}
                variant={index === 0 ? "primary" : "secondary"}
                testId={action.testId ?? `${props.testId ?? testId}-action-${index}`}
              />
            ))}
          </div>
        )}
      </div>
    );
  }

  if (props.variant === "no-match") {
    const title = props.title ?? t("emptyState.noMatch.title", "Kein Treffer");
    const description =
      props.description ??
      t(
        "emptyState.noMatch.description",
        "Es gibt Einträge, aber keiner passt zum aktuellen Filter.",
      );
    return (
      <div className={styles.root} data-testid={props.testId ?? testId}>
        <p className={styles.title}>{title}</p>
        <p className={styles.description}>{description}</p>
        <div className={styles.actions}>
          <button
            type="button"
            className={styles.primaryButton}
            data-testid={`${props.testId ?? testId}-reset-filters`}
            onClick={props.onResetFilters}
          >
            {props.resetFiltersLabel ?? t("editor.resetFilters", "Filter zurücksetzen")}
          </button>
        </div>
      </div>
    );
  }

  if (props.variant === "error") {
    return (
      <div className={styles.root} role="alert" data-testid={props.testId ?? testId}>
        <p className={styles.title}>{props.title}</p>
        <p className={styles.description}>{props.description}</p>
        <div className={styles.actions}>
          <button
            type="button"
            className={styles.primaryButton}
            data-testid={`${props.testId ?? testId}-retry`}
            onClick={props.onRetry}
          >
            {props.retryLabel ?? t("emptyState.error.retryLabel", "Erneut versuchen")}
          </button>
        </div>
      </div>
    );
  }

  // variant === "forbidden"
  return (
    <div className={styles.root} data-testid={props.testId ?? testId}>
      <p className={styles.title}>
        {props.title ?? t("emptyState.forbidden.title", "Keine Berechtigung")}
      </p>
      <p className={styles.description}>
        {t("emptyState.forbidden.requiredRole", "Dafür wird die Rolle „{{role}}“ benötigt.", {
          role: props.requiredRole,
        })}
      </p>
      <p className={styles.description}>{props.grantedBy}</p>
    </div>
  );
}
