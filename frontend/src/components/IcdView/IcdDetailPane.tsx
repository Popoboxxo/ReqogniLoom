/**
 * ARCH-L1-001 ReactFrontend — IcdDetailPane (Presenter).
 *
 * leaf_id: COMP-RF-001 (IcdView)
 * req_id:  REQ-L2-ICD-001 (ICD CRUD + immutable versioning),
 *          REQ-L1-095 (ArtifactInspector adoption), REQ-006 (similar interfaces),
 *          REQ-092 (memoized read-only fields), REQ-050 (Container/Presenter split)
 *
 * Right-panel detail view for a single ICD: read-only contract, the new-version
 * form and the "Similar Interfaces" panel. Pure presenter — all state and the
 * new-version submit are driven by props from the IcdView container.
 */

import { memo, useMemo } from "react";
import { useTranslation } from "react-i18next";
import type { Icd, IcdDetail } from "../../api/icds";
import { VersionBadge } from "../shared/VersionBadge";
import { RightSidebar } from "../shared/ArtifactInspector";
import type { VersionRef } from "../shared/ArtifactInspector";
import { findSimilarICDs, inputStyle, labelStyle } from "./icd-view-shared";

export interface IcdDetailPaneProps {
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
export function IcdDetailPane({
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
