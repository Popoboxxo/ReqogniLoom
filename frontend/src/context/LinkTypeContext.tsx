/**
 * Loads the active workspace's link-type catalog once and shares it.
 *
 * Every consumer that used to import `ALL_LINK_TYPES` reads from here instead,
 * so there is exactly one source of truth per workspace rather than a
 * hardcoded frontend list drifting from the backend (audit finding B4).
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import {
  linkTypesApi,
  type LinkTypeDefinition,
  type WorkspaceLinkType,
} from "../api/link-types";
import { useWorkspace } from "./WorkspaceContext";

type Lang = "de" | "en";
type Perspective = "downstream" | "upstream" | "neutral";

interface LinkTypeContextValue {
  linkTypes: WorkspaceLinkType[];
  isLoading: boolean;
  error: string | null;
  reload: () => Promise<void>;
  /** Only active, manually creatable types — what a link dialog may offer. */
  creatableLinkTypes: WorkspaceLinkType[];
  definitionFor: (key: string) => LinkTypeDefinition | undefined;
  isAllowedPair: (key: string, sourceType: string, targetType: string) => boolean;
  labelFor: (key: string, lang: Lang, perspective: Perspective) => string;
}

const LinkTypeContext = createContext<LinkTypeContextValue | undefined>(undefined);

/** `"TestCase:unit"` -> `"TestCase"`, mirroring the backend normalizer. */
function normalizeArtifactType(artifactType: string): string {
  return artifactType.split(":", 1)[0] ?? "";
}

export function LinkTypeProvider({ children }: { children: ReactNode }) {
  const { activeWorkspace } = useWorkspace();
  const [linkTypes, setLinkTypes] = useState<WorkspaceLinkType[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const workspaceId = activeWorkspace?.id;

  const reload = useCallback(async () => {
    if (!workspaceId) {
      setLinkTypes([]);
      return;
    }
    setIsLoading(true);
    setError(null);
    try {
      setLinkTypes(await linkTypesApi.listForWorkspace(workspaceId));
    } catch (err) {
      // A failed catalog load must not take the tree down: the link dialog
      // degrades to an empty type list and says so, rather than the whole
      // workspace view unmounting.
      setLinkTypes([]);
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsLoading(false);
    }
  }, [workspaceId]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const value = useMemo<LinkTypeContextValue>(() => {
    const byKey = new Map(linkTypes.map((row) => [row.key, row.definition]));

    return {
      linkTypes,
      isLoading,
      error,
      reload,
      creatableLinkTypes: linkTypes.filter(
        (row) => row.definition.active && row.definition.manual_creatable,
      ),
      definitionFor: (key) => byKey.get(key),
      isAllowedPair: (key, sourceType, targetType) => {
        const definition = byKey.get(key);
        // Unknown key: reject. The old frontend had no notion of an invalid
        // pair at all and let the backend 400 after the user hit Save.
        if (!definition) return false;
        const source = normalizeArtifactType(sourceType);
        const target = normalizeArtifactType(targetType);
        // A caller-supplied "*" is a wildcard too, not just a backend pair's
        // own "*" — e.g. "is `key` valid from this source to ANY target"
        // (CreateTraceLinkDialog, before the user has picked a target yet).
        // Without this, every pair whose backend target isn't literally "*"
        // (i.e. almost all of them) would spuriously reject a caller-side
        // "*" query, since "*" !== a real backend type string.
        return definition.allowed_pairs.some(
          (pair) =>
            (sourceType === "*" || pair.source_type === "*" || pair.source_type === source) &&
            (targetType === "*" || pair.target_type === "*" || pair.target_type === target),
        );
      },
      labelFor: (key, lang, perspective) =>
        byKey.get(key)?.label?.[lang]?.[perspective] ?? key,
    };
  }, [linkTypes, isLoading, error, reload]);

  return <LinkTypeContext.Provider value={value}>{children}</LinkTypeContext.Provider>;
}

export function useLinkTypes(): LinkTypeContextValue {
  const context = useContext(LinkTypeContext);
  if (context === undefined) {
    throw new Error("useLinkTypes must be used within a LinkTypeProvider");
  }
  return context;
}
