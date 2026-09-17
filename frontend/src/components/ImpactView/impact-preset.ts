/**
 * Shared handoff contract between TraceabilityView's "Impact" artifact
 * picker and the canonical `/impact` route (issue #184 — de-duplicates the
 * two overlapping impact-analysis surfaces).
 *
 * TraceabilityView already has the workspace's artifacts + title map loaded
 * (for endpoint rendering), so it can pre-resolve a preset root artifact
 * without another network round-trip. ImpactView reads the preset once on
 * mount (one-shot — cleared immediately after) and, if present, skips its
 * own search step and loads the artifact straight into the tree.
 *
 * sessionStorage (not router state) is used deliberately: TraceabilityView
 * does not use react-router (its smoke tests render it outside a Router),
 * so the handoff must not depend on `useNavigate`/`Link`.
 */

export const IMPACT_PRESET_STORAGE_KEY = "reqlo-impact-preset";

export interface ImpactPreset {
  id: string;
  title: string;
  artifactType: string;
}
