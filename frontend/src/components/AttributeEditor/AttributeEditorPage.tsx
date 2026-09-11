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

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useMatch, useNavigate, useParams, useSearchParams } from "react-router-dom";

import {
  attributeDefinitionsApi,
  downloadAttributeDefinitionDocument,
  type AttributeDefinitionDocument,
  type AttributeItemType,
  type AttributeOrigin,
  type AttributeSpec,
  type NewAttributeInput,
  type OnCollision,
  type SectionLayout,
  type SectionSpec,
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
import { AttributeImportDialog } from "./AttributeImportDialog";
import { AttributeInspector } from "./AttributeInspector";
import { AttributeList } from "./AttributeList";
import { AttributeTable } from "./AttributeTable";
import {
  deleteSection,
  deleteSectionSpec,
  moveAttribute,
  moveSection,
  patchAttribute,
  renameSection,
  renameSectionSpec,
  setSectionLayout,
  toggleSectionVisible,
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
  const [sections, setSections] = useState<SectionSpec[]>([]);
  const [loadedSections, setLoadedSections] = useState<SectionSpec[]>([]);
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
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);
  const [deleteUsageCount, setDeleteUsageCount] = useState<number | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [removeOptionTarget, setRemoveOptionTarget] = useState<string | null>(null);
  const [removeOptionUsageCount, setRemoveOptionUsageCount] = useState<number | null>(null);
  const [viewMode, setViewMode] = useState<ViewMode>(loadViewMode);
  const [pendingImport, setPendingImport] = useState<{
    document: AttributeDefinitionDocument;
    fileName: string;
  } | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

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
        setSections(definition.sections);
        setLoadedSections(definition.sections);
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
        setSections(definition.sections);
        setLoadedSections(definition.sections);
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

  // Task 11 (spec section 6): download the current definition as a
  // re-importable JSON document -- reuses apiClient (not a raw fetch, unlike
  // api/export.ts's CSV/ReqIF downloads: those need a raw Blob response,
  // export_definition's REST endpoint returns plain JSON apiClient already
  // parses for us).
  const handleExport = useCallback(async (): Promise<void> => {
    setError(null);
    try {
      const document = isGlobal
        ? await attributeDefinitionsApi.exportGlobal(itemType, preset)
        : activeWorkspace?.id
          ? await attributeDefinitionsApi.exportWorkspace(activeWorkspace.id, itemType)
          : null;
      if (!document) return;
      const scope = isGlobal ? preset : "workspace";
      downloadAttributeDefinitionDocument(document, `${itemType}-${scope}-attributes.json`);
    } catch (exc: unknown) {
      setError(extractErrorMessage(exc));
    }
  }, [activeWorkspace?.id, isGlobal, itemType, preset]);

  const handleFileSelected = useCallback(
    (event: React.ChangeEvent<HTMLInputElement>): void => {
      const file = event.target.files?.[0];
      event.target.value = ""; // allow re-selecting the same file next time
      if (!file) return;
      setError(null);
      const reader = new FileReader();
      reader.onload = () => {
        try {
          const document = JSON.parse(String(reader.result)) as AttributeDefinitionDocument;
          setPendingImport({ document, fileName: file.name });
        } catch {
          setError(t("attributes.import.invalidFile"));
        }
      };
      reader.onerror = () => setError(t("attributes.import.invalidFile"));
      reader.readAsText(file);
    },
    [t]
  );

  const handleConfirmImport = useCallback(
    async (onCollision: OnCollision): Promise<void> => {
      if (!pendingImport) return;
      if (isGlobal) {
        await attributeDefinitionsApi.importGlobal(
          itemType, preset, pendingImport.document, onCollision
        );
      } else if (activeWorkspace?.id) {
        await attributeDefinitionsApi.importWorkspace(
          activeWorkspace.id, itemType, pendingImport.document, onCollision
        );
      }
      await load();
    },
    [activeWorkspace?.id, isGlobal, itemType, load, pendingImport, preset]
  );

  // Selection/scratch state is scoped to one (itemType, preset) view — carrying
  // it across a switch risks matching an unrelated attribute of the same name
  // on the newly loaded type (e.g. both Risk and Issue have a "title").
  useEffect(() => {
    setSelected(null);
    setEmptySections([]);
    setNewSection(null);
  }, [itemType, preset, isGlobal]);

  const isDirty = useMemo(
    () =>
      JSON.stringify(attributes) !== JSON.stringify(loaded) ||
      JSON.stringify(sections) !== JSON.stringify(loadedSections),
    [attributes, loaded, sections, loadedSections]
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
          attributes,
          sections
        );
        setAttributes(result.attributes);
        setLoaded(result.attributes);
        setSections(result.sections);
        setLoadedSections(result.sections);
        if (typeof result.propagated_workspace_count === "number") {
          toast.show(
            t("attributes.propagated", { count: result.propagated_workspace_count })
          );
        }
      } else if (activeWorkspace?.id) {
        const result = await attributeDefinitionsApi.putWorkspace(
          activeWorkspace.id,
          itemType,
          attributes,
          sections
        );
        setAttributes(result.attributes);
        setLoaded(result.attributes);
        setSections(result.sections);
        setLoadedSections(result.sections);
        setIsCustomized(result.is_customized);
        setOrigins(result.origins);
      }
    } catch (exc: unknown) {
      setError(extractErrorMessage(exc));
    } finally {
      setSaving(false);
    }
  }, [activeWorkspace?.id, attributes, isGlobal, itemType, preset, sections, t]);

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
      setSections(result.sections);
      setLoadedSections(result.sections);
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
        setSections((current) => renameSectionSpec(current, from, to));
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
        setSections((current) => deleteSectionSpec(current, name));
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

  const handleToggleSectionVisible = useCallback((name: string): void => {
    setSections((current) => toggleSectionVisible(current, name));
  }, []);

  const handleSetSectionLayout = useCallback((name: string, layout: SectionLayout): void => {
    setSections((current) => setSectionLayout(current, name, layout));
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

  // Delete confirmation (Task 5): fetches the usage count before showing the
  // confirmation so the admin sees "N artifacts use this" instead of
  // deleting blind. Global scope has no single workspace to probe (the
  // backend's count_usages is workspace-scoped only, there is no
  // cross-workspace aggregate) -- the confirmation there shows a plain
  // message with no count, which Task 6's option-removal flow can follow
  // the same way.
  const handleRequestDeleteAttribute = useCallback(
    (name: string): void => {
      setDeleteTarget(name);
      setDeleteUsageCount(null);
      if (!isGlobal && activeWorkspace?.id) {
        void attributeDefinitionsApi
          .getUsageCount(activeWorkspace.id, itemType, name)
          .then(setDeleteUsageCount)
          .catch(() => setDeleteUsageCount(0));
      } else {
        setDeleteUsageCount(0);
      }
    },
    [activeWorkspace?.id, isGlobal, itemType]
  );

  const handleConfirmDeleteAttribute = useCallback(async (): Promise<void> => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      if (isGlobal) {
        await attributeDefinitionsApi.deleteGlobalAttribute(itemType, preset, deleteTarget);
      } else if (activeWorkspace?.id) {
        await attributeDefinitionsApi.deleteWorkspaceAttribute(
          activeWorkspace.id,
          itemType,
          deleteTarget
        );
      }
      setDeleteTarget(null);
      await load();
    } catch (exc: unknown) {
      setError(extractErrorMessage(exc));
    } finally {
      setDeleting(false);
    }
  }, [activeWorkspace?.id, deleteTarget, isGlobal, itemType, load, preset]);

  // Task 6: same shape as handleRequestDeleteAttribute above, but the actual
  // removal is a LOCAL patch (options are just another attribute property,
  // saved through the page's normal Save button), not an immediate API
  // call -- only the confirmation's usage-count probe hits the server.
  const handleRequestRemoveOption = useCallback(
    (optionValue: string): void => {
      setRemoveOptionTarget(optionValue);
      setRemoveOptionUsageCount(null);
      if (!isGlobal && activeWorkspace?.id && selectedAttribute) {
        void attributeDefinitionsApi
          .getUsageCount(activeWorkspace.id, itemType, selectedAttribute.name, optionValue)
          .then(setRemoveOptionUsageCount)
          .catch(() => setRemoveOptionUsageCount(0));
      } else {
        setRemoveOptionUsageCount(0);
      }
    },
    [activeWorkspace?.id, isGlobal, itemType, selectedAttribute]
  );

  const handleConfirmRemoveOption = useCallback((): void => {
    if (!removeOptionTarget || !selectedAttribute) return;
    setAttributes((current) =>
      patchAttribute(current, selectedAttribute.name, {
        options: selectedAttribute.options.filter((o) => o.value !== removeOptionTarget),
      })
    );
    setRemoveOptionTarget(null);
  }, [removeOptionTarget, selectedAttribute]);

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
        <button
          type="button"
          data-testid="attribute-editor-export"
          disabled={!isAdmin}
          onClick={() => void handleExport()}
        >
          {t("actions.export")}
        </button>
        <button
          type="button"
          data-testid="attribute-editor-import"
          disabled={!isAdmin}
          onClick={() => fileInputRef.current?.click()}
        >
          {t("actions.import")}
        </button>
        <input
          ref={fileInputRef}
          type="file"
          accept="application/json"
          data-testid="attribute-editor-import-file"
          hidden
          onChange={handleFileSelected}
        />
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
            sections={sections}
            origins={isGlobal ? undefined : origins}
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
            onDeleteAttribute={handleRequestDeleteAttribute}
            onToggleSectionVisible={handleToggleSectionVisible}
            onSetSectionLayout={handleSetSectionLayout}
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
            onRequestRemoveOption={handleRequestRemoveOption}
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

      {deleteTarget !== null ? (
        <ConfirmDialog
          title={t("attributes.deleteAttribute.title")}
          message={
            deleteUsageCount === null
              ? t("attributes.deleteAttribute.loading")
              : deleteUsageCount > 0
                ? t("attributes.deleteAttribute.confirmWithUsage", {
                    name: deleteTarget,
                    count: deleteUsageCount,
                  })
                : t("attributes.deleteAttribute.confirmPlain", { name: deleteTarget })
          }
          confirmLabel={t("actions.delete")}
          testId="attribute-delete-confirm"
          isSubmitting={deleting || deleteUsageCount === null}
          onConfirm={() => void handleConfirmDeleteAttribute()}
          onCancel={() => setDeleteTarget(null)}
        />
      ) : null}

      {removeOptionTarget !== null ? (
        <ConfirmDialog
          title={t("attributes.options.deleteConfirmTitle")}
          message={
            removeOptionUsageCount === null
              ? t("attributes.options.deleteConfirmLoading")
              : removeOptionUsageCount > 0
                ? t("attributes.options.deleteConfirmWithUsage", {
                    value: removeOptionTarget,
                    count: removeOptionUsageCount,
                  })
                : t("attributes.options.deleteConfirmPlain", { value: removeOptionTarget })
          }
          confirmLabel={t("actions.delete")}
          testId="attribute-option-delete-confirm"
          isSubmitting={removeOptionUsageCount === null}
          onConfirm={handleConfirmRemoveOption}
          onCancel={() => setRemoveOptionTarget(null)}
        />
      ) : null}

      {pendingImport !== null ? (
        <AttributeImportDialog
          fileName={pendingImport.fileName}
          onConfirm={handleConfirmImport}
          onClose={() => setPendingImport(null)}
        />
      ) : null}
    </div>
  );
}
