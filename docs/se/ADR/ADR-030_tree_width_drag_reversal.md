---
adr_id: ADR-030
title: "Per-module draggable tree width in SplitView (UI-001 reversal)"
status: accepted
date: 2026-11-19
deciders: [user, se-architect]
affected_reqs: [REQ-L1-084, REQ-L3-RF009-001, REQ-L2-RF-209]
superseded_by: null
type: ADR
scope: frontend/splitview/tree-width
author_agent: concept-reviewer
---

# ADR-030: Per-module draggable tree width in SplitView (UI-001 reversal)

## Kontext

UI-001/S3.2 entfernte den Legacy-Vertrag (`leftPanel`/`rightPanel`, Drag,
`reqflow_splitview_*`, `initialLeftWidth`), weil zwei parallele Implementierungen
in einer 1035-Zeilen-Datei, eine kopierte mobile State-Machine und drei
divergierende Breakpoint-Quellen vorlagen (R2S-006). Das war ein
Architektur-Hygiene-Entscheid („ein SplitView-Pfad"), **kein** UX-Urteil über
verstellbare Breiten.

Dabei wurden jedoch zwei bestehende Akzeptanzkriterien stillschweigend
fallengelassen:

- **REQ-L1-084**: „Der Trenner MUSS verschiebbar (resizable) sein" — AC
  „Breite des rechten/linken Panels ist via Drag&Drop anpassbar". Status:
  *Not Implemented / Test Status: Missing*.
- **REQ-L3-RF009-001**: „Divider reagiert auf Mouse-Drag" + „Speichert das
  Layout (Ratio) persistiert im localStorage". Status: *Not Implemented*.

`TESTPLAN_v1.8.0-beta.15` (CSS-03) erwartet den Split-View-Drag weiterhin
einschließlich Größen-Reset. Die jetzige User-Forderung (D3: Breite pro Modul,
optimaler Default, per Drag anpassbar und gespeichert) ist damit keine neue
Laune, sondern **Wiederherstellung von REQ-Compliance**.

Zu erhalten ist die Single-Contract-Single-Source-Eigenschaft von UI-001:
keine zweite Implementierung, keine zweite Breakpoint-Quelle, kein
`spineIsHorizontal`/`NARROW_RATIO`, Footer bleibt Geschwister des SplitView.

## Alternativen

- **A (gewählt): Per-Modul-Drag + neuer gerätelokaler Key.** `treeWidth` (px)
  ist auf Desktop autoritativ; `ratio` wird zum Initialwert (nur ohne
  gespeicherten Wert), `minWidths` zu den Clamp-Grenzen. Default je Modul;
  Key `reqflow.splitview.treeWidth.v2.<moduleType>`.
  + Erfüllt D3 **und** REQ-L1-084 / REQ-L3-RF009-001; kein Legacy-Contract;
    sofortiges Feedback, kein API-Call.
  – Zweite Breiten-Semantik neben `ratio` braucht klare Autoritätsregel;
    neue A11y-/Persistenz-/Snapshot-Fläche.
- **B (abgelehnt): Nur per-Modul-Defaults, keine Drag-Interaktion.**
  + Kleinste Fläche, fixed-ratio-Architektur bleibt.
  – Verletzt die explizite User-Forderung „adjustable by dragging" **und**
    lässt die beiden REQ-ACs unerfüllt. Dokumentierter Fallback, falls Task 8
    Regressionen erzeugt.
- **C (abgelehnt): Legacy-Vertrag reaktivieren** (`leftPanel`/`rightPanel`,
  `reqflow_splitview_*`, `initialLeftWidth` aus der Historie).
  + Minimaler Code-Delta. – Reintroduziert exakt UI-001/R2S-006
    (Doppelimplementierung, kopierte State-Machine, Breakpoint-Drift),
    erzwingt Rückmigration aller 8 Hosts, bricht
    `breakpoint-token-gate.test.ts`. Hart abgelehnt.
- **D (deferred): Serverseitige Q1-User-Präferenz** (Cross-Device-Sync).
  + Konsistent über Geräte, kein localStorage. – 8 Registry-Einträge plus
    Serializer/API-Fläche; in Plan §7 bewusst deferred. Nicht in diesem Schnitt.

## Entscheidung

**Ein Contract, eine Hook-Instanz.** Neuer optionaler Prop `moduleType`;
Breite wird über `useTreeWidth()` pro Modul gelesen/geschrieben.

- **Autorität:** Nach dem ersten Drag ist `treeWidth` (px) allein autoritativ.
  `ratio` dient nur als **Initialwert**, solange kein gespeicherter Wert
  existiert. `minWidths` definiert die **Clamp-Grenzen** in px.
- **Clamp (F1/F2 aufgelöst):** Die untere Grenze ist `minWidths[0]` (aktuell
  380 px, Token `--list-min`); `Home` setzt genau diesen Wert — nicht 200 px.
  Die obere Grenze ist
  `effMax = min(70 % × contentWidth, contentWidth − minWidths[1] − dividerWidth)`
  und wird zur Laufzeit aus der gemessenen Content-Breite berechnet
  (`ResizeObserver`/Ref), **nicht** über ein neues `@media (max-width: Npx)`.
  `End` setzt `effMax`. Bei Widerspruch zwischen `ratio`-Initialwert und
  Clamp gewinnt der Clamp.
- **Persistenz:** ausschließlich `reqflow.splitview.treeWidth.v2.<moduleType>`.
  `reqflow_splitview_*` wird weder gelesen noch geschrieben (0 Code-Treffer).
  Korruptive/out-of-range Werte fallen ohne Crash auf den Modul-Default zurück.
- **Reset:** `Enter`/Doppelklick löscht den gespeicherten Wert und fällt auf
  den Modul-Default zurück (ADR 350 px / Requirements 424 px / …).
- **Divider:** `role="separator"`, `aria-valuenow/min/max`, `tabindex="0"`,
  24×24 px Trefferfläche, `data-testid="tree-width-separator"`; Pfeile ±16 px,
  `Shift`+Pfeil ±64 px, `Home`/`End`, `prefers-reduced-motion` respektiert.
  In `zone === 'mobile'` ist er **inert** (kein Tab-Stop, kein `aria-valuenow`).
- **Unangetastet:** `useSplitViewMobileState`, Testids `splitview-list/detail/back`,
  Footer als Geschwister, `--bp-lg` inspector-exklusiv, kein `spine`-Slot,
  kein `spineIsHorizontal`/`NARROW_RATIO`, `breakpoint-token-gate.test.ts`
  bleibt grün und wird **nicht** gelockert.

**Abgrenzung zu ADR-029:** Dort wurde localStorage für *geteilte Dokument-Inhalte*
(Node-Positionen mit Backend-Export) abgelehnt. Hier ist die Breite eine
*kosmetische, gerätelokale UI-Layout-Präferenz* ohne Backend-Relevanz —
die Ablehnung gilt nicht für diesen Fall.

## Konsequenzen

- **Positiv:** REQ-Compliance wiederhergestellt (REQ-L1-084, REQ-L3-RF009-001);
  bessere Usability für baumlastige Module; Defaults optimal pro Modul;
  keine zweite Implementierung; gerätelokal, kein Tenant-Daten-/Rechte-Bypass.
- **Negativ:** Zweite Breiten-Semantik (`ratio` vs. `treeWidth`) muss dokumentiert
  und getestet werden; neue A11y-Fläche; ~14 Visual-Baselines churnen
  (Owner `e2e-tester`); keine Cross-Device-Synchronisation (bewusst deferred);
  localStorage-Werte können korrupt sein → Clamp/Default-Fallback nötig.

## Review-Status

`status: accepted` — Statuswechsel am 2026-11-19 durch `se-architect` von
`proposed` nach `accepted` (AGENTS.md ADR-Lifecycle).

**Grund:** MADR-Minimal-Standard vollständig erfüllt — alle sieben
Frontmatter-Pflichtfelder vorhanden, Body-Struktur (`## Kontext` als
Problem-Statement, `## Alternativen` mit Abwägung inkl. rejected,
`## Entscheidung` präzise/testbar, `## Konsequenzen` positiv und negativ),
Filename `ADR-030_tree_width_drag_reversal.md` konventionskonform, ADR-ID 030
eindeutig und monoton nach 029. Die drei `affected_reqs` (REQ-L1-084,
REQ-L3-RF009-001, REQ-L2-RF-209) existieren in `docs/se` bzw. der
Traceability-Matrix. Das `concept-reviewer`-Gate hat den Reversal mit Verdict
*BEFÜRWORTET* freigegeben; die ADR-Findings F1 (Clamp 380 px statt 200 px +
`effMax`-Formel), F2 (70 %-Kappe gegen `minWidths[1]`/detailMin abgesichert)
und F3 (REQ-Begründung im `## Kontext`) sind eingearbeitet. Keine offenen
Blocker; das Critic-Finding „unbegründete Entscheidungsumkehr" liegt nicht vor
(Task-7-DoD erfüllt).

Dieses ADR wurde als Teil von Task 7 des Remediation-Plans erstellt und durch
`concept-reviewer` geprüft.

**Folgeschritt (außerhalb dieses Edits):** Die `open_adrs`-Felder der drei
`affected_reqs` sind derzeit bereits `[]` und listen `ADR-030` nicht — ein
Entfernen ist aktuell nicht nötig. Sollte dennoch ein Eintrag zu pflegen sein,
obliegt das Entfernen `se-requirements` (REQ-Dateien lagen nicht im Scope
dieses Reviews). Die Rückverfolgbarkeit bleibt über `affected_reqs` in diesem
ADR erhalten.
