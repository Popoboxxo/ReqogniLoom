/**
 * Mirrors `_PROTECTED_PATCH_FIELDS`
 * (backend/rest_api/mixins/workflow_transitions.py) so an
 * `*ArtifactForm`-driven PATCH body can be checked, in a plain TS unit test,
 * for the exact failure class Task 19's C-1 fix round found: a field the
 * REST layer rejects outright on PATCH leaking through because the form
 * spreads a full GET payload into its values with no filter.
 *
 * Kept as a manually-synced literal copy (no cross-language import is
 * possible) rather than re-deriving it — if the backend set changes, update
 * this one too. Every rollout wave's `<ItemType>ArtifactForm.test.tsx` should
 * import `assertNoProtectedPatchFields` and run it against a REALISTIC,
 * full GET-shaped fixture (every field the real serializer returns), not a
 * minimal hand-built one — a minimal fixture is exactly what let the
 * original Risk bug (`uid`) ship undetected.
 */
import { expect } from "vitest";

export const PROTECTED_PATCH_FIELDS = new Set([
  "artifact_id",
  "created_at",
  "created_by_id",
  "id",
  "is_admin",
  "modified_by_id",
  "tenant_id",
  "updated_at",
  "uid",
  "version",
  "workspace_id",
]);

export function assertNoProtectedPatchFields(patch: Record<string, unknown>): void {
  const leaked = Object.keys(patch).filter((key) => PROTECTED_PATCH_FIELDS.has(key));
  expect(leaked).toEqual([]);
}
