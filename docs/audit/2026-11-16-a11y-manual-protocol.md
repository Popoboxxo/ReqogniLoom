---
type: a11y-manual-protocol
status: pending
date: 2026-11-16
author_agent: e2e-tester
requirement: REQ-056
finding: A11Y-002
signoff: PENDING
---

# Manuelles Screenreader-/Tastatur-Protokoll — S3.3 / A11Y-002

> **Status: manuelle Prüfung PROTOKOLLIERT, NICHT durchgeführt — Konformitätsaussage erst nach menschlichem Sign-off.**
>
> Dieses Dokument ist eine **leere, vorbereitete Vorlage**. Es wurden **keine** NVDA-, JAWS- oder
> VoiceOver-Sitzungen durchgeführt, keine Browser/Screenreader-Kombination getestet und keine
> Befunde bestätigt. Jede Matrixzelle ist bewusst `offen/PENDING — menschliche Freigabe erforderlich`.
> Ein automatisiertes axe-Gate (selbst mit `wcag22aa`) deckt nur ca. 30–40 % der WCAG-Erfolgskriterien
> ab und ist **kein** Konformitätsnachweis. Die Aussage „wcag22aa" im CI-Gate ist ein Tag-Set, keine
> Konformitätsaussage.

## 1. Ziel und_scope

- Zielstufe: **WCAG 2.2 AA** (entspricht EN 301 549 für öffentliche Auftraggeber).
- Geprüfte Artefakte: ReqogniLoom-Frontend (React 19), seeded Demo-Tenant, 5 Themes
  (`dark`, `light`, `bauhaus`, `nordic`, `sepia`), 24 kuratierte Routen.
- Automatisierte Vorarbeit: `e2e/tests/a11y-smoke.spec.ts` (CI-Shard 6) und
  `e2e/a11y-followup.js` (manuell). Deren grünes Ergebnis ersetzt **keine** der unten
  aufgeführten manuellen Prüfungen.

## 2. Umgebung / Versionen — ALLE FELDER offen

| Feld | Wert | Status |
|---|---|---|
| Datum der Prüfung | — | offen/PENDING — menschliche Freigabe erforderlich |
| Prüfer(in) (Name) | — | offen/PENDING — menschliche Freigabe erforderlich |
| App-Version / Build | — | offen/PENDING — menschliche Freigabe erforderlich |
| Git-Commit | — | offen/PENDING — menschliche Freigabe erforderlich |
| OS + Version | — | offen/PENDING — menschliche Freigabe erforderlich |
| Firefox-Version | — | offen/PENDING — menschliche Freigabe erforderlich |
| Chrome-Version | — | offen/PENDING — menschliche Freigabe erforderlich |
| Safari-Version | — | offen/PENDING — menschliche Freigabe erforderlich |
| NVDA-Version | — | offen/PENDING — menschliche Freigabe erforderlich |
| JAWS-Version | — | offen/PENDING — menschliche Freigabe erforderlich |
| VoiceOver-Version (macOS/iOS) | — | offen/PENDING — menschliche Freigabe erforderlich |
| Browser/Zoom (400 %-Prüfung) | — | offen/PENDING — menschliche Freigabe erforderlich |
| Session-Dauer / Protokoll-Datei | — | offen/PENDING — menschliche Freigabe erforderlich |

## 3. Legende

- **Erwartete Ankündigung** beschreibt den **erwünschten** Screenreader-Output (Referenz, kein
  messwert). Sie ist eine Erwartung, kein Befund.
- Jede SR-Zelle ist `offen/PENDING — menschliche Freigabe erforderlich`. Es wird **nichts**
  als geprüft, bestanden oder fehlerhaft ausgegeben.
- Modus: `B` = Browse-/Lesemodus, `F` = Fokusmodus. Beide Modi sind pro Zelle getrennt
  zu prüfen (siehe §5).

## 4. Szenario-Matrix

| ID | Szenario / Schritt | WCAG SC | Erwartete Ankündigung (Referenz) | NVDA / Firefox (B + F) | JAWS / Chrome (B + F) | VoiceOver / Safari (B + F) |
|---|---|---|---|---|---|---|
| S01 | Login → Landing; Skip-Link per Tab fokussieren und aktivieren | 2.4.1, 2.4.11 | „Zum Inhalt springen, Link" → Fokus auf `<main id="main-content">`, Link nicht vom Sidebar-Rail verdeckt | offen/PENDING — menschliche Freigabe erforderlich | offen/PENDING — menschliche Freigabe erforderlich | offen/PENDING — menschliche Freigabe erforderlich |
| S02 | Sidebar-`role="tree"`: ↑↓→←, Home/End, Enter, `*` (Expand all), Type-Ahead | 2.1.1, 4.1.2 | „<Knoten>, Ebene N von M, eingeklappt/ausgeklappt, ausgewählt" + korrekte Baumtiefe; Rover-Fokus folgt | offen/PENDING — menschliche Freigabe erforderlich | offen/PENDING — menschliche Freigabe erforderlich | offen/PENDING — menschliche Freigabe erforderlich |
| S03 | Inspector-`role="tablist"` mit Manual Activation: Pfeiltasten → Tab/Space/Enter | 2.1.1, 4.1.2 | „<Tab>, Tab, N von M, nicht ausgewählt" → nach Aktivierung „ausgewählt"; zugehöriges Tabpanel benannt | offen/PENDING — menschliche Freigabe erforderlich | offen/PENDING — menschliche Freigabe erforderlich | offen/PENDING — menschliche Freigabe erforderlich |
| S04 | ArtifactTable: gesperrte Zeile (A11Y-001) und Zeilen-Checkbox (A11Y-006) | 1.1.1, 4.1.2, 1.3.1 | „Gesperrt — <Grund>, Bild/Text" hörbar; Checkbox „<Artefikt-Titel> auswählen, Kontrollkästchen" statt generischem „Zeile auswählen" (Identifikation über den benannten Checkbox-Label — bewusst KEIN `<th scope="row">`, da Spalten dynamisch sind; 1.3.1-Rest bleibt separater Follow-up) | offen/PENDING — menschliche Freigabe erforderlich | offen/PENDING — menschliche Freigabe erforderlich | offen/PENDING — menschliche Freigabe erforderlich |
| S05 | Shared Dialog öffnen: `aria-modal`, Trap, Escape, Fokus-Restore zum Trigger | 2.1.2, 2.4.3, 4.1.2 | „Dialog, <Titel>" + Fokus im Panel; Tab bleibt im Dialog; Escape schließt; Fokus kehrt zum Trigger zurück; Hintergrund im B-Modus nicht erreichbar | offen/PENDING — menschliche Freigabe erforderlich | offen/PENDING — menschliche Freigabe erforderlich | offen/PENDING — menschliche Freigabe erforderlich |
| S06 | Verschachtelte Dialoge: Trap-/Restore-Reihenfolge beim Schließen | 2.1.2, 2.4.3 | Fokus kehrt zum **übergeordneten** Dialog zurück, nicht zum Seiten-Trigger; nur ein `aria-modal` aktiv | offen/PENDING — menschliche Freigabe erforderlich | offen/PENDING — menschliche Freigabe erforderlich | offen/PENDING — menschliche Freigabe erforderlich |
| S07 | Formularvalidierung: Fehler-Fokus und Live-Region | 3.3.1, 4.1.3 | Fehler wird beim Absenden angesagt, Fokus wandert erstes ungültiges Feld; `role="alert"` einmalig, nicht doppelt | offen/PENDING — menschliche Freigabe erforderlich | offen/PENDING — menschliche Freigabe erforderlich | offen/PENDING — menschliche Freigabe erforderlich |
| S08 | Prose-Links im Markdown (A11Y-003, Use of Color) im B-Modus | 1.4.1 | Link ist auch ohne Farbe erkennbar (Underline/Nicht-Farbe-Signal), Ankündigung „Link" im Fließtext; Hover/Fokus ändert nicht nur die Farbe | offen/PENDING — menschliche Freigabe erforderlich | offen/PENDING — menschliche Freigabe erforderlich | offen/PENDING — menschliche Freigabe erforderlich |
| S09 | Fokusring auf 5 Themes (A11Y-004), gegen `surface-raised`/Selected-/Hover-BG | 1.4.11, 2.4.13 | Fokusindikator im realen gerenderten Kontext sichtbar und ≥ 3:1; Bauhaus nicht unsichtbar | offen/PENDING — menschliche Freigabe erforderlich | offen/PENDING — menschliche Freigabe erforderlich | offen/PENDING — menschliche Freigabe erforderlich |
| S10 | Reflow 320 px / 400 % Zoom auf 24 Routen; 2.4.11 bei offenem Drawer | 1.4.10, 2.4.11 | Kein horizontaler Dokument-Scroll; fokussiertes Element nicht verdeckt; Inhalte nicht abgeschnitten | offen/PENDING — menschliche Freigabe erforderlich | offen/PENDING — menschliche Freigabe erforderlich | offen/PENDING — menschliche Freigabe erforderlich |
| S11 | Workflow-/GraphCanvas-Knoten und -Kanten per Tastatur aktivieren | 2.1.1, 4.1.2 | Knoten/Kanten erreichbar (tabIndex 0), „Knoten/Kante, <Label>, Taste Enter/Space zum Aktivieren"; Aktivierung löst Aktion aus | offen/PENDING — menschliche Freigabe erforderlich | offen/PENDING — menschliche Freigabe erforderlich | offen/PENDING — menschliche Freigabe erforderlich |
| S12 | strukturelle Landmarks/h1 auf `/audit` und `/metrics` (statisch ohne h1) | 1.3.1, 2.4.6 | Genau eine `<h1>` pro Ansicht; Landmarks `banner`/`nav`/`main` im Rotor/Browse-Modus korrekt aufgelistet | offen/PENDING — menschliche Freigabe erforderlich | offen/PENDING — menschliche Freigabe erforderlich | offen/PENDING — menschliche Freigabe erforderlich |
| S13 | Inspector-Live-Regionen (Verschiebungen/Status) im B- und F-Modus | 4.1.3 | Änderung einmalig angesagt, nicht im Fokusmodus verschluckt und nicht doppelt | offen/PENDING — menschliche Freigabe erforderlich | offen/PENDING — menschliche Freigabe erforderlich | offen/PENDING — menschliche Freigabe erforderlich |

## 5. Bekannte Screenreader-Divergenzen (bei der Prüfung zu berücksichtigen)

- **NVDA/JAWS Browse- vs. Fokusmodus:** Im Browsermodus navigiert der SR über die virtuelle
  Dokumentstruktur; Tastatur-Handler der App (z. B. Pfeiltasten im Tree) greifen **nicht**.
  Im Fokusmodus erreicht der SR die App-Handler, verliert aber die Line-by-Line-Lesefunktion.
  Beide Modi müssen pro Szenario separat geprüft werden; ein „grün" im einen Modus ist kein
  Beleg für den anderen.
- **VoiceOver-Rotor:** `role="tree"`, `role="tablist"` (Manual Activation) und `aria-modal`
  werden im VoiceOver-Rotor anders gruppiert und angesagt als in NVDA/JAWS. Insbesondere
  `aria-modal`-Hintergrundinhalte können im Rotor sichtbar bleiben, obwohl sie im Fokusmodus
  korrekt gesperrt sind → S05/S06 nicht allein über den Rotor bewerten.
- **Kein SR ist Referenz für alle:** NVDA/Firefox, JAWS/Chrome und VoiceOver/Safari weichen
  bei Benennung, Level-Ankündigung und Live-Region-Timing voneinander ab. Die Konformität
  wird über die **Vereinigung** der drei Kombinationen beurteilt, nicht über ein „Leitsystem".
- **Zoom/Reflow ist SR-unabhängig:** 1.4.10/2.4.11 (S10) muss zusätzlich visuell (ohne SR)
  bei 400 % geprüft werden; ein SR-Befund ersetzt die visuelle Messung nicht.
- ** axe-Grenzen:** 2.1.1, 2.4.3, Lesereihenfolge, 1.4.1 und 4.1.3 sind nicht automatisierbar;
  ein grünes `a11y-smoke.spec.ts` darf hier nicht als Freigabe verstanden werden.

## 6. Freigabe / Sign-off

| Rolle | Name | Datum | Entscheidung | Status |
|---|---|---|---|---|
| Prüfer(in) Screenreader | — | — | — | offen/PENDING — menschliche Freigabe erforderlich |
| Review Accessibility | — | — | — | offen/PENDING — menschliche Freigabe erforderlich |
| Product Owner | — | — | — | offen/PENDING — menschliche Freigabe erforderlich |

**Erst wenn alle Zellen in §4 und alle Sign-off-Zeilen in §6 von einer menschlichen Prüfung
ausgefüllt und freigegeben sind, darf eine WCAG-2.2-AA-Konformitätsaussage getroffen werden.
Bis dahin gilt: manuelle Prüfung PROTOKOLLIERT, NICHT durchgeführt — Konformitätsaussage erst
nach menschlichem Sign-off.**

## 7. Beziehung zum automatisierten Gate

- `e2e/tests/a11y-smoke.spec.ts` (CI-Shard 6): 24 Routen × 5 Themes, `wcag22aa`,
  serious/critical blocken, moderate/minor als JSON-Anhänge, 320px-Reflow, Tastatur-Checks.
  Der Sweep ist ein orthogonales Vorfilter, kein Ersatz für §4.
- `e2e/a11y-followup.js`: manueller 5-Theme-Sweep, jetzt ebenfalls mit `wcag22aa`; läuft
  bewusst **nicht** in CI.
- Diese Vorlage ist die Missing Link zwischen „automatisiert grün" und „menschlich
  freigegeben"; sie darf nicht ausgefüllt werden, ohne dass eine echte Prüfung stattfand.
