# Analyse: Import-, ID- und Traceability-Lücken

> Status: **Analyse — noch nicht umgesetzt.** Dieses Dokument fasst 7 vom User gemeldete
> Auffälligkeiten zusammen, inkl. Root-Cause (Code-Fundstelle + empirische DB-Prüfung
> wo möglich). Keine der beschriebenen Lücken wurde im Rahmen dieser Analyse behoben.
>
> Datum: 2026-07-19
> Kontext: Test-Import der SE-Dokumentation (`docs/se/`) via
> `backend/application/management/commands/migrate_se_docs.py` in die Demo-Workspace.

---

## 1. `uid`-Feld-Semantik vs. gewünschtes „ForeignID"-Feld

**Beobachtung:** Unklar, wie die IDs aus den Quelldokumenten (`REQ-L1-005`, `ARCH-L1-000`, …)
ins `uid`-Feld gelangen, und ob das der vorgesehene Zweck des Felds ist.

**Befund:**
- `uid` ist auf `StakeholderNeed`, `Requirement`, `ArchitectureElement`, `Artifact`, `TestCase`,
  `TestRun` vorhanden (`backend/persistence/models.py`), mit Help-Text
  **„Unique identifier (read-only, auto-generated)"** (z. B. Zeile 601-606 für `StakeholderNeed`).
- In der Praxis ist `uid` aber **kein** automatisch generiertes Feld, sondern ein optionaler
  Parameter, der von den Service-Methoden (`RequirementService.create_requirement(..., uid=None)`,
  `backend/application/requirement_service.py:145`) durchgereicht wird. Bei normaler UI-Erstellung
  bleibt `uid` also i. d. R. `NULL` — der Help-Text „auto-generated" stimmt nicht mit dem
  tatsächlichen Verhalten überein.
- `migrate_se_docs.py` nutzt `uid` zweckentfremdet als **Idempotenz-/Identitätsschlüssel**: Es
  schreibt die externen Dokumenten-IDs (`REQ-L1-005` etc.) direkt hinein, um bei wiederholten
  Importläufen bestehende Artefakte wiederzuerkennen.
- Die von dir im Browser gesehene ID (`.../requirements/12d0a9af-a523-...`) ist **nicht** die
  `uid`, sondern die interne Primärschlüssel-`id` (UUID) des `Requirement`/`Artifact` — das sind
  zwei unabhängige Felder, die aktuell aber leicht verwechselt werden können, weil in der UI
  vermutlich nur eines der beiden konsistent sichtbar ist.

**Einschätzung:**
- Es gibt aktuell **kein** separates Feld für „externe/Legacy-ID aus einem Import-Job" — `uid`
  übernimmt informell diese Rolle, kollidiert damit aber konzeptionell mit seinem eigentlichen
  (laut Help-Text) Zweck als ReqFlow-eigene, auto-generierte ID.
- Der gewünschte `ForeignID`-Ansatz (separates Feld für Importe, `uid`/interne ID bleibt
  ReqFlow-eigen und konsistent) ist eine saubere Trennung von zwei heute vermischten Konzepten.
  Betrifft mindestens: Model-Feld (neue Migration), `ENTITY_FIELD_SPECS`
  (`backend/application/export_service.py`), `ImportService`, und `migrate_se_docs.py`
  (Umstellung von `uid=` auf `foreign_id=` als Idempotenz-Schlüssel).

---

## 2. Requirement-Links im Dialog nicht klickbar

**Beobachtung:** Links wie `http://localhost:5173/requirements/<uuid>` sind in einem Dialog
nicht klickbar.

**Befund:** `frontend/src/components/RequirementEditors/ReqTraceLinkPanel.tsx`, Zeilen 494-561
(genutzt im Requirement-Detail-View, eingebunden in `RequirementEditors.tsx:427`). Der Titel
eines verlinkten Artefakts wird als reines `<span data-testid="req-tracelink-title">` gerendert
(Zeile 543) — kein `onClick`, kein `<a href>`, kein Router-`<Link>`. Das umgebende `<li>`
(Zeilen 517-530) hat ebenfalls keinen Navigations-Handler.

Zum Vergleich: Zwei Schwester-Komponenten machen es bereits richtig —
`frontend/src/components/shared/trace-link-display.tsx` (Zeilen 175-193, `<button onClick=>`)
und `frontend/src/components/shared/ArtifactInspector/TracePanel.tsx` (Zeilen 286-299,
`renderRow`, ebenfalls klickbarer `<button>`). `ReqTraceLinkPanel` ist der einzige Ausreißer ohne
Klick-Handler.

**Einschätzung:** Klar lokalisierter, kleiner Bug — Muster für den Fix existiert bereits im
selben Codebase (`trace-link-display.tsx` / `TracePanel.tsx`).

---

## 3. `status` wurde nicht importiert

**Beobachtung:** Status-Feld wurde beim SE-Doc-Import nicht befüllt.

**Befund — empirisch bestätigt:**
- `ENTITY_FIELD_SPECS` (`backend/application/export_service.py`) unterstützt `status` sowohl für
  `StakeholderNeed` als auch `Requirement` — das CSV-Schema ist **nicht** die Einschränkung.
- `migrate_se_docs.py`s Row-Builder setzen `status` aber nie:
  ```python
  def _stakeholder_need_row(uid, title, body):
      return {"title": title[:500], "description": _csv_safe(body), "uid": uid}

  def _requirement_row(uid, title, body):
      return {"title": ..., "description": ..., "level": ..., "uid": uid}
  ```
  (nur `_adr_row()` setzt `status`, gemappt aus einer `**Status:**`-Zeile im Quelldokument).
- DB-Check in der Demo-Workspace bestätigt den Effekt: **alle 738 importierten Requirements und
  alle 58 importierten StakeholderNeeds** stehen auf dem Modell-Default `draft` (1 einzelnes
  `in_review` bei den Requirements stammt nicht aus dem SE-Import).

**Einschätzung:** Klarer, einfach behebbarer Gap — die Quelldokumente (`docs/se/`) müssten
geprüft werden, ob sie überhaupt einen Status pro Requirement/Need führen; falls nicht, ist
„alles auf `draft`" ggf. sogar korrekt und keine Lücke, sondern erwartetes Verhalten des
Quellmaterials.

---

## 4. Keine sichtbaren Verbindungen zwischen Bedarfen und Anforderungen

**Beobachtung:** Keine Verbindungen zwischen StakeholderNeeds („Bedarfe") und Requirements
(„Anforderungen") sichtbar — Verdacht auf Systemproblem statt Datenlücke.

**Befund — empirisch bestätigt: Verdacht trifft zu, es ist ein Anzeigeproblem, keine
Datenlücke.**
- DB-Check: **43 Trace-Links** vom Typ `derives-from` zwischen Requirement und StakeholderNeed
  existieren in der Demo-Workspace (Ergebnis der `traceability-matrix.md`-Auswertung durch
  `migrate_se_docs.py`, Abschnitt „§1 REQ-L0→REQ-L1").
- Die Daten sind also vorhanden. Das Problem liegt in der Darstellung — konsistent mit Punkt 6/7
  unten: Die vorhandenen Anzeige-Komponenten (`ReqTraceLinkPanel`, `TracePanel`) zeigen Links nur
  als **flache Liste ohne Filterung/Gruppierung nach Richtung oder Zieltyp**, und der Link selbst
  ist laut Punkt 2 nicht klickbar — es ist plausibel, dass die Links zwar in der Liste stehen,
  aber im UI leicht übersehen werden (z. B. wenn StakeholderNeed-Links nicht optisch von anderen
  Link-Typen abgesetzt sind, oder wenn primär auf der StakeholderNeed-Seite geschaut wurde und
  dort keine eingehenden Links gerendert werden — das wäre gesondert zu prüfen).

**Einschätzung:** Kein Daten-Bug. Bevor hier etwas implementiert wird: gezielt prüfen, ob die
StakeholderNeed-Detailansicht (Pendant zu `ReqTraceLinkPanel` für Requirements) überhaupt
eingehende `derives-from`-Links anzeigt — das wurde in dieser Analyse noch nicht untersucht.

---

## 5. Suche in der Auswirkungsanalyse (Impact Analysis) funktioniert nicht

**Befund:** `frontend/src/components/ImpactView/ImpactView.tsx`.
- Suchfeld (`data-testid="impact-search-input"`, Zeilen 358-380) triggert `runSearch()`
  (Zeilen 298-316), die einen echten Backend-Call macht:
  `searchApi.search(query.trim(), activeWorkspace.id, { limit: 10 })`
  (`frontend/src/api/search.ts:30-51`, `GET /api/v1/search/?q=...`). Kein Feldnamen-Mismatch
  gefunden.
- Suche wird **nur** bei `Enter`-Taste oder Klick auf „Artefakt laden" ausgelöst
  (Zeilen 363-368) — **kein Live-/As-you-type-Filter, kein Debounce**. Wer erwartet, dass die
  Ergebnisliste beim Tippen reagiert, sieht scheinbar „keine Funktion".

**Einschätzung:** Zwei mögliche Ursachen, nicht in dieser Analyse unterscheidbar ohne Live-Test:
(a) reines UX-Missverständnis (Suche funktioniert nur nach Enter/Klick), oder (b) ein
tatsächlicher Backend-/Datenbug bei `GET /api/v1/search/` für die konkret verwendeten Suchbegriffe
(z. B. liefert die Suche für SE-importierte Artefakte keine Treffer). Empfehlung: vor
Implementierung einmal live reproduzieren (Suchbegriff eingeben + Enter drücken) und Network-Tab
prüfen, ob der Request überhaupt Treffer liefert.

---

## 6. Requirement-Dialog: hierarchische Trace-Baum-Ansicht fehlt

**Befund:** Requirement-Detailansicht (`RequirementEditors.tsx`, rechtes Panel,
Zeilen 401-460+) zeigt Trace-Links aktuell über zwei **unabhängige, flache** Listen:
- `ReqTraceLinkPanel` (Zeilen 489-564): eine flache `<ul>` aller Links des Requirements.
- `TracePanel` (ArtifactInspector, Zeilen 286-316): flache Inbound-/Outbound-Sektionen, je eine
  einstufige `<ul>` — Zeilen sind klickbar (navigieren weg), aber nicht expandierbar.

Eine dritte Komponente, `TraceabilityPanel.tsx` (Upstream-/Downstream-Sektionen), ist ebenfalls
nur eine flache Liste **und wird laut Code aktuell gar nicht mehr eingebunden**
(`RequirementForm.tsx:60-68` dokumentiert explizit, dass ihre `upstreamLinks`/`downstreamLinks`-
Props „no longer consumed here" sind — nur noch von Tests referenziert, kein Produktivpfad).

Der einzige rekursive/aufklappbare Baum im gesamten Frontend ist `ArtifactTreeNode` in
`ImpactView.tsx` (Zeilen 101-282) — das ist aber eine eigene Seite (Impact Analysis), nicht Teil
des Requirement-Dialogs.

**Einschätzung:** Echter Feature-Gap, keine Regression. Die Baum-Logik aus `ArtifactTreeNode`
(`ImpactView.tsx`) ist ein sinnvoller Ausgangspunkt/Vorbild für eine wiederverwendbare
Baum-Komponente im Requirement-Dialog.

---

## 7. Requirement-Dialog: Verknüpfte ArchitectureElements nicht erkennbar gruppiert

**Befund:** ArchitectureElement-Links werden angezeigt, aber **nicht** vom Rest getrennt:
- `ReqTraceLinkPanel.tsx` lädt ArchitectureElements (Zeilen 146-182) und listet sie beim
  Link-Anlegen in einer eigenen `<optgroup>` (Zeilen 384-392) — nach dem Anlegen erscheint der
  Link aber in derselben flachen Liste wie jeder andere Link-Typ (Zeilen 494-561), ohne visuelle
  Gruppierung nach Zieltyp.
- `TracePanel.tsx` mappt `"ArchitectureElement"` auf Kind `"architecture"` (Zeilen 64-65), rendert
  es aber in derselben Inbound-/Outbound-`<ul>` wie Requirement- und TestCase-Links
  (Zeilen 301-316) — keine eigene „Architektur"-Sektion.

**Einschätzung:** Selbes Muster wie Punkt 6 — hängt an derselben Baum-/Gruppierungs-Lücke.
Sinnvoll gemeinsam mit Punkt 6 zu lösen (z. B. Baum gruppiert nach Zieltyp: StakeholderNeed /
Requirement / ArchitectureElement / TestCase).

---

## Zusammenfassung nach Aufwand/Typ

| # | Thema | Typ | Aufwand (grob) |
|---|-------|-----|-----------------|
| 1 | `uid` vs. `ForeignID` | Datenmodell-Erweiterung (Migration + Service + Import) | Mittel-Groß |
| 2 | Nicht-klickbare Links | Bugfix, Vorbild existiert im Code | Klein |
| 3 | `status` nicht importiert | Bugfix in `migrate_se_docs.py`-Row-Buildern | Klein |
| 4 | Bedarf↔Anforderung „unsichtbar" | Vermutlich Anzeigeproblem, keine Datenlücke — weitere Prüfung nötig | Klein-Mittel |
| 5 | Impact-Analysis-Suche | Unklar: UX (kein Live-Filter) oder echter Bug — Live-Repro nötig | Unklar |
| 6 | Hierarchischer Trace-Baum im Requirement-Dialog | Neues Feature, Vorbild (`ArtifactTreeNode`) existiert | Mittel |
| 7 | ArchitectureElement-Gruppierung im Requirement-Dialog | Neues Feature, kombinierbar mit #6 | Mittel |

**Nächster Schritt:** Dieses Dokument dient nur der Analyse. Für die Umsetzung einzelner Punkte
bitte separat freigeben/priorisieren.
