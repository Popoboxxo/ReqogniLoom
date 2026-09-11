/**
 * AttributeEditorPage (Task 26, spec section 6.1).
 *
 * Shell reused from the workflow editor where the two are actually
 * type-compatible: `PresetSegmentedControl` (a plain 3-way
 * `WorkspacePreset` switch, no domain coupling) and the global-scope
 * query-string contract (`entityType`/`preset`) are shared verbatim with
 * `WorkflowEditorPage`.
 *
 * DEVIATION from the plan's literal snippet: the entity-type picker is a
 * small local `<select>`, not the `WorkflowEditor`'s `EntityTypeSelector`.
 * `EntityTypeSelector` is typed to `WorkflowEntityType` (9 members, includes
 * `MainGoal`) while attribute definitions are keyed by `AttributeItemType`
 * (10 members, includes `Icd`/`GlossaryTerm` instead) — the two unions are
 * genuinely incompatible (`attribute-definitions.ts`'s own docstring already
 * flags this as a "silent 404 instead of a compile error" trap). Reusing the
 * real component would also fire one `useWorkflowData` workflow-graph fetch
 * per entity type just to render a "N states" badge that has no meaning in
 * an attribute editor. Only the type-compatible pieces are shared; the
 * type-INcompatible piece gets its own minimal, correctly-typed equivalent.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useMatch, useNavigate, useParams, useSearchParams } from "react-router-dom";

import {
  attributeDefinitionsApi,
  type AttributeItemType,
  type AttributeOrigin,
  type AttributeSpec,
  type NewAttributeInput,
} from "../../api/attribute-definitions";
import { extractErrorMessage } from "../../api/client";
import type { WorkspacePreset } from "../../types";
import { useAuth } from "../../context/AuthContext";
import { useWorkspace } from "../../context/WorkspaceContext";
import { ConfirmDialog } from "../shared/ConfirmDialog";
import { useToast } from "../shared/Toast/useToast";
import { PresetSegmentedControl } from "../WorkflowEditor/PresetSegmentedControl";
import { WORKFLOW_PRESETS } from "../WorkflowEditor/constants";
import styles from "./AttributeEditor.module.css";
import { AttributeCreateDialog } from "./AttributeCreateDialog";
import { AttributeInspector } from "./AttributeInspector";
import { AttributeList } from "./AttributeList";
import { AttributeTable } from "./AttributeTable";
import {
  deleteSection,
  moveAttribute,
  moveSection,
  patchAttribute,
  renameSection,
} from "./attribute-edits";

/** The 10 bootstrapped item types (`AttributeItemType`, see
 * `api/attribute-definitions.ts`) — deliberately its own list, not
 * `WORKFLOW_ENTITY_TYPES` (see module docstring above). */
const ATTRIBUTE_ITEM_TYPES: readonly AttributeItemType[] = [
  "Requirement",
  "StakeholderNeed",
  "ArchitectureElement",
  "TestCase",
  "Adr",
  "Risk",
  "Issue",
  "Goal",
  "Icd",
  "GlossaryTerm",
  "ChangeRequest",
];

const DEFAULT_ITEM_TYPE: AttributeItemType = "Requirement";

type ViewMode = "list" | "table";
const VIEW_MODE_STORAGE_KEY = "attributeEditor.viewMode";

function loadViewMode(): ViewMode {
  try {
    return localStorage.getItem(VIEW_MODE_STORAGE_KEY) === "table" ? "table" : "list";
  } catch {
    // Private browsing / storage disabled — default silently, this is a
    // per-viewer convenience, never load-bearing.
    return "list";
  }
}

function itemTypeFromSlug(slug: string | undefined): AttributeItemType | null {
  if (!slug) return null;
  const match = ATTRIBUTE_ITEM_TYPES.find((t) => t.toLowerCase() === slug.toLowerCase());
  return match ?? null;
}

export interface AttributeEditorPageProps {
  /** `"workspace"` (default) edits the override; `"global"` the tenant default. */
  scope?: "workspace" | "global";
}

export function AttributeEditorPage({
  scope = "workspace",
}: AttributeEditorPageProps = {}): JSX.Element {
  const { t } = useTranslation();
  const isGlobal = scope === "global";
  const { entityType: entitySlug } = useParams<{ entityType: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const { activeWorkspace } = useWorkspace();
  const { roles } = useAuth();
  const isAdmin = roles.includes("admin");

  // Whether this instance is actually mounted under the routed
  // `/attributes/*` path (standalone page, `NavigationShell.tsx`) as opposed
  // to embedded elsewhere with no `:entityType` route param at all
  // (`WorkspaceSettings.tsx`'s "Attributes" tab, `SystemSettings.tsx`'s
  // "Attribute Defaults" tab). Only the routed case has a slug to read;
  // every embedded mount must carry its selection in a query param instead,
  // or switching types would navigate the host page away entirely (it did,
  // before this check existed — see code-review finding).
  const isRouted = useMatch("/attributes/*") !== null;

  const itemType: AttributeItemType =
    itemTypeFromSlug(isRouted ? entitySlug : searchParams.get("entityType") ?? undefined) ??
    DEFAULT_ITEM_TYPE;
  const preset = (WORKFLOW_PRESETS.find((p) => p === searchParams.get("preset")) ??
    "standard") as WorkspacePreset;

  const [attributes, setAttributes] = useState<AttributeSpec[]>([]);
  const [loaded, setLoaded] = useState<AttributeSpec[]>([]);
  const [isCustomized, setIsCustomized] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const [emptySections, setEmptySections] = useState<string[]>([]);
  const [newSection, setNewSection] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const toast = useToast();
  const [saving, setSaving] = useState(false);
  const [confirmReset, setConfirmReset] = useState(false);
  const [createSection, setCreateSection] = useState<string | null>(null);
  const [origins, setOrigins] = useState<Record<string, AttributeOrigin>>({});
  const [viewMode, setViewMode] = useState<ViewMode>(loadViewMode);

  const handleSetViewMode = useCallback((mode: ViewMode): void => {
    setViewMode(mode);
    try {
      localStorage.setItem(VIEW_MODE_STORAGE_KEY, mode);
    } catch {
      // Same non-load-bearing fallback as loadViewMode above.
    }
  }, []);

  const load = useCallback(async (): Promise<void> => {
    setError(null);
    try {
      if (isGlobal) {
        const definition = await attributeDefinitionsApi.getGlobal(itemType, preset);
        setAttributes(definition.attributes);
        setLoaded(definition.attributes);
        setIsCustomized(false);
        setOrigins({});
      } else {
        if (!activeWorkspace?.id) return;
        const definition = await attributeDefinitionsApi.getWorkspace(
          activeWorkspace.id,
          itemType
        );
        setAttributes(definition.attributes);
        setLoaded(definition.attributes);
        setIsCustomized(definition.is_customized);
        setOrigins(definition.origins);
      }
    } catch (exc: unknown) {
      setError(extractErrorMessage(exc));
    }
  }, [activeWorkspace?.id, isGlobal, itemType, preset]);

  useEffect(() => {
    void load();
  }, [load]);

  // Selection/scratch state is scoped to one (itemType, preset) view — carrying
  // it across a switch risks matching an unrelated attribute of the same name
  // on the newly loaded type (e.g. both Risk and Issue have a "title").
  useEffect(() => {
    setSelected(null);
    setEmptySections([]);
    setNewSection(null);
  }, [itemType, preset, isGlobal]);

  const isDirty = useMemo(
    () => JSON.stringify(attributes) !== JSON.stringify(loaded),
    [attributes, loaded]
  );

  const selectedAttribute = attributes.find((a) => a.name === selected) ?? null;

  const handleSave = useCallback(async (): Promise<void> => {
    setSaving(true);
    setError(null);
    toast.clear();
    try {
      if (isGlobal) {
        const result = await attributeDefinitionsApi.putGlobal(
          itemType,
          preset,
          attributes
        );
        setAttributes(result.attributes);
        setLoaded(result.attributes);
        if (typeof result.propagated_workspace_count === "number") {
          toast.show(
            t("attributes.propagated", { count: result.propagated_workspace_count })
          );
        }
      } else if (activeWorkspace?.id) {
        const result = await attributeDefinitionsApi.putWorkspace(
          activeWorkspace.id,
          itemType,
          attributes
        );
        setAttributes(result.attributes);
        setLoaded(result.attributes);
        setIsCustomized(result.is_customized);
        setOrigins(result.origins);
      }
    } catch (exc: unknown) {
      setError(extractErrorMessage(exc));
    } finally {
      setSaving(false);
    }
  }, [activeWorkspace?.id, attributes, isGlobal, itemType, preset, t]);

  const handleReset = useCallback(async (): Promise<void> => {
    if (!activeWorkspace?.id) return;
    setConfirmReset(false);
    try {
      const result = await attributeDefinitionsApi.resetWorkspace(
        activeWorkspace.id,
        itemType
      );
      setAttributes(result.attributes);
      setLoaded(result.attributes);
      setIsCustomized(result.is_customized);
      setOrigins(result.origins);
    } catch (exc: unknown) {
      setError(extractErrorMessage(exc));
    }
  }, [activeWorkspace?.id, itemType]);

  // NOTE (deviation from the plan's literal snippet): `renameSection` and
  // `deleteSection` can throw. Calling them from INSIDE a `setState` updater
  // (`setAttributes((current) => renameSection(current, ...))`, as the plan's
  // own snippet did) does not work — React invokes that updater during its
  // own render pass, outside this function's call stack, so the surrounding
  // try/catch never sees the throw and it becomes an uncaught render-phase
  // error instead of a caught, displayed `attribute-editor-error`
  // (live-reproduced by the "refuses to delete a section that still holds
  // attributes" test). Validating synchronously against the already-known
  // `attributes` state before calling `setAttributes` fixes it.
  const handleRenameSection = useCallback(
    (from: string, to: string): void => {
      setError(null);
      try {
        const next = renameSection(attributes, from, to);
        setAttributes(next);
        setEmptySections((current) =>
          current.map((s) => (s === from ? to.trim() : s)).filter(Boolean)
        );
      } catch (exc: unknown) {
        setError(exc instanceof Error ? exc.message : String(exc));
      }
    },
    [attributes]
  );

  const handleDeleteSection = useCallback(
    (name: string): void => {
      setError(null);
      try {
        // Throws when the section still holds attributes — spec section 6.1
        // allows deleting an EMPTY section only.
        const next = deleteSection(attributes, name);
        setAttributes(next);
        setEmptySections((current) => current.filter((s) => s !== name));
      } catch (exc: unknown) {
        setError(exc instanceof Error ? exc.message : String(exc));
      }
    },
    [attributes]
  );

  const handleMoveSection = useCallback((name: string, toIndex: number): void => {
    setAttributes((current) => moveSection(current, name, toIndex));
  }, []);

  // The inspector's free-text section field moves a single attribute into a
  // (possibly new) section, same as a drag in `AttributeList` — so it must
  // renumber `order` via `moveAttribute` too, not a raw `patchAttribute`
  // (which left the old `order` behind and could tie with an existing
  // attribute in the target section). Reuses the same empty-name guard and
  // error display as `handleRenameSection` for consistency.
  const handleInspectorSectionChange = useCallback(
    (attributeName: string, nextSection: string): void => {
      const clean = nextSection.trim();
      if (!clean) {
        setError("A section name may not be empty.");
        return;
      }
      setError(null);
      setAttributes((current) =>
        moveAttribute(current, attributeName, clean, Number.MAX_SAFE_INTEGER)
      );
    },
    []
  );

  // Creation is always an immediate API call (Task 1/2's create endpoints),
  // never a locally-buffered edit like moveAttribute/patchAttribute below —
  // the new attribute needs a real row (workspace-only rows have no
  // source_global counterpart to stage against). Refetches on success so the
  // rest of the page reflects the server's normalized entry.
  const handleCreateAttribute = useCallback(
    async (input: NewAttributeInput): Promise<void> => {
      if (isGlobal) {
        await attributeDefinitionsApi.createGlobalAttribute(itemType, preset, input);
      } else {
        if (!activeWorkspace?.id) return;
        await attributeDefinitionsApi.createWorkspaceAttribute(
          activeWorkspace.id,
          itemType,
          input
        );
      }
      await load();
    },
    [activeWorkspace?.id, isGlobal, itemType, preset, load]
  );

  const handleSelectItemType = useCallback(
    (next: AttributeItemType): void => {
      if (isRouted) {
        navigate(`/attributes/${next}`);
      } else {
        setSearchParams((params) => {
          params.set("entityType", next);
          return params;
        });
      }
    },
    [isRouted, navigate, setSearchParams]
  );

  return (
    <div className={styles.page} data-testid="attribute-editor">
      <div className={styles.toolbar}>
        <label className={styles.toolbarField}>
          <span>{t("attributes.entityType")}</span>
          <select
            className={styles.control}
            data-testid="attribute-editor-entity-type"
            value={itemType}
            onChange={(event) =>
              handleSelectItemType(event.target.value as AttributeItemType)
            }
          >
            {ATTRIBUTE_ITEM_TYPES.map((type) => (
              <option key={type} value={type}>
                {t(`attributes.entityTypes.${type}`, { defaultValue: type })}
              </option>
            ))}
          </select>
        </label>
        {isGlobal ? (
          <PresetSegmentedControl
            value={preset}
            onChange={(next) =>
              setSearchParams((params) => {
                params.set("preset", next);
                return params;
              })
            }
          />
        ) : null}
        <span className={styles.spacer} />
        <span className={styles.toolbarField} role="group" aria-label={t("attributes.viewMode.list")}>
          <button
            type="button"
            data-testid="attribute-editor-view-list"
            aria-pressed={viewMode === "list"}
            disabled={viewMode === "list"}
            onClick={() => handleSetViewMode("list")}
          >
            {t("attributes.viewMode.list")}
          </button>
          <button
            type="button"
            data-testid="attribute-editor-view-table"
            aria-pressed={viewMode === "table"}
            disabled={viewMode === "table"}
            onClick={() => handleSetViewMode("table")}
          >
            {t("attributes.viewMode.table")}
          </button>
        </span>
        {newSection === null ? (
          <button
            type="button"
            data-testid="attribute-editor-add-section"
            disabled={!isAdmin}
            onClick={() => setNewSection("")}
          >
            {t("attributes.addSection")}
          </button>
        ) : (
          <input
            className={styles.control}
            data-testid="attribute-editor-new-section-name"
            value={newSection}
            autoFocus
            onChange={(event) => setNewSection(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && newSection.trim()) {
                setEmptySections((current) => [...current, newSection.trim()]);
                setNewSection(null);
              }
              if (event.key === "Escape") setNewSection(null);
            }}
          />
        )}
        {!isGlobal && isCustomized ? (
          <button
            type="button"
            data-testid="attribute-editor-reset"
            disabled={!isAdmin}
            onClick={() => setConfirmReset(true)}
          >
            {t("attributes.reset")}
          </button>
        ) : null}
        <button
          type="button"
          data-testid="attribute-editor-save"
          disabled={!isAdmin || saving || !isDirty}
          onClick={() => void handleSave()}
        >
          {t("actions.save")}
        </button>
      </div>

      {error ? (
        <div className={styles.error} role="alert" data-testid="attribute-editor-error">
          {error}
        </div>
      ) : null}
      {toast.message ? (
        <div className={styles.toast} role="status" data-testid="attribute-editor-toast">
          {toast.message}
        </div>
      ) : null}

      <div className={styles.body}>
        {viewMode === "list" ? (
          <AttributeList
            attributes={attributes}
            emptySections={emptySections}
            selected={selected}
            readOnly={!isAdmin}
            onSelect={setSelected}
            onMove={(name, toSection, toIndex) =>
              setAttributes((current) => moveAttribute(current, name, toSection, toIndex))
            }
            onRenameSection={handleRenameSection}
            onDeleteSection={handleDeleteSection}
            onMoveSection={handleMoveSection}
            onAddAttribute={setCreateSection}
          />
        ) : (
          <AttributeTable
            attributes={attributes}
            origins={isGlobal ? undefined : origins}
            selected={selected}
            onSelect={setSelected}
          />
        )}
        {selectedAttribute ? (
          <AttributeInspector
            attribute={selectedAttribute}
            allAttributes={attributes}
            readOnly={!isAdmin}
            onPatch={(patch) =>
              setAttributes((current) =>
                patchAttribute(current, selectedAttribute.name, patch)
              )
            }
            onSectionChange={(nextSection) =>
              handleInspectorSectionChange(selectedAttribute.name, nextSection)
            }
          />
        ) : null}
      </div>

      {confirmReset ? (
        <ConfirmDialog
          title={t("attributes.reset")}
          message={t("attributes.resetConfirm")}
          confirmLabel={t("attributes.reset")}
          testId="attribute-editor-reset"
          confirmTestId="attribute-editor-reset-confirm"
          cancelTestId="attribute-editor-reset-cancel"
          onConfirm={() => void handleReset()}
          onCancel={() => setConfirmReset(false)}
        />
      ) : null}

      {createSection !== null ? (
        <AttributeCreateDialog
          scope={isGlobal ? "global" : "workspace"}
          section={createSection}
          existingNames={attributes.map((a) => a.name)}
          onCreate={handleCreateAttribute}
          onClose={() => setCreateSection(null)}
        />
      ) : null}
    </div>
  );
}
