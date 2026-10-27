/**
 * ARCH-L1-001 ReactFrontend — BaselinesView.
 *
 * leaf_id: COMP-RF-001 (NavigationShell — gated by preset)
 * req_id:  REQ-L1-018 (Baselines),
 *          REQ-L1-049 (Baseline scope-select with 3 scopes),
 *          REQ-L2-RF-007 (Preset-basierte Sichtbarkeit — Baselines gated),
 *          REQ-002 (Split-View Layout)
 *
 * Split-View layout with resizable divider:
 *   - Left panel: baseline list + create button
 *   - Divider: 4px resizable
 *   - Right panel: create form OR baseline detail (scope, artifact, created)
 *
 * Hidden in Minimal preset (gated upstream by NavigationShell).
 *
 * Interfaces consumed:
 *   IF-RF-EXT-OUT-001 → GET/POST/DELETE /api/v1/baselines/
 *   IF-RF-EXT-OUT-001 → GET /api/v1/artifacts/ (artifact picker for create form)
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  isSeAuditorBlocked,
  type BaselineDiff,
  type BaselineScope,
} from "../../api/baselines";
import { useAuth } from "../../context/AuthContext";
import { SplitView } from "../SplitView/SplitView";
import { PageHeader } from "../shared/PageHeader";
import { EmptyState } from "../shared/EmptyState/EmptyState";
import { ListToolbar } from "../shared/ListToolbar";
import { ConfirmDialog } from "../shared/ConfirmDialog";
import { Dialog } from "../shared/Dialog";
import type { Artifact } from "../../types";
import {
  BaselineComparePanel,
  BaselineEntriesSection,
} from "./BaselinesPanels";
import styles from "./BaselinesView.module.css";
import { useBaselinesData } from "./useBaselinesData";

// GH-513 / F5 (PR #554 review): mirrors the backend
// `MIN_OVERRIDE_REASON_LENGTH` in `backend/application/baseline_facade.py`
// so the two are not two independently-drifting magic numbers.
//
// GH-821 hardens the backend bar beyond length (>= 4 words, >= 3 distinct
// words, not a copy of the rule ids). The textarea can only mirror the length
// part; `baselines.overrideHint` states the content requirement, and the
// backend remains the authority (its 400 is rendered verbatim).
const MIN_OVERRIDE_REASON_LENGTH = 15;

// Issue #48: mirrors `BaselineSerializer.name` (max_length=500) so the field
// stops the user at the boundary instead of letting the request come back as
// a 400 they can only fix by guessing how much to delete.
const MAX_BASELINE_NAME_LENGTH = 500;

// Re-exported so existing imports (and unit tests) that pull DiffItemRow from
// this module keep working after the Container/Presenter split (REQ-050).
export { DiffItemRow } from "./BaselinesPanels";

/** Extract a `{ error: { message } }`-shaped API error message. */
function baselineErrorMessage(err: unknown): string {
  return (
    (err as { error?: { message?: string } })?.error?.message ?? String(err)
  );
}

// REQ-L1-049: only these three scopes are valid. The order is intentional
// (most common first) and matches the i18n key ordering in the locales.
const SCOPE_OPTIONS: { value: BaselineScope; labelKey: string }[] = [
  { value: "document", labelKey: "baselines.scopeDocument" },
  { value: "project", labelKey: "baselines.scopeProject" },
  { value: "global", labelKey: "baselines.scopeGlobal" },
];

function formatDate(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleString();
  } catch {
    return iso;
  }
}

export default function BaselinesView(): JSX.Element {
  const { t } = useTranslation();
  const { roles } = useAuth();
  // UI-21 / GH-513: the backend only accepts an override justification from
  // 'admin'/'approver' (AuthorizationService.WORKFLOW_APPROVAL, see
  // baseline_facade._assert_override_permission) — everyone else used to see
  // the full waiver panel anyway and only learned they lacked permission
  // after typing a reason and hitting a raw 403 on submit.
  const canOverrideAuditGate = roles.includes("admin") || roles.includes("approver");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  // #181: list-panel search (by name) + scope filter (ListToolbar).
  const [listSearch, setListSearch] = useState<string>("");
  const [scopeFilter, setScopeFilter] = useState<BaselineScope | "">("");
  const [showForm, setShowForm] = useState(false);
  // #1282: the create flow is a modal <Dialog> now — the name field is its
  // initial focus target (matching the other create dialogs).
  const createNameInputRef = useRef<HTMLInputElement | null>(null);
  // Issue #48: the create form had no name field at all, so every baseline
  // landed on the backend's `Baseline <ISO timestamp>` fallback and the list
  // became a wall of indistinguishable timestamps — with no way to say what a
  // baseline was actually taken for. Optional on purpose: leaving it blank
  // keeps the old generated-name behaviour rather than blocking the action.
  const [formName, setFormName] = useState<string>("");
  const [formArtifactId, setFormArtifactId] = useState<string>("");
  // REQ-L1-049: scope is now one of {document, project, global}; default
  // is "project" to match the backend model default.
  const [formScope, setFormScope] = useState<BaselineScope>("project");
  const [isSaving, setIsSaving] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  // GH-513: the SE-Auditor gate (GH-490) blocks creation while the workspace
  // has BLOCKER findings, and most findings have no in-UI fix (GH-451) — so a
  // blocked create must offer the documented waiver instead of a dead end.
  // The panel appears only after the backend actually answered
  // SE_AUDITOR_BLOCKED; an unevaluable auditor is not waivable and keeps the
  // plain error.
  const [gateBlocked, setGateBlocked] = useState(false);
  const [overrideReason, setOverrideReason] = useState("");
  // REQ-L2-BL-003: baseline compare (field-level diff). ``showCompare`` swaps
  // the right panel to the compare form + result. The diff state stays local
  // to the container since it is imperative (button-triggered, not a query).
  const [showCompare, setShowCompare] = useState(false);
  const [compareAId, setCompareAId] = useState<string>("");
  const [compareBId, setCompareBId] = useState<string>("");
  const [diff, setDiff] = useState<BaselineDiff | null>(null);
  const [diffLoading, setDiffLoading] = useState(false);
  const [diffError, setDiffError] = useState<string | null>(null);

  // All data-fetching (lists, scope preview, detail, create/delete/compare)
  // lives in useBaselinesData (TanStack Query — REQ-049/REQ-050).
  const {
    baselines,
    artifacts,
    isLoading,
    error,
    scopePreview,
    scopePreviewLoading,
    scopePreviewError,
    detail,
    detailLoading,
    detailError,
    refreshList,
    createBaseline,
    deleteBaseline,
    compareBaselines,
  } = useBaselinesData({ showForm, formScope, formArtifactId, selectedId });

  // The render still reads a `state`-shaped object (kept for parity with the
  // pre-decomposition markup).
  const state = { baselines, artifacts, isLoading, error };

  // When form opens, default to the first available artifact.
  useEffect(() => {
    if (showForm && !formArtifactId && artifacts.length > 0) {
      setFormArtifactId(artifacts[0].id);
    }
  }, [showForm, formArtifactId, artifacts]);

  const handleCreate = useCallback(
    async (withOverride = false): Promise<void> => {
      // REQ-L1-049: ``document`` scope requires an artifact.
      if (formScope === "document" && !formArtifactId) {
        setCreateError(t("baselines.artifactRequired"));
        return;
      }
      setIsSaving(true);
      setCreateError(null);
      try {
        const created = await createBaseline({
          scope: formScope,
          artifactId: formArtifactId,
          name: formName,
          ...(withOverride ? { overrideReason } : {}),
        });
        setShowForm(false);
        setFormName("");
        setFormArtifactId("");
        setFormScope("project");
        setGateBlocked(false);
        setOverrideReason("");
        setSelectedId(created.id);
      } catch (err: unknown) {
        setCreateError(baselineErrorMessage(err));
        // Sticky on purpose: a rejected override (403 / too short) must not
        // hide the panel the user is in the middle of using.
        if (isSeAuditorBlocked(err)) setGateBlocked(true);
      } finally {
        setIsSaving(false);
      }
    },
    [formArtifactId, formScope, formName, overrideReason, t, createBaseline],
  );

  // UI-20: unified on the shared ConfirmDialog instead of window.confirm —
  // consistent styling/i18n/focus-trap with the rest of the app.
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);

  const handleDelete = useCallback(
    async (id: string): Promise<void> => {
      try {
        await deleteBaseline(id);
        if (selectedId === id) setSelectedId(null);
      } catch {
        // Failure surfaces via the hook's `error` (delete mutation error).
      }
    },
    [deleteBaseline, selectedId]
  );

  const confirmDelete = useCallback((): void => {
    if (!pendingDeleteId) return;
    const id = pendingDeleteId;
    setPendingDeleteId(null);
    void handleDelete(id);
  }, [pendingDeleteId, handleDelete]);

  const handleCompare = useCallback(async (): Promise<void> => {
    if (!compareAId || !compareBId) {
      setDiffError(t("baselines.compareSelectBoth"));
      return;
    }
    if (compareAId === compareBId) {
      setDiffError(
        t("baselines.compareSameBaseline")
      );
      return;
    }
    setDiffLoading(true);
    setDiffError(null);
    try {
      const result = await compareBaselines(compareAId, compareBId);
      setDiff(result);
    } catch (err: unknown) {
      setDiffError(baselineErrorMessage(err));
      setDiff(null);
    } finally {
      setDiffLoading(false);
    }
  }, [compareAId, compareBId, t, compareBaselines]);

  const openCompare = useCallback((): void => {
    setShowForm(false);
    setShowCompare(true);
    setSelectedId(null);
    setDiff(null);
    setDiffError(null);
  }, []);

  const closeCompare = useCallback((): void => {
    setShowCompare(false);
    setDiff(null);
    setDiffError(null);
  }, []);

  // #1282: creation runs in the shared modal <Dialog>, like every other
  // entity route — open and close are now distinct actions, and closing
  // discards the draft (mirrors the old Cancel button verbatim).
  const openCreateForm = useCallback((): void => {
    setShowCompare(false);
    setSelectedId(null);
    setFormName("");
    setCreateError(null);
    setGateBlocked(false);
    setOverrideReason("");
    setShowForm(true);
  }, []);

  const closeCreateForm = useCallback((): void => {
    setShowForm(false);
    setCreateError(null);
    setGateBlocked(false);
    setOverrideReason("");
  }, []);

  // #181: search (by name) + scope filter. Computed unconditionally (rules
  // of hooks) — must run before the loading/error early returns below.
  const filteredBaselines = useMemo(() => {
    const q = listSearch.trim().toLowerCase();
    return state.baselines.filter((bl) => {
      if (scopeFilter && bl.scope !== scopeFilter) return false;
      if (q && !(bl.name || "").toLowerCase().includes(q)) return false;
      return true;
    });
  }, [state.baselines, listSearch, scopeFilter]);

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  if (state.isLoading) {
    return (
      <div data-testid="baselines-view">
        <p role="status" className={styles.loadingText}>
          {t("loading")}
        </p>
      </div>
    );
  }

  if (state.error) {
    return (
      <div data-testid="baselines-view" role="alert" className={styles.errorPanel}>
        <p className={styles.errorText}>{state.error}</p>
        <button onClick={() => void refreshList()} className={`btn-primary ${styles.reloadBtn}`}>
          {t("actions.reload")}
        </button>
      </div>
    );
  }

  const selectedBaseline =
    state.baselines.find((bl) => bl.id === selectedId) ?? null;

  const hasActiveListControls = Boolean(listSearch || scopeFilter);
  const resetListFilters = (): void => {
    setListSearch("");
    setScopeFilter("");
  };

  const overrideSubmitDisabled =
    isSaving || overrideReason.trim().length < MIN_OVERRIDE_REASON_LENGTH;

  // REQ-L1-049: ``document`` scope needs an artifact — the same boolean drives
  // the submit button's `disabled` attribute and its enabled/disabled class.
  const createSubmitDisabled =
    isSaving || (formScope === "document" && !formArtifactId);

  return (
    <div data-testid="baselines-view" className={styles.page}>
      {/* Baselines/TestRuns are not Spine artifacts (no derivation chain), but
          PageHeader still applies. Creating a baseline is the page's only
          create action, so it must be reachable without opening a menu
          (#1405 R1-04): it renders as a visible secondary header action —
          not the primary one, because taking a baseline is a less-frequent,
          more consequential action than creating an artifact (task 5.2
          brief). */}
      <PageHeader
        title={t("nav.baselines")}
        summary={t("baselines.summary", { count: state.baselines.length })}
        secondaryActions={[
          {
            label: showCompare
              ? t("actions.cancel")
              : t("baselines.compare", "Compare"),
            onClick: () => (showCompare ? closeCompare() : openCompare()),
            disabled: state.baselines.length < 2,
            testId: "compare-baseline-btn",
          },
          {
            label: t("baselines.create"),
            onClick: openCreateForm,
            testId: "create-baseline-btn",
          },
        ]}
      />

      <div className={styles.content}>
      <SplitView
        moduleType="baselines"
        leftMinWidth={280}
        leftPanel={
          <>
        <ListToolbar
          testIdPrefix="baseline-list"
          searchValue={listSearch}
          onSearchChange={setListSearch}
          searchPlaceholder={t("editor.searchPlaceholder", "Search...")}
          filters={[
            {
              id: "scope",
              allLabel: t("baselines.allScopes", "Alle Scopes"),
              value: scopeFilter,
              options: SCOPE_OPTIONS.map((opt) => ({ value: opt.value, label: t(opt.labelKey) })),
              onChange: (v) => setScopeFilter(v as BaselineScope | ""),
            },
          ]}
          countLabel={
            hasActiveListControls
              ? t("editor.filteredCount", { shown: filteredBaselines.length, total: state.baselines.length })
              : String(state.baselines.length)
          }
        />

        {state.baselines.length === 0 ? (
          <EmptyState
            variant="empty"
            testId="baselines-empty"
            title={t("baselines.emptyTitle", "No baselines yet")}
            description={t(
              "baselines.emptyDescription",
              "Baselines capture a point-in-time snapshot of your artifacts.",
            )}
            actions={[
              {
                label: t("baselines.create"),
                prefixWithPlus: true,
                onClick: () => setShowForm(true),
                testId: "baselines-empty-create",
              },
            ]}
          />
        ) : filteredBaselines.length === 0 ? (
          <EmptyState variant="no-match" testId="baselines-no-match" onResetFilters={resetListFilters} />
        ) : (
          <ul data-testid="baseline-list" className={styles.list}>
            {filteredBaselines.map((bl) => {
              const isSelected = bl.id === selectedId && !showForm;
              return (
                <li
                  key={bl.id}
                  data-testid="baseline-item"
                  role="button"
                  tabIndex={0}
                  aria-pressed={isSelected}
                  onClick={() => {
                    setShowForm(false);
                    setSelectedId(bl.id);
                  }}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      setShowForm(false);
                      setSelectedId(bl.id);
                    }
                  }}
                  className={`${styles.listItem} ${isSelected ? styles.listItemSelected : ""}`}
                >
                  <strong className={styles.listItemName}>
                    {bl.name || `${bl.id.slice(0, 8)}…`}
                  </strong>
                  <span className={styles.listItemMeta}>
                    {bl.scope} | {formatDate(bl.created_at)}
                  </span>
                </li>
              );
            })}
          </ul>
        )}
          </>
        }
        rightPanel={
          showCompare ? (
            <BaselineComparePanel
              baselines={state.baselines}
              aId={compareAId}
              bId={compareBId}
              onChangeA={setCompareAId}
              onChangeB={setCompareBId}
              onCompare={() => void handleCompare()}
              diff={diff}
              loading={diffLoading}
              error={diffError}
            />
          ) : selectedBaseline ? (
          <div data-testid="baseline-detail" className={styles.detailPanel}>
            <h2 className={styles.detailTitle} title={selectedBaseline.id}>
              {selectedBaseline.name || `${selectedBaseline.id.slice(0, 8)}…`}
            </h2>

            <dl className={styles.detailGrid}>
              <dt className={styles.detailTerm}>{t("baselines.id")}</dt>
              <dd className={styles.detailValue}>
                <code className={styles.mono}>{selectedBaseline.id}</code>
              </dd>

              <dt className={styles.detailTerm}>{t("baselines.scope")}</dt>
              <dd className={styles.detailValue}>{selectedBaseline.scope}</dd>

              <dt className={styles.detailTerm}>{t("baselines.artifact")}</dt>
              <dd className={styles.detailValue}>
                {selectedBaseline.artifact_id ? (
                  <code className={styles.mono}>{selectedBaseline.artifact_id}</code>
                ) : (
                  "—"
                )}
              </dd>

              <dt className={styles.detailTerm}>{t("baselines.created")}</dt>
              <dd className={styles.detailValue}>
                {formatDate(selectedBaseline.created_at)}
              </dd>
            </dl>

            {/* REQ-L2-BL-012: captured items with their full-state snapshot. */}
            <BaselineEntriesSection
              entries={detail?.entries ?? null}
              loading={detailLoading}
              error={detailError}
            />

            <button
              type="button"
              data-testid="baseline-delete-btn"
              onClick={() => setPendingDeleteId(selectedBaseline.id)}
              className={styles.deleteBtn}
            >
              {t("actions.delete")}
            </button>
          </div>
        ) : (
          <p className={styles.selectPrompt}>
            {t("baselines.selectBaseline")}
          </p>
          )
        }
      />
      </div>

      {/* #1282: baseline creation runs in the shared modal <Dialog> (role=dialog,
          focus trap, Escape, focus return) like every other entity route —
          previously it rendered an inline panel in the right-hand SplitView
          pane, the one create flow in the app that was not a modal. */}
      {showForm && (
        <Dialog
          title={t("baselines.create")}
          onClose={closeCreateForm}
          testId="baseline-create-dialog"
          initialFocusRef={createNameInputRef}
        >
          <div data-testid="create-baseline-form" className={styles.createPanel}>
            {/* Issue #48: name the baseline. Optional — an empty value keeps
                the backend's generated `Baseline <timestamp>` name. */}
            <label htmlFor="baseline-name" className={styles.formLabel}>
              {t("baselines.name", "Name")}
            </label>
            <input
              id="baseline-name"
              ref={createNameInputRef}
              data-testid="baseline-name-input"
              type="text"
              value={formName}
              maxLength={MAX_BASELINE_NAME_LENGTH}
              onChange={(e) => {
                setFormName(e.target.value);
                setCreateError(null);
              }}
              placeholder={t(
                "baselines.namePlaceholder",
                "z. B. Release 1.2 Freigabe",
              )}
              aria-describedby="baseline-name-hint"
              className={styles.formInput}
            />
            <p id="baseline-name-hint" className={styles.formHint}>
              {t(
                "baselines.nameHint",
                "Optional. Ohne Angabe wird ein Name aus dem Zeitstempel erzeugt. Der Name muss im Workspace eindeutig sein.",
              )}
            </p>

            <label htmlFor="baseline-scope" className={styles.formLabel}>
              {t("baselines.scope")}
            </label>
            {/* REQ-L1-049: radio group with the three valid scopes. */}
            <div data-testid="baseline-scope-group" className={styles.scopeGroup}>
              {SCOPE_OPTIONS.map((opt) => (
                <label
                  key={opt.value}
                  htmlFor={`baseline-scope-${opt.value}`}
                  className={styles.scopeOption}
                >
                  <input
                    id={`baseline-scope-${opt.value}`}
                    data-testid={`baseline-scope-${opt.value}`}
                    type="radio"
                    name="baseline-scope"
                    value={opt.value}
                    checked={formScope === opt.value}
                    onChange={() => setFormScope(opt.value)}
                  />
                  <span>{t(opt.labelKey)}</span>
                </label>
              ))}
            </div>

            {/* REQ-L1-049: live count of items that would be included for
                the chosen scope. Re-fetches on scope/artifact change. */}
            <p
              data-testid="baseline-scope-count"
              aria-live="polite"
              className={`${styles.scopeCount} ${scopePreviewError ? styles.scopeCountError : ""}`}
            >
              {scopePreviewError
                ? scopePreviewError
                : scopePreviewLoading
                  ? t("baselines.scopeCountLoading")
                  : scopePreview
                    ? t("baselines.scopeCountReady", {
                        count: scopePreview.count,
                      })
                    : formScope === "document" && !formArtifactId
                      ? t("baselines.scopeCountNeedsArtifact")
                      : t("baselines.scopeCountIdle")}
            </p>

            {/* REQ-L1-049: artifact picker is shown only for document scope. */}
            {formScope === "document" && (
              <>
                <label htmlFor="baseline-artifact" className={styles.formLabel}>
                  {t("baselines.artifact")}
                </label>
                <select
                  id="baseline-artifact"
                  data-testid="baseline-artifact-select"
                  value={formArtifactId}
                  onChange={(e) => setFormArtifactId(e.target.value)}
                  disabled={state.artifacts.length === 0}
                  className={styles.artifactSelect}
                >
                  {state.artifacts.length === 0 ? (
                    <option value="">{t("baselines.noArtifacts")}</option>
                  ) : (
                    state.artifacts.map((a) => {
                      // The /artifacts/ payload currently exposes only the ID
                      // (no title/name field). Read them defensively so the
                      // label upgrades automatically once the backend adds them.
                      const named = a as Artifact & { title?: string; name?: string };
                      const label = named.title ?? named.name ?? `${a.id.slice(0, 8)}…`;
                      return (
                        <option key={a.id} value={a.id}>
                          {a.artifact_type} — {label}
                        </option>
                      );
                    })
                  )}
                </select>
              </>
            )}

            {createError && (
              <p role="alert" className={styles.formError}>
                {createError}
              </p>
            )}

            {/* GH-513: waiver panel — shown only after the backend answered
                SE_AUDITOR_BLOCKED. The button stays disabled until the
                justification is long enough for the backend to accept it, so
                the user is not sent into a second round-trip to learn that.
                UI-21: the backend only accepts the waiver from 'admin'/
                'approver' — a caller without that role gets a plain hint
                instead of a fillable form that only fails after submit. */}
            {gateBlocked && !canOverrideAuditGate && (
              <p
                role="alert"
                data-testid="baseline-override-no-permission"
                className={styles.overrideHint}
              >
                {t("baselines.overrideNoPermission")}
              </p>
            )}
            {gateBlocked && canOverrideAuditGate && (
              <div
                data-testid="baseline-override-panel"
                className={styles.overridePanel}
              >
                <label
                  htmlFor="baseline-override-reason"
                  className={styles.overrideLabel}
                >
                  {t("baselines.overrideLabel")}
                </label>
                <p className={styles.overrideHint}>
                  {t("baselines.overrideHint")}
                </p>
                <textarea
                  id="baseline-override-reason"
                  data-testid="baseline-override-reason"
                  value={overrideReason}
                  onChange={(e) => setOverrideReason(e.target.value)}
                  rows={3}
                  className={styles.overrideReasonInput}
                />
                <button
                  type="button"
                  data-testid="baseline-override-submit-btn"
                  onClick={() => void handleCreate(true)}
                  disabled={overrideSubmitDisabled}
                  className="btn-danger"
                >
                  {t("baselines.overrideSubmit")}
                </button>
              </div>
            )}

            <div className={styles.formActions}>
              <button
                type="button"
                data-testid="baseline-submit-btn"
                onClick={() => void handleCreate()}
                disabled={createSubmitDisabled}
                className="btn-primary"
              >
                {isSaving ? t("actions.saving") : t("actions.save")}
              </button>
              <button
                type="button"
                data-testid="baseline-create-cancel-btn"
                onClick={closeCreateForm}
                className="btn-secondary"
              >
                {t("actions.cancel")}
              </button>
            </div>
          </div>
        </Dialog>
      )}

      {pendingDeleteId && (
        <ConfirmDialog
          title={t("baselines.deleteConfirmTitle", "Delete baseline?")}
          message={t("baselines.deleteConfirm", "Really delete this baseline?")}
          confirmLabel={t("actions.delete")}
          onConfirm={confirmDelete}
          onCancel={() => setPendingDeleteId(null)}
          testId="baseline-delete-confirm"
        />
      )}
    </div>
  );
}
