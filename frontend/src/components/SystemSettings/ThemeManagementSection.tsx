/**
 * ARCH-L1-001 ReactFrontend — Theme Management section (Theme Presets).
 *
 * System-Admin surface in System Settings → Administration: list palettes,
 * import a palette from a JSON file, export any palette as JSON, delete
 * custom palettes. System palettes are read-only server-side and therefore
 * render a read-only badge instead of a delete button.
 */

import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  themePalettesApi,
  type ThemeMode,
  type ThemePalette,
} from "../../api/themePalettes";
import styles from "./ThemeManagementSection.module.css";

export function ThemeManagementSection(): JSX.Element {
  const { t } = useTranslation();
  const [palettes, setPalettes] = useState<ThemePalette[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [tenantDefaultKey, setTenantDefaultKey] = useState<string>("default");
  const [tenantDefaultMode, setTenantDefaultMode] = useState<ThemeMode>("dark");
  const [tenantDefaultSaved, setTenantDefaultSaved] = useState<boolean>(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

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
            <span className={styles.rowLabel}>{p.label}</span>
            <span className={styles.rowKey}>{p.key}</span>
            {p.is_system && (
              <span data-testid={`theme-readonly-badge-${p.key}`} className={styles.badge}>
                {t("systemSettings.themes.readOnly")}
              </span>
            )}
            <span className={styles.spacer} />
            <button
              type="button"
              data-testid={`theme-export-${p.key}`}
              onClick={() => handleExport(p.key)}
            >
              {t("systemSettings.themes.export")}
            </button>
            {!p.is_system && (
              <button
                type="button"
                data-testid={`theme-delete-${p.key}`}
                onClick={() => handleDelete(p.key)}
              >
                {t("systemSettings.themes.delete")}
              </button>
            )}
          </li>
        ))}
      </ul>
      <label className={styles.importLabel}>
        {t("systemSettings.themes.importLabel")}
        <input
          ref={fileInputRef}
          type="file"
          accept="application/json"
          data-testid="theme-import-input"
          onChange={(e) => void handleImportFile(e)}
        />
      </label>
      <div className={styles.tenantDefault} data-testid="tenant-default-picker">
        <span className={styles.tenantDefaultLabel}>
          {t("systemSettings.themes.tenantDefaultLabel")}
        </span>
        <select
          data-testid="tenant-default-palette-select"
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
          value={tenantDefaultMode}
          onChange={(e) => selectTenantDefaultMode(e.target.value as ThemeMode)}
        >
          <option value="dark">{t("nav.darkMode")}</option>
          <option value="light">{t("nav.lightMode")}</option>
        </select>
        <button
          type="button"
          data-testid="tenant-default-save"
          onClick={handleSaveTenantDefault}
        >
          {t("systemSettings.themes.tenantDefaultSave")}
        </button>
        {tenantDefaultSaved && (
          <span className={styles.tenantDefaultSaved} data-testid="tenant-default-saved">
            {t("systemSettings.themes.tenantDefaultSaved")}
          </span>
        )}
      </div>
    </section>
  );
}
