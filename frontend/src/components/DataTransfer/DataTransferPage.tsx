/**
 * ARCH-L1-001 ReactFrontend — Datenübernahme (P8).
 *
 * leaf_id: COMP-RF-001 (NavigationShell scope — data-transfer UI)
 * req_id:  REQ-L0-013 (Übernahme bestehender Daten),
 *          D14b/D14c (ZIP-Snapshot / async Export),
 *          D17 (geprüfter Ziel-Instanz-Restore),
 *          D18 (neue UI-Seite „Datenübernahme" mit Vorschau)
 *
 * Three panels:
 *   1. Snapshot export — fetch a versioned full snapshot, show counts, download.
 *   2. Snapshot import — file + dry-run preview into an existing or new workspace.
 *   3. Checked restore — admin-only, captcha-gated, dry-run plan preview (D17).
 *
 * Every interactive element carries a `data-testid` (E2E requirement).
 */
import { useCallback, useState, type ChangeEvent } from "react";
import { useTranslation } from "react-i18next";
import { useWorkspace } from "../../context/WorkspaceContext";
import { PageHeader } from "../shared/PageHeader";
import {
  dataTransferApi,
  type RestoreResult,
  type SnapshotDocument,
  type SnapshotImportResult,
} from "../../api/dataTransfer";
import styles from "./DataTransferPage.module.css";

function entityCount(snapshot: SnapshotDocument | null): number {
  if (!snapshot?.entities) return 0;
  return Object.values(snapshot.entities).reduce(
    (sum, list) => sum + (Array.isArray(list) ? list.length : 0),
    0
  );
}

function relationCount(snapshot: SnapshotDocument | null): number {
  if (!snapshot?.relations) return 0;
  return Object.values(snapshot.relations).reduce(
    (sum, list) => sum + (Array.isArray(list) ? list.length : 0),
    0
  );
}

export default function DataTransferPage(): JSX.Element {
  const { t } = useTranslation();
  const { activeWorkspace } = useWorkspace();
  const workspaceId = activeWorkspace?.id ?? "";

  const [snapshot, setSnapshot] = useState<SnapshotDocument | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Import state
  const [importFile, setImportFile] = useState<File | null>(null);
  const [dryRun, setDryRun] = useState(true);
  const [newWorkspaceName, setNewWorkspaceName] = useState("");
  const [targetWorkspaceId, setTargetWorkspaceId] = useState("");
  const [importResult, setImportResult] = useState<SnapshotImportResult | null>(null);

  // Restore state
  const [backupId, setBackupId] = useState("");
  const [restoreDryRun, setRestoreDryRun] = useState(true);
  const [restoreTargetTenant, setRestoreTargetTenant] = useState("");
  const [restoreTargetWorkspace, setRestoreTargetWorkspace] = useState("");
  const [restoreConfirm, setRestoreConfirm] = useState("");
  const [restoreResult, setRestoreResult] = useState<RestoreResult | null>(null);

  const run = useCallback(
    async (action: () => Promise<void>) => {
      setBusy(true);
      setError(null);
      try {
        await action();
      } catch (exc) {
        setError(exc instanceof Error ? exc.message : String(exc));
      } finally {
        setBusy(false);
      }
    },
    []
  );

  const onExport = () =>
    run(async () => {
      const doc = await dataTransferApi.exportSnapshot(workspaceId);
      setSnapshot(doc);
      setImportResult(null);
    });

  const onDownload = () => {
    if (!snapshot) return;
    const name = `${activeWorkspace?.name ?? "workspace"}-snapshot.json`;
    dataTransferApi.downloadSnapshot(snapshot, name);
  };

  const onFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0] ?? null;
    setImportFile(file);
    setImportResult(null);
  };

  const onImport = () =>
    run(async () => {
      if (!importFile) throw new Error(t("dataTransfer.import.noFile"));
      const text = await importFile.text();
      const doc = JSON.parse(text) as SnapshotDocument;
      const result = await dataTransferApi.importSnapshot(workspaceId, doc, {
        dryRun,
        newWorkspaceName: newWorkspaceName.trim() || undefined,
        targetWorkspaceId: targetWorkspaceId.trim() || undefined,
      });
      setImportResult(result);
    });

  const onRestore = () =>
    run(async () => {
      if (!backupId.trim()) throw new Error(t("dataTransfer.restore.noBackup"));
      const result = await dataTransferApi.restoreBackup(
        {
          backupId: backupId.trim(),
          dryRun: restoreDryRun,
          targetTenant: restoreTargetTenant.trim() || undefined,
          targetWorkspace: restoreTargetWorkspace.trim() || undefined,
        },
        restoreConfirm
      );
      setRestoreResult(result);
    });

  return (
    <main className={styles.page} data-testid="data-transfer-page">
      <PageHeader
        title={t("dataTransfer.title")}
        summary={t("dataTransfer.summary")}
        testId="data-transfer-header"
      />

      {error !== null && (
        <div role="alert" className={styles.error} data-testid="data-transfer-error">
          {error}
        </div>
      )}

      {/* 1 — Snapshot export */}
      <section className={styles.panel} aria-labelledby="dt-export-heading">
        <h2 id="dt-export-heading">{t("dataTransfer.export.title")}</h2>
        <p>{t("dataTransfer.export.description")}</p>
        <button
          type="button"
          className="btn-primary"
          onClick={onExport}
          disabled={busy || !workspaceId}
          data-testid="snapshot-export-button"
        >
          {t("dataTransfer.export.action")}
        </button>
        {snapshot !== null && (
          <div className={styles.result} data-testid="snapshot-export-result">
            <span data-testid="snapshot-export-entities">
              {t("dataTransfer.export.entities", { count: entityCount(snapshot) })}
            </span>
            <span data-testid="snapshot-export-relations">
              {t("dataTransfer.export.relations", { count: relationCount(snapshot) })}
            </span>
            <button
              type="button"
              className="btn-secondary"
              onClick={onDownload}
              data-testid="snapshot-download-button"
            >
              {t("dataTransfer.export.download")}
            </button>
          </div>
        )}
      </section>

      {/* 2 — Snapshot import / copy */}
      <section className={styles.panel} aria-labelledby="dt-import-heading">
        <h2 id="dt-import-heading">{t("dataTransfer.import.title")}</h2>
        <p>{t("dataTransfer.import.description")}</p>
        <input
          type="file"
          accept="application/json,.json"
          onChange={onFileChange}
          data-testid="snapshot-import-file"
          aria-label={t("dataTransfer.import.fileLabel")}
        />
        <label className={styles.checkbox}>
          <input
            type="checkbox"
            checked={dryRun}
            onChange={(e) => setDryRun(e.target.checked)}
            data-testid="snapshot-import-dry-run"
          />
          {t("dataTransfer.import.dryRun")}
        </label>
        <label className={styles.field}>
          {t("dataTransfer.import.newWorkspace")}
          <input
            type="text"
            value={newWorkspaceName}
            onChange={(e) => setNewWorkspaceName(e.target.value)}
            data-testid="snapshot-import-new-workspace"
          />
        </label>
        <label className={styles.field}>
          {t("dataTransfer.import.targetWorkspace")}
          <input
            type="text"
            value={targetWorkspaceId}
            onChange={(e) => setTargetWorkspaceId(e.target.value)}
            data-testid="snapshot-import-target-workspace"
            placeholder="UUID"
          />
        </label>
        <button
          type="button"
          className="btn-primary"
          onClick={onImport}
          disabled={busy || importFile === null || !workspaceId}
          data-testid="snapshot-import-button"
        >
          {dryRun
            ? t("dataTransfer.import.preview")
            : t("dataTransfer.import.action")}
        </button>
        {importResult !== null && (
          <div className={styles.result} data-testid="snapshot-import-result">
            <span data-testid="snapshot-import-created">
              {t("dataTransfer.import.created", { count: importResult.created })}
            </span>
            <span data-testid="snapshot-import-updated">
              {t("dataTransfer.import.updated", { count: importResult.updated })}
            </span>
            <span data-testid="snapshot-import-skipped">
              {t("dataTransfer.import.skipped", { count: importResult.skipped })}
            </span>
            <span data-testid="snapshot-import-reconciled">
              {t("dataTransfer.import.reconciled", { count: importResult.reconciled })}
            </span>
            {importResult.warnings.map((warning, index) => (
              <p key={index} className={styles.warning}>{warning}</p>
            ))}
          </div>
        )}
      </section>

      {/* 3 — Checked restore */}
      <section className={styles.panel} aria-labelledby="dt-restore-heading">
        <h2 id="dt-restore-heading">{t("dataTransfer.restore.title")}</h2>
        <p>{t("dataTransfer.restore.description")}</p>
        <label className={styles.field}>
          {t("dataTransfer.restore.backupId")}
          <input
            type="text"
            value={backupId}
            onChange={(e) => setBackupId(e.target.value)}
            data-testid="restore-backup-id"
            placeholder="UUID"
          />
        </label>
        <label className={styles.checkbox}>
          <input
            type="checkbox"
            checked={restoreDryRun}
            onChange={(e) => setRestoreDryRun(e.target.checked)}
            data-testid="restore-dry-run"
          />
          {t("dataTransfer.restore.dryRun")}
        </label>
        <label className={styles.field}>
          {t("dataTransfer.restore.targetTenant")}
          <input
            type="text"
            value={restoreTargetTenant}
            onChange={(e) => setRestoreTargetTenant(e.target.value)}
            data-testid="restore-target-tenant"
            placeholder="UUID (optional)"
          />
        </label>
        <label className={styles.field}>
          {t("dataTransfer.restore.targetWorkspace")}
          <input
            type="text"
            value={restoreTargetWorkspace}
            onChange={(e) => setRestoreTargetWorkspace(e.target.value)}
            data-testid="restore-target-workspace"
            placeholder="UUID (optional)"
          />
        </label>
        <label className={styles.field}>
          {t("dataTransfer.restore.confirmation")}
          <input
            type="text"
            value={restoreConfirm}
            onChange={(e) => setRestoreConfirm(e.target.value)}
            data-testid="restore-confirmation"
            placeholder="RESTORE"
          />
        </label>
        <button
          type="button"
          className="btn-primary"
          onClick={onRestore}
          disabled={busy || !backupId.trim() || restoreConfirm !== "RESTORE"}
          data-testid="restore-button"
        >
          {restoreDryRun ? t("dataTransfer.restore.preview") : t("dataTransfer.restore.action")}
        </button>
        {restoreResult !== null && (
          <div className={styles.result} data-testid="restore-result">
            <span data-testid="restore-checksum">
              {t("dataTransfer.restore.checksum", {
                value: String(restoreResult.checksum_verified),
              })}
            </span>
            <span data-testid="restore-format">
              {t("dataTransfer.restore.format", {
                value: restoreResult.format_version,
              })}
            </span>
            {restoreResult.warnings.map((warning, index) => (
              <p key={index} className={styles.warning}>{warning}</p>
            ))}
          </div>
        )}
      </section>
    </main>
  );
}
