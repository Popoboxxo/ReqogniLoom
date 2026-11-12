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
  type BaselineScope,
} from "../../api/baselines";
import { useAuth } from "../../context/AuthContext";
import { useWorkspace } from "../../context/WorkspaceContext";
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
import { BaselineTagsEditor } from "./BaselineTagsEditor";
import { BaselineRollbackPanel } from "./BaselineRollbackPanel";
import { MilestoneList } from "./MilestoneList";
import { TagInput } from "../shared/tag-input";
import styles from "./BaselinesView.module.css";
import { useBaselinesData } from "./useBaselinesData";
import { useBaselineCompare } from "./use-baseline-compare";
import { useBaselineCreateForm } from "./use-baseline-create";

// GH-513 / F5 (PR #554 review): mirrors the backend
// `MIN_OVERRIDE_REASON_LENGTH` in `backend/application/baseline_facade.py`
// so the two are not two independently-drifting magic numbers.
//
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
  // F6 (ui-review): the tag editor's `disabled` prop was dead code — no caller
  // passed it, so a viewer could type chips and only learned about the missing
  // write authority from a raw 403. `editor` is the role the backend requires
  // for `PUT /baselines/{id}/tags/`; `admin` is a superset (same rule as
  // `hooks/useHasRole`).
  const canEdit =
    roles.includes("admin") || roles.includes("editor");
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
  // F4.3: server-side tag filter (`GET /api/v1/baselines/?tag=…`).
  const [tagFilter, setTagFilter] = useState<string>("");
  // #1282: the create flow is a modal <Dialog> now — the name field is its
  // initial focus target (matching the other create dialogs).
  const createNameInputRef = useRef<HTMLInputElement | null>(null);
  // REQ-L2-BL-003: baseline compare (field-level diff). ``showCompare`` swaps
  // the right panel to the compare form + result. The diff state stays local
  // to the container since it is imperative (button-triggered, not a query).
  const {
    showCompare,
    compareAId,
    compareBId,
    diff,
    diffLoading,
    diffError,
    setCompareAId,
    setCompareBId,
    openCompare,
    closeCompare,
    handleCompare,
  } = useBaselineCompare(t);

  const {
    showForm,
    formName,
    formTags,
    formArtifactId,
    formScope,
    isSaving,
    createError,
    gateBlocked,
    overrideReason,
    createSubmitDisabled,
    overrideSubmitDisabled,
    setShowForm,
    setFormName,
    setFormArtifactId,
    setFormScope,
    setIsSaving,
    setCreateError,
    setGateBlocked,
    setOverrideReason,
    handleFormTagsChange,
    openCreateForm,
    closeCreateForm,
    resetAfterCreate,
  } = useBaselineCreateForm({
    t,
    onBeforeOpen: () => {
      closeCompare();
      setSelectedId(null);
    },
  });

  // All data-fetching (lists, scope preview, detail, create/delete/compare)
  // lives in useBaselinesData (TanStack Query — REQ-049/REQ-050).
  const {
    baselines,
    allTags,
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
    setTags,
  } = useBaselinesData({ showForm, formScope, formArtifactId, selectedId, tagFilter });



  // The render still reads a `state`-shaped object (kept for parity with the
  // pre-decomposition markup).
  const state = { baselines, artifacts, isLoading, error };

  // F7 (ui-review): the tag filter is workspace-scoped state, so a workspace
  // switch must not carry the previous workspace's label into the list call.
  const activeWorkspaceId = useWorkspace().activeWorkspace?.id;
  useEffect(() => {
    setTagFilter("");
  }, [activeWorkspaceId]);

  // F7 (ui-review): a filter whose label is no longer offered by `allTags`
  // (renamed/removed on every baseline, or left over from a switch) has no
  // matching <option> while the query keeps filtering — an unexplained empty
  // list. Falling back to "all tags" makes the empty state explicable and
  // re-runs the list query without the filter.
  useEffect(() => {
    if (!tagFilter) return;
    const available = allTags.some(
      (tag) => tag.toLowerCase() === tagFilter.toLowerCase(),
    );
    if (!available) setTagFilter("");
  }, [tagFilter, allTags]);

  // When the form opens, default to the first available artifact.
  useEffect(() => {
    if (showForm && !formArtifactId && artifacts.length > 0) {
      setFormArtifactId(artifacts[0].id);
    }
  }, [showForm, formArtifactId, artifacts]);

  const handleCreate = useCallback(
    async (withOverride = false): Promise<void> => {
      // REQ-L1-049: document scope requires an artifact.
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
          tags: formTags,
          ...(withOverride ? { overrideReason } : {}),
        });
        resetAfterCreate();
        setSelectedId(created.id);
      } catch (err: unknown) {
        setCreateError(baselineErrorMessage(err));
        // Sticky on purpose: a rejected override must not hide the panel the
        // user is in the middle of using.
        if (isSeAuditorBlocked(err)) setGateBlocked(true);
      } finally {
        setIsSaving(false);
      }
    },
    [
      formArtifactId,
      formScope,
      formName,
      formTags,
      overrideReason,
      t,
      createBaseline,
      resetAfterCreate,
      setCreateError,
      setIsSaving,
      setGateBlocked,
    ]
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

  // Leaving the create form and clearing the selection is page navigation,
  // not compare state — it stays here and wraps the hook's opener.
  const openCompareView = useCallback((): void => {
    setShowForm(false);
    setSelectedId(null);
    openCompare();
  }, [openCompare]);

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

  const hasActiveListControls = Boolean(listSearch || scopeFilter || tagFilter);
  const resetListFilters = (): void => {
    setListSearch("");
    setScopeFilter("");
    setTagFilter("");
  };

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
            onClick: () => (showCompare ? closeCompare() : openCompareView()),
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
        {/* F4.3: tag filter. Server-side (`?tag=…`) — the options come from
            the unfiltered list so picking one does not collapse the menu. */}
        <div className={styles.tagFilterRow}>
          <label htmlFor="baseline-tag-filter" className={styles.tagFilterLabel}>
            {t("baselines.tagFilter")}
          </label>
          <select
            id="baseline-tag-filter"
            data-testid="baseline-tag-filter"
            value={tagFilter}
            onChange={(e) => setTagFilter(e.target.value)}
            className={styles.tagFilterSelect}
          >
            <option value="">{t("baselines.tagFilterAll")}</option>
            {allTags.map((tag) => (
              <option key={tag} value={tag}>
                {tag}
              </option>
            ))}
          </select>
        </div>
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

            {/* F4.3: tag chips + add/remove + save (`PUT /baselines/{id}/tags/`). */}
            <BaselineTagsEditor
              key={selectedBaseline.id}
              tags={selectedBaseline.tags ?? []}
              onSave={(tags) => setTags(selectedBaseline.id, tags)}
              disabled={!canEdit}
            />

            {/* REQ-L2-BL-012: captured items with their full-state snapshot. */}
            <BaselineEntriesSection
              entries={detail?.entries ?? null}
              loading={detailLoading}
              error={detailError}
            />

            {/* F4.5: rollback flow — preview → CCB change request → apply
                (ADR-025). Additive mount; the panel owns its own state, so a
                baseline switch remounts it via `key`. */}
            <BaselineRollbackPanel
              key={selectedBaseline.id}
              baselineId={selectedBaseline.id}
              canEdit={canEdit}
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

      {/* Plan B B6-T2 (#879): planned review milestones live under the
          Baselines route. Prop-driven (workspace + write authority), so the
          container stays the single owner of both values. */}
      {activeWorkspaceId && (
        <MilestoneList
          workspaceId={activeWorkspaceId}
          canEdit={canEdit}
        />
      )}

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

            {/* F4.3: optional tags. Enter (or comma) commits a chip; an empty
                list simply sends no `tags` field. */}
            <label htmlFor="baseline-create-tags" className={styles.formLabel}>
              {t("baselines.tags")}
            </label>
            <TagInput
              data-testid="baseline-create-tags"
              inputId="baseline-create-tags"
              tags={formTags}
              onChange={handleFormTagsChange}
              placeholder={t("baselines.tagPlaceholder")}
            />

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
