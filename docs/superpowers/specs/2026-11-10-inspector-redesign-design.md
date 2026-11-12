# Artefakt-Inspector — Neukonzept (Design und Spec)

> **Status:** Draft, Gate für Task 6 (Freigabe durch Daniel). Kein Produktivcode.
> **Auftrag:** Task 5 aus [`../plans/2026-11-10-phase-b2-inspector-concept.md`](../plans/2026-11-10-phase-b2-inspector-concept.md).
> **Eingaben:** [Ist-Analyse](../../analysis/2026-11-inspector-ist.md) (I-01 … I-21),
> [Usability-Prüfung](../../analysis/2026-11-inspector-usability.md) (U-01 … U-18),
> [Best-Practice-Recherche](../../analysis/2026-11-inspector-best-practice.md) (Q1 … Q15, M1 … M6),
> [`docs/UI_KONZEPT.md`](../../UI_KONZEPT.md) §3.4, §5, §6, §7.
> **Mockups:** [`inspector-redesign-mockups/`](inspector-redesign-mockups/README.md) — Requirements (voll),
> Glossary (ohne Spine), Schmalansicht 768 px.
> **Sprache:** Deutsch (interne Doku). Code-/Datei-Belege in Originalschreibweise, Pfade relativ zur Repo-Wurzel.

**Scope:** Neuentwurf der Darstellung, Struktur und Interaktion des bestehenden Artefakt-Inspectors
(`frontend/src/components/shared/ArtifactInspector/`, Shell `RightSidebar.tsx`) und seines Verhältnisses zur
`TraceSpine` (`frontend/src/components/shared/TraceSpine/`). **Nicht** Scope: Backend-Fachlogik (außer den in
§11 benannten, notwendigen Ergänzungen), Artefakt-Formulare, Listen, Navigation, Rechte, Export.

---

## 0. Messlage und Belegkonvention

Diese Spec erbt die Messlage von Task 2 und Task 3. Sie erfindet keine Messwerte.

| Aussage | Grundlage | Belastbarkeit |
|---|---|---|
| Klick-/Scroll-/Runden-Zahlen im Ist | Code-Pfad, [Usability §3](../../analysis/2026-11-inspector-usability.md) | **Untergrenze** — Tippen, Suchen, Fehlversuche kommen hinzu |
| Bildschirmfotos | keine — am 2026-11-11 lief kein Stack ([Ist §0](../../analysis/2026-11-inspector-ist.md)) | **nicht vorhanden** |
| Breitenverhalten 768 / 1024 / 1440 px | CSS/JS-Arithmetik + Code; in §4.4 nachgerechnet | **abgeleitet, nicht gerendert** — visuell nachzuprüfen |
| Nielsen-Schwere | Expertenurteil, [Usability §4](../../analysis/2026-11-inspector-usability.md) | Ordnung, keine Nutzerdaten |
| Kontrast | Token-Paare + `theme-contrast.test.ts` | Token-Ebene geprüft, Inspector-Paare erst nach Umsetzung |

**Belegkonvention:** Jeder Ist-Befund trägt `datei:zeile` oder eine Referenz auf I-/U-/Q-Nummern.
Wo ein Beleg am heutigen `origin/main` abweichende Zeilennummern hat, steht die geprüfte Fundstelle.
**Neue Befunde** dieser Spec (über Task 2/3 hinaus) sind als **N-xx** markiert und einzeln belegt.

**Heuristiken (H1–H10):** H1 Sichtbarkeit des Systemstatus · H2 Übereinstimmung mit der realen Welt ·
H3 Nutzerkontrolle und -freiheit · H4 Konsistenz und Standards · H5 Fehlervermeidung · H6 Wiedererkennen
statt Erinnern · H7 Flexibilität und Effizienz · H8 Ästhetik und minimalistisches Design · H9 Fehler
erkennen und beheben · H10 Hilfe und Dokumentation (Nielsen; Nummerierung wie
[Usability §4](../../analysis/2026-11-inspector-usability.md)).

### 0.1 Die Ist-Befunde I-01 … I-21 im Überblick

Die Spec zitiert im Text I-Nummern. Damit jede Nummer ohne Seitensprung nachschlagbar ist, steht hier
eine Zeile je Befund; die vollständige Fassung mit Belegspannen und Schwere steht in der
[Ist-Analyse](../../analysis/2026-11-inspector-ist.md).

| I-ID | Kurzfassung | Beleg | Auflösung in dieser Spec |
|---|---|---|---|
| I-01 | Glossary rendert die Shell **inline** als Block unter „Verwendungen", nicht als rechte Spalte | `GlossaryDetailPanel.tsx:71-102` · `GlossaryView.module.css:211-215,248-250` | §2.4, §11 D8, §8 M5 |
| I-02 | ICD legt die Shell in ein CSS-Grid (`2fr 1fr`); `width`/`flex-basis` und Resize wirken nur *innerhalb* des Grid-Tracks | `IcdDetailPane.module.css:112-116` | §8 M6 |
| I-03 | Trace-Links bei ICD doppelt (`IcdLinkedElements` **und** `TracePanel`) | `IcdDetailPane.tsx:231-235,249-253` | §2.4 |
| I-04 | `hideTraceLinks` ist ein Routen-Schalter, kein Typ-Merkmal; für 6 Typen fehlt eine Read-Ansicht | `RightSidebar.tsx:49-57,458` · `TraceSpine.tsx:225-255` | §2.3, §3 |
| I-05 | Das `baselines`-Prop übergibt kein Aufrufer → Baseline-Chips sind toter Pfad (vertieft in N-01) | `VersionPanel.tsx:112-120,200-202` · `types.ts:110-115` | §11 D6 |
| I-06 | Id-Space-Bruch: `CommentPanel` erwartet die generische Artefakt-PK, alle Aufrufer übergeben die Entity-ID | `CommentPanel.tsx:20-25` · `backend/application/comment_service.py:100-112` | §11 D5 |
| I-07 | Derselbe Bruch ist im Inspector inkonsistent gelöst: eine Shell, drei ID-Verträge | `TracePanel.tsx:163-167` · `InterviewProvenanceBadge.tsx:6-13` | §11 D5 |
| I-08 | „Anheften" ohne Wirkung: `pinned` steuert nur `aria-pressed` und Farbe | `RightSidebar.tsx:153,160,381-395` | §11 D7 |
| I-09 | Einklapp-Default 1600 px für alle Typen, unabhängig vom Platz der Route | `RightSidebar.tsx:87,110-118` | §4.2 |
| I-10 | Kein Tab-/Anker-Konzept; `sidebar.inspector.refresh`/`skeletonLoading` sind definiert, aber ungenutzt | `RightSidebar.tsx:327-336,443-460` | §2.1, §4.3 |
| I-11 | `aria-label` mit rohem `kind` („Inspector for stakeholderNeed") | `RightSidebar.tsx:434` | §7, SC 4.1.2 |
| I-12 | Landmark-/ID-Inkonsistenz: drei `role="region"` mit statischem Label, globale IDs | `VersionPanel.tsx:397-401` · `DiffPanel.tsx:172-178` | §7, SC 1.3.1 |
| I-13 | **Spine-Slot ungenutzt:** `SplitView` bietet einen dedizierten `spine`-Slot (`SplitView.tsx:109-111,332`), **kein Konsument nutzt ihn**; die Spine liegt bei 8 Routen im scrollenden Detailbereich und scrollt mit dem Formular weg | `SplitView.tsx:109-111,332` · `RequirementEditors.tsx:778-790` | §2.3, §4.1; §8 M1 setzt die Spine in den `SplitView`-`spine`-Slot |
| I-14 | Zwei Kinds auf einer Route (Goals) mit getrennten Persistenz-Slots → Zustand springt | `GoalsPage.tsx:332-352,379-384` | §5.4 |
| I-15 | `diff-unsupported` ist unerreichbar (alle 12 Kinds sind diff-fähig) | `types.ts:128-144` · `DiffPanel.tsx:115-119` | §3, §8 M8 |
| I-16 | Elffach literales `white` in Inspector-CSS statt `--color-on-primary` (im Bauhaus-Theme navy) | `RightSidebar.module.css:67,163` · `VersionPanel.module.css:236,245-246,255` | §6.2, §8 M8 |
| I-17 | Geometrie gemischt: vier Radius-Tokens, Chip-Höhen 22/44, Resize-Hitbox 24, Höhen-Literale | `RightSidebar.module.css:43-49,144-149` · `TracePanel.module.css:143,208-209` | §6.1, §6.5 |
| I-18 | **Stale Kommentar:** ICD behauptet „`/versions/` endpoint is not exposed yet", obwohl `VERSIONS_FETCHERS` `icd` enthält | `IcdDetailPane.tsx:78-82` vs. `VersionPanel.tsx:64-79` | §8 M8 (Kommentar löschen, nicht mitwandern) |
| I-19 | **DE-Locale mit ASCII-Umlauten** in Nutzertexten: „Verknuepfte Testfaelle anzeigen", „{{count}} Testfaelle" | `i18n/locales/de.json:2707-2708` · Fallback `TraceSpine.tsx:240` | §5.5 (i18n-Tabelle), §8 M8 (DE-Strings korrigieren) |
| I-20 | Eingeklappter Streifen: nur der Expand-Button trägt ein Testid; Emoji-Glyphen `⏱`/`≅` | `RightSidebar.tsx:337-365` | §8.3, §6.2 |
| I-21 | `mainGoal` hat bewusst keine Trace-Ansicht (fachlich begründet) | `GoalsPage.tsx:26-32,383` | §3 (Ausnahme im Typ-Vertrag) |

### 0.2 N-01 (neu): Der Baseline-Bezug ist nicht nur nicht verdrahtet — er ist nicht abfragbar

Task 2 (I-05) und Task 3 (U-02) beschreiben den fehlenden Baseline-Bezug als „Prop wird nicht übergeben".
Die Prüfung am Backend zeigt eine tiefere Ursache:

- `frontend/src/api/baselines.ts:258-268` — `baselinesApi.list()` akzeptiert **nur** `workspace_id` und `tag`.
- `backend/rest_api/views.py:5959-5996` — `BaselineViewSet.list()` liest **nur** `workspace_id` und `tag`
  (`list_baselines(workspace_id=…, ctx=…, tag=…)`). Ein `artifact_id`-Filter existiert nicht.
- `frontend/src/components/shared/ArtifactInspector/types.ts:47-51` behauptet dagegen, `baselineIds` werde
  „from `GET /api/v1/baselines/?artifact_id=<id>`" aufgelöst — dieser Aufruf ist so nicht möglich.
- `backend/rest_api/serializers.py:2208-2215` — `BaselineSummarySerializer.version` ist die **Lock-Version**
  (`LOCK_VERSION_HELP_TEXT`), **nicht** die gepinnte Artefakt-Version. `pinnedVersion` lässt sich aus der
  Baseline-Liste also gar nicht ableiten.
- Die gepinnte Version eines Artefakts steckt in `Baseline.entries` (`BaselineDeltaEntry.version`,
  `frontend/src/api/baselines.ts:36-44`), die **nur** die Detail-Antwort liefert (`BaselineSummarySerializer`
  lässt `entries` bewusst weg, `backend/rest_api/serializers.py:2181-2202`).

**Konsequenz:** „Diff gegen Baseline X" im Inspector braucht **eine** neue Backend-Fähigkeit. Das ist keine
Verdrahtungsarbeit. Siehe §11 D6.

---

## 1. Ziel und Messlatte

Der Entwurf wird an den drei schwersten Problemen aus Task 3 gemessen, nicht an Geschmack.
Die Reihenfolge und die Ist-Werte sind wörtlich aus
[Usability §5](../../analysis/2026-11-inspector-usability.md) übernommen.

### 1.1 Die drei Messlatten

**M-1 — Kommentare sind für alle Typen nicht abrufbar (U-01, Schwere 4).**

| | |
|---|---|
| **Ist** | 1 Klick (Inspector aufklappen) + 1–2 Scrolls bis „Comments"; Ergebnis = Fehlerbanner „Could not load comments." Composer bleibt bedienbar und läuft in denselben Fehler. Belege: `CommentPanel.tsx:20-24,36-43,157-175` · `api/comments.ts:57-62` · `backend/application/comment_service.py:100-113` |
| **Zielwert** | **0 Fehler** (ein Kommentar-Request, HTTP 200), **0 Scrolls** bis zur ersten Kommentarzeile, **1 Klick** oder **1 Kürzel** bis zum Kommentar-Reiter. Anzahl **offener** Kommentare ist ohne Öffnen des Reiters ablesbar (Reiter-Label und Rail-Zähler). |
| **Prüfung** | E2E: Artefakt öffnen → Kommentar-Reiter → Liste sichtbar, offene Anzahl im Reiter-Label; Netzwerk: genau ein `GET /artifacts/<pk>/comments/`, Status 200. |

**M-2 — „Seit Baseline X" ist nicht beantwortbar (U-02, Schwere 3).**

| | |
|---|---|
| **Ist** | 3 Klicks + 1 Scroll für ein Diff (Version → Zeilenmenü → „Compare to current"); **≥ 6 Klicks + 2 Seitenwechsel** für den Baseline-Bezug. Belege: `RightSidebar.tsx:445-458` · `VersionPanel.tsx:112-120,200-202` · `types.ts:110-115` · neu: N-01 |
| **Zielwert** | **1 Klick** bis der Vergleich gegen die zuletzt gewählte Basis sichtbar ist (Reiter „Diff"), **2 weitere Interaktionen** zum Wechsel der Basis, **0 Seitenwechsel**, **0 Scrolls**; das Vergleichspaar ist an genau einer Stelle benannt (§2.2). |
| **Prüfung** | E2E: Diff-Reiter → Paar-Zeile „Basis … → Arbeitsstand vN" sichtbar; Basiswechsel aktualisiert Paar-Zeile und Diff ohne Navigation. |
| **Vorbehalt** | Zielwert gilt nur, wenn §11 D6 die Backend-Fähigkeit freigibt. Ohne D6 bleibt M-2 **nicht erreichbar**; dann gilt der Ersatz-Zielwert: Version→Version-Vergleich in **2 Klicks, 0 Scrolls** (heute 3 Klicks + 1 Scroll). |

**M-3 — Vier Panels in einer Scrollbox ohne Tabs oder Anker (U-04, Schwere 3).**

| | |
|---|---|
| **Ist** | 1 Scroll bis „Trace", 1–2 Scrolls bis „Comments", **0 Direktziele**; eine Scrollbox für alle Panels; keine Zähler im eingeklappten Streifen. Belege: `RightSidebar.tsx:327-336,443-460` · `RightSidebar.module.css:76-86` |
| **Zielwert** | Je Bereich **ein benanntes, direkt erreichbares Ziel** (Reiter): **0 Scrolls** bis zum Bereichseinstieg, **1 Klick** oder **1 Kürzel**. Vier Bereiche, vier Ziele. Bereichszustand ist über die URL reproduzierbar (`?inspector=links`). |
| **Prüfung** | E2E: jeder Reiter ist per Klick und per `Alt+I` + Pfeiltasten **fokussierbar** und mit `Enter`/`Space` aktivierbar (§5.1, manuelle Aktivierung); Scrollposition des Panel-Bereichs ist beim Reiterwechsel 0. |

### 1.2 Sekundäre Ziele (adressiert, aber nicht Messlatte)

Task 3 empfiehlt ausdrücklich, U-05 und U-07 „gemeinsam mit dem jeweiligen Platzhalter" zu lösen, nicht als
eigene Baustelle ([Usability §5](../../analysis/2026-11-inspector-usability.md), letzter Absatz):

- **U-05** (Default eingeklappt unter 1600 px): Der Inspector ist ab 1280 px standardmäßig **offen**
  (R2/R3, §4.2). Im Rail-Zustand (R4) zeigt der Streifen **Zähler** statt nur Glyphen — die Funktion ist
  damit auch eingeklappt sichtbar (H1).
- **U-07** (Verifikation für sechs Typen ohne Bedienelement): Das Verifikations-Badge erscheint an **jeder**
  Station, nicht nur an Requirement/Architecture (§2.3, §8.4).
- **U-09** (Navigation verliert Kontext): Reiter, Filter und Scrollposition werden pro Artefakt und Route
  gehalten; Rückkehr stellt sie wieder her (§5.4).
- **U-06** (Trace doppelt bei ICD/Glossary): Die zweite Darstellung entfällt (§2.4).

### 1.3 Abgrenzung der Messlatte

M-1 bis M-3 sind **Aufwandsmaße** (Klicks, Scrolls, Runden, „beantwortbar ja/nein"), keine Zeit- oder
Zufriedenheitsmaße. Es gibt keine Nutzerstudie; die Zielwerte sind Soll-Grenzen für die Umsetzung, keine
gemessene Verbesserung. Ein Entwurf, der eine Messlatte nicht senkt, ist nach dem Review Focus des Plans
abzulehnen.

---

## 2. Informationsarchitektur

### 2.1 Der Grundschnitt: Rail → Panel → Reiter

Die Fläche beantwortet weiterhin **eine** Frage (UI_KONZEPT §3.4), aber nicht mehr vier gleichzeitig.
Der Inspector hat **genau vier Bereiche**, jeder mit **einem** Besitzer:

```
Inspector
├─ Kopfzeile      „Inspector" + Schließen        (eine Aktion, keine Inhalte)
├─ Reiterleiste   Version · Diff · Links · Kommentare     ← je ein Direktziel (M-3)
└─ Bereich        genau ein Reiter ist sichtbar
```

- **Kein fünfter Bereich.** Provenienz ist die erste Zeile des Reiters „Version"; Status und Identität
  gehören **nicht** in den Inspector (§2.2).
- **Höchstens zwei Offenbarungsebenen** (Q1): Reiter → Zeile/Detailzeile. Ein Dialog aus dem Inspector
  heraus ist die dritte Ebene und nur für destruktive Bestätigungen erlaubt (bestehendes `ConfirmDialog`).
- **Bauform:** Der Inspector ist ein **Panel**, kein Drawer im engeren Sinn: Version, Links und Kommentare
  sind Dauerinhalt neben dem Inhalt, nicht transiente Nebeninformation (Q5). Auf schmalen Breiten wechselt
  er in den **Overlay-Modus** desselben Panels (Q3), nicht in ein anderes Bauteil. Begriffe dieser Spec:
  **Panel** = inline, **Rail** = eingeklappt, **Sheet** = Overlay.
- **Ein DOM-Knoten für Rail und Sheet.** Rail und Sheet sind **dasselbe** Bauteil in zwei Zuständen; es gibt
  keine zweite Montagestelle. Im Sheet-Zustand ist der **Rail-Inhalt nicht gerendert** (nicht bloß verdeckt
  oder per `visibility`/`display` unsichtbar geschaltet), im Rail-Zustand ist der Sheet-Inhalt nicht
  gerendert. Damit existiert zu keinem Zeitpunkt ein zweiter, unsichtbarer Satz von Zählern, Reitern oder
  Schaltflächen im Accessibility-Tree (WCAG 1.3.1, 4.1.2; H4).

### 2.2 Ein Ort je Information

Regel: **Eine Information hat genau eine lesende Fundstelle.** Markierungen *innerhalb* einer Liste
(„Aktuell", „hier", Suspect-Punkt) sind kein zweiter Ort — sie sind Zustand der Liste.

| Information | Einziger Ort | Was dort steht | Erscheint **nicht** in |
|---|---|---|---|
| **Identität** (Artefakt-ID, Typkürzel) | Artefaktkopf der Route (`<ArtifactId>`, UI_KONZEPT §3.1, §12.4) | ID in `--font-mono`, Typkürzel | Inspector (kein ID-Kopf, keine Typzeile) |
| **Workflow-Status** | Artefaktkopf (`<StatusBadge>`, UI_KONZEPT §8.2) | genau ein Badge | Inspector, Reiter, Zeilen |
| **Aktuelle Version** | Artefaktkopf (`<VersionBadge>`) **und** als Zeilenmarkierung „Aktuell" im Reiter „Version" | Badge im Kopf; die Zeile ist die Liste selbst | Diff-Reiter (dort nur als rechte Seite des Paars) |
| **Versionsverlauf** (Labels, Zeit, Baseline-Pins, Herkunft) | Reiter **Version** | Provenienz-Zeile, dann Zeilen absteigend | überall sonst |
| **Diff** (Feldänderungen) | Reiter **Diff** | Legende, Paar-Zeile, Feldblöcke | Artefaktkörper, Version-Reiter |
| **Vergleichspaar** | Reiter **Diff**, genau eine Paar-Zeile („Basis … → Arbeitsstand vN") | links + rechts + Wechsel-Affordanz | Version-Reiter (markiert keine Auswahl), Live-Region allein |
| **Ableitungskette** (Position, Richtung, Abdeckungslücken, Verifikationszähler) | **Trace-Spine** (außerhalb des Inspectors, §2.3) | Stationen + `↑`/`↓` + `⚠` + `V·n` | Links-Reiter (nur Zusammenfassung, §2.3) |
| **Link-Inventar** (alle Typen, Richtung, Suspect, Anlegen/Löschen) | Reiter **Links** | Zeilen je Link + Filter + „Verknüpfung anlegen" | Artefaktkörper, ICD-Detail, Glossary-Detail |
| **Kommentare** (Autor, Zeit, Text, offen/erledigt) | Reiter **Kommentare** | Liste + „offen: n" + Composer | Kopfzeile, Rail (dort nur die Zahl) |
| **Herkunft/Provenienz** (Interview) | Erste Zeile im Reiter **Version** | Badge + Interview-ID | Kopfzeile des Artefakts |
| **Zahlen im zugeklappten Zustand** | **Rail** | offene Kommentare, Links gesamt, Versionen | nirgends sonst als Badge am Artefakt |

**Warum Status und ID aus dem Inspector herausfallen:** Sie sind Identität, nicht Historie. Heute zeigt der
Inspector weder Status noch ID (der Kopf ist Sache der Route) — die Regel hält das so und verhindert, dass
eine spätere „Inspector-Kopfzeile" sie ein zweites Mal einführt (H4 Konsistenz).
**Folge für die Migration:** Wo der Artefaktkopf heute keinen Status zeigt (UI_KONZEPT §8.2: „nur in einem
von sieben Detail-Köpfen"), ist das ein **Kopffehler der Route**, kein Inspector-Feature (§8.4).

### 2.3 Verhältnis Trace-Spine ↔ Reiter „Links"

Das ist der Kern des Review-Fokus „doppelte Darstellung" und der einzige Punkt, an dem Spine und Inspector
zusammenwirken ([Usability §6.4](../../analysis/2026-11-inspector-usability.md)).

**Arbeitsteilung nach Frage, nicht nach Objekt** (Q6, Q9):

| | Trace-Spine | Reiter „Links" |
|---|---|---|
| **Frage** | *Wo stehe ich, und was fehlt?* (UI_KONZEPT §3.4) | *Was hängt an diesem Artefakt, und wie verwalte ich es?* |
| **Inhalt** | Stationen der Ableitungskette, Richtung, Abdeckungslücke, Verifikationszähler | vollständiges Inventar **aller** Link-Typen mit Richtung, Suspect, Aktion |
| **Darstellung** | Aggregat: Station + Zähler + Glyph | Zeilen: Typ-Pille, ID, Titel, Richtung, Suspect |
| **Aktion** | Station öffnen (temporär), `V·n` öffnen | anlegen, löschen, filtern, öffnen |
| **Sichtbarkeit** | immer sichtbar, solange ein Artefakt offen ist; scrollt nicht mit | nur bei aktivem Reiter |

**Die Regel gegen Doppelung:**

1. **Ableitungs- und Verifikationslinks** (`derives-from`, `decomposes`, `refines`, `satisfies`, `realizes`,
   `allocated-to`, `verifies`) werden **als Zeilen nur in der Spine** gelesen. Der Reiter „Links" zeigt für
   diese Gruppe **eine Zusammenfassungszeile** („6 Ableitungs- und Verifikationslinks — in der Spine") mit
   einem Sprungziel, **keine** Zeilen. Belege für die Typen: `backend/link_types/builtin.py`.
2. **Alle übrigen Link-Typen** (`mitigates`, `decides`, `references`, `diagram-ref`, tenant-spezifische)
   erscheinen **als Zeilen nur im Reiter „Links"**. Die Spine zeigt sie nicht — sie sind keine Ableitung.
3. **Verifikation ist ein Badge, keine Station** (UI_KONZEPT §5.2). Das Badge erscheint an **jeder**
   Station, deren Verifikationsliste nicht leer ist — nicht nur an Requirement/Architecture
   (`TraceSpine.tsx:225-255` ist heute die Einschränkung, U-07). Die Daten liegen je Station bereits vor
   (`useDerivationChain.ts:378-395`).
4. **Ein Link ist damit an genau einer Stelle als Zeile lesbar.** Die Zusammenfassungszeile ist ein Zähler
   plus Sprung, kein zweiter Eintrag (H6, H8).
5. **Ohne Spine** (Glossary, ICD, Diagram) entfällt die Zusammenfassungszeile; der Reiter „Links" zeigt
   **alle** Typen als Zeilen. Damit erbt kein Typ ohne Spine das Verhalten der Gruppe A (Review Focus
   „Typ-Unterschiede"). `IcdLinkedElements` entfällt (§2.4).

**Warum nicht „Links-Reiter zeigt alles zusätzlich":** Zwei Zeilen für denselben Link kosten Pflege
(Doppelanzeige bei Änderung), Filterlogik an zwei Orten und die Frage „welche ist die Wahrheit?" — genau die
Klasse Fehler, die U-06 heute bei ICD/Glossary erzeugt. Ein Ort je Information ist die billigere Variante
(H4, H8).

### 2.4 Was heute doppelt ist und verschwindet

| Doppelung | Heute | Beleg | Auflösung |
|---|---|---|---|
| Trace-Links bei ICD | `IcdLinkedElements` **und** `TracePanel` | `IcdDetailPane.tsx:231-235,249-253` | `IcdLinkedElements` entfernen; Reiter „Links" ist der einzige Ort (§8 M6) |
| „Verwendungen" bei Glossary | Überschrift „Verwendungen" **und** `TracePanel` in derselben Spalte | `GlossaryDetailPanel.tsx:79-100` | Überschrift entfällt; Reiter „Links" übernimmt, Label bleibt „Verwendungen" (Terminologie-Profil, §8 M5) |
| Verifikationsliste | `V·n` (nur 2 Typen) **und** `TraceLinkPanel` unter dem Formular (6 Typen) | `TraceSpine.tsx:225-255` · `TraceLinkPanel.tsx:277-323` | Badge an allen Stationen; `TraceLinkPanel` bleibt CRUD-Fläche der Route, wird aber nicht mehr als *Lese*ersatz gebraucht (U-07) |
| Vergleichspaar | Diff-Panel **und** Live-Region unterhalb der Klickstelle | `VersionPanel.tsx:102-120` · `DiffPanel.tsx:190-206` | eine Paar-Zeile im Diff-Reiter; **eine** Live-Region für den ganzen Inspector (§5.3) |

---

## 3. Typ-Matrix

Zwölf `ArtifactKind`-Werte (`types.ts:21-33`). Alle zwölf haben Diff und Versionen
(`DIFF_SUPPORTED_KINDS`, `types.ts:128-144`; `VERSIONS_FETCHERS`, `VersionPanel.tsx:66-94`) —
der oft zitierte Typ-Unterschied „Diff ja/nein" existiert im Frontend **nicht** (I-15). Der echte
Typ-Unterschied ist **Spine ja/nein** und **Link-Zeilen ja/nein**.

| `kind` | Spine | Diff | Reiter „Links" | Standardreiter | Besonderheit / Beleg |
|---|---|---|---|---|---|
| `requirement` | ja | ja | Zeilen: sonstige · Zusammenfassung: Ableitung | Version | SplitView; `hideTraceLinks` entfällt (heute `RequirementEditors.tsx:747-752`) |
| `stakeholderNeed` | ja | ja | wie oben | Version | `NeedsEditors.tsx:405` hat `artifact_id` bereits |
| `risk` | ja | ja | wie oben | Version | `RiskEditors.tsx:120` `artifact_id` vorhanden |
| `adr` | ja | ja | wie oben | Version | `AdrEditors.tsx:150` `artifact_id` vorhanden |
| `issue` | ja | ja | wie oben | Version | `IssueEditors.tsx:120` `artifact_id` vorhanden |
| `testCase` | ja | ja | wie oben | Version | `TestCaseEditors.tsx:342,359` nutzt `artifact_id` schon für Links |
| `architecture` | ja | ja | wie oben | Version | Baumtiefe → Stationen je Ebene (`useDerivationChain.ts:19-24`) |
| `goal` | ja | ja | wie oben | Version | zwei Kinds auf einer Route, getrennte Persistenz-Slots (I-14) |
| `mainGoal` | **nein** | ja | **nein** | Version | fachlich begründet: kein `artifact_id`, kein Trace-Graph (`GoalsPage.tsx:26-32`); I-21 |
| `glossary` | **nein** | ja | **alle Typen als Zeilen** | Version | Shell heute inline unter „Verwendungen" (I-01/U-15) |
| `icd` | **nein** | ja | **alle Typen als Zeilen** | Version | Grid-Track `2fr 1fr` (I-02/U-18); Doppelung entfällt (§2.4) |
| `diagram` | **nein** | ja | **alle Typen als Zeilen** | Version | Flex-Pane (`DiagramDetailView.module.css:30-34`) |

**Standardreiter ist für alle Typen „Version".** Begründung: (a) konsistent über alle Typen (H4) — der
Review Focus warnt vor einem Entwurf, der Typen unterschiedlich behandelt; (b) entspricht der heutigen
Panel-Reihenfolge und macht die Migration billiger; (c) „Was ist das?" beantwortet die Detailseite, die
Historie ist die häufigste Inspector-Aufgabe, die heute nicht blockiert ist. Ein typabhängiger Standardreiter
wäre eine zweite Verhaltensregel ohne Nutzenbeleg.
**Ausnahme `mainGoal`:** gleicher Standardreiter, aber ohne Links-Reiter; der Reiter wird nicht gerendert
(nicht deaktiviert), damit die Reiterleiste nicht wie ein Fehler aussieht (H1).

**Rail-Zähler je Typ:** Version (Anzahl), Diff (letzte Änderung vorhanden: ja/nein), Links (Anzahl; bei
`mainGoal` entfällt), Kommentare (**offen**). Kein Zähler ohne Datenquelle — `0` wird als `0` gezeigt, nicht
als leerer Platz.

**Jeder Rail-Zähler ist ein `<button>`** (kein `<span>`): er trägt einen lokalisierten `aria-label`
(„Kommentare, 3 offen"), `aria-controls` auf die Inspector-Fläche und öffnet mit einem Klick das Sheet bzw.
Panel **auf dem zugehörigen Reiter** (§5.1). Die Buchstabenkürzel `V`/`D`/`L`/`K` sind
`aria-hidden="true"` — der Name kommt vollständig aus dem `aria-label`; sonst würde „V 9" vorgelesen
(WCAG 4.1.2, heute `RightSidebar.tsx:344,353`, I-20).

---

## 4. Layout und responsives Verhalten

### 4.1 Zonen und Breiten (token-gebunden)

Die Zonen folgen UI_KONZEPT §6.1, ergänzt um die Spine und den Inspector. Alle Breiten sind aus Tokens
abgeleitet; die Komponenten-Aliase stehen in §6.1.

| Zone | Breite | Token / Ableitung |
|---|---|---|
| Navigation | 240 px, ≥ `--bp-lg` sichtbar | `--nav-width` |
| Liste / Baum | 320–480 px, `flex: 0 0 clamp(320px, 30%, 480px)` | `--list-min` (380) ist der Wunschwert, 320 der Zustand „Inspector offen" (§4.4) |
| Spine | 52 px, senkrecht am linken Rand des Detailbereichs | `calc(var(--btn-h-lg) + var(--space-2))` |
| Inhalt | Rest; ≥ 508 px bei R2-Default, beim Ziehen nie unter 448 px (Deckel auf die Inspector-Breite) | `--detail-min` (520 als Ziel, 448 als **Untergrenze** beim Ziehen) |
| Inspector (Panel) | 280 px Minimum · **320 px Default in R2** · **360 px Default in R1** · 520 px Maximum, ziehbar | `--inspector-w-min`, `--inspector-w-default`, `--inspector-w-wide`, `--inspector-w-max` (§6.1) |
| Inspector (Rail) | 40 px | `calc(var(--btn-h-sm) + var(--space-1) * 2)` |

**Die vier Breiten-Aliase sind die einzigen Stellen, an denen eine Inspector-Breite als Literal steht**
(`--inspector-w-min: 280px` · `--inspector-w-default: 320px` · `--inspector-w-wide: 360px` ·
`--inspector-w-max: 520px`, §6.1). Jede Regel, jede Zustandsbeschreibung (§4.2) und jeder Kürzel-Vertrag
(§5.2, `Home`/`End`) referenziert **diese Namen**, nie die Zahl: sonst wandert die Breite bei der nächsten
Anpassung an fünf Stellen auseinander.

**448 px ist die Untergrenze, 508 px der Default.** Beim Ziehen darf der Inhalt bis 448 px schrumpfen
(Deckel auf die Inspector-Maximalbreite); im R2-Default bleiben **508 px**. Die beiden Werte sind nicht
austauschbar — 448 px ist kein Default, sondern die Grenze, an der die Formulare noch ohne horizontales
Scrollen funktionieren müssen (§4.4, D1).

**Scroll-Modell bleibt UI_KONZEPT §7:** genau drei Scrollflächen (Navigation, Liste, Detail-Inhalt).
Der Inspector bekommt **keine** vierte: die Reiterleiste steht, der Bereich scrollt **innerhalb** der
Detail-Fläche — er ist Teil von ihr, kein eigener Container. Das ersetzt die heutige `.panels`-Scrollbox
(`RightSidebar.module.css:76-86`), die eine fünfte Fläche ist.

### 4.2 Die fünf Breiten-Zustände

| Zustand | Breite | Inspector-Form | Default | Begründung |
|---|---|---|---|---|
| **R1** | ≥ 1600 px | **Panel** inline (dritte Zone im Detailbereich) | offen, `--inspector-w-wide` (360) | 1600 − 240 − 380 − 52 − 360 = **568 px** Inhalt ≥ 520 ✓ |
| **R2** | 1440–1599 px | **Panel** inline | offen, `--inspector-w-default` (320) | 1440 − 240 − 320 − 52 − 320 = **508 px** Inhalt (12 px unter Konzept-Minimum, §4.4 / D1) |
| **R3** | 1024–1439 px | **Sheet** (Overlay über dem Detailbereich, kein Scrim, schließbar, **non-modal**) | offen ab 1280 px, sonst Rail | Bei 1024 wäre inline rechnerisch kein lesbarer Inhalt übrig (§4.4) |
| **R4** | 768–1023 px | **Rail** in Fluss + **Sheet** auf Anforderung, Sheet-Breite = 100 % des Detailbereichs, **non-modal** | **Rail** | Navigation off-canvas (UI_KONZEPT §6.3); Spine waagerecht unter dem Artefaktkopf |
| **R5** | < 768 px | **Vollbild-Fläche** (ersetzt den Inhalt, „Zurück" im Kopf) | geschlossen, Zähler am Auslöser im Artefaktkopf | eine Spalte (UI_KONZEPT §6.3); unter 360 px brechen die Reiter in zwei Reihen um (§4.2, 1.4.10) |

**Sheet-Zustand (R3/R4): non-modal + `inert` — die Entscheidung, nicht die Ausnahme.**

Das Sheet ist **non-modal** (kein Fokus-Trap im Sheet, kein Scrim): die Liste und die Navigation bleiben
bedienbar, weil der Nutzer beim Lesen der Kommentare weiter das nächste Artefakt öffnen will (Q2/Q5, H7).
Non-modal heißt aber **nicht**, dass der überdeckte Detailbereich weiter im Accessibility-Tree und in der
Tab-Reihenfolge steht: er ist visuell nicht erreichbar, wäre per Tab aber fokussierbar — genau der Fall, den
WCAG 2.2 **SC 2.4.11** verbietet. Deshalb:

1. Bei offenem Sheet erhält der **überdeckte Detailbereich** (`<main>` samt Spine) das Attribut `inert`.
   `inert` entfernt ihn aus Fokusreihenfolge und Accessibility-Tree; die **Liste bleibt bedienbar** (sie ist
   nicht `inert`).
2. Die Fokusreihenfolge **endet am letzten Sheet-Element**; es gibt keinen Zyklus und keinen Trap.
3. `Esc`, der Schließen-Button und jeder andere Schließweg geben den Fokus an den **Auslöser** zurück
   (§5.1, Rückgabe-Kette).
4. Beim Schließen wird `inert` entfernt — in derselben Transaktion, in der das Sheet aus dem DOM geht
   (kein Frame, in dem der Bereich weder fokussierbar noch sichtbar ist).

**Der Rail-Zustand ist kein eigener Baum.** Rail und Sheet sind ein DOM-Knoten (§2.1): im Sheet-Zustand ist
der Rail-Inhalt **nicht gerendert**, im Rail-Zustand der Sheet-Inhalt. Ein `hidden`-Attribut auf dem jeweils
anderen Zweig wäre die zweitbeste Lösung — es würde zwei Zustände mit unterschiedlicher A11y-Wirkung
(`inert` vs. `hidden`) in einem Bauteil mischen (H4).

**Was bei 768 px genau passiert (Review Focus „schmale Fenster"):**

- Navigation off-canvas; Liste 45 % / Detail 55 % (UI_KONZEPT §6.3) — bei 768 px: **346 / 422 px**.
- Spine **waagerecht** unter dem Artefaktkopf, horizontal scrollbar ab fünf Stationen, Reihenfolge der Kette
  bleibt erhalten (UI_KONZEPT §5 „Verhalten"). Sie kostet Höhe, nicht Breite.
- Inspector startet als **Rail (40 px)** rechts im Detailbereich. Der Inhalt behält 382 px. Das ist eng, aber
  lesbar; der Rail zeigt Zähler, damit die Funktion sichtbar bleibt (U-05).
- Ein Klick auf den Rail öffnet das **Sheet über dem Detailbereich (422 px breit → 100 %)**, nicht über der
  Liste. Es hat einen sichtbaren Schließen-Button, `Esc` schließt, Fokus wandert hinein und an den Auslöser
  zurück (§5.1). Kein Scrim, damit der Zusammenhang „ich bin in diesem Artefakt" erhalten bleibt; der
  überdeckte Detailbereich wird `inert` (siehe Sheet-Zustand oben).
- Der Reiterstreifen ist bei 422 px **in R4 horizontal scrollbar** (vier Reiter × ~88 px + Zähler > 422). Die
  Scrollbarkeit ist sichtbar (Fade am Rand, `scrollbar-gutter: stable`), Reiter werden in R4 nicht
  umgebrochen — die Alternative wäre ein Umbruch bei 422 px, der drei Reiterzeilen und einen Höhenverlust im
  Sheet erzeugt.

**Was in R5 (< 768 px) passiert (1.4.10 Reflow, 1.4.4 Resize text):**

- Eine Spalte; der Inspector ersetzt als **Vollbild-Fläche** den Inhalt, „Zurück" steht im Kopf. Der
  Auslöser im Artefaktkopf trägt die Zähler (§3).
- **Unter 360 px brechen die Reiter in zwei Reihen um** (`flex-wrap: wrap`, Reiter behalten ihre Reihenfolge).
  Bei 320 px — der schmalsten zu unterstützenden Breite — entsteht **kein horizontaler Seiten-Scroll**;
  Sheet-Kante, Innenabstände und Formulare bleiben innerhalb der Spalte. Ein horizontal scrollbarer
  Reiterstreifen ist in R5 **nicht** zulässig, weil er bei 320 px die einzige waagerechte Scrollfläche der
  Seite wäre.
- Der Umbruch ist ein Layoutwechsel, kein Zustandswechsel: `aria-selected`, `aria-controls` und die
  Reiter-Reihenfolge bleiben gleich (§7 Id-Vertrag).

**Was bei 1024 px genau passiert:** Navigation sichtbar (240 px), Liste 45 % von 784 = **353 px**, Detail
**431 px**, Spine 52 px senkrecht, Inhalt **379 px**. Der Inspector ist ein Sheet
(`--inspector-w-wide` 360, gedeckelt durch `--inspector-w-max` und 100 %); er
überdeckt den Inhalt, nicht die Liste. Eingeklappt (unter 1280 px) ist er ein 40-px-Rail, der Inhalt behält
339 px. → **Der Inspector verdrängt bei 1024 px keinen Inhalt, er überlagert ihn temporär** (Review Focus).

### 4.3 Screens (SCR-IDs) und Zustände

| ID | Screen | Zweck | Zustände |
|---|---|---|---|
| `SCR-INSP-01` | Inspector als Panel (R1/R2) | Historie, Diff, Links, Kommentare neben dem Inhalt | loading, empty, error, partial, success |
| `SCR-INSP-02` | Inspector als Rail (alle Breiten, zugeklappt) | Funktion sichtbar halten; Zähler lesen | leer (alle 0), Zähler, Fokus |
| `SCR-INSP-03` | Inspector als Sheet (R3/R4) | Inspector auf schmaler Breite | loading, empty, error, offen/geschlossen, Fokus im Sheet |
| `SCR-INSP-04` | Inspector als Vollbild (R5) | Inspector auf einer Spalte | wie 01 + Zurück-Navigation |
| `SCR-SPINE-01` | Trace-Spine senkrecht (R1–R3) | Position + Abdeckung | loading, leer, teilweise, Fehler |
| `SCR-SPINE-02` | Trace-Spine waagerecht (R4/R5) | dasselbe, platzsparend | dasselbe, horizontal scrollbar |

**Zustandsregeln (für alle vier Screens gleich, H4):**

| Zustand | Darstellung | Text (i18n) |
|---|---|---|
| loading | Skeleton in Endhöhe (kein Sprung, UI_KONZEPT §7.3) | `sidebar.inspector.skeletonLoading` (existiert, heute ungenutzt — I-10) |
| empty | gestrichelter Rahmen `--color-border`, `--color-text-muted` | je Bereich ein eigener Satz (§5.5, i18n-Tabelle) |
| error | Banner `--color-diff-removed-bg`/`-text` + **ein** „Erneut versuchen" | `sidebar.inspector.error.{{panel}}` |
| partial | Zeile bleibt sichtbar, Aktion `aria-disabled="true"` **ohne** natives `disabled`, Grund als `aria-describedby` auf sichtbarem Text **plus** `title` | `sidebar.inspector.partial.noSnapshot` (heute ohne Grund, U-13) |
| success | Regelinhalt | — |

**Ein Disabled-Vertrag (gilt für alle Bauteile, §6.2):** `aria-disabled="true"` **ohne** natives
`disabled`-Attribut. Begründung: ein nativ deaktivierter Button ist nicht fokussierbar, sein Grund ist per
Tastatur also nicht erreichbar — bei uns ist der Grund die eigentliche Information („kein gespeicherter
Schnappschuss", U-13). Der Grund steht als `aria-describedby` auf **sichtbarem** Text (eine Zeile, kein
Tooltip); `title` kommt zusätzlich für die Maus dazu. Die Aktion bleibt fokussierbar, reagiert aber nicht
(kein Request, keine Zustandsänderung). Ausnahme: kein Fall im Inspector ist so destruktiv, dass ein
natives `disabled` nötig wäre.

**Composer-Fehlerpfad (Kommentar anlegen schlägt fehl):**

1. Die Fehlermeldung steht in der **`role="alert"`-Region** (§5.3), nicht unter dem Feld — sie ist die
   Ansage *und* die sichtbare Meldung (`sidebar.inspector.error.commentCreate`).
2. Die Textarea erhält `aria-invalid="true"` und `aria-describedby="comment-error"`; `#comment-error` ist
   der sichtbare Meldungstext.
3. Der Fokus wandert **auf die Textarea** (nicht auf den Submit-Button), damit die Korrektur direkt möglich
   ist.
4. Der **eingegebene Text bleibt erhalten** — kein Leeren des Feldes, kein erneutes Tippen (H3, H5).
5. Nach erfolgreichem Senden: `aria-invalid` und `aria-describedby` werden entfernt, das Feld wird geleert,
   die Ansage ist `sidebar.inspector.live.commentCreated` (§5.3).

Zwei Fehlerzustände, die heute fehlen, sind Pflicht: **Kommentare ohne Retry** (`CommentPanel.tsx:105-109`)
und **Diff ohne eigenen Fehlerzustand** (`DiffPanel.tsx` delegiert an `ArtifactDiff`). Beide bekommen das
Banner aus der Tabelle.

### 4.4 Der Breiten-Konflikt bei 1440 px — nachgerechnet

UI_KONZEPT §6.1 fordert Liste ≥ 380 px und Detail ≥ 520 px, §6.2 zusätzlich Navigation 240 px.
Mit einem standardmäßig **offenen** Inspector passen diese vier Mindestbreiten nicht zusammen:

| Kombination | Summe | Ergebnis bei 1440 px |
|---|---|---|
| 240 + 380 + 52 + 520 + 360 (Panel-Default) | 1552 | **112 px zu breit** |
| 240 + 380 + 52 + 520 + 280 (Panel-Minimum) | 1472 | **32 px zu breit** |
| 240 + 320 + 52 + 520 + 280 (Liste 320, Panel-Min.) | 1412 | passt, 28 px Rest |
| 240 + 320 + 52 + 320 + 320 (Liste 320, Panel 320 Default) | 1252 | passt; Inhalt **508 px** |

**Diese Spec wählt die letzte Zeile:** Liste 320 px, Panel 320 px, Inhalt 508 px. Der Inhalt liegt damit
**12 px unter** der Konzept-Mindestbreite von 520 px. Das ist eine bewusste Abweichung, kein Rechenfehler,
und sie ist Daniel zur Entscheidung vorgelegt (§11 **D1**). Kein Stack lief; **508 px sind nicht gerendert
geprüft** — die Formulare müssen bei 508 px ohne horizontales Scrollen funktionieren (Prüfpunkt im
Umsetzungsplan).

---

## 5. Interaktion und Tastatur

### 5.1 Fokusreihenfolge

DOM-Reihenfolge = Tab-Reihenfolge (keine `tabindex`-Umsortierung, H4):

| # | Element | Fokusverhalten | Heuristik |
|---|---|---|---|
| 1 | Skip-Link „Direkt zum Inspector" (erstes fokussierbares Element im Detailbereich, sichtbar bei Fokus) | springt auf die Inspector-Überschrift `#inspector-heading` (`tabindex="-1"`); **existiert heute nicht** (U-14) | H7 |
| 2 | Artefaktkopf-Aktionen | Standard | — |
| 3 | Spine | **ein** Tab-Stopp (Roving Tabindex), Pfeil ↑/↓ zwischen Stationen | H7 |
| 4 | Inhalt / Formular | unverändert | — |
| 5 | **Splitter** (`role="separator"`, `tabindex="0"`) | **eigener Tab-Stopp an seiner DOM-Position**: erstes Kind der Inspector-Fläche, also **vor** der Kopfzeile (heute dieselbe Stelle, `RightSidebar.tsx:269-271`). Er wird nicht ans Ende der Fläche verschoben — die Reihenfolge folgt dem DOM, nicht der Wunschvorstellung (Q13, H4). In R4 (Sheet = 100 % der Detailbreite) gibt es keinen Splitter; Stufe 5 entfällt dort | H7 |
| 6 | Inspectorkopf („Schließen") | eine Aktion | — |
| 7 | Reiterleiste | **ein** Tab-Stopp; ←/→/Home/End bewegen den Fokus, **Enter/Space aktivieren** (§5.2) | H7 |
| 8 | Aktiver Bereich | das `tabpanel` selbst ist fokussierbar (`tabindex="0"`, §7), danach die Zeilen | H1 |

**Reiterwechsel: Fokus bleibt auf dem Reiter (manuelle Aktivierung).**

Jeder Reiterwechsel löst einen Fetch aus (Versionen, Diff, Links, Kommentare). Deshalb gilt die
**manuelle Aktivierung** der APG-*tabs*: ←/→/Home/End verschieben nur den Fokus, `Enter`/`Space` aktiviert.
Das ist eine bewusste Abweichung vom vorhandenen Helfer: `shared/tablistKeyboardNav.ts:34-58` ruft
`onChange(nextId)` direkt im Pfeil-Handler (`:52`), also *automatische* Aktivierung — für die Settings-Reiter
richtig, für den Inspector würde jedes Durchblättern vier Requests auslösen. Der Inspector braucht die
Variante „Fokus bewegen ohne `onChange`" (§8 M1).

- Nach dem Aktivieren **bleibt der Fokus auf dem gewählten Reiter** — er wandert nicht in den Bereich und
  nicht auf eine Überschrift. Die Reiterleiste ist damit der stabile Anker für die nächste Pfeiltaste.
- `scrollIntoView({ block: "nearest" })` gilt **nur für Zeilen-Fokus** (Tastatur-Navigation in langen Listen),
  nicht für Reiter und nicht für Überschriften.
- Überschriften tragen `tabindex="-1"` **ausschließlich als programmatisches Fokusziel**: die
  Inspector-Überschrift als Skip-Link-Ziel (Schritt 1). Bereichsüberschriften (`h3`) sind **kein** Tab-Stopp
  und **kein** automatisches Fokusziel — sonst springt der Fokus bei jedem Reiterwechsel und die
  Reiterleiste verliert ihren Anker (H3, 2.4.3).
- Für das Fokusziel „Kopfzeile" (Ausklappen, Vollbild, §5.1 unten) trägt der **Kopfzeilen-Container**
  `tabindex="-1"`, nicht die Überschrift — so bleibt `tabindex` auf Überschriften auf den Skip-Link-Fall
  beschränkt.

**Sheet/Vollbild (R3–R5):** Beim Öffnen wandert der Fokus auf den aktiven Reiter. Das Sheet ist
**non-modal** — es gibt **keinen Fokus-Trap im Sheet**, der überdeckte Detailbereich ist aber `inert`
(§4.2): die Fokusreihenfolge endet damit am letzten Sheet-Element, ohne Zyklus. `Esc` schließt und gibt den
Fokus an den Auslöser zurück; beim Schließen wird die Scrollposition des Inhalts wiederhergestellt.

**Vollbild (R5):** Beim Wechsel in die Vollbild-Fläche wandert der Fokus auf den **Kopfzeilen-Container**
(`tabindex="-1"`) — nicht auf den ersten Reiter, weil der „Zurück"-Weg die erste Orientierung ist. Der
Wechsel wird über die **polite-Region** angesagt (`sidebar.inspector.live.fullscreenOpened`), nicht über
`role="alert"`: es ist kein Fehler. Beim Zurückgehen kehrt der Fokus zum **Auslöser** im Artefaktkopf zurück.

**Ausklappen/Einklappen (S9):** Ausklappen (Rail → Panel/Sheet, `Alt+Shift+I` oder Klick) setzt den Fokus
auf den **Kopfzeilen-Container** (`tabindex="-1"`); Einklappen (Splitter-`Enter` oder Schließen) setzt ihn
auf den **Rail-Aufklappen-Button** (`aria-expanded="false"`). Beide Ziele sind fokussierbar, ohne ein
zusätzliches Tab-Stopp zu erzeugen.

**Fokus-Rückgabe mit Fallback-Kette (H6):** Der Rückgabefokus ist der **Auslöser**, der das Sheet geöffnet
hat. Existiert er nicht mehr (Route gewechselt, Zeile neu gerendert, Element entfernt), gilt in dieser
Reihenfolge: **Auslöser → Rail-Aufklappen-Button → Kopfzeilen-Container**. Die Kette ist erschöpfend; der
Fokus fällt nie auf `<body>` zurück.

**`Esc` schließt die innerste Ebene (H4/H5):** `Esc` wirkt in dieser Priorität: (1) offene Stationsliste in
der Spine, (2) offenes Sheet bzw. Vollbild-Fläche. Fokus im Composer ist **keine** eigene Ebene: `Esc` dort
schließt das Sheet **und verwirft den eingegebenen Text nicht** — der Feldwert bleibt im Zustand erhalten
(auch über Schließen und erneutes Öffnen). Ein zweites Verhalten (erst „Feld verlassen", dann „Sheet
schließen") wäre eine unsichtbare Stufe ohne sichtbaren Zustand.

**Spine-Station:** `Enter`/`Space` öffnet die Stationsliste (`aria-expanded`), `Esc` schließt sie und gibt
den Fokus an die Station zurück. Ein zweiter Klick auf dieselbe Station schließt sie (heutiges Verhalten,
`TraceSpine.tsx:81-83`, bleibt).
**Deaktivierte Kettenglieder** tragen künftig einen Grund als `title` **und** `aria-describedby`
(heute: `useDerivationChain.ts:54-61,269-271` + kein `title`, U-13).

### 5.2 Kürzel

| Kürzel | Wirkung | Kontext |
|---|---|---|
| `Alt+I` | Inspector fokussieren; falls geschlossen, öffnen | global in einer Artefakt-Route |
| `Alt+Shift+I` | Inspector ein-/ausklappen (Rail ↔ Panel/Sheet), Fokusziel nach §5.1 (S9) | global |
| `←` `→` `Home` `End` | **Fokus** auf den nächsten/vorherigen/ersten/letzten Reiter — **aktiviert nicht** (manuelle Aktivierung, §5.1) | Fokus in der Reiterleiste |
| `Enter` / `Space` | **Reiter aktivieren** (genau ein Fetch) | Fokus auf einem Reiter |
| `↑` `↓` | Station wechseln | Fokus in der Spine |
| `Enter` / `Space` | Station oder Zeile öffnen | Fokus auf Station/Zeile |
| `Esc` | innerste Ebene schließen (Stationsliste → Sheet/Vollbild), Fokus zurück; **verwirft keinen Composer-Text** (§5.1) | überall im Inspector |
| `←` `→` | Breite ± `--space-4` (16 px), geklemmt auf `--inspector-w-min`/`--inspector-w-max` | Fokus auf dem Resize-Handle |
| `Home` / `End` | Breite `--inspector-w-min` / `--inspector-w-max` | Fokus auf dem Resize-Handle |
| `Enter` | Ein-/Ausklappen (fixed-Splitter-Semantik), Fokus auf den Rail-Aufklappen-Button | Fokus auf dem Resize-Handle |

Die beiden `Enter`-Zeilen kollidieren nicht: sie gelten in verschiedenen Kontexten (Reiter vs. Splitter vs.
Zeile). Die Reiter-Zeile ist die einzige mit **manueller** Aktivierung — sie ist der Grund, warum
`Enter`/`Space` in der Reiterleiste überhaupt eine eigene Zeile braucht.

Keine Ein-Buchstaben-Kürzel (Kollision mit Formularfeldern). Kürzel werden nur registriert, solange kein
Eingabefeld den Fokus hat.

### 5.3 Live-Regionen (genau zwei)

Heute hat jedes Panel seine eigene Ansage, die Diff-Ansage sitzt **unter** der Klickstelle (U-03). Künftig:
**eine** höfliche Region (`aria-live="polite"`) und **eine** alarmierende (`role="alert"`), beide am Ende des
Inspectors, nicht je Panel.

**Schlüsselwurzel:** alle neuen Schlüssel liegen unter `sidebar.inspector.*` — **nicht** unter
`inspector.*`. Grund: `inspector` existiert bereits als Namensraum an anderen Wurzeln
(`diagram.inspector` für das Eigenschaften-Panel, `workflow.inspector` für den Zustands-Inspektor,
`de.json:1859`/`:2518`); ein neuer Schlüssel `inspector.*` würde beim nächsten Umbenennen stillschweigend
den falschen Namensraum treffen. Der bestehende Namensraum `sidebar.inspector` enthält bereits
`title`/`ariaLabel`/`collapse`/`expand`/`refresh`/`skeletonLoading`/`resize` (`de.json:2228-2237`).
Das Review nennt die Live-Schlüssel noch mit dem Präfix `inspector.`; sie liegen aus dem genannten Grund
unter `sidebar.inspector.` — die Schlüsselnamen selbst sind unverändert.

| Schlüssel | DE | EN | Region |
|---|---|---|---|
| `sidebar.inspector.live.tabChanged` | „Bereich {{tab}}, {{count}} Einträge." | "{{tab}} section, {{count}} items." | polite |
| `sidebar.inspector.live.versionLoaded` | „{{count}} Versionen geladen." | "{{count}} versions loaded." | polite |
| `sidebar.inspector.live.diffLoaded` | „Vergleich {{from}} bis {{to}} geladen, {{n}} geänderte Felder." | "Comparison {{from}} to {{to}} loaded, {{n}} changed fields." | polite |
| `sidebar.inspector.live.linksLoaded` | „{{count}} Verknüpfungen geladen, davon {{derived}} in der Spine." | "{{count}} links loaded, {{derived}} shown in the spine." | polite |
| `sidebar.inspector.live.commentsLoaded` | „{{count}} Kommentare, {{open}} offen." | "{{count}} comments, {{open}} open." | polite |
| `sidebar.inspector.live.baselineSelected` | „Basis {{name}} gewählt." | "Baseline {{name}} selected." | polite |
| `sidebar.inspector.live.linkCreated` | „Verknüpfung erstellt: {{type}} {{id}}." | "Link created: {{type}} {{id}}." | polite |
| `sidebar.inspector.live.linkDeleted` | „Verknüpfung {{type}} {{id}} gelöscht." | "Link {{type}} {{id}} deleted." | polite |
| `sidebar.inspector.live.commentCreated` | „Kommentar erstellt." | "Comment created." | polite |
| `sidebar.inspector.live.commentResolved` | „Kommentar als erledigt markiert." | "Comment marked as resolved." | polite |
| `sidebar.inspector.live.commentDeleted` | „Kommentar gelöscht." | "Comment deleted." | polite |
| `sidebar.inspector.live.retrySucceeded` | „{{panel}} geladen." | "{{panel}} loaded." | polite |
| `sidebar.inspector.live.retryFailed` | „{{panel}} weiterhin nicht verfügbar." | "{{panel}} still unavailable." | alert (einmal je Versuch) |
| `sidebar.inspector.live.fullscreenOpened` | „Inspector im Vollbild geöffnet. Zurück im Kopf der Seite." | "Inspector opened full screen. Back in the page header." | polite |
| `sidebar.inspector.live.resized` | „Inspector {{width}} Pixel breit." | "Inspector {{width}} pixels wide." | polite |
| `sidebar.inspector.error.{{panel}}` | „{{panel}} konnte nicht geladen werden. Erneut versuchen." | "{{panel}} could not be loaded. Try again." | alert (einmal je Fehler) |

**Regeln (S6):**

1. **Genau eine Ansage pro Interaktion.** Löschen einer Verknüpfung ist *eine* Ansage
   (`linkDeleted`), nicht zwei (`linkDeleted` + `linksLoaded`). Retry ist *eine* Ansage
   (`retrySucceeded`/`retryFailed`), nicht zusätzlich `versionLoaded`.
2. **`xxxLoaded` unterdrückt `tabChanged` im selben Task.** Ein Reiterwechsel löst beides aus; die
   geladene Zahl ist die nützlichere Information, die allgemeine „Bereich X" ist die schwächere. Bleibt der
   Fetch aus (Cache-Treffer), fällt die Ansage auf `tabChanged` zurück — dann ist sie die einzige.
3. **Zählerstände sind polite; nur Fehler sind alert** — und ein Fehler nur **einmal** pro Ereignis (kein
   Dauerfeuer in Retry-Schleifen, U-03).
4. **Eine Ansage ist nie die einzige Fundstelle einer Information** (deshalb die sichtbare Paar-Zeile in
   §2.2 und der sichtbare Fehlertext in §4.3).
5. Die Ansagetexte tragen **keine Zahlen aus zwei Quellen**: `{{count}}` ist die geladene Menge, `{{open}}`
   die offene Teilmenge — beide werden aus derselben Antwort berechnet, nicht aus zwei Requests.

### 5.4 Zustandserhalt

- Reiterwahl, Filter und Scrollposition je `kind` **und** Artefakt-ID, in `sessionStorage`
  (Schlüssel `reqflow_inspector_tab_<kind>_<id>`). Heute existieren nur drei Schlüssel je `kind` für
  Einklappen/Breite/Pin (`RightSidebar.tsx:74-76`), kein Reiterzustand (I-10).
- `goal` und `mainGoal` bekommen **einen** gemeinsamen Persistenz-Slot (behebt I-14: Zustand springt beim
  Wechsel).
- Reiterwahl ist über die URL reproduzierbar (`?inspector=links`), damit ein Link auf „die Kommentare
  dieses Artefakts" möglich ist (Q10: Zustand reproduzierbar).

### 5.5 i18n-Vertrag (DE/EN)

**Wurzel ist `sidebar.inspector.*`, nicht `inspector.*`.** `inspector` existiert bereits an anderen Wurzeln
(`diagram.inspector`, `workflow.inspector`); ein neuer Schlüssel `inspector.*` würde beim nächsten Umbenennen
still den falschen Namensraum treffen. **Platzhalterform ist einheitlich `{{panel}}`** (i18next-Syntax) — die
Schreibweise `<panel>` in §4.3 war Metasyntax und ist ersetzt.

| Verwendung | Schlüssel | Status | DE | EN |
|---|---|---|---|---|
| Reiter „Version" | `sidebar.version.title` | vorhanden | Version | Version |
| Reiter „Diff" | `sidebar.diff.title` | vorhanden | Diff | Diff |
| Reiter „Links" | `sidebar.inspector.tab.links` | **neu** | Links | Links |
| Reiter „Kommentare" | `comments.heading` | vorhanden | Kommentare | Comments |
| Reiter „Links" im Glossary | `terminologyLabel("glossary.usages")` (Terminologie-Profil, `glossary.usages`) | vorhanden | Verwendungen | Usages |
| Zähler (sichtbar, Ziffer) + Zähler-Ansage | `sidebar.inspector.count.open` · `sidebar.inspector.railCount` | **neu** | offen: {{n}} · „{{tab}}, {{open}} offen" | open: {{n}} · "{{tab}}, {{open}} open" |
| Aktion „Erneut versuchen" | `actions.retry` | vorhanden | Erneut versuchen | Retry |
| Aktion „Neuen Link erstellen" | `actions.newLink` | vorhanden | Neuen Link erstellen | Create new link |
| Aktion „In der Spine anzeigen" | `sidebar.inspector.action.showInSpine` | **neu** | In der Spine anzeigen | Show in spine |
| Aktion „Löschen" (Link) | `actions.delete` | vorhanden | Löschen | Delete |
| Kommentar „Erledigen" / „Löschen" / „Kommentieren" | `comments.resolve` · `comments.delete` · `comments.submit` | vorhanden | Erledigen · Löschen · Kommentieren | Resolve · Delete · Comment |
| Empty „Version" | `sidebar.version.empty` | vorhanden | Keine Versionshistorie für dieses Artefakt. | No version history for this artifact. |
| Empty „Diff" | `sidebar.diff.empty` | vorhanden | Wähle oben zwei Versionen zum Vergleichen. | Select two versions above to compare. |
| Empty „Links" (mit Spine, keine weiteren) | `sidebar.inspector.empty.linksOther` | **neu** | Keine weiteren Verknüpfungen. | No other links. |
| Empty „Links" (ohne Spine) | `sidebar.inspector.empty.linksAll` | **neu** | Keine Verknüpfungen. | No links. |
| Empty „Kommentare" | `comments.empty` | vorhanden | Noch keine Kommentare. | No comments yet. |
| Fehler je Bereich | `sidebar.inspector.error.{{panel}}` | **neu** | {{panel}} konnte nicht geladen werden. Erneut versuchen. | {{panel}} could not be loaded. Try again. |
| Partial-Grund | `sidebar.inspector.partial.noSnapshot` | **neu** | Kein gespeicherter Schnappschuss für diese Version. | No stored snapshot for this version. |
| Composer sendet | `sidebar.inspector.composer.submitting` | **neu** | Wird gesendet … | Sending … |

**Warum der Reiter „Links" nicht `sidebar.trace.title` nutzt.** Der bestehende Schlüssel heißt **DE
„Trace-Links" / EN „Trace Links"** (`de.json:2267`, `en.json:2267`); derselbe Begriff steht in
`tracelinks.panelTitle`. Beide benennen die **Trace-Teilmenge** (Ableitung + Verifikation). Der Reiter zeigt
genau **nicht** diese Teilmenge als Zeilen, sondern das Inventar der übrigen Typen (`mitigates`, `decides`,
`references`, `diagram-ref`, tenant-spezifische, §2.3). Ein Label „Trace-Links" würde damit das Gegenteil der
Regel aus §2.3 behaupten. Deshalb ein eigener, kurzer Schlüssel; die beiden bestehenden Keys bleiben
unverändert (der CRUD-Block der Route heißt weiter „Trace-Links").

**Warum `comments.heading` wiederverwendet wird.** Reiter-Label und Bereichsüberschrift meinen dasselbe
Konzept; zwei Schlüssel würden bei der nächsten Umbenennung auseinanderlaufen (H4). Die Kürze ist
ausreichend („Kommentare" = 10 Zeichen).

**Kein neues Nomen „Verknüpfung" in Aktionen.** Die Aktion heißt `actions.newLink` („Neuen Link erstellen",
vorhanden); die Mockups sind darauf umgestellt. Nur die Zähler- und Leerzustandssätze führen das Wort
„Verknüpfung", weil sie Sätze und keine Labels sind.

**Je Bereich genau ein Empty-Satz**, keine Wiederverwendung eines Satzes aus einem anderen Bereich: die
Tabelle enthält vier Bereiche (Links mit zwei Varianten, weil mit/ohne Spine verschiedene Sätze braucht) —
das ist die vollständige Liste.

---

## 6. Token- und Varianten-Vertrag

Nur Tokens aus `frontend/src/styles/tokens.css`. Komponenten-Aliase sind erlaubt, müssen aber **im selben
CSS-Modul deklariert** sein (der Token-Existenz-Test akzeptiert nur lokale Deklarationen,
`frontend/src/test/design-tokens.test.ts:168-207`). **Keine neuen Primitives, keine Literale für Farbe,
Höhe, Radius, Abstand.**

### 6.1 Höhen, Radien, Abstände

| Element | Höhe | Radius | Abstand | Tokens |
|---|---|---|---|---|
| Inspector-Fläche (Panel/Sheet) | volle Höhe des Detailbereichs | 0 (bündig) | — | `--color-surface-raised`; Kante an der Listenseite = **Splitter-/Sheet-Ruheline** (`--color-text-muted`, siehe Kanten-Tabelle), alle übrigen Kanten `var(--control-border-width) solid var(--color-border)` |
| Kopfzeile | `var(--btn-h-md)` (36) | 0 | `--space-3 var(--space-4)` | `--font-size-base`, `--weight-semibold` |
| Reiter (`.btn-tab` aus `global.css`) | `min-height: var(--inspector-tab-h)` (32) | `--radius-btn` (außen), 0 innen | `--space-1 var(--space-3)` | `--font-size-sm`, `--weight-semibold` |
| Bereichskörper | — | — | `--space-4`, `gap: --space-3` | Karten und Zeilen `--color-surface`; die Panel-Fläche darunter bleibt `--color-surface-raised` |
| Abschnittsüberschrift | — | — | `--space-2 0` | `--font-size-sm`, `--font-cond`, `--tracking-wide`, `--color-text-muted` |
| Zeile (Version/Link/Kommentar) | `min-height: var(--inspector-row-h)` (36) | `--radius-sm` im Hover | `--space-2 var(--space-3)` | `--color-text`, `--color-surface`; Hover `--color-surface-raised` |
| Zeilen-Aktionsbutton (Icon) | `var(--btn-h-sm)` (32) | `--radius-btn` | — | Hover `--color-border`, gedrückt `--color-primary`/`--color-on-primary` |
| Filter-Chip (Text) | `var(--btn-h-sm)` (32) | `--radius-full` | `--space-1 var(--space-3)` | `--color-surface`, `--color-border` |
| Status-/Typ-/Level-Badge | **22 px** (`BADGE_HEIGHT`, `frontend/src/utils/badgeBase.ts:67`) | **`--radius-sm`** (`utils/badgeBase.ts:92`) | — | `--color-badge-*` — **keine** lokale Badge-Geometrie |
| Rail | Breite `calc(var(--btn-h-sm) + var(--space-1) * 2)` = 40 | 0 | `--space-2 0` | `--color-surface-raised` |
| Rail-Button (Schließen/Aufklappen und **jeder Zähler**) | `var(--btn-h-sm)` (32) | `--radius-btn` | — | — |
| Rail-Zähler | — | `--radius-full` | `0 var(--space-1)` | **`--font-size-xs`** (kein `9px`-Literal), `--font-cond` |
| Resize-Handle (Hitbox) | volle Höhe | 0 | Breite `var(--inspector-resize-hit)` (24) | **Ruheline `var(--control-border-width) solid var(--color-text-muted)` (1 px)**; Hover/Fokus 2 px `--color-primary` |
| Spine-Rail | Breite `calc(var(--btn-h-lg) + var(--space-2))` = 52 | 0 | `--space-2` | `--color-border` |
| Spine-Station | `min-height: var(--btn-h-md)` (36) | `--radius-btn` | `--space-1` | `--color-text`, `--color-text-muted` |
| Empty-State | — | `--radius-md` | `--space-3 var(--space-2)` | `var(--control-border-width) dashed var(--color-border)`, `--color-text-muted`, `--font-size-sm` |
| Error-Banner | — | `--radius-md` | `--space-3` | `--color-diff-removed-bg`, `--color-diff-removed-text` |
| Sheet (R3/R4) | volle Höhe | 0 | — | `--shadow-card`, `--color-surface-raised`, **Kante `var(--control-border-width) solid var(--color-text-muted)`** |
| Motion | — | — | — | nur `--transition-fast` für `background`, `border-color`, `width`; `prefers-reduced-motion` → keine Transition |

**Sichtbare Kanten statt „Rahmen bei Hover" (WCAG 1.4.11).** Die Zusage „`--color-border` erfüllt 3:1" ist
falsch und wird hier ersetzt: `--color-border` erreicht auf `--color-surface*` nur **1.42–1.48:1**. Geprüfte
Paare sind deshalb:

| Kante | Token | Kontrast |
|---|---|---|
| Sheet-Kante (links) | `var(--control-border-width) solid var(--color-text-muted)` (1 px) | **7.24:1** auf `--color-surface`, **7.58:1** auf `--color-surface-raised` |
| Splitter-Ruheline | `var(--control-border-width) solid var(--color-text-muted)` (1 px) | **7.24:1** / **7.58:1** (dieselben Paare) |
| Splitter bei Hover/Fokus | 2 px `--color-primary` | `--color-border-hover` bleibt **nur** Hover-Fläche, keine Kante |

Damit ist die Trennlinie **auch im Ruhezustand sichtbar**. Der Griff ist heute transparent
(`RightSidebar.module.css`-Muster) und wird erst bei Hover zur Linie — das ist ein 1.4.11-Verstoß, weil die
Grenze zwischen Inhalt und Inspector im Ruhezustand nur über `--color-border` (unter 3:1) existiert.

**Rahmenbreite und Fokus-Offset (keine 1-px-Literale, eine begründete Ausnahme):** jede Kante nutzt
`var(--control-border-width)` statt `1px` (`tokens.css:847`); im Mockup ist das derselbe Wert, aber
token-gebunden. Der Fokusring ist `2px solid var(--color-focus)` mit **Offset 1 px** (vorher 2 px) — der
Offset ist **kein Token** (es gibt keines, `tokens.css:849` nur `--control-focus-ring`); er wird hier als
einzige begründete Ausnahme festgelegt, damit Ring und Kante im 24-px-Griff nicht kollidieren.

**Keine Schriftgröße unter `--font-size-xs`.** Die Mikro-Typografie der Mockups (8/9/10/11 px an
Stationslabels, Zählern, Badges) war teils nicht token-fähig und teils unter der Lesbarkeitsgrenze; alle
diese Stellen nutzen `--font-size-xs` (12 px). Damit ist `--font-size-xs` die Untergrenze im Inspector —
eine Ausnahme gibt es nicht.

**Komponenten-Aliase (im jeweiligen Modul deklariert und dort verwendet):**

```
--inspector-w-min: 280px;          /* Zieh-Untergrenze, §5.2 Home */
--inspector-w-default: 320px;      /* Panel-Default R2 */
--inspector-w-wide: 360px;         /* Panel-Default R1 */
--inspector-w-max: 520px;          /* Zieh-Obergrenze, §5.2 End */
--inspector-rail-w: calc(var(--btn-h-sm) + var(--space-1) * 2);   /* 40 */
--inspector-tab-h: var(--btn-h-sm);
--inspector-row-h: var(--btn-h-md);
--inspector-spine-w: calc(var(--btn-h-lg) + var(--space-2));      /* 52 */
--inspector-resize-hit: var(--btn-h-xs);                          /* 24 */
```

Die **vier Breiten-Aliase** sind die einzigen nackten Pixelwerte, und sie sind **Breitenpräferenzen**, keine
Geometrie-Tokens: 280/320/360/520 px sind die vier Zahlen, die §4.1, §4.2 und §5.2 benennen, und sie stehen
genau einmal hier. Sie werden **nicht** als Inline-Objektliteral gesetzt (das würde die Ratchet brechen,
§8.3), sondern entweder über eine benannte, hochgezogene `CSSProperties`-Konstante — bestehendes Muster
`style={asideStyle}`, `RightSidebar.tsx:269-308` — oder über `element.style.setProperty("--inspector-w-…", …)`
per Ref (CSSOM; zählt nicht als `style={{`, gleiche Begründung wie bei den Sheet-Hooks aus #874,
`ui-ratchet.test.ts:456-460`). Alle übrigen Aliase leiten sich aus `--btn-h-*` und `--space-*` ab.

### 6.2 Zustände

| Zustand | Darstellung | Tokens |
|---|---|---|
| default | Panel-/Sheet-Fläche mit Kante | `--color-surface-raised`, Kante `var(--control-border-width) solid var(--color-border)` |
| default (Zeile/Karte **auf** der Fläche) | eigene Fläche, damit die Zeile lesbar bleibt | `--color-surface` |
| hover | Fläche wechselt auf die jeweils andere Rolle, **kein** Farbwechsel des Textes | Zeile: `--color-surface` → `--color-surface-raised`; `--color-border-hover` |
| active/pressed | Fläche + Rahmen | `--color-border-hover` |
| selected (Reiter) | `.btn-tab[aria-selected="true"]` | `--color-primary`, `--color-on-primary` |
| selected (Filter-Chip) | `aria-pressed="true"` | `--color-primary-text` (Text), `--color-primary` (Kante, `var(--control-border-width)`) |
| selected (Zeile) | `--color-card-active-bg` (Flächen-Fill) | `--color-card-active-bg` |
| focus-visible | 2-px-Ring, **1 px Offset**, **nie** `outline: none` | `--control-focus-ring` (`var(--color-focus)`) |
| disabled | 50 % Deckkraft **plus** `aria-disabled="true"` (ohne natives `disabled`) **plus** `aria-describedby` auf sichtbaren Grund | `--color-text-muted` |
| loading | Skeleton in Endhöhe | `--color-border`, `--color-surface` |
| error | Banner (§6.1) + ein Retry | `--color-diff-removed-bg/-text` |
| empty | gestrichelter Rahmen | `var(--control-border-width) dashed var(--color-border)`, `--color-text-muted` |

**Zustände je Bauteil** (die Tabelle oben ist der allgemeine Vertrag; hier die Bauteile, die mehr als
`default`/`hover` haben):

| Bauteil | Zustände | Darstellung / Verhalten | Tokens |
|---|---|---|---|
| Filter-Chip | default · hover · **selected** (`aria-pressed="true"`) · focus-visible · disabled | `aria-pressed` ist der Zustandsträger; keine zweite Klasse, kein `data-`-Attribut. selected = Text `--color-primary-text`, Kante `var(--control-border-width)` in `--color-primary` (kein Fill — sonst `PRIMARY_FILL_BASELINE`, §8.3) | `--color-primary-text`, `--color-primary`, `--color-surface` |
| Composer | default · **submitting** · **disabled** · error | `submitting`: Submit-Button `aria-disabled="true"` + Label `sidebar.inspector.composer.submitting`, Textarea `readOnly`; `disabled` (leerer Text): Submit ebenfalls `aria-disabled`, Grund „Text erforderlich" als `aria-describedby`. Beides ohne natives `disabled` | `--color-text-muted` |
| Zeilen-Aktionsbutton | default · hover · **busy** · **disabled** · **partial** | `busy`: Icon durch Skeleton in Icon-Größe ersetzt, `aria-busy="true"`, Button `aria-disabled="true"`; `disabled`: `aria-disabled` + Grund; `partial`: Aktion sichtbar, `aria-disabled` + `aria-describedby` auf die Zeilen-Notiz (§4.3) | `--color-text-muted`, `--color-border` |
| Resize-Handle | default · hover · focus-visible · **dragging** | `dragging` (`aria-valuenow` ändert sich, `data-dragging`): Linie 2 px `--color-primary`, Textauswahl im Dokument unterbunden, Cursor `col-resize` bleibt | `--color-primary` |
| Sheet | geschlossen · opening · open · open+detail-`inert` · closing | opening/closing nur via `--transition-fast`; bei `prefers-reduced-motion` ohne Transition. `inert` wird mit dem Öffnen gesetzt und mit dem Schließen entfernt (§4.2) | — |

**Zähler im gewählten Reiter (Kontrast).** Der Zähler liegt im Reiter-Label. Auf dem **gewählten** Reiter war
die bisherige Invertierung (`--color-on-primary` als Fläche, `--color-primary-text` als Text) falsch:
`--color-primary-text` ist **kein On-Primary-Vordergrund** — im Bauhaus-Theme kommt sie auf 1.00:1, im
Dark-Theme auf 2.98:1. Richtig ist **keine** Invertierung:

```css
/* Zähler im gewählten Reiter */
color: var(--color-on-primary);
background: var(--color-primary);
border: var(--control-border-width) solid var(--color-on-primary); /* nur auf dem gewählten Reiter */
```

Geprüfte Paare (`--color-on-primary` auf `--color-primary`): **light 6.29:1 · dark 6.29:1 · bauhaus 7.52:1**.
Der 1-px-Rahmen in `--color-on-primary` ist nötig, weil Zähler-Fläche und Reiter-Fläche sonst identisch sind
und der Zähler unsichtbar würde (H1) — die **Ziffernfarbe** bleibt dabei `--color-on-primary`, sie wird nicht
invertiert.

**Kein `white`-Literal.** Heute elfmal (`RightSidebar.module.css:67,163` · `VersionPanel.module.css:236,
245-246,255` · `TracePanel.module.css:54,175,184-185,194`), im Bauhaus-Theme navy und damit ein
Kontrastfehler (I-16). Richtig ist `--color-on-primary`.

### 6.3 Farben — Rollen, nicht Werte

| Rolle | Token | Verwendung im Inspector |
|---|---|---|
| Primär | `--color-primary` / `--color-on-primary` | gewählter Reiter, gedrückte Aktion, Fokusring |
| Fläche | `--color-surface-raised` (Panel/Sheet, Rail) · `--color-surface` (Zeilen, Karten) | Die Fläche ist **heller** als der Inhalt, Zeilen/Karten liegen **auf** ihr — dieselbe Rollenverteilung wie in den Mockups. Hover tauscht die beiden Rollen, nicht die Helligkeit Richtung „beliebig" |
| Rahmen | `--color-border`, `--color-border-hover`, `--color-border-subtle` | Trennlinien, Hover |
| Text | `--color-text`, `--color-text-muted` | Inhalt, Metadaten |
| Status | `--color-badge-{success,info,warning,danger,neutral}-{bg,text}` | `<Badge>` im Artefaktkopf (nicht im Inspector) |
| Diff | `--color-diff-{added,removed,modified,unchanged}-{bg,text}` | Diff-Reiter, Legende |
| Fehler | `--color-diff-removed-bg`, `--color-diff-removed-text` | Error-Banner |
| Fokus | `--color-focus` | `--control-focus-ring` |

Farbe trägt **nur** Workflow-Status (UI_KONZEPT §3.3). Link-Typen und Artefakt-Typen werden über **Text**
unterschieden (Typ-Pille mit Label), nicht über eine Farbskala. Diff-Zustände tragen zusätzlich ein
**Zeichen** (`+`/`−`/`~`) und eine **Legende** (Q12, WCAG 1.4.1).

### 6.4 Verbotene Muster (maschinell geprüft)

| Verboten | Prüfung |
|---|---|
| `style={{ … }}`-Objektliteral in `.tsx` | `ui-ratchet.test.ts:746-747` (`STYLE_BRACE_BASELINE = 3`, exakte Gleichheit) |
| Hex-Farbe in `.tsx` | `ui-ratchet.test.ts:954-956` (17 Vorkommen / 3 Dateien) |
| Hex-Farbe in neuem CSS | `ui-ratchet.test.ts:1039-1040` (203 / **1** Datei = `tokens.css`; eine zweite Datei macht rot) |
| `background: var(--color-primary);` in `components/**/*.css` | `ui-ratchet.test.ts:1253-1254` (`PRIMARY_FILL_BASELINE = 26`) |
| Button ohne `btn-*`-Klasse | `design-system-ratchet.test.ts` / Baseline `maxViolations: 0` |
| Emoji als UI-Glyph | dasselbe (`emoji-as-ui-glyph`, `maxViolations: 0`) — betrifft `⏱`/`≅` in `RightSidebar.tsx:344,353` |
| Unbenanntes Aktionslabel („Öffnen" mehrfach) | dasselbe (`ambiguous-button-label`) |
| Button-Geometrie off-token | dasselbe (`button-geometry-off-token`) — `--btn-h-*`, `--radius-btn`, `--radius-full` |
| Ziel unter 24 px | **kein generelles Gate**: `interactive-hit-targets.test.ts` pinnt vier Referenz-Controls (`IdChip`-`.copyButton`, `RequirementList`-`.deleteButton`, die Section-Toggles in `ArtifactSections.tsx`, das Verifikations-Badge in `TraceSpine.tsx`) plus die Token-Skala (`--space-6`, `--btn-h-sm`). Neue Inspector-Controls werden **nicht** automatisch geprüft — die 24-px-Zusage ist eine Spec-Zusage (§7 SC 2.5.8), die im Umsetzungsplan belegt werden muss |
| `1px`-Kante statt Token | Review-Befund: Kanten nutzen `var(--control-border-width)` (§6.1) |
| Schriftgröße unter `--font-size-xs` | Review-Befund: `9px`/`10px`-Literale in Zählern und Stationslabels sind unzulässig (§6.1) |

### 6.5 Auflösung der „19 Button-Höhen, 7 Radien"

Der Audit-Restwert aus #186 ist im Inspector **nicht** als 19 Höhen sichtbar, aber dieselbe Ursache:
Literale neben Tokens. Ist im Inspector: **4 Radius-Tokens** (`--radius-md` ×10, `--radius-btn` ×9,
`--radius-full` ×6, `--radius-sm` ×3) und **3 Höhen-Tokens** (32/36/44) **plus 4 Literale** (22, 24, 32, 44)
— Belege in I-17 (`RightSidebar.module.css:43-49,144-149,174-177` · `TracePanel.module.css:143,208-209,223`).

**Ziel im Inspector: 4 Höhen-Rollen, 3 Radien, 0 Literale.**

Die Badge-Zeile ist dabei die Korrektur am Ist: das echte `<Badge>` hat **22 px** Höhe und **`--radius-sm`**,
nicht `--radius-full` (`frontend/src/utils/badgeBase.ts:67` `BADGE_HEIGHT = '22px'` und `:92`
`borderRadius: 'var(--radius-sm)'`). Die Spec übernimmt den Ist-Vertrag des Badges, statt ihn zu erfinden.

| Rolle | Höhe | Radius |
|---|---|---|
| Badge (Typ/Status/Level/Version) | **22 px** — `BADGE_HEIGHT` in `utils/badgeBase.ts:67`, keine lokale Geometrie | **`--radius-sm`** (`utils/badgeBase.ts:92`) |
| dicht / Icon-only | `--btn-h-xs` (24) — nur Resize-Hitbox | `--radius-btn` (6) |
| Standard / Icon-Button / Zeile | `--btn-h-sm` (32) / `--btn-h-md` (36) | `--radius-btn` (6) |
| groß / Eingabe | `--btn-h-lg` (44) | `--radius-btn` (6) |
| Fläche (Karte, Banner) | — | `--radius-md` (12) |
| Pille (Chip, Zähler) | — | `--radius-full` |

Vier Höhen-Rollen heißt fünf Werte (22/24/32/36/44) — die Rollen zählen, nicht die Zahlen. `--radius-sm` und
`--radius-btn` sind derselbe Wert (`--radius-btn: var(--radius-sm)`), deshalb bleiben es **drei** Radien:
6 / 12 / full. `--radius-lg` (16) wird im Inspector **nicht** verwendet (nur Dialog/Sheet-Ecken außerhalb).

---

## 7. Barrierefreiheit gegen WCAG 2.2 AA

Untergrenze, nicht Ziel. Jede Zeile ist eine prüfbare Zusage; Task 6 lässt `accessibility-specialist` und
`ui-reviewer` gegen diese Tabelle prüfen.

| SC | Anforderung | Entscheidung in dieser Spec |
|---|---|---|
| **1.3.1** Info and Relationships | Landmark, Überschriften, Reiter semantisch | Der Inspector ist ein **`<aside>` mit `aria-labelledby`** auf die Kopfzeile — **ohne** explizites `role="complementary"` (das ist die implizite Rolle eines `<aside>`; ein zusätzliches Attribut wäre Rauschen). Genau **ein** Inspector je Seite; Top-Level (nicht in `<main>` verschachtelt, Q15). Reiter als `role="tablist"`/`tab`/`tabpanel` nach dem Id-Vertrag unten. **Überschriften-Ebenen:** die Detail-Überschrift und die Inspector-Überschrift sind beide **`h2`** und damit Geschwister; Bereichsüberschriften sind **`h3`**; keine Sprünge, keine `h4`/`h5` im Inspector (S12). |
| **1.4.1** Use of Color | Diff nicht nur Farbe | `+`/`−`/`~` je Zeile + Legende im Diff-Reiter (Q12) |
| **1.4.3** Contrast (Minimum) | Text ≥ 4.5:1 | ausschließlich Token-Paare. Geprüft und hier belegt sind die beiden kritischen Paare: Zähler im gewählten Reiter **6.29:1** (light), **6.29:1** (dark), **7.52:1** (bauhaus) — §6.2; Kanten **7.24:1**/`surface` bzw. **7.58:1**/`surface-raised` — §6.1. Die übrigen Inspector-Paare prüft `theme-contrast.test.ts` auf Semantik-Ebene; die konkreten Paare sind nach der Umsetzung zu messen (kein Stack heute) |
| **1.4.4** Resize text | 200 % Zoom ohne Textverlust | keine feste Höhe, die Text abschneidet (Höhen sind `min-height`); Reiter und Zeilen brechen um, statt zu kürzen; die Reiterleiste ist in R4 scrollbar **ohne** Textverlust und in R5 zweizeilig (§4.2) |
| **1.4.10** Reflow | 320 px ohne horizontale Seiten-Scrollfläche | unter 360 px brechen die Reiter in zwei Reihen um; unter 768 px ersetzt die Vollbild-Fläche den Inhalt (eine Spalte); **kein** horizontaler Seiten-Scroll bei 320 px — der einzige waagerechte Scroll ist in R4 die Reiterleiste (≤ 422 px, nicht die Seite) |
| **1.4.11** Non-text Contrast | Kanten/Glyphen ≥ 3:1 | **geprüfte Paare statt Token-Namen:** Sheet-Kante und Splitter-Ruheline sind `var(--control-border-width) solid var(--color-text-muted)` → **7.24:1** auf `--color-surface`, **7.58:1** auf `--color-surface-raised`. `--color-border-hover` bleibt **Hover-Fläche/‑Rahmen**, nicht die Ruhekante. Fokusring `--color-focus`; Stationsglyphen `--color-text` |
| **2.1.1** Keyboard | alles per Tastatur | Reiter (APG *tabs* mit **manueller Aktivierung**: ←/→ = Fokus, `Enter`/`Space` = aktivieren), Spine (Roving Tabindex), Resize (Pfeile/`Home`/`End`/`Enter`), Zeilenmenü (APG *menu*), **Rail-Zähler als `<button>`** (im Tab-Pfad) |
| **2.4.3** Focus Order | Reihenfolge = DOM | §5.1: acht Stufen, **inklusive Splitter** (`role="separator"`, `tabindex="0"`) an seiner DOM-Position vor der Kopfzeile; Skip-Link ist das erste fokussierbare Element im Detailbereich |
| **2.4.7** Focus Visible | sichtbarer Fokus | `--control-focus-ring` mit **1 px** Offset; `outline: none` ist ein Review-Befund |
| **2.4.11** Focus Not Obscured (AA, 2.2) | Fokus nicht verdeckt | Bei offenem Sheet ist der **überdeckte Detailbereich `inert`** (§4.2): kein fokussierbares Element liegt hinter dem Sheet, die **Fokusreihenfolge endet am letzten Sheet-Element**, kein Trap. `scrollIntoView({ block: "nearest" })` gilt **nur für Zeilen-Fokus**, nicht für Reiter/Überschriften. Das Sheet beginnt unter der Reiterleiste |
| **2.5.7** Dragging Movements (AA, 2.2) | Ziehen hat Ein-Punkt-Alternative | Resize-Handle: Pfeile ±16 px, `Home`/`End` (= `--inspector-w-min`/`-max`), `Enter` = ein-/ausklappen (Q13) |
| **2.5.8** Target Size (AA, 2.2) | ≥ 24 px | jeder interaktive Treffer ≥ `--btn-h-xs` — als **Spec-Zusage**, nicht als „Test deckt es ab": `interactive-hit-targets.test.ts` pinnt genau vier Referenz-Controls (`IdChip`-`.copyButton`, `RequirementList`-`.deleteButton`, `ArtifactSections`-Toggles, `TraceSpine`-Verifikations-Badge) plus die Token-Skala, **kein generelles Gate** |
| **3.2.3** Consistent Navigation | gleiche Reihenfolge über Typen | §3 Typ-Matrix, §5.1 eine Fokusreihenfolge für alle 12 Typen, §3 eine Rail-Zähler-Reihenfolge (V·D·L·K) |
| **4.1.2** Name, Role, Value | Name ohne Rohwert | `aria-label` mit **lokalisierter** Typbezeichnung, nicht `kind` (heute „Inspector for stakeholderNeed", I-11/U-11); Resize-Handle: `role="separator"`, `aria-valuenow/min/max`, `aria-valuetext` („320 Pixel") und `aria-controls` auf den Inspector (Q13); Rail-Zähler: `<button>` mit `aria-label` („Kommentare, 3 offen") + `aria-controls`, Kürzel `aria-hidden` (§3) |
| **4.1.3** Status Messages (AA) | Ansagen ohne Fokuswechsel | genau zwei Live-Regionen (§5.3), **eine Ansage je Interaktion**; `xxxLoaded` unterdrückt `tabChanged` im selben Task; Fehler nur einmal je Ereignis |

**Id-Vertrag der Reiter (S3).** Zwei IDs je Reiter, `<key>` ∈ `version | diff | links | comments`:

| Element | Attribute |
|---|---|
| Reiter | `id="inspector-tab-<key>"` · `role="tab"` · `aria-controls="inspector-panel-<key>"` · `aria-selected` (`true` / `false`) · `tabindex="0"` (gewählt) / `"-1"` (übrige) |
| Bereich | `id="inspector-panel-<key>"` · `role="tabpanel"` · `aria-labelledby="inspector-tab-<key>"` · `tabindex="0"` · inaktive Panels **`hidden`** (nicht nur `display:none` per Klasse) |
| Rail-Aufklapp-Button | `aria-expanded` (`true` / `false`) · `aria-controls` auf die Inspector-Fläche |
| Spine-Station | `aria-expanded` (Stationsliste) · `aria-controls` auf ihre Stationsliste; die Liste selbst ist eine benannte Gruppe |

Die `data-testid`s spiegeln diese IDs (`inspector-tab-<key>`, `inspector-panel-<key>`, §8.4). Grund für den
Vertrag: ohne feste IDs existieren heute drei globale Label-IDs (`inspector-version-label` u. a., I-12), und
`aria-controls`/`aria-labelledby` können ins Leere zeigen — ein Verweis, der nicht auflöst, ist ein
4.1.2-Verstoß und im Test nicht sichtbar.

**Annotationen sind kein Inhalt.** Die Ziffern-Marker der Mockups (`.mark`) sind reine Lesehilfen für dieses
Dokument. Sie tragen `aria-hidden="true"`; sonst würde der Accessible Name der Kopfzeile bzw. der
Bereichsüberschrift „Inspector 2" lauten (4.1.2, 1.3.1).

**Zusätzlich:** `prefers-reduced-motion` schaltet die Breiten-/Ein-/Ausblend-Transition ab (heute die
einzigen `@media`-Regeln im Projekt, UI_KONZEPT §6.3); `scrollbar-gutter: stable` bleibt (UI_KONZEPT §7.3);
die Reiterleiste ist bei R4 (≤ 422 px) horizontal scrollbar **ohne** Fokusverlust und bricht in R5 (< 360 px)
in zwei Reihen um (1.4.10).

**Was diese Spec nicht verspricht:** keine Aussage über tatsächlich gemessene Kontrastwerte der **neuen**
Paare — gemessen sind ausschließlich die hier genannten Token-Paare (Zähler, Kanten); keine Aussage über
Screenreader-Ausgabe in einem echten AT (kein Stack, kein AT-Lauf). Beides ist Prüfpunkt in Task 6.

---

## 8. Migration

### 8.1 Reihenfolge

Acht Schritte, jeder ein eigener PR, jeder mit grüner Suite und **ohne** Erhöhung einer Ratchet-Konstante.
Reihenfolge nach Risiko und Beweiskraft: erst der komplexeste Typ, damit der Musterfehler früh auffällt.

| # | Schritt | Warum hier | Belege / Risiko |
|---|---|---|---|
| **M1** | Shell umbauen: Reiter (manuelle Aktivierung) + Rail + `inert`-Klammer + zwei Live-Regionen + Skip-Link; Route **Requirements** | Requirements hat alles: Spine, SplitView, Provenienz, `artifact_id` | `RequirementEditors.tsx:747-752`; höchste Sichtbarkeit |
| **M2** | `stakeholderNeed`, `risk`, `adr`, `issue`, `testCase` | identische Form (Entity + Spine + `hideTraceLinks`) | `NeedsEditors.tsx:405` · `RiskEditors.tsx:120` u. a. |
| **M3** | `architecture` | Baumtiefe, `LevelBadge`, `leftMinWidth 250` | `useDerivationChain.ts:19-24` |
| **M4** | `goal` + `mainGoal` | zwei Kinds, gemeinsamer Persistenz-Slot, kein Links-Reiter für `mainGoal` | `GoalsPage.tsx:26-32` |
| **M5** | `glossary` | inline → rechte Spalte; „Verwendungen" entfällt | `GlossaryDetailPanel.tsx:79-100` |
| **M6** | `icd` | Grid-Track ersetzen; `IcdLinkedElements` entfernen | `IcdDetailPane.tsx:231-235,249-253` · `IcdDetailPane.module.css:112-116` |
| **M7** | `diagram` | Flex-Pane, letzter Typ | `DiagramDetailView.module.css:30-34` |
| **M8** | Aufräumen | `hideTraceLinks` löschen, `diff-unsupported`-Zweig löschen, `white`-Literale, Emoji-Glyphen, Pin, stale ICD-Kommentar, DE-Umlaute | I-15, I-16, I-18, I-19, I-20, I-08 |

**Warum `mainGoal` vor `glossary`:** `mainGoal` ist der einzige Typ ohne Spine **und** ohne Links; er beweist,
dass die Typ-Matrix wirklich typabhängig greift. `glossary` beweist danach die Umstellung der Position.

### 8.2 Rückfallpfad

- **Kein Feature-Flag, kein Parallelbetrieb zweier Shells.** Die Migration ist pro Route ein Austausch des
  Mount-Punkts. `RightSidebar` bleibt bis M8 importierbar, wird aber ab M1 von keiner migrierten Route mehr
  verwendet.
- **Rückfall = Revert eines PRs.** Da jede Route einzeln umgestellt ist, kostet ein Rückfall genau eine
  Route, keine gemeinsame Zustandsänderung. Es gibt keinen geteilten Reiterzustand über Routen hinweg
  (Schlüssel enthalten `kind` und ID, §5.4).
- **Kompatibilitäts-Shim:** `hideTraceLinks` wird ab M1 an den Aufrufstellen **gelöscht**, nicht ignoriert.
  Die Shell leitet „hat Links-Reiter" aus `kind` ab (Typ-Matrix §3). Kein stiller Prop, der nichts tut
  (Lehre aus I-08).
- **Daten-Rückfall:** Die alte `VERSIONS_FETCHERS`/`mapKindToDiffEntityType`-Zuordnung bleibt unverändert;
  die Spec ändert keine Endpunkte (außer der D6-Ergänzung, falls freigegeben).

### 8.3 Ratchet-Auswirkung (`frontend/src/test/ui-ratchet.test.ts`)

| Konstante | Wert | Regel | Auswirkung dieser Spec |
|---|---|---|---|
| `STYLE_BRACE_BASELINE` (`:746-747`) | **3**, exakte Gleichheit | kein `style={{`-Literal | Neue Shell: **0** Literale. Dynamische Breite über CSS-Custom-Property; ein `style`-Prop mit **benanntem** `CSSProperties`-Objekt ist erlaubt (bestehendes Muster `style={asideStyle}`, `RightSidebar.tsx:269-308`), ein Inline-Literal nicht. |
| `HEX_LITERAL_OCCURRENCE_BASELINE` / `_FILE_BASELINE` (`:954-956`) | 17 / 3 | keine Hex-Farbe in `.tsx` | **0** neue; Fokusring und Farben nur über `var(--…)`. |
| `HEX_LITERAL_CSS_*` (`:1039-1040`) | 203 / **1** | Hex nur in `tokens.css` | Neue CSS-Module dürfen **kein** Hex enthalten (sonst Dateizahl 2 → rot). |
| `PRIMARY_FILL_BASELINE` (`:1253-1254`) | 26 | kein `background: var(--color-primary);` in `components/**/*.css` | **0** Delta: der gewählte Reiter nutzt `.btn-tab` aus `global.css` (außerhalb des Scan-Bereichs, `ui-ratchet.test.ts:1343`). Kein eigener Primär-Fill im Inspector-CSS. |
| `TREE_IMPLEMENTATION_BASELINE` (`:1115-1118`) | 1 | genau eine Baum-Implementierung | unberührt (kein neuer Baum) |
| `STATUS_BADGE_*` / `LEVEL_BADGE_*` (`:1133-1134`, `:1164-1165`) | 1 / 1 | genau eine Implementierung | unberührt; Badges nur über `<Badge>`/`<StatusBadge>`/`<LevelBadge>` |
| `LOCAL_TOAST_BASELINE` (`:1205-1206`) | 2 | kein page-lokaler Toast | unberührt (Inspector nutzt kein Toast) |

**Zusätzlich zu beachten (nicht `ui-ratchet`, aber gleiche Wirkung):**

- `design-system-ratchet.test.ts` + `design-system-ratchet.baseline.json`: alle vier Checks stehen auf
  `maxViolations: 0`. Neue Buttons brauchen `btn-*`, neue Labels müssen das Objekt benennen, Geometrie muss
  aus `--btn-h-*`/`--radius-btn`/`--radius-full` kommen. **Konkrete Folge:** die drei Sektions-Glyphen im
  eingeklappten Streifen (`RightSidebar.tsx:344,353` — `⏱`, `≅`) sind Emoji-Glyphen und müssen durch Icons
  ersetzt werden; der Rail bekommt `data-testid` je Zähler (heute fehlen sie, I-20/§3.1).
- **Die zwei Inspector-Exemptions in der Baseline müssen im selben PR verschwinden, sonst ist der Lauf
  rot.** Beide Einträge exemptieren genau den Code, den diese Spec ersetzt:
  - `design-system-ratchet.baseline.json:89` — `button-missing-design-system-class::components/shared/
    ArtifactInspector/RightSidebar.tsx::div[data-testid=artifact-inspector-resize]`. Der Eintrag wird
    **gelöscht** (die Datei existiert nach M8 nicht mehr; ein Stehenlassen ist stale → rot). Achtung, der
    Check greift beim neuen Griff erneut: er meldet **jedes** intrinsische Element mit `onPointerDown`/
    `onClick` ohne `btn-*`-Klasse (`design-system-ratchet.test.ts:583-620`). Zwei zulässige Auflösungen —
    eine ist im PR zu wählen und zu belegen:
    (a) *empfohlen:* der Griff trägt `btn-icon` als Chrome-Haken (Geometrie bleibt `--inspector-resize-hit`,
    24 px, per Modul-Regel) → **keine** Exemption nötig;
    (b) der Griff bleibt chrome-los (kein Button-Look): dann wird im **neuen** Modul eine Exemption mit
    Begründung auf den **neuen** `data-testid` eingetragen — nicht der alte Key umgeschrieben.
  - `design-system-ratchet.baseline.json:116` — `button-geometry-off-token::components/shared/
    ArtifactInspector/TracePanel.module.css::.skeletonChip`. Der Skeleton-Chip bekommt
    `min-height: var(--btn-h-sm)` (bzw. entfällt mit `TracePanel`); der Eintrag wird im selben PR entfernt.
  - Regel daraus: **jede Exemption, deren Ziel in diesem PR verschwindet, wird im selben PR gelöscht** —
    Baseline-Einträge sind kein Archiv.
- **Flächen-Fills nur über `--color-card-active-bg`.** Jede „gewählte Zeile"/„gewählte Karte" nutzt
  `background: var(--color-card-active-bg)`, nie `background: var(--color-primary)`. Andernfalls steigt
  `PRIMARY_FILL_BASELINE` um 1 und die Ratchet ist rot (§8.3, oberste Tabelle). Ausnahme bleibt der
  `.btn-tab`-Reiter, weil dessen Regel in `global.css` liegt (`ui-ratchet.test.ts:1343`).
- `interactive-hit-targets.test.ts`: **kein generelles 24-px-Gate.** Der Test pinnt vier Referenz-Controls
  und die Token-Skala (SC 2.5.8, §7); die Ausweitung des Verifikations-Badges auf alle Stationen (§2.3)
  muss die `btn-ghost`-Geometrie behalten, weil genau diese Komposition dort gepinnt ist — neue Controls
  sind damit **nicht** automatisch abgedeckt.
- `design-tokens.test.ts`: jeder `var(--x)` muss in `tokens.css` **oder im selben Modul** deklariert sein →
  Komponenten-Aliase (§6.1) lokal halten.
- **Messregel:** Wer eine Konstante senkt, misst sie im selben PR neu und senkt sie mit; **nie** erhöhen
  (`ui-ratchet.test.ts:16-22`).

### 8.4 Je-Typ-Checkliste (Definition of Done pro migrationsschritt)

1. Mount-Punkt ersetzt, `hideTraceLinks` an der Aufrufstelle gelöscht.
2. Artefaktkopf zeigt ID **und** Status (sonst hat der Typ die Information nirgends, §2.2).
3. Kommentar-Pfad liefert HTTP 200 (`artifact_id` übergeben, §11 D5).
4. Reiter „Links" vorhanden — außer `mainGoal`; Reiter nicht gerendert, nicht deaktiviert.
5. Verifikations-Badge erscheint an jeder Station mit Daten.
6. Kein zweiter Trace-Ort mehr im Detail (ICD/Glossary/Sonstiges).
7. `data-testid`-Inventar ergänzt: `inspector-tab-<key>`, `inspector-panel-<key>`, `inspector-rail`,
   `inspector-rail-open`, `inspector-rail-count-<key>`, `inspector-close`, `inspector-live`, `inspector-alert`,
   `inspector-diff-pair`, `inspector-baseline-select`. IDs und Testids sind dieselben (§7 Id-Vertrag).
8. `RightSidebar.a11y.test.tsx`-Muster (jeder Button hat einen Namen) bleibt grün — auf den neuen Reitern.
9. KEIN `style={{`, kein Hex, kein Emoji, keine Literal-Geometrie, keine Schriftgröße unter
   `--font-size-xs` (§8.3, §6.1).
10. Visuelle Prüfung bei 1440 / 1024 / 768 / 320 px **mit laufendem Stack** (heute nicht möglich, §0);
    bei 320 px ohne horizontalen Seiten-Scroll (§4.2, 1.4.10).
11. Die zwei Inspector-Exemptions der Design-System-Baseline sind im selben PR entfernt (§8.3).

---

## 9. Nicht-Ziele

- **Keine Link-Validität** („passen zwei verknüpfte Artefakte inhaltlich noch zusammen?"). Q9 beschreibt das
  als DOORS-Next-Konzept; ReqogniLoom hat es nicht. Es wird **nicht** als Anforderung erfunden.
- **Keine Live-Zusammenarbeit**, keine Präsenzanzeige, keine Kommentar-Threads/Benachrichtigungen.
- **Kein zweiter Inspector** auf einer Seite (Q15: mehrere Complementary-Landmarks brauchen je ein Label —
  wir vermeiden den Fall).
- **Keine dritte Offenbarungsebene** (Q1): kein Unterpanel, kein Popover-Dialog außer destruktiver
  Bestätigung.
- **Keine Änderung** an Artefakt-Formularen, Listen, Navigation, Rechten, Export (PDF/ReqIF), Selektion.
- **Kein Diff-Rendering-Umbau** von `ArtifactDiff` (nur Einbettung + Legende + Fehlerzustand). Split/Unified
  ist ein eigener Gegenstand (Q11).
- **Keine neuen Design-Tokens.** Nur Komponenten-Aliase (§6.1).
- **Kein Backend-Feature** außer der in §11 D5/D6 ausdrücklich zur Entscheidung gestellten Ergänzung.
- **Keine Aussage über Performance** (Ladezeiten, Request-Zahl ist kein Zeitmaß).

---

## 10. Quellenverweise auf Task 4

Alle Quellen mit URL und Abrufdatum 2026-11-11 in
[`2026-11-inspector-best-practice.md`](../../analysis/2026-11-inspector-best-practice.md). Hier nur die
Zuordnung „Entscheidung → Quelle". Keine Quelle ist aus dem Gedächtnis ergänzt.

| Entscheidung in dieser Spec | Quelle | Muster |
|---|---|---|
| §2.1 vier Reiter, höchstens zwei Ebenen | Q1 (NN/g, Progressive Disclosure) | M2 |
| §2.1 Panel statt Drawer; Sheet nur als Modus | Q5 (GitLab Pajamas), Q2 (NN/g Side Sheet), Q3 (PatternFly Drawer) | M1, M3 |
| §2.1/§4.2 Overlay-Modus bei mittlerer Breite, Vollbild unterhalb | Q3, Q4 (PatternFly Primary-Detail), Q5 | M3 |
| §2.3 Spine = Kette, Reiter = Inventar | Q6 (Jama Trace View), Q9 (DOORS Next Links Explorer) | M1, M2 |
| §2.3 Richtung und Suspect am Link sichtbar | Q7 (Jama Relationships) | M1 |
| §2.3 kompakte Link-Zeile (Typ + ID + Titel + Status) | Q8 (Jira Link work items) | M2 |
| §2.2/§2.3 ein Ort je Information | Q1, Q5, UI_KONZEPT §3.4 | M2 |
| §4.2 Rail-Öffnung, Auswahl- und Leerzustand | Q4 (PatternFly Primary-Detail) | M1 |
| §4.4/§6.1 Splitter nur wo Platz gebraucht wird | Q3, Q4 | M4 |
| §5.2 Resize-Tastaturvertrag (`separator`, Pfeile, Home/End, Enter) | Q13 (WAI-ARIA APG Window Splitter) | M4 |
| §5.1/§5.3 Disclosure + Live-Region | Q14 (APG Disclosure), Q15 (APG Complementary Landmark) | M5 |
| §7 Landmark/Label/Fokus | Q15, Q14 | M5 |
| Diff: zwei Endpunkte explizit, Paar reproduzierbar | Q10 (GitHub Comparing commits) | M6 |
| Diff: Rauschen reduzierbar, Änderungsarten + Legende | Q11 (GitHub Branches), Q12 (Confluence Page History) | M6 |

**Nicht verwendet** (in Task 4 dokumentiert, nicht erreichbar): Material Design 3, IBM Carbon, Shopify
Polaris. Die Spec stützt sich deshalb für Panel-Muster auf PatternFly, Pajamas und NN/g.

---

## 11. Offene Entscheidungen für Daniel

Der Plan verlangt, offene Gestaltungsfragen **einzeln** zu stellen, nicht gesammelt zu entscheiden. Diese
Liste ist das Gate für Task 6. Jede Zeile: Frage, Optionen, Empfehlung, Blockadewirkung.

**D1 — Mindestbreiten bei 1440 px (blockierend für §4).**
Frage: Darf der Zustand „Inspector offen" die Konzept-Mindestbreiten unterschreiten?
- **A (Empfehlung):** Liste 320, Inhalt 508, Inspector 320. Ein Inspector ist ab 1440 standardmäßig offen;
  der Inhalt liegt 12 px unter `--detail-min` (520). Formulare müssen bei 508 px funktionieren.
- **B:** Mindestbreiten 380/520 halten → Inspector unter 1600 px standardmäßig **zu** (Rail). Löst U-05 nicht.
- **C:** Unter 1600 px **Overlay** statt inline. Verdeckt beim Öffnen den Inhalt, den der Nutzer bearbeitet.
Empfehlung: **A**, mit der Auflage, 508 px im Umsetzungsplan visuell zu prüfen.

**D2 — Arbeitsteilung Spine ↔ Reiter „Links" (blockierend für §2).**
Frage: Zeigt der Reiter „Links" auch die Ableitungs-/Verifikationszeilen?
- **A (Empfehlung):** Nein — nur Zusammenfassungszeile + Sprung in die Spine. Ein Link ist als Zeile an
  genau einer Stelle lesbar.
- **B:** Ja, vollständiges Inventar zusätzlich. Zwei Orte, zwei Filter, Doppelpflege (das heutige U-06).
- **C:** Reiter „Links" entfällt ganz; nur Spine + CRUD-Panel. Verliert `mitigates`/`decides`-Sicht.
Empfehlung: **A**.

**D3 — Bauform (blockierend für §4.2/R3–R5).**
Frage: Panel oder Drawer als Grundmuster?
- **A (Empfehlung):** **Panel** (Dauerinhalt), das auf schmalen Breiten in einen **Overlay-Modus desselben
  Bauteils** wechselt. Ein Bauteil, drei Formen (Panel/Rail/Sheet).
- **B:** Drawer überall (transient). Widerspricht Q5: Version/Links/Kommentare sind Dauerinhalt.
- **C:** Zwei Bauteile (Panel ≥1024, Drawer <1024). Doppelte Implementierung, zwei A11y-Verträge.
Empfehlung: **A**.

**Konsequenz aus dem Review (B1) — zur Empfehlung A gehörend, nicht optional:** Das Sheet bleibt non-modal
(kein Fokus-Trap **im** Sheet), aber der **überdeckte Detailbereich wird `inert`** (§4.2). Ohne diese
Klammer ist „non-modal" keine zulässige Bauformentscheidung, sondern ein WCAG-2.4.11-Verstoß: der Fokus
könnte in einen Bereich wandern, der hinter dem Sheet liegt und nicht sichtbar ist. Der Preis ist benannt:
ein `inert`-Attribut, das mit Öffnen und Schließen gesetzt/entfernt werden muss — eine Zeile Code an einer
Stelle, kein zweites Bauteil.

**D4 — Reiter oder gestapelte Abschnitte mit Ankern (nicht blockierend).**
- **A (Empfehlung):** Vier Reiter, ein Bereich sichtbar. 0 Scrolls bis zum Bereichseinstieg (M-3), klare
  Landmark-Struktur, ein `tabpanel`.
- **B:** Gestapelt + Ankerleiste. Weniger Umbau, aber weiterhin eine Scrollfläche und zwei „Direktziele"
  pro Information.
Empfehlung: **A**.

**D5 — Id-Space der Kommentare (blockierend für M-1).**
Frage: Woher bekommt `CommentPanel` die generische Artifact-PK?
- **A (Empfehlung):** Die Shell bekommt **zwei** IDs: `entityId` (Version/Diff/Trace) und `artifactPk`
  (Kommentare). Die Routen reichen `artifact_id` durch (bei 7 Typen vorhanden:
  `RequirementEditors.tsx:742` · `NeedsEditors.tsx:405` · `RiskEditors.tsx:120` · `AdrEditors.tsx:150` ·
  `IssueEditors.tsx:120` · `TestCaseEditors.tsx:342` · `ArchitectureEditors.tsx:431`).
- **B:** Backend löst die Entity-ID auf (`comment_service`). Widerspricht der bewussten 404-Entscheidung
  (#983, `comment_service.py:100-113`) und versteckt Fehlaufrufe.
- **C:** Kommentare bleiben defekt. M-1 nicht erreichbar.
Empfehlung: **A**. **Offen bleibt:** `glossary`, `icd`, `diagram`, `goal`, `mainGoal` — dort ist die
Verfügbarkeit von `artifact_id` **nicht geprüft**; `mainGoal` hat laut Code **kein** `artifact_id`
(`GoalsPage.tsx:26-32`) und braucht eine Typ-/Backend-Erweiterung oder bleibt ohne Kommentare.

**D6 — Baseline-Bezug (blockierend für M-2; siehe N-01).**
Frage: Wie wird „gepinnte Version dieses Artefakts in Baseline X" beschaffbar?
- **A (Empfehlung):** Neuer, kleiner Lese-Endpunkt
  `GET /api/v1/artifacts/<pk>/baselines/` → `[{id, name, scope, pinned_version}]`, aufgelöst aus den
  Baseline-Einträgen, tenant-/RLS-gesichert. Ein Request, keine N+1, kein Client-Filter über alle Baselines.
- **B:** Nur `document`-Scope unterstützen (dort ist der Pin eindeutig). Projekt-/Global-Baselines bleiben
  außen vor → U-02 nur halb gelöst.
- **C:** Client-seitig alle Workspace-Baselines + Details laden und filtern. N+1 über die Detail-Antwort
  (`entries` nur im Detail, N-01), potenziell hunderte Einträge je Baseline. Abzulehnen.
- **D:** Baseline-Bezug streichen; M-2 gilt nur für Version→Version (Ersatz-Zielwert §1.1).
Empfehlung: **A**, Umsetzung im B2.1-Plan, nicht in B2.

**D7 — „Anheften" (nicht blockierend).**
Heute ein toter Schalter: `pinned` wirkt nur auf `aria-pressed` und Farbe (`RightSidebar.tsx:153,160,381-395`,
I-08/U-10).
- **A (Empfehlung):** Entfernen. Ein Bedienelement ohne Wirkung ist ein Fehler (H1, H10).
- **B:** Mit Bedeutung füllen: „Panel bleibt beim Wechsel des Artefakts offen und behält den Reiter".
  Braucht eine definierte Navigationssemantik (und ist mit §5.4 teilweise schon erreicht).
- **C:** Behalten als rein visuelle Markierung. Dann muss das Label „Markiert" heißen, nicht „Anheften".
Empfehlung: **A**; falls B gewünscht, ist es ein eigenes Ticket.

**D8 — Glossary-Einbindung (nicht blockierend, aber Typ-Matrix).**
Heute ist die Shell bei Glossary ein Block **unter** der Überschrift „Verwendungen" in der Detailspalte
(I-01/U-15).
- **A (Empfehlung):** Rechte Spalte wie alle anderen Typen (Panel/Sheet/Rail nach Breite), „Verwendungen"
  entfällt als eigener Block (der Reiter „Links" übernimmt, Label bleibt „Verwendungen").
- **B:** Inline-Block behalten, nur in Reiter umbauen. Billiger, aber der Typ bleibt strukturell anders —
  genau der Review-Fokus „Typ-Unterschiede ohne fachliche Ursache".
Empfehlung: **A**.

---

## 12. Entschieden ohne Rückfrage (Transparenz)

Diese Punkte sind **keine** offenen Fragen; sie sind hier begründet, damit nichts stillschweigend passiert.

| Entscheidung | Begründung |
|---|---|
| Standardreiter = „Version" für alle Typen | Konsistenz (H4), Migrationsnähe, häufigste nicht-blockierte Aufgabe (§3) |
| Genau vier Bereiche (kein fünfter „Herkunft") | Provenienz ist eine Zeile im Reiter „Version"; ein eigener Reiter für ein Badge wäre Verschwendung (Q1) |
| Status und ID **nicht** im Inspector | Identität gehört in den Artefaktkopf (UI_KONZEPT §3.1, §8.2); verhindert einen zweiten Ort (§2.2) |
| Reiterleiste auf `.btn-tab` | existiert bereits, token-konform, `background: var(--color-primary)` liegt in `global.css` und bewegt die Ratchet nicht (§8.3) |
| Verifikations-Badge an **allen** Stationen | Daten liegen vor (`useDerivationChain.ts:378-395`), heutige Einschränkung ist der Fehler (U-07) |
| Kein Fokus-Trap im Sheet, aber `inert` dahinter | non-modal (Q2/Q5) — ein Trap wäre eine falsche Modalitätszusage; der überdeckte Detailbereich ist dennoch `inert`, sonst wandert der Fokus hinter das Sheet (WCAG 2.4.11, §4.2) |
| Höchstens zwei Live-Regionen | eine pro Inspector statt einer pro Panel (U-03, WCAG 4.1.3) |
| Rail zeigt Zähler statt nur Glyphen | U-05: eingeklappt muss die Funktion sichtbar bleiben (H1) |
| Achse „Version/Diff/Links/Kommentare" statt „Details/Verlauf/Trace" | Begriffe aus dem bestehenden i18n-Namensraum (`sidebar.version`, `sidebar.diff`, `comments`), keine neuen Produktbegriffe. Der Reiter „Links" bekommt einen eigenen Schlüssel, weil `sidebar.trace.title` „Trace-Links"/„Trace Links" heißt und damit die Teilmenge benennt, die **nicht** als Zeilen dort steht (§5.5) |

---

## 13. Anhang: Abgleich mit Task 3 (jeder Verstoß adressiert?)

| U-ID | Schwere | Adressiert durch | Status |
|---|---|---|---|
| U-01 | 4 | §11 D5, M-1, §4.3 Fehlerzustand | **Lösung hängt an D5** |
| U-02 | 3 | §11 D6, M-2 | **Lösung hängt an D6** |
| U-03 | 3 | §2.2 Paar-Zeile, §5.3 eine Live-Region | gelöst |
| U-04 | 3 | §2.1 vier Reiter, M-3, §5.4 URL-Zustand | gelöst |
| U-05 | 3 | §4.2 Default offen ab 1280, Rail mit Zählern | gelöst |
| U-06 | 3 | §2.4 ICD/Glossary-Doppelung entfällt | gelöst |
| U-07 | 3 | §2.3 Badge an allen Stationen | gelöst |
| U-08 | 3 | nicht adressiert — „keine Abdeckung" bleibt nur für vorhandene Stationen sichtbar (`TraceSpine.tsx:211-221`) | **offen, eigenes Ticket** |
| U-09 | 3 | §5.4 Zustandserhalt; Navigation selbst unverändert | teilweise |
| U-10 | 2 | §11 D7 | hängt an D7 |
| U-11 | 2 | §7 SC 4.1.2 (lokalisiertes Label), §5.3 (Datumsformat im Kommentar) | gelöst |
| U-12 | 2 | §7 SC 1.3.1 (ein Landmark, `aria-labelledby`) | gelöst |
| U-13 | 2 | §5.1 deaktivierte Glieder mit Grund | gelöst |
| U-14 | 2 | §5.1 Skip-Link, ein Tab-Stopp pro Leiste, `Alt+I` | gelöst |
| U-15 | 3 | §11 D8, §8 M5 | hängt an D8 |
| U-16 | 2 | **nicht adressiert** — `V·n` bleibt eine Untergrenze (`useDerivationChain.ts:30-38`); die Spec ändert die Zählung nicht | **offen** |
| U-17 | 2 | §4.3 einheitlicher Fehlerzustand mit Retry | gelöst |
| U-18 | 2 | §8 M6 (Grid-Track → Panel/Sheet) | gelöst |

**U-08 und U-16 bleiben bewusst offen.** Beide sind Datenmodell-/Zählfragen (fehlende Station, Untergrenze
des Zählers), keine Darstellungsfragen. Sie hier „mitzulösen" würde die Messlatte verwässern; sie gehören in
je ein eigenes Ticket, sonst entsteht der Eindruck, der Neuentwurf behebe sie.

---

## 14. Review-Nachweis (2026-11-12)

Einarbeitung der Review-Befunde vom 2026-11-12. Eine Zeile je Befund-ID; „Stelle" nennt den Abschnitt, in
dem die Änderung belegbar ist. Die Mockups sind jeweils mitgezogen (Spalte „Stelle" nennt die Datei, wenn
die Änderung dort liegt).

| Befund | Änderung | Stelle |
|---|---|---|
| **B1** | Sheet bleibt non-modal, aber der überdeckte Detailbereich ist bei offenem Sheet `inert` (Liste bleibt bedienbar); Fokus endet am letzten Sheet-Element; `Esc`/Schließen gibt den Fokus an den Auslöser zurück. §12-Begründung auf „kein Trap im Sheet, `inert` dahinter" präzisiert; D3 um diese Konsequenz ergänzt. Mockup kennzeichnet den verdeckten Bereich als `inert`. | §4.2 (Sheet-Zustand), §7 SC 2.4.11, §11 D3, §12; `narrow-768.html` |
| **B2** | 1.4.11-Zusage ersetzt: Sheet-Kante und Splitter-Ruheline `1px solid var(--color-text-muted)` — **7.24:1** auf `--color-surface`, **7.58:1** auf `--color-surface-raised`; `--color-border-hover` nur noch Hover. Resize-Handle hat die Linie auch im Ruhezustand. | §7 SC 1.4.11, §6.1 (Kanten-Tabelle, Resize-Handle-Zeile); Mockups (`.resize::after`) |
| **B3** | Zähler im gewählten Reiter: `color: var(--color-on-primary)` auf `background: var(--color-primary)` (light 6.29:1, dark 6.29:1, bauhaus 7.52:1), **keine** Invertierung; `--color-primary-text` ist kein On-Primary-Vordergrund. 1-px-Rahmen in `--color-on-primary` hält den Zähler sichtbar. | §6.2 (Zähler-Absatz); `narrow-768.html`, `requirements.html`, `glossary.html` |
| **S1** | Splitter ist Stufe 5 der Fokusreihenfolge, mit `role="separator"` und `tabindex="0"` an seiner DOM-Position (erstes Kind der Inspector-Fläche, vor der Kopfzeile) — dokumentiert, nicht umsortiert. | §5.1, §7 SC 2.4.3 |
| **S2** | Reiterwechsel mit **manueller Aktivierung** (Pfeile = Fokus, `Enter`/`Space` = aktivieren, weil jeder Reiter einen Fetch auslöst); Fokus bleibt auf dem Tab; `scrollIntoView({block:"nearest"})` nur für Zeilenfokus; `tabindex="-1"` auf Überschriften nur als Skip-Link-Ziel (Kopfzeilen-Container trägt die übrigen Fokusziele). | §5.1, §5.2, §1.1 M-3, §7 SC 2.1.1 |
| **S3** | Id-Vertrag: `inspector-tab-<key>` (`role="tab"`, `aria-controls`, `aria-selected`, `tabindex` 0/−1) ↔ `inspector-panel-<key>` (`role="tabpanel"`, `aria-labelledby`, `tabindex="0"`, inaktive `hidden`); Rail-Aufklapp-Button `aria-expanded`+`aria-controls`; Spine-Station `aria-controls` auf ihre Stationsliste. | §7 (Id-Vertrag), §8.4 |
| **S4** | Rail und Sheet sind **ein** DOM-Knoten; im Sheet-Zustand ist der Rail-Inhalt nicht gerendert (nicht nur verdeckt). | §2.1, §4.2 |
| **S5** | Ein Disabled-Vertrag: `aria-disabled="true"` ohne natives `disabled`, Grund als `aria-describedby` auf sichtbarem Text plus `title`; §4.3 und §6.2 angeglichen, je Bauteil konkretisiert. | §4.3, §6.2 |
| **S6** | Live-Region-Schlüssel ergänzt: `commentCreated`, `commentResolved`, `commentDeleted`, `linkDeleted`, `retrySucceeded`, `retryFailed` (plus `fullscreenOpened`). Regel: genau eine Ansage je Interaktion; `xxxLoaded` unterdrückt `tabChanged` im selben Task. | §5.3 |
| **S7** | Composer-Fehlerpfad: Meldung in der alert-Region, `aria-invalid` + `aria-describedby="comment-error"` auf der Textarea, Fokus auf die Textarea, eingegebener Text bleibt erhalten. | §4.3 |
| **S8** | Vollbild (R5): Fokus auf die Kopfzeile (`tabindex="-1"`), zurück auf den Auslöser, Ansage über die polite-Region (`fullscreenOpened`). | §5.1, §5.3 |
| **S9** | Einklappen (Splitter-`Enter` oder Schließen) → Fokus auf den Rail-Aufklappen-Button; Ausklappen → auf den Kopfzeilen-Container. | §5.1, §5.2 |
| **S10** | WCAG 1.4.10 und 1.4.4 in §7 ergänzt; in R5 brechen die Reiter unter 360 px in zwei Reihen um, bei 320 px kein horizontaler Seiten-Scroll. | §7, §4.2, §5.1 |
| **S11** | Rail-Zähler sind `<button>` mit `aria-label` („Kommentare, 3 offen") und `aria-controls`; Klick öffnet das Sheet auf dem zugehörigen Reiter; Kürzel V/D/L/K `aria-hidden`. | §3, §6.1, §7 SC 4.1.2; Mockups (Rail) |
| **S12** | Überschriften-Ebenen vereinheitlicht: Detail-`h2` und Inspector-`h2` sind Geschwister, Bereichsüberschriften `h3`; die Mockups nutzen `h2`/`h3` statt `h3`/`h4`/`h5`. | §7 SC 1.3.1; alle drei Mockups |
| **H1** | Explizites `role="complementary"` entfällt; Zusage lautet „`<aside>` mit `aria-labelledby`". | §7 SC 1.3.1; `requirements.html` (Legende) |
| **H2** | Annotationsziffern (`.mark`) sind `aria-hidden="true"` und damit nicht Teil des Accessible Name der Überschrift. | §7 (Annotationen), Mockups (`.mark`) |
| **H3** | Rail-Zähler-Typografie auf `--font-size-xs`; kein `9px`-Literal; generell keine Schriftgröße unter `--font-size-xs`. | §6.1; alle drei Mockups |
| **H4** | `Esc` im Composer verwirft keinen Text (Feldwert bleibt im Zustand erhalten, auch über Schließen/Öffnen). | §5.1, §5.2 |
| **H5** | `Esc` schließt die innerste Ebene in fester Priorität: Stationsliste → Sheet/Vollbild. | §5.1 |
| **H6** | Fokus-Rückgabe mit Fallback-Kette: Auslöser → Rail-Aufklappen-Button → Kopfzeilen-Container (nie `<body>`). | §5.1 |
| **UB1** | Breiten-Token benannt: `--inspector-w-min: 280px`, `--inspector-w-default: 320px`, `--inspector-w-wide: 360px`, `--inspector-w-max: 520px`; §4.1/§4.2/§5.2 referenzieren die Namen. | §6.1, §4.1, §4.2, §5.2 |
| **US1** | Badge-Zeile korrigiert: `borderRadius: var(--radius-sm)` und `minHeight: 22px` (`utils/badgeBase.ts:92,67`), nicht `--radius-full`; Ziel jetzt „4 Höhen-Rollen, 3 Radien, 0 Literale". | §6.1, §6.5; Mockups (`.badge`) |
| **US2** | Zustände je Bauteil ergänzt: Filter-Chip `selected`, Composer `submitting`/`disabled`, Zeilen-Aktionsbutton `busy`/`disabled`/`partial`, Resize-Handle `dragging`, Sheet-Zustände. | §6.2 (Zustände je Bauteil) |
| **US3** | i18n-Key-Tabelle DE/EN für Reiter, Aktionen, Zähler (`offen: {{n}}`), je Bereich ein Empty-Satz; Wurzel `sidebar.inspector.*`; Platzhalter einheitlich `{{panel}}`; `terminologyLabel("glossary.usages")` für Glossary; Reiter „Links" gegen `sidebar.trace.title` („Trace-Links"/„Trace Links") geprüft und die Abweichung begründet. | §5.5, §4.3, §5.3, §12 |
| **US4** | Ratchet-Exemptions: `design-system-ratchet.baseline.json:89` (`button-missing-design-system-class`, `RightSidebar.tsx`-Resize-Handle) und `:116` (`button-geometry-off-token`, `.skeletonChip`) müssen im selben PR entfernt werden; Flächen-Fills ausschließlich `--color-card-active-bg` (sonst `PRIMARY_FILL_BASELINE` +1). | §8.3, §8.4 |
| **US5** | Flächenrolle korrigiert: Panel/Sheet = `--color-surface-raised`, Zeilen/Karten = `--color-surface` (wie die Mockups); Hover tauscht die Rollen. | §6.1, §6.2, §6.3 |
| **UH1** | I-Tabelle ergänzt (I-01 … I-21), I-18 und I-19 mit eigener Zeile; bei I-13 ist der `SplitView`-`spine`-Slot explizit genannt. | §0.1, §8.1 M8 |
| **UH2** | `requirements.html`: Liste auf 320 px / Inhalt 508 px umgestellt (448 px ist Untergrenze, nicht R2-Default); Mikro-Typografie auf `--font-size-xs`; fehlende Aliase `--inspector-w-max`, `--inspector-tab-h`, `--inspector-row-h` definiert; `.badge` auf 22 px. | `requirements.html`; §6.1, §4.1 |
| **UH3** | Kantenbreite `var(--control-border-width)` statt `1px`; Fokus-Offset auf 1 px angeglichen und als Token-Ausnahme begründet (es gibt kein Offset-Token). | §6.1, §6.2, §7 SC 2.4.7; alle drei Mockups |
| **UH4** | `interactive-hit-targets.test.ts` nicht mehr als generelles 24-px-Gate dargestellt — nur vier Referenz-Controls plus Token-Skala. | §6.4, §7 SC 2.5.8, §8.3 |
