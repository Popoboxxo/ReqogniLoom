/**
 * ARCH-L1-001 ReactFrontend — Top-Level Error Boundary.
 *
 * leaf_id: COMP-RF-001 (NavigationShell)
 * req_id:  REQ-L3-RF001-003 (Top-Level Error Boundary)
 *
 * Catches unhandled React errors in child components.
 * Renders a translated error message with recovery options.
 */

import { Component, type ErrorInfo, type ReactNode } from "react";

interface ErrorBoundaryProps {
  children: ReactNode;
  /** Label for "Reload" action — passed from parent with i18n */
  reloadLabel?: string;
  /** Label for "Back" action */
  backLabel?: string;
  /** Label for error title */
  errorTitle?: string;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error?: Error;
  errorInfo?: ErrorInfo;
}

export class ErrorBoundary extends Component<
  ErrorBoundaryProps,
  ErrorBoundaryState
> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    // Log to console — no stack-trace leakage to user (REQ-L3-RF001-003)
    console.error("[ErrorBoundary] Unhandled error:", error, errorInfo);
    this.setState({ errorInfo });
  }

  private handleReload = (): void => {
    window.location.reload();
  };

  private handleBack = (): void => {
    this.setState({ hasError: false, error: undefined, errorInfo: undefined });
    window.history.back();
  };

  render(): ReactNode {
    if (!this.state.hasError) {
      return this.props.children;
    }

    const {
      reloadLabel = "Reload",
      backLabel = "Back",
      errorTitle = "An unexpected error occurred.",
    } = this.props;

    return (
      <div
        role="alert"
        style={{
          padding: "2rem",
          textAlign: "center",
          fontFamily: "sans-serif",
        }}
      >
        <h2>{errorTitle}</h2>
        <p style={{ color: "#666", marginBottom: "1.5rem" }}>
          {this.state.error?.message ?? "Unknown error"}
        </p>
        <div style={{ display: "flex", gap: "1rem", justifyContent: "center" }}>
          <button onClick={this.handleReload}>{reloadLabel}</button>
          <button onClick={this.handleBack}>{backLabel}</button>
        </div>
      </div>
    );
  }
}
