import * as React from "react";

export const buttonStyle: React.CSSProperties = {
  background: "var(--accent)",
  color: "var(--bg-1)",
  border: "none",
  borderRadius: "var(--radius-sm)",
  padding: "6px 12px",
  cursor: "pointer",
  fontSize: "var(--text-xs)",
};

// `testId` is optional and additive so every caller keeps the plain banner,
// while the requirement views can address theirs (requirement-error) without
// wrapping it in a second element.
export function ErrorBanner({
  message,
  testId,
}: {
  message: string | null;
  testId?: string;
}): JSX.Element | null {
  if (!message) return null;
  return (
    <span data-testid={testId} style={{ color: "var(--danger, red)", fontSize: "var(--text-xs)" }}>
      {message}
    </span>
  );
}
