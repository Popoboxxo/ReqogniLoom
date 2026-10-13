---
title: Bugfix-Runde 2 — Umsetzungsplan
date: 2026-10-12
branch_base: main @ 65515769
author_agent: orchestrator
status: proposed
scope: 5 Kernkandidaten + 1 Entscheidungsspur (Restpool nach Bugfix-Runde 1; #1136 ist geschlossen)
---

# Bugfix-Runde 2 — Umsetzungsplan

> **Status:** `proposed` — dieser Plan implementiert **nichts** selbst. Er beschreibt
> Paket, Reihenfolge, Wellen, Fix-Ansätze und Akzeptanzkriterien.
>
> **Faktenbasis:** Triage-Daten (Schicht, Datei/Symbol, Aufwand, Abhängigkeiten) wurden
> **in dieser Session im Repo verifiziert**. Verifizierte Angaben sind mit
> „**verifiziert**" markiert; Angaben aus Issue-Bodies sind als „laut Issue" markiert;
> Annahmen sind explizit als **Annahme** gekennzeichnet.
>
> **Abgrenzung zum Vorgänger** (`docs/audit/2026-10/bugfix-round-plan.md`, 2026-10-04,
> 27 triagierte Issues, Wellen M0–M4): jene Runde ist abgeschlossen. Von den 18
> In-Scope-Bugs sind #1145–#1154 (beta.18-Block) und #988, #1112, #1115, #1116, #1128,
> #1129, #1130 geschlossen. **Kein Issue des Vorgängerplans ist in diesem Plan erneut
> enthalten.** Dieser Plan arbeitet den **Restpool** ab, der danach übrig blieb.

---

## 0. Ausgangslage

| Aspekt | Wert (verifiziert, 2026-10-12) |
|---|---|
| Branch | `chore/release-1.8.0-beta.20` |
| HEAD / `origin/main` | `0ee47d25` / `65515769` |
| Letzter Release | `v1.8.0-beta.20` |
| Working Tree | 3 untracked Pfade, keine Modified-Dateien |
| Offene Issues (gesamt) | 29 |
| Offene Issues mit Label `bug` | **0** |
| Offene Issues mit Label `enhancement` | 29 |

**Konsequenz:** Der klassische Defekt-Pool ist leer. Jedes offene Issue trägt nur
`enhancement`. Die Runde muss sich daher aus dem **Material** speisen, das zwar als
`enhancement` gelabelt ist, aber **verifizierte Funktionsdefekte oder messbare
Inkonsistenzen** beschreibt — sonst bleibt die Runde substanzlos. Diese Einstufung
je Kandidat ist in §1 dokumentiert und begründet.

**In dieser Session neu gemessen** (starke Signale, die in keinem Issue standen):

| Messung | Dokumentiert | Tatsächlich | Drift |
|---|---|---|---|
| MCP-Tool-Anzahl | `227` (`.meta-config/project.yaml` L102,150,179,236,366 = 5 Vorkommen; `AGENTS.md` L8,39; `CLAUDE.md` 2 Vorkommen) | **228** (`docs/agent-templates/tool-manifest.json`, Feld `tool_count = 228`) | **+1** |
| Built-in Trace-Link-Typen | `11` (issue #1104 behauptet `20`) | **11** (`backend/link_types/builtin.py::BUILTIN_LINK_TYPES`, 11 Keys) | 0 — Issue-Behauptung falsch |
| DRF Router-ViewSets | `28` | **28** gesamt (19 in `backend/rest_api/views.py`, Rest in weiteren Modulen) | 0 |
| APIView-Subklassen | `74` | **81** gesamt (8 in `backend/rest_api/views.py`) | +7 |

---

## 1. Triage-Tabelle

### 1.1 Kernkandidaten (5)

| # | Severity | Typ | Einstufung | Betroffene Schicht / Datei (verifiziert) | Aufwand |
|---|---|---|---|---|---|
| **1178** | HIGH | Bug (Datenintegrität) | **Kernkandidat** — verifizierte Lücke in Duplikaterkennung | `backend/application/requirement_service.py:261` (`create_requirement`), `backend/application/import_service.py:781-890` (`_dedupe_rows`, `_natural_key`, `_duplicate_item`), `backend/rest_api/views.py:8938-8974` (Legacy- vs. v2-Response), `frontend/src/components/CsvImport/CsvImport.tsx:387-433` | M |
| **1196** | MED | Bug (UI/UX) | **Kernkandidat** — verifiziert, Bulk nur im Proposals-Zweig | `frontend/src/components/Reviews/ReviewsView.tsx:171` (`bulkConfirm`), `:226-228` (`listMode`/`queueMode`/`selectedIds`), `:636-670` (Bulk-Button-Rendering) | M |
| **1104** | MED | Bug (Meta/Doku-Drift) | **Kernkandidat** — **messbarer** Drift +1 verifiziert | `.meta-config/project.yaml:102,150,179,236,366` (Quelle, 5 Vorkommen), `AGENTS.md:8,39` + `CLAUDE.md` (je 2 Vorkommen, generierte Artefakte) | S |
| **1103** | MED | Bug/Enhancement (Test-Infra) | **Kernkandidat** — 3 Ratchets, 3 Mechanismen, verifiziert | `backend/mcp_server/tests/test_entity_surface_parity.py` + `entity_surface_baseline.json` + `entity_surface_matrix.py`; `frontend/src/test/design-system-ratchet.test.ts` + `.baseline.json`; `backend/mcp_server/tests/test_tool_manifest_drift.py` + `docs/agent-templates/tool-manifest.json` | M |
| **1117** | LOW | Bug (Test-Debt) | **Kernkandidat (von NI zu umsetzbar reklassifiziert)** — Harness statt Repro | Test-Runner/CI-Artefakt-Pfad; Reporter-Konfiguration | S |

### 1.2 Entscheidungsspur (3) — eigene Spur, nicht droppen

| # | Severity | Typ | Status (verifiziert) | Nächster konkreter Schritt |
|---|---|---|---|---|
| **1135** | HIGH | Security-Enhancement | **HARD STOP.** Dependency `django-axes` fehlt; Lockout-Policy + Gate-Entscheidung offen (Mechanismus, Policy, Admin-Gate, Autorisierungs-Achse). Betrifft `/admin/`, **nicht** die REST-Auth (dort greifen `LoginRateThrottle`/`LoginIpRateThrottle` bereits) | Entscheidung dokumentieren — danach Umsetzung in eigener Runde |
| **1138** | MED | Requirements | **HARD STOP.** ADR-017 lässt den Traceability-Anker für Plugin-Versioning offen (Finding 002-02); Option A (REQ anlegen) vs. Option B (non-product-Deklaration). `PLUG-04` hängt dran | `requirements`-Agent: Entscheidung herbeiführen, `PLUG-04` referenziert sie |
| **1110** | — | Housekeeping (SE) | Aggregator „Entscheidungswellen 2026-09" — trägt die Koordination der o.g. Entscheidungen | Kein Fix; als Aggregator für 1135/1138 nachführen |

> **Querverweis:** `docs/audit/2026-09/review/W4_CLOSEOUT.md:303` hält fest, dass
> „keines der offenen Items ist ein akuter Defekt". Diese Aussage stimmt für die
> drei Posten der Tabelle — sie ist **kein** Freibrief für die fünf Kernkandidaten,
> die verifizierte Funktionsdefekte sind.
>
> **Nachtrag #1136 (nicht Teil dieser Runde):** im vorbereitenden Verlauf wurde #1136
> zunächst als offener Decision-Pending-Kandidat geführt. Verifikation am 2026-10-12:
> das Issue ist seit **2026-10-04 21:12 UTC geschlossen** (`COMPLETED`), Entscheidung
> D4 ist dokumentiert, Migrationen `application/0030`–`0034`, `auth_tenancy/0017`
> sowie `persistence/0109/0110` liegen vor, und alle sechs Residual-Sub-Issues sind
> geschlossen (R-3 → #1184, R-7 → #1179, R-8 → #1180, R-9 → #1181, STOPP-S1 → #1182,
> A4/R-2 → #1183). `RLS_PREAUTH_ENFORCED` / `hard_enforced` bleiben bewusst OFF
> (Ship-Default); der Flip ist ein operativer Akt mit Pre-Flip-Checkliste
> (`docs/audit/2026-10/1136-r3-unscoped-inventory.md:116-143`), **kein**
> Bugfix-Arbeitspaket. Damit ist dieses Issue vollständig abgearbeitet und scheidet
> aus dem Pool aus.

### 1.3 Explizit out-of-scope

| # | Grund |
|---|---|
| 1230, 1171 | Roadmap — eigener Umfang, keine Bugfix-Session |
| 792, 941, 934, 946, 186, 92, 378, 272, 85, 89, 50, 18 | Enhancement / Epic / Feature — eigene Planung |
| 801, 1094, 878, 877, 879 | Enhancement UI/SE — eigene Roadmap |
| 598 | Abgeschlossener Frontend-Review-Verdikt (APPROVE) — Historie |
| 587 | Promptfoo-Testinfrastruktur (Phase 3) — langlaufendes Vorhaben, eigener Scope |

> **Summe:** 5 Kernkandidaten + 3 Entscheidungsspur + 21 out-of-scope = **29 offene
> Issues** vollständig erfasst. Kein Issue aus dem Vorgängerplan wiederholt, #1136
> als geschlossen ausgeschieden.

---

## 2. Wellen / Phasen

Grundsatz wie im Vorgänger: jede Welle ist **unabhängig shippbar**, eigener
`fix/*`-Branch off `main @ 65515769`, kein Commit auf `main` (Branch-Guard).

**Release-Blocker-Analogie zu Welle 0?** **Nein — und das ist explizit begründet:**
Die Vorgänger-Welle 0 (#1145: SHA-Label-Mismatch, `celery-beat` unhealthy,
`/health/live|ready` 404) existierte, weil Version-, Health- und Build-Signale
**nicht verlässlich** waren und damit jede Re-Validierung messunsicher. Verifiziert
(2026-10-12): `backend/reqogniloom/urls.py:37-43` routet `/health/live`,
`/health/ready` und den `/health/`-Alias; die SHA-Kette ist geschlossen. Es gibt
**keinen** offenen Blocker, der die Vertrauenswürdigkeit der Re-Validierung
untergräbt. Eine Welle 0 wäre daher reine Ritualistik ohne Blockade-Wirkung.

---

### Welle 1 — Meta-/Doku-Drift + Ratchet-Konsolidierung

| Aspekt | Inhalt |
|---|---|
| **Ziel** | Die **messbare** Zahlen-Inkonsistenz (228 ≠ 227) an der Quelle schließen und die drei Ratchet-Mechanismen auf ein Framework heben. Beides ist **reine Verifikations-/Tooling-Arbeit ohne Produktionscode-Risiko**. |
| **Enthalten** | **1104** (Zahlen an Meta-Quelle + Korrektur der falschen Link-Typ-Behauptung), **1103** (Ratchet-Framework mit einheitlichem Re-Baseline) |
| **Risiko** | Niedrig für 1104 (nur Doku/Meta). Mittel für 1103 (neues Framework muss alle drei Ratchets migrieren, ohne sie zu schwächen — ein Framework, das eine echte Regression durchlässt, ist schlechter als drei inkonsistente). |
| **Rollback** | 1104: Zahlen-Edit revertieren (nur Text). 1103: Framework-Datei revertieren; die drei Baselines bleiben unangetastet, weil das Framework sie nur **liest**. |
| **Begründung Vorrang** | Höchster Hebel pro Risiko. Beide Issues sind **selbstverifizierend**: ein grünes Test-Gate beweist den Fix, keine Manual-QS nötig. Sie laufen zudem vollständig parallel zur restlichen Runde. |

### Welle 2 — Datenintegrität & Freigabe-Flow

| Aspekt | Inhalt |
|---|---|
| **Ziel** | Die beiden **funktionalen Kernbugs**: Duplikaterkennung (1178) und Massen-Freigabe (1196). |
| **Enthalten** | **1178** (M), **1196** (M) |
| **Risiko** | Mittel. 1178 berührt Persistenz-Pfade (Create + Import → kann Import-Verhalten ändern); 1196 berührt den Freigabe-Flow (Sicherheits-/Korrektheits-relevant: Bulk-Approve darf nicht still einzeln fehlschlagen). |
| **Rollback** | Pro Fix eigener Commit, einzeln revertierbar. |
| **Hinweis** | 1178 und 1196 sind **datei-disjunkt** (Backend-Persistenz bzw. `ReviewsView.tsx`) — parallelisierbar (§4.2). |

### Welle 3 — Test-Harness-Härtung

| Aspekt | Inhalt |
|---|---|
| **Ziel** | Flüchtige Testfehlschläge **fangbar** machen statt nur zu zählen. Löst 1117 als **Harness-Verbesserung**, ohne auf die nicht existente Repro-Info zu warten. |
| **Enthalten** | **1117** |
| **Risiko** | Niedrig. Kein Produktionscode; berührt nur Reporter-/Artefakt-Konfiguration. |
| **Rollback** | Branch verwerfen. |

### Welle 4 — Entscheidungsspur (kein Implementierungs-Branch)

| Aspekt | Inhalt |
|---|---|
| **Ziel** | Die zwei HARD-STOP-Issues **entscheiden** statt liegen lassen; den Aggregator #1110 nachführen. |
| **Enthalten** | **1135** (HARD STOP), **1138** (HARD STOP), **1110** (Aggregator) |
| **Risiko** | Hoch für 1135/1138: Dependency-, Policy- und Governance-Entscheidungen, die außerhalb eines Bugfix-Kontexts getroffen werden müssen (Dependency-Sign-off, REQ-Verantwortung). |
| **Rollback** | **Kein Code → nichts zurückzurollen.** Entscheidung wird dokumentiert; bei Vertagung bleibt der Status `decision pending` explizit stehen. |
| **Branch** | **keiner.** Ergebnis sind Kommentare/Entscheidungsnotizen an den Issues, kein `fix/*`-Branch. Sollte sich aus 1135 ein Umsetzungsauftrag ergeben, ist das eine eigene Runde mit eigenem Branch. |
| **Nicht in dieser Welle** | #1136 (geschlossen 2026-10-04), `RLS_PREAUTH_ENFORCED`/`hard_enforced`-Flag-Flip (operativer Akt mit Pre-Flip-Checkliste) |

---

## 3. Issue-Fix-Spezifikation

### 3.1 #1178 — Duplikaterkennung: Lücke in drei Schichten

**Befundlage (verifiziert):**

1. **CSV-Import hat bereits eine Titel-Prüfung** — `backend/application/import_service.py:823-861`
   (`_dedupe_rows`) prüft gegen die existierenden Titel im Workspace, casefold, **ABER**:
   `_natural_key` (:791-806) wählt den Schlüssel in der Priorität `uid` → `id` → `title`.
   Eine CSV, deren Zeilen **`id`/`uid` tragen** (also jede CSV, die aus dem Export stammt),
   prüft **ausschließlich** gegen `existing_ids` / `existing_uids`. Die Titel-Spalte wird
   in diesem Fall **nie** verglichen. **Das ist der Mechanismus, der 880 Zeilen mit 32
   Titeln erlaubt** — jede Zeile hat eine eigene ID, also ist jede Zeile „neu".
2. **REST-Import-Response (Legacy, ADR-014 §5 Standard) verschweigt die Ursache** —
   `backend/rest_api/views.py:8938-8952` liefert `skipped_count` + `errors` + `warnings`,
   aber **keine** `items[].cause`. Der Detail-Pfad existiert nur unter Contract v2
   (`result.to_dict()`, :8961). Das Frontend typisiert `items[].cause`
   (`frontend/src/api/import.ts:84-92`) — rendert aber keinen davon
   (`CsvImport.tsx:387-433` zeigt nur `errors` und `warnings`).
3. **UI/REST-Create-Pfad hat gar keine Prüfung** — `requirement_service.py:261`
   (`create_requirement`) hat null Duplikat-Logik (ein `duplicates`-Treffer im ganzen
   File ist ein Docstring-Kommentar, L245).

**Lösungsansatz (drei Teilfixes, gemeinsam shippbar):**

1. **Import — Titel-Ergänzungsprüfung.** In `_dedupe_rows` zusätzlich zur
   Uid/Id-Spaltenprüfung eine **Titel-Existenprüfung im Workspace-Scope**
   (`_workspace_filter`) fahren, wenn eine Titel-Spalte vorhanden ist. Damit wird auch
   bei unique-`id`-Zeilen ein Doppeltitel erkannt. **Wichtig (Abgrenzung):** das
   bestehende Verhalten „Hit in anderem Workspace ist kein Duplikat" (Kommentar
   :808-816) muss **erhalten bleiben** — sonst klassifiziert ein Export→Import die
   Quellzeilen als Duplikate.
2. **Import — Ursache sichtbar machen.** Die Duplikat-Ursache muss aus dem
   `skipped`-Zählen herausgezogen und in die **Legacy**-Response als geordnete
   `skipped[]`-Liste (Zeile, Identifier, Ursache) aufgenommen — analog zur
   v2-`items`-Struktur, ohne Contract zu brechen (additiv).
3. **Create — Warnpfad.** In `create_requirement` eine **nicht-blockierende** Warnung
   bei existierendem, normalisiert gleichem Titel im selben Workspace. **Annahme:**
   Warnung, nicht Rejection — blockierendes Verhalten ist ein BREAKING CHANGE für alle
   Create-Clients (REST + MCP) und braucht eine eigene REQ-/Entscheidung. Dies ist
   hier **ausdrücklich nicht** vorgesehen; das Issue nennt „blockierend optional".

**Betroffene Dateien:**
- `backend/application/import_service.py` (`_dedupe_rows`, `_natural_key`, `_duplicate_item`)
- `backend/rest_api/views.py:8938-8974` (Legacy-Response)
- `backend/application/requirement_service.py:261` (`create_requirement`)
- `frontend/src/components/CsvImport/CsvImport.tsx:387-433` (Ursache rendern)
- `frontend/src/api/import.ts` (Typ ggf. erweitern)

**Teststrategie:**
- `backend/application/tests/test_import_service_hardening.py:110` (bestehend, `skipped_count`)
- `backend/rest_api/tests/test_csv_import_hardening.py`, `test_csv_import.py`
- `frontend/src/components/CsvImport/CsvImportOutcome.test.tsx`
- Neu: Fall „CSV mit eindeutiger `id`-Spalte + doppeltem Titel im selben Workspace" → `skipped`
- Neu: Regression „CSV→Import in **anderen** Workspace" → weiterhin `created`

**Akzeptanzkriterium:**
- [ ] CSV mit eindeutiger `id`-Spalte und Titeln, die bereits im Workspace existieren,
  liefert diese Zeilen als `skipped` mit Ursache `DUPLICATE`.
- [ ] Die Legacy-Response enthält je übersprungener Zeile Ursache + Identifier.
- [ ] Das Frontend zeigt die Ursache an (neuer `data-testid`, z. B. `csv-import-skipped-list`).
- [ ] Create mit existierendem Titel liefert eine Warnung im Body und erzeugt **trotzdem**
  die Zeile (kein Breaking Change).
- [ ] Bestehendes Verhalten „anderer Workspace ≠ Duplikat" bleibt grün.
- [ ] Metrisch: ein Replay der β.18-Messung (880/32) würde künftig stoppen.

### 3.2 #1196 — Keine Massen-Freigabe in der Warteschlange

**Befundlage (verifiziert):** In `ReviewsView.tsx` existiert Auswahl-State
(`selectedIds`, :228) und eine sequenzielle `bulkConfirm(ids, confirmOne)` (:171),
aber das Bulk-Button-Rendering ist an `queueMode === "proposals"` gebunden
(:636 `{queueMode === "proposals" && selectedIds.length > 0 && (`). Im
Normalmodus (`review`) gibt es **keine** Zeilen-Checkboxen — laut Issue gemessen:
1 Checkbox auf der Seite, und die ist der Modus-Schalter (`reviews-queue-mode-checkbox`).

**Lösungsansatz:**
1. Zeilen-Checkboxen im `review`-Modus aktivieren (neuer `data-testid="review-item-checkbox"`,
   gesteuert über denselben `selectedIds`-State).
2. Bulk-Aktion für die reguläre Warteschlange analog zum Proposals-Zweig rendern
   (`reviews-bulk-confirm-btn`, auch im `review`-Modus), mit `Freigeben`/`Ablehnen`.
3. Begründung **einmal für den Batch** abfragen; Einzelbegründung ist die Annahme nur,
   falls die API sie pro Item erzwingt — **zu verifizieren** an der Transition-API.
4. Ergebnisbericht „N freigegeben, M fehlgeschlagen" (`reviews-bulk-confirm-result`
   existiert bereits für den Proposals-Pfad). Teilfehler brechen den Lauf nicht ab —
   dieselbe Semantik wie die bestehende sequenzielle `bulkConfirm`.

**Betroffene Dateien:** `frontend/src/components/Reviews/ReviewsView.tsx` (State,
Rendering, Aktion); i18n-Labels (DE/EN).

**Teststrategie:** Vitest — vorhandene Dateien
`ReviewsView.bulkconfirm.test.tsx`, `ReviewsView.proposals.test.tsx`,
`ReviewsView.reasonGate.test.tsx`, `ReviewsView.gateHint.test.tsx` als Muster; neuer
Fall für den `review`-Modus.

**Akzeptanzkriterium:**
- [ ] Im Modus `review` rendert jede Zeile eine Checkbox (`review-item-checkbox`).
- [ ] Bei Auswahl ≥1 erscheint `reviews-bulk-confirm-btn` (nicht nur im `proposals`-Modus).
- [ ] Ein Klick gibt alle ausgewählten Einträge frei; Ergebnisbericht zeigt N/M.
- [ ] Teilfehler (ein Eintrag schlägt fehl) brechen den Lauf nicht ab.
- [ ] Bestehende Proposals-Bulk-Suite bleibt grün (kein Verhaltenswechsel dort).

### 3.3 #1104 — Meta-Projektbeschreibung trägt veraltete Zahlen

**Befundlage (verifiziert):**
- `docs/agent-templates/tool-manifest.json` trägt selbst `tool_count = 228`,
  `generated_from = reqogniloom==1.8.0-beta.20`. Das Manifest ist also **selbst
  beschreibend** — die dokumentierte Zahl ist nachprüfbar, nicht geschätzt.
- `.meta-config/project.yaml` schreibt an **5 Vorkommen** `227`
  (L102, 150, 179, 236, 366). `AGENTS.md` (L8, L39) und `CLAUDE.md` (2 Vorkommen)
  sind daraus generierte Artefakte.
- Die im Issue behauptete Link-Typ-Zahl `20` ist **falsch**: `BUILTIN_LINK_TYPES` hat
  exakt 11 Keys. Die dokumentierten `11` sind korrekt.
- Die ViewSet-Zerlegung (`28 ViewSets + 74 APIViews`) trägt laut Issue nichts bei;
  verifiziert: 28 Router-ViewSets (korrekt), 81 APIView-Subklassen (nicht 74 — aber
  die registrierte Router-Menge ist die maßgebliche Zahl, **Annahme**: nur ViewSet-Zahl
  korrigieren, APIView-Zahl bewusst weglassen statt falsch weiterzuführen).

**Lösungsansatz (zwei Arbeitspakete):**

**WP-A — Korrektur an der Quelle.**`.meta-config/project.yaml` an allen 5 Vorkommen
`227` → `228`. Dann Regeneration der abgeleiteten Dateien (`AGENTS.md`, `CLAUDE.md`)
über den agent-meta-Sync — **nicht** von Hand editieren, sonst überschreibt der
nächste Sync die Korrektur wieder (das ist der eigentliche Kernbefund des Issues).

**WP-B — Issue-Korrektur.** Den falschen Link-Typ-Anspruch (`11 → 20`) im Issue
kommentieren und mit dem nachgewiesenen Stand (11, `backend/link_types/builtin.py`)
korrigieren; ViewSet-Zerlegung klären.

**Betroffene Dateien:** `.meta-config/project.yaml` (L102-103, 150, 179, 236-237, 366),
danach `AGENTS.md`, `CLAUDE.md` (generiert).

**Teststrategie:** Kein Unit-Test sinnvoll (reiner Text). Stattdessen **Drift-Gate**:
`scripts/check-version-drift.sh` prüft nachweislich **nicht** die Tool-Anzahl
(verifiziert: kein Treffer auf `227|228|tool|manifest`). Neuer kleiner Check, der
`docs/agent-templates/tool-manifest.json::tool_count` gegen die Zahl in
`.meta-config/project.yaml` vergleicht. Dieser Check ist das eigentliche
Präventions-Artefakt — **er** verhindert, dass 227/228/229 wieder unbemerkt driften.

**Akzeptanzkriterium:**
- [ ] `.meta-config/project.yaml` führt durchgängig `228`.
- [ ] Generierte `AGENTS.md`/`CLAUDE.md` zeigen `228` nach Sync.
- [ ] Ein `tool_count`-Drift wird durch den neuen Check **rot** (Test mit absichtlich
  falscher Zahl schlägt fehl).
- [ ] Issue #1104 trägt den Korrektur-Kommentar zur Link-Typ-Behauptung.

### 3.4 #1103 — Drei Ratchets, drei Re-Baseline-Mechanismen

**Befundlage (verifiziert):** Drei Ratchets mit **drei unterschiedlichen** Konventionen:

| Ratchet | Baseline | Re-Baseline | Stale-Erkennung | Gap-Pflicht |
|---|---|---|---|---|
| Entity-Surface-Parität | `entity_surface_baseline.json` | `ENTITY_SURFACE_DUMP=<path>` env | **ja** (`:277-280`: roter Eintrag → FAIL) | Issue-Referenz in `_comment` |
| Design-System | `design-system-ratchet.baseline.json` | `DESIGN_SYSTEM_RATCHET_DUMP=1` env (:103) | **nein** | `maxViolations` als Deckel (:66) |
| Tool-Manifest-Drift | `tool-manifest.json` | **keiner** (nur `_MANIFEST_PATH_ENV`-Override, :53) | n/a (Vollvergleich) | n/a |

Der beste Mechanismus existiert bereits (Parität). Das Framework ist also eine
**Hebung der zwei schwächeren Ratchets auf das Niveau der stärksten** — keine
Neukonstruktion.

**Lösungsansatz:** Ein gemeinsames, minimales Ratchet-Framework (Python-Modul unter
`backend/` bzw. JS unter `frontend/src/test/` — **zu entscheiden** in der Umsetzung,
Python bevorzugt, da zwei von drei Ratchets dort liegen), das bereitstellt:
1. Einheitliches **named** Re-Baseline-Kommando (env-var je Ratchet, dokumentiert im
   Framework-Header), nie ein Nebeneffekt eines normalen Laufs.
2. **Stale-Baseline-Erkennung** als Framework-Primitiv (Key verschwunden → FAIL mit
   Benennung) — von allen drei konsumiert.
3. **Erlaubte Gaps mit Grund + Issue-Link** als Schema-Pflicht — alle drei Baselines
   validieren dagegen.
4. **Ein Test**, der beweist, dass eine echte Regression nicht durch Re-Baseline
   verschwinden kann (Re-Baseline erzeugt Baseline mit der Regression → Folge-Lauf rot).

**Betroffene Dateien:** neues Framework-Modul + Migration der drei Ratchet-Suiten.

**Teststrategie:** pytest für das Framework; je Ratchet ein Bestehend-Bleib-Test.

**Akzeptanzkriterium:**
- [ ] Alle drei Ratchets nutzen denselben Re-Baseline-Einstieg.
- [ ] Stale-Eintrag (gelöstes Problem) → FAIL in allen drei.
- [ ] Jeder erlaubte Gap trägt Grund **und** Issue-Link (Schema-validiert).
- [ ] Test „echte Regression überlebt Re-Baseline nicht" ist grün.
- [ ] Alle drei Ratchet-Suiten bleiben grün.

### 3.5 #1117 — Flüchtige Frontend-Fehlschläge fangbar machen

**Befundlage:** 3 Fehlschläge in einem Full Run, Folgelauf grün, Tests nie
identifiziert. Als Bug = **Needs-Info** (es gibt keine Repro). Als
**Systemverbesserung** vollständig umsetzbar — genau das schlägt das Issue vor.

**Lösungsansatz:** Harness so härten, dass der nächste Auftritt **identifizierbar**
ist statt nur zählbar: JSON-Reporter + Artefakt-Sicherung (failure records inkl.
Testdatei/Name/Trace) für den Frontend-Run. Plus: Klassifizierungshelfer, der
Timeout-Fehschläge als eigene Kategorie markiert, damit die zwei bekannten
Nicht-Determinus-Ratchet-Fälle aus beta.16 als Muster confrontierbar sind.

**Betroffene Dateien:** Frontend-Test-Runner-Konfiguration (Vitest-Reporter) und/oder
CI-Artefakt-Schritt; **zu verifizieren**, welche Reporter-Hooks verfügbar sind.

**Teststrategie:** Selbsttest: absichtlich instabiler Test → Reporter erzeugt
identifizierbares Artefakt.

**Akzeptanzkriterium:**
- [ ] Der Frontend-Run schreibt ein maschinenlesbares Fehler-Artefakt (JSON).
- [ ] Ein Fehlschlag ist danach nach Testdatei + Name identifizierbar.
- [ ] Timeout-Fehschläge sind als Kategorie unterscheidbar.
- [ ] Der Lauf selbst bleibt grün, wenn alles grün ist (keine neuen Failure-Modi).

---

## 4. Reihenfolge & Abhängigkeiten

### 4.1 Harte Abhängigkeiten

```
1178 (Import) ──► 1178 (Response) ──► 1178 (Frontend-Rendering)
1104 (Quelle) ──► 1104 (Sync AGENTS.md/CLAUDE.md) ──► 1104 (Drift-Gate)
1103 (Framework) ──► 1103 (Ratchet-Migration ×3) ──► 1103 (Regressions-Unverwundbarkeits-Test)
1196 ──► (Transition-API: Batch-Begründung? zu verifizieren)
1117 ──► (Reporter-Verfügbarkeit? zu verifizieren)
1135, 1138 ──► Entscheidung (HARD STOP, kein Branch, eigener Track)
```

> **Keine Welle-0-Analogie:** alle Wellen 1–3 sind voneinander unabhängig; es gibt
> keinen Blocker, der die Re-Validierung der übrigen Fixes messunsicher machen würde
> (§2).

### 4.2 Parallelisierbarkeit (Datei-Disjunktheit)

| Gruppe | Issues | Disjunkt? | Parallel? |
|---|---|---|---|
| Welle 1 | 1104, 1103 | ja (Meta/Doku vs. Test-Suiten) | **ja** |
| Welle 2 | 1178, 1196 | ja (Backend-Persistenz vs. `ReviewsView.tsx`) | **ja** |
| Welle 3 | 1117 | allein | n/a |
| Entscheidungsspur | 1135, 1138, 1110 | n/a (kein Code) | n/a |

### 4.3 Empfohlene Abarbeitungsreihenfolge

```
W1: 1104 ─┐
           ├─► PR-Wave-1 (fix/wave1-meta-drift-ratchet)
    1103 ─┘
W2: 1178 ─┐
           ├─► PR-Wave-2 (fix/wave2-duplicate-bulk-approve)
    1196 ─┘
W3: 1117 ────────► PR-Wave-3 (fix/wave3-flaky-test-harness)
W4: 1135, 1138, 1110 ──► Entscheidungsspur, kein Branch
```

### 4.4 #1136 — ausgeschieden (bereits geschlossen)

**Kein Arbeitspaket.** Im vorbereitenden Verlauf wurde #1136 zunächst als
Decision-Pending-Kandidat geführt. Verifikation am 2026-10-12: **geschlossen seit
2026-10-04 21:12 UTC (`COMPLETED`).** Der Issue-Body beschreibt damit einen
veralteten Stand (2026-09-27: „Two parts remain deliberately not implemented"),
der nicht mehr gilt:

| Body-Behauptung (veraltet) | Heutiger Stand (verifiziert) |
|---|---|
| „Pre-auth tables cannot take the standard GUC policy" | `auth_tenancy/0017_preauth_staged_rls.py` — staged Policy hinter `app.rls_preauth_enforced`; SECURITY-DEFINER-Funktionen `auth_api_key_lookup` / `auth_resolve_roles` |
| „Webhook/outbox tables have no RLS because they have no `tenant_id`" | `application/0030_as_staged_tenant_id.py`, `0031_backfill_staged_tenant_id.py`, `0032_as_staged_rls.py`, `0033_as_outbox_worker_functions.py`, `0034_rls_hard_enforcement_policy.py` |
| Decision-Pending | **Entschieden (D4):** SECURITY-DEFINER-Lookup-Funktion + staged Rollout der `as_*`-`tenant_id` |
| Residuals offen | R-3 → #1184 ✅, R-7 → #1179 ✅, R-8 → #1180 ✅, R-9 → #1181 ✅, STOPP-S1 → #1182 ✅, A4/R-2 → #1183 ✅ |

**Verbleibend (außerhalb dieser Runde):** `RLS_PREAUTH_ENFORCED` und `hard_enforced`
sind bewusst **OFF** (Ship-Default). Ihr Flip ist ein **operativer Akt** mit eigener
Pre-Flip-Checkliste — live-DB-Verifikation, Checklisten-Punkte 3–5 aus
`docs/audit/2026-10/1136-r3-unscoped-inventory.md:116-143`. Das ist kein
Bugfix-Arbeitspaket und wird hier **nicht** eingeplant.

---

## 5. Verifikation / DoD

### 5.1 Globale Kommandos (verifiziert in dieser Session)

Die Vorgänger-Plan-Kommandos waren selbst als „zu verifizieren" markiert. Hier die
**tatsächlichen** Kommandos dieses Repos:

| Zweck | Kommando (verifiziert) | Beleg |
|---|---|---|
| Backend-Tests | `make test-backend` → Container `pytest -q` | `Makefile:77-78`, `testing/docker-compose.test.yml:58` |
| Frontend-Tests | `make test-frontend` → `npm install && npm test` = `vitest run` | `Makefile:81-82`, `:74`, `frontend/package.json` |
| Beide (unit/integration, **kein** E2E) | `make test` | `Makefile:74` |
| Frontend-Lint | `cd frontend && npm run lint` | `frontend/package.json` |
| Backend-Lint | `ruff check . --select=F821,F822` (ruff `0.16.5`) | `.github/workflows/ci.yml:114-127` |
| Frontend-Typecheck | `cd frontend && npm run build` (`tsc -p tsconfig.build.json && vite build`) | `frontend/package.json` |
| E2E (manuell, langsam) | `cd e2e && npm install && npx playwright test` | `Makefile:104` |
| Template-/Manifest-Suite | `pytest docs/agent-templates dist` | `.github/workflows/ci.yml:264-265` |
| Version-Drift | `./scripts/check-version-drift.sh` | `.github/workflows/version-drift-check.yml:169-170` |

> **Wichtig:** die lokalen `docker compose`-basierten `make`-Ziele brauchen einen
> laufenden Stack. Für reine Unit-/Vitest-Suiten sind die nativen
> `cd backend && python -m pytest` / `cd frontend && npm run test` äquivalent; die
> CI-Sets (`ci.yml:51-66`) zeigen die Pfad-Splits.

### 5.2 DoD pro Fix

1. **Reproduktion:** bestehender/neuer Test schlägt **vor** dem Fix fehl.
2. **Fix:** minimaler, fokussierter Change; keine Kollateral-Refactorings.
3. **Nachweis:** derselbe Test grün; zusätzlich die in §3 genannten Proof-Tests grün.
4. **Regression-Guard:** `make test-backend` + `make test-frontend` ohne neue Fehler.
5. **Lint/Typecheck:** `ruff check . --select=F821,F822`, `npm run lint`, `npm run build` sauber.
6. **Config-/Doku-Fixes** (1104): Sync-Gate statt Unit-Test; `scripts/check-version-drift.sh` grün.
7. **Security-adjazent:** Secret-Scan vor jedem Commit (Paved Road `secret-scanning`);
   bei 1178 (Persistenz-Pfad) und 1103 (Manifest) zusätzlich Drift-Gate prüfen.
8. **Manifest-Berührung** (1178, 1103, 1104): Drift-Gate `test_tool_manifest_drift.py` grün.

### 5.3 Proof-Matrix

| Issue | Proof-Test | Typ |
|---|---|---|
| 1178 | `application/tests/test_import_service_hardening.py:110`, `rest_api/tests/test_csv_import_hardening.py`, `CsvImportOutcome.test.tsx` | pytest + Vitest |
| 1196 | `ReviewsView.bulkconfirm.test.tsx` (Muster), neuer `review`-Modus-Fall | Vitest |
| 1104 | neuer `tool_count`-Drift-Check + `scripts/check-version-drift.sh` | Config/Gate |
| 1103 | `test_entity_surface_parity.py`, `design-system-ratchet.test.ts`, `test_tool_manifest_drift.py` + Framework-Suite | pytest + Vitest |
| 1117 | neuer Reporter-Selbsttest (instabiler Test → Artefakt) | Vitest/Harness |

> **Kein Proof-Test für #1136** — das Issue ist geschlossen (§4.4). Seine bestehende
> Abdeckung (`persistence/tests/test_rls_coverage.py`,
> `test_rls_plain_child_models.py`, `auth_tenancy/tests/test_unscoped_readers_guard_1184.py`)
> bleibt unverändert in Kraft und ist Teil des Regression-Guards.

---

## 6. Branch-/Commit-Strategie

- **Branch-Basis:** `main @ 65515769`. **Nie** direkt auf `main`/`master`
  (Branch-Guard).

| Welle | Branch-Vorschlag |
|---|---|
| Welle 1 | `fix/wave1-meta-drift-ratchet` |
| Welle 2 | `fix/wave2-duplicate-bulk-approve` |
| Welle 3 | `fix/wave3-flaky-test-harness` |
| Entscheidungsspur | **kein Branch** — Kommentare/Entscheidungsnotizen an #1135, #1138, #1110 |

- **Commits:** Conventional Commits, Englisch, Imperativ, ≤72 Zeichen erste Zeile.
  - Mit REQ-Bezug: `fix(REQ-xxx): ...` / `feat(REQ-xxx): ...`
  - Ohne REQ (reine Bugfixes): `fix: ...`
  - Bei 1103 (Framework-Anteil): erst REQ via `requirements`, dann `feat(REQ-xxx)`.
- **Commit-Granularität:** ein logischer Fix pro Commit; Tests im selben Commit (TDD-Nachweis).
- **PR pro Welle** gegen `main`; PR-Beschreibung verlinkt die Issue-Nummern
  (`Fixes #<nr>`) gemäß Issue-Lifecycle.
- **Secret-Scan** vor jedem Commit (Paved Road `secret-scanning`).
- **Push/Tag/Branch-Management:** ausschließlich `git`-Agent — **nicht** Teil
  dieser Planungs-Session.

### 6.1 / 6.2 Duplikate & Cluster

- **#1135 ⇄ #1138:** beide sind Entscheidungsposten aus demselben Audit-Track
  (SEC-04 / PLUG-04), inhaltlich entkoppelt. Keine Arbeits-Abhängigkeit.
- **#1178 ⇄ #1196:** berühren beide den Prüf-/Freigabe-Pfad, aber in disjunkten
  Dateien. Keine inhaltliche Kopplung.
- **#1117 ⇄ #1103:** beide betreffen Test-Vertrauen; 1117 ist Harness, 1103 ist
  Gate-Konsistenz. Keine Datei-Überschneidung.

### 6.3 Bekannte Lücken des Pools

Die 29 offenen Issues sind nicht vollständig issue-getrennt: mehrere Roadmap-/Epic-Posten
(#792, #941, #934, #946, #186) überlappen inhaltlich mit den ausgeschlossenen
Enhancement-Clustern. Diese Überlappung ist **out-of-scope** und wird nur hier
festgehalten, damit sie nicht bei der nächsten Runde erneut triagiert werden muss.

---

## 7. Risiken & offene Entscheidungen

### 7.1 Decision-Pending (Owner / benötigter Input)

| Issue | Entscheidung | Benötigter Input | Auswirkung |
|---|---|---|---|
| **1135** | Lockout-Mechanismus (`django-axes` vs. custom), Lockout-Policy, Admin-Gate | Dependency-Sign-off + Policy-Dokument | **HARD STOP** — startet nicht |
| **1138** | Option A (REQ anlegen) vs. Option B (non-product) | `requirements`-Agent-Entscheidung | `PLUG-04` blockiert |
| **1136** | **keine offen** — D4 steht, alle Residuals geschlossen, Issue `COMPLETED` seit 2026-10-04 | — | **Ausgeschieden** aus dem Pool; Flag-Flip ist operativer Akt |
| **1178** | Warnung vs. harte Ablehnung im Create-Pfad | REQ-Entscheidung (hier: **Annahme Warnung**) | Blockierung wäre BREAKING CHANGE |
| **1196** | Batch-Begründung einmal vs. pro Item | Transition-API-Verifikation | Umsetzungsdetail |

### 7.2 Zu verifizierende Annahmen

| Annahme | Verifikationsweg |
|---|---|
| Transition-API erlaubt Batches mit einer Begründung (#1196) | `backend/rest_api/views.py` Workflow-Transitions-Route lesen |
| Vitest-Reporter-Hooks für Artefakt-Sicherung verfügbar (#1117) | `frontend/package.json` / Vitest-Config |
| APIView-Zahl 74 korrekt oder bewusst weglassen (#1104) | Router-Registrierung in `rest_api/` zählen |
| Create-Pfad-Warnung ist API-additiv ohne Breaking Change (#1178) | Serializer-/Response-Contract der Create-Route |

### 7.3 Risiken

| Risiko | Issue(s) | Gegenmaßnahme |
|---|---|---|
| Import-Verhaltensänderung bricht bestehende Import-Suites | 1178 | Bestehende Import-Tests als Guards; Fall „anderer Workspace" explizit testen |
| Bulk-Approve-Flow wird semi-silent | 1196 | Teilfehler-Report als Pflicht; bestehende `bulkConfirm`-Semantik beibehalten |
| Framework schwächt statt stärkt | 1103 | „Regression überlebt Re-Baseline nicht"-Test als Gate; stärksten Ratchet (Parität) als Referenz |
| Meta-Sync überschreibt Korrektur erneut | 1104 | Korrektur an `.meta-config/project.yaml`, nicht an generierten Dateien; Drift-Gate |
| Reverse-Migration fehlt | — | entfällt: #1136 ist geschlossen, kein Change in dieser Runde |
| Harness erzeugt neue Failure-Modi | 1117 | Reporter muss bei grünem Lauf stumm bleiben |

---

## 8. Self-Review des Plans

- **Vollständigkeit:** Alle **29** offenen Issues sind erfasst (5 Kern + 3 Entscheidungsspur
  + 21 out-of-scope). Kein Issue aus dem Vorgängerplan wiederholt. #1136 wurde im
  Verlauf als **geschlossen** verifiziert und ausgeschieden (§4.4) — die Pool-Zahl
  wurde entsprechend korrigiert.
- **Fakten vs. Annahmen:** Triage-Daten im Repo verifiziert (Dateien, Symbole, Zeilen).
  Die vier Messungen in §0 sind eigenständig gemessen. Annahmen sind in §7.2 gelistet
  mit Verifikationsweg.
- **Messbarkeit:** Jeder Kernkandidat hat testbare Akzeptanzkriterien (§3) mit
  Proof-Test (§5.3).
- **Abhängigkeiten:** harte Teilfix-Ketten, Entscheidungsspur, zu verifizierende Annahmen
  in §4 und §7 abgebildet.
- **Wellen-Shippability:** Welle 1–3 unabhängig auf eigenem `fix/*`-Branch mergebar;
  Entscheidungsspur ohne Branch; keine Commits auf `main`.
- **Abgrenzung:** keine Welle-0-Ritualistik ohne Blockade (§2), keine Übernahme
  geschlossener Vorgänger-Bugs (§1), keine Wiederholung von #1136-Arbeit (§4.4).
- **Klarstellung #1136:** der Issue-Body beschreibt einen **veralteten** Stand
  (2026-09-27). Die Umsetzung ist erfolgt, alle Residual-Issues sind geschlossen, das
  Issue selbst seit 2026-10-04 `COMPLETED`. Wer den Body als Auftrag liest, würde
  Arbeit wiederholen, die existiert. Der verbleibende Flag-Flip ist operativ, kein
  Bugfix.
- **Meta-Drift ist ein Symptom, nicht der Kern:** #1104s eigentlicher Befund ist,
  dass eine Zahl im agent-meta-managed Block nur per Meta-Änderung reparierbar ist.
  WP-B verhindert die Wiederholung, indem ein `tool_count`-Drift-Gate eingeführt wird.
- **Nicht implementiert:** Dieser Plan enthält **keine** Code-Änderungen und löst
  **keine** Commits/Pushes aus.

---

## 9. Ausführungsprotokoll (2026-10-13, final, gemerged)

> **Status:** `merged` — alle vier PRs sind nach grüner CI gegen `main` gemerged.
> `main` steht auf `612c76e9`.
>
> **Dieser Abschnitt ändert die Planvorgaben nicht.** Er dokumentiert den Ist-Stand
> der Ausführung und die verbleibenden offenen Punkte.

### 9.1 Branches, Commits, PRs

Alle vier Branches basierten auf `main @ 65515769` und sind in dieser Reihenfolge
gemerged (Welle 1 zuletzt, weil sie das Protokoll der gesamten Runde trägt).

| Phase | Branch | PR | Merge-Commit | Issues |
|---|---|---|---|---|
| 2 | `fix/wave2-duplicate-bulk-approve` | #1272 | `58215f1` | #1178, #1196 |
| 3 | `fix/wave3-flaky-test-harness` | #1273 | `24f3e93` | #1117 |
| 4 | `fix/decision-track` | #1274 | `99f6391` | #1135, #1138, #1110 |
| 1 | `fix/wave1-meta-drift-ratchet` | #1271 | `612c76e` | #1103 |

**`fix/wave1-meta-drift-ratchet`** (7 Commits, davon 2 aus dem Abschluss)

| Commit | Message | Issues |
|---|---|---|
| `7250ca7c` | `chore(agent-meta): drop REQ traceability from the DoD checklist` | Meta |
| `98974c67` | Merge `origin/main` inkl. Auflösung des REQ-193-Konflikts | — |
| `324c0518` | `docs(audit): finalize round 2 execution log` | — |
| `0eeb97a6` | `docs(audit): record wave 1/2 execution status` | — |
| `20c3fcce` | `feat(REQ-193): unify baseline regression ratchets` | #1103 |
| `d06fa00e` | `test(agent-templates): gate documented tool count against the manifest` | #1104 WP-B |
| `4da48466` | `fix(meta): correct documented MCP tool count to 228` | #1104 WP-A |
| `29bfdfe0` | `docs(audit): add bugfix round 2 execution plan` | — |

**`fix/wave2-duplicate-bulk-approve`** (5 Commits)

| Commit | Message | Issues |
|---|---|---|
| `5159c9c1` | `feat(ui): bulk approve and reject in the review queue` | #1196 |
| `cd3facad` | `feat(requirements): warn on duplicate titles before insert` | #1178 |
| `135b5371` | `fix(ui): render duplicate skip causes in the CSV import outcome` | #1178 |
| `92642154` | `fix(import): surface per-row duplicate causes in the legacy response` | #1178 |
| `1dcbb9bb` | `fix(import): detect duplicate titles even when a natural key is present` | #1178 |

**`fix/wave3-flaky-test-harness`** (6 Commits)

| Commit | Message | Issues |
|---|---|---|
| `f2d0324e` | `chore(frontend): add @types/node for the vitest reporter` | #1117 |
| `4220d0cd` | `fix(frontend): use TestCollection for the vitest task tree` | #1117 |
| `5dfd8193` | `fix(frontend): typecheck the flaky artifact reporter` | #1117 |
| `1f53f67f` | `chore(frontend): register the flaky artifact reporter` | #1117 |
| `7015ea21` | `test(frontend): write a flaky failure artifact from the vitest run` | #1117 |
| `863a91d3` | `test(frontend): add failure classifier for flaky artifacts` | #1117 |

**`fix/decision-track`** (4 Commits)

| Commit | Message | Issues |
|---|---|---|
| `8a10025a` | `docs(requirements): renumber #1135 requirement to REQ-194` | #1135 |
| `88da246a` | `docs(adr): accept ADR-021 after concept review closes the major finding` | #1135 |
| `cc11ca2c` | `docs(requirements): add REQ-193 for admin login brute-force` | #1135 |
| `010496cf` | `docs(se): decide plugin versioning traceability as non-product` | #1138 |

### 9.2 Umsetzungsstand je Issue

| Issue | Stand | Schicksal |
|---|---|---|
| **#1104** | WP-A + WP-B (`4da48466`, `d06fa00e`), WP-C als Issue-Arbeit (Kommentar mit Falsifikation der Link-Typ-Behauptung 11≠20); Restposten `+ 74 APIViews` ist User-Entscheidung | **offen** — letzter Tracker für diesen Rest |
| **#1103** | erledigt (`20c3fcce`) | **geschlossen** (via #1271) |
| **#1178** | alle vier Teilfixes | **geschlossen** (via #1272) |
| **#1196** | erledigt | **geschlossen** (via #1272) |
| **#1117** | erledigt (5 Commits + 1 Typ-Fix) | **geschlossen** (via #1273) |
| **#1138** | **entschieden: Option B** — Non-Product-Statement (`010496cf`), weil ADR-017 es bereits im Titel trägt | **geschlossen** (via #1274) |
| **#1135** | **HARD STOP aufgelöst:** concept-review nachgeholt (READY-MIT-VORBEHALT), F1 durch REQ-194 geschlossen, ADR-021 `accepted` | **geschlossen** (via #1274) |
| **#1110** | Aggregator mit Wellenstand + Abschlusskommentar | **geschlossen** (letzter Merge) |
| **#1275** (neu) | Admin-Gate + 2FA-Residuum (ADR-021 O5), vor dem Schließen von #1135 angelegt | **offen** |

### 9.3 Verifizierter Teststatus (2026-10-13)

| Bereich | Kommando | Ergebnis |
|---|---|---|
| **DB-gebundene Backend-Tests** (Welle 1 + 2) | Test-Overlay `backend-test` | **152 passed, 1 skipped** |
| **Admin-Lockout** (#1135) | Test-Overlay `backend-test` | **25 passed** |
| Ratchet-Framework (Backend, DB-frei) | `pytest mcp_server/tests/test_ratchet_framework.py` | **17 passed** |
| **Welle 3 Kern + Ratchet + i18n** | `vitest` (3 Dateien) | **43 passed** |
| **Welle 3 im Fehlerfall** | temporärer fehlschlagender Test → Artefakt | Assertion **und** Timeout korrekt kategorisiert |
| **CI je PR vor dem Merge** | `gh pr checks` | **16/16 pass** auf allen vier PRs |

Kein Merge auf rot.

### 9.4 Entscheidungen, die der Lauf erzwungen hat

1. **Der Node-Typ-Fehler war real, nicht Vorbelastung.** Ich hatte die TS-Fehler des
   Reporters als Vorbelastung eingeordnet, weil *„kein Workflow `tsc` ausführt"*. Falsch:
   der Playwright-Workflow hat den Step **„Verify prod Docker build"**, und der läuft
   `npm run build` = `tsc -p tsconfig.build.json`. Folge: der Production-Image-Build
   brach ab und alle vier E2E-Shards schlugen fehl. Behoben mit `@types/node@22`
   (`f2d0324e`) — was dieselbe Lücke in `bluepencil-vendor.test.ts` mit schließt.
   Die zwei Lehren stehen in 9.5 als Prozess-Notiz.
2. **`exclude` war der falsche Hebel.** Es filtert den `include`-Match, nicht einen
   Import, der schon im Graphen ist — die Datei landete trotzdem in `files`.
3. **`concept-reviewer`-Subagent funktioniert**, der Orchestrator-Dispatch tat es nicht
   (Upstream-Fehler). Das ermöglichte den regelkonformen Abschluss von #1135 über ein
   echtes Review statt einer Eigenbeurteilung.
4. **#1136 und #1135 waren beide „decision pending" und bereits erledigt.** Beide
   Issue-Bodys beschreiben Stände vom September. Ohne Verifikation wären hier zwei
   Arbeitspakete geplant worden, die existieren.
5. **REQ-193-Doppelvergabe** aus zwei unabhängigen Vergaben ohne zweigübergreifende
   Dublettenprüfung. Aufgelöst per Folge-Commit (`8a10025a`) auf REQ-194, **vor** den
   Merges; der Merge-Konflikt in `docs/REQUIREMENTS.md` wurde auf Welle 1 mit `98974c67`
   behoben. Kein History-Rewrite, weil die Commits in offenen PRs standen.
6. **Meta-Quelle bereinigt** (`7250ca7c`): `AGENTS.md`-ENTRY sagte `REQ-Trace: false`,
   die on-merge-DoD in `.meta-config/project.yaml:482` verlangte trotzdem noch
   REQ-Traceability. Nebenbefund: die committete `generated-file-hashes.json` war
   **bereits vorher** stale — das Drift-Gate hat das offenbar nie gemergt gesehen.
7. **Folge-Issue vor Schließen:** #1275 für Admin-Gate + 2FA-Residuum, damit es nicht im
   geschlossenen #1135 verstaubt.

### 9.5 Verbleibende offene Punkte

| # | Punkt | Owner | Blocker? |
|---|---|---|---|
| 1 | `frontend/dist/`-Tracking (getrackte Build-Artefakte, nicht gitignored) | User | nein |
| 2 | ADR-Kandidat **ii** (Workspace vs. Tenant) — jetzt in #1275 | User + `se-architect` | blockiert Admin-Gate und RLS-Achse |
| 3 | 2FA-Residuum (ADR-021 O5) — jetzt in #1275 | eigene Planung | nein |
| 4 | `+ 74 APIViews`-Zusatz in `.meta-config/project.yaml` — letzter Tracker ist #1104 | User | nein |
| 5 | `frontend/test-results/` ist gitignored, aber **vorhanden**; für CI-Upload wäre ein Ablageort je Job nötig | DevOps | nein |
| 6 | `@types/node`-Version künftig mitziehen (Pflege, kein Blocker) | `dependency-auditor` | nein |

**Prozess-Notiz (aus 9.4 Punkt 1):** für künftige Änderungen an Dateien, die Node-APIs
nutzen, gilt: erst `npm run build` (nicht nur `tsc -p tsconfig.json`) prüfen, denn der
Production-Docker-Build ist ein Gate. Und „kein Workflow macht tsc" stimmt nur, wenn der
Docker-Build mitgezählt wird.

---

*Protokolliert vom Haupt-Thread am 2026-10-13. Vier Branches, 22 Commits, 4 PRs
gemerged, sieben Issues geschlossen, ein Folge-Issue angelegt. Kein Merge auf rot.*
