# Theme Presets: Zwei-Achsen-Theming, User-Presets, System-Default, Import/Export — Design

## Ziel

Löst Issue #707 ("Theme palette and light/dark mode cannot be combined —
flat list instead of two axes") strukturell, nicht kosmetisch. Palette
(`default`/`bauhaus`/`nordic`/`sepia`/…) und Modus (`dark`/`light`) werden
zwei unabhängige, frei kombinierbare Achsen statt einer flachen Liste von 5
Einträgen. Die gewählte Kombination wird zum **User-Preset**: server-seitig
pro Nutzer gespeichert, geräteübergreifend wirksam. Ein **System-Default**
(Tenant-weit, in den System-Einstellungen) greift für Nutzer ohne eigene
Präferenz. System-Admins können Paletten als JSON **importieren/
exportieren**; die eingebauten System-Paletten sind einsehbar, aber nicht
editierbar. Die linke Navigationsleiste wird von Palette+Modus
mitgesteuert, nicht nur der Content-Bereich.

## Ausgangslage (Ist-Zustand)

- `frontend/src/context/ThemeContext.tsx`: `THEMES` ist eine flache Liste
  von 5 Einträgen (`dark`, `light`, `bauhaus`, `nordic`, `sepia`) — jeder
  Eintrag ist gleichzeitig Palette UND Modus. `toggleTheme()` zykelt
  einfach durch die Liste. Persistenz nur via `localStorage`
  (`STORAGE_KEY = "reqflow-theme"`), geräte-lokal.
- `frontend/src/styles/tokens.css`: jede der 5 Optionen ist ein eigener
  `:root[data-theme="<id>"]`-Block mit hartcodierten Farb-Custom-Properties.
  `dark`/`light` haben je einen vollständigen, unabhängigen Block — de
  facto bereits die "Default"-Palette in beiden Modi. `bauhaus`, `nordic`,
  `sepia` existieren dagegen nur als je EIN Block (keine getrennte
  Hell/Dunkel-Variante).
- Workspace-Ebene: `backend/rest_api/serializers.py:1108` (`theme`-Feld auf
  `Workspace`), `_workspace_to_dict`/PATCH-Whitelist
  (`backend/rest_api/views.py:3993,4262`) — ein Workspace kann heute schon
  einen Theme-*String* als Default hinterlegen, der beim ersten Besuch
  restauriert wird (`hasStoredThemePreference()`-Mechanismus in
  `ThemeContext.tsx`). Dieser Mechanismus bleibt als Konzept relevant, wird
  aber durch das neue User-Preset/System-Default-Modell abgelöst (siehe
  Fehlerfälle).
- Kein Backend-Modell für Paletten-Farbwerte existiert — alles ist
  statisches CSS, im Repo eingecheckt, nicht zur Laufzeit veränderbar.
  Import/Export ist damit heute grundsätzlich unmöglich, nicht nur
  ungebaut.

## Architektur-Überblick

Farb-Tokens werden aus dem CSS herausgelöst und zur **Datenbank als
Single Source of Truth**. Strukturelle Tokens (Spacing, Radius,
Typografie-Skala, Schatten — alles Nicht-Farb-Werte) bleiben unverändert
in `tokens.css`.

```
ThemePalette (DB, Backend)
  ├─ is_system=True: default, bauhaus, nordic, sepia (geseedet, read-only)
  └─ is_system=False: von Admin importierte Custom-Paletten
       ↓
GET /api/v1/theme-palettes/  → Frontend lädt alle sichtbaren Paletten
       ↓
Frontend wählt (palette_key, mode) — aus UserThemePreference, sonst
TenantThemeDefault, sonst hartcodierter Fallback ("default", "dark")
       ↓
applyPalette(paletteTokens) — schreibt Farb-Custom-Properties per
element.style.setProperty() auf <html>, zusätzlich data-theme-mode
Attribut für :root[data-theme-mode="..."]-Selektoren in tokens.css
(strukturelle/modus-abhängige Nicht-Farb-Anpassungen, falls nötig)
```

Warum dynamische Injection statt weiterer statischer CSS-Blöcke: eine
importierte Custom-Palette hat keinen kompilierten CSS-Block im Repo —
sie muss zur Laufzeit angewendet werden können. Damit System- und
Custom-Paletten denselben Codepfad durchlaufen (kein Sonderfall für "die
eingebauten"), wenden auch die 4 System-Paletten ihre Farbwerte über
denselben `applyPalette()`-Mechanismus an, aus denselben DB-Zeilen
gelesen. `tokens.css` verliert damit seine Farb-Blöcke komplett zugunsten
der Seed-Migration (siehe Datenmodell) — das ist die eigentliche
Auflösung von Issue #161 ("Token-System hat kaum Reichweite") für die
Farb-Dimension, auch wenn das nicht das primäre Ziel dieser Spec ist.

## Datenmodell

**Neue App-Zugehörigkeit:** `admin_ops` (gleiches Muster wie das gerade
gebaute Banner-Feature — Tenant-weite, Admin-konfigurierbare Objekte).

**`ThemePalette`** (`TenantScopedModel`):
- `key`: `CharField`, z. B. `"default"`, `"bauhaus"`, `"acme-brand"`.
  Eindeutig pro Tenant (`unique_together` mit `tenant`).
- `label`: `CharField` — Anzeigename.
- `is_system`: `BooleanField`, `default=False`. `True` nur für die 4
  geseedeten Paletten — REST-Layer verweigert PATCH/DELETE auf
  `is_system=True`-Zeilen (403), egal welche Rolle.
- `dark_tokens`: `JSONField` — Farb-Custom-Properties für Dunkel-Modus,
  z. B. `{"--color-bg-primary": "#1a1a1a", "--color-text-primary": "#f0f0f0", ...}`.
  **Pflichtfeld** — kein Palette-Objekt ohne vollständigen Dark-Satz.
- `light_tokens`: `JSONField` — analog für Hell-Modus. **Ebenfalls
  Pflichtfeld** — keine Teil-Paletten. Das ist die bewusste Antwort auf
  die Ausgangslage: `bauhaus`/`nordic`/`sepia` bekommen als Teil der
  Migration (Task-Ebene, nicht dieser Spec) ihre fehlende zweite Variante
  neu entworfen, bevor sie in dieses Modell geseedet werden — kein
  Fallback-Mechanismus für fehlende Modi, weil das die
  Zwei-Achsen-Garantie (jede Palette in jedem Modus nutzbar) aufweichen
  würde.
- `token_keys_version`: `CharField` — Version des erwarteten
  Farb-Token-Schlüssel-Sets (siehe Fehlerfälle, Import-Validierung).
- `created_by`: `FK[User]`, `null=True` (leer für System-Paletten).
- `created_at`, `updated_at`.

**`UserThemePreference`** (`TenantScopedModel`, ein Objekt pro User):
- `user`: `OneToOneField[User]`.
- `palette_key`: `CharField`, verweist auf `ThemePalette.key` (kein
  harter FK, da eine Palette gelöscht werden könnte, während ein User sie
  noch referenziert — siehe Fehlerfälle für den Fallback).
- `mode`: `CharField`, `"dark"` | `"light"`.
- `updated_at`.

**`TenantThemeDefault`** (`TenantScopedModel`, ein Objekt pro Tenant —
gleiches Eindeutigkeits-Muster wie `Banner`s Global-Scope-Constraint):
- `palette_key`: `CharField`.
- `mode`: `CharField`.
- Partial-Unique-Constraint: genau eine Zeile pro Tenant.

**Migration:** seeded die 4 System-Paletten (`default`, `bauhaus`,
`nordic`, `sepia`) mit `is_system=True` und vollständigen
`dark_tokens`/`light_tokens`. `default`s beide Varianten werden 1:1 aus
den heutigen `:root`/`:root[data-theme="light"]`-Blöcken übernommen
(keine Farbänderung, reine Datenmigration). `bauhaus`/`nordic`/`sepia`s
jeweils fehlende Variante muss als Teil dieser Migration farblich neu
entworfen werden (Kontrast-Konformität wie die bestehenden Blöcke,
geprüft von `frontend/src/test/theme-contrast.test.ts`, das um die neuen
Kombinationen erweitert wird) — das ist echte Design-Arbeit, kein
mechanischer Task, und wird im Implementierungsplan als eigener,
zeitlich größerer Task ausgewiesen.

## API

- `GET /api/v1/theme-palettes/` — alle sichtbaren Paletten (System +
  Tenant-Custom) mit vollen Token-Daten. Kein Auth-Level über normalen
  Workspace-Zugriff hinaus (jeder eingeloggte User braucht das, um sein
  Theme anzuwenden).
- `POST /api/v1/theme-palettes/` — importiert eine neue Custom-Palette.
  Body: `{"label": str, "dark_tokens": {...}, "light_tokens": {...}}`.
  Nur System-Admin. `is_system` wird server-seitig immer auf `False`
  gesetzt (Client kann es nicht setzen). Validierung: `dark_tokens`/
  `light_tokens` müssen exakt das Schlüssel-Set aus dem aktuellen
  `token_keys_version`-Kontrakt enthalten — kein Mehr, kein Weniger
  (verhindert sowohl unvollständige als auch beliebige/Fremd-CSS-Keys).
- `GET /api/v1/theme-palettes/{key}/export/` — beliebige Palette
  (System oder Custom) als JSON zum Download, gleiche Form wie der
  Import-Body plus `label`/`key`/`is_system`-Metadaten. Jeder mit
  Workspace-Zugriff darf exportieren (Lesen, kein Schreiben).
- `DELETE /api/v1/theme-palettes/{key}/` — nur Custom-Paletten
  (`is_system=False`), nur System-Admin. `is_system=True` → 403.
  Löschen einer Palette, die noch von `UserThemePreference`- oder
  `TenantThemeDefault`-Zeilen referenziert wird: siehe Fehlerfälle.
- `GET/PUT /api/v1/users/me/theme-preference/` — eigenes User-Preset.
  `PUT` Body: `{"palette_key": str, "mode": "dark"|"light"}`. Jeder
  eingeloggte User für sich selbst.
- `GET/PUT /api/v1/system/theme-default/` — Tenant-weiter Default. `PUT`
  nur System-Admin. Gleiche Rollenprüfung wie die bestehende
  `GlobalBannerView` (`Operation.READ` für GET, `WRITE`/Tenant-Admin für
  PUT).

## Frontend

**`ThemeContext.tsx`** (grundlegend umgebaut):
- State wird zu zwei Werten: `paletteKey: string`, `mode: "dark" | "light"`
  statt einem `theme: string`.
- Lädt beim Mount `GET /api/v1/theme-palettes/` (gecacht, selten
  ändernde Daten) und `GET /api/v1/users/me/theme-preference/`.
  Auflösungsreihenfolge: `UserThemePreference` (falls gesetzt) →
  `TenantThemeDefault` → hartcodierter Fallback (`"default"`, `"dark"`,
  identisch zum heutigen `FALLBACK_THEME`).
- `applyPalette(palette: ThemePalette, mode)`: schreibt
  `document.documentElement.style.setProperty(key, value)` für jeden
  Eintrag in `palette[mode + "_tokens"]`, setzt zusätzlich
  `document.documentElement.dataset.themeMode = mode` (für eventuelle
  modus-abhängige, nicht-farbliche `tokens.css`-Selektoren, z. B.
  Schatten-Intensität).
- `setPreference(paletteKey, mode)`: aktualisiert lokalen State sofort
  (optimistic), sendet `PUT /api/v1/users/me/theme-preference/` im
  Hintergrund.
- `hasStoredThemePreference()`/`localStorage`-Fallback bleibt NUR für den
  Zeitraum zwischen erstem Seitenaufbau und dem Eintreffen der
  Server-Antwort erhalten (verhindert einen sichtbaren Flash-of-default-
  theme) — sobald die Server-Antwort da ist, überschreibt sie den
  `localStorage`-Wert und schreibt ihn auch dorthin zurück (Cache für den
  nächsten Ladevorgang, nicht mehr Quelle der Wahrheit).

**Navigationsleiste:** `NavigationShell`/Sidebar-Komponenten müssen
ausschließlich `var(--color-*)`-Custom-Properties nutzen, keine
hartcodierten Werte — Implementierungsplan enthält einen Grep-Audit-Task,
der jeden hartcodierten Farbwert in `NavigationShell/`-Komponenten gegen
die neuen Tokens migriert (Anschluss an die bereits laufende
Hex-Literal-Ratchet-Konvention aus `ui-ratchet.test.ts`).

**System-Einstellungen** — neuer Abschnitt "Theme-Verwaltung"
(`ThemeManagementSection.tsx`, analog `BannerSection.tsx`):
- Liste aller Paletten (System + Custom), System-Paletten mit
  Read-only-Badge, Farbvorschau (kleine Swatch-Reihe pro Modus).
- "Exportieren"-Button pro Palette (löst Datei-Download aus).
- "Importieren"-Button (Datei-Upload, JSON) — nur sichtbar für
  System-Admin.
- "Als Tenant-Default setzen"-Auswahl (Palette + Modus-Dropdown).

**User-Einstellungen** — bestehender Profil-Bereich
(`UserProfileSettings/`) bekommt einen Palette/Modus-Picker, der
`setPreference()` aufruft. Ersetzt den bisherigen `toggleTheme()`-Button
in der Navigationsleiste durch zwei unabhängige Controls (Paletten-
Auswahl, Modus-Umschalter) — die Kombinierbarkeit muss auch im
Schnellzugriff sichtbar sein, nicht nur in den Einstellungen.

## Fehlerfälle

- Custom-Palette wird gelöscht, während ein User oder der Tenant-Default
  sie referenziert: `UserThemePreference`/`TenantThemeDefault` behalten
  den (jetzt toten) `palette_key` — beim nächsten Laden greift
  `ThemeContext`s Auflösung: Palette nicht in der geladenen Liste
  gefunden → fällt auf den nächsten Schritt der Kette zurück (User-Pref
  ungültig → Tenant-Default; Tenant-Default ungültig → hartcodierter
  Fallback). Kein Absturz, kein Weißbildschirm.
- Import mit unvollständigem/falschem Token-Set → `400` mit Liste der
  fehlenden/unerwarteten Keys (kein stiller Teil-Import).
- Versuch, eine System-Palette zu PATCHen/DELETEn → `403`, Fehlermeldung
  "System themes are read-only".
- Kein `WRITE`/Tenant-Admin-Recht für Import/Export/Default-Setzen →
  `403`, gleiche Rollenprüfung wie Banner-Feature.
- Palette lädt nicht (Netzwerkfehler) → `ThemeContext` bleibt auf dem
  zuletzt bekannten `localStorage`-Cache, kein Blockieren des
  restlichen App-Ladens.

## Testing (Überblick, Details folgen im Implementierungsplan)

- Backend: Modell-Constraints (`is_system` read-only, Tenant-Uniqueness
  für `TenantThemeDefault`), Import-Validierung (vollständige/unerwartete
  Keys), Export-Symmetrie (Export-Output ist gültiger Import-Input),
  Fallback-Kette bei gelöschter Referenz.
- Frontend: `applyPalette()` schreibt genau die erwarteten CSS-Properties;
  Auflösungsreihenfolge (User → Tenant → Fallback) als reiner Unit-Test;
  Kontrast-Tests (`theme-contrast.test.ts`) für alle neuen
  Palette×Modus-Kombinationen; Sidebar-Snapshot/Visual-Regression für
  mindestens 2 Kombinationen, um zu verifizieren, dass die Navigation
  mitfärbt.
- i18n: alle neuen UI-Strings (Theme-Verwaltung, Import/Export-Buttons,
  Fehlermeldungen) brauchen DE/EN-Paare.
- `data-testid` auf allen neuen interaktiven Elementen.

## Bewusst außerhalb dieses Scopes (v1)

- Kein Theme-Marktplatz/Sharing zwischen Tenants — Import ist rein
  lokal pro Tenant, keine Cross-Tenant-Bibliothek.
- Kein Workspace-Level-Override zwischen User-Preset und Tenant-Default
  — nur die zwei Ebenen aus der ursprünglichen Anforderung. Das
  bestehende `Workspace.theme`-Feld (Ist-Zustand) wird durch dieses
  Modell funktional abgelöst, aber nicht in dieser Spec formal entfernt
  (Migrations-/Deprecation-Entscheidung ist Sache des
  Implementierungsplans).
- Kein visueller In-App-Paletten-Editor (Farbpicker, Live-Vorschau beim
  Bauen einer neuen Palette) — Import ist für v1 ausschließlich JSON-
  Datei-basiert, keine GUI zum Erstellen einer Palette von Grund auf.
- Keine Migration bestehender `localStorage`-Präferenzen aus der Zeit vor
  diesem Feature in `UserThemePreference` — ein User mit einer alten
  `localStorage`-Präferenz sieht beim ersten Laden nach dem Rollout den
  System-Default, bis er/sie erneut wählt (kein Daten-Backfill aus dem
  Browser in die DB, da serverseitig kein Zugriff auf clientseitigen
  `localStorage`-Inhalt für andere Nutzer/Geräte besteht).
