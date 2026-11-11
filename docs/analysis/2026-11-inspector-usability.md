# Usability-Prüfung Artefakt-Inspector — 2026-11

**Auftrag:** Task 3 aus `docs/superpowers/plans/2026-11-10-phase-b2-inspector-concept.md` (Usability-Prüfung an fünf Aufgaben).
**Eingabe:** `docs/analysis/2026-11-inspector-ist.md` (Task 2, Inventar und Inkonsistenzen I-01 … I-21).
**Zweck:** Ist-Aufwand je Nutzeraufgabe belegen, Verstöße gegen Nielsens zehn Heuristiken mit Schwere bewerten, die drei schwersten Probleme als Messlatte für Task 5 benennen.
**Stand:** Worktree `fix/phase-b1-frontend-hygiene`, Basis `origin/main` @ `f8c07842`.
**Sprache:** Deutsch (interne Doku). Belege als `datei:zeile`, Pfade relativ zur Repo-Wurzel.

---

## 1. Methode und Messdefinitionen

Die Prüfung ist eine **heuristische Evaluation am Code**, keine moderierte Nutzerstudie und keine instrumentierte Messung. Es lief kein Stack (`docs/analysis/2026-11-inspector-ist.md`, Abschnitt 0), daher gibt es keine Screenshots und keine gemessenen Millisekunden.

| Größe | Definition | Ermittlung |
|---|---|---|
| **Klick** | Eine Aktivierung eines Bedienelements (Maus oder Tastatur). Scrollen, Hover und Lesen zählen nicht als Klick. | Code-Pfad (welche Controls in welcher Reihenfolge nötig sind) |
| **Scroll** | Zusätzliche Scroll-/Suchstrecke, die kein Klick ist, aber Aufmerksamkeit kostet. Getrennt ausgewiesen. | DOM-Reihenfolge + `overflow`-Container |
| **Wartezeit** | Anzahl **sequenzieller HTTP-Runden**, bis die Antwort sichtbar sein kann. Keine Millisekunden. | Fetch-Ketten im Code |
| **Kontextverlust** | Information, die der Nutzer nach dem Schritt nicht mehr sieht und im Kopf behalten muss (Nielsen H6). | Zustands-/Routing-Analyse |
| **Schwere** | 0 = kein Problem · 1 = kosmetisch · 2 = gering · 3 = schwer · 4 = Blockade (Aufgabe nicht erfüllbar) | Nielsen-Skala 0–4 |

**Prämissen:** Viewport 1440 × 900, keine gespeicherten Inspector-Präferenzen. Folge: Der Inspector startet **eingeklappt** (`RightSidebar.tsx:87,110-118` — Breakpoint 1600 px). Die `TraceSpine` ist davon nicht betroffen, sie liegt außerhalb der Shell.

**Nebenlast unabhängig von der Aufgabe:** Jede Detailseite mit Spine lädt beim Öffnen zwei `impact`-Requests (parallel) und danach einen `resolve`-Batch — also **2 sequenzielle Runden und 3 Requests**, bevor die Kette vollständig ist (`useDerivationChain.ts:208-210,241-250`). Wird der Inspector aufgeklappt, kommen je nach Typ bis zu fünf weitere Requests dazu (Version 1 · Diff 2 · Trace 1 · Kommentare 1 · Provenienz 1; `RightSidebar.tsx:443-460`, `DiffPanel.tsx:208-217`).

---

## 2. Die fünf Aufgaben (wörtlich aus dem Plan)

1. „Was realisiert oder testet diese Anforderung?" (Trace-Sicht)
2. „Was hat sich seit Baseline X an diesem Artefakt geändert?" (Version/Diff)
3. „Wer hat wann was kommentiert, und was ist offen?" (Kommentare)
4. „Wo sitzt dieses Artefakt in der Ableitungskette?" (Spine)
5. „Springe zum verknüpften Artefakt und zurück." (Navigation)

Typ-Gruppen für die Pfadanalyse (Begründung in Task 2, Abschnitt 2):

- **Gruppe A — Spine, TracePanel ausgeblendet:** Requirement, StakeholderNeed, Risk, ADR, Issue, TestCase, Architecture, Goal.
- **Gruppe B — keine Spine, TracePanel sichtbar:** Glossary, ICD, Diagram.
- **Sonderfall:** MainGoal (keine Spine, TracePanel ausgeblendet → gar keine Trace-Ansicht; `GoalsPage.tsx:26-32,383`).

---

## 3. Ist-Pfade je Aufgabe

### 3.1 Aufgabe 1 — „Was realisiert oder testet diese Anforderung?"

**Gruppe A (Requirement, exemplarisch).** Die Spine steht oben im Detailbereich (`RequirementEditors.tsx:784-790`). Eine Station sammelt nur Artefakte **ihres eigenen Typs**; die eigene Station enthält daher höchstens gleichartige Artefakte (z. B. andere Requirements), nie die Architektur- oder Test-Links des geöffneten Artefakts (`useDerivationChain.ts:328,355-367`). Ohne gleichartige Nachbarn ist die eigene Station deaktiviert (`TraceSpine.tsx:151-155`). Die Antwort liegt deshalb in der **fremden** Station:

| Teilschritt | Klicks | Scroll | Kontextverlust | Wartezeit |
|---|---|---|---|---|
| „Was realisiert das?" → Klick auf Station „Architektur" | 1 | 0 | — | 0 (Kette beim Seitenaufbau geladen) |
| Panel listet die realisierenden Elemente | 0 | 0 | Station „Architektur" ist jetzt offen | — |
| „Was testet das?" → Klick auf `V·n` der **eigenen** Station (Tests werden dem geöffneten Artefakt zugeordnet, `useDerivationChain.ts:378-381`) | 1 | 0 | **Die Liste „realisiert" schließt sich** (nur ein offenes Panel, `TraceSpine.tsx:81-83,165-171,243-250`) | 0 |
| Zurück zu „realisiert" | +1 | 0 | Liste „tests" schließt sich | 0 |
| Tests einer **anderen** Station (z. B. Architecture) ansehen | +1 | 0 | vorherige Liste weg | 0 |

**Ergebnis:** 2 Klicks für beide Antworten, 3+ beim Hin- und Herschalten; **kein** Kontextverlust über Navigation, aber **wechselseitiger Ausschluss** der beiden Listen. Fehlt die Architektur-Station ganz (keine Links), rendert die Spine sie gar nicht — „nichts realisiert das" ist damit nicht als Aussage sichtbar (`TraceSpine.tsx:211-221` zeigt „keine Abdeckung" nur für *vorhandene* Stationen).

**Gruppe A, übrige Typen.** Das `V·n`-Badge wird ausschließlich für Stationen vom Typ Requirement und Architecture gerendert (`TraceSpine.tsx:225-255`). Für Risk, ADR, Issue, TestCase, StakeholderNeed und Goal existiert die Verifikationsliste im Datenmodell (sie wird jeder Station zugeordnet, `useDerivationChain.ts:382-395`), aber **kein Control zeigt sie**. Ersatz: das CRUD-Panel `TraceLinkPanel` unterhalb des Formulars (`RiskEditors.tsx:230`, `AdrEditors.tsx:371`, `IssueEditors.tsx:232`, `TestCaseEditors.tsx:359`), gruppiert nach Richtung („Incoming"/„Outgoing"), nicht nach Verifikation (`TraceLinkPanel.tsx:277-323`).

| Teilschritt (Risk) | Klicks | Scroll | Kontextverlust | Wartezeit |
|---|---|---|---|---|
| „Was realisiert das?" → Station „Architektur"/„Requirement" | 1 | 0 | — | 0 |
| „Was testet das?" → es gibt kein Badge | — | — | — | — |
| Ersatz: zu `TraceLinkPanel` unter dem Formular scrollen, Zeilen nach Typ-Badge `verifies` absuchen | 0 | 1 (bis Formularende) | Ort wechselt (Spine → Fläche unter dem Formular) | 1 (Links-Request) |

**Gruppe B (Glossary, ICD, Diagram).** Kein Spine; das TracePanel ist das dritte von vier gestapelten Panels in einer Scrollbox (`RightSidebar.tsx:443-460` · `RightSidebar.module.css:76-86`).

| Teilschritt | Klicks | Scroll | Kontextverlust | Wartezeit |
|---|---|---|---|---|
| Inspector aufklappen | 1 | 0 | — | 1 (Version) + 2 (Diff) + 1 (Trace) + 1 (Kommentare) + 1 (Provenienz) |
| Zu „Trace" scrollen (unter Version + Diff) | 0 | 1 | Versionsliste aus dem Blick | — |
| Link-Typ-Chips prüfen (Katalog kann ~20 Typen umfassen), ggf. filtern | 0–k | 0 | — | — |

Bei **ICD** ist die Antwort zusätzlich doppelt vorhanden (`IcdLinkedElements` und TracePanel, `IcdDetailPane.tsx:231-235,249-253`), bei **Glossary** steht die Shell unter der Überschrift „Verwendungen" (`GlossaryDetailPanel.tsx:79-102`) — dieselbe Information, zwei Orte, unterschiedliche Beschriftung.

---

### 3.2 Aufgabe 2 — „Was hat sich seit Baseline X geändert?"

| Teilschritt | Klicks | Scroll | Kontextverlust | Wartezeit |
|---|---|---|---|---|
| Inspector aufklappen (bei <1600 px) | 1 | 0 | — | 3 (Version 1 · Diff 2) |
| Version des Artefakts finden (Liste im obersten Panel) | 0 | 0 | — | — |
| Zeilen-Menü „⋯" der Startversion öffnen | 1 | 0 | — | — |
| „Compare to current" wählen | 1 | 0 | — | 1 (Diff-Request) |
| Ergebnis lesen: das Diff rendert **unter** der Versionsliste | 0 | 1 | **Welche zwei Versionen verglichen werden, steht nur im Diff-Panel**; die Versionsliste markiert die Auswahl nicht (`VersionPanel.tsx:102-120` erhält `diffLeft/diffRight` nicht) | — |

**Minimum: 3 Klicks + 1 Scroll.** Der Vergleich ist immer „gewählte Version → aktuelle" (`RightSidebar.tsx:193-197`); ein beliebiges Paar ist über die UI nicht wählbar.

**Der Baseline-Bezug fehlt vollständig.** `baselines` wird von keinem Aufrufer übergeben (`RightSidebar.tsx:445-451` · `VersionPanel.tsx:112-120`), die Chip-Renderer sind toter Code (`VersionPanel.tsx:200-202,271`, i18n-Keys `sidebar.version.baselineChip`). Damit ist „**seit Baseline X**" nicht beantwortbar, ohne die Route zu verlassen:

| Workaround | Klicks | Kontextverlust | Wartezeit |
|---|---|---|---|
| `/baselines` öffnen, Baseline suchen, gepinnte Version ablesen, zurück zum Artefakt, dort dieselbe Version im Menü wählen | ≥6 + 2 Navigationen | Baseline-Name, Version und Artefakt müssen im Kopf behalten werden | 2 zusätzliche Seitenaufbauten |

Zusatz: Die Live-Region, die den Vergleichsbereich ansagt, sitzt im DiffPanel (`DiffPanel.tsx:190-206`) — also unterhalb der Stelle, an der der Nutzer gerade geklickt hat; die Ansage ist für Sehende nicht wahrnehmbar und für Screenreader-Nutzer eine Ansage über einen Wechsel, den sie nicht ausgelöst zu haben glauben.

---

### 3.3 Aufgabe 3 — „Wer hat wann was kommentiert, und was ist offen?"

| Teilschritt | Klicks | Scroll | Kontextverlust | Wartezeit |
|---|---|---|---|---|
| Inspector aufklappen | 1 | 0 | — | 1 (Kommentar-Request, schlägt fehl, s. u.) |
| Zu „Comments“ scrollen (letztes von vier Panels, unter Version + Diff + ggf. Trace) | 0 | 1–2 | Versions-/Diff-Kontext weg | — |
| Liste lesen | 0 | 0 | — | — |

**Der Pfad endet in einem Fehler.** `CommentPanel` erwartet die generische **Artifact-PK** (`CommentPanel.tsx:20-25`, Endpoint `/artifacts/<id>/comments/`, `api/comments.ts:56-62`), alle 11 Aufrufer übergeben die **Entity-ID** (`RequirementEditors.tsx:891`, `RiskEditors.tsx:235`, `GoalsPage.tsx:381`, `GlossaryDetailPanel.tsx:85`, `IcdDetailPane.tsx:251`, `DiagramDetailView.tsx:539`, …). Das Backend löst bewusst nicht auf und antwortet 404, genau für diesen Fall dokumentiert (`backend/application/comment_service.py:100-112` · `backend/rest_api/collaboration_views.py:53-62`). Sichtbare Folge: Fehlerbanner „Could not load comments." (`CommentPanel.tsx:36-43,105-109`) — **und der Composer bleibt aktiv** (`CommentPanel.tsx:157-175`), sodass ein Schreibversuch in denselben Fehler läuft.

Zusätzlich, selbst bei funktionierendem Abruf:

- „wann" wird als roher Wire-String gerendert (`<span>{comment.createdAt}</span>`, `CommentPanel.tsx:127`) — kein Datumsformat, keine Lokalisierung.
- „was ist offen?" ist nur über Zeilenstil + fehlenden „Resolve"-Button erkennbar (`CommentPanel.tsx:118-141`); es gibt keinen Zähler, kein Badge, keinen Einstieg außerhalb des Panels.
- Im eingeklappten Zustand zeigt der Streifen keinen Hinweis auf ungelesene/offene Kommentare (`RightSidebar.tsx:314-368`).

---

### 3.4 Aufgabe 4 — „Wo sitzt dieses Artefakt in der Ableitungskette?"

| Gruppe | Pfad | Klicks | Scroll | Kontextverlust | Wartezeit |
|---|---|---|---|---|---|
| A (8 Typen) | Spine oben im Detail; eigene Station mit „◀ hier" markiert (`TraceSpine.tsx:177-190`) | 0 | 0 | — | 2 (Kette) |
| A, nach Bearbeitung eines langen Formulars | Spine ist **im scrollenden Detailbereich** (`RequirementEditors.tsx:778-790`), also weggescrollt | 0 | 1 (zurück nach oben) | Positionsgefühl geht verloren | — |
| A, Architecture | Eine Station pro realer Baumtiefe (`useDerivationChain.ts:19-24`) | 0 | 0 | — | 2 |
| B (Glossary, ICD, Diagram) | Keine Spine, kein Ersatz | **nicht beantwortbar** | — | — | — |
| MainGoal | Keine Spine | **nicht beantwortbar** (fachlich begründet, `GoalsPage.tsx:26-32`) | — | — | — |

Die Antwort ist bei Gruppe A also billig (0 Klicks) — aber sie ist **flüchtig**: sobald der Nutzer im Formular arbeitet, ist die Kette aus dem Blick, und es gibt keinen Slot, der sie festhält (der `spine`-Slot von `SplitView` ist ungenutzt, `SplitView.tsx:109-111`).

---

### 3.5 Aufgabe 5 — „Springe zum verknüpften Artefakt und zurück."

| Teilschritt (Gruppe A) | Klicks | Scroll | Kontextverlust | Wartezeit |
|---|---|---|---|---|
| Station öffnen | 1 | 0 | — | 0 |
| Panel-Eintrag anklicken → Navigation | 1 | 0 | **Ausgangsseite verlassen**; offenes Panel, Scrollposition, Formularzustand weg | 2 (Kette der Zielseite) |
| Zurück (Browser-Back) | 1 | 1 | Seite wieder da, aber **Station ist zu** — Antwort muss neu aufgebaut werden | 2 |
| Station + Eintrag erneut öffnen | 2 | 0 | — | 0 |
| **Runde gesamt** | **5** | 1 | 2 Kontextverluste | 4 Runden |

Erschwerend:

- Einträge können **deaktiviert** sein, ohne Grund: `isOpenable` fällt für „nicht aufgelöst", „lädt noch" und „fehlgeschlagen" auf `false` zusammen (`useDerivationChain.ts:54-61,269-271`), der Button hat dann kein `title` (`TraceSpine.tsx:295-305`). In Architecture sind nur Elemente des lokal geladenen Baums öffenbar (`ArchitectureEditors.tsx:589-594`) — der Rest ist toter Klick.
- Gruppe B: TracePanel-Zeile klicken (`TracePanel.tsx:357-373`) → Navigation; zurück sind Filter-Chips und Scrollposition weg (`deselected` ist lokaler State, `TracePanel.tsx:147-149`).
- Es gibt kein „Peek"/Vorschau, keinen neuen Tab, keinen Breadcrumb zurück zur Station.

---

## 4. Verstöße gegen Nielsens zehn Heuristiken

Nummerierung der Heuristiken: H1 Sichtbarkeit des Systemstatus · H2 Übereinstimmung mit der realen Welt · H3 Nutzerkontrolle und -freiheit · H4 Konsistenz und Standards · H5 Fehlervermeidung · H6 Wiedererkennen statt Erinnern · H7 Flexibilität und Effizienz · H8 Ästhetik und minimalistisches Design · H9 Fehler erkennen und beheben · H10 Hilfe und Dokumentation.

| ID | Aufgabe | Typen | Heuristik | Schwere | Befund | Beleg |
|---|---|---|---|---|---|---|
| **U-01** | 3 | alle 12 | H9, H5, H1 | **4** | Kommentare werden mit der Entity-ID abgerufen, der Endpoint verlangt die Artifact-PK → 404, Fehlerbanner statt Liste; Composer bleibt bedienbar und produziert denselben Fehler. | `CommentPanel.tsx:20-25,36-43,157-175` · `api/comments.ts:56-62` · `backend/application/comment_service.py:100-112` · Aufrufer `RequirementEditors.tsx:891` |
| **U-02** | 2 | alle 12 | H6, H10 | **3** | „Seit Baseline X" ist nicht beantwortbar: keine Baseline-Chips, kein Baseline-Selektor; die gepinnte Version muss auf einer anderen Route nachgeschlagen und im Kopf gehalten werden. | `RightSidebar.tsx:445-451` · `VersionPanel.tsx:112-120,200-202` · `types.ts:110-115` |
| **U-03** | 2 | alle 12 | H1, H6 | 3 | Das Vergleichspaar ist in der Versionsliste nicht markiert; welcher Vergleich läuft, steht nur im Diff-Panel und in dessen Live-Region — unterhalb der Klickstelle. | `VersionPanel.tsx:102-120` (kein `diffLeft/diffRight`) · `RightSidebar.tsx:193-197` · `DiffPanel.tsx:190-206` |
| **U-04** | 1, 3, 5 | alle 12 | H7, H8, H6 | **3** | Vier Panels in **einer** Scrollbox, feste Reihenfolge, keine Tabs/Anker: „Kommentare" ist immer Scrollen an Version + Diff (+ ggf. Trace) vorbei; der eingeklappte Streifen zeigt keine Zähler. | `RightSidebar.tsx:327-336,443-460` · `RightSidebar.module.css:76-86` |
| **U-05** | 1–5 | alle 12 | H7, H1 | 3 | Default **eingeklappt** unter 1600 px: auf 1440/1280 px ist der Inspector beim ersten Besuch unsichtbar; die Funktion muss entdeckt werden, obwohl sie der einzige Ort für Version/Diff/Kommentare ist. | `RightSidebar.tsx:87,110-118` |
| **U-06** | 1 | ICD, Glossary | H4, H8 | 3 | Trace-Information an zwei Orten mit zwei Begriffen: `IcdLinkedElements` + TracePanel; bei Glossary Überschrift „Verwendungen" + TracePanel in derselben Spalte. | `IcdDetailPane.tsx:231-235,249-253` · `GlossaryDetailPanel.tsx:71-102` |
| **U-07** | 1 | Risk, ADR, Issue, TestCase, StakeholderNeed, Goal | H1, H4 | 3 | Verifikationslisten werden geladen, aber nur für Requirement-/Architecture-Stationen gerendert (`V·n`). Für sechs Typen ist die Frage „was testet das?" nicht über die Spine beantwortbar; Ersatz ist ein CRUD-Panel unter dem Formular, gruppiert nach Richtung statt nach Verifikation. | `TraceSpine.tsx:225-255` · `useDerivationChain.ts:382-395` · `TraceLinkPanel.tsx:277-323` |
| **U-08** | 1, 4 | alle mit Spine | H1 | 3 | Fehlende Abdeckung ist nur sichtbar, wenn die Station **existiert**: fehlt z. B. die Architektur-Station ganz, sagt die UI nichts — „nichts realisiert das" sieht aus wie „kein Konzept dafür". | `TraceSpine.tsx:209-221` · `useDerivationChain.ts:328,355-367` |
| **U-09** | 5 | alle | H3, H6 | 3 | Navigation verlässt die Seite vollständig; beim Zurück sind offenes Spine-Panel, Filterchips und Scrollposition weg — die Runde kostet 5 Klicks und 2 Kontextverluste. | `TraceSpine.tsx:81-83` · `TracePanel.tsx:147-149,357-373` |
| **U-10** | — | alle | H1, H4 | 2 | „Anheften" ist ein toter Schalter: `pinned` ändert nur `aria-pressed` und die Farbe, keine Layout-/Scroll-/Mount-Entscheidung. | `RightSidebar.tsx:153,160,381-395` |
| **U-11** | 3, 4 | alle | H2, H4 | 2 | Rohwerte in Nutzertexten: `aria-label` „Inspector for stakeholderNeed" (kind unübersetzt), Kommentar-Zeitstempel als Wire-String, DE-Locale mit ASCII-Umlauten („Testfaelle"). | `RightSidebar.tsx:434` · `en.json:2230` · `CommentPanel.tsx:127` · `de.json:2707-2708` |
| **U-12** | — | alle | H4 | 2 | Landmark-Muster inkonsistent: drei Panels `role="region"` + statische `aria-labelledby`-IDs, Kommentare ohne Region; bei mehr als einem Inspector wären die IDs doppelt. | `VersionPanel.tsx:397-401` · `DiffPanel.tsx:172-178` · `TracePanel.tsx:431-436` · `CommentPanel.tsx:97-102` |
| **U-13** | 5 | alle mit Spine | H9, H1 | 2 | Deaktivierte Kettenglieder erklären nicht, warum: drei verschiedene Ursachen (nicht aufgelöst / lädt / fehlgeschlagen) fallen auf `false` zusammen, der Button trägt keinen `title`. | `useDerivationChain.ts:54-61,269-271` · `TraceSpine.tsx:295-305` |
| **U-14** | 3, 5 | alle | H7 | 2 | Tastaturweg: die `<aside>` steht im DOM **nach** dem gesamten Detailformular; es gibt keinen Skip-Link und kein Kürzel zu den Panels — bei langen Formularen sind es Dutzende Tab-Schritte bis „Comments". | `RequirementEditors.tsx:778-894` (DOM-Reihenfolge) · `RightSidebar.tsx:429-465` |
| **U-15** | 1, 3 | Glossary | H4, H2 | 3 | Die Shell ist bei Glossary **keine Seitenleiste**, sondern ein Block unter „Verwendungen" in der Detailspalte; Version, Diff und Kommentare erscheinen damit unter einer Überschrift, die etwas anderes benennt. | `GlossaryDetailPanel.tsx:71-102` · `GlossaryView.module.css:211-215` |
| **U-16** | 1 | alle mit Spine | H1 | 2 | Der Verifikationszähler `V·n` ist laut Code-Doku eine **Untergrenze** (nicht erreichbare Tests werden nicht mitgezählt), wird aber als exakte Zahl dargestellt. | `useDerivationChain.ts:30-38` |
| **U-17** | 2, 3 | alle | H9 | 2 | Fehlerbehandlung ungleich: Version/Trace haben „Reload", Kommentare nicht; Version hängt die rohe Backend-Meldung an den Text. | `VersionPanel.tsx:240-258` · `TracePanel.tsx:413-424` · `CommentPanel.tsx:105-109` |
| **U-18** | 2, 3 | ICD | H1 | 2 | Bei ICD steht die Shell in einem Grid-Track (`2fr 1fr`); der Resize-Handle ändert nur die Breite innerhalb der Spalte — sichtbare Lücke, keine Spaltenbreite. | `IcdDetailPane.module.css:112-116` · `RightSidebar.tsx:269-271,411-427` |

**Verteilung:** 1 × Schwere 4, 9 × Schwere 3, 8 × Schwere 2, 0 × Schwere 1 (kosmetische Einzelfälle sind in Task 2 als I-15/I-18/I-19 erfasst und hier nicht erneut gezählt).

---

## 5. Ranking: die drei schwersten Probleme

Tie-Break bei gleicher Schwere: (1) macht das Problem eine der fünf gestellten Fragen auf der Produktoberfläche unbeantwortbar, (2) Zahl der betroffenen Aufgaben, (3) Zahl der betroffenen Artefakttypen.

### Platz 1 — U-01: Kommentare sind für alle Artefakttypen nicht abrufbar (Schwere 4)

Der Inspector übergibt die Entity-ID an einen Endpoint, der die generische Artifact-PK verlangt; das Backend antwortet bewusst mit 404 statt mit „leer". Aufgabe 3 („wer hat wann was kommentiert, und was ist offen?") ist damit **für 12 von 12 Typen blockiert**, und der Composer lädt zu einem zweiten Fehlschlag ein.
**Beleg:** `CommentPanel.tsx:20-25,36-43,157-175` · `api/comments.ts:56-62` · `backend/application/comment_service.py:100-112` · `backend/rest_api/collaboration_views.py:53-62`.
**Ist-Wert als Messlatte:** 1 Aufklapp-Klick + 1 Scroll, Ergebnis = Fehlerbanner. Ziel für Task 5: 1 Pfad, 0 Fehler, offene Kommentare ohne Scroll erkennbar.

### Platz 2 — U-02: „Seit Baseline X" ist nicht beantwortbar (Schwere 3)

Baseline-Bezüge existieren im Datenmodell (`BaselineSummary`, `baselineIds`), werden aber nie an das VersionPanel gereicht — die Chip-Renderer und die i18n-Texte sind toter Code. Der Nutzer muss die gepinnte Version auf einer anderen Route nachschlagen und im Kopf behalten; der Inspector selbst kennt nur „Version → aktuell".
**Beleg:** `RightSidebar.tsx:445-451` · `VersionPanel.tsx:112-120,200-202,271` · `types.ts:110-115`.
**Ist-Wert:** 3 Klicks + 1 Scroll für ein Diff, ≥6 Klicks + 2 Navigationen für den Baseline-Bezug. Ziel für Task 5: Baseline im Inspector wählbar, ohne die Route zu verlassen.

### Platz 3 — U-04: Vier Panels in einer Scrollbox ohne Tabs oder Anker (Schwere 3)

Die Shell hat keine Informationsarchitektur: feste Reihenfolge, ein `overflow-y: auto`, kein Sprungziel. „Kommentare" liegt immer unter Version + Diff (+ Trace), der eingeklappte Streifen zeigt keine Zähler. Das trifft **alle 12 Typen** und **drei der fünf Aufgaben** (1, 3, 5) und ist die gemeinsame Ursache der meisten Scroll-Kosten in Abschnitt 3.
**Beleg:** `RightSidebar.tsx:327-336,443-460` · `RightSidebar.module.css:76-86`.
**Ist-Wert:** 1 Scroll bis „Trace", 1–2 Scrolls bis „Comments", 0 Direktziele. Ziel für Task 5: je Information ein benannter, direkt erreichbarer Ort.

**Knapp dahinter (nicht im Ranking, aber Messlatte-relevant):** U-05 (Default eingeklappt unter 1600 px — „alle Panels unsichtbar beim ersten Besuch") und U-07 (Verifikation für sechs Typen ohne Bedienelement). Beide folgen aus derselben Shell-Entscheidung wie U-04 bzw. aus der Typ-Matrix und sollten in Task 5 gemeinsam mit dem jeweiligen Platzhalter adressiert werden, nicht als eigene Baustelle.

---

## 6. Was das für Task 5 bedeutet (ohne Lösung zu entwerfen)

1. Jede der drei Messlatten braucht einen **Zielwert**, der gegen den Ist-Wert oben prüfbar ist (Klicks, Scrolls, „beantwortbar ja/nein").
2. Die Typ-Matrix aus Task 2, Abschnitt 3 ist die Prüfregel gegen „ein einheitlicher Entwurf bricht Typen ohne Spine": Glossary/ICD/Diagram und MainGoal müssen im Entwurf ein definiertes Verhalten haben, nicht implizit das der Gruppe A erben.
3. Die Id-Space-Frage (U-01, Task 2 I-06/I-07) ist eine **Vorab-Entscheidung**, keine Designfrage: ein Ort je Information setzt einen Ort je Identität voraus.
4. U-09 (Navigation und Rückkehr) ist die einzige Aufgabe, bei der die Spine und der Inspector zusammenwirken — der Entwurf muss „Spine am Rand, Panel rechts" als ein System beschreiben, nicht als zwei Bauteile.

---

## 7. Grenzen dieser Prüfung

- Keine Laufzeitmessung, keine Screenshots, kein Stack (Task 2, Abschnitt 0). Klickzahlen sind aus dem Code-Pfad abgeleitet, nicht beobachtet; sie sind als **Untergrenze** zu lesen (Tippen, Suchen, Fehlversuche kommen hinzu).
- U-01 ist aus Frontend-Aufruf und Backend-Vertrag abgeleitet, nicht im Browser reproduziert. Bestätigung mit einem echten Artefakt steht aus und ist Voraussetzung für die Priorisierung in Task 5.
- Die Prüfung deckt keine visuellen Aspekte (Kontrast, Abstände) ab; Token-/Kontrastbefunde stehen in Task 2 (I-16, I-17) und gehören in die a11y-Prüfung (Task 6).
- Nielsen-Schwere ist ein Expertenurteil ohne Nutzerdaten; sie ordnet die Probleme, sie ersetzt keine Messung mit Anwendern.
