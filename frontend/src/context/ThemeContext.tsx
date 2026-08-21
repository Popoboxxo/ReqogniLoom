/**
 * ARCH-L1-001 ReactFrontend — Theme Context.
 *
 * leaf_id: COMP-RF-001 (NavigationShell)
 * req_id:  REQ-L1-081-THEME (Light/Dark mode, always AA-readable)
 *
 * Applies the resolved theme to <html data-theme="..."> so styles/tokens.css
 * can flip every --color-* token. Preference order: localStorage > OS
 * prefers-color-scheme > dark (this app's default identity).
 *
 * UI concept ch. 8.6 / Task 8.1: a theme is an open-ended *id*, not one of two
 * fixed modes. Everything theme-specific lives in `styles/tokens.css` (a
 * primitive block plus a `:root[data-theme="<id>"]` semantic block); the only
 * code-side touch point for a new theme is one entry in `THEMES` below.
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

/**
 * A theme id. Matches the `data-theme` attribute value written to <html> and
 * the `:root[data-theme="<id>"]` selector in styles/tokens.css. Deliberately
 * an open string type rather than a closed union — adding a theme must not
 * require touching component code.
 */
export type Theme = string;

/** The dark default identity — rendered by the bare `:root` block. */
export const DEFAULT_DARK: Theme = "dark";
/** The light default — `:root[data-theme="light"]`. */
export const DEFAULT_LIGHT: Theme = "light";

export interface ThemeDefinition {
  /** `data-theme` value; must have a matching block in styles/tokens.css. */
  id: Theme;
  /** i18n key of the label offered when this theme is the next one. */
  labelKey: string;
}

/**
 * The registered themes, in switcher order. Adding a theme means adding one
 * entry here plus its token blocks in styles/tokens.css — nothing else.
 */
export const THEMES: readonly ThemeDefinition[] = [
  { id: DEFAULT_DARK, labelKey: "nav.darkMode" },
  { id: DEFAULT_LIGHT, labelKey: "nav.lightMode" },
  { id: "bauhaus", labelKey: "nav.bauhausTheme" },
  { id: "nordic", labelKey: "nav.nordicTheme" },
  { id: "sepia", labelKey: "nav.sepiaTheme" },
];

/** Theme applied when neither storage nor the OS expresses a preference. */
const FALLBACK_THEME: Theme = DEFAULT_DARK;

const STORAGE_KEY = "reqflow-theme";

interface ThemeContextValue {
  theme: Theme;
  /** The registered theme `toggleTheme` will switch to next. */
  nextTheme: ThemeDefinition;
  setTheme: (theme: Theme) => void;
  /** Advance to the next registered theme, wrapping around. */
  toggleTheme: () => void;
}

const ThemeContext = createContext<ThemeContextValue | undefined>(undefined);

function isRegistered(id: string | null): id is Theme {
  return id !== null && THEMES.some((t) => t.id === id);
}

/** True if a real, registered theme preference is already stored — i.e. this
 * is not the user's first visit with an opinion on theme. Used by
 * WorkspaceContext to decide whether the workspace-default restore effect
 * should apply on load (first-ever visit) or defer to the stored choice
 * (returning visit — #568 override-seeding fix). */
export function hasStoredThemePreference(): boolean {
  return isRegistered(window.localStorage.getItem(STORAGE_KEY));
}

function nextThemeOf(current: Theme): ThemeDefinition {
  const index = THEMES.findIndex((t) => t.id === current);
  return THEMES[(index + 1) % THEMES.length];
}

function resolveInitialTheme(): Theme {
  const stored = window.localStorage.getItem(STORAGE_KEY);
  if (isRegistered(stored)) return stored;
  if (window.matchMedia?.("(prefers-color-scheme: light)").matches) {
    return DEFAULT_LIGHT;
  }
  return FALLBACK_THEME;
}

export function ThemeProvider({ children }: { children: ReactNode }): JSX.Element {
  const [theme, setThemeState] = useState<Theme>(resolveInitialTheme);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    window.localStorage.setItem(STORAGE_KEY, theme);
  }, [theme]);

  const setTheme = useCallback(
    (next: Theme): void => setThemeState(isRegistered(next) ? next : FALLBACK_THEME),
    []
  );
  const toggleTheme = useCallback(
    (): void => setThemeState((prev) => nextThemeOf(prev).id),
    []
  );

  const value = useMemo<ThemeContextValue>(
    () => ({ theme, nextTheme: nextThemeOf(theme), setTheme, toggleTheme }),
    [theme, setTheme, toggleTheme]
  );

  return (
    <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
  );
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme must be used within ThemeProvider");
  return ctx;
}
