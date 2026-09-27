/**
 * ARCH-L1-001 ReactFrontend — Theme Management section (Theme Palettes).
 *
 * System-Admin surface in System Settings → Administration: list palettes,
 * import a palette from a JSON file, export any palette as JSON, delete
 * custom palettes. System palettes are read-only server-side and therefore
 * render a read-only badge plus a permanently disabled Delete control.
 *
 * Issue #1093 — three defects, all fixed here:
 *   1. No control carried a design-system class. Everything below is a global
 *      `.btn-*` / `.field-select` class; this component's module owns layout
 *      only (#954 convention).
 *   2. Seven identically-labelled "Exportieren" buttons with no object
 *      reference. Every action now says what it acts on: the visible label
 *      names the FORMAT ("JSON exportieren") and the accessible name / tooltip
 *      names the OBJECT ("Bauhaus als JSON exportieren"). The accessible name
 *      contains the visible label, so WCAG 2.5.3 Label in Name holds.
 *   3. The read-only state was prose above the list ("System-Paletten sind
 *      schreibgeschützt" in the section hint) and the row silently omitted its
 *      Delete control. It is now a state ON the control: a disabled Delete
 *      whose tooltip and accessible name explain why, next to the per-row
 *      read-only badge.
 *
 * Import: the control already was a real file picker (`<input type="file">`,
 * the only one in the frontend) — there is no inline text field to replace.
 * The repo has no file-picker *dialog* convention to follow, so none is
 * invented (that would be exactly the per-page drift this section is being
 * fixed for). What changes is that the picker is a labelled, focusable,
 * design-system-styled control instead of a bare native input.
 */

import { useEffect, useId, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  themePalettesApi,
  type ThemeMode,
  type ThemePalette,
} from "../../api/themePalettes";
import { ConfirmDialog } from "../shared/ConfirmDialog";
import styles from "./ThemeManagementSection.module.css";

export function ThemeManagementSection(): JSX.Element {
  const { t } = useTranslation();
  const [palettes, setPalettes] = useState<ThemePalette[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [tenantDefaultKey, setTenantDefaultKey] = useState<string>("default");
  const [tenantDefaultMode, setTenantDefaultMode] = useState<ThemeMode>("dark");
  const [tenantDefaultSaved, setTenantDefaultSaved] = useState<boolean>(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const importInputId = useId();
  // UI-09 (system audit P4): deleting a palette is destructive and
  // irreversible — require explicit confirmation.
  const [pendingDelete, setPendingDelete] = useState<ThemePalette | null>(null);

  useEffect(() => {
    let cancelled = false;
    themePalettesApi
      .list()
      .then((r) => {
        if (!cancelled) setPalettes(r.results);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(
            (err as { error?: { message?: string } })?.error?.message ?? String(err)
          );
        }
      });
    themePalettesApi
      .getTenantDefault()
      .then((d) => {
        if (cancelled) return;
        setTenantDefaultKey(d.palette_key ?? "default");
        setTenantDefaultMode(d.mode ?? "dark");
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  function handleSaveTenantDefault(): void {
    themePalettesApi
      .setTenantDefault(tenantDefaultKey, tenantDefaultMode)
      .then(() => {
        setTenantDefaultSaved(true);
        setError(null);
      })
      .catch((err: unknown) => {
        setError(
          (err as { error?: { message?: string } })?.error?.message ?? String(err)
        );
      });
  }

  function selectTenantDefaultKey(key: string): void {
    setTenantDefaultKey(key);
    setTenantDefaultSaved(false);
  }

  function selectTenantDefaultMode(mode: ThemeMode): void {
    setTenantDefaultMode(mode);
    setTenantDefaultSaved(false);
  }

  function reload(): void {
    themePalettesApi
      .list()
      .then((r) => setPalettes(r.results))
      .catch(() => undefined);
  }

  function handleExport(key: string): void {
    themePalettesApi.exportPalette(key).then((palette) => {
      const blob = new Blob([JSON.stringify(palette, null, 2)], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${key}.theme.json`;
      a.click();
      URL.revokeObjectURL(url);
    });
  }

  function handleDelete(key: string): void {
    themePalettesApi.deletePalette(key).then(reload).catch(() => undefined);
  }

  function confirmDelete(): void {
    if (!pendingDelete) return;
    handleDelete(pendingDelete.key);
    setPendingDelete(null);
  }

  /**
   * Issue #1093: "Als Standard speichern" had no visible target. The button's
   * accessible name and tooltip, and the caption next to it, all name the
   * palette + mode the two selects currently hold — so it is impossible to
   * save the wrong default by accident.
   */
  const tenantDefaultTarget = useMemo(() => {
    const palette = palettes.find((p) => p.key === tenantDefaultKey);
    const modeLabel =
      tenantDefaultMode === "dark" ? t("nav.darkMode") : t("nav.lightMode");
    return palette ? `${palette.label} · ${modeLabel}` : modeLabel;
  }, [palettes, tenantDefaultKey, tenantDefaultMode, t]);

  async function handleImportFile(e: React.ChangeEvent<HTMLInputElement>): Promise<void> {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      // jsdom's File polyfill lacks .text(); FileReader works everywhere.
      const text = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result));
        reader.onerror = () => reject(reader.error);
        reader.readAsText(file);
      });
      const parsed = JSON.parse(text) as {
        label?: string;
        key?: string;
        dark_tokens?: Record<string, string>;
        light_tokens?: Record<string, string>;
      };
      await themePalettesApi.importPalette(
        parsed.label ?? "",
        parsed.dark_tokens ?? {},
        parsed.light_tokens ?? {}
      );
      setError(null);
      reload();
    } catch (err: unknown) {
      setError(
        (err as { error?: { message?: string } })?.error?.message ?? String(err)
      );
    } finally {
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  return (
    <section className={styles.section} data-testid="theme-management-section">
      <h3>{t("systemSettings.themes.heading")}</h3>
      <p className={styles.hint}>{t("systemSettings.themes.hint")}</p>
      {error && (
        <p role="alert" data-testid="theme-management-error" className={styles.error}>
          {error}
        </p>
      )}
      <ul className={styles.list}>
        {palettes.map((p) => (
          <li key={p.key} data-testid={`theme-row-${p.key}`} className={styles.row}>
            <span className={styles.rowMain}>
              <span className={styles.rowLabel}>{p.label}</span>
              <span className={styles.rowKey}>{p.key}</span>
              {p.is_system && (
                <span data-testid={`theme-readonly-badge-${p.key}`} className={styles.badge}>
                  {t("systemSettings.themes.readOnly")}
                </span>
              )}
            </span>
            <span className={styles.rowActions}>
              <button
                type="button"
                className="btn-secondary"
                data-testid={`theme-export-${p.key}`}
                onClick={() => handleExport(p.key)}
                title={t("systemSettings.themes.exportJsonFor", { label: p.label })}
                aria-label={t("systemSettings.themes.exportJsonFor", { label: p.label })}
              >
                {t("systemSettings.themes.exportJson")}
              </button>
              {/* Issue #1093: the read-only state lives ON the control. A
                  system palette's Delete is permanently disabled with an
                  explanation, instead of the control being silently absent
                  (which left "not applicable" indistinguishable from
                  "not permitted for you"). */}
              <button
                type="button"
                className="btn-danger"
                data-testid={`theme-delete-${p.key}`}
                onClick={() => setPendingDelete(p)}
                disabled={p.is_system}
                title={
                  p.is_system
                    ? t("systemSettings.themes.systemReadOnlyHint")
                    : t("systemSettings.themes.deleteFor", { label: p.label })
                }
                aria-label={
                  p.is_system
                    ? t("systemSettings.themes.systemReadOnlyHint")
                    : t("systemSettings.themes.deleteFor", { label: p.label })
                }
              >
                {t("systemSettings.themes.delete")}
              </button>
            </span>
          </li>
        ))}
      </ul>
      <div className={styles.importRow}>
        <label className={styles.importLabel} htmlFor={importInputId}>
          {t("systemSettings.themes.importLabel")}
        </label>
        {/* The real file picker. Driven by the button next to it, so it is not
            a Tab stop of its own; it keeps its `data-testid` so the import
            test can feed it a File directly. */}
        <input
          ref={fileInputRef}
          id={importInputId}
          type="file"
          accept="application/json"
          className={styles.importInput}
          data-testid="theme-import-input"
          onChange={(e) => void handleImportFile(e)}
        />
        {/* #1093: the visible, design-system trigger. A native file input cannot
            be restyled into a button, so the control the user actually clicks
            is a real `.btn-secondary` that opens the picker. */}
        <button
          type="button"
          className="btn-secondary"
          data-testid="theme-import-btn"
          onClick={() => fileInputRef.current?.click()}
        >
          {t("systemSettings.themes.importButton")}
        </button>
      </div>
      <div className={styles.tenantDefault} data-testid="tenant-default-picker">
        <span className={styles.tenantDefaultLabel}>
          {t("systemSettings.themes.tenantDefaultLabel")}
        </span>
        <select
          data-testid="tenant-default-palette-select"
          className="field-select"
          value={tenantDefaultKey}
          onChange={(e) => selectTenantDefaultKey(e.target.value)}
        >
          {palettes.map((p) => (
            <option key={p.key} value={p.key}>
              {p.label}
            </option>
          ))}
        </select>
        <select
          data-testid="tenant-default-mode-select"
          className="field-select"
          value={tenantDefaultMode}
          onChange={(e) => selectTenantDefaultMode(e.target.value as ThemeMode)}
        >
          <option value="dark">{t("nav.darkMode")}</option>
          <option value="light">{t("nav.lightMode")}</option>
        </select>
        {/* Issue #1093: the visible target of the save, next to the two selects
            that define it. */}
        <span className={styles.tenantDefaultTarget} data-testid="tenant-default-target">
          {t("systemSettings.themes.tenantDefaultTarget", {
            target: tenantDefaultTarget,
          })}
        </span>
        <button
          type="button"
          className="btn-primary"
          data-testid="tenant-default-save"
          onClick={handleSaveTenantDefault}
          title={t("systemSettings.themes.tenantDefaultSaveFor", {
            target: tenantDefaultTarget,
          })}
          aria-label={t("systemSettings.themes.tenantDefaultSaveFor", {
            target: tenantDefaultTarget,
          })}
        >
          {t("systemSettings.themes.tenantDefaultSave")}
        </button>
        {tenantDefaultSaved && (
          <span className={styles.tenantDefaultSaved} data-testid="tenant-default-saved">
            {t("systemSettings.themes.tenantDefaultSaved")}
          </span>
        )}
      </div>

      {pendingDelete && (
        <ConfirmDialog
          title={t("systemSettings.themes.deleteConfirmTitle")}
          message={t("systemSettings.themes.deleteConfirmMessage", {
            label: pendingDelete.label,
          })}
          confirmLabel={t("systemSettings.themes.deleteConfirmButton", {
            label: pendingDelete.label,
          })}
          onConfirm={confirmDelete}
          onCancel={() => setPendingDelete(null)}
          testId="theme-delete-confirm"
        />
      )}
    </section>
  );
}
