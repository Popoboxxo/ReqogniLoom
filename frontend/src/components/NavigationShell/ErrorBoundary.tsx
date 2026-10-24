/**
 * ARCH-L1-001 ReactFrontend — Top-Level Error Boundary.
 *
 * leaf_id: COMP-RF-001 (NavigationShell)
 * req_id:  REQ-L3-RF001-003 (Top-Level Error Boundary)
 *
 * Catches unhandled React errors in child components and renders a neutral,
 * translated message plus a reference id. The thrown error's raw message is
 * never rendered: it routinely carries internals (hosts, user names, driver
 * output) that must not reach the UI (#598 W4a). The reference id correlates
 * the screenshot with the console entry the same error produced.
 */

import { Component, type ErrorInfo, type ReactNode } from "react";
import styles from "./ErrorBoundary.module.css";

interface ErrorBoundaryProps {
  children: ReactNode;
  /** Label for "Reload" action — passed from parent with i18n */
  reloadLabel?: string;
  /** Label for "Back" action */
  backLabel?: string;
  /** Label for error title */
  errorTitle?: string;
  /** Neutral guidance shown instead of the raw error message. */
  hintLabel?: string;
  /** Label in front of the reference id ("Referenz" / "Reference"). */
  referenceLabel?: string;
}

interface ErrorBoundaryState {
  hasError: boolean;
  /** Correlates the rendered message with the console entry. */
  referenceId?: string;
}

/**
 * Build a collision-resistant, URL-safe reference id.
 *
 * Deliberately not `crypto.randomUUID`: that API is missing on non-secure
 * origins, and the deployed QA stack is served over plain HTTP — the fallback
 * would then throw inside the error boundary itself (review finding R2).
 */
function createReferenceId(): string {
  return (
    Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 8)
  );
}

export class ErrorBoundary extends Component<
  ErrorBoundaryProps,
  ErrorBoundaryState
> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(): ErrorBoundaryState {
    // The error object is intentionally not kept in state — nothing rendered
    // from it is safe to show, and holding it would tempt a future edit to
    // render the raw message again.
    return { hasError: true, referenceId: createReferenceId() };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    // Diagnostics stay in the console, keyed by the id the user sees.
    console.error(
      "[ErrorBoundary] Unhandled error",
      { referenceId: this.state.referenceId },
      error,
      errorInfo
    );
  }

  private handleReload = (): void => {
    window.location.reload();
  };

  private handleBack = (): void => {
    this.setState({ hasError: false, referenceId: undefined });
    window.history.back();
  };

  render(): ReactNode {
    const { hasError, referenceId } = this.state;
    if (!hasError) {
      return this.props.children;
    }

    const {
      reloadLabel = "Reload",
      backLabel = "Back",
      errorTitle = "An unexpected error occurred.",
      hintLabel = "Please reload the page. If the error persists, give support the reference.",
      referenceLabel = "Reference",
    } = this.props;

    return (
      <div role="alert" className={styles.wrapper}>
        <h2>{errorTitle}</h2>
        <p className={styles.message}>{hintLabel}</p>
        <p className={styles.reference} data-testid="error-reference">
          {referenceLabel}: <code>{referenceId}</code>
        </p>
        <div className={styles.actions}>
          <button className="btn-primary" onClick={this.handleReload} data-testid="error-reload-btn">{reloadLabel}</button>
          <button className="btn-secondary" onClick={this.handleBack} data-testid="error-back-btn">{backLabel}</button>
        </div>
      </div>
    );
  }
}
