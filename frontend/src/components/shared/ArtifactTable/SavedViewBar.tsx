/**
 * Task 4.6 — saved-view bar (plan 2026-11-04-tabellenansicht-s4).
 *
 * Lists private + workspace views for the current `(workspace, itemType)`,
 * applies one through the server (`apply` is the authoritative filter check),
 * saves the current state as a new view, and updates/deletes only what the
 * caller owns (or an admin). A view that has gone stale (an attribute was
 * removed) still applies: the bar shows the server's `warnings` instead of
 * pretending nothing happened. A missing slice-3 route degrades to "no views".
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import {
  savedViewsApi,
  type SavedView,
  type SavedViewVisibility,
  type TableViewState,
} from "../../../api/table-views";
import { extractApiErrorMessage } from "../../../api/client";
import { useAuth } from "../../../context/AuthContext";
import { Dialog } from "../Dialog";
import { ConfirmDialog } from "../ConfirmDialog";
import styles from "./ArtifactTable.module.css";

export interface SavedViewBarProps {
  workspaceId: string;
  itemType: string;
  current: TableViewState;
  onApply(view: SavedView): void;
}

function isMissingRoute(error: unknown): boolean {
  return (error as { error?: { code?: string } } | null)?.error?.code === "NOT_FOUND";
}

export function SavedViewBar({
  workspaceId,
  itemType,
  current,
  onApply,
}: SavedViewBarProps): JSX.Element {
  const { t } = useTranslation();
  const auth = useAuth();
  const currentUserId = auth.user?.id ?? null;
  const isAdmin = auth.isTenantAdmin;

  const [views, setViews] = useState<SavedView[]>([]);
  const [selectedId, setSelectedId] = useState<string>("");
  const [warnings, setWarnings] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [name, setName] = useState("");
  const [visibility, setVisibility] = useState<SavedViewVisibility>("private");
  const [dialogError, setDialogError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<SavedView | null>(null);

  const nameInputRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async (): Promise<void> => {
    try {
      setViews(await savedViewsApi.list(workspaceId, itemType));
      setError(null);
    } catch (exc) {
      setViews([]);
      if (!isMissingRoute(exc)) setError(extractApiErrorMessage(exc));
    }
  }, [workspaceId, itemType]);

  useEffect(() => {
    setSelectedId("");
    setWarnings([]);
    void load();
  }, [load]);

  const selected = views.find((view) => view.id === selectedId) ?? null;
  const canModify = selected
    ? selected.owner_id === currentUserId || isAdmin
    : false;

  async function applyView(view: SavedView): Promise<void> {
    setError(null);
    try {
      const result = await savedViewsApi.apply(view.id, {
        workspace_id: workspaceId,
        page_size: 100,
      });
      setWarnings(result.warnings ?? []);
      onApply(view);
    } catch (exc) {
      setError(extractApiErrorMessage(exc));
    }
  }

  async function saveView(): Promise<void> {
    const trimmed = name.trim();
    if (!trimmed) return;
    setSaving(true);
    setDialogError(null);
    try {
      const created = await savedViewsApi.create(workspaceId, itemType, {
        name: trimmed,
        visibility,
        columns: current.columns,
        filters: current.filters,
        sort: current.sort,
      });
      setViews((list) => [...list, created]);
      setSelectedId(created.id);
      setDialogOpen(false);
      setName("");
    } catch (exc) {
      setDialogError(extractApiErrorMessage(exc));
    } finally {
      setSaving(false);
    }
  }

  async function updateSelected(): Promise<void> {
    if (!selected) return;
    try {
      const updated = await savedViewsApi.update(selected.id, {
        name: selected.name,
        visibility: selected.visibility,
        columns: current.columns,
        filters: current.filters,
        sort: current.sort,
        expected_version: selected.version,
      });
      setViews((list) => list.map((view) => (view.id === updated.id ? updated : view)));
      setError(null);
    } catch (exc) {
      setError(extractApiErrorMessage(exc));
    }
  }

  async function deleteSelected(): Promise<void> {
    if (!pendingDelete) return;
    try {
      await savedViewsApi.remove(pendingDelete.id);
      setViews((list) => list.filter((view) => view.id !== pendingDelete.id));
      if (selectedId === pendingDelete.id) setSelectedId("");
      setPendingDelete(null);
    } catch (exc) {
      setError(extractApiErrorMessage(exc));
      setPendingDelete(null);
    }
  }

  return (
    <div className={styles.savedViewBar} data-testid="saved-view-bar">
      <label className={styles.inlineLabel}>
        {t("table.savedViews")}
        <select
          className={styles.select}
          data-testid="saved-view-select"
          value={selectedId}
          onChange={(event) => {
            const id = event.target.value;
            setSelectedId(id);
            const view = views.find((entry) => entry.id === id);
            if (view) void applyView(view);
          }}
        >
          <option value="">{t("table.savedViewNone")}</option>
          {views.map((view) => (
            <option key={view.id} value={view.id}>
              {view.name}
              {view.visibility === "workspace" ? ` · ${t("table.visibilityWorkspace")}` : ""}
            </option>
          ))}
        </select>
      </label>

      <button
        type="button"
        className={`btn btn-secondary ${styles.secondaryButton}`}
        data-testid="saved-view-save"
        onClick={() => {
          setDialogError(null);
          setDialogOpen(true);
        }}
      >
        {t("table.saveView")}
      </button>

      {selected && canModify && (
        <>
          <button
            type="button"
            className={`btn btn-secondary ${styles.secondaryButton}`}
            data-testid="saved-view-update"
            onClick={() => void updateSelected()}
          >
            {t("table.updateView")}
          </button>
          <button
            type="button"
            className={`btn btn-danger ${styles.dangerButton}`}
            data-testid="saved-view-delete"
            onClick={() => setPendingDelete(selected)}
          >
            {t("table.deleteView")}
          </button>
        </>
      )}

      {views.length === 0 && (
        <span className={styles.hint} data-testid="saved-view-empty">
          {t("table.savedViewEmpty")}
        </span>
      )}

      {warnings.length > 0 && (
        <p className={styles.warning} role="status" data-testid="saved-view-warnings">
          {t("table.savedViewStale", { fields: warnings.join(", ") })}
        </p>
      )}

      {error && (
        <p className={styles.warning} role="alert" data-testid="saved-view-error">
          {error}
        </p>
      )}

      {dialogOpen && (
        <Dialog
          title={t("table.saveView")}
          onClose={() => setDialogOpen(false)}
          initialFocusRef={nameInputRef}
          size="sm"
          testId="saved-view-dialog"
        >
          <label className={styles.filterLabel}>
            {t("table.savedViewName")}
            <input
              ref={nameInputRef}
              className={styles.input}
              data-testid="saved-view-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
          </label>
          <label className={styles.filterLabel}>
            {t("table.savedViewVisibility")}
            <select
              className={styles.select}
              data-testid="saved-view-visibility"
              value={visibility}
              onChange={(event) =>
                setVisibility(event.target.value as SavedViewVisibility)
              }
            >
              <option value="private">{t("table.visibilityPrivate")}</option>
              <option value="workspace">{t("table.visibilityWorkspace")}</option>
            </select>
          </label>
          {dialogError && (
            <p className={styles.warning} role="alert" data-testid="saved-view-dialog-error">
              {dialogError}
            </p>
          )}
          <div className={styles.dialogActions}>
            <button
              type="button"
              className={`btn btn-secondary ${styles.secondaryButton}`}
              data-testid="saved-view-cancel"
              onClick={() => setDialogOpen(false)}
            >
              {t("table.cancel")}
            </button>
            <button
              type="button"
              className={`btn btn-primary ${styles.primaryButton}`}
              data-testid="saved-view-submit"
              disabled={saving || name.trim() === ""}
              onClick={() => void saveView()}
            >
              {t("table.save")}
            </button>
          </div>
        </Dialog>
      )}

      {pendingDelete && (
        <ConfirmDialog
          title={t("table.deleteView")}
          message={t("table.deleteViewConfirm", { name: pendingDelete.name })}
          confirmLabel={t("table.delete")}
          cancelLabel={t("table.cancel")}
          onConfirm={() => void deleteSelected()}
          onCancel={() => setPendingDelete(null)}
          testId="saved-view-delete-confirm"
        />
      )}
    </div>
  );
}
