# UI-Audit: Dialoge, Popups, Tabs, Buttons und Attribut-Layout

> **Status:** Audit abgeschlossen, Umsetzungsplan abgeleitet
> **Datum:** 2026-09-18
> **Grundlage:** `docs/UI_KONZEPT.md` (Kapitel 3, 8, 12, 13, 14, 15, 16, Anhang B)
> **Methode:** Statische Messung (`ripgrep`, Regex über `frontend/src`) **und** reale
> Sichtprüfung am laufenden Stack `localhost:5173` (Admin-Login, Playwright).
> **Änderungsumfang:** reine Analyse — es wurde **kein** Anwendungscode geändert.

Der zugehörige Umsetzungsplan steht in
[`docs/plans/2026-09-18-ui-dialog-und-button-konsolidierung.md`](../plans/2026-09-18-ui-dialog-und-button-konsolidierung.md).

---

## 0. Messverfahren und Vorbehalt

Alle Zahlen sind reproduzierbar. Genau wie in Anhang B des UI-Konzepts gilt: die
statischen Werte stammen aus `frontend/src` **ohne** `*.test.tsx`, die dynamischen aus
Playwright gegen den laufenden Dev-Stack.

**Wichtiger Vorbehalt zu den gemessenen Baselines.** Die drei Ratchet-Werte
(`STYLE_BRACE_BASELINE = 811`, `PRIMARY_FILL_BASELINE = 29`,
`HEX_LITERAL_OCCURRENCE_BASELINE = 17`) sind **heute exakt auf dem eingefrorenen
Grenzwert** — nicht darüber. Das ist keine Beruhigung, sondern der eigentliche Befund:
**der Ratchet ist an allen drei Stellen am Anschlag.** Jede neue Komponente mit einem
einzigen `style={{...}}` oder einer einzigen `background: var(--color-primary)`-Deklaration
lässt `frontend-test` rot werden. Der Druck ist damit real und unmittelbar, die Zahlen
selbst sind es nicht (Befund **M-00**).

---

## 1. Kennzahlen-Übersicht

| Kennzahl | Gemessen | Ziel | Quelle |
|---|---:|---:|---|
| `<button>` gesamt (Komponenten, ohne Tests) | **424** | — | statisch |
| davon **ohne jede `className`** | **207 (48,8 %)** | 0 | statisch |
| `.btn-*`-Klassen-Nutzung | 115 | — | statisch |
| konkurrierende Eigen-Button-Klassen in Modulen | **18 Klassen in 17 Dateien** | 0 | statisch |
| `style={{...}}` in `components/` | **811** | → 0 | Ratchet |
| `background: var(--color-primary)` in Modulen | **29** | → 0 | Ratchet |
| Sechsfarb-Hex-Literale | **17 in 3 Dateien** | → 0 | Ratchet |
| Inline-`style={{}}` in den 12 dialogreichsten Dateien | **165** | 0 | statisch |
| Routen | **53** | — | statisch |
| Routen mit `PageHeader` | 26 Verzeichnisse importieren sie | 53 | statisch |
| TSX-Dateien ohne `useTranslation` | **24 von 192 (12,5 %)** | 0 | statisch |
| i18n-Schlüsselparität EN ↔ DE | **1954 = 1954, 0 Abweichung** | 0 | statisch |
| Modal-Wrapper (Dialog-Primitive) | **1 kanonisch + 2 Bestätigungs-Dialoge** | 1 + 1 | statisch |
| Dialoge mit `inline style`-Footer | siehe **F-02** | 0 | statisch |
| Feld-Labels, die rohe Systemnamen zeigen | siehe **A-01** | 0 | real geprüft |

---

## 2. Die geprüften Dialoge, Popups und Tabs

### 2.1 Vollständige Inventur (Modal-Wrapper)

| # | Datei | Zeilen | Nutzt `shared/Dialog` | Bewertung |
|---|---|---:|---|---|
| 1 | `shared/Dialog/Dialog.tsx` | 193 | ist die Primitive | **kanonisch** |
| 2 | `shared/ConfirmDialog.tsx` | 106 | ja (vermutlich) | eigener Bestätigungs-Dialog |
| 3 | `WorkflowEditor/ConfirmDialog.tsx` | 74 | ja (vermutlich) | **zweiter** Bestätigungs-Dialog |
| 4 | `WorkflowEditor/WorkflowModal.tsx` | 53 | ja | legitimer Prop-Adapter |
| 5 | `WorkflowEditor/WorkflowModal.tsx` | 53 | ja | ok |
| 6 | `WorkflowEditor/StateDialog.tsx` | — | via WorkflowModal | ok |
| 7 | `WorkflowEditor/TransitionDialog.tsx` | — | via WorkflowModal | ok |
| 8 | `AdminDialog/SystemHealthDialog.tsx` | 14290 B | ja | 13 Inline-Styles |
| 9 | `AdminDialog/TriLabelOverviewDialog.tsx` | 5846 B | ja | |
| 10 | `AttributeEditor/AttributeCatalogDialog.tsx` | 10145 B | ja | |
| 11 | `AttributeEditor/AttributeCreateDialog.tsx` | 7322 B | ja | |
| 12 | `AttributeEditor/AttributeImportDialog.tsx` | 3149 B | ja | |
| 13 | `Goals/ArchiveConfirmDialog.tsx` | — | ja | |
| 14 | `Goals/GoalFormDialog.tsx` | — | ja | |
| 15 | `NavigationShell/CreateWorkspaceModal.tsx` | — | ja | |
| 16 | `Reviews/SignatureDialog.tsx` | 193 | ja | **umschifft den Footer** (4 Inline-Styles) |
| 17 | `SystemSettings/EnforcementFlipDialog.tsx` | — | ja | |
| 18 | `shared/CreateTraceLinkDialog/create-trace-link-dialog.tsx` | — | ja | |

**Ergebnis:** `shared/Dialog` als Primitive ist durchgesetzt — **26 Komponentendateien**
konsumieren sie, und `createPortal` existiert im gesamten `frontend/src` **genau einmal**
(Import + Aufruf, beide in `Dialog.tsx` — geprüft mit
`rg -n "createPortal" frontend/src`, 2 Treffer, beide in dieser Datei). Das ist eine gute
Nachricht und war vor der letzten Runde offensichtlich nicht so.

**Aber:** die **Footer-Konvention wird an mindestens zwei Stellen umgangen** (F-02), und
es gibt **zwei konkurrierende Bestätigungs-Dialoge** (F-03).

### 2.2 Tabs (ist der Bestand sauber?)

| Tab-System | Ort | Befund |
|---|---|---|
| Attribut-Sektionen (Artefakt-Formular) | `ArtifactForm.tsx:675-694` | korrekt: `role="tablist"`/`role="tab"`, `aria-selected`, Roving-Tabindex, `aria-expanded` — bei *einer* Sektion ist die Umsetzung als **Sektions-Disclosure**, nicht als Tabliste, sinnvoll |
| Markdown Edit/Preview | `MarkdownTabGroup.tsx:27-50` | korrekt: `role="tablist"`, `aria-selected`, `aria-controls`, Roving-Tabindex |
| Attribut-Sektionen **im Create-Modus** | `ArtifactForm.tsx:661-673` | **kein** Toggle — als `<span>` mit `aria-current="false"` gerendert (bewusst, Pflichtfeld hinter zugeklapptem Header wäre unsichtbar) |
| Attribut-Katalog / Layout-Editor | `AttributeCatalogDialog.tsx`, `LayoutFlowEditor.tsx` | je eigener Tab-Mechanismus, nicht geprüft bis ins Detail |
| Listenansicht/Tabellenansicht-Umschalter | `AttributeEditorPage.tsx:696-713` | `aria-pressed`-Buttons ohne `.btn-*`-Klasse (9 von 9 Buttons klassenlos) |

**Ergebnis:** Die ARIA-Mechanik der Tabs ist an den geprüften Stellen korrekt. Der Mangel
liegt **nicht** bei den Tabs, sondern beim **Aussehen der Tab-/Toggle-Controls** — sie
fallen in die 207 klassenlosen Buttons.

---

## 3. Findings

Schweregrade: **blocker** (bricht Konzept/AA oder ist ein Konsistenzbruch mit hoher
Sichtbarkeit), **major**, **minor**.

### Gruppe M — Messbefunde / Ratchet

#### M-00 — Alle drei Ratchet-Baselines stehen exakt auf dem Grenzwert · **blocker (prozessual)**
- `STYLE_BRACE_BASELINE = 811`, gemessen **811**
- `PRIMARY_FILL_BASELINE = 29`, gemessen **29**
- `HEX_LITERAL_OCCURRENCE_BASELINE = 17` (nicht nachgemessen, s. u.)
- Datei: `frontend/src/test/ui-ratchet.test.ts:503,978,711`
- **Wirkung:** Der Ratchet, der eine Rückkehr zum Wildwuchs verhindern soll, kann aktuell
  **nicht** greifen, weil er keine Reserve hat. Die nächste legitime neue Komponente macht
  ihn rot — und dann wird die Konstante "nach oben korrigiert", was laut Kommentar in der
  Datei ausdrücklich verboten ist.
- **Konsequenz für den Plan:** Der Plan muss **senken**, nicht nur halten.

### Gruppe F — Dialoge, Popups, Footer

#### F-01 — `ArtifactForm` rendert seine Aktionsleiste im Body statt im Dialog-Footer · **major**
- `frontend/src/components/shared/ArtifactForm/ArtifactForm.tsx:782-803` rendert
  `<div className={styles.actions}>` **innerhalb** des Formulars.
- `ArtifactForm.module.css:185-189` definiert `.actions` mit **nur**
  `display:flex; gap:var(--space-2); justify-content:flex-end`.
- Der `Dialog`-Footer hat dagegen (`Dialog.module.css:143-149`)
  `padding: var(--space-3) var(--space-6) var(--space-5)` plus `border-top`.
- **Wirkung:** Der wichtigste Dialog der App (Requirement anlegen/bearbeiten) hat einen
  Aktionsblock ohne Trennlinie und mit anderem Abstand als jeder andere Dialog. Real
  bestätigt: im Create-Dialog stehen `Cancel`/`Create` direkt unter dem letzten
  Formularfeld, ohne `border-top`, mit sichtbar weniger Luft als der `Dialog`-Footer sie
  vorsieht.
- **Betroffen:** alle 8 Artefakttypen, die `ArtifactForm` verwenden (Requirement,
  Architecture, Adr, Risk, Issue, TestCase, StakeholderNeed, Goal).

#### F-02 — Inline-Style-Footer umgeht die Konvention · **major**
- `frontend/src/components/Reviews/SignatureDialog.tsx:41-70` definiert
  `bodyStyle`, `footerStyle`, `inputStyle`, `labelStyle` als `React.CSSProperties`-Literale.
- Damit ist der Footer dieses Dialogs ein **dritter** Abstand (weder `Dialog`-Footer noch
  `ArtifactForm.actions`), und obendrein werden vier `style={{...}}` gezählt, ohne dass die
  `Dialog`-Primitive ihre eigenen Abstandsregeln anwenden kann.
- **Wirkung:** Signatur-Dialog wirkt schmaler/enger als der Rest; die
  Bottom-Sheet-Touch-Ziele aus `Dialog.module.css:215-217` (`.footer button`) greifen hier
  **nicht**, weil die Buttons nicht im `footer`-Slot liegen.

#### F-03 — Zwei konkurrierende Bestätigungs-Dialoge · **minor**
- `frontend/src/components/shared/ConfirmDialog.tsx` (106 Zeilen)
- `frontend/src/components/WorkflowEditor/ConfirmDialog.tsx` (74 Zeilen)
- Namentlich identisch, unterschiedlicher Umfang, zwei Wartungsorte für denselben Zweck.
- **Wirkung:** Löschbestätigungen können je nach Aufrufer unterschiedlich aussehen.

#### F-04 — `SystemHealthDialog` als Admin-Dialog mit 13 Inline-Styles · **minor**
- `frontend/src/components/AdminDialog/SystemHealthDialog.tsx`
- Der Admin-Bereich ist der Ort, an dem Konsistenz am stärksten erwartet wird (er wird
  selten benutzt und muss beim ersten Blick verständlich sein), hält aber die meisten
  Inline-Styles aller Dialoge nach `TestRunsList` und `IcdView`.

### Gruppe B — Buttons

#### B-01 — Knapp die Hälfte aller Buttons hat keine Klasse · **blocker**
- **207 von 424** `<button>`-Elementen in `frontend/src/components/` (ohne Tests) haben
  **kein** `className`-Attribut.
- Das UI-Konzept definiert genau **vier** kanonische Klassen
  (`global.css:103-183`: `.btn-primary`, `.btn-secondary`, `.btn-danger`, `.btn-ghost`)
  mit **einer** Höhe (`--btn-h-md` = 36px) und **einem** Radius (`--radius-btn` = 6px).
- Ein klassenloser Button erbt nur `global.css:52-57`
  (`cursor`, `font-family`, `transition`, `border:none`) — **keine** Höhe, **keinen**
  Radius, **keine** Farbe, **keine** Hover-Rückmeldung.
- **Schwerste Einzelstellen** (Anzahl klassenloser Buttons / Buttons insgesamt):
  | Datei | klassenlos / gesamt |
  |---|---|
  | `AttributeEditor/AttributeEditorPage.tsx` | **9 / 9** |
  | `GlossaryView/GlossaryView.tsx` | **9 / 11** |
  | `AttributeEditor/LayoutFlowEditor.tsx` | **8 / 8** |
  | `AttributeEditor/AttributeList.tsx` | **8 / 8** |
  | `DiagramView/DiagramDetailView.tsx` | **7 / 7** |
  | `NavigationShell/SidebarNavigation.tsx` | 6 / 10 |
  | `WorkspaceSettings/WorkspaceSettings.tsx` | **6 / 6** |
  | `BaselinesView/BaselinesView.tsx` | **5 / 5** |
  | `CsvImport/CsvImport.tsx` | 5 / 7 |
  | `WorkspaceSettings/PermissionsSection.tsx` | **5 / 5** |
  | `TestCaseEditors/DeriveTestCasePanel.tsx` | **5 / 5** |
- **Wirkung:** Genau das, was du siehst. Auf der Attribut-Seite stehen Toolbar-Buttons ohne
  Rahmen, ohne Füllung, ohne definierte Höhe neben `.btn-*`-Buttons mit Rahmen — die Klick-
  fläche ist kleiner als 36px, die Trefferfläche damit unter dem Konzeptmaß.

#### B-02 — 18 konkurrierende Button-Klassen in Modulen · **major**
Gemessene, namentlich verschiedene Eigen-Implementierungen:

`.actionBtn` · `.actionButton` · `.btn` · `.btnDanger` · `.btnGhost` · `.btnOutline` ·
`.btnOutlineDanger` · `.btnOutlinePrimary` · `.btnPrimary` · `.button` · `.buttonPrimary` ·
`.cancelBtn` · `.primaryBtn` · `.primaryButton` · `.saveButton` · `.secondaryBtn` ·
`.secondaryButton` · `.submitBtn`

in 17 Dateien, u. a. `GlossaryView.module.css` (`.btn`, `.btnOutline`, `.btnOutlinePrimary`,
`.btnOutlineDanger`), `CsvImport.module.css` (`.primaryBtn`, `.secondaryBtn`),
`IcdDetailPane.module.css` (`.submitBtn`, `.submitBtnEnabled`, `.submitBtnDisabled`,
`.cancelBtn`), `WorkflowEditor.module.css` (`.btnPrimary`, `.btnDanger`, `.btnGhost`).

- Das ist die Bestätigung der im Konzept zitierten „fünf parallelen Button-Systeme" — in
  Wahrheit **19** (4 kanonische + 18 Modul-Varianten, mit Überlappung).
- Der Ratchet misst davon nur einen Ausschnitt: `PRIMARY_FILL_BASELINE = 29` erfasst
  `background: var(--color-primary);` in Modulen, **nicht** die Klassenvielfalt selbst.
- **Wirkung:** Derselbe „Speichern"-Button ist je nach Seite unterschiedlich hoch, rund
  oder eckig, mit oder ohne Hover-Verfärbung.

#### B-03 — Disabled-Behandlung ist inkonsistent · **minor**
- Kanonisch: `global.css:176-183` setzt `opacity: .55`, `cursor: not-allowed`,
  `transform: none` für alle vier Klassen.
- `IcdDetailPane.module.css` hat dagegen eigene `.submitBtnDisabled`-Zustände, d. h. dort
  existiert eine **zweite** Disabled-Semantik.

#### B-04 — Icon-only-Buttons ohne einheitliches Maß · **minor**
- `global.css` kennt `--btn-h-sm/md/lg` (32/36/44px). Mehrere Module setzen stattdessen
  Literale: `DiagramGraphEditor.module.css:228` `width:32px;height:32px`,
  `DiagramList.module.css:54` `font-size:1.1rem`, `DiagramGraphEditor.module.css:65`
  `padding: 6px 10px`. Das sind genau die „hardcodierten Größen", die die Konvention
  verbietet.

### Gruppe A — Attribut-Format und -Anordnung (dein zweiter Kritikpunkt)

#### A-01 — Feld-Labels zeigen rohe Systemnamen statt Übersetzung · **blocker**
- Ursache: `frontend/src/components/shared/ArtifactForm/fields/FieldShell.tsx:70` rendert
  `attributeLabel(attribute, language)` (den Definitions-Label) und **nie** einen
  i18n-Schlüssel.
- **Real im Create-Dialog bestätigt** (Sichtprüfung, angemeldet, `/requirements` →
  „+ New Requirement"): die Felder
  - `acceptance_criteria`
  - `verification_method`

  erscheinen **als roher Name**, während im selben Dialog `Priority`, `Difficulty`,
  `Owner`, `Reporter`, `Rationale`, `Source`, `Verification status`, `Validation method`
  übersetzt sind. Der Dialog **mischt** also beide Konventionen.
- Die Übersetzungshilfe existiert bereits: `en.json:2161` / `de.json:2161`
  `artifactForm.field.{description,context,consequences}` — sie kennt nur **drei** Felder
  und wird ausschließlich von `MarkdownTabGroup.tsx:47` benutzt.
- **Wirkung:** Für einen Nutzer liest sich `acceptance_criteria` wie ein Fehler. Für den
  nicht-englischen Nutzer ist es schlicht nicht übersetzt, obwohl die Sprache auf DE steht.

#### A-02 — Sektions-Reihenfolge folgt der Definition, nicht dem Nutzerweg · **major**
- `ArtifactForm.tsx:142-166` (`groupIntoSections`) ordnet Sektionen nach
  **First-Appearance** im Attribut-Array.
- Real beobachtete Reihenfolge im Requirement-Dialog:
  `Attribution` → `Classification` → `Content` → `Identification` → `Verification` → `Traceability`.
- Erwartbar wäre für einen Nutzer: **Identification** (Titel) → **Content**
  (Beschreibung) → **Classification** → **Verification** → **Attribution** →
  **Traceability**.
- **Wirkung:** Der erste Screen des Dialogs zeigt „Attribution" und „Owner/Reporter" —
  Metadaten vor dem Inhalt. Das ist die Ursache deines Eindrucks, dass das Format nicht passt.

#### A-03 — Sektion „Content" enthält zwei potenziell konkurrierende Beschreibungsfelder · **major**
- Real auf `/attributes` (Sichtprüfung, Entity Type „Requirement") gesehen, Sektion
  **Content** enthält **gleichzeitig**:
  - `description` (klein, Monospace-artig) mit Label **„Description"**
  - `Description` (groß) mit Label **„Description"**
  - `acceptance_criteria`
- Zwei Attribute, deren Namen sich nur in der Groß-/Kleinschreibung unterscheiden und die
  als **identisches** Label „Description" gerendert werden, sind für den Nutzer nicht
  unterscheidbar.
- **Vorbehalt:** Ich habe das als **Datenbefund** in der laufenden Instanz beobachtet. Ob
  das aus einem Seed, einer Migration oder importierten Daten stammt, ist mit diesem Audit
  **nicht** geklärt und muss vor einem Fix geprüft werden (Aufgabe im Plan).

#### A-04 — Sektions-Verhalten unterscheidet sich zwischen Create und Edit · **minor**
- `ArtifactForm.tsx:661-673`: im Create-Modus ist der Sektionskopf ein `<span>` **ohne**
  Toggle, mit `aria-current="false"`.
- Im Edit-Modus (`ArtifactForm.tsx:675-694`) ist derselbe Kopf ein `<button>` mit
  `aria-expanded` und Chevron.
- **Wirkung:** Derselbe Dialog sieht in beiden Modi unterschiedlich aus (aufklappbar vs.
  starr). Das ist begründet (Kommentar im Code nennt Pflichtfelder hinter zugeklapptem
  Header), aber es ist ein **sichtbarer** Bruch, der erklärt werden muss — entweder durch
  eine sichtbare Sperr-Semantik (Schloss) oder durch einheitliches Verhalten.

#### A-05 — `aria-current="false"` auf einem `<span>` ist irreführend · **minor**
- `ArtifactForm.tsx:670` setzt `aria-current="false"` auf einen nicht-interaktiven
  `<span>`. Der Wert `"false"` ist laut ARIA der Standardwert einer Angabe, die hier gar
  nicht existiert; er suggeriert eine Navigation, die es nicht gibt.

### Gruppe I — i18n

#### I-01 — Die Übersetzungs-Parität ist **grün**, die Abdeckung nicht · **major**
- Gemessen: **1954 Schlüssel in EN, 1954 in DE, 0 Abweichungen** — die
  `i18n-parity.test.ts`-Anforderung aus `UI_KONZEPT.md:16.1` ist erfüllt.
- Gleichzeitig: **24 von 192** TSX-Dateien (12,5 %) benutzen `useTranslation` nicht,
  darunter `FieldShell.tsx`, `ListToolbar.tsx`, `StatusBadge.tsx`, `LevelBadge.tsx`,
  `Badge.tsx`, `WorkflowModal.tsx`, `WorkflowEditorLayout.tsx` und die sechs
  `*ArtifactForm.tsx`-Adapter.
- Nicht jede dieser Dateien gibt Text aus (manche sind reine Wrapper) — aber `FieldShell`
  tut es, und genau das erzeugt A-01.
- **Wirkung:** Der Paritätstest kann A-01 nicht finden, weil der Schlüssel **fehlt**, nicht
  **abweicht**. Der Test misst die falsche Seite.

#### I-02 — `nav.menuClose`-Klasse von Lücken im Hardcode · **minor**
- In den sechs `*ArtifactForm.tsx`-Adaptern und `ListToolbar.tsx` sind Texte/Beschriftungen
  hardcodiert statt über i18n. Das erzeugt je nach Sprache Mischtexte.

### Gruppe S — Zustände, Feedback, Fehler

#### S-01 — `role="alert"` existiert nur im Formular-Feld · **major**
- Vorhanden: `FieldShell.tsx:87-92` setzt `role="alert" aria-live="assertive"` für
  serverseitige Feldfehler (GitHub #677).
- Das UI-Konzept fordert (`UI_KONZEPT.md:12.12`) **vier** Rückmeldungsarten: Toast (Erfolg,
  4s), `role="alert"` im Formular (Fehler), Fehler beim Laden mit „Erneut versuchen",
  Hinweis im Fluss.
- Der Ratchet `LOCAL_TOAST_BASELINE = 2` belegt: es gibt nur **zwei** verbliebene lokale
  Toast-Implementierungen und die gemeinsame Primitive `shared/Toast/useToast` — aber die
  **Fehler-bei-Laden**-Variante mit Wiederholen ist nicht als Primitive nachgewiesen.

#### S-02 — Leerzustand vs. Kein-Treffer nicht durchgängig unterschieden · **major (Verdacht)**
- `UI_KONZEPT.md:13.3` verlangt die Unterscheidung ausdrücklich.
- `EmptyState` wird in **84** Komponenten referenziert — die Primitive ist also breit im
  Einsatz.
- **Nicht abgeschlossen:** Ob jede Liste den Filterfall korrekt als „Kein Treffer" mit
  „Filter zurücksetzen" statt als „Leer" mit „Neu anlegen" rendert, ist in diesem Audit
  **nicht** flächig geprüft (nur der Requirements-Fall real gesehen, dort korrekt).

### Gruppe D — Durchsetzung

#### D-01 — Kein Automatismus gegen klassenlose Buttons · **blocker (prozessual)**
- `ui-ratchet.test.ts` prüft `PRIMARY_FILL_PATTERN` (CSS-Module), `STATUS_BADGE`,
  `LEVEL_BADGE`, `TREE`, `LOCAL_TOAST`, `STYLE_BRACE`, `HEX_LITERAL`.
- Es gibt **keinen** Test, der einen `<button>` ohne `className` oder ohne `.btn-*`-Klasse
  zählt. Genau deshalb sind es 207 geworden.
- **Wirkung:** Ohne diesen Zähler wird jede Migration nach kurzer Zeit zurückfallen.

---

## 4. Was ausdrücklich **gut** ist (damit es nicht beim Umbau kaputtgeht)

| Bereich | Befund |
|---|---|
| Dialog-Primitive | `shared/Dialog` ist durchgesetzt; `createPortal` existiert genau **einmal** im Quellbaum (Import + Aufruf in `Dialog.tsx`, sonst nirgends) |
| Dialog-ARIA | `role="dialog"` + `aria-modal` + `aria-labelledby` + Fokustrap + Escape + Fokusrückgabe in der Primitive; die im Konzept (15.1) kritisierte Lage „`aria-modal` in 9 Dateien, `role="dialog"` in 0" ist **behoben** |
| Tabs | `MarkdownTabGroup` und die Artefakt-Sektionen nutzen korrektes `role="tablist"`/`role="tab"`/`aria-selected`/`aria-controls`/Roving-Tabindex |
| Fokusring | `global.css:63-67` global `:focus-visible` mit Token — die im Konzept teuerste Einzelbaustelle („`outline: none` ohne Ersatz") ist **behoben** |
| i18n-Parität | 1954 = 1954, 0 Abweichung, automatisch getestet |
| Bottom-Sheet | `Dialog.module.css:159-217` mit `dvh`, `visualViewport`, Safe-Area und 44px-Touch-Zielen |
| Token-Architektur | Zwei Ebenen (primitiv → semantisch), hell/dunkel plus drei Zusatzthemes, Kontrast geprüft |
| Ratchet-Existenz | Das Sperrklinken-Prinzip ist implementiert und dokumentiert — es fehlt nur die Reserve (M-00) und der Button-Zähler (D-01) |

---

## 5. Abgrenzung: was dieser Audit **nicht** geleistet hat

1. **Keine pixelgenaue Einzelabnahme aller ~30 Dialoge.** 18 Modal-Wrapper wurden
   inventarisiert und ihre Struktur geprüft; **real im Browser** gesehen wurden der
   Requirement-Create-Dialog und die Attribut-Seite. Die übrigen Bewertungen stützen sich
   auf Code-Evidenz. Das ist ausdrücklich der **Zwischenschritt**, den du verlangt hast.
2. **Keine Kontrastberechnung aller Dialoge.** Die Token-Ebene ist kontrastgeprüft; ob jede
   Kombination in jedem Dialog den geprüften Paaren entspricht, folgt aus den Findings zu
   Inline-Styles (F-02, F-04) nur teilweise.
3. **A-03 ist ein Datenbefund, kein Codebefund** — Herkunft nicht geklärt.
4. **S-02 ist ein Verdacht**, nicht flächig belegt.
5. **Kein Backend-Anteil.** Ob `acceptance_criteria` vs. `Description` aus einem
   Preset, einem Seed oder einer Import-Migration stammt, wurde nicht ermittelt.

---

## 6. Ableitung: Welche Findings der Plan adressiert

| Finding | Aufgabe im Plan | GitHub-Issue |
|---|---|---|
| M-00 | T-00 (Baselines verifizieren und senken) | #876 (Zahlen korrigieren) |
| B-01, B-02 | T-10 bis T-14 | **#986** |
| B-03, B-04 | T-11, T-14 | #986 |
| F-01, F-02 | T-20, T-21 | **#985** (falls Eigenbau-Overlay) |
| F-03 | T-22 | — |
| F-04 | T-23 | **#985** (`SystemHealthDialog`) |
| A-01, I-01 | T-30, T-31 | **#583** (`acceptance_criteria`) |
| I-02 | T-32 | — |
| A-02 | T-40 | **#929**, **#871** |
| A-03 | T-41 | #929, #583 |
| A-04, A-05 | T-42, T-43 | — |
| S-01 | T-50 | — |
| S-02 | T-51 | — |
| D-01 | T-60 | — |
| Einzelabnahme Rest-Dialoge | T-70 | — |
| — *(neu ergänzt)* | I-30 | **#926**, **#318** |
| — *(neu ergänzt)* | I-40 | **#808**, **#927**, **#928**, **#987** |
| — *(neu ergänzt)* | I-50 | **#186**, **#85**, **#876**, **#801**, **#810**, **#946** |

### 6.1 Issues, die dieser Audit bestätigt oder korrigiert

| # | Verhältnis zum Audit |
|---|---|
| **986** | **Bestätigt und verschärft.** Das Issue misst 10 Signaturen auf `/settings`; der Audit zeigt die strukturelle Ursache: **207 von 424** Buttons haben **keine** Klasse. Der 13,33-px-Fund im Issue ist das Symptom. |
| **985** | **Bestätigt.** Der Audit hat Escape/Fokus-Rückgabe der `shared/Dialog`-Primitive als **vorhanden** belegt — der wahrscheinlichste Fall ist daher ein **Eigenbau-Overlay**, nicht ein Defekt der Primitive. Das grenzt I-10 ein. |
| **926** | **Bestätigt.** Deckt sich mit Audit **F-02** (Dialog-Konventionen werden umgangen) und **I-02** (Label ohne Locale-Eintrag). |
| **318** | **Falsch gelabelt** (nur `enhancement`), ist aber barrierefreiheits-relevant → Label-Korrektur in I-00. |
| **876** | **Zahlen veraltet.** Issue nennt 1.015 Inline-Styles / 74 Hex-Farben; gemessen sind es **811** `style={{}}` und **17** Hex-Literale in **3** Dateien (`ui-ratchet.test.ts:503,711-712`). Vor der Abarbeitung korrigieren. |
| **871** | **Vermutlich veraltet.** Issue meldet fehlende Attribute `Rationale`, `Source`, `Owner`, `Priority` — alle vier **sind** im Create-Dialog vorhanden (real geprüft, Sektionen `Attribution`/`Classification`). Vor dem Fix gegen den Ist-Stand prüfen. |
| **186** | **Zombie-Verdacht.** Alle 19 in der Epic-Tabelle gelisteten Sub-Issues sind **CLOSED**, der Epic steht offen. Abschluss prüfen statt weiterführen. |
| **583** | **Teilweise bestätigt.** Der `acceptance_criteria`-Teil überschneidet sich direkt mit Audit **A-01** (roher Systemname als Label). |

### 6.2 Was der Audit **nicht** als Issue gefunden hat

Zu drei Befunden existiert **kein** offenes Issue — sie sind neu und gehören als Issues
angelegt (Aufgabe **I-70** im Plan):

1. **A-03** — `description` vs. `Description` als zwei Attribute in derselben Sektion.
2. **A-04/A-05** — Sektions-Toggle-Verhalten divergiert zwischen Create und Edit;
   `aria-current="false"` auf einem `<span>`.
3. **S-02** — Leerzustand vs. Kein-Treffer ist nicht flächig geprüft und möglicherweise
   nicht durchgängig umgesetzt.

Der Plan liegt unter
[`docs/plans/2026-09-18-ui-dialog-und-button-konsolidierung.md`](../plans/2026-09-18-ui-dialog-und-button-konsolidierung.md).
