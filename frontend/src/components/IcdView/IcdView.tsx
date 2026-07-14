/**
 * ARCH-L1-001 ReactFrontend — IcdView (REQ-L0-017, REQ-L1-028, REQ-L2-ICD-001) — Container.
 *
 * leaf_id: COMP-RF-001 (NavigationShell — gated by preset)
 * req_id:  REQ-L0-017 (Rekursive Architektur-Hierarchie mit versionierten ICDs),
 *          REQ-L1-028 (ICD-Verwaltung),
 *          REQ-L2-ICD-001 (CRUD + immutable Versioning),
 *          REQ-002 (Split-View Layout),
 *          REQ-050 (Container/Presenter decomposition)
 *
 * Interface Control Document management in a split-view layout:
 *   - Left panel: list of all ICDs in the active workspace (+ create button)
 *   - Divider: 4px resizable
 *   - Right panel: create form OR the IcdDetailPane presenter (version history,
 *     "New Version" flow and traceability sidebar)
 *
 * Data-fetching lives in useIcdData (TanStack Query); this container owns only
 * UI + form state and orchestrates create / new-version.
 *
 * NOTE: Past versions are immutable. There is no DELETE button — the DB
 * trigger `trg_icd_version_immutable` (ADR-ICD-01) makes deletion a
 * privileged trigger-bypassing operation, not exposed in the UI.
 * Use "archive" / "supersede" semantics via the new-version flow.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useParams, useNavigate } from "react-router-dom";
import {
  type CreateIcdPayload,
  type Icd,
  type NewVersionPayload,
} from "../../api/icds";
import type { ArchitectureElement } from "../../types";
import { SplitView } from "../SplitView/SplitView";
import { IcdDetailPane } from "./IcdDetailPane";
import { useIcdData } from "./useIcdData";
import {
  extractErrorMessage,
  inputStyle,
  joinListField,
  labelStyle,
  parseListField,
  shortId,
} from "./icd-view-shared";

export default function IcdView(): JSX.Element {
  const { t } = useTranslation();
  const { id: routeId } = useParams<{ id?: string }>();
  const navigate = useNavigate();

  const {
    icds,
    architectureElements,
    isLoading,
    isLoadingArch,
    isLoadingDetail,
    error,
    selectedDetail,
    createIcd,
    createVersion,
  } = useIcdData(routeId);

  // ---- UI + form state -----------------------------------------------------
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

  // Pre-fill the new-version form whenever the selected detail (re)loads.
  useEffect(() => {
    if (!selectedDetail) return;
    setNvDirection(selectedDetail.direction ?? "unidirectional");
    setNvInterfaceType(selectedDetail.interface_type ?? "");
    setNvContract(selectedDetail.semantic_description ?? "");
    setNvPre(joinListField(selectedDetail.preconditions));
    setNvPost(joinListField(selectedDetail.postconditions));
    setNvInv(joinListField(selectedDetail.invariants));
  }, [selectedDetail]);

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
    const payload: Omit<CreateIcdPayload, "workspace_id"> = {
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
      const created = await createIcd(payload);
      setShowCreate(false);
      resetCreateForm();
      navigate(`/icds/${created.id}`);
    } catch (err) {
      setFormError(extractErrorMessage(err, t("icds.createFailed")));
    } finally {
      setIsSaving(false);
    }
  }, [
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
    createIcd,
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
      await createVersion(routeId, payload);
      setShowNewVersion(false);
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
    createVersion,
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
    [architectureById],
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
          onClick={() => navigate(0)}
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
          <div data-testid="create-icd-form" style={{ maxWidth: "720px" }}>
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
                  e.target.value as "unidirectional" | "bidirectional",
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
                disabled={
                  isSaving || isLoadingArch || architectureElements.length < 2
                }
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
