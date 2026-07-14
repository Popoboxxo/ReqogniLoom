/**
 * ARCH-L1-001 ReactFrontend — IcdView (REQ-L0-017, REQ-L1-028, REQ-L2-ICD-001).
 *
 * leaf_id: COMP-RF-001 (NavigationShell — gated by preset)
 * req_id:  REQ-L0-017 (Rekursive Architektur-Hierarchie mit versionierten ICDs),
 *          REQ-L1-028 (ICD-Verwaltung),
 *          REQ-L2-ICD-001 (CRUD + immutable Versioning),
 *          REQ-002 (Split-View Layout)
 *
 * Interface Control Document management in a split-view layout:
 *   - Left panel: list of all ICDs in the active workspace (+ create button)
 *   - Divider: 4px resizable
 *   - Right panel: create form OR detail view with version history,
 *     "New Version" flow and traceability sidebar
 *
 * NOTE: Past versions are immutable. There is no DELETE button — the DB
 * trigger `trg_icd_version_immutable` (ADR-ICD-01) makes deletion a
 * privileged trigger-bypassing operation, not exposed in the UI.
 * Use "archive" / "supersede" semantics via the new-version flow.
 */

import { memo, useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useParams, useNavigate } from "react-router-dom";
import { useWorkspace } from "../../context/WorkspaceContext";
import {
  icdsApi,
  type Icd,
  type IcdDetail,
  type CreateIcdPayload,
  type NewVersionPayload,
} from "../../api/icds";
import { architectureApi } from "../../api/architecture";
import type { ArchitectureElement } from "../../types";
import { SplitView } from "../SplitView/SplitView";
import { VersionBadge } from "../shared/VersionBadge";
import { RightSidebar } from "../shared/ArtifactInspector";
import type { VersionRef } from "../shared/ArtifactInspector";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function shortId(id: string): string {
  return `${id.slice(0, 8)}…`;
}

function parseListField(value: string): string[] {
  return value
    .split("\n")
    .map((s) => s.trim())
    .filter((s) => s.length > 0);
}

function joinListField(values: string[] | undefined): string {
  return Array.isArray(values) ? values.join("\n") : "";
}

function extractErrorMessage(err: unknown, fallback: string): string {
  const e = err as { error?: { message?: string } };
  return e?.error?.message ?? (err ? String(err) : fallback);
}

// Similarity algorithm: tokenize ICD names and compute Jaccard similarity
function tokenize(name: string): Set<string> {
  return new Set(
    name
      .toLowerCase()
      .split(/[\s\-_/]+/)
      .filter((t) => t.length > 2)
  );
}

function similarity(a: string, b: string): number {
  const ta = tokenize(a);
  const tb = tokenize(b);
  const intersection = new Set([...ta].filter((t) => tb.has(t)));
  const union = new Set([...ta, ...tb]);
  return union.size > 0 ? intersection.size / union.size : 0;
}

function findSimilarICDs(
  current: Icd,
  allICDs: Icd[],
  threshold = 0.5
): Array<{ icd: Icd; score: number }> {
  return allICDs
    .filter((icd) => icd.id !== current.id)
    .map((icd) => ({ icd, score: similarity(current.name, icd.name) }))
    .filter(({ score }) => score >= threshold)
    .sort((a, b) => b.score - a.score);
}

// ---------------------------------------------------------------------------
// Main component — split-view
// ---------------------------------------------------------------------------

export default function IcdView(): JSX.Element {
  const { t } = useTranslation();
  const { activeWorkspace } = useWorkspace();
  const { id: routeId } = useParams<{ id?: string }>();
  const navigate = useNavigate();

  // ---- State ---------------------------------------------------------------
  const [icds, setIcds] = useState<Icd[]>([]);
  const [architectureElements, setArchitectureElements] = useState<
    ArchitectureElement[]
  >([]);
  const [selectedDetail, setSelectedDetail] = useState<IcdDetail | null>(null);

  const [isLoading, setIsLoading] = useState(true);
  const [isLoadingDetail, setIsLoadingDetail] = useState(false);
  const [isLoadingArch, setIsLoadingArch] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [showCreate, setShowCreate] = useState(false);
  const [showNewVersion, setShowNewVersion] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  // Create form fields
  const [formName, setFormName] = useState("");
  const [formSource, setFormSource] = useState("");
  const [formTarget, setFormTarget] = useState("");
  const [formDirection, setFormDirection] = useState<
    "unidirectional" | "bidirectional"
  >("unidirectional");
  const [formInterfaceType, setFormInterfaceType] = useState("");
  const [formContract, setFormContract] = useState("");
  const [formPre, setFormPre] = useState("");
  const [formPost, setFormPost] = useState("");
  const [formInv, setFormInv] = useState("");

  // New-version form fields (pre-filled with current values)
  const [nvDirection, setNvDirection] = useState<
    "unidirectional" | "bidirectional"
  >("unidirectional");
  const [nvInterfaceType, setNvInterfaceType] = useState("");
  const [nvContract, setNvContract] = useState("");
  const [nvPre, setNvPre] = useState("");
  const [nvPost, setNvPost] = useState("");
  const [nvInv, setNvInv] = useState("");

  // ---- Data loaders --------------------------------------------------------

  const loadList = useCallback(async (): Promise<void> => {
    if (!activeWorkspace) {
      setIcds([]);
      setArchitectureElements([]);
      setIsLoading(false);
      return;
    }
    setIsLoading(true);
    setError(null);
    try {
      // Phase 1: Load ICDs first (fast) → tree appears immediately
      // REQ-014: split loading to show ICD tree before architecture elements finish
      const icdResp = await icdsApi.list(activeWorkspace.id);
      setIcds(icdResp.results);
      setIsLoading(false); // Tree now visible

      // Phase 2: Load architecture elements in background
      // (needed for source/target dropdowns in create form)
      setIsLoadingArch(true);
      try {
        // Bug fix B-ICD-004: fetch the full architecture element list via
        // architectureApi.listAll (follows pagination links) so every element
        // is selectable in the source/target dropdowns.
        const archAll = await architectureApi.listAll(activeWorkspace.id);
        setArchitectureElements(archAll);
      } finally {
        setIsLoadingArch(false);
      }
    } catch (err) {
      setError(extractErrorMessage(err, t("icds.loadFailed")));
      setIsLoading(false);
    }
  }, [activeWorkspace, t]);

  const loadDetail = useCallback(
    async (icdId: string): Promise<void> => {
      setIsLoadingDetail(true);
      try {
        const detail = await icdsApi.get(icdId);
        setSelectedDetail(detail);

        // Pre-fill the new-version form with the current values
        setNvDirection(detail.direction ?? "unidirectional");
        setNvInterfaceType(detail.interface_type ?? "");
        setNvContract(detail.semantic_description ?? "");
        setNvPre(joinListField(detail.preconditions));
        setNvPost(joinListField(detail.postconditions));
        setNvInv(joinListField(detail.invariants));
      } catch (err) {
        setError(extractErrorMessage(err, t("icds.loadFailed")));
        setSelectedDetail(null);
      } finally {
        setIsLoadingDetail(false);
      }
    },
    [t]
  );

  // Initial load
  useEffect(() => {
    void loadList();
  }, [loadList]);

  // Sync route param with selection
  useEffect(() => {
    if (routeId) {
      void loadDetail(routeId);
    } else {
      setSelectedDetail(null);
    }
  }, [routeId, loadDetail]);

  // ---- Handlers ------------------------------------------------------------

  const resetCreateForm = (): void => {
    setFormName("");
    setFormSource("");
    setFormTarget("");
    setFormDirection("unidirectional");
    setFormInterfaceType("");
    setFormContract("");
    setFormPre("");
    setFormPost("");
    setFormInv("");
    setFormError(null);
  };

  const handleSelectIcd = (icd: Icd): void => {
    setShowNewVersion(false);
    setShowCreate(false);
    navigate(`/icds/${icd.id}`);
  };

  const handleCreate = useCallback(async (): Promise<void> => {
    if (!activeWorkspace) return;
    if (!formName.trim()) {
      setFormError(t("icds.nameRequired"));
      return;
    }
    if (!formSource) {
      setFormError(t("icds.sourceRequired"));
      return;
    }
    if (!formTarget) {
      setFormError(t("icds.targetRequired"));
      return;
    }
    if (formSource === formTarget) {
      setFormError(t("traceability.sameEndpoints"));
      return;
    }

    setIsSaving(true);
    setFormError(null);
    const payload: CreateIcdPayload = {
      workspace_id: activeWorkspace.id,
      name: formName.trim(),
      source_element_id: formSource,
      target_element_id: formTarget,
      direction: formDirection,
      interface_type: formInterfaceType.trim(),
      semantic_description: formContract,
      preconditions: parseListField(formPre),
      postconditions: parseListField(formPost),
      invariants: parseListField(formInv),
    };
    try {
      const created = await icdsApi.create(payload);
      setShowCreate(false);
      resetCreateForm();
      await loadList();
      navigate(`/icds/${created.id}`);
    } catch (err) {
      setFormError(extractErrorMessage(err, t("icds.createFailed")));
    } finally {
      setIsSaving(false);
    }
  }, [
    activeWorkspace,
    formName,
    formSource,
    formTarget,
    formDirection,
    formInterfaceType,
    formContract,
    formPre,
    formPost,
    formInv,
    t,
    loadList,
    navigate,
  ]);

  const handleNewVersion = useCallback(async (): Promise<void> => {
    if (!routeId) return;
    setIsSaving(true);
    setFormError(null);
    const payload: NewVersionPayload = {
      direction: nvDirection,
      interface_type: nvInterfaceType.trim(),
      semantic_description: nvContract,
      preconditions: parseListField(nvPre),
      postconditions: parseListField(nvPost),
      invariants: parseListField(nvInv),
    };
    try {
      await icdsApi.createVersion(routeId, payload);
      setShowNewVersion(false);
      await loadList();
      await loadDetail(routeId);
    } catch (err) {
      setFormError(extractErrorMessage(err, t("icds.newVersionFailed")));
    } finally {
      setIsSaving(false);
    }
  }, [
    routeId,
    nvDirection,
    nvInterfaceType,
    nvContract,
    nvPre,
    nvPost,
    nvInv,
    t,
    loadList,
    loadDetail,
  ]);

  // ---- Derived data --------------------------------------------------------

  const architectureById = useMemo(() => {
    const m = new Map<string, ArchitectureElement>();
    for (const el of architectureElements) m.set(el.id, el);
    return m;
  }, [architectureElements]);

  const artifactLabel = useCallback(
    (id: string): string => {
      const el = architectureById.get(id);
      if (el) return `${el.title} (${el.element_type})`;
      return shortId(id);
    },
    [architectureById]
  );

  // ---- Render: loading / error states --------------------------------------

  if (isLoading) {
    return (
      <div data-testid="icd-view">
        <p
          role="status"
          style={{
            fontSize: "var(--font-size-base)",
            color: "var(--color-text-muted)",
            padding: "var(--space-6)",
          }}
        >
          {t("loading")}
        </p>
      </div>
    );
  }

  if (error && !routeId) {
    return (
      <div
        data-testid="icd-view"
        role="alert"
        style={{
          background: "var(--color-surface)",
          border: "1px solid var(--color-danger)",
          borderRadius: "var(--radius-lg)",
          padding: "var(--space-6)",
          boxShadow: "var(--shadow-card)",
          maxWidth: "480px",
        }}
      >
        <p style={{ color: "var(--color-danger)", margin: 0 }}>{error}</p>
        <button
          onClick={() => void loadList()}
          style={{
            marginTop: "var(--space-4)",
            background: "var(--color-primary)",
            color: "var(--color-surface)",
            border: "none",
            borderRadius: "var(--radius-md)",
            padding: "var(--space-2) var(--space-4)",
            cursor: "pointer",
          }}
        >
          {t("actions.reload")}
        </button>
      </div>
    );
  }

  // ---- Render: split-view ----------------------------------------------------

  return (
    <div
      data-testid="icd-view"
      style={{
        height: "100%",
        fontFamily: "var(--font-sans)",
        color: "var(--color-text)",
      }}
    >
      <SplitView
        moduleType="icds"
        leftMinWidth={280}
        leftPanel={
          <>
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginBottom: "var(--space-4)",
          }}
        >
          <h3
            style={{
              margin: 0,
              fontSize: "var(--font-size-lg)",
              fontWeight: 700,
              color: "var(--color-text)",
            }}
          >
            {t("icds.title")} ({icds.length})
          </h3>
          <button
            type="button"
            data-testid="create-icd-btn"
            onClick={() => {
              setShowCreate((v) => !v);
              setShowNewVersion(false);
              setFormError(null);
            }}
            style={{
              background: "var(--color-primary)",
              color: "white",
              border: "none",
              borderRadius: "var(--radius-md)",
              padding: "var(--space-2) var(--space-4)",
              fontSize: "var(--font-size-sm)",
              fontWeight: 600,
              cursor: "pointer",
              transition: "var(--transition-fast)",
            }}
          >
            {showCreate ? t("actions.cancel") : `+ ${t("icds.create")}`}
          </button>
        </div>

        {icds.length === 0 ? (
          <p
            data-testid="icds-empty"
            style={{
              fontSize: "var(--font-size-sm)",
              color: "var(--color-text-muted)",
            }}
          >
            {t("icds.empty")}
          </p>
        ) : (
          <ul
            data-testid="icds-list"
            style={{ listStyle: "none", padding: 0, margin: 0 }}
          >
            {icds.map((icd) => {
              const isSelected = icd.id === routeId && !showCreate;
              return (
                <li
                  key={icd.id}
                  data-testid={`icd-item-${icd.id}`}
                  onClick={() => handleSelectIcd(icd)}
                  style={{
                    padding: "var(--space-3) var(--space-4)",
                    marginBottom: "var(--space-2)",
                    background: isSelected
                      ? "var(--color-surface-raised)"
                      : "var(--color-surface)",
                    borderRadius: "var(--radius-md)",
                    border: isSelected
                      ? "1px solid var(--color-primary)"
                      : "1px solid var(--color-border)",
                    cursor: "pointer",
                    transition: "var(--transition-fast)",
                  }}
                >
                  <strong
                    style={{
                      display: "block",
                      color: "var(--color-text)",
                      fontSize: "var(--font-size-base)",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                    }}
                  >
                    {icd.name}
                  </strong>
                  <span
                    style={{
                      color: "var(--color-text-muted)",
                      fontSize: "var(--font-size-sm)",
                      fontFamily: "monospace",
                    }}
                  >
                    {shortId(icd.source_element_id)} →{" "}
                    {shortId(icd.target_element_id)}
                  </span>
                  <span
                    style={{
                      display: "block",
                      color: "var(--color-text-muted)",
                      fontSize: "var(--font-size-xs)",
                    }}
                  >
                    {t("icds.source")}: {artifactLabel(icd.source_element_id)} ·{" "}
                    {t("icds.target")}: {artifactLabel(icd.target_element_id)}
                  </span>
                </li>
              );
            })}
          </ul>
        )}
          </>
        }
        rightPanel={
          showCreate ? (
          <div
            data-testid="create-icd-form"
            style={{ maxWidth: "720px" }}
          >
            <h3
              style={{
                fontSize: "var(--font-size-lg)",
                fontWeight: 700,
                marginTop: 0,
                marginBottom: "var(--space-4)",
                color: "var(--color-text)",
              }}
            >
              + {t("icds.create")}
            </h3>
            <label htmlFor="icd-name" style={labelStyle}>
              {t("icds.nameLabel")}
            </label>
            <input
              id="icd-name"
              data-testid="icd-name-input"
              type="text"
              value={formName}
              onChange={(e) => setFormName(e.target.value)}
              placeholder={t("icds.namePlaceholder")}
              style={inputStyle}
            />

            <label htmlFor="icd-source" style={labelStyle}>
              {t("icds.source")}
            </label>
            <select
              id="icd-source"
              data-testid="icd-source-select"
              value={formSource}
              onChange={(e) => setFormSource(e.target.value)}
              disabled={isLoadingArch && architectureElements.length === 0}
              style={inputStyle}
            >
              <option value="">
                {isLoadingArch && architectureElements.length === 0
                  ? t("loading")
                  : t("icds.selectSource")}
              </option>
              {architectureElements.map((el) => (
                <option key={el.id} value={el.id}>
                  {el.title} ({el.element_type})
                </option>
              ))}
            </select>

            <label htmlFor="icd-target" style={labelStyle}>
              {t("icds.target")}
            </label>
            <select
              id="icd-target"
              data-testid="icd-target-select"
              value={formTarget}
              onChange={(e) => setFormTarget(e.target.value)}
              disabled={isLoadingArch && architectureElements.length === 0}
              style={inputStyle}
            >
              <option value="">
                {isLoadingArch && architectureElements.length === 0
                  ? t("loading")
                  : t("icds.selectTarget")}
              </option>
              {architectureElements.map((el) => (
                <option key={el.id} value={el.id}>
                  {el.title} ({el.element_type})
                </option>
              ))}
            </select>

            <label htmlFor="icd-direction" style={labelStyle}>
              {t("icds.direction")}
            </label>
            <select
              id="icd-direction"
              data-testid="icd-direction-select"
              value={formDirection}
              onChange={(e) =>
                setFormDirection(
                  e.target.value as "unidirectional" | "bidirectional"
                )
              }
              style={inputStyle}
            >
              <option value="unidirectional">
                {t("icds.directionUnidirectional")}
              </option>
              <option value="bidirectional">
                {t("icds.directionBidirectional")}
              </option>
            </select>

            <label htmlFor="icd-interface-type" style={labelStyle}>
              {t("icds.interfaceType")}
            </label>
            <select
              id="icd-interface-type"
              data-testid="icd-interface-type-select"
              value={formInterfaceType}
              onChange={(e) => setFormInterfaceType(e.target.value)}
              style={inputStyle}
            >
              <option value="">{t("icds.selectInterfaceType")}</option>
              <option value="provides">Provides</option>
              <option value="requires">Requires</option>
              <option value="event-in">Event In</option>
              <option value="event-out">Event Out</option>
              <option value="data">Data</option>
              <option value="control">Control</option>
            </select>

            <label htmlFor="icd-contract" style={labelStyle}>
              {t("icds.contract")}
            </label>
            <textarea
              id="icd-contract"
              data-testid="icd-contract-textarea"
              value={formContract}
              onChange={(e) => setFormContract(e.target.value)}
              placeholder={t("icds.contractPlaceholder")}
              rows={4}
              style={{ ...inputStyle, fontFamily: "inherit" }}
            />

            <label htmlFor="icd-preconditions" style={labelStyle}>
              {t("icds.preconditions")}
            </label>
            <textarea
              id="icd-preconditions"
              data-testid="icd-preconditions-input"
              value={formPre}
              onChange={(e) => setFormPre(e.target.value)}
              rows={2}
              style={{ ...inputStyle, fontFamily: "inherit" }}
              placeholder="One per line"
            />

            <label htmlFor="icd-postconditions" style={labelStyle}>
              {t("icds.postconditions")}
            </label>
            <textarea
              id="icd-postconditions"
              data-testid="icd-postconditions-input"
              value={formPost}
              onChange={(e) => setFormPost(e.target.value)}
              rows={2}
              style={{ ...inputStyle, fontFamily: "inherit" }}
              placeholder="One per line"
            />

            <label htmlFor="icd-invariants" style={labelStyle}>
              {t("icds.invariants")}
            </label>
            <textarea
              id="icd-invariants"
              data-testid="icd-invariants-input"
              value={formInv}
              onChange={(e) => setFormInv(e.target.value)}
              rows={2}
              style={{ ...inputStyle, fontFamily: "inherit" }}
              placeholder="One per line"
            />

            {formError && (
              <p
                role="alert"
                data-testid="create-icd-error"
                style={{
                  color: "var(--color-danger)",
                  fontSize: "var(--font-size-sm)",
                  margin: "var(--space-3) 0 0 0",
                }}
              >
                {formError}
              </p>
            )}

            <div
              style={{
                display: "flex",
                gap: "var(--space-3)",
                marginTop: "var(--space-4)",
              }}
            >
              <button
                type="button"
                data-testid="create-icd-submit"
                onClick={() => void handleCreate()}
                disabled={isSaving || isLoadingArch || architectureElements.length < 2}
                style={{
                  background: "var(--color-primary)",
                  color: "white",
                  border: "none",
                  borderRadius: "var(--radius-md)",
                  padding: "var(--space-2) var(--space-6)",
                  fontSize: "var(--font-size-sm)",
                  cursor: isSaving || isLoadingArch ? "not-allowed" : "pointer",
                  opacity: isSaving || isLoadingArch ? 0.7 : 1,
                }}
              >
                {isSaving ? t("actions.saving") : t("actions.save")}
              </button>
              <button
                type="button"
                onClick={() => {
                  setShowCreate(false);
                  resetCreateForm();
                }}
                style={{
                  background: "transparent",
                  color: "var(--color-text)",
                  border: "1px solid var(--color-border)",
                  borderRadius: "var(--radius-md)",
                  padding: "var(--space-2) var(--space-6)",
                  fontSize: "var(--font-size-sm)",
                  cursor: "pointer",
                }}
              >
                {t("actions.cancel")}
              </button>
            </div>
          </div>
        ) : routeId && isLoadingDetail ? (
          <p
            role="status"
            style={{
              color: "var(--color-text-muted)",
              padding: "var(--space-6)",
            }}
          >
            {t("loading")}
          </p>
        ) : routeId && selectedDetail ? (
          <IcdDetailPane
            detail={selectedDetail}
            allICDs={icds}
            artifactLabel={artifactLabel}
            onSelectIcd={(id) => navigate(`/icds/${id}`)}
            showNewVersion={showNewVersion}
            setShowNewVersion={setShowNewVersion}
            formError={formError}
            setFormError={setFormError}
            isSaving={isSaving}
            onNewVersion={() => void handleNewVersion()}
            nvDirection={nvDirection}
            setNvDirection={setNvDirection}
            nvInterfaceType={nvInterfaceType}
            setNvInterfaceType={setNvInterfaceType}
            nvContract={nvContract}
            setNvContract={setNvContract}
            nvPre={nvPre}
            setNvPre={setNvPre}
            nvPost={nvPost}
            setNvPost={setNvPost}
            nvInv={nvInv}
            setNvInv={setNvInv}
          />
        ) : (
          <p
            style={{
              color: "var(--color-text-muted)",
              fontSize: "var(--font-size-lg)",
              padding: "var(--space-8)",
              textAlign: "center",
            }}
          >
            {t("icds.selectIcd", "Select an ICD from the list")}
          </p>
          )
        }
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Detail pane (right panel content)
// ---------------------------------------------------------------------------

interface IcdDetailPaneProps {
  detail: IcdDetail;
  allICDs: Icd[];
  artifactLabel: (id: string) => string;
  onSelectIcd: (id: string) => void;
  showNewVersion: boolean;
  setShowNewVersion: React.Dispatch<React.SetStateAction<boolean>>;
  formError: string | null;
  setFormError: (v: string | null) => void;
  isSaving: boolean;
  onNewVersion: () => void;
  nvDirection: "unidirectional" | "bidirectional";
  setNvDirection: (v: "unidirectional" | "bidirectional") => void;
  nvInterfaceType: string;
  setNvInterfaceType: (v: string) => void;
  nvContract: string;
  setNvContract: (v: string) => void;
  nvPre: string;
  setNvPre: (v: string) => void;
  nvPost: string;
  setNvPost: (v: string) => void;
  nvInv: string;
  setNvInv: (v: string) => void;
}

function IcdDetailPane({
  detail,
  allICDs,
  artifactLabel,
  onSelectIcd,
  showNewVersion,
  setShowNewVersion,
  formError,
  setFormError,
  isSaving,
  onNewVersion,
  nvDirection,
  setNvDirection,
  nvInterfaceType,
  setNvInterfaceType,
  nvContract,
  setNvContract,
  nvPre,
  setNvPre,
  nvPost,
  setNvPost,
  nvInv,
  setNvInv,
}: IcdDetailPaneProps): JSX.Element {
  const { t } = useTranslation();

  // Build the current VersionRef consumed by ArtifactInspector
  // (REQ-L2-RF-035). ICD's /versions/ endpoint is not exposed yet
  // (UI standards §5.1), so we feed the inspector the current version
  // only — VersionPanel renders the empty state for older entries.
  const currentVersion: VersionRef = useMemo(
    () => ({
      version: detail.version,
      label: `v${detail.version}`,
      createdAt: detail.created_at,
      baselineIds: [],
    }),
    [detail.version, detail.created_at]
  );

  return (
    <div>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: "var(--space-6)",
        }}
      >
        <div>
          <h2
            data-testid="icd-detail-title"
            style={{
              fontSize: "var(--font-size-2xl)",
              fontWeight: 700,
              color: "var(--color-text)",
              margin: 0,
            }}
          >
            {detail.name}{" "}
            <VersionBadge version={detail.version} />
          </h2>
          <p
            style={{
              color: "var(--color-text-muted)",
              fontSize: "var(--font-size-sm)",
              margin: "var(--space-1) 0 0 0",
            }}
          >
            {t("icds.source")}: {artifactLabel(detail.source_element_id)} →{" "}
            {t("icds.target")}: {artifactLabel(detail.target_element_id)}
          </p>
        </div>
        <button
          type="button"
          data-testid="icd-new-version-btn"
          onClick={() => setShowNewVersion((v) => !v)}
          style={{
            background: "var(--color-primary)",
            color: "white",
            border: "none",
            borderRadius: "var(--radius-md)",
            padding: "var(--space-2) var(--space-4)",
            fontSize: "var(--font-size-sm)",
            cursor: "pointer",
            transition: "var(--transition-fast)",
          }}
        >
          {showNewVersion ? t("actions.cancel") : `+ ${t("icds.newVersion")}`}
        </button>
      </div>

      {showNewVersion && (
        <div
          data-testid="icd-new-version-form"
          style={{
            background: "var(--color-surface)",
            border: "1px solid var(--color-border)",
            borderRadius: "var(--radius-lg)",
            boxShadow: "var(--shadow-card)",
            padding: "var(--space-6)",
            marginBottom: "var(--space-6)",
            maxWidth: "720px",
          }}
        >
          <p
            style={{
              fontSize: "var(--font-size-sm)",
              color: "var(--color-text-muted)",
              margin: "0 0 var(--space-4) 0",
            }}
          >
            {t("icds.immutableHint")}
          </p>
          {renderVersionFields(
            nvDirection,
            setNvDirection,
            nvInterfaceType,
            setNvInterfaceType,
            nvContract,
            setNvContract,
            nvPre,
            setNvPre,
            nvPost,
            setNvPost,
            nvInv,
            setNvInv,
            t
          )}
          {formError && (
            <p
              role="alert"
              style={{
                color: "var(--color-danger)",
                fontSize: "var(--font-size-sm)",
                margin: "var(--space-3) 0 0 0",
              }}
            >
              {formError}
            </p>
          )}
          <div
            style={{
              display: "flex",
              gap: "var(--space-3)",
              marginTop: "var(--space-4)",
            }}
          >
            <button
              type="button"
              data-testid="icd-new-version-submit"
              onClick={onNewVersion}
              disabled={isSaving}
              style={{
                background: "var(--color-primary)",
                color: "white",
                border: "none",
                borderRadius: "var(--radius-md)",
                padding: "var(--space-2) var(--space-6)",
                fontSize: "var(--font-size-sm)",
                cursor: isSaving ? "not-allowed" : "pointer",
                opacity: isSaving ? 0.7 : 1,
              }}
            >
              {isSaving ? t("actions.saving") : t("actions.save")}
            </button>
            <button
              type="button"
              onClick={() => {
                setShowNewVersion(false);
                setFormError(null);
              }}
              style={{
                background: "transparent",
                color: "var(--color-text)",
                border: "1px solid var(--color-border)",
                borderRadius: "var(--radius-md)",
                padding: "var(--space-2) var(--space-6)",
                fontSize: "var(--font-size-sm)",
                cursor: "pointer",
              }}
            >
              {t("actions.cancel")}
            </button>
          </div>
        </div>
      )}

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "2fr 1fr",
          gap: "var(--space-6)",
        }}
      >
        <div>
          <div
            data-testid="icd-contract-section"
            style={{
              background: "var(--color-surface)",
              border: "1px solid var(--color-border)",
              borderRadius: "var(--radius-lg)",
              boxShadow: "var(--shadow-card)",
              padding: "var(--space-6)",
              marginBottom: "var(--space-6)",
            }}
          >
            <h3
              style={{
                fontSize: "var(--font-size-lg)",
                fontWeight: 600,
                color: "var(--color-text)",
                margin: "0 0 var(--space-4) 0",
              }}
            >
              {t("icds.contract")}
            </h3>
            <ReadOnlyField
              label={t("icds.interfaceType")}
              value={detail.interface_type ?? "—"}
            />
            <ReadOnlyField
              label={t("icds.direction")}
              value={
                detail.direction
                  ? t(
                      detail.direction === "bidirectional"
                        ? "icds.directionBidirectional"
                        : "icds.directionUnidirectional"
                    )
                  : "—"
              }
            />
            <div style={{ marginBottom: "var(--space-4)" }}>
              <label
                style={{
                  display: "block",
                  fontWeight: 500,
                  color: "var(--color-text)",
                  fontSize: "var(--font-size-sm)",
                  marginBottom: "var(--space-1)",
                }}
              >
                {t("icds.contract")}
              </label>
              <div
                data-testid="icd-contract-textarea"
                style={{
                  padding: "var(--space-3)",
                  background: "var(--color-surface-raised)",
                  border: "1px solid var(--color-border)",
                  borderRadius: "var(--radius-md)",
                  minHeight: "80px",
                  whiteSpace: "pre-wrap",
                  color: "var(--color-text)",
                  fontSize: "var(--font-size-base)",
                }}
              >
                {detail.semantic_description || "—"}
              </div>
            </div>
            <ReadOnlyList
              label={t("icds.preconditions")}
              values={detail.preconditions}
            />
            <ReadOnlyList
              label={t("icds.postconditions")}
              values={detail.postconditions}
            />
            <ReadOnlyList
              label={t("icds.invariants")}
              values={detail.invariants}
            />
          </div>

          {/* REQ-006: Show similar interfaces based on name token similarity. */}
          <SimilarIcdsPanel
            currentICD={allICDs.find((icd) => icd.id === detail.id) || null}
            allICDs={allICDs}
            onSelect={onSelectIcd}
          />
        </div>

        {/* Removed: replaced by ArtifactInspector (REQ-L1-095).
            The inline version-list + traceability aside is replaced by the
            shared <RightSidebar kind="icd" />, which owns the VersionPanel,
            DiffPanel and TracePanel (UI standards §3 / §4 / §11). */}
        <RightSidebar
          kind="icd"
          artifactId={detail.id}
          currentVersion={currentVersion}
        />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

const labelStyle: React.CSSProperties = {
  display: "block",
  fontWeight: 500,
  color: "var(--color-text)",
  marginTop: "var(--space-3)",
  marginBottom: "var(--space-1)",
  fontSize: "var(--font-size-sm)",
};

const inputStyle: React.CSSProperties = {
  width: "100%",
  border: "1px solid var(--color-border)",
  borderRadius: "var(--radius-md)",
  padding: "var(--space-3)",
  fontSize: "var(--font-size-base)",
  background: "var(--color-surface)",
  color: "var(--color-text)",
  boxSizing: "border-box",
};

interface ReadOnlyFieldProps {
  label: string;
  value: string;
}

// REQ-092: memoized for performance — pure read-only field. Its props derive
// from the stable ``detail`` object, so it must not re-render while the sibling
// new-version form drives parent (IcdDetailPane) re-renders on every keystroke.
const ReadOnlyField = memo(function ReadOnlyField({
  label,
  value,
}: ReadOnlyFieldProps): JSX.Element {
  return (
    <div style={{ marginBottom: "var(--space-3)" }}>
      <label
        style={{
          display: "block",
          fontWeight: 500,
          color: "var(--color-text)",
          fontSize: "var(--font-size-sm)",
          marginBottom: "var(--space-1)",
        }}
      >
        {label}
      </label>
      <div
        style={{
          padding: "var(--space-2) var(--space-3)",
          background: "var(--color-surface-raised)",
          border: "1px solid var(--color-border)",
          borderRadius: "var(--radius-md)",
          color: "var(--color-text)",
          fontSize: "var(--font-size-base)",
        }}
      >
        {value}
      </div>
    </div>
  );
});

interface ReadOnlyListProps {
  label: string;
  values: string[];
}

// REQ-092: memoized for performance — pure list. ``values`` is a stable array
// reference off the ``detail`` object (preconditions/postconditions/invariants),
// so memo skips re-rendering when the parent re-renders for form-input changes.
const ReadOnlyList = memo(function ReadOnlyList({
  label,
  values,
}: ReadOnlyListProps): JSX.Element {
  return (
    <div style={{ marginBottom: "var(--space-3)" }}>
      <label
        style={{
          display: "block",
          fontWeight: 500,
          color: "var(--color-text)",
          fontSize: "var(--font-size-sm)",
          marginBottom: "var(--space-1)",
        }}
      >
        {label}
      </label>
      {values.length === 0 ? (
        <div
          style={{
            padding: "var(--space-2) var(--space-3)",
            background: "var(--color-surface-raised)",
            border: "1px solid var(--color-border)",
            borderRadius: "var(--radius-md)",
            color: "var(--color-text-muted)",
            fontSize: "var(--font-size-sm)",
          }}
        >
          —
        </div>
      ) : (
        <ul
          style={{
            listStyle: "disc inside",
            padding: "var(--space-2) var(--space-3)",
            margin: 0,
            background: "var(--color-surface-raised)",
            border: "1px solid var(--color-border)",
            borderRadius: "var(--radius-md)",
            color: "var(--color-text)",
            fontSize: "var(--font-size-sm)",
          }}
        >
          {values.map((v, i) => (
            <li key={i}>{v}</li>
          ))}
        </ul>
      )}
    </div>
  );
});

interface VersionFieldsProps {
  t: (key: string, opts?: Record<string, unknown>) => string;
}

function renderVersionFields(
  direction: "unidirectional" | "bidirectional",
  setDirection: (v: "unidirectional" | "bidirectional") => void,
  interfaceType: string,
  setInterfaceType: (v: string) => void,
  contract: string,
  setContract: (v: string) => void,
  pre: string,
  setPre: (v: string) => void,
  post: string,
  setPost: (v: string) => void,
  inv: string,
  setInv: (v: string) => void,
  t: VersionFieldsProps["t"]
): JSX.Element {
  return (
    <div>
      <label htmlFor="icd-nv-direction" style={labelStyle}>
        {t("icds.direction")}
      </label>
      <select
        id="icd-nv-direction"
        data-testid="icd-nv-direction-select"
        value={direction}
        onChange={(e) =>
          setDirection(e.target.value as "unidirectional" | "bidirectional")
        }
        style={inputStyle}
      >
        <option value="unidirectional">{t("icds.directionUnidirectional")}</option>
        <option value="bidirectional">{t("icds.directionBidirectional")}</option>
      </select>

      <label htmlFor="icd-nv-interface-type" style={labelStyle}>
        {t("icds.interfaceType")}
      </label>
      <select
        id="icd-nv-interface-type"
        data-testid="icd-nv-interface-type-select"
        value={interfaceType}
        onChange={(e) => setInterfaceType(e.target.value)}
        style={inputStyle}
      >
        <option value="">{t("icds.selectInterfaceType")}</option>
        <option value="provides">Provides</option>
        <option value="requires">Requires</option>
        <option value="event-in">Event In</option>
        <option value="event-out">Event Out</option>
        <option value="data">Data</option>
        <option value="control">Control</option>
      </select>

      <label htmlFor="icd-nv-contract" style={labelStyle}>
        {t("icds.contract")}
      </label>
      <textarea
        id="icd-nv-contract"
        data-testid="icd-nv-contract-textarea"
        value={contract}
        onChange={(e) => setContract(e.target.value)}
        rows={4}
        style={{ ...inputStyle, fontFamily: "inherit" }}
      />

      <label htmlFor="icd-nv-pre" style={labelStyle}>
        {t("icds.preconditions")}
      </label>
      <textarea
        id="icd-nv-pre"
        data-testid="icd-nv-pre-input"
        value={pre}
        onChange={(e) => setPre(e.target.value)}
        rows={2}
        style={{ ...inputStyle, fontFamily: "inherit" }}
      />

      <label htmlFor="icd-nv-post" style={labelStyle}>
        {t("icds.postconditions")}
      </label>
      <textarea
        id="icd-nv-post"
        data-testid="icd-nv-post-input"
        value={post}
        onChange={(e) => setPost(e.target.value)}
        rows={2}
        style={{ ...inputStyle, fontFamily: "inherit" }}
      />

      <label htmlFor="icd-nv-inv" style={labelStyle}>
        {t("icds.invariants")}
      </label>
      <textarea
        id="icd-nv-inv"
        data-testid="icd-nv-inv-input"
        value={inv}
        onChange={(e) => setInv(e.target.value)}
        rows={2}
        style={{ ...inputStyle, fontFamily: "inherit" }}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// SimilarIcdsPanel — shows similar interfaces based on name similarity
// ---------------------------------------------------------------------------

interface SimilarIcdsPanelProps {
  currentICD: Icd | null;
  allICDs: Icd[];
  onSelect: (icdId: string) => void;
}

function SimilarIcdsPanel({
  currentICD,
  allICDs,
  onSelect,
}: SimilarIcdsPanelProps): JSX.Element {
  const { t } = useTranslation();

  // REQ-092: memoized for performance — findSimilarICDs runs an O(n·m) Jaccard
  // similarity over every ICD and sorts the result. Without memoization this
  // recomputes on every parent re-render (e.g. new-version form keystrokes);
  // memoizing on [currentICD, allICDs] recomputes only when the inputs change.
  const similarICDs = useMemo(
    () => (currentICD ? findSimilarICDs(currentICD, allICDs) : []),
    [currentICD, allICDs]
  );

  if (!currentICD || similarICDs.length === 0) {
    return <div />;
  }

  return (
    <div
      data-testid="similar-icds-panel"
      style={{
        background: "var(--color-warning-bg)",
        border: "1px solid var(--color-warning)",
        borderRadius: "var(--radius-lg)",
        padding: "var(--space-4)",
        marginBottom: "var(--space-6)",
      }}
    >
      <h4
        style={{
          fontSize: "var(--font-size-base)",
          fontWeight: 600,
          color: "var(--color-text)",
          margin: "0 0 var(--space-3) 0",
        }}
      >
        {t("icds.similarInterfaces", "Similar Interfaces")}
      </h4>
      <ul
        style={{
          listStyle: "none",
          padding: 0,
          margin: 0,
        }}
      >
        {similarICDs.map(({ icd, score }) => (
          <li
            key={icd.id}
            data-testid={`similar-icd-${icd.id}`}
            onClick={() => onSelect(icd.id)}
            style={{
              padding: "var(--space-3)",
              marginBottom: "var(--space-2)",
              background: "var(--color-surface)",
              border: "1px solid var(--color-border)",
              borderRadius: "var(--radius-md)",
              cursor: "pointer",
              transition: "var(--transition-fast)",
            }}
            onMouseEnter={(e) => {
              (e.currentTarget as HTMLLIElement).style.background =
                "var(--color-surface-raised)";
              (e.currentTarget as HTMLLIElement).style.borderColor =
                "var(--color-primary)";
            }}
            onMouseLeave={(e) => {
              (e.currentTarget as HTMLLIElement).style.background =
                "var(--color-surface)";
              (e.currentTarget as HTMLLIElement).style.borderColor =
                "var(--color-border)";
            }}
          >
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
              }}
            >
              <span
                style={{
                  fontWeight: 500,
                  color: "var(--color-text)",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                  flex: 1,
                }}
              >
                {icd.name}
              </span>
              <span
                data-testid={`similarity-score-${icd.id}`}
                style={{
                  fontSize: "var(--font-size-sm)",
                  fontWeight: 600,
                  color: "var(--color-warning-text)",
                  marginLeft: "var(--space-2)",
                  whiteSpace: "nowrap",
                }}
              >
                {Math.round(score * 100)}%
              </span>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
