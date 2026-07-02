/**
 * ARCH-L1-001 ReactFrontend — IcdList (REQ-L1-040 Phase 2).
 *
 * leaf_id: COMP-RF-001
 * req_id:  REQ-L1-040 (SE Masks Unification — ModalDialogBase adoption),
 *          REQ-L2-ICD-001 (CRUD + immutable Versioning)
 *
 * Dual-modal ICD list view built on ModalDialogBase:
 *   1. CREATE workflow — new ICD (name, source/target, contract spec, v1)
 *   2. NEW VERSION workflow — appends an immutable IcdVersion to an
 *      existing ICD (contract fields editable, version auto-incremented)
 *
 * Versioning / immutability contract (PRESERVED, NOT refactored):
 *   - icdsApi.createVersion() APPENDS a new IcdVersion; past versions are
 *     never modified (DB trigger `trg_icd_version_immutable`, ADR-ICD-01).
 *   - No DELETE is exposed — supersede via the new-version flow instead.
 *   - The current version number is displayed read-only; the next version
 *     number is computed by the backend, never by this component.
 *
 * Interfaces implemented:
 *   IF-RF-INT-002 ← I18nService via useTranslation
 *   IF-RF-EXT-OUT-001 → icdsApi (POST /api/v1/icds/, PATCH /api/v1/icds/<id>/)
 *   IF-RF-EXT-OUT-001 → architectureApi.listAll (source/target dropdowns)
 */

import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useWorkspace } from "../../context/WorkspaceContext";
import {
  icdsApi,
  type Icd,
  type IcdDetail,
  type CreateIcdPayload,
  type NewVersionPayload,
} from "../../api/icds";
import { architectureApi } from "../../api/architecture";
import ModalDialogBase, {
  SHARED_STYLES,
} from "../RequirementsList/ModalDialogBase";
import type { ArchitectureElement } from "../../types";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

type Direction = "unidirectional" | "bidirectional";

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

function shortId(id: string): string {
  return `${id.slice(0, 8)}…`;
}

// ---------------------------------------------------------------------------
// Contract form fields — shared between CREATE and NEW VERSION modals.
// The pre/post/invariant textareas map to the backend contract payload
// (preconditions[], postconditions[], invariants[], semantic_description).
// ---------------------------------------------------------------------------

interface ContractFieldsProps {
  idPrefix: string;
  direction: Direction;
  setDirection: (v: Direction) => void;
  interfaceType: string;
  setInterfaceType: (v: string) => void;
  contract: string;
  setContract: (v: string) => void;
  pre: string;
  setPre: (v: string) => void;
  post: string;
  setPost: (v: string) => void;
  inv: string;
  setInv: (v: string) => void;
  disabled: boolean;
}

function ContractFields({
  idPrefix,
  direction,
  setDirection,
  interfaceType,
  setInterfaceType,
  contract,
  setContract,
  pre,
  setPre,
  post,
  setPost,
  inv,
  setInv,
  disabled,
}: ContractFieldsProps): JSX.Element {
  const { t } = useTranslation();
  const textareaStyle: React.CSSProperties = {
    ...SHARED_STYLES.input,
    fontFamily: "inherit",
    resize: "vertical",
  };

  return (
    <>
      <div>
        <label htmlFor={`${idPrefix}-direction`} style={SHARED_STYLES.label}>
          {t("icds.direction")}
        </label>
        <select
          id={`${idPrefix}-direction`}
          data-testid={`${idPrefix}-direction-select`}
          value={direction}
          onChange={(e) => setDirection(e.target.value as Direction)}
          disabled={disabled}
          style={SHARED_STYLES.input}
        >
          <option value="unidirectional">
            {t("icds.directionUnidirectional")}
          </option>
          <option value="bidirectional">
            {t("icds.directionBidirectional")}
          </option>
        </select>
      </div>
      <div>
        <label
          htmlFor={`${idPrefix}-interface-type`}
          style={SHARED_STYLES.label}
        >
          {t("icds.interfaceType")}
        </label>
        <input
          id={`${idPrefix}-interface-type`}
          data-testid={`${idPrefix}-interface-type-input`}
          type="text"
          value={interfaceType}
          onChange={(e) => setInterfaceType(e.target.value)}
          disabled={disabled}
          placeholder={t("icds.interfaceTypePlaceholder")}
          style={SHARED_STYLES.input}
        />
      </div>
      <div>
        <label htmlFor={`${idPrefix}-contract`} style={SHARED_STYLES.label}>
          {t("icds.contract")}
        </label>
        <textarea
          id={`${idPrefix}-contract`}
          data-testid={`${idPrefix}-contract-textarea`}
          value={contract}
          onChange={(e) => setContract(e.target.value)}
          disabled={disabled}
          rows={4}
          placeholder={t("icds.contractPlaceholder")}
          style={textareaStyle}
        />
      </div>
      <div>
        <label htmlFor={`${idPrefix}-pre`} style={SHARED_STYLES.label}>
          {t("icds.preconditions")}
        </label>
        <textarea
          id={`${idPrefix}-pre`}
          data-testid={`${idPrefix}-pre-input`}
          value={pre}
          onChange={(e) => setPre(e.target.value)}
          disabled={disabled}
          rows={2}
          placeholder="One per line"
          style={textareaStyle}
        />
      </div>
      <div>
        <label htmlFor={`${idPrefix}-post`} style={SHARED_STYLES.label}>
          {t("icds.postconditions")}
        </label>
        <textarea
          id={`${idPrefix}-post`}
          data-testid={`${idPrefix}-post-input`}
          value={post}
          onChange={(e) => setPost(e.target.value)}
          disabled={disabled}
          rows={2}
          placeholder="One per line"
          style={textareaStyle}
        />
      </div>
      <div>
        <label htmlFor={`${idPrefix}-inv`} style={SHARED_STYLES.label}>
          {t("icds.invariants")}
        </label>
        <textarea
          id={`${idPrefix}-inv`}
          data-testid={`${idPrefix}-inv-input`}
          value={inv}
          onChange={(e) => setInv(e.target.value)}
          disabled={disabled}
          rows={2}
          placeholder="One per line"
          style={textareaStyle}
        />
      </div>
    </>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function IcdList(): JSX.Element {
  const { t } = useTranslation();
  const { activeWorkspace } = useWorkspace();

  // ---- List state ----------------------------------------------------------
  const [icds, setIcds] = useState<Icd[]>([]);
  const [architectureElements, setArchitectureElements] = useState<
    ArchitectureElement[]
  >([]);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  // ---- CREATE modal state --------------------------------------------------
  const [showCreate, setShowCreate] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [name, setName] = useState("");
  const [source, setSource] = useState("");
  const [target, setTarget] = useState("");
  const [direction, setDirection] = useState<Direction>("unidirectional");
  const [interfaceType, setInterfaceType] = useState("");
  const [contract, setContract] = useState("");
  const [pre, setPre] = useState("");
  const [post, setPost] = useState("");
  const [inv, setInv] = useState("");

  // ---- NEW VERSION modal state ----------------------------------------------
  // nvTarget holds the IcdDetail of the ICD being versioned. Its `version`
  // field is the CURRENT (latest) version — the only version that may evolve.
  // Older versions are immutable by contract and are never loaded for edit.
  const [nvTarget, setNvTarget] = useState<IcdDetail | null>(null);
  const [nvLoadingId, setNvLoadingId] = useState<string | null>(null);
  const [nvError, setNvError] = useState<string | null>(null);
  const [nvSubmitting, setNvSubmitting] = useState(false);
  const [nvDirection, setNvDirection] = useState<Direction>("unidirectional");
  const [nvInterfaceType, setNvInterfaceType] = useState("");
  const [nvContract, setNvContract] = useState("");
  const [nvPre, setNvPre] = useState("");
  const [nvPost, setNvPost] = useState("");
  const [nvInv, setNvInv] = useState("");

  // ---- Data loading ----------------------------------------------------------

  const loadList = useCallback(async (): Promise<void> => {
    if (!activeWorkspace) {
      setIcds([]);
      setArchitectureElements([]);
      setIsLoading(false);
      return;
    }
    setIsLoading(true);
    setLoadError(null);
    try {
      const [icdResp, archAll] = await Promise.all([
        icdsApi.list(activeWorkspace.id),
        architectureApi.listAll(activeWorkspace.id),
      ]);
      setIcds(icdResp.results);
      setArchitectureElements(archAll);
    } catch (err) {
      setLoadError(extractErrorMessage(err, t("icds.loadFailed")));
    } finally {
      setIsLoading(false);
    }
  }, [activeWorkspace, t]);

  useEffect(() => {
    void loadList();
  }, [loadList]);

  // ---- Derived data ----------------------------------------------------------

  const architectureById = useMemo(() => {
    const m = new Map<string, ArchitectureElement>();
    for (const el of architectureElements) m.set(el.id, el);
    return m;
  }, [architectureElements]);

  const artifactLabel = useCallback(
    (id: string): string => {
      const el = architectureById.get(id);
      return el ? `${el.title} (${el.element_type})` : shortId(id);
    },
    [architectureById]
  );

  // Group ICDs by name — logical identities sharing a name form one group
  // whose entries represent independent versioned contracts.
  const groupedIcds = useMemo(() => {
    const groups = new Map<string, Icd[]>();
    for (const icd of icds) {
      const bucket = groups.get(icd.name);
      if (bucket) bucket.push(icd);
      else groups.set(icd.name, [icd]);
    }
    return groups;
  }, [icds]);

  // ---- CREATE workflow -------------------------------------------------------

  const resetCreateForm = (): void => {
    setName("");
    setSource("");
    setTarget("");
    setDirection("unidirectional");
    setInterfaceType("");
    setContract("");
    setPre("");
    setPost("");
    setInv("");
    setFormError(null);
  };

  const closeCreate = (): void => {
    resetCreateForm();
    setShowCreate(false);
  };

  const toggleCreate = (): void => {
    if (showCreate) {
      closeCreate();
    } else {
      // Modals are mutually exclusive — close the new-version modal first.
      closeNewVersion();
      setShowCreate(true);
    }
  };

  const handleCreateSubmit = async (
    e: React.FormEvent<HTMLFormElement>
  ): Promise<void> => {
    e.preventDefault();
    if (!activeWorkspace) return;
    if (!name.trim()) {
      setFormError(t("icds.nameRequired"));
      return;
    }
    if (!source) {
      setFormError(t("icds.sourceRequired"));
      return;
    }
    if (!target) {
      setFormError(t("icds.targetRequired"));
      return;
    }
    if (source === target) {
      setFormError(t("traceability.sameEndpoints"));
      return;
    }
    setIsSubmitting(true);
    setFormError(null);
    const payload: CreateIcdPayload = {
      workspace_id: activeWorkspace.id,
      name: name.trim(),
      source_element_id: source,
      target_element_id: target,
      direction,
      interface_type: interfaceType.trim(),
      semantic_description: contract,
      preconditions: parseListField(pre),
      postconditions: parseListField(post),
      invariants: parseListField(inv),
    };
    try {
      await icdsApi.create(payload);
      closeCreate();
      await loadList();
    } catch (err) {
      setFormError(extractErrorMessage(err, t("icds.createFailed")));
    } finally {
      setIsSubmitting(false);
    }
  };

  // ---- NEW VERSION workflow ---------------------------------------------------

  const closeNewVersion = (): void => {
    setNvTarget(null);
    setNvError(null);
  };

  const openNewVersion = async (icd: Icd): Promise<void> => {
    // Mutually exclusive with the create modal.
    closeCreate();
    setNvLoadingId(icd.id);
    setNvError(null);
    try {
      // Fetch the CURRENT version's contract as the editing baseline.
      // Past versions stay untouched — createVersion() appends, never mutates.
      const detail = await icdsApi.get(icd.id);
      setNvDirection(detail.direction ?? "unidirectional");
      setNvInterfaceType(detail.interface_type ?? "");
      setNvContract(detail.semantic_description ?? "");
      setNvPre(joinListField(detail.preconditions));
      setNvPost(joinListField(detail.postconditions));
      setNvInv(joinListField(detail.invariants));
      setNvTarget(detail);
    } catch (err) {
      setLoadError(extractErrorMessage(err, t("icds.loadFailed")));
    } finally {
      setNvLoadingId(null);
    }
  };

  const handleNewVersionSubmit = async (
    e: React.FormEvent<HTMLFormElement>
  ): Promise<void> => {
    e.preventDefault();
    if (!nvTarget) return;
    setNvSubmitting(true);
    setNvError(null);
    const payload: NewVersionPayload = {
      direction: nvDirection,
      interface_type: nvInterfaceType.trim(),
      semantic_description: nvContract,
      preconditions: parseListField(nvPre),
      postconditions: parseListField(nvPost),
      invariants: parseListField(nvInv),
    };
    try {
      await icdsApi.createVersion(nvTarget.id, payload);
      closeNewVersion();
      await loadList();
    } catch (err) {
      setNvError(extractErrorMessage(err, t("icds.newVersionFailed")));
    } finally {
      setNvSubmitting(false);
    }
  };

  // ---- Render ------------------------------------------------------------------

  if (isLoading) {
    return (
      <p role="status" style={{ color: "var(--color-text-muted)" }}>
        {t("loading")}
      </p>
    );
  }

  if (loadError) {
    return (
      <div role="alert">
        <p style={{ color: "var(--color-danger)" }}>{loadError}</p>
        <button
          type="button"
          onClick={() => void loadList()}
          style={SHARED_STYLES.primaryButton}
        >
          {t("actions.reload")}
        </button>
      </div>
    );
  }

  return (
    <>
      {/* Modal 1: CREATE new ICD */}
      <ModalDialogBase
        title={t("icds.title")}
        isOpen={showCreate}
        onToggle={toggleCreate}
        onSubmit={handleCreateSubmit}
        onCancel={closeCreate}
        error={formError}
        isSubmitting={isSubmitting}
        itemCount={icds.length}
        testIdPrefix="icd"
        buttonTestIdPrefix="icd"
        newButtonLabel={`+ ${t("icds.create")}`}
      >
        <div>
          <label htmlFor="icd-name" style={SHARED_STYLES.label}>
            {t("icds.nameLabel")} *
          </label>
          <input
            id="icd-name"
            data-testid="icd-name-input"
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            autoFocus
            disabled={isSubmitting}
            placeholder={t("icds.namePlaceholder")}
            style={SHARED_STYLES.input}
          />
        </div>
        <div>
          <label htmlFor="icd-source" style={SHARED_STYLES.label}>
            {t("icds.source")} *
          </label>
          <select
            id="icd-source"
            data-testid="icd-source-select"
            value={source}
            onChange={(e) => setSource(e.target.value)}
            disabled={isSubmitting}
            style={SHARED_STYLES.input}
          >
            <option value="">{t("icds.selectSource")}</option>
            {architectureElements.map((el) => (
              <option key={el.id} value={el.id}>
                {el.title} ({el.element_type})
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="icd-target" style={SHARED_STYLES.label}>
            {t("icds.target")} *
          </label>
          <select
            id="icd-target"
            data-testid="icd-target-select"
            value={target}
            onChange={(e) => setTarget(e.target.value)}
            disabled={isSubmitting}
            style={SHARED_STYLES.input}
          >
            <option value="">{t("icds.selectTarget")}</option>
            {architectureElements.map((el) => (
              <option key={el.id} value={el.id}>
                {el.title} ({el.element_type})
              </option>
            ))}
          </select>
        </div>
        <ContractFields
          idPrefix="icd"
          direction={direction}
          setDirection={setDirection}
          interfaceType={interfaceType}
          setInterfaceType={setInterfaceType}
          contract={contract}
          setContract={setContract}
          pre={pre}
          setPre={setPre}
          post={post}
          setPost={setPost}
          inv={inv}
          setInv={setInv}
          disabled={isSubmitting}
        />
      </ModalDialogBase>

      {/* Modal 2: NEW VERSION for existing ICD (append-only, immutable past) */}
      {nvTarget && (
        <ModalDialogBase
          title={`${t("icds.newVersion")}: ${nvTarget.name}`}
          isOpen={true}
          onToggle={closeNewVersion}
          onSubmit={handleNewVersionSubmit}
          onCancel={closeNewVersion}
          error={nvError}
          isSubmitting={nvSubmitting}
          itemCount={1}
          testIdPrefix="icd-nv"
          buttonTestIdPrefix="icd-nv"
        >
          <p
            data-testid="icd-nv-immutable-hint"
            style={{
              fontSize: "var(--font-size-sm)",
              color: "var(--color-text-muted)",
              margin: 0,
            }}
          >
            {t("icds.immutableHint")}
          </p>
          {/* Version is auto-incremented by the backend — read-only display */}
          <div>
            <label style={SHARED_STYLES.label}>
              {t("icds.currentVersion")}
            </label>
            <div
              data-testid="icd-nv-version-display"
              aria-readonly="true"
              style={{
                ...SHARED_STYLES.input,
                background: "var(--color-surface-raised)",
                color: "var(--color-text-muted)",
              }}
            >
              {t("icds.versionBadge", { n: nvTarget.version })} →{" "}
              {t("icds.versionBadge", { n: nvTarget.version + 1 })}
            </div>
          </div>
          <ContractFields
            idPrefix="icd-nv"
            direction={nvDirection}
            setDirection={setNvDirection}
            interfaceType={nvInterfaceType}
            setInterfaceType={setNvInterfaceType}
            contract={nvContract}
            setContract={setNvContract}
            pre={nvPre}
            setPre={setNvPre}
            post={nvPost}
            setPost={setNvPost}
            inv={nvInv}
            setInv={setNvInv}
            disabled={nvSubmitting}
          />
        </ModalDialogBase>
      )}

      {/* ICD list — grouped by name; each row offers the new-version flow */}
      {icds.length > 0 && (
        <div data-testid="icd-groups">
          {Array.from(groupedIcds.entries()).map(([groupName, entries]) => (
            <div key={groupName} style={{ marginBottom: "var(--space-4)" }}>
              <h3
                style={{
                  fontSize: "var(--font-size-base)",
                  fontWeight: 600,
                  color: "var(--color-text)",
                  margin: "0 0 var(--space-2) 0",
                }}
              >
                {groupName}
              </h3>
              <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
                {entries.map((icd) => (
                  <li
                    key={icd.id}
                    data-testid={`icd-item-${icd.id}`}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "var(--space-3)",
                      padding: "var(--space-3) var(--space-4)",
                      marginBottom: "var(--space-2)",
                      background: "var(--color-surface)",
                      borderRadius: "var(--radius-md)",
                      border: "1px solid var(--color-border)",
                    }}
                  >
                    <span style={{ flex: 1, minWidth: 0 }}>
                      <span
                        style={{
                          display: "block",
                          color: "var(--color-text-muted)",
                          fontSize: "var(--font-size-sm)",
                        }}
                      >
                        {t("icds.source")}:{" "}
                        {artifactLabel(icd.source_element_id)} →{" "}
                        {t("icds.target")}:{" "}
                        {artifactLabel(icd.target_element_id)}
                      </span>
                    </span>
                    <button
                      type="button"
                      data-testid={`icd-new-version-btn-${icd.id}`}
                      onClick={() => void openNewVersion(icd)}
                      disabled={nvLoadingId !== null}
                      style={{
                        ...SHARED_STYLES.primaryButton,
                        opacity: nvLoadingId === icd.id ? 0.6 : 1,
                        cursor:
                          nvLoadingId !== null ? "not-allowed" : "pointer",
                      }}
                    >
                      {nvLoadingId === icd.id
                        ? t("loading")
                        : `+ ${t("icds.newVersion")}`}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </>
  );
}
