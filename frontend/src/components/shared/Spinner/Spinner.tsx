/**
 * ARCH-L1-001 ReactFrontend — <Spinner> (2026-08-20 UI-feedback fix).
 *
 * Every async action across the app (interview chat send, AI derivation,
 * form save) previously gave the user no signal beyond a disabled button
 * and, at best, a text swap ("Save" -> "Saving...") — no animated
 * indicator anywhere in the codebase. This is the shared primitive: drop
 * `{busy && <Spinner />}` next to a button label. Not a replacement for
 * `<EmptyState loading>` (whole-view "hasn't loaded yet"); this is for a
 * single already-visible action waiting on its response.
 */
import styles from "./Spinner.module.css";

interface SpinnerProps {
  size?: "sm" | "md";
  /** Screen-reader label; the spinner itself is decorative (aria-hidden). */
  label?: string;
}

export function Spinner({ size = "sm", label = "Loading" }: SpinnerProps): JSX.Element {
  return (
    <>
      <span
        className={`${styles.spinner} ${size === "md" ? styles.md : styles.sm}`}
        aria-hidden="true"
        data-testid="spinner"
      />
      <span className={styles.srOnly}>{label}</span>
    </>
  );
}
