/**
 * ARCH-L1-001 ReactFrontend — Theme Presets API.
 *
 * Wraps the /api/v1/ theme-palette endpoints:
 *   GET/POST   /admin/theme-palettes/
 *   GET        /admin/theme-palettes/<key>/export/
 *   DELETE     /admin/theme-palettes/<key>/
 *   GET/PUT    /users/me/theme-preference/
 *   GET/PUT    /system/theme-default/
 */

import { apiClient } from "./client";

export interface ThemePalette {
  key: string;
  label: string;
  is_system: boolean;
  dark_tokens: Record<string, string>;
  light_tokens: Record<string, string>;
}

export type ThemeMode = "dark" | "light";

export interface UserThemePreference {
  palette_key: string | null;
  mode: ThemeMode | null;
}

export interface TenantThemeDefault {
  palette_key: string;
  mode: ThemeMode;
}

export const themePalettesApi = {
  list: (): Promise<{ results: ThemePalette[] }> =>
    apiClient.get<{ results: ThemePalette[] }>("/admin/theme-palettes/"),

  importPalette: (
    label: string,
    darkTokens: Record<string, string>,
    lightTokens: Record<string, string>
  ): Promise<ThemePalette> =>
    apiClient.post<ThemePalette>("/admin/theme-palettes/", {
      label,
      dark_tokens: darkTokens,
      light_tokens: lightTokens,
    }),

  exportPalette: (key: string): Promise<ThemePalette> =>
    apiClient.get<ThemePalette>(`/admin/theme-palettes/${key}/export/`),

  deletePalette: (key: string): Promise<void> =>
    apiClient.delete<void>(`/admin/theme-palettes/${key}/`),

  getPreference: (): Promise<UserThemePreference> =>
    apiClient.get<UserThemePreference>("/users/me/theme-preference/"),

  setPreference: (paletteKey: string | null, mode: ThemeMode): Promise<UserThemePreference> =>
    apiClient.put<UserThemePreference>("/users/me/theme-preference/", {
      palette_key: paletteKey,
      mode,
    }),

  getTenantDefault: (): Promise<TenantThemeDefault> =>
    apiClient.get<TenantThemeDefault>("/system/theme-default/"),

  setTenantDefault: (paletteKey: string, mode: ThemeMode): Promise<TenantThemeDefault> =>
    apiClient.put<TenantThemeDefault>("/system/theme-default/", {
      palette_key: paletteKey,
      mode,
    }),
};
