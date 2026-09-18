# Umsetzungsplan: UI-Konsolidierung Dialoge, Buttons, Tabs und Attribut-Format

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps
> use checkbox (`- [ ]`) syntax for tracking.

**Ziel:** Die im [UI-Audit 2026-09-18](../reviews/UI_AUDIT_2026-09-18_DIALOGE_BUTTONS_ATTRIBUTE.md)
belegten Inkonsistenzen beseitigen — 207 klassenlose Buttons, 18 konkurrierende
Button-Klassen, drei verschiedene Dialog-Fußabstände, rohe Systemnamen als Feld-Labels und
eine nutzerferne Attribut-Reihenfolge — **ohne** die laut Audit bereits korrekten Bereiche
(Dialog-ARIA, Tabs, Fokusring, i18n-Parität) zu beschädigen.

**Architektur:** Es wird **keine** neue Primitive erfunden. Alle vier vorhandenen
Fundamente bleiben: `.btn-*` aus `styles/global.css`, `shared/Dialog`, die
Attribut-Definition aus `shared/ArtifactForm`, und die Ratchet-Tests aus
`frontend/src/test/ui-ratchet.test.ts`. Der Plan ist reine **Konsolidierung auf
Vorhandenes** plus **zwei neue Ratchet-Zähler**, damit die Migration nicht zurückfällt.

**Tech-Stack:** React 18 + TypeScript 5.5 strict, CSS Modules mit `styles/tokens.css`,
react-i18next, vitest, Playwright, ESLint 9.

**Quellen:** [UI-Audit 2026-09-18](../reviews/UI_AUDIT_2026-09-18_DIALOGE_BUTTONS_ATTRIBUTE.md) ·
[UI-Konzept](../../UI_KONZEPT.md) Kapitel 3, 8, 12, 13, 14, 16

---

## Global Constraints

- **Keine neuen Farb-Literale.** Jede Farbe über `var(--color-*)`, jede Größe über
  `var(--space-*)` oder `var(--btn-h-*)`. Das ESLint-Gate
  `no-literal-color-in-inline-style` und der Ratchet `HEX_LITERAL_*` prüfen das.
- **Kein neues `style={{...}}`.** `STYLE_BRACE_BASELINE = 811` steht laut Audit (M-00)
  **exakt** auf dem Messwert. Jede neue Inline-Style-Stelle macht `frontend-test` rot.
- **Kein neues `background: var(--color-primary);` in einem CSS-Modul.**
  `PRIMARY_FILL_BASELINE = 29` steht exakt auf dem Messwert (M-00). Genau diese Deklaration
  gehört `.btn-primary` allein.
- **Kein neuer klassenloser `<button>`.** Bis T-60 landet, gilt die Regel manuell; danach
  erzwingt sie der Test.
- **Baselines werden gesenkt, nie erhöht.** Wörtlich aus
  `ui-ratchet.test.ts:19-22`: „Never raise a baseline to make a test pass — that defeats
  the ratchet's purpose." Jede Aufgabe, die eine Baseline senkt, senkt die Konstante **im
  selben PR**.
- **`data-testid` auf jedem interaktiven Element** (E2E-Pflicht, Playwright).
- **i18n-Schlüssel sind verschachtelte Objekte** in
  `frontend/src/i18n/locales/{de,en}.json`, **keine** gepunkteten Flachschlüssel
  (`keySeparator` ist `"."`). `src/test/i18n-parity.test.ts` verlangt strukturelle
  Gleichheit — **jede** neue Taste muss in **beiden** Dateien landen.
- **Der Dialog-Fuß ist der `Dialog`-`footer`-Slot.** Kein Aufrufer rendert seine
  Aktionsleiste selbst, außer er begründet es im Code (F-01-Ausnahme regeln).
- **Tabs bleiben, wie sie sind.** `role="tablist"`/`role="tab"`/`aria-selected`/
  `aria-controls`/Roving-Tabindex sind laut Audit korrekt — es wird **nur** die
  Button-Optik der Tab-/Toggle-Controls angefasst, nie die ARIA-Mechanik.
- Testbefehle (aus dem Repo-Root), analog zum Tabellenansicht-Plan:
  ```bash
  FT() { docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml \
      --project-directory . run --rm frontend-test sh -c "npm install && npx vitest run $*"; }
  E2E() { cd e2e && npx playwright test "$@"; }
  ```
  Nie die volle Playwright-Suite im Fix-Loop — nur die berührten Specs.
- Branch: `refactor/ui-dialog-button-konsolidierung`. Conventional Commits, englische
  Nachrichten. **Nie** direkt auf `main`.

---

## Reihenfolge und Abhängigkeiten

```
T-00 Baselines verifizieren ─────────────┐  (muss zuerst, sonst misst jede
                                         │   spätere Aufgabe gegen falsche Zahlen)
                                         ▼
T-60 Ratchet-Zähler für Buttons ──┐   (muss früh, damit die Migration
                                  │    messbar ist)
                                  ▼
T-10 Button-Inventar + Mapping ──► T-11 T-12 T-13 T-14   (Block B)
T-20 Dialog-Fuß Konvention ──────► T-21 T-22 T-23        (Block F)
T-30 Feld-Label-Resolver ────────► T-31 T-32             (Block A/I)
T-40 Sektions-Reihenfolge ───────► T-41 T-42 T-43        (Block A)
T-50 Feedback/Leerzustand ───────► T-51                  (Block S)
T-70 Einzelabnahme Rest-Dialoge ─────────────────────────► (Abschluss)
```

---

## Block 0 — Messfundament

### T-00 · Baselines nachmessen und auf den echten Wert setzen

**Bezug:** Audit M-00.

- [ ] **Die drei Ratchet-Werte unabhängig nachmessen** (exakt die Regex der Testdatei
      verwenden, nicht eine eigene — sonst misst man etwas anderes):
  - `STYLE_BRACE_PATTERN = /style=\{\{/g` über `collectNonTestTsxFiles(COMPONENTS_DIR)`
  - `PRIMARY_FILL_PATTERN = /background:\s*var\(--color-primary\)\s*;/g` über
    `collectCssFiles(COMPONENTS_DIR)` **nach** Kommentar-Strip
  - `HEX_LITERAL_PATTERN = /#[0-9a-fA-F]{3,8}/g` über `collectNonTestTsxFiles(SRC_DIR)`
- [ ] **Werte dokumentieren** (Ist-Wert, Baseline, Delta) in einem neuen Abschnitt
      „Messwerte 2026-09-18" in `docs/reviews/UI_AUDIT_2026-09-18_*.md`.
- [ ] **Falls ein Ist-Wert unter der Baseline liegt:** Konstante in
      `ui-ratchet.test.ts` auf den Ist-Wert senken — im selben Commit.
- [ ] **Falls ein Ist-Wert exakt auf der Baseline liegt:** keine Änderung, aber der
      Befund M-00 wird bestätigt und im Plan als Begründung für „jede Aufgabe senkt" geführt.
- [ ] `FT ui-ratchet` → grün.

**Akzeptanz:** Die drei Ist-Werte sind schriftlich belegt und die Konstanten sind
nachweislich ≤ Ist-Wert.

---

### T-60 · Ratchet-Zähler für klassenlose Buttons einführen

**Bezug:** Audit D-01. **Muss vor der Button-Migration landen**, sonst ist der Fortschritt
nicht messbar und der Rückfall nicht verhindert.

**Datei:** `frontend/src/test/ui-ratchet.test.ts`

- [ ] **Zähler definieren**, im Stil der vorhandenen Konstanten (Kommentarblock mit
      Begründung, Datum und Zielwert):
  ```ts
  // Audit 2026-09-18, Finding B-01: 207 of 424 <button> elements under
  // components/ carry no className at all, so they inherit only the four
  // declarations in global.css:52-57 — no height, no radius, no colour, no
  // hover. That is the machine-checkable core of the "buttons look like five
  // different products" verdict.
  //
  // This is a frozen ceiling, not a zero-target: 207 call sites cannot be
  // migrated in one change. Lower the constant whenever a file converts to
  // the canonical .btn-* classes. Target for this migration: <= 60.
  const CLASSLESS_BUTTON_PATTERN = /<button\b(?![^>]*\bclassName=)[^>]*>/g;
  const CLASSLESS_BUTTON_BASELINE = 207;
  ```
- [ ] **Zähler zum Laufen bringen** über `collectNonTestTsxFiles(COMPONENTS_DIR)`, mit
      `toBeLessThanOrEqual(CLASSLESS_BUTTON_BASELINE)`.
- [ ] **Prüfen, dass der Zähler nicht überzählt:** Kommentare innerhalb eines `<button>`-Tags
      kommen nicht vor; ein `<button` in einem JSX-Kommentar ist unwahrscheinlich, aber der
      Test soll wie `countNonCommentOccurrences` bei Bedarf Kommentare entfernen.
- [ ] **Gegenprobe:** den Zähler einmal versuchsweise auf `206` setzen, `FT ui-ratchet`
      laufen lassen und **rot** werden sehen — beweist, dass der Regex greift.
- [ ] Konstante zurück auf `207`, `FT ui-ratchet` → grün.

**Akzeptanz:** Der Test zählt die 207, die Gegenprobe war rot, der Test ist wieder grün.

---

## Block B — Buttons

### T-10 · Mapping-Tabelle als Entscheidungsgrundlage

**Bezug:** Audit B-01, B-02.

- [ ] **Alle 18 Modul-Button-Klassen auf die vier kanonischen abbilden.** Ergebnis ist eine
      Tabelle (im Plan oder im Audit-Report) mit drei Spalten: *Modul-Klasse* → *Ziel*
      (`.btn-primary` / `-secondary` / `-danger` / `-ghost` oder **„bleibt"**) → *Grund*.
      Startpunkt aus dem Audit:
      | Modul-Klasse(n) | Vorschlag Ziel |
      |---|---|
      | `.btnPrimary`, `.primaryBtn`, `.primaryButton`, `.buttonPrimary`, `.actionButton` (primär genutzt) | `.btn-primary` |
      | `.secondaryBtn`, `.secondaryButton`, `.btnOutline` | `.btn-secondary` |
      | `.btnOutlineDanger`, `.btnDanger`, `.cancelBtn` | `.btn-danger` |
      | `.btnGhost`, `.actionBtn` (transparent) | `.btn-ghost` |
      | `.submitBtn` + `.submitBtnEnabled/Disabled` (IcdDetailPane) | `.btn-primary` + kein eigener Disabled-Zustand |
      | `.saveButton` (Banner-Sektionen) | prüfen: evtl. legitim eigener Kontext |
      | `.btn` (GlossaryView) Basisklasse | prüfen, ob sie nur Geometrie ist |
  - [ ] **Ausnahmen explizit begründen.** Die Audit-Tabelle nennt legitime Nicht-Buttons
        (`background: var(--color-primary)` für gewählte Tabs/Chips) — dieselbe Sorgfalt hier.
- [ ] **Für jede „bleibt"-Entscheidung** einen Codekommentar mit Begründung vorsehen.

**Akzeptanz:** Die Tabelle ist vollständig, jede der 18 Klassen ist zugeordnet.

---

### T-11 · `DiagramGraphEditor` und `DiagramList` auf Tokens ziehen

**Bezug:** B-04 (Literalmaße).

- [ ] `DiagramGraphEditor.module.css:65` `padding: 6px 10px` → `var(--space-2) var(--space-3)`
      (oder die nächstliegende Token-Stufe) und `:228` `width/height: 32px` →
      `var(--btn-h-sm)`.
- [ ] `DiagramGraphEditor.module.css:688` dieselbe Literal-Padding-Stelle.
- [ ] `DiagramList.module.css:54` `font-size: 1.1rem` → Token-Stufe; `line-height: 1`
      prüfen.
- [ ] `DiagramGraphEditor.module.css:109` `padding: 0` + `border: none` als Icon-Button
      prüfen — Icon-Buttons brauchen nach Konzept 8.5 **3:1** gegen die Umgebung.
- [ ] `FT ui-ratchet` → grün, `CLASSLESS_BUTTON` unverändert oder gesunken.

**Akzeptanz:** Keine Pixel-Literale mehr in diesen drei Regeln.

---

### T-12 · Toolbar-Buttons der Attribut-Seite auf `.btn-*` (9 klassenlose Buttons)

**Bezug:** B-01, schwerste Einzelstelle (`9/9`). Real gesehen: `List`/`Table`/`Layout`/
`Export`/`Import`/`Add from catalog`/`Add section`/`Save` stehen als nackte Textbuttons in
einer Reihe.

**Datei:** `frontend/src/components/AttributeEditor/AttributeEditorPage.tsx:696-794`

- [ ] **View-Mode-Umschalter** (`attribute-editor-view-list`, `-view-table`): das ist ein
      Segmented-Control, **kein** Primärbutton-Paar. Prüfen, ob dafür eine eigene,
      token-basierte Segmented-Control-Regel existiert (`.btn-tab` in `global.css:186`
      existiert bereits!). Auf `.btn-tab` umstellen statt auf `.btn-primary` — sonst
      leuchtet der gewählte Modus wie eine Aktion.
- [ ] **`attribute-editor-layout-toggle`**: ist ein `aria-pressed`-Toggle, also `.btn-secondary`
      plus sichtbarer gedrückter Zustand.
- [ ] **`attribute-editor-export` / `-import`**: Sekundäraktionen → `.btn-secondary`.
- [ ] **„Add from catalog" / „Add section"**: prüfen, ob das Sekundär (→ `.btn-secondary`)
      oder primär ist. Es darf **genau eine** Primäraktion im Kopf geben (Konzept 12.1) —
      und das ist `Save`.
- [ ] **`Save`**: `.btn-primary`, disabled solange nichts geändert.
- [ ] **Danach:** `CLASSLESS_BUTTON_BASELINE` auf den neuen Ist-Wert senken (erwartet
      −9 → 198).
- [ ] `FT ui-ratchet` + `E2E attributes` (falls Spec existiert) → grün.

**Akzeptanz:** 0 klassenlose Buttons in `AttributeEditorPage.tsx`, Baseline gesenkt.

---

### T-13 · `GlossaryView`, `BaselinesView`, `WorkspaceSettings`, `CsvImport`

**Bezug:** B-01.

- [ ] `GlossaryView.tsx` (9 klassenlose) — `.btn`, `.btnOutline`, `.btnOutlinePrimary`,
      `.btnOutlineDanger` aus `GlossaryView.module.css:30-60` auf die kanonischen Klassen
      umstellen und die vier Modul-Klassen **löschen**.
- [ ] `BaselinesView.tsx` (5) — alle auf `.btn-*`.
- [ ] `WorkspaceSettings.tsx` (6) + `PermissionsSection.tsx` (5) — auf `.btn-*`; für die
      Berechtigungsmatrix prüfen, ob Icon-Buttons (`var(--btn-h-sm)`) oder Textbuttons.
- [ ] `CsvImport.tsx` (5 von 7) — `.primaryBtn`/`.secondaryBtn` aus
      `CsvImport.module.css:136,153` entfernen, auf kanonisch umstellen.
- [ ] Nach **jeder** Datei: Baseline senken und `FT ui-ratchet`.
- [ ] `E2E csv-import glossary baselines workspace-settings` → grün.

**Akzeptanz:** Die vier Modul-Paare sind gelöscht, Baseline ist um die migrierte Anzahl
gesunken.

---

### T-14 · Restliche klassenlose Buttons und verbleibende Modul-Klassen

**Bezug:** B-01, B-02, B-03.

- [ ] `AttributeEditor/LayoutFlowEditor.tsx` (8), `AttributeList.tsx` (8),
      `DiagramView/DiagramDetailView.tsx` (7), `TestRuns/*` (7 über 3 Dateien),
      `SystemSettings/*` (11 über 3 Dateien), `UserProfileSettings/*` (7),
      `DashboardViews/WorkspaceCard.tsx` (4), `NavigationShell/SidebarNavigation.tsx` (6),
      `RequirementEditors/ReqTraceLinkPanel.tsx` (4), `RequirementTreeNode.tsx` (3) und die
      übrigen 20+ Dateien mit 1–3 Vorkommen.
- [ ] **`SidebarNavigation` gesondert betrachten:** Navigationseinträge sind **keine**
      Buttons im Aktionssinn — hier ist zu prüfen, ob eine eigene, token-basierte
      Navigations-Regel die richtige Antwort ist statt `.btn-ghost`. Entscheidung
      dokumentieren.
- [ ] **`SubmitBtnDisabled`-Dublette** (B-03): `IcdDetailPane.module.css:79-89` entfernen und
      den kanonischen `:disabled`-Zustand nutzen.
- [ ] **Ziel am Ende von T-14:** ≤ 60 klassenlose Buttons (Rest = bewusste Ausnahmen mit
      Kommentar). Baseline entsprechend senken.

**Akzeptanz:** `CLASSLESS_BUTTON_BASELINE <= 60`, jede verbleibende Stelle hat einen
Codekommentar mit Grund.

---

## Block F — Dialoge und Popups

### T-20 · Dialog-Fuß als eine Regel durchsetzen

**Bezug:** F-01, F-02.

- [ ] **Entscheidung dokumentieren:** Ist `ArtifactForm` ein Sonderfall (Formular mit
      eigenem Submit-Handling), der den Footer-Slot nicht nutzen kann? Falls **ja**:
      `ArtifactForm.module.css:185-189` muss **dieselben** Werte wie
      `Dialog.module.css:143-149` tragen (`padding: var(--space-3) var(--space-6)
      var(--space-5)`, `border-top: 1px solid var(--color-border)`), damit beide Wege
      identisch aussehen. Falls **nein**: `ArtifactForm` bekommt einen Weg, seinen
      Aktionsblock in den `footer`-Slot zu heben.
- [ ] Die Entscheidung als Kommentar in beiden Dateien verlinken (Toggle-Ausnahme-Stil aus
      `UI_KONZEPT.md:16.3`).
- [ ] `FT` betroffene Artefakt-Tests → grün.

**Akzeptanz:** Der Requirement-Create-Dialog hat sichtbar denselben Fuß wie
`SignatureDialog` und `CreateWorkspaceModal`.

---

### T-21 · `SignatureDialog` auf die Primitive ziehen

**Bezug:** F-02.

**Datei:** `frontend/src/components/Reviews/SignatureDialog.tsx:41-70`

- [ ] **`bodyStyle`, `footerStyle`, `inputStyle`, `labelStyle`** durch CSS-Modul-Klassen
      ersetzen (`SignatureDialog.module.css` neu anlegen, token-basiert).
- [ ] Die vier `style={{...}}`-Stellen **entfernen** → `STYLE_BRACE_BASELINE` von **811** auf
      **807** senken (exakter Delta, nach dem Commit nachmessen).
- [ ] **Footer-Buttons in den `footer`-Slot** — dadurch greifen die 44px-Touch-Ziele aus
      `Dialog.module.css:215-217` automatisch.
- [ ] **Prüfen:** Der `labels`-Block ist im Dialog-Kontext ein Formularfeld → dafür muss die
      kanonische Feld-Optik gelten (siehe T-30).
- [ ] `E2E review-workflow` → grün.

**Akzeptanz:** 0 Inline-Styles in `SignatureDialog.tsx`, Baseline um 4 gesenkt.

---

### T-22 · Zwei Bestätigungs-Dialoge auf einen reduzieren

**Bezug:** F-03.

- [ ] **Diff der beiden Dateien** `shared/ConfirmDialog.tsx` (106 Z.) und
      `WorkflowEditor/ConfirmDialog.tsx` (74 Z.) erstellen und die funktionalen
      Unterschiede auflisten (Props, Testids, Texte, Varianten).
- [ ] **Entscheiden:** `shared/ConfirmDialog` gewinnt (breiter, `shared/`, hat Testids);
      der Workflow-Variante fehlende Fähigkeiten dort ergänzen.
- [ ] **`WorkflowEditor/ConfirmDialog.tsx` löschen** und die Aufrufer
      (`StateDialog`, `TransitionDialog`, `WorkflowEditorPage`) auf `shared/ConfirmDialog`
      umstellen.
- [ ] `E2E se-workflow` → grün.

**Akzeptanz:** Genau eine Bestätigungs-Primitive im Baum.

---

### T-23 · Admin-Dialoge aufräumen

**Bezug:** F-04.

- [ ] `AdminDialog/SystemHealthDialog.tsx` (13 Inline-Styles),
      `SystemSettings/WorkspaceAdminSection.tsx` (12) → CSS-Modul-Klassen, Baseline senken.
- [ ] `AdminDialog/TriLabelOverviewDialog.tsx` und `SystemSettings/EnforcementFlipDialog.tsx`
      gegen die Konvention prüfen (Fuß, Titel, `role`).
- [ ] **Alle Admin-Dialoge einmal real durchklicken** (System Settings → User Management →
      Audit) und Screenshots ablegen.
- [ ] `E2E user-management banners workspace-settings` → grün.

**Akzeptanz:** Admin-Dialoge haben keinen Inline-Style mehr und einen Fuß wie alle anderen.

---

## Block A/I — Attribut-Labels und Übersetzung

### T-30 · Feld-Label-Resolver mit i18n-Vorrang

**Bezug:** A-01, I-01. **Das ist die Ursache des sichtbaren Sprachen-Mischmaschs.**

**Datei:** `frontend/src/components/shared/ArtifactForm/fields/FieldShell.tsx:25-29, 69-70`

- [ ] **Reihenfolge der Label-Auflösung festlegen und implementieren:**
      1. `t(\`artifactForm.field.${attribute.name}\`)`, **wenn** der Schlüssel existiert;
      2. sonst der Definitions-Label (`attribute.label.en/de`);
      3. sonst der rohe Name (`attribute.name`) — nur als letzter Notnagel.
- [ ] **`useTranslation` in `FieldShell.tsx` einführen** (Datei steht in der 24er-Liste
      ohne `useTranslation`).
- [ ] **Fallback prüfen:** `i18next` liefert bei fehlendem Schlüssel den Schlüssel selbst
      zurück — es braucht deshalb eine explizite Existenzprüfung (`i18n.exists(key)`) oder
      die Signatur `t(key, { defaultValue: "" })` mit Leerprüfung, damit ein fehlender
      Schlüssel **nicht** als `artifactForm.field.acceptance_criteria` sichtbar wird.
- [ ] **Hilfsfunktion** `attributeLabel()` (Zeile 26-29) so umbauen, dass sie die Sprache
      nicht mehr selbst auswählt, sondern den bereits aufgelösten Text bekommt.

**Akzeptanz:** `acceptance_criteria` erscheint nicht mehr als roher Name.

---

### T-31 · Übersetzungen für alle Kern-Attributnamen ergänzen

**Bezug:** A-01. Der Schlüsselbaum `artifactForm.field.*` kennt heute nur **drei** Einträge.

- [ ] **Alle Attributnamen auflisten**, die real in den Create-/Edit-Dialogen der acht
      Artefakttypen erscheinen (aus der Definition, nicht geraten): mindestens
      `acceptance_criteria`, `title`, `description`, `status`, `priority`, `category`,
      `type`, `level`, `verification_method`, `validation_method`, `rationale`, `source`,
      `owner`, `reporter`, `complexity_fibonacci`, `difficulty`, `criticality`.
- [ ] **Für jeden Namen** eine verständliche Bezeichnung in **EN und DE** ergänzen —
      `artifactForm.field` in `en.json:2161` **und** `de.json:2161`.
      Beispiel: `acceptance_criteria` → EN „Acceptance criteria", DE „Akzeptanzkriterien".
- [ ] **Regel für Terminologie:** Fachbegriffe, die das UI-Konzept 14.1 ausdrücklich als
      Zielgruppensprache behält (Baseline, Trace Link, Requirement), werden **nicht**
      übersetzt; reine Systemnamen (`acceptance_criteria`, `complexity_fibonacci`) **immer**.
- [ ] `FT i18n-parity` → grün (beide Dateien strukturell gleich).
- [ ] **Danach** den realen Dialog in **beiden** Sprachen durchklicken und Screenshots
      ablegen.

**Akzeptanz:** Kein roher `snake_case`-Name mehr als sichtbares Label; Paritätstest grün.

---

### T-32 · Die sechs `*ArtifactForm`-Adapter und `ListToolbar` gegen i18n prüfen

**Bezug:** I-02.

- [ ] `RequirementArtifactForm.tsx`, `ArchitectureArtifactForm.tsx`, `AdrArtifactForm.tsx`,
      `RiskArtifactForm.tsx`, `IssueArtifactForm.tsx`, `TestCaseArtifactForm.tsx`,
      `shared/ListToolbar.tsx` auf hardcodierte Texte prüfen.
- [ ] Hardcodierte Beschriftungen über i18n ziehen (beide Sprachen).
- [ ] **Nicht jede Datei braucht `useTranslation`** — reine Wrapper, die nur Props
      durchreichen und Text von außen bekommen, bleiben ohne. Die Entscheidung pro Datei
      dokumentieren, damit die 24er-Liste nicht pauschal als Schuld gelesen wird.

**Akzeptanz:** Kein sichtbarer Mischtext mehr; die verbleibenden Dateien ohne
`useTranslation` sind als reine Wrapper belegt.

---

## Block A — Attribut-Anordnung

### T-40 · Sektions-Reihenfolge kuratieren

**Bezug:** A-02.

**Datei:** `frontend/src/components/shared/ArtifactForm/ArtifactForm.tsx:142-166`
(`groupIntoSections`) — ordnet heute nach First-Appearance.

- [ ] **Soll-Reihenfolge festlegen** (Vorschlag, mit dem Nutzer abzustimmen):
      `Identification` → `Content` → `Classification` → `Verification` → `Attribution` →
      `Traceability` → `Change control` → `Type-specific` → `Custom fields`.
- [ ] **Zentrale Konstante** einführen, z. B. `SECTION_ORDER: readonly string[]`, und
      `groupIntoSections` danach sortieren; unbekannte Sektionen (Workspace-definierte)
      **ans Ende**, in Definitionsreihenfolge.
- [ ] **Keine Sektion darf verschwinden** — die Sortierung ist rein ordinal.
- [ ] **Workspace-Kompatibilität:** Die Attribut-Definition ist per Workspace
      konfigurierbar. Eine feste Reihenfolge darf eine bewusst gesetzte
      Definition-Reihenfolge nicht überschreiben, falls der Workspace das explizit steuert.
      Prüfen, ob `SectionLayout`/`sections[].order` dafür der richtige Hebel ist und die
      Konstante nur den **Fallback** bildet.
- [ ] `FT ArtifactForm` + `FT layout-flow` → grün (es gibt `layout-flow.test.ts`!).
- [ ] Real durchklicken: Requirement, Architecture, TestCase.

**Akzeptanz:** `Identification` ist die erste Sektion im Create-Dialog.

---

### T-41 · Befund A-03 klären: `description` vs. `Description`

**Bezug:** A-03. **Das ist zuerst eine Datenfrage, keine Codeänderung.**

- [ ] **Herkunft ermitteln:** auf `/attributes?entityType=Requirement` prüfen, ob beide
      Attribute in der Definition stehen, und über die API
      (`/api/v1/attribute-definitions/`) bzw. die DB nachsehen, welches `kind`
      (`core`/`extended`), welchen `section` und welche `order` sie haben.
- [ ] **Entscheiden:**
  - Falls `Description` ein versehentlich angelegtes Extended-Attribut ist → als Datenproblem
    dokumentieren und dem Nutzer zur Löschung vorlegen (nicht eigenmächtig löschen).
  - Falls es zwei legitime Felder sind → die **Labels** müssen sich unterscheiden (T-31),
    z. B. „Description" vs. „Description (legacy)" — aber nur, wenn das fachlich stimmt.
- [ ] **Falls Code-Ursache:** `ensure_sections`/`materialize_sections` prüfen, ob ein
      Groß-/Kleinschreibungs-Normalisierungsschritt fehlt.

**Akzeptanz:** Die Herkunft ist belegt und eine Entscheidung liegt vor.

---

### T-42 · Sektions-Verhalten Create vs. Edit sichtbar begründen

**Bezug:** A-04, A-05.

**Datei:** `ArtifactForm.tsx:661-694`

- [ ] **`aria-current="false"` von dem `<span>` entfernen** (Zeile 670) — der Wert ist auf
      einem nicht-interaktiven Element irreführend (A-05).
- [ ] Entweder:
      - **(a)** Im Create-Modus einen **sichtbaren Hinweis** an den nicht aufklappbaren
        Sektionskopf setzen (z. B. das Schloss-Symbol `lockedHint` aus
        `artifactForm.lockedHint`, das bereits existiert und übersetzt ist), damit der
        Unterschied **gewollt** aussieht; **oder**
      - **(b)** die Sektionen auch im Create-Modus aufklappbar machen und das
        Pflichtfeld-Problem anders lösen (z. B. automatisches Aufklappen beim
        Save-Versuch mit Fokussprung zum ersten ungültigen Feld).
- [ ] Begründung als Kommentar belassen/ergänzen.
- [ ] `E2E requirements requirement-editor` → grün.

**Akzeptanz:** Der Unterschied ist entweder beseitigt (b) oder erklärt (a).

---

### T-43 · Sektions-Kopf-Optik an die Button-Regel anschließen

**Bezug:** B-01 (Sektionsköpfe sind `<button>` in `ArtifactForm.tsx:675`).

- [ ] Prüfen, ob der Sektionskopf-`<button>` klassenlos ist und damit in den Zähler fällt;
      wenn ja, eine token-basierte Modul-Klasse verwenden (kein `.btn-*`, weil es ein
      Disclosure ist — aber Geometrie über `--btn-h-*`/`--space-*`).
- [ ] `aria-expanded` und Chevron-Verhalten unverändert lassen (Audit: korrekt).

**Akzeptanz:** Sektionsköpfe haben definierte Höhe und Fokusring, ARIA unverändert.

---

## Block S — Feedback und Zustände

### T-50 · Lade- und Fehlerzustände als Primitive prüfen

**Bezug:** S-01.

- [ ] **Inventur:** Alle Stellen, die `Loading`/`loading` rendern (494 Treffer in
      Komponenten — davon viele Identifier, nicht Renderings), nach **drei** Musterarten
      klassifizieren: Spinner, Skeleton, gar nichts.
- [ ] Das Konzept 13.2 verlangt **Platzhalter in der Form des späteren Inhalts**, nicht ein
      zentriertes Rädchen, und **kein** Rendering unter 300 ms.
- [ ] **Falls ein Skeleton-Bedarf belegt ist:** als Aufgabe „Skeleton-Primitive" anlegen —
      `shared/Spinner/Spinner.tsx` existiert bereits und bleibt für kurzlebige Fälle.
- [ ] **Fehler-bei-Laden mit „Erneut versuchen"** (Konzept 12.12) prüfen: existiert eine
      Primitive dafür? Falls nicht, ist das der größere Bedarf als das Skeleton.

**Akzeptanz:** Die Lade-/Fehlerlage ist klassifiziert und eine begründete Aufgabe entstanden.

---

### T-51 · Leerzustand vs. Kein-Treffer flächig nachziehen

**Bezug:** S-02.

- [ ] **Alle listenführenden Routen auflisten** (Requirements, Needs, Architecture, ADRs,
      Risks, Issues, TestCases, Test Runs, Baselines, Glossary, ICDs, Diagrams, Reviews,
      Trace Links, Goals).
- [ ] **Pro Route real prüfen:** Filter setzen, sodass nichts passt — erscheint „Kein
      Treffer" mit **„Filter zurücksetzen"**, oder fälschlich „Leer" mit „Neu anlegen"?
- [ ] Findings pro Route dokumentieren; Fixes als eigene Aufgaben aufnehmen (nicht in
      diesem Plan vorziehen).
- [ ] Ergebnis in den Audit-Report als neuen Abschnitt nachtragen.

**Akzeptanz:** Eine belegte Liste „Route → korrekt / falsch" liegt vor.

---

## Block E — Abschluss

### T-70 · Einzelabnahme der restlichen Dialoge

**Bezug:** Audit §5, Punkt 1 — die im Zwischenschritt **nicht** einzeln gesehenen Dialoge.

- [ ] **Jeden der 18 Modal-Wrapper** real öffnen und mit diesen sieben Kriterien bewerten
      (Checkliste pro Dialog, Ergebnis im Audit-Report):
      1. Titel = Beschriftung des auslösenden Knopfes (Konzept 12.8)
      2. Fuß aus dem `footer`-Slot, ohne Inline-Styles
      3. `role="dialog"` + `aria-modal` + `aria-labelledby` (Primitive prüfen)
      4. Escape schließt, Fokus kehrt zum Auslöser zurück
      5. Fokus fällt beim Öffnen auf das erste bedienbare Element
      6. Fehler bleiben im Dialog sichtbar (`role="alert"`), Dialog schließt **nicht**
      7. genau **eine** Primäraktion
- [ ] **Screenshots** je Dialog in **DE hell** und **EN dunkel**.
- [ ] **Ergebnis-Tabelle** in `docs/reviews/UI_AUDIT_2026-09-18_*.md` als Nachtrag.
- [ ] Verbleibende Findings als neue Aufgaben aufnehmen.

**Akzeptanz:** 18/18 Dialoge sind einzeln belegt.

---

### T-71 · Abschlussmessung und Baseline-Freeze

- [ ] **Alle Kennzahlen aus §1 des Audits erneut messen** und in einer Tabelle
      Ist-vorher → Ist-nachher → Δ gegenüberstellen.
- [ ] **Alle gesenkten Baselines** in `ui-ratchet.test.ts` gegen die Ist-Werte verifizieren.
- [ ] `FT` (volle Frontend-Suite) → grün.
- [ ] `E2E` berührte Specs → grün.
- [ ] Ergebnis in `docs/reviews/UI_AUDIT_2026-09-18_*.md` als „Ergebnis" nachtragen.

**Akzeptanz:** Jede Kennzahl ist gesunken oder unverändert, keine gestiegen.

---

## Fortschritts-Regeln

- **Nach jeder Aufgabe:** `FT ui-ratchet` — und die betroffene Baseline **im selben Commit**
  senken.
- **Nach jedem Block:** die realen Screenshots erneuern und in den Audit-Report legen.
- **Nie** eine Baseline erhöhen. Wenn eine Aufgabe sie nicht senken kann, wird das als
  Finding notiert, nicht als Ausnahme verbucht.
- **Nie** die ARIA-Mechanik der Tabs oder des `Dialog` anfassen, ohne T-70 zu wiederholen —
  sie ist laut Audit korrekt und damit das wertvollste, was dieser Umbau beschädigen kann.

---

## Offene Entscheidungen (vor der Umsetzung mit dem Nutzer klären)

1. **`ArtifactForm`-Fuß:** Sonderfall mit angeglichenem Abstand (T-20 Variante A) oder
   Umbau auf den `footer`-Slot (Variante B)?
2. **Attribut-Anordnung (T-40):** Ist die vorgeschlagene Soll-Reihenfolge richtig, oder gibt
   es eine fachlich andere Priorität? Insbesondere: gehört `Attribution` (Owner/Reporter)
   wirklich **nach** `Verification`?
3. **`description` vs. `Description` (T-41):** erst klären, ob Datenmüll — dann entscheiden.
4. **Button-Ziel `≤ 60`** (T-14): Ist das die akzeptierte Obergrenze für bewusste
   Ausnahmen, oder soll auf 0 gegangen werden?
5. **Befund A-03 / T-41** darf **nicht** durch eigenmächtiges Löschen von Attributen gelöst
   werden — Datenmutation braucht explizite Freigabe.
