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

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useParams, useNavigate } from "react-router-dom";
import {
  type CreateIcdPayload,
  type Icd,
  type NewVersionPayload,
} from "../../api/icds";
import type { ArchitectureElement } from "../../types";
import { SplitView } from "../SplitView/SplitView";
import { PageHeader } from "../shared/PageHeader";
import { Dialog } from "../shared/Dialog";
import { IcdDetailPane } from "./IcdDetailPane";
import { IcdList } from "./IcdList";
import { useIcdData } from "./useIcdData";
import {
  extractErrorMessage,
  joinListField,
  parseListField,
  shortId,
} from "./icd-view-shared";
import styles from "./IcdView.module.css";

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
    refreshList,
    refreshDetail,
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

  const openCreateForm = useCallback((): void => {
    setShowCreate(true);
    setShowNewVersion(false);
    setFormError(null);
  }, []);

  // F-08 (Dialog migration): Escape / backdrop click / × must discard the
  // draft exactly like the existing Cancel button.
  const handleCancelCreate = useCallback((): void => {
    setShowCreate(false);
    resetCreateForm();
  }, []);

  // F-08: initial-focus target for Dialog's focus trap — the form's first
  // real field (name input), not Dialog's own × close button.
  const icdNameInputRef = useRef<HTMLInputElement | null>(null);

  // REQ-173: a workflow transition mutates the ICD's status server-side, so
  // refresh the detail (badge label) and the list (any status column) after it.
  const handleWorkflowTransition = useCallback((): void => {
    void refreshDetail();
    void refreshList();
  }, [refreshDetail, refreshList]);

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
          className={styles.viewLoading}
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
        className={styles.errorPanel}
      >
        <p className={styles.errorPanelText}>{error}</p>
        <button
          onClick={() => navigate(0)}
          className={styles.reloadButton}
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
      className={styles.root}
    >
      {/* 12.1: exactly one <h1>, always-visible summary, one primary action
          — replaces the bare <h3>({count}) header that used to live inline
          in the left panel. */}
      <PageHeader
        title={t("icds.title")}
        summary={t("icds.summary", { count: icds.length })}
        primaryAction={{
          label: t("icds.create"),
          prefixWithPlus: true,
          onClick: openCreateForm,
          testId: "create-icd-btn",
        }}
      />

      <div className={styles.splitHost}>
      <SplitView
        moduleType="icds"
        leftMinWidth={280}
        leftPanel={
          <IcdList
            items={icds}
            selectedId={!showCreate ? routeId : undefined}
            onSelect={handleSelectIcd}
            onCreateNew={openCreateForm}
          />
        }
        rightPanel={
          showCreate ? (
          // F-08 (Dialog migration): wrapped in the shared Dialog primitive
          // (GESAMTTEST_BERICHT 2026-08-21 §5 finding 8); form markup unchanged.
          <Dialog
            title={t("icds.create")}
            onClose={handleCancelCreate}
            initialFocusRef={icdNameInputRef}
            size="lg"
            testId="create-icd-dialog"
          >
          <div data-testid="create-icd-form" className={styles.createForm}>
            <h3
              className={styles.createHeading}
            >
              + {t("icds.create")}
            </h3>

            {!isLoadingArch && architectureElements.length < 2 && (
              <p
                data-testid="icd-needs-elements-hint"
                className={styles.needsElementsHint}
              >
                {t("icds.needsElementsHint")}
              </p>
            )}

            <label htmlFor="icd-name" className={styles.fieldLabel}>
              {t("icds.nameLabel")}
            </label>
            <input
              id="icd-name"
              data-testid="icd-name-input"
              ref={icdNameInputRef}
              type="text"
              value={formName}
              onChange={(e) => setFormName(e.target.value)}
              placeholder={t("icds.namePlaceholder")}
              className={styles.fieldInput}
            />

            <label htmlFor="icd-source" className={styles.fieldLabel}>
              {t("icds.source")}
            </label>
            <select
              id="icd-source"
              data-testid="icd-source-select"
              value={formSource}
              onChange={(e) => setFormSource(e.target.value)}
              disabled={isLoadingArch && architectureElements.length === 0}
              className={styles.fieldInput}
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

            <label htmlFor="icd-target" className={styles.fieldLabel}>
              {t("icds.target")}
            </label>
            <select
              id="icd-target"
              data-testid="icd-target-select"
              value={formTarget}
              onChange={(e) => setFormTarget(e.target.value)}
              disabled={isLoadingArch && architectureElements.length === 0}
              className={styles.fieldInput}
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

            <label htmlFor="icd-direction" className={styles.fieldLabel}>
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
              className={styles.fieldInput}
            >
              <option value="unidirectional">
                {t("icds.directionUnidirectional")}
              </option>
              <option value="bidirectional">
                {t("icds.directionBidirectional")}
              </option>
            </select>

            <label htmlFor="icd-interface-type" className={styles.fieldLabel}>
              {t("icds.interfaceType")}
            </label>
            <select
              id="icd-interface-type"
              data-testid="icd-interface-type-select"
              value={formInterfaceType}
              onChange={(e) => setFormInterfaceType(e.target.value)}
              className={styles.fieldInput}
            >
              <option value="">{t("icds.selectInterfaceType")}</option>
              <option value="provides">Provides</option>
              <option value="requires">Requires</option>
              <option value="event-in">Event In</option>
              <option value="event-out">Event Out</option>
              <option value="data">Data</option>
              <option value="control">Control</option>
            </select>

            <label htmlFor="icd-contract" className={styles.fieldLabel}>
              {t("icds.contract")}
            </label>
            <textarea
              id="icd-contract"
              data-testid="icd-contract-textarea"
              value={formContract}
              onChange={(e) => setFormContract(e.target.value)}
              placeholder={t("icds.contractPlaceholder")}
              rows={4}
              className={styles.fieldTextarea}
            />

            <label htmlFor="icd-preconditions" className={styles.fieldLabel}>
              {t("icds.preconditions")}
            </label>
            <textarea
              id="icd-preconditions"
              data-testid="icd-preconditions-input"
              value={formPre}
              onChange={(e) => setFormPre(e.target.value)}
              rows={2}
              className={styles.fieldTextarea}
              placeholder={t("icds.onePerLinePlaceholder")}
            />

            <label htmlFor="icd-postconditions" className={styles.fieldLabel}>
              {t("icds.postconditions")}
            </label>
            <textarea
              id="icd-postconditions"
              data-testid="icd-postconditions-input"
              value={formPost}
              onChange={(e) => setFormPost(e.target.value)}
              rows={2}
              className={styles.fieldTextarea}
              placeholder={t("icds.onePerLinePlaceholder")}
            />

            <label htmlFor="icd-invariants" className={styles.fieldLabel}>
              {t("icds.invariants")}
            </label>
            <textarea
              id="icd-invariants"
              data-testid="icd-invariants-input"
              value={formInv}
              onChange={(e) => setFormInv(e.target.value)}
              rows={2}
              className={styles.fieldTextarea}
              placeholder={t("icds.onePerLinePlaceholder")}
            />

            {formError && (
              <p
                role="alert"
                data-testid="create-icd-error"
                className={styles.formError}
              >
                {formError}
              </p>
            )}

            <div
              className={styles.formActions}
            >
              <button
                type="button"
                data-testid="create-icd-submit"
                onClick={() => void handleCreate()}
                disabled={
                  isSaving || isLoadingArch || architectureElements.length < 2
                }
                className={`${styles.submitButton} ${
                  isSaving || isLoadingArch
                    ? styles.submitButtonDisabled
                    : styles.submitButtonEnabled
                }`}
              >
                {isSaving ? t("actions.saving") : t("actions.save")}
              </button>
              <button
                type="button"
                onClick={handleCancelCreate}
                className={styles.cancelButton}
              >
                {t("actions.cancel")}
              </button>
            </div>
          </div>
          </Dialog>
        ) : routeId && isLoadingDetail ? (
          <p
            role="status"
            className={styles.detailLoading}
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
            onWorkflowTransition={handleWorkflowTransition}
          />
        ) : (
          <p
            className={styles.selectPrompt}
          >
            {t("icds.selectIcd", "Select an ICD from the list to view details.")}
          </p>
          )
        }
      />
      </div>
    </div>
  );
}
