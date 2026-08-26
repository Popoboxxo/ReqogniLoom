/**
 * ARCH-L1-001 ReactFrontend — Theme Context (Theme Presets, two-axis).
 *
 * leaf_id: COMP-RF-001 (NavigationShell)
 * req_id:  REQ-L1-081-THEME (Light/Dark mode, always AA-readable)
 *
 * The theme is now TWO independent axes:
 *   - paletteKey: which named color palette (DB-backed ThemePalette row),
 *   - mode:       dark | light.
 *
 * Resolution order on load: user preference (server) > tenant default
 * (server) > localStorage cache > built-in fallback ("default"/dark).
 *
 * The resolved palette's --color-* token map is applied onto
 * document.documentElement as INLINE custom properties — inline style beats
 * every stylesheet rule, so the DB palette overrides the static fallbacks
 * in styles/tokens.css without touching them.
 *
 * Legacy compat: styles/tokens.css still ships complete :root theme blocks
 * selected via ``data-theme``. Until the palette list resolves (and as a
 * graceful fallback while offline) we keep writing a compatible value:
 *   - one of the three named single-mode palettes -> its own CSS block,
 *   - otherwise the mode ("dark" lives on bare :root, "light" has a block).
 * Once the inline tokens land they win anyway; the attribute only decides
 * what renders BEFORE/without server data. Additionally
 * ``data-theme-mode`` carries the raw mode for mode-only selectors.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { themePalettesApi, type ThemeMode, type ThemePalette } from "../api/themePalettes";

/** Palettes whose identity IS one specific look; used for the legacy
 * ``data-theme`` CSS-block mapping above. */
const NAMED_CSS_PALETTES = new Set(["bauhaus", "nordic", "sepia"]);

const FALLBACK_PALETTE = "default";
const FALLBACK_MODE: ThemeMode = "dark";

/**
 * Built-in fallback mode when no stored/server preference exists yet: honor
 * the OS/browser color-scheme preference before falling back to
 * ``FALLBACK_MODE``. This restores behavior the single-axis theme system had
 * (dropped when this file was rewritten for two-axis palettes) — without it,
 * every first-time session (no localStorage, no user/tenant preference,
 * e.g. a freshly seeded tenant) always renders dark regardless of the
 * visitor's OS preference.
 */
function resolveFallbackMode(): ThemeMode {
  try {
    if (window.matchMedia?.("(prefers-color-scheme: light)")?.matches) {
      return "light";
    }
  } catch {
    // matchMedia unavailable in this environment — use the built-in fallback.
  }
  return FALLBACK_MODE;
}

const STORAGE_KEY_PALETTE = "reqflow-theme-palette";
const STORAGE_KEY_MODE = "reqflow-theme-mode";
/** Pre-feature storage keys (flat single-axis themes). Kept so an old
 * cached choice still influences the initial paint instead of flashing. */
const LEGACY_STORAGE_KEY = "reqflow-theme";

interface ThemeContextValue {
  paletteKey: string;
  mode: ThemeMode;
  /** Every palette visible to this user (system stock + tenant custom). */
  palettes: ThemePalette[];
  setPreference: (paletteKey: string, mode: ThemeMode) => void;
}

const ThemeContext = createContext<ThemeContextValue | undefined>(undefined);

/** Legacy-compatible ``data-theme`` value for a (paletteKey, mode) pair. */
function legacyDataTheme(paletteKey: string, mode: ThemeMode): string {
  if (NAMED_CSS_PALETTES.has(paletteKey)) return paletteKey;
  return mode;
}

function applyPalette(
  palette: ThemePalette | undefined,
  mode: ThemeMode,
  paletteKey: string
): void {
  const root = document.documentElement;
  if (palette) {
    const tokens = mode === "dark" ? palette.dark_tokens : palette.light_tokens;
    Object.entries(tokens).forEach(([key, value]) => {
      root.style.setProperty(key, value);
    });
  }
  root.dataset.theme = legacyDataTheme(paletteKey, mode);
  root.dataset.themeMode = mode;
}

function readStored(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeStored(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // Storage unavailable (private mode, disabled) — session-only preference.
  }
}

export function ThemeProvider({ children }: { children: ReactNode }): JSX.Element {
  // Initial state: last cached choice (instant paint), else pre-feature
  // legacy cache, else built-in fallback. The server resolution below
  // overrides this once it arrives.
  const [palettes, setPalettes] = useState<ThemePalette[]>([]);
  const [paletteKey, setPaletteKey] = useState<string>(
    () => readStored(STORAGE_KEY_PALETTE) || readStored(LEGACY_STORAGE_KEY) || FALLBACK_PALETTE
  );
  const [mode, setMode] = useState<ThemeMode>(() => {
    const stored = readStored(STORAGE_KEY_MODE);
    if (stored === "light" || stored === "dark") return stored;
    const legacy = readStored(LEGACY_STORAGE_KEY);
    if (legacy === "light") return "light";
    return resolveFallbackMode();
  });

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      themePalettesApi.list(),
      themePalettesApi.getPreference(),
      themePalettesApi.getTenantDefault(),
    ])
      .then(([paletteList, userPref, tenantDefault]) => {
        if (cancelled) return;
        setPalettes(Array.isArray(paletteList?.results) ? paletteList.results : []);
        const resolvedKey =
          userPref.palette_key || tenantDefault.palette_key || FALLBACK_PALETTE;
        const resolvedMode = userPref.mode || tenantDefault.mode || resolveFallbackMode();
        setPaletteKey(resolvedKey);
        setMode(resolvedMode);
      })
      .catch(() => {
        // Network failure: keep the localStorage-cached values already in state.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const palette = palettes.find((p) => p.key === paletteKey);
    applyPalette(palette, mode, paletteKey);
    writeStored(STORAGE_KEY_PALETTE, paletteKey);
    writeStored(STORAGE_KEY_MODE, mode);
  }, [palettes, paletteKey, mode]);

  const setPreference = useCallback((newPaletteKey: string, newMode: ThemeMode): void => {
    setPaletteKey(newPaletteKey);
    setMode(newMode);
    // Promise.resolve(): a test double returning undefined stays harmless.
    Promise.resolve(themePalettesApi.setPreference(newPaletteKey, newMode)).catch(() => {
      // Server persistence failed — the local choice still applies this session.
    });
  }, []);

  const value = useMemo<ThemeContextValue>(
    () => ({ paletteKey, mode, palettes, setPreference }),
    [paletteKey, mode, palettes, setPreference]
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme must be used within ThemeProvider");
  return ctx;
}
