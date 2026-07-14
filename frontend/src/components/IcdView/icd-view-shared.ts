/**
 * ARCH-L1-001 ReactFrontend — IcdView shared helpers & styles.
 *
 * leaf_id: COMP-RF-001 (IcdView)
 * req_id:  REQ-L2-ICD-001 (ICD CRUD + versioning),
 *          REQ-006 (similar-interface detection),
 *          REQ-050 (Container/Presenter decomposition — shared snippets)
 *
 * Pure helpers, the Jaccard name-similarity used by the "Similar Interfaces"
 * panel, and the token-based form styles shared by the IcdView container and
 * the IcdDetailPane presenter. Extracted from the former monolithic IcdView.
 */

import type { Icd } from "../../api/icds";

export function shortId(id: string): string {
  return `${id.slice(0, 8)}…`;
}

export function parseListField(value: string): string[] {
  return value
    .split("\n")
    .map((s) => s.trim())
    .filter((s) => s.length > 0);
}

export function joinListField(values: string[] | undefined): string {
  return Array.isArray(values) ? values.join("\n") : "";
}

export function extractErrorMessage(err: unknown, fallback: string): string {
  const e = err as { error?: { message?: string } };
  return e?.error?.message ?? (err ? String(err) : fallback);
}

// Similarity algorithm: tokenize ICD names and compute Jaccard similarity
function tokenize(name: string): Set<string> {
  return new Set(
    name
      .toLowerCase()
      .split(/[\s\-_/]+/)
      .filter((t) => t.length > 2),
  );
}

function similarity(a: string, b: string): number {
  const ta = tokenize(a);
  const tb = tokenize(b);
  const intersection = new Set([...ta].filter((t) => tb.has(t)));
  const union = new Set([...ta, ...tb]);
  return union.size > 0 ? intersection.size / union.size : 0;
}

export function findSimilarICDs(
  current: Icd,
  allICDs: Icd[],
  threshold = 0.5,
): Array<{ icd: Icd; score: number }> {
  return allICDs
    .filter((icd) => icd.id !== current.id)
    .map((icd) => ({ icd, score: similarity(current.name, icd.name) }))
    .filter(({ score }) => score >= threshold)
    .sort((a, b) => b.score - a.score);
}

export const labelStyle: React.CSSProperties = {
  display: "block",
  fontWeight: 500,
  color: "var(--color-text)",
  marginTop: "var(--space-3)",
  marginBottom: "var(--space-1)",
  fontSize: "var(--font-size-sm)",
};

export const inputStyle: React.CSSProperties = {
  width: "100%",
  border: "1px solid var(--color-border)",
  borderRadius: "var(--radius-md)",
  padding: "var(--space-3)",
  fontSize: "var(--font-size-base)",
  background: "var(--color-surface)",
  color: "var(--color-text)",
  boxSizing: "border-box",
};
