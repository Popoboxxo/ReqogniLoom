/**
 * LinkTypeEditorPage — admin UI for the link-type catalog (spec section 4.2).
 *
 * leaf_id: COMP-RF-LTE-001
 *
 * Global scope manages the tenant-wide templates (`/link-type-defaults/`);
 * workspace scope manages the materialized per-workspace catalog
 * (`/workspaces/<id>/link-type-definitions/`). Both render the same flat
 * list of rows with an inline expand-to-edit form — `system_owned` rows are
 * locked (greyed out, lock glyph, no edit action), mirroring how locked
 * attributes render elsewhere in the admin UI.
 *
 * Every `style=` prop below is a hoisted `React.CSSProperties` const, never
 * an inline double-brace object literal — `src/test/ui-ratchet.test.ts`
 * (`STYLE_BRACE_BASELINE`) fails the build on a new inline-style occurrence
 * under `components/`, so this file must add zero (that pattern even matches
 * inside comments, so this note is deliberately worded around it).
 */

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { linkTypesApi } from "../../api/link-types";
import type {
  GlobalLinkType,
  LinkTypeDefinition,
  LinkTypePair,
  SuspectRule,
  TriLabel,
  WorkspaceLinkType,
} from "../../api/link-types";
import { useWorkspace } from "../../context/WorkspaceContext";
import { PageHeader } from "../shared/PageHeader";

export interface LinkTypeEditorPageProps {
  scope: "global" | "workspace";
}

type LinkTypeRow = WorkspaceLinkType | GlobalLinkType;

/** The four propagation behaviours the backend engine can dispatch on, in
 * the exact order the test file pins for the `<select>`. */
const SUSPECT_RULES: SuspectRule[] = [
  "none",
  "target_change_flags_source",
  "source_change_flags_target",
  "parent_change_flags_children",
];

const EMPTY_TRI_LABEL: TriLabel = { downstream: "", upstream: "", neutral: "" };

const DEFAULT_DEFINITION: LinkTypeDefinition = {
  label: { de: { ...EMPTY_TRI_LABEL }, en: { ...EMPTY_TRI_LABEL } },
  allowed_pairs: [],
  coverage_relevant: false,
  suspect_rule: "none",
  impact_weight: 1,
  manual_creatable: true,
  system_owned: false,
  active: true,
  built_in: false,
};

/** Editable subset of `LinkTypeDefinition`, plus the row key (writable only
 * for a new global type). `original` carries the fields this form never
 * exposes (`manual_creatable`, `system_owned`, `built_in`) through unchanged. */
interface FormState {
  key: string;
  impactWeight: string;
  suspectRule: SuspectRule;
  coverageRelevant: boolean;
  active: boolean;
  allowedPairs: LinkTypePair[];
  labels: Record<"de" | "en", TriLabel>;
  original: LinkTypeDefinition;
}

function toFormState(key: string, definition: LinkTypeDefinition): FormState {
  return {
    key,
    impactWeight: String(definition.impact_weight),
    suspectRule: definition.suspect_rule,
    coverageRelevant: definition.coverage_relevant,
    active: definition.active,
    allowedPairs: definition.allowed_pairs.map((pair) => ({ ...pair })),
    labels: {
      de: { ...definition.label.de },
      en: { ...definition.label.en },
    },
    original: definition,
  };
}

function fromFormState(form: FormState): LinkTypeDefinition {
  return {
    ...form.original,
    label: form.labels,
    allowed_pairs: form.allowedPairs,
    coverage_relevant: form.coverageRelevant,
    suspect_rule: form.suspectRule,
    impact_weight: Number(form.impactWeight) || 0,
    active: form.active,
  };
}

function isWorkspaceRow(row: LinkTypeRow): row is WorkspaceLinkType {
  return "is_customized" in row;
}

function errorMessage(err: unknown): string {
  if (err instanceof Error) return err.message;
  const apiErr = err as { error?: { message?: string } };
  return apiErr?.error?.message ?? String(err);
}

// ---------------------------------------------------------------------------
// Styles (hoisted — see file-level note)
// ---------------------------------------------------------------------------

const pageStyle: React.CSSProperties = {
  maxWidth: "960px",
  margin: "0 auto",
  padding: "var(--space-6)",
};

const listStyle: React.CSSProperties = {
  listStyle: "none",
  margin: "var(--space-5) 0 0",
  padding: 0,
  display: "flex",
  flexDirection: "column",
  gap: "var(--space-2)",
};

const rowStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  gap: "var(--space-3)",
  padding: "var(--space-3) var(--space-4)",
  background: "var(--color-surface)",
  border: "1px solid var(--color-border)",
  borderRadius: "var(--radius-md)",
};

const rowLockedStyle: React.CSSProperties = {
  ...rowStyle,
  background: "var(--color-surface-raised)",
  opacity: 0.65,
};

const rowKeyStyle: React.CSSProperties = {
  fontWeight: 600,
  fontSize: "var(--font-size-base)",
  color: "var(--color-text)",
};

const rowActionsStyle: React.CSSProperties = {
  display: "flex",
  gap: "var(--space-2)",
};

const lockIconStyle: React.CSSProperties = {
  color: "var(--color-text-muted)",
  fontSize: "var(--font-size-sm)",
};

const formStyle: React.CSSProperties = {
  marginTop: "var(--space-2)",
  padding: "var(--space-4)",
  background: "var(--color-surface)",
  border: "1px solid var(--color-border)",
  borderRadius: "var(--radius-md)",
  display: "flex",
  flexDirection: "column",
  gap: "var(--space-3)",
};

const fieldLabelStyle: React.CSSProperties = {
  display: "block",
  marginBottom: "var(--space-1)",
  fontWeight: 600,
  fontSize: "var(--font-size-sm)",
  color: "var(--color-text)",
};

const inputStyle: React.CSSProperties = {
  width: "100%",
  padding: "var(--space-2) var(--space-3)",
  borderRadius: "var(--radius-md)",
  border: "1px solid var(--color-border)",
  background: "var(--color-surface-raised)",
  color: "var(--color-text)",
  fontSize: "var(--font-size-sm)",
  boxSizing: "border-box",
};

const checkboxRowStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: "var(--space-2)",
};

const checkboxLabelStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: "var(--space-2)",
  fontSize: "var(--font-size-sm)",
  color: "var(--color-text)",
};

const labelGridStyle: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(3, 1fr)",
  gap: "var(--space-2)",
};

const labelGroupStyle: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: "var(--space-2)",
};

const pairsContainerStyle: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: "var(--space-2)",
};

const pairRowStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: "var(--space-2)",
};

const pairInputStyle: React.CSSProperties = {
  ...inputStyle,
  width: "auto",
  flex: 1,
};

const formActionsStyle: React.CSSProperties = {
  display: "flex",
  justifyContent: "flex-end",
  gap: "var(--space-2)",
};

/**
 * Inline hint under a control — same shape as `WorkspaceSettings.tsx`'s
 * `hintStyle`, which is this codebase's existing convention for an
 * explanatory note in a settings form.
 */
const hintStyle: React.CSSProperties = {
  margin: "var(--space-1) 0 0",
  fontSize: "var(--font-size-sm)",
  color: "var(--color-text-muted)",
};

const errorStyle: React.CSSProperties = {
  margin: "var(--space-3) 0 0",
  padding: "var(--space-3)",
  color: "var(--color-danger)",
  background: "var(--color-surface)",
  border: "1px solid var(--color-danger)",
  borderRadius: "var(--radius-md)",
  fontSize: "var(--font-size-sm)",
};

// ---------------------------------------------------------------------------
// Inline edit/create form
// ---------------------------------------------------------------------------

interface LinkTypeFormProps {
  form: FormState;
  onChange: (form: FormState) => void;
  onSave: () => void;
  onCancel: () => void;
  saving: boolean;
  isNew?: boolean;
}

function LinkTypeForm({ form, onChange, onSave, onCancel, saving, isNew }: LinkTypeFormProps): JSX.Element {
  const { t } = useTranslation();

  const updatePair = (index: number, field: keyof LinkTypePair, value: string): void => {
    onChange({
      ...form,
      allowedPairs: form.allowedPairs.map((pair, i) => (i === index ? { ...pair, [field]: value } : pair)),
    });
  };

  const addPair = (): void => {
    onChange({ ...form, allowedPairs: [...form.allowedPairs, { source_type: "*", target_type: "*" }] });
  };

  const removePair = (index: number): void => {
    onChange({ ...form, allowedPairs: form.allowedPairs.filter((_, i) => i !== index) });
  };

  const updateLabel = (lang: "de" | "en", perspective: keyof TriLabel, value: string): void => {
    onChange({
      ...form,
      labels: { ...form.labels, [lang]: { ...form.labels[lang], [perspective]: value } },
    });
  };

  return (
    <div style={formStyle}>
      {isNew && (
        <div>
          <label style={fieldLabelStyle} htmlFor="link-type-key-input">
            {t("linkType.key")}
          </label>
          <input
            id="link-type-key-input"
            data-testid="link-type-key-input"
            value={form.key}
            onChange={(e) => onChange({ ...form, key: e.target.value })}
            style={inputStyle}
          />
        </div>
      )}

      <div>
        <label style={fieldLabelStyle} htmlFor="link-type-impact-weight-input">
          {t("linkType.impactWeight")}
        </label>
        <input
          id="link-type-impact-weight-input"
          type="number"
          min="0"
          step="0.1"
          data-testid="link-type-impact-weight-input"
          value={form.impactWeight}
          onChange={(e) => onChange({ ...form, impactWeight: e.target.value })}
          style={inputStyle}
        />
        {/* Honesty note: no backend code reads `impact_weight` or
            `coverage_relevant` from the catalog yet — the coverage
            calculator and the allocation-coverage query still hardcode
            `verifies` / `allocated-to`. The values are stored and returned
            faithfully; they just have no effect on any computation today. */}
        <p style={hintStyle} data-testid="link-type-inert-fields-hint">
          {t("linkType.inertFieldsHint")}
        </p>
      </div>

      <div>
        <label style={fieldLabelStyle} htmlFor="link-type-suspect-rule-select">
          {t("linkType.suspectRule")}
        </label>
        <select
          id="link-type-suspect-rule-select"
          data-testid="link-type-suspect-rule-select"
          value={form.suspectRule}
          onChange={(e) => onChange({ ...form, suspectRule: e.target.value as SuspectRule })}
          style={inputStyle}
        >
          {SUSPECT_RULES.map((rule) => (
            <option key={rule} value={rule}>
              {t(`linkType.suspectRuleValues.${rule}`)}
            </option>
          ))}
        </select>
      </div>

      <div style={checkboxRowStyle}>
        <label style={checkboxLabelStyle}>
          <input
            type="checkbox"
            data-testid="link-type-coverage-relevant-checkbox"
            checked={form.coverageRelevant}
            onChange={(e) => onChange({ ...form, coverageRelevant: e.target.checked })}
          />
          {t("linkType.coverageRelevant")}
        </label>
        {/* Same inert-field caveat as `impact_weight` above — repeated here
            because the checkbox sits far enough from that hint to be read
            on its own. */}
        <span style={hintStyle} data-testid="link-type-coverage-inert-hint">
          {t("linkType.inertFieldsHint")}
        </span>
        <label style={checkboxLabelStyle}>
          <input
            type="checkbox"
            data-testid="link-type-active-checkbox"
            checked={form.active}
            onChange={(e) => onChange({ ...form, active: e.target.checked })}
          />
          {t("linkType.active")}
        </label>
      </div>

      <div>
        <span style={fieldLabelStyle}>{t("linkType.allowedPairs")}</span>
        <div data-testid="link-type-allowed-pairs-editor" style={pairsContainerStyle}>
          {form.allowedPairs.map((pair, index) => (
            // Rows have no stable identity of their own (plain {source_type,
            // target_type} pairs) — the array index is the only key available.
            <div key={index} style={pairRowStyle}>
              <input
                aria-label={t("traceability.source", "Source")}
                data-testid={`link-type-pair-source-${index}`}
                value={pair.source_type}
                onChange={(e) => updatePair(index, "source_type", e.target.value)}
                style={pairInputStyle}
              />
              <input
                aria-label={t("traceability.target", "Target")}
                data-testid={`link-type-pair-target-${index}`}
                value={pair.target_type}
                onChange={(e) => updatePair(index, "target_type", e.target.value)}
                style={pairInputStyle}
              />
              <button
                type="button"
                className="btn-danger"
                data-testid={`link-type-pair-remove-${index}`}
                onClick={() => removePair(index)}
              >
                {t("actions.delete")}
              </button>
            </div>
          ))}
          <button type="button" className="btn-secondary" data-testid="link-type-pair-add" onClick={addPair}>
            {t("actions.add")}
          </button>
        </div>
      </div>

      <div style={labelGridStyle}>
        {(["de", "en"] as const).map((lang) => (
          <div key={lang} style={labelGroupStyle}>
            <span style={fieldLabelStyle}>{lang.toUpperCase()}</span>
            {(["downstream", "upstream", "neutral"] as const).map((perspective) => (
              <input
                key={perspective}
                aria-label={`${lang} ${perspective}`}
                data-testid={`link-type-label-${lang}-${perspective}-input`}
                value={form.labels[lang][perspective]}
                onChange={(e) => updateLabel(lang, perspective, e.target.value)}
                style={inputStyle}
              />
            ))}
          </div>
        ))}
      </div>

      <div style={formActionsStyle}>
        <button
          type="button"
          className="btn-secondary"
          data-testid="link-type-cancel-button"
          onClick={onCancel}
          disabled={saving}
        >
          {t("actions.cancel")}
        </button>
        <button
          type="button"
          className="btn-primary"
          data-testid="link-type-save-button"
          onClick={onSave}
          disabled={saving}
        >
          {t("actions.save")}
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export function LinkTypeEditorPage({ scope }: LinkTypeEditorPageProps): JSX.Element {
  const { t } = useTranslation();
  const { activeWorkspace } = useWorkspace();
  const workspaceId = activeWorkspace?.id;

  const [rows, setRows] = useState<LinkTypeRow[]>([]);
  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [creatingNew, setCreatingNew] = useState(false);
  const [form, setForm] = useState<FormState | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load(): Promise<void> {
      try {
        if (scope === "global") {
          const data = await linkTypesApi.listGlobal();
          if (!cancelled) setRows(data);
        } else if (workspaceId) {
          const data = await linkTypesApi.listForWorkspace(workspaceId);
          if (!cancelled) setRows(data);
        }
      } catch (err) {
        if (!cancelled) setError(errorMessage(err));
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [scope, workspaceId]);

  const openEdit = (row: LinkTypeRow): void => {
    setEditingKey(row.key);
    setCreatingNew(false);
    setForm(toFormState(row.key, row.definition));
    setError(null);
  };

  const openNew = (): void => {
    setCreatingNew(true);
    setEditingKey(null);
    setForm(toFormState("", DEFAULT_DEFINITION));
    setError(null);
  };

  const closeForm = (): void => {
    setEditingKey(null);
    setCreatingNew(false);
    setForm(null);
    setError(null);
  };

  const handleSave = async (): Promise<void> => {
    if (!form) return;
    setSaving(true);
    setError(null);
    const definition = fromFormState(form);
    try {
      if (creatingNew) {
        const created = await linkTypesApi.createGlobal(form.key, definition);
        setRows((prev) => [...prev, created]);
      } else if (scope === "global") {
        const updated = await linkTypesApi.updateGlobal(editingKey as string, definition);
        setRows((prev) => prev.map((row) => (row.key === editingKey ? updated : row)));
      } else if (workspaceId) {
        const updated = await linkTypesApi.updateForWorkspace(workspaceId, editingKey as string, definition);
        setRows((prev) => prev.map((row) => (row.key === editingKey ? updated : row)));
      }
      closeForm();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  const handleReset = async (key: string): Promise<void> => {
    if (!workspaceId) return;
    setError(null);
    try {
      const updated = await linkTypesApi.resetForWorkspace(workspaceId, key);
      setRows((prev) => prev.map((row) => (row.key === key ? updated : row)));
    } catch (err) {
      setError(errorMessage(err));
    }
  };

  return (
    <div style={pageStyle}>
      <PageHeader
        title={t("linkType.title")}
        primaryAction={
          scope === "global"
            ? { label: t("linkType.newType"), onClick: openNew, testId: "link-type-new-button" }
            : undefined
        }
      />

      {/* Honesty note next to the "new type" button: a genuinely novel,
          tenant-invented key passes catalog validation and can be edited and
          viewed, but a separate Layer-1 gate
          (`traceability/trace_link_manager.py::_validate_link_type`) still
          rejects it when a trace link is actually created. Defining a type is
          legitimate even when using it is not yet possible, so the button
          stays enabled — the limitation is stated instead of hidden. */}
      {scope === "global" && (
        <p style={hintStyle} data-testid="link-type-new-type-hint">
          {t("linkType.newTypeLimitationHint")}
        </p>
      )}

      <ul style={listStyle}>
        {rows.map((row) => {
          const locked = row.definition.system_owned;
          const isCustomized = isWorkspaceRow(row) && row.is_customized;
          return (
            <li key={row.key}>
              <div
                data-testid={`link-type-row-${row.key}`}
                style={locked ? rowLockedStyle : rowStyle}
                aria-disabled={locked ? "true" : undefined}
              >
                <span style={rowKeyStyle}>{row.key}</span>
                {locked ? (
                  <span data-testid={`link-type-lock-${row.key}`} style={lockIconStyle}>
                    <span aria-hidden="true">🔒</span> {t("linkType.locked")}
                  </span>
                ) : (
                  <div style={rowActionsStyle}>
                    {scope === "workspace" && isCustomized && (
                      <button
                        type="button"
                        className="btn-secondary"
                        data-testid={`link-type-reset-${row.key}`}
                        onClick={() => void handleReset(row.key)}
                      >
                        {t("linkType.reset")}
                      </button>
                    )}
                    <button
                      type="button"
                      className="btn-ghost"
                      data-testid={`link-type-edit-${row.key}`}
                      onClick={() => openEdit(row)}
                    >
                      {t("actions.edit")}
                    </button>
                  </div>
                )}
              </div>
              {editingKey === row.key && form && (
                <LinkTypeForm form={form} onChange={setForm} onSave={() => void handleSave()} onCancel={closeForm} saving={saving} />
              )}
            </li>
          );
        })}
      </ul>

      {creatingNew && form && (
        <LinkTypeForm form={form} onChange={setForm} onSave={() => void handleSave()} onCancel={closeForm} saving={saving} isNew />
      )}

      {error && (
        <p role="alert" data-testid="link-type-error" style={errorStyle}>
          {error}
        </p>
      )}
    </div>
  );
}

LinkTypeEditorPage.displayName = "LinkTypeEditorPage";
