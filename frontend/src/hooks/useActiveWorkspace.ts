/**
 * `useWorkspace().activeWorkspace`, degraded to `null` when no
 * `WorkspaceProvider` is mounted.
 *
 * WHY THIS EXISTS
 * ---------------
 * `useWorkspace` throws outside a provider, deliberately: a route that cannot
 * work without a workspace must fail loudly instead of rendering against a
 * placeholder. Two hooks model "no workspace to resolve against" as an explicit,
 * documented state instead — `useArtifactDefinition` (`definition: null`) and
 * `useCreateFormFields` (`entries: null`, "render the plain attribute
 * definition"). For those, throwing on the very same condition is the
 * inconsistency: an isolated component test that renders a create dialog
 * without a provider has no workspace, which is precisely the degraded state
 * both hooks already handle.
 *
 * The reader is `useOptionalWorkspace` (exported by `WorkspaceContext.tsx`),
 * NOT a `try`/`catch` around `useWorkspace`: a catch would turn any future
 * throw from inside the provider into a silent "no workspace" state instead of
 * surfacing it. It is called unconditionally on every render, so the hook order
 * stays stable.
 */

import { useOptionalWorkspace } from "../context/WorkspaceContext";
import type { Workspace } from "../types";

export function useActiveWorkspace(): Workspace | null {
  return useOptionalWorkspace()?.activeWorkspace ?? null;
}
