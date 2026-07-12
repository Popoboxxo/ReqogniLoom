# Frontend-Feedback Strategie-Design — 2026-07-12

**Status:** Cluster A in Bearbeitung | B/C/D ausstehend (Freigabe durch User vor Beginn)
**Quelle:** Feedback-Protokoll `transcrips/2026-07-12.md` — 22 Ansichten getestet
**Strategie:** ~90 Einzelpunkte in 4 Cluster priorisiert nach Hebelwirkung.
**Bearbeitung:** Cluster A → Bestätigung → Cluster B → Bestätigung → C → D

---

## Cluster A — Gemeinsame Root-Cause-Komponenten (aktuell in Bearbeitung)

Priorität höchste, da Fixes hier den meisten Views gleichzeitig helfen.

| ID | Work Package | Scope | Tier | REQ-ID | Status |
|----|-------------|-------|------|--------|--------|
| A1 | Versioning/Diff-Service reparieren | Versionierung + Diff defekt in praktisch allen Views: "Versionen konnten nicht geladen werden", "error [object Object]". Zentrale Service-/API-Schicht. | senior-developer | REQ-001 | ausstehend |
| A2 | Trace/Link-Resolver: IDs → lesbare Titel | In Anforderungen, Architektur, ADRs, Impact-Analyse werden Traces nur als ID/Typ angezeigt, nicht als Titel des referenzierten Elements. Gemeinsamer Resolver/Serializer fehlt. | developer | REQ-002 | ausstehend |
| A3 | Einheitliches Tree/Baum-Modul | Navigationsbaum sieht in jeder Ansicht anders aus (Bedarfe, Anforderungen, Architektur, ADRs, Risiken, Probleme, Testfälle, Diagramme). Basis: `docs/architecture/DESIGN_TREE_VIEW_L0_L4_HIERARCHY.md`. Vor Beginn prüfen was bereits implementiert ist. | senior-developer | REQ-003 | ausstehend |
| A4 | i18n-Leak beheben | Rohe Translation-Keys statt Labels: `editor.status` (ADRs, Risiken, Testfälle), `workspace.create.submit` (Neuer-Workspace-Button). Weitere betroffene Keys suchen. | junior-developer | REQ-004 | ausstehend |
| A5 | Link-Erstellen-Dialog: Suche + Vereinheitlichung | Dialog zum Traces-Erstellen hat kein Suchfeld und sieht in Architektur, Impact-Analyse, ADRs jeweils anders aus. Hängt von A2 ab (Titel-Resolver muss zuerst da sein). | developer | REQ-005 | ausstehend |
| A6 | Soft-Delete-Statusmodell | Endnutzer können in Architektur, ADRs, Glossar Elemente hart löschen. Gewünscht: Status outdated/deprecated/deleted statt physischem Löschen; hartes Löschen nur für Admins. Cross-cutting Datenmodell-Änderung. | senior-developer | REQ-006 | ausstehend |
| A7 | Splitter-Fix + Badge-Kürzel | Splitter-Hitbox vergrößern (Anforderungen, Diagramme). Element-Typ-Badges auf Kürzel kürzen (S, HW, SW, C, ...) statt Volltext (SysRec, Hardware, Software, Component). | junior-developer | REQ-007 | ausstehend |

---

## Cluster B — View-spezifische Blocker-Bugs (ausstehend, Freigabe nötig)

Bugs die in einzelnen Views blockieren, aber keine gemeinsame Root-Cause haben.

| ID | Work Package | Ansicht | Beschreibung |
|----|-------------|---------|-------------|
| B1 | KI-Ableitung ohne Reaktion | Bedarfe, Anforderungen | KI-Ableitung-Button funktioniert nicht (kein Ergebnis, keine Fehlermeldung) |
| B2 | Validation-Error ohne Details | Anforderungen | Speichern zeigt nur "validation failed" ohne Fehlerbeschreibung |
| B3 | AI-Button für Ableitung fehlt | Anforderungen | AI-Derivation-Button fehlt komplett (vorhanden in Bedarfen, nicht in Anforderungen) |
| B4 | Tags-Implementierung defekt | Probleme | Tags sind vorhanden aber vollständig nicht funktionsfähig |
| B5 | UUID-Fehler in Baselines | Baselines | "badly formed hexadecimal UUID string" bei allen Scope-Einstellungen; Feature komplett außer Betrieb |
| B6 | Confirm-Button ohne Wirkung | Testläufe | "Abschließen/Confirm"-Button klickbar, aber ohne Effekt |
| B7 | Spracheinstellung ohne Wirkung | Workspace-Einstellungen | Deutsch/Englisch-Umschaltung hat keine Wirkung |
| B8 | Attribut-Sichtbarkeit HTTP 404 | Workspace-Einstellungen | Speichern von Attribut-Sichtbarkeit wirft HTTP 404 |
| B9 | ICDS initialer Baum fehlt | ICDS | Baum wird erst nach dem ersten Speichern angezeigt (sprunghafte UX) |

---

## Cluster C — Fehlende Kernfunktionen (ausstehend, Freigabe nötig)

Features die noch gar nicht existieren, aber für den Kernanwendungsfall nötig sind.

| ID | Work Package | Beschreibung |
|----|-------------|-------------|
| C1 | Impact-Graph-Visualisierung | Vollständige Hierarchie + Verknüpfungen als interaktiver Graph/Tree mit Filtern (Elementtyp, Linktyp) |
| C2 | Traces für Risiken | Risiken haben keine Trace-Funktion — muss ergänzt werden |
| C3 | Links/Traces für Probleme | Probleme haben keine Verknüpfungsmöglichkeit; insbesondere Verknüpfung zu Risiken fehlt |
| C4 | Testfall → Testlauf-Zuweisung | Testfälle können nicht zu Testläufen zugewiesen werden (und umgekehrt) |
| C5 | Testlauf zeigt Testfälle | Innerhalb eines Testlaufs sind die enthaltenen Testfälle nicht sichtbar |
| C6 | Custom Fields workspace-weit | Custom Fields sollen zentral pro Workspace definiert werden, nicht pro Element |
| C7 | Import/Export komplett | Export fehlt ganz; Import auf alle Elementtypen erweitern; rekursiver Import/Export-Workflow |
| C8 | SEMetrik Tooltips/Hilfsmodus | Alle Metriken brauchen erklärende Tooltips / einen einschaltbaren Hilfsmodus |
| C9 | Glossar-Traces | Traces für einzelne Glossar-Begriffe ziehen |
| C10 | Glossar-Synonym-Verlinkung | Synonyme direkt mit bestehenden Glossar-Einträgen verknüpfen |
| C11 | Nutzerprofil editierbar | Vorname/Nachname einsehbar + änderbar; Activity-Log "Zuletzt bearbeitet" |
| C12 | AI Prompt Konsolidierung | "AI Prompt Templates" und "AI Derivation Prompts" zu einer einzigen, funktionierenden Oberfläche zusammenführen |

---

## Cluster D — UI/Design-Polish (ausstehend, Freigabe nötig)

Optische und ergonomische Verbesserungen ohne funktionale Blocker-Wirkung.

| ID | Work Package | Ansicht | Beschreibung |
|----|-------------|---------|-------------|
| D1 | "Offene Punkte" umbenennen | Dashboard | Begriff unklar; selbsterklärendes Label verwenden |
| D2 | Redundanter Draft-Status | Bedarfe | Status in Kopfzeile und Badge gleichzeitig — eines entfernen |
| D3 | Stakeholder-Auswahl kontextlos | Anforderungen | "Stakeholder" als Anforderungstyp macht in diesem Kontext keinen Sinn |
| D4 | Redundante Titelanzeige | Architektur | Element-Titel wird mehrfach angezeigt — nur an einer Stelle |
| D5 | Elementtypen dynamisch | Architektur | Elementtypen nachträglich ändern, erweitern, löschen ermöglichen |
| D6 | "Impact Analyse" bricht aus Rahmen | Impact-Analyse | Titel passt nicht in seinen Container |
| D7 | UI verschoben beim Klick | Impact-Analyse | Layout-Fehler beim Öffnen des Link-Erstellen-Dialogs |
| D8 | Inkonsistente Entitätsanzeige | ADRs | Versionierungs-Status und ID-Darstellung weicht von anderen Views ab |
| D9 | Inspector-Bug Trace-Typ | ADRs | Im Inspector fehlt der Trace-Typ ("allocate to" ohne Typ) |
| D10 | Verantwortlicher: Freitext + Autocomplete | Risiken | Feld muss Freitext UND User-Dropdown/Autocomplete kombinieren |
| D11 | Glossar-Dialog Layout | Glossar | Dialog zusammengequetscht; Titel und Buttons brechen aus Rahmen |
| D12 | Glossar-Scope vereinfachen | Glossar | "Alle/Workspace/Global" → nur "Workspace/Global" |
| D13 | Workspace-Einstellungen Redesign | Workspace-Einstellungen | Gesamtlayout und Proportionen neu gestalten |
| D14 | Dropdown Weiß-auf-Weiß | Workspace-Einstellungen | Entitätstyp-Dropdown: weiße Schrift auf weißem Hintergrund |
| D15 | Traceability-Default | Workspace-Einstellungen | Default-Linktyp soll "derives from" sein |
| D16 | Disaster Recovery Dropdown | Workspace-Einstellungen | Gleicher Kontrast-Bug wie D14 |
| D17 | Datenimport deplatziert | Workspace-Einstellungen | Datenimport gehört nicht in Workspace-Einstellungen |
| D18 | Workflows + Item Permissions | Workspace-Einstellungen | Komplett überarbeiten (als "Katastrophe" bewertet) |
| D19 | Access Token Dialog Optik | Profil | Funktioniert, aber visuell überarbeitungswürdig |
| D20 | Workspace-Changer deplatziert | Profil | Im Profil fehl am Platz; bessere Platzierung finden |
| D21 | Login-Screen Design + Metadaten | Login | Design überarbeiten; Tool-Name, Version, Patch-Level anzeigen |
| D22 | Baselines Artefakt-Suche mit Namen | Baselines | Aktuell nur Artefakttypen sichtbar, keine Namen |
| D23 | ICDS Schnittstellen-Typen | ICDS | Dropdown-Entscheidung noch offen |
| D24 | ICDS Similar-Algorithmus | ICDS | Kriterien für Ähnlichkeitserkennung definieren |
| D25 | Neuer-Workspace-Dialog Platzierung | Workspace-Anlegen | Aus dem Navigationsbaum herauslösen |
| D26 | Diagramme Typ vs. Quelle | Diagramme | Unterschied zwischen "Typ" und "Quelle" unklar |

---

## Entscheidungslog

| Datum | Entscheidung |
|-------|-------------|
| 2026-07-12 | Cluster-Reihenfolge A→B→C→D durch User bestätigt |
| 2026-07-12 | B/C/D starten erst nach expliziter Freigabe durch User |
| 2026-07-12 | REQ-IDs A1=REQ-001, A2=REQ-002, A3=REQ-003, A4=REQ-004, A5=REQ-005, A6=REQ-006, A7=REQ-007 (REQUIREMENTS.md war leer, SE-Register bleibt separat) |
| 2026-07-12 | DESIGN_TREE_VIEW-Proposal (REQ-001 im Doc) → formal als REQ-003 registriert um Kollision mit A1 zu vermeiden |
| 2026-07-12 | Playwright-E2E nicht automatisch ausführen (policy: playwright-policy.md) |
