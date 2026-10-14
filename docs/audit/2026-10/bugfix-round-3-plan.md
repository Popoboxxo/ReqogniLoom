---
title: Bugfix-Runde 3 — Umsetzungsplan (beta.20-Nachmeldung)
date: 2026-10-13
branch_base: origin/main @ 1b3e85af
author_agent: orchestrator
status: proposed
scope: 24 verifizierte beta.20-Bugs in 6 Wellen + 6 getroffene Entscheidungen (§8.1)
---

# Bugfix-Runde 3 — Umsetzungsplan

> **Status:** `proposed` — dieser Plan implementiert **nichts** selbst. Er beschreibt
> Paket, Reihenfolge, Wellen, Fix-Ansätze und Akzeptanzkriterien.
>
> **Faktenbasis:** Alle Befunde wurden **in dieser Session im Repo verifiziert**
> (Stand `origin/main @ 1b3e85af`, lokaler Branch `chore/round-2-closeout @ 252c3571`).
> Verifizierte Angaben sind mit „**verifiziert**" markiert; Issue-Behauptungen ohne
> Repo-Beleg als „laut Issue"; Hypothesen explizit als **Annahme**.
>
> **Abgrenzung zum Vorgänger** (`docs/audit/2026-10/bugfix-round-2-plan.md`, 2026-10-12,
> 8 Issues in 4 Wellen): jene Runde ist **gemerged** (`main` stand danach auf `612c76e9`,
> Closeout `252c3571`). **Kein Issue der Runde 2 ist hier erneut enthalten.** Dieser Plan
> arbeitet ausschließlich die **seit 2026-10-12 neu gemeldete beta.20-Bugflut** ab plus die
> vier in §9.5 der Runde 2 hinterlassenen Restpunkte.

---

## 0. Ausgangslage

| Aspekt | Wert (verifiziert, 2026-10-13) |
|---|---|
| Branch | `chore/round-2-closeout` (Runde-2-Closeout) |
| `origin/main` | `1b3e85af` (Merge PR #1276 „round-2-closeout") |
| Messbasis der gemeldeten Bugs | `v1.8.0-beta.20` (`0ee47d25`) |
| Neue Issues seit 2026-10-12 | **32** (#1239–#1270, #1275) |
| Davon bugfix-relevant | **24** (9 QA + 3 DEPLOY + 4 SE + 8 BluePencil-Bugs/UI) |
| Davon Feature/Roadmap (out-of-scope) | 5 BluePencil-Features (#1257, #1260, #1263, #1265, #1266) + Roadmaps |
| Residuen aus Runde 2 §9.5 | 4 (dist-Tracking, #1275, #1104-Rest, test-results-CI) |
| Offene Issues mit Label `bug` | weiterhin 0 (alle kommen ohne `bug`-Label) |

**Konsequenz:** Wie in Runde 2 speist sich die Runde aus Material, das **kein**
`bug`-Label trägt, aber verifizierte Funktionsdefekte beschreibt. Neu ist die **Breite**:
erstmals betreffen die Meldungen alle sechs Schichten (UI-Formular, Design-System,
Trace-Identität, SE-Gates, Memory/Deploy, API-Robustheit) gleichzeitig. Der Plan bündelt
sie deshalb **nicht nach Issue-Nummern, sondern nach geteilter Komponente** — genau das,
was der Auftrag „holistisch und großflächig" verlangt.

### 0.1 Verifikations-Methodik dieser Session

Fünf parallele Read-only-Analysen gegen `origin/main`:

1. **Frontend-Formular** (#1239, #1256, #1254, #1252)
2. **Frontend-Dialog/Design** (#1264, #1253, #1258, #1259)
3. **Memory/Deploy** (#1248, #1247, #1250, #1249, #1251)
4. **Import/Delete/API** (#1242, #1241, #1244, #1240, #1243)
5. **SE-Gates/Traceability** (#1267, #1268, #1269, #1270, #1262)

Ergänzend durch den Haupt-Thread geprüft: `git diff 0ee47d25..origin/main -- frontend/src`
(**leer** für `ArtifactForm/RequirementEditors/ArchitectureEditors` → beta.20-Code == main-Code
für den #1239-Pfad), `include_deleted`-Verbreitung, `SuggestionsInbox`-Renderpfad,
`origin/main`-Historie.

---

## 1. Die neue Bugflut: Inventar

| # | Sev | Track | Kurz | Cluster |
|---|---|---|---|---|
| 1239 | 🔴 CRITICAL | QA | Edit/Save im Requirement-Detail persistiert nichts | A |
| 1256 | 🟠 HIGH | BLUEPENCIL | Version/Änderungen nach Speichern nicht sichtbar | A |
| 1252 | 🟡 MED | BLUEPENCIL | /requirements: horizontale Scrollbars in der Artefaktliste | A |
| 1254 | 🟡 MED | BLUEPENCIL | /architecture: „Ableiten"-Button schlecht positioniert | A/B |
| 1255 | 🟡 MED | BLUEPENCIL | Löschen-Button: Zweck klären, gelöschte Artefakte sichtbar | A |
| 1264 | 🟠 HIGH | BLUEPENCIL | Glossar-Dialog defekt/nicht standardkonform + Baum-Standards | B |
| 1253 | 🟠 HIGH | BLUEPENCIL | Trace-Link-Dialog: Linktyp-Dropdown öffnet stumm nicht | B |
| 1258 | 🟡 MED | BLUEPENCIL | /system-settings: Buttons ohne einheitliches Format | B |
| 1259 | 🟠 HIGH | BLUEPENCIL | /settings: Attribut-Katalog nicht auffindbar/bearbeitbar | B |
| 1270 | 🟡 MED | SE | Artefakt-Identität: `id` vs. `artifact_id` inkonsistent | C |
| 1261 | 🟡 MED | BLUEPENCIL | ID-Semantik: Workspace-`uid` vs. globale UUID als Attribut | C |
| 1267 | 🟠 HIGH | SE | Kein Freigabe-Gate für Verifikation (96,5 % Dead-Ends) | D |
| 1268 | 🟠 HIGH | SE | ICDs vom Trace-Graph abgeschnitten (0 Links) | D |
| 1269 | 🟡 MED | SE | TestCases ohne Schritte, TestRuns ohne Bezug/Version | D |
| 1262 | 🟡 MED | BLUEPENCIL | SE-Auditor: Regel-ID unverständlich + fehlender Filter | D |
| 1248 | 🟠 HIGH | QA | Memory-Write-Scope ≠ Read-Scope → Inhalt unsichtbar | E |
| 1247 | 🟠 HIGH | QA | REGRESSION #1153: `memory.ask` weiter degraded (falsch geschlossen) | E |
| 1250 | 🟠 HIGH | DEPLOY | `MEMORY_BACKEND=qdrant`: Collections da, 0 Punkte (App-Seite) | E |
| 1249 | 🟠 HIGH | DEPLOY | honcho-Familie `restart_policy: no` → Daemon-Neustart killt Gedächtnis | E |
| 1251 | 🟡 MED | DEPLOY | Qdrant-Auswahl braucht Doku (ask/digest, Base-URL, Tool-Namen) | E |
| 1240 | 🟠 HIGH | QA | `suggest-architecture` intermittierend 500 (LLM-JSON) | F |
| 1241 | 🟠 HIGH | QA | `DELETE /workspaces/<id>/` 500 sobald Inhalt vorhanden | F |
| 1242 | 🟡 MED | QA | ReqIF-Reimport dupliziert Needs + Trace-Links | F |
| 1243 | 🟡 MED | QA | `requirement_bundle compressed&async` schlägt 2/2 fehl | F |
| 1244 | 🟡 MED | QA | Workspace-PATCH erzwingt kein If-Match; OpenAPI ohne 412 | F |
| 1245 | 🟡 MED | QA | Suggestion-Inbox aus menschlicher UI nicht befüllbar | F |

**Cluster-Legende:** A = Detail-Formular & Artefakt-Chrom · B = Design-System-Standards ·
C = Trace-Identität · D = SE-Gates & Auditor · E = Gedächtnis · F = API-Robustheit.

### 1.1 Residuen aus Runde 2 (§9.5) + Entscheidungen

**Alle sechs Entscheidungen am 2026-10-13 getroffen** (Details §8.1/§8.2):

| # | Punkt | Entscheidung (2026-10-13) | Owner |
|---|---|---|---|
| D1 | `frontend/dist/`-Tracking (254 Dateien, 5,9 MB) | **Untracken + gitignoren** | `git` |
| D2 | ADR-Kandidat **ii** (Workspace vs. Tenant) → #1275 | **Option B** ⚠️ *korrigiert 2026-10-14: ADR-011 (`accepted`) entscheidet bereits Option C — s. §8.1* | — |
| D3 | 2FA-Residuum (ADR-021 O5) → #1275 | **Risiko-Akzeptanz dokumentieren + Roadmap-Tracking** | `se-architect` + `requirements` |
| D4 | `+ 74 APIViews` in `.meta-config/project.yaml` (Tracker #1104) | **Zusatz entfernen; nur ViewSet-Zahl (28) führen** | `git` (Meta) |
| D5 | #1267-Gate-Statuscode | **400 `VALIDATION_ERROR`** | `developer` (W4) |
| D6 | #1255 Löschen-Semantik (§4.4) | **Hard-Delete-Button entfernen; nur „Veralten" (`deprecated`)** | `developer` (W1) |

> **Offener Restpunkt (kein D-Item):** `frontend/test-results/` braucht einen Job-scoped
> CI-Ablageort (Ansatz entschieden, noch nicht implementiert) — kleiner `devops-engineer`-Task.

---

## 2. Tiefenanalyse: Behauptung vs. Verifikation

Dies ist der **Kern** dieser Runde: die Issue-Bodies sind — wie schon in Runde 2 bei
#1135/#1136 — an mehreren Stellen **ungenau**. Wer sie als Auftrag liest, würde teils am
falschen Ende reparieren. Die folgende Tabelle hält den verifizierten Stand fest.

| # | Behauptung (laut Issue) | Verifikation (Repo) | Konsequenz für den Fix |
|---|---|---|---|
| **1239** | Save setzt **gar keinen PATCH** ab; allein `transitions/`-Refetch | **Nicht reproduzierbar.** `ArtifactForm.handleSave` (`ArtifactForm.tsx:624-691`) ruft immer `onSave` → `apiClient.patch` (7 Detail-Adapter); jeder Skip-Pfad zeigt sonst einen Fehler. Dateien **byte-identisch** zu beta.20 (`git diff` leer). | **Erst re-messen** (Playwright-Netzwerk-Trace, beide Presets). Dann fixen, was real. Unabhängig: Guard-Test „Save ⇒ PATCH". |
| **1256** | Version/Änderungen nach Save nicht sofort sichtbar | **Verifiziert.** `ArtifactInspector/VersionPanel.tsx:146-173` hat Deps `[kind, artifactId]`, **kein** `currentVersion`-Refetch; `DiffPanel` tut es (`:304-341`). Kein Versions-Header existiert. | Additiver, konkreter Bug. Fix = Refetch der Version-Liste + Serverantwort als Wahrheit. |
| **1252** | „Feste Spaltenbreiten" erzeugen Overflow | **Teilweise falsch.** Textzellen sind korrekt (`min-width:0`+Ellipsis). Overflow-Quellen sind **strukturell**: SplitView-Left-Panel `overflow:auto` + 260px-Floor (`SplitView.tsx:146-150,580-588`), unbounded `16px/Level`-Tree-Indent (`workspace-tree.module.css:44`), 22px-Löschbutton. | Containment, nicht Spaltenbreiten. |
| **1253** | Linktyp-Dropdown öffnet stumm; **Hint ist englisch** | **Stumm-Öffnen verifiziert** (`link-type-listbox.tsx:223-226`; Click-Return `:414`). **i18n-Behauptung falsch** (Key in `de.json:433` **und** `en.json:433`). **Echt**: Hint nicht handlungsleitend + Linktyp-Katalog-Routen ohne UI-Einstieg. | Handlungsleitend machen + Katalog erreichbar; i18n nicht anfassen. |
| **1254** | „Ableiten"-Button schlecht positioniert | **Verifiziert.** `.deriveSlot` (`ArchitectureEditors.module.css:127-129`) hat **nur** `margin-top`; Arch ist die einzige Route, auf der der Derive-Trigger außerhalb eines Panels steht (Req/Needs in `.deriveHost`). | Gemeinsame Aktionszone (Detail-Standard). |
| **1255** | Löschen-Button unerwartet; gelöschte nicht sichtbar | **Teilweise verifiziert.** `include_deleted` existiert **nur** für Requirements (`RequirementEditors.tsx:82,591-596`); `handleDelete` ist in `ArtifactForm` zentral. Alle Typen haben `deprecated` + Transition (`definition_store.py:129 ff.`). | **Entschieden (D6):** Button entfernen, „Veralten"-Transition + `include_deleted` systemweit. |
| **1264** | Glossar-Dialog defekt; ebenso Navigationsbaum | **Fokus-Kampf im Glossar nicht reproduzierbar** (nur `initialFocusRef`, kein `autoFocus`). Kampf **existiert woanders**: `ArchitectureEditors.tsx:528+550` (`autoFocus` **und** `initialFocusRef`), `ArtifactForm.tsx:420-431` (Mount-Fokus). Kein Navigationsbaum in Dialogen. **Echt**: Glossar-Buttons klassenlos (10/11; eigenes `.btn`-Set `GlossaryView.module.css:30-60`). | Standard „**ein** Fokus-Owner" systemweit + Glossar auf Tokens. |
| **1258** | 54 Buttons / 9 Höhen / 5 Radien | **Zahlen nicht reproduzierbar**; **Struktur bestätigt**: `.btn-*` + 6 ad-hoc Klassen (`--radius-md`) + 4 klassenlose Buttons (`MemorySystemSettingsSection.tsx:319,327,354,357`). Statisch: 3 Radien / 5 Höhen-Geometrien. Präzedenz #986: 6 Höhen/3 Radien auf `/settings`. | Button-Token-Migration + Ratchet senken. |
| **1259** | Katalog in `/settings` nicht auffindbar | **Premise teilweise falsch**: `attributes`-Tab existiert (`WorkspaceSettings.tsx:261,635`), `/attributes`-Route existiert. **Echt**: kein Nav-/In-App-Einstieg zu `/attributes` und beiden Linktyp-Katalogen; `?tab=` wird nur initial gelesen. | Einstiege schaffen, Labels schärfen. |
| **1270** | `id` vs. `artifact_id` verursacht falsche Coverage | **Verifiziert.** Reads liefern beide (`serializers.py:1018/1028`, `:1303/1310`); Links speichern **Artifact**-IDs (`views.py:5367-5368`). **Interne** Consumer mappen korrekt (`coverage_calculator.py:162-192`). Risiko = **externe** Consumer. | Doku/OpenAPI + additiver Alias + CI-Konsistenztest. **Kein** Breaking-Rename. |
| **1261** | Workspace-`uid` vs. globale UUID verwechselt | **Verifiziert.** `uid` lokal/monoton; `id` global; Client-`uid` wird 400 abgewiesen. UUID als Attribut fehlt. | System-Attribut `global_uuid` + Labels. Querbezug #1094. |
| **1267** | „Kein Verifikations-Gate"; Issue verlangt 409 | **Teilweise unzutreffend.** `verification_method` ist im `extended`-Gate **bereits** Pflicht (Rule 5, `precondition_rules.py:240-362`; `mandatory_fields.py:113-117`). **Echte Lücke**: Verifikations-**Link** vor `approved` (Rule 7 ist TestCase-only, `:501-622`; Test `test_se_conformance_gates.py:1032-1056` pinnt genau das). Alle Gates antworten heute **400** `VALIDATION_ERROR`, nicht 409. | Gate auf Requirements erweitern (extended), 400 (Hausstil) documentiert; Metric neu. |
| **1268** | ICD-Linktypen fehlen im Regelwerk | **Config bereits vorhanden**: `("*","Icd")` (`builtin.py:361`), `Icd` auflösbar (`artifact_backing.py:46`, `trace_link_service.py:282-301`; Test #1075). **Echte Lücke**: `icd/traceability_connector.py:82-87` verlinkt nur Arch→Arch, **nie** Icd↔Arch. `backend/semantic/` existiert nicht. | Connector erzeugen Icd-Links + Audit-Regel + Metric + UI. |
| **1269** | `result`-Feld als Freitext; `test_case_ids` fehlt | **Teilweise falsch.** `result` existiert **nicht**; `status` ist enum (`models.py:2320-2329`, `serializers.py:2142-2145`). `test_case_ids` **existiert bereits** (`:2112-2118`). `steps` ist optional (`:1317-1319`). | `steps`-Pflicht (Approval) + `tested_artifact_version` neu. |
| **1262** | Regel-ID ohne Legende, kein Filter | **Verifiziert.** Finding trägt nur `rule_id` (`audit/types.py:39-72`); kein Katalog-Endpoint; Filter nur `scope/limit/offset` (`audit_views.py:124-181`). | Katalog-Endpoint + Server-Filter + UI. |
| **1248** | Einträge werden auf **Tenant**-Ebene geschrieben | **Nicht bestätigt.** Alle Writes sind scope-suffig (Peers `honcho_backend.py:592-639`; `tasks.py:248-253`). **Echt**: Write-Scope kommt vom LLM-Extraktor (`prompts.py:43-47`), Read-Scope vom Aufrufer; Default ohne `workspace_id` = `user` (`memory_entry_service.py:566-575`). | Scope-Vertrag vereinheitlichen + Doku. QA-Felder (`observer=tenant`) haben keinen In-Repo-Produzenten. |
| **1247** | Header erreicht `complete()` nicht | **Teilweise.** Shim existiert (`docker-compose.yml:1320-1361,1429-1467`); Vendor-Pfad **außerhalb** des Repos (Grenze dokumentiert: `test_opencode_session_check_1050.py:307-311`); Live-Spike **skip** (`test_honcho_deploy_contract.py:223-252`); Runbook-Gate prüft **nur das Log** (`DEPLOY_RUNBOOK.md:149-154`). | #1153 wieder öffnen; Smoke auf echten `complete()`-Call; Image-Pin prüfen. |
| **1250** | Punkte kommen nicht an | **Verifiziert, Ursache präzisiert:** zwei **fail-open**-Abzweige — (1) `embedding is None` → kein Write, kein Fehler (`qdrant_backend.py:406-408` ← `embedding_service.py:345-354`); (2) `upsert`-Exception → `warning` + `False`, `backend_ref` NULL (`:435-443`). `health()` prüft keine Punktzahl (`:537-558`). | Fail-loud + Health + Reconcile als Guard. |
| **1249** | honcho-Familie überlebt Daemon-Neustart nicht | **Verifiziert.** `honcho`, `honcho-postgres`, `honcho-redis` ohne Policy (`docker-compose.yml:1190,1205,1283`); nur `honcho-deriver` `unless-stopped` (`:1408`). Kein Compose-Contract-Test für Policies. | `restart: unless-stopped` + Contract-Test. |
| **1251** | Alte MCP-Tool-Namen; Qdrant-Degradation undokumentiert | **Teils.** Qdrant-Degradation **undokumentiert** (0 Treffer in `MCP-SURFACE.md`/`REQUIREMENTS.md`; `qdrant_backend.py:228-233,610-626`). `QDRANT_BASE_URL` leer ist **intentional** (`.env.example:469-491`). Tool-Namen **aktuell** (`tool-manifest.json:4970,5300`); alte Namen sind **LLM-Capability-IDs** (`.env.example:157-160`). | Capability-Matrix + Capability-vs-MCP-Tabelle. |
| **1242** | Externe Identität von Needs/Relations nicht geprüft | **Verifiziert (Root-Cause).** `foreign_identifier` wird bei `:1245` **vor** dem Reset `:1258` fixiert; bei Cross-Workspace-`_<uuid>` + leerem ATTR-UID geht die Identität **verloren** → Reimport dupliziert Needs; Relations folgen (Endpunkt-Duplikate). | Identität **immer** persistieren + Regressionstest. |
| **1241** | Workspace-Delete mit Inhalt 500 | **Verifiziert (Root-Cause).** `we_engine_definition.self`-`PROTECT` (`workflow/models.py:236`) + Workspace-Cascade → `ProtectedError` → unmapped → 500 (`workspace_service.py:789`; `views.py:203-246,301-302`). Leerer WS: keine `we_item_state` → 204. | Explizite Löschreihenfolge + `ProtectedError`→409/400. |
| **1244** | Workspace-PATCH ohne If-Match; OpenAPI ohne 412 | **Verifiziert.** Workspace-ViewSet nutzt kein `ETagMixin` (`views.py:5765-5778,5874-5953`); Serializer ohne `expected_version`; OpenAPI live gemessen: **0/338** Pfade mit 412. | `ETagMixin` anwenden + `expected_version` + 412-Deklaration. |
| **1240** | `_parse_json_list` wirft JSONDecodeError → 500 | **Mechanismus anders.** `_parse_json_list` **fängt** JSONDecodeError → `LlmResponseError` (`ai_derivation_service.py:2844-2847`). Der 500 entsteht im **View-Mapping** (`views.py:1586-1592`: nur ValidationError/NotFoundError). `is_mock_fallback` geht bei Parse-Fehler verloren (`:2665-2675`). | `LlmResponseError`→502 + robuste Extraktion + einheitliche Fence-Behandlung (5 Stellen). |
| **1243** | `choices[0]` ungeschützt; Async-Timeout zu kurz | **Verifiziert.** `providers.py:2137` (auch `:1581,1943`) unguarded; Async-Dispatch **ohne** Timeout (`bundle_compression_service.py:408-411`) → 30 s vs. Sync 180 s (`timeouts.py:46-54`). | Guard + Async nutzt Long-Running-Timeout. |
| **1245** | Inbox aus UI nicht befüllbar | **Teilweise falsch.** `SuggestionsInbox` **existiert** (`ReviewsView.tsx:1045-1048`), hinter Mode-Toggle (`:744-754`). 409 ist **by design** fail-closed. **Echt**: Auffindbarkeit/Doku. | Sichtbarkeit + Doku; **kein** Verhaltenswechsel. |

**Zusammenfassung:** 11 der 24 Issues bestätigen sich im Code **wie gemeldet**
(1256, 1252-strukturell, 1254, 1255, 1258, 1259, 1261, 1262, 1249, 1244).
**7 Issues haben ungenaue bis falsche Ursachen** (1239, 1253, 1264, 1267, 1268, 1269,
1251) und müssen am **verifizierten** Befund gefixt werden, nicht am Issue-Wortlaut.
**6 Issues** sind Root-Cause-verifiziert, aber mit präzisierter Mechanik
(1240, 1241, 1242, 1243, 1250, 1248).

---

## 3. Wellen

Grundsatz wie in Runde 2: jede Welle ist **unabhängig shippbar**, eigener
`fix/*`-Branch off `origin/main @ 1b3e85af`, kein Commit auf `main` (Branch-Guard).
Die Bündelung folgt der **geteilten Komponente** (holistisch), nicht dem Issue-Track.

| Welle | Thema | Issues | Sev | Aufwand |
|---|---|---|---|---|
| **W1** | Detail-Formular & Artefakt-Chrom | 1239, 1256, 1252, 1255 | 🔴🟠🟡 | L |
| **W2** | Design-System-Standards | 1264, 1253, 1258, 1259, 1254 | 🟠🟡 | M |
| **W3** | Trace-Identität | 1270, 1261 | 🟡 | M |
| **W4** | SE-Gates & Auditor | 1267, 1268, 1269, 1262 | 🟠🟡 | L |
| **W5** | Gedächtnis-Zuverlässigkeit | 1249, 1250, 1248, 1247, 1251 | 🟠🟡 | M |
| **W6** | API-Robustheit & Lebenszyklus | 1240, 1241, 1242, 1243, 1244, 1245 | 🟠🟡 | L |

### Welle 1 — Detail-Formular & Artefakt-Chrom

| Aspekt | Inhalt |
|---|---|
| **Ziel** | Zuerst die potenziellen **Datenverluste** und die geteilte Detail-Komponente stabilisieren. Ein Fix in `ArtifactForm`/`ArtifactInspector` wirkt **auf alle 7 Detailtypen** (Requirement, Architecture, Adr, Risk, Issue, TestCase, Need). |
| **Enthalten** | **1239** (Re-Messung + Fix), **1256** (Version-Panel-Refetch), **1252** (Overflow-Containment), **1255** (D6: Delete-Button → „Veralten" + `include_deleted` systemweit) |
| **Risiko** | Hoch für 1239 (unbekannte Ursache, ggf. nur in deploytem Build reproduzierbar). Mittel für 1252/1255 (geteilte CSS/Listen-Komponenten). |
| **Rollback** | Pro Fix eigener Commit, einzeln revertierbar. |
| **Begründung Vorrang** | 1239 ist CRITICAL (stiller Datenverlust). 1256 ist **verifiziert** und teilt denselben Refresh-Pfad — im selben Branch gelöst, sonst zementiert man zwei Wahrheiten. |

### Welle 2 — Design-System-Standards

| Aspekt | Inhalt |
|---|---|
| **Ziel** | Die **geteilten** UI-Primitive (Dialog-Fokus, Button-Tokens, Linktyp-Katalog-Erreichbarkeit) systemweit auf **einen** Standard heben — statt einzelne Sichten zu flicken. |
| **Enthalten** | **1264** (Fokus-Owner-Standard + Glossar-Tokens), **1253** (Dropdown + Katalog-Einstieg), **1258** (Button-Token-Migration + Ratchet), **1259** (Katalog-Auffindbarkeit), **1254** (Aktionszone, zieht den Button-Standard) |
| **Risiko** | Mittel. Fokus-Standard berührt **31 Dialog-Consumer**; Button-Migration berührt Settings/System-Settings/Glossar/Workflows. Ratchet darf **nicht** verwässert werden. |
| **Rollback** | Branch verwerfen; Tokens sind additiv, Geometrien über `--btn-h-*`/`--radius-*` reversibel. |
| **Begründung** | Der Befund ist **ein** Fokus-Mechanismus- und **ein** Button-Wildwuchs-Problem. Einzel-Fixes würden drei bis vier inkonsistente Standards erzeugen. |

### Welle 3 — Trace-Identität

| Aspekt | Inhalt |
|---|---|
| **Ziel** | Die Zweideutigkeit `id` vs. `artifact_id` und `uid` vs. UUID **dokumentiert und testbar** schließen, ohne den API-Contract zu brechen. |
| **Enthalten** | **1270** (OpenAPI-Semantik + additiver Alias + CI-Konsistenztest), **1261** (`global_uuid`-System-Attribut + Labels) |
| **Risiko** | Niedrig. Rein additive Felder + Doku; interne Consumer mappen bereits korrekt. |
| **Rollback** | Additive Felder entfernen; Doku revertieren. |
| **Querbezug** | #1094 (Workspace-ID) bündeln oder wechselseitig verlinken. |

### Welle 4 — SE-Gates & Auditor

| Aspekt | Inhalt |
|---|---|
| **Ziel** | Die **rechte V-Seite** durchsetzbar machen (Gate statt nur Report) und die Auditor-Ausgabe handlungsfähig machen. |
| **Enthalten** | **1267** (Verifikations-Link-Gate, extended), **1268** (ICD-Connector + Audit-Regel + Metric), **1269** (TestCase-Steps + TestRun-Version), **1262** (Regel-Katalog + Filter) |
| **Risiko** | Hoch für 1267: ein Freigabe-Gate ändert das **Freigabe-Verhalten**; muss auf `extended` beschränkt und feature-geflaggt sein. Mittel für 1268/1269 (Connector/Datenmodell). |
| **Rollback** | Gate Rule hinter Feature-Flag → abschaltbar; Connector-additiv. |
| **Entscheidung** | Policy für 1267 (Gate-Semantik + Statuscode) ist **decision-pending** (§8). |

### Welle 5 — Gedächtnis-Zuverlässigkeit

| Aspekt | Inhalt |
|---|---|
| **Ziel** | Das Kernfeature „das System erinnert sich" wieder **lesbar** und **überlebensfähig** machen; stilles Versagen durch lautes ersetzen. |
| **Enthalten** | **1249** (Compose-Restart + Contract-Test), **1250** (Qdrant fail-loud + Health + Reconcile), **1248** (Scope-Vertrag), **1247** (#1153 wieder öffnen + echter Smoke; Vendor-Grenze dokumentieren), **1251** (Capability-Matrix) |
| **Risiko** | Mittel. 1248 ändert Lese-/Schreib-Defaults (Verhaltensänderung); 1247 ist teilweise **vendor-extern** (nicht voll in-repo lösbar). |
| **Rollback** | Compose-Änderung trivial; Scope-Änderung braucht Testabdeckung vor Merge. |
| **Reihenfolge** | 1249 (Deploy, unabhängig) → 1250 (Backend) → 1248 → 1247/1251 (Doku/Boundary). |

### Welle 6 — API-Robustheit & Lebenszyklus

| Aspekt | Inhalt |
|---|---|
| **Ziel** | 500er auf **erwartbare** Fehler und saubere Lebenszyklus-Semantik zurückführen; Import/Export idempotent machen. |
| **Enthalten** | **1240** (LLM-JSON-Robustheit vereinheitlicht), **1241** (Workspace-Delete-Kaskade), **1242** (ReqIF-Identität), **1243** (Provider-Guard + Async-Timeout), **1244** (Workspace-ETag + 412), **1245** (Inbox-Auffindbarkeit/Doku) |
| **Risiko** | Mittel. 1242 ändert Import-Verhalten (Idempotenz); 1241 berührt Kaskaden; 1244 berührt OpenAPI-Contract. |
| **Rollback** | Pro Fix eigener Commit; ETag nur bei vorhandenem `If-Match` scharf (siehe §4.24). |

---

## 4. Fix-Spezifikation

### 4.1 #1239 — Save persistiert nichts (CRITICAL)

**Befund (verifiziert):** Die gesamte Kette ist vorhanden und sendet PATCH:
`ArtifactForm.tsx:624-691` (`handleSave`) → `onSave` je Adapter (z. B.
`RequirementArtifactForm.tsx:160-174` → `requirementsApi.update` → `apiClient.patch`,
`api/requirements.ts:274-287`). Skip-Pfade sind **alle** sichtbar: `savingRef` (Doppelklick),
`missingCreateValue` (nur Create), `changeReasonMissing` (extended, setzt `role="alert"` +
Fokus). `handleSave` fängt Fehler und rendert sie (`:662-678`). Die gemeldeten Dateien sind
**byte-identisch** zu beta.20.

**Damit ist der gemeldete Verlauf („kein PATCH, keine Fehlermeldung") in diesem Stand
nicht reproduzierbar.** Task 1 ist daher die Re-Messung, nicht der Fix.

**Lösungsansatz (drei Schritte):**
1. **Re-Messung** auf `main @ 1b3e85af`: Playwright-Netzwerk-Trace für Save auf
   `/requirements/<id>` in `standard` **und** `extended`, Felder Titel + Beschreibung.
   Reproduktion → Ursache eingrenzen; **keine** Reproduktion → Falsifikations-Kommentar am
   Issue + Guard-Test (unten).
2. **Verteidigende Härtung** unabhängig vom Ausgang: nach `await onSave(payload)` die
   **Serverantwort** als Wahrheit setzen (nicht den lokalen `values`-Snapshot), damit die
   Sichtbarkeit nicht an einem Dirty-State hängt; den `transitions/`-Refetch aus dem
   Save-Pfad entkoppeln (Ursache des irreführenden GET).
3. **Regressionstest** (der eigentliche Wert): „Save auf Detailseite ⇒ genau ein PATCH +
   Versions-Bump (+ `change_reason` im extended)". Damit kann der Defekt nicht unbemerkt
   zurückkehren.

**Betroffene Dateien (holistisch):** `shared/ArtifactForm/ArtifactForm.tsx`,
7 Detail-Adapter (`RequirementEditors/RequirementArtifactForm.tsx`,
`ArchitectureEditors/ArchitectureArtifactForm.tsx`, `AdrEditors`, `RiskEditors`,
`IssueEditors`, `TestCaseEditors`, `NeedsEditors`), `api/requirements.ts` u. a.,
`RequirementEditors/useRequirementData.ts`, `ArchitectureEditors/useArchitectureData.ts`.

**Teststrategie:** neuer Vitest-Fall „Save calls the update API once" je Detailtyp (Muster:
bestehende Editor-Tests); E2E-Fall mit Netzwerk-Assertion.

**Akzeptanzkriterium:**
- [ ] Re-Messung auf `main` durchgeführt und dokumentiert (reproduziert **oder** falsifiziert).
- [ ] Bei Reproduktion: Ursache benannt, Fix, Test rot-vor/grün-nach.
- [ ] Bei Falsifikation: Issue-Kommentar mit Trace + Guard-Test bleibt.
- [ ] Save auf `/requirements` und `/architecture` setzt sichtbar einen PATCH ab (Hook-Test).

### 4.2 #1256 — Version/Änderungen nach Save nicht sichtbar (HIGH)

**Befund (verifiziert):** `ArtifactInspector/VersionPanel.tsx:146-173` lädt Versionen mit
Deps `[kind, artifactId]`; `currentVersion` ist **nicht** in den Deps und wird nach einem
Save nicht invalidiert → Markierung „aktuell" und Liste bleiben stale. `DiffPanel` reagiert
korrekt (`:304-341`). Ein Versions-Header-Widget existiert auf den Detailseiten nicht.

**Lösungsansatz (holistisch, ein Ort):**
1. `VersionPanel` auf `currentVersion` (bzw. einen `refreshKey`) reagieren lassen.
2. Nach erfolgreichem Save die Version-Query invalidieren — zentral in den
   `use*Data`-Hooks (`useRequirementData.ts:55-66`, `useArchitectureData.ts:67-78`), damit
   **alle 7 Detailtypen** denselben Pfad nutzen.
3. Serverantwort führt: `version`/`updated_at` aus der Refetch-Antwort lesen.

**Betroffene Dateien:** `shared/ArtifactInspector/VersionPanel.tsx`,
`shared/ArtifactInspector/DiffPanel.tsx` (nur Absicherung), `Frontend data-hooks`.

**Teststrategie:** Vitest — Save mocken, Version-Liste-Refetch asserten; Regressionsfall
„Version inkrementiert ohne manuellen Reload" auf `/requirements` **und** `/architecture`.

**Akzeptanzkriterium:**
- [ ] Nach Save zeigt `VersionPanel` die neue Version ohne Reload (req + arch).
- [ ] Kein Verhaltenswechsel im `DiffPanel`.

### 4.3 #1252 — Horizontale Scrollbars in der Artefaktliste (MED)

**Befund (verifiziert):** Textzellen sind korrekt begrenzt. Overflow entsteht strukturell:
`SplitView`-Left-Panel ist `overflow:auto` (beide Achsen) mit 260px-Floor
(`SplitView.tsx:146-150,580-588`), Tree-Indent wächst unbounded (`workspace-tree.module.css:44`),
fixer 22px-Löschbutton.

**Lösungsansatz (holistisch — `SplitView` + `WorkspaceTree` tragen **alle** Listenrouten):**
1. `SplitView`-Scrollfläche: `overflow-x: hidden` (bzw. `overflow: auto` nur Y), `min-width: 0`
   auf Flex-Kindern.
2. Tree: Indent ab Tiefe N kappen oder Titel ellipsieren (`title`-Attribut für Volltext).
3. Gegenprobe 1280/1024/768: keine horizontale Scrollbar auf `body`.

**Betroffene Dateien:** `SplitView/SplitView.tsx` (+ CSS), `shared/WorkspaceTree/workspace-tree.module.css`,
`RequirementList.module.css`.

**Teststrategie:** UI-Ratchet-/Computed-Style-Test; visuelle Gegenprobe in E2E (3 Breiten).

**Akzeptanzkriterium:**
- [ ] Keine horizontale Scrollbar in der Artefaktliste bei 1280/1024/768 px.
- [ ] Andere `SplitView`-Routen (Architecture, Adr, Risk …) unverändert nutzbar.

### 4.4 #1255 — Löschen-Button-Semantik (MED) — **entschieden: nur „Veralten"**

**Befund (verifiziert):** `handleDelete` ist zentral in `ArtifactForm` (`:693+`); das
Detail-Panel rendert `artifact-form-delete`. `include_deleted` existiert **nur** für
Requirements (`RequirementEditors.tsx:82,591-596`). **Alle** Artefakttypen besitzen einen
`deprecated`-Zustand mit `approved → deprecated`/`draft → deprecated`-Transition und
`state_meta: {deprecated: {is_outdated_equivalent: true}}`
(`workflow/definition_store.py:129,136,162,202,253,294,334,589,720,730,800,887,894 …`) —
der Wechsel ist also **überall** schon modelliert.

**Entscheidung (User, 2026-10-13):** Kein Hard-Delete an Artefakten — der Button wird
**entfernt**; angeboten wird „**Veralten**" (= Transition nach `deprecated`).

**Lösungsansatz (holistisch, ein Mechanismus für alle 7 Detailtypen):**
1. `artifact-form-delete` aus `ArtifactForm` entfernen; stattdessen eine Aktion
   `artifact-form-deprecate` rendern, die die Workflow-Transition nach `deprecated` auslöst
   (im `extended`-Preset über die bestehende `change_reason`-Pflicht, Rollen-Gate greift).
2. Aktion nur zeigen, wenn ein `→ deprecated`-Übergang laut Transitions-API erlaubt ist
   (kein toter Button; konsistent mit `WorkflowStatusEditor`).
3. Die bestehende Soft-Delete-/`outdated`-Sichtbarkeit systemweit exponieren:
   `include_deleted`-Filter (+ Badge „veraltet") auf **allen** Artefaktlisten, nicht nur
   Requirements.
4. REST/MCP-`DELETE` **bleibt** erhalten (Admin-/Datenhygiene-Pfad), wird aber **nicht**
   mehr aus der Artefakt-Detail-UI angeboten; im `docs/api/` dokumentiert.
5. Reaktivierung (`deprecated →` zurück) als Folge-Issue notieren, falls nicht im Scope.

**Betroffene Dateien:** `shared/ArtifactForm/ArtifactForm.tsx` (Button → Deprecate),
7 Detail-Adapter (onDelete → onDeprecate), die Listen-/Editor-Komponenten
(`RequirementEditors`, `ArchitectureEditors`, `AdrEditors`, `RiskEditors`, `IssueEditors`,
`TestCaseEditors`, `NeedsEditors`) + jeweilige API-Wrapper.

**Teststrategie:** je Detailtyp „Deprecate-Aktion setzt `deprecated`"-Test (Transitions-Mock);
je Liste „include_deleted schaltet veraltete Einträge sichtbar"; Negativtest „kein
`artifact-form-delete` mehr".

**Akzeptanzkriterium:**
- [ ] Kein `artifact-form-delete` mehr in der Artefakt-Detail-UI.
- [ ] „Veralten" setzt über die Transition `deprecated` (extended: mit Begründung).
- [ ] `include_deleted`/Badge auf allen Artefaktlisten wirksam.
- [ ] REST/MCP-`DELETE` unverändert und dokumentiert.

### 4.5 #1264 — Dialog-/Baum-Standards & Glossar (HIGH)

**Befund (verifiziert):** Der shared `Dialog` setzt Initialfokus selbst
(`Dialog.tsx:103-107`, `use-focus-trap.ts:129-139`). Im Glossar **kein** Kampf (nur
`initialFocusRef`, `GlossaryView.tsx:364-382`). Konkurrierende Fokus-Mechanismen existieren
in `ArchitectureEditors.tsx:528+550` (`autoFocus` **und** `initialFocusRef`) und
`ArtifactForm.tsx:420-431` (Mount-Fokus). Glossar nutzt ein eigenes Button-Set und 10/11
klassenlose Buttons (`GlossaryView.module.css:30-60`). Einen Navigationsbaum **im Dialog**
gibt es nicht — der Seitenbaum ist `WorkspaceTree` (`role="tree"`).

**Lösungsansatz (systemweit):**
1. **Ein Fokus-Owner:** nur `Dialog` setzt den Initialfokus. Entfernen von `autoFocus` in
   `ArchitectureEditors.tsx:550`; Mount-Autofokus in `ArtifactForm.tsx:420-431` dialog-aware
   machen (im Dialog nicht selbst fokussieren). Test: genau **eine** Fokusbewegung pro Öffnen.
2. **Glossar** auf `.btn-*`-Tokens migrieren; klassenlose Buttons ausstatten.
3. **Baum-Standards:** `aria-current`, Tastaturnavigation, aktiver Zustand im `WorkspaceTree`
   prüfen und in den Design-System-Ratchet aufnehmen.

**Betroffene Dateien:** `shared/Dialog/*`, `shared/CreateTraceLinkDialog/*`,
`ArchitectureEditors/ArchitectureEditors.tsx`, `shared/ArtifactForm/ArtifactForm.tsx`,
`GlossaryView/*`, `shared/WorkspaceTree/*`.

**Teststrategie:** Dialog-Fokus-Owner-Test; Glossar-Button-Konformität; Baum-a11y-Test.

**Akzeptanzkriterium:**
- [ ] Genau eine Initialfokus-Bewegung pro Dialog-Öffnen (arch + glossary).
- [ ] Kein `autoFocus` mehr in dialog-gerenderten Formularen.
- [ ] Glossar-Buttons nutzen Design-Tokens.

### 4.6 #1253 — Linktyp-Dropdown öffnet stumm (HIGH)

**Befund (verifiziert):** `link-type-listbox.tsx:223-226` blockiert das Öffnen bei
`optionCount === 0` (`:414`), gepinnt durch Test `create-trace-link-dialog.test.tsx:1028-1047`.
Hint existiert (i18n in DE+EN vorhanden) — aber text-only (`create-trace-link-dialog.module.css:57-61`),
ohne Aktion. Linktyp-Katalog-Routen existieren (`NavigationShell.tsx:169,171`), haben aber
**keinen** UI-Einstieg.

**Lösungsansatz (holistisch für alle 6 Aufruf-Routen):**
1. Bei `optionCount === 0` die Liste **öffnen** und Erklärung anzeigen, statt stumm zu bleiben
   (Test anpassen — er pinnt heute das Gegenteil).
2. Hint **handlungsleitend**: welche Zielartefakte sind für die Quelle erlaubt
   (Daten über `isAllowedPair`), plus Deep-Link zum Linktyp-Katalog.
3. **Einstiege** für `/settings/link-types` und `/system-settings/link-types` in der Navigation.

**Betroffene Dateien:** `shared/CreateTraceLinkDialog/link-type-listbox.tsx`,
`create-trace-link-dialog.tsx`, `context/LinkTypeContext.tsx`,
`NavigationShell/NavigationShell.tsx`, i18n (DE/EN).

**Teststrategie:** bestehenden Test invertieren; Hint-Aktion + Katalog-Link; Navigationstest.

**Akzeptanzkriterium:**
- [ ] Bei 0 Optionen öffnet die Liste mit Erklärung + erlaubten Zieltypen.
- [ ] Der Katalog ist aus dem Hint und der Navigation erreichbar.

### 4.7 #1258 — Button-Standard (MED)

**Befund (verifiziert):** Statisch 3 Radien / 5 Höhen-Geometrien auf `/system-settings`;
4 klassenlose Buttons (`MemorySystemSettingsSection.tsx:319,327,354,357`); 6 ad-hoc Klassen
(`--radius-md`). Repo-weit 424 Buttons, 48,8 % klassenlos. Präzedenz #986 (6 Höhen/3 Radien).

**Lösungsansatz:** Button-Token-Migration (`btn-primary/secondary/ghost`,
`--btn-h-sm/md/lg`, `--radius-btn`) für Settings/System-Settings/Glossar/Workflows;
`STYLE_BRACE_BASELINE` / Design-Ratchet **senken**; neuer Ratchet „distinct button
geometries per Route ≤ 2".

**Betroffene Dateien:** `styles/global.css`, `styles/tokens.css`, die betroffenen
`*.module.css`, `frontend/src/test/ui-ratchet.test.ts`, `design-system-ratchet.*`.

**Akzeptanzkriterium:**
- [ ] `/settings` und `/system-settings`: ≤ 2 Radien, ≤ 3 Höhen, 0 klassenlose Buttons.
- [ ] Ratchet mit **gesenktem** Baseline grün.

### 4.8 #1259 — Attribut-Katalog-Auffindbarkeit (HIGH)

**Befund (verifiziert):** `attributes`-Tab existiert (`WorkspaceSettings.tsx:261,635`);
`/attributes`-Route existiert (`NavigationShell.tsx:207-210`). **Echt**: kein Nav-/In-App-Einstieg
zu `/attributes` und beiden Linktyp-Katalogen; Tab-Label „Attributes" mehrdeutig.

**Lösungsansatz:** klare Navigationseinträge/Deep-Links (mit #1253 WP3 gemeinsam),
Label schärfen („Attribut-Katalog"), Leerzustand mit Import-Aktion, Doku der Deep-Links.

**Betroffene Dateien:** `NavigationShell/*`, `Settings/WorkspaceSettings.tsx`,
`AttributeEditor/*`, i18n.

**Akzeptanzkriterium:**
- [ ] Aus der UI heraus ist der Attribut-Katalog in ≤ 1 Klick erreichbar.
- [ ] Deep-Link (`/settings?tab=attributes`) dokumentiert.

### 4.9 #1254 — Aktionszone „Ableiten" (MED)

**Befund (verifiziert):** `.deriveSlot` hat nur `margin-top`; Arch ist die einzige Route, auf
der der Derive-Trigger außerhalb eines Panels steht.

**Lösungsansatz:** eine **Aktionszonen-Regel** für Detailseiten (Footer/Header-Zone mit
`border-top`, Abstand ≥ 16 px), Derive-Trigger dort einordnen — konsistent für Requirements,
Architecture, Needs. Zieht den Button-Standard aus W2.

**Akzeptanzkriterium:**
- [ ] Derive-Trigger sitzt auf allen Detailrouten in der Standard-Aktionszone.
- [ ] Ratchet-Gegenprobe grün.

### 4.10 #1270 — `id` vs. `artifact_id` (MED)

**Befund (verifiziert):** Reads liefern beide; Links speichern Artifact-IDs; interne Consumer
mappen korrekt; Risiko ist extern.

**Lösungsansatz (nicht-brechend):**
1. OpenAPI-/Serializer-Hilfetexte: `id` = Entity-PK für API-Pfade, `artifact_id` = kanonische
   ID für Trace-Links.
2. **Additiver** Alias in der Trace-Link-Read (`source_artifact_id`/`target_artifact_id`)
   neben dem bestehenden `source_id`/`target_id` — kein Rename.
3. CI-Konsistenztest: Artifact-Read ↔ Trace-Link joinen über die kanonische ID.
4. Doku `docs/api/REST-CONVENTIONS.md`.

**Betroffene Dateien:** `serializers.py:1018/1028,1303/1310,1444-1446`,
`views.py:5349-5397`, `icd_views.py:349-403`, `docs/api/*`.

**Akzeptanzkriterium:**
- [ ] OpenAPI erklärt beide IDs; Alias additiv vorhanden.
- [ ] CI-Test grün; **keine** bestehende Response bricht.

### 4.11 #1261 — `global_uuid`-Attribut (MED)

**Lösungsansatz:** read-only System-Attribut `global_uuid` im Katalog; UI-Labels
„ID (Workspace)" / „UUID (global)"; Doku Export/Import-Mapping; #1094 verlinken/bündeln.

**Betroffene Dateien:** `attribute_definitions/*`, Serializer/UI-Reads, `docs/*`.

**Akzeptanzkriterium:**
- [ ] `global_uuid` als Attribut sichtbar (Anzeige-Konfiguration).
- [ ] Kein Setzen möglich (read-only).

### 4.12 #1267 — Verifikations-Gate (HIGH)

**Befund (verifiziert):** `verification_method` ist im `extended`-Approval **bereits** Pflicht
(Rule 5). Lücke: Requirement-seitiges `verifies`-Link (Rule 7 TestCase-only; Kontrolltest
`test_se_conformance_gates.py:1032-1056` pinnt, dass ein Requirement **ohne** Link gültig ist).

**Lösungsansatz:**
1. Rule 7 auf **Requirements** erweitern, wenn `traceability_target` gesetzt ist
   (nur `extended`, per Feature-Flag `require_verification_on_approval` — neu, Default ON in
   `extended`). `verification_method ∈ {Test}` verlangt ein `verifies`-Link; `inspection`/
   `analysis`/`demonstration` bleiben zulässig (dokumentiert).
2. Verstoß mit Begründung zurückgeben. **Entschieden (User, 2026-10-13): 400**
   `VALIDATION_ERROR` — konsistent mit allen anderen Workflow-Gates (nicht 409 wie im Issue
   gewünscht; die Begründung bleibt im Body).
3. Metric `verification_coverage` in `/metrics/` exposen (existiert nicht).

**Betroffene Dateien:** `workflow/precondition_rules.py`, `presets/registry.py` (Feature-Key),
`se_metrics/*`, `traceability/audit/*` (Report bleibt Report).

**Akzeptanzkriterium:**
- [ ] Requirement ohne `verifies`-Link kann im `extended` nicht auf `approved` (außer
      Methode inspection/analysis/demonstration).
- [ ] Flag aus ⇒ altes Verhalten.
- [ ] `verification_coverage` in `/metrics/`.

### 4.13 #1268 — ICD-Anbindung (HIGH)

**Befund (verifiziert):** Pair-Config vorhanden; Lücke ist der Connector
(`icd/traceability_connector.py:82-87` verlinkt nur Arch→Arch).

**Lösungsansatz:**
1. Connector erzeugt zusätzlich `references`-Links `Icd ↔ ArchitectureElement` (ids).
2. Audit-Regel `IFC-001` („ICD ohne Link zu einem Architektur-Element").
3. Interface-Coverage-Metric.
4. UI: ICD-Detail zeigt verknüpfte Elemente in **beide** Richtungen (`IcdDetailPane`, `TraceLinkPanel`).

**Betroffene Dateien:** `icd/traceability_connector.py`, `icd/icd_manager.py`,
`traceability/audit/registry.py` + neue Regel, `se_metrics/*`, `rest_api/icd_views.py`,
Frontend `IcdView/*`.

**Akzeptanzkriterium:**
- [ ] Neu angelegter ICD trägt einen `references`-Link; Audit meldet ICD ohne Link.
- [ ] Coverage-Metric + beidseitige UI-Darstellung.

### 4.14 #1269 — TestCase-Steps & TestRun-Version (MED)

**Befund (verifiziert):** `steps` optional (`serializers.py:1317-1319`); `result`-Feld existiert
nicht (enum `status`); `test_case_ids` existiert bereits; `tested_artifact_version` fehlt.

**Lösungsansatz:**
1. Precondition: `steps` nicht leer bei `approved`, außer `test_type ∈ {inspection, analysis,
   demonstration}` (Code-Vokabular; „exploratory" existiert nicht).
2. `TestRun.tested_artifact_version` (Commit/Tag) + Serializer/MCP.
3. `TestRunResult.test_case`-Bindung härten (heute `SET_NULL`; nullable dokumentieren oder
   Restriktion).
4. Abgleich `verification_method` ↔ TestCase-Typ (#878 verlinken).

**Betroffene Dateien:** `persistence/models.py`, `rest_api/serializers.py`,
`application/test_service.py`, `application/test_run_service.py`, Migrationen, MCP `tools/tests.py`.

**Akzeptanzkriterium:**
- [ ] TestCase ohne Steps kann (außer Sondertypen) nicht `approved` werden.
- [ ] TestRun trägt die getestete Artefakt-Version.

### 4.15 #1262 — Auditor-Regel-Katalog & Filter (MED)

**Befund (verifiziert):** Finding trägt nur `rule_id`; kein Katalog-Endpoint; Filter nur
`scope/limit/offset/include_suppressed`.

**Lösungsansatz:**
1. `GET /api/v1/audit/rules/` mit `rule_id`, Titel, Beschreibung, Severity, Standardbezug,
   „so beheben". Metadaten an den 14 Regeln nachtragen (heute nur Docstrings).
2. Server-Filter `rule_id`, `severity`, `artifact_type` am Audit-Endpoint (REST + MCP).
3. UI: Tooltip/Popover an der Regel-ID + Filterleiste mit Zählern.

**Betroffene Dateien:** `traceability/audit/registry.py` (+ Regel-Metadaten),
`rest_api/audit_views.py`, `rest_api/urls.py`, `mcp_server/tools/audit.py`,
Frontend `Audit/audit-dashboard`.

**Akzeptanzkriterium:**
- [ ] `/audit/rules/` liefert alle Regeln mit Erklärung.
- [ ] Filter nach Regel/Severity funktioniert serverseitig; UI zeigt Regel-Text.

### 4.16 #1248 — Memory-Scope-Vertrag (HIGH)

**Befund (verifiziert):** Kein Tenant-Write im Code. Echt: Write-Scope aus LLM-Extraktion,
Read-Scope aus Aufrufer; Default ohne `workspace_id` = `user`; Workspace-Panel default
`workspace` → Workspace-Facts unsichtbar.

**Lösungsansatz:**
1. Read-Default konsistent: liegt ein `workspace_id` vor, ist der Default-Scope `workspace`
   (statt `user`) — heute weichen Panel- und Einzel-Reads ab.
2. Interview-Write: Session-/Peer-Zuordnung sicherstellen (dokumentieren, dass ein
   `interview.chat`-Fakt über `memory.list` desselben Workspace auffindbar ist).
3. Scope-Matrix dokumentieren (REST/MCP-Filter × Write-Quelle).

**Betroffene Dateien:** `application/memory_entry_service.py:566-575,597-610`,
`memory/tasks.py`, `memory/prompts.py`, `memory/memory_rest.py`, `docs/api/MCP-SURFACE.md`.

**Akzeptanzkriterium:**
- [ ] Ein via `interview.chat` erzeugter Fakt ist mit demselben `workspace_id` über
      `memory.list`/`memory.query` auffindbar.
- [ ] Default-Scope ist getestet und dokumentiert.

### 4.17 #1247 — Memory.ask-Regression (HIGH)

**Befund (verifiziert, Grenze dokumentiert):** Shim existiert; Vendor-Pfad extern; Gate prüft
nur das Log; Live-Spike skip.

**Lösungsansatz:**
1. **#1153 wieder öffnen** (Closed-Zustand widerspricht der Messung).
2. Preflight/Health auf einen **echten** `complete()`-Roundtrip erweitern (statt nur
   Header-Ableitung zu prüfen); #1186-Smoke entsprechend schärfen.
3. Honcho-Image-/SDK-Pin prüfen (`requirements.txt:169` `honcho-ai==2.5.1` vs.
   `requirements.lock:66` `2.3.0`).
4. Falls Vendor-seitig nicht behebbar: dokumentierte Degradierung (lautes `degraded`) statt
   stiller Fehlantwort — Grenze explizit in `DEPLOY/README.md`.

**Betroffene Dateien:** `deploy/docker-compose.yml` (Preflight), `memory/honcho_backend.py`,
`memory/tests/test_honcho_deploy_contract.py`, `docs/DEPLOY_RUNBOOK.md`.

**Akzeptanzkriterium:**
- [ ] Ein automatisierter Check belegt den Header **am Wire** (oder die Grenze ist explizit
      als Upstream-Eskalation dokumentiert).
- [ ] #1153 ist wieder offen.

### 4.18 #1250 — Qdrant-Write fail-loud (HIGH)

**Befund (verifiziert):** Zwei fail-open-Abzweige; `health()` ohne Punkte-Check; Fakes zu
tolerant.

**Lösungsansatz:**
1. Fail-loud: `embedding is None` → Fehler (Task/Entry-Status); `upsert`-Exception →
   propagieren/markieren statt `return False` ohne Folge.
2. `health()` prüft Punktzahl/Collection-Erwartung.
3. `memory_reconcile.py` als periodischen Guard (Celery beat) einplanen.
4. Tests mit signaturgenauem Client (nicht kwargs-tolerant).

**Betroffene Dateien:** `memory/qdrant_backend.py:366-443,537-558`,
`llm_adapter/embedding_service.py`, `memory/tasks.py`, `memory/tests/*`.

**Akzeptanzkriterium:**
- [ ] Fehlendes Embedding/Upsert-Fehler erzeugt sichtbaren Fehler, keinen stillen `total=0`.
- [ ] Reconcile-Bericht erkennt „never mirrored".

### 4.19 #1249 — Honcho-Restart-Policies (HIGH)

**Befund (verifiziert):** Drei honcho-Services ohne Policy.

**Lösungsansatz:** `restart: unless-stopped` für `honcho`, `honcho-postgres`, `honcho-redis`;
Contract-Test erweitern: alle Langzeit-Services mit Policy, One-Shots
(`migrate`, `llm-preflight`, `honcho-migrate`) ausgenommen.

**Betroffene Dateien:** `deploy/docker-compose.yml`,
`memory/tests/test_honcho_deploy_contract.py`.

**Akzeptanzkriterium:**
- [ ] `docker inspect` zeigt für alle Laufzeit-Services `unless-stopped`.
- [ ] Contract-Test parst die Compose-Datei und schlägt bei Verstoß fehl.

### 4.20 #1251 — Capability-Matrix-Doku (MED)

**Befund (verifiziert):** Qdrant-Degradation undokumentiert; Base-URL leer ist intentional;
Tool-Namen aktuell.

**Lösungsansatz:** Capability-Matrix (Backend × Scope/`ask`/`digest`/externe Abhängigkeit) in
`deploy/README.md` + `docs/api/MCP-SURFACE.md`; Tabelle **LLM-Capability-ID ↔ MCP-Tool-Name**
(z. B. `check_consistency`-Capability vs. `requirement.check_consistency`-Tool), um die
Verwechslung zu beenden.

**Akzeptanzkriterium:**
- [ ] Matrix veröffentlicht; `ask`/`digest`-Degradierung je Backend benannt.
- [ ] Namens-Umstellungstabelle vorhanden.

### 4.21 #1240 — Robuste LLM-JSON-Extraktion (HIGH)

**Befund (verifiziert):** Exception wird gefangen; 500 entsteht im View-Mapping;
`is_mock_fallback` geht bei Parse-Fehler verloren; schwache Fence-Bereinigung an 5 Stellen.

**Lösungsansatz:**
1. `LlmResponseError` → **502 `LLM_OUTPUT_INVALID`** im View-Mapping
   (`views.py:1586-1592` + Facade).
2. Gemeinsames robustes JSON-Extraktionshelfer (Regex-Fence + `JSONDecoder.raw_decode`,
   Muster `interview_multi_protocol.py:103-120`) für alle 5 Stellen
   (`ai_derivation_service.py:492,2843`, `architecture_decompose_service.py:1016`,
   `ai_review_service.py:546`, `traceability_suggest_service.py:934`).
3. `is_mock_fallback` auch im Fehlerfall anwenden.

**Akzeptanzkriterium:**
- [ ] Nicht-JSON-LLM-Output → strukturierter 502, **nie** 500.
- [ ] Unit-Tests (Fences/Extra-Data) für alle 5 Call-Sites.

### 4.22 #1241 — Workspace-Delete-Kaskade (HIGH)

**Befund (verifiziert):** `we_engine_definition.self`-`PROTECT` → `ProtectedError` → 500.

**Lösungsansatz:**
1. Löschreihenfolge in `workspace_service.py:746-791`: `we_item_state` (und abhängige Zeilen)
   **vor** `we_engine_definition` löschen — oder die Collector-Reihenfolge explizit auflösen.
2. `ProtectedError` im View-Mapping auf **409/400 mit Begründung** abbilden (statt 500).
3. Regressionstest „Workspace **mit** Inhalt → 204".

**Betroffene Dateien:** `application/workspace_service.py`, `rest_api/views.py` (Mapping),
`workflow/models.py` (nur Bewertung), Tests.

**Akzeptanzkriterium:**
- [ ] `DELETE /workspaces/<id>/` mit Inhalt → 204 (Kaskade) oder 409 mit Begründung.
- [ ] Kein generischer 500.

### 4.23 #1242 — ReqIF-Reimport-Idempotenz (MED)

**Befund (verifiziert):** `foreign_identifier` wird vor dem Reset fixiert; leerer ATTR-UID →
Identitätsverlust → Duplikate bei Needs/Relations.

**Lösungsansatz:**
1. `foreign_identifier` nach dem Cross-Workspace-Reset **neu ableiten/persistieren**
   (`reqif_import_service.py:1245-1258,1396-1397`); lokale `uid` aus ATTR-UID immer schreiben.
2. Externe **Relation**-Identität für Idempotenz persistieren.
3. Regressionstest: Cross-Workspace + **leerer** ATTR-UID (bestehende Fixture nutzt
   `uid="NEED-001"` → blinde Stelle).

**Akzeptanzkriterium:**
- [ ] Zweiter Import derselben Datei: 0 created für Requirements **und** Needs **und** Relations.
- [ ] Neuer Test deckt den leeren-ATTR-UID-Fall.

### 4.24 #1244 — Workspace-ETag & 412 (MED)

**Befund (verifiziert):** Workspace ohne `ETagMixin`; OpenAPI 0/338 mit 412.

**Lösungsansatz:**
1. `ETagMixin` (`mixins/etag.py:150`) an `retrieve`/`partial_update` des Workspace-ViewSets.
2. `ExpectedVersionSerializerMixin` für Workspace; `WorkspaceService.update_metadata` prüft
   die Version.
3. **Semantik wie Artefakt-Endpoints:** **falsches** `If-Match` → 412; **fehlendes**
   `If-Match` → weiterhin erlaubt (Last-Writer-Wins, konsistent mit `requirements.ts:262-267`).
4. `412` in drf-spectacular für alle ETag-Endpoints deklarieren.

**Akzeptanzkriterium:**
- [ ] `GET /workspaces/<id>/` liefert `ETag`; falsches `If-Match` → 412.
- [ ] OpenAPI deklariert 412 für die ETag-Endpoints.

### 4.25 #1243 — Provider-Guard & Async-Timeout (MED)

**Befund (verifiziert):** `providers.py:2137` (und `:1581,1943`) unguarded; Async ohne
Timeout → 30 s vs. Sync 180 s.

**Lösungsansatz:**
1. `response.choices`-Extraktion in **allen drei** Providern absichern (leer/None →
   `LlmTransportError`).
2. `bundle_compression`-Async-Dispatch übergibt `timeout_seconds=long_running` (180 s),
   analog Sync.

**Akzeptanzkriterium:**
- [ ] Leere Choices → sauberer Fehler, kein `TypeError`.
- [ ] Async-Kompression mit >30 s Latenz läuft durch.

### 4.26 #1245 — Suggestion-Inbox-Auffindbarkeit (MED)

**Befund (verifiziert):** Inbox existiert hinter Mode-Toggle; 409 fail-closed ist korrekt.

**Lösungsansatz:** Empty-State erklärt, dass Suggestions **agent-generiert** sind und nur mit
agent-typisiertem API-Key befüllt werden; Mode-Toggle prominenter; Doku
(Doku-Pfad „Agent-Key → Suggestion"). **Kein** Verhaltenswechsel an der Fail-Closed-Regel.

**Akzeptanzkriterium:**
- [ ] Inbox-Mode ist ohne Vorwissen auffindbar; Empty-State nennt den Agent-Pfad.
- [ ] Fail-Closed-Verhalten unverändert (Test bleibt grün).

---

## 5. Reihenfolge & Abhängigkeiten

### 5.1 Harte Abhängigkeiten

```
W1: 1239 (Re-Messung) ──► 1239 (Härtung/Guard)     1256 ──┐
    1252, 1255 (unabhängig)                              ├─► PR-Wave-1
W2: 1264 (Fokus-Owner) ──► 1254 (Aktionszone nutzt Button-Standard)
    1253 (Dropdown) ──► 1259 (gemeinsame Katalog-Einstiege)
W3: 1270, 1261 (unabhängig)
W4: 1267 (Flag + Rule)  1268 (Connector ──► Rule/Metric)  1269 ──► 1262? (nein, entkoppelt)
W5: 1249 (Deploy)  1250 (Backend) ──► 1248 (Scope)  1247/1251 (Doku/Boundary)
W6: 1240-Helper ──► 1240-Call-Sites (×5)  1243 (Guards)  1242  1241  1244  1245
```

- **1239 ist keine Voraussetzung für 1256**, teilen aber den Refresh-Pfad → gemeinsamer Branch.
- **W4-1267** ist **feature-geflaggt**, damit der Gate nicht systemweit zwingt.

### 5.2 Parallelisierbarkeit (Datei-Disjunktheit)

| Gruppe | Parallel? | Begründung |
|---|---|---|
| W1 ⇄ W2 | **nein (sequenziell)** | beide im Frontend (Form/Dialog/Settings-CSS); W2 zieht #1254 aus W1 |
| W1/W2 ⇄ W3–W6 | **ja** | W3 = Serializer/Doku (additiv), W4/W5/W6 = Backend/Deploy |
| W3 ⇄ W4 ⇄ W5 ⇄ W6 | **ja** | disjunkte Module |
| innerhalb W6 | teilweise | 1240-Helper zuerst, dann Call-Sites; Rest parallel |

### 5.3 Empfohlene Abarbeitung

```
W1 ─► PR-Wave-1 (fix/wave1-detail-form-chrome)
W2 ─► PR-Wave-2 (fix/wave2-design-system-standards)   [nach W1]
W3 ─► PR-Wave-3 (fix/wave3-trace-identity)            [parallel zu W4–W6]
W4 ─► PR-Wave-4 (fix/wave4-se-gates-auditor)
W5 ─► PR-Wave-5 (fix/wave5-memory-reliability)
W6 ─► PR-Wave-6 (fix/wave6-api-robustness)
Entscheidungsspur ─► fix/decision-track (D1–D4, kein Produktcode)
```

---

## 6. Branch-/Commit-Strategie

- **Branch-Basis:** `origin/main @ 1b3e85af`. **Nie** direkt auf `main`/`master`
  (Branch-Guard).
- **Commits:** Conventional Commits, Englisch, Imperativ, ≤ 72 Zeichen erste Zeile.
  `fix(REQ-xxx): …` bei REQ-Bezug, sonst `fix: …`.
- **Commit-Granularität:** ein logischer Fix pro Commit; Tests im selben Commit (TDD).
- **PR pro Welle** gegen `main`; Beschreibung verlinkt die Issues (`Fixes #<nr>`).
- **Secret-Scan** vor jedem Commit (Paved Road `secret-scanning`).
- **Push/Tag/Branch-Management:** ausschließlich `git`-Agent — nicht Teil dieser Planung.

| Welle | Branch-Vorschlag |
|---|---|
| W1 | `fix/wave1-detail-form-chrome` |
| W2 | `fix/wave2-design-system-standards` |
| W3 | `fix/wave3-trace-identity` |
| W4 | `fix/wave4-se-gates-auditor` |
| W5 | `fix/wave5-memory-reliability` |
| W6 | `fix/wave6-api-robustness` |
| Residuen/Entscheidungen | `fix/decision-track` |

---

## 7. Verifikation / DoD

### 7.1 Globale Kommandos (verifiziert in Runde 2, unverändert gültig)

| Zweck | Kommando |
|---|---|
| Backend-Tests | `make test-backend` → Container `pytest -q` |
| Frontend-Tests | `make test-frontend` → `npm install && npm test` (`vitest run`) |
| Beide (ohne E2E) | `make test` |
| Frontend-Lint | `cd frontend && npm run lint` |
| Backend-Lint | `ruff check . --select=F821,F822` |
| Frontend-Typecheck/Build | `cd frontend && npm run build` (`tsc -p tsconfig.build.json && vite build`) |
| E2E (manuell) | `cd e2e && npm install && npx playwright test` |
| Template-/Manifest-Suite | `pytest docs/agent-templates dist` |
| Version-Drift | `./scripts/check-version-drift.sh` |
| **Compose-Validierung (neu, W5)** | `docker compose -f deploy/docker-compose.yml config -q` |
| **OpenAPI-Validation (neu, W6/1244)** | `python manage.py spectacular --validate` (bzw. Schema-Snapshot-Test) |

### 7.2 DoD pro Fix

1. **Reproduktion:** Test/Re-Messung schlägt **vor** dem Fix fehl (bzw. Falsifikation belegt).
2. **Fix:** minimal, fokussiert, **holistisch** (alle betroffenen Consumer/Entity-Typen).
3. **Nachweis:** Proof-Tests grün; keine neue Regression.
4. **Regression-Guard:** `make test-backend` + `make test-frontend` ohne neue Fehler.
5. **Lint/Typecheck:** `ruff`, `npm run lint`, `npm run build` sauber.
6. **Manifest-Berührung** (1244 OpenAPI, 1262 MCP-Tools): Drift-Gate
   `test_tool_manifest_drift.py` grün.
7. **Security-adjazent:** Secret-Scan vor jedem Commit; 1241 (Kaskade) und 1242 (Import)
   zusätzlich RLS-/Tenant-Guards prüfen.

### 7.3 Proof-Matrix

| Issue | Proof-Test | Typ |
|---|---|---|
| 1239 | neuer Editor-Test „Save ⇒ 1× PATCH"; E2E-Netzwerk-Assertion | Vitest + E2E |
| 1256 | Versions-Refetch-Test (req + arch) | Vitest |
| 1252 | Computed-Style-/Ratchet-Test @1280/1024/768 | Vitest |
| 1255 | „Veralten"-Transition-Test je Typ; `include_deleted` je Liste | Vitest |
| 1264 | Dialog-Fokus-Owner-Test; Glossar-Button-Konformität; Baum-a11y | Vitest |
| 1253 | Listbox-Empty-Open-Test (invertiert); Katalog-Link/Nav-Test | Vitest |
| 1258 | Button-Ratchet mit gesenktem Baseline | Vitest |
| 1259 | Nav-/Deep-Link-Test | Vitest |
| 1254 | Aktionszonen-Test | Vitest |
| 1270 | OpenAPI-Feldtest + CI-Konsistenztest (Read ↔ Link) | pytest |
| 1261 | `global_uuid`-Attributtest | pytest |
| 1267 | Gate-Test Requirement ohne `verifies` (extended) + Flag aus | pytest |
| 1268 | Connector-Test + `IFC-001` + Metric | pytest |
| 1269 | Steps-Precondition + `tested_artifact_version` | pytest |
| 1262 | `/audit/rules/` + Filtertest | pytest |
| 1248 | Write→Read-Scope-Test | pytest |
| 1247 | Preflight-Smoke (Header am Wire) oder Eskalations-Doku | Harness |
| 1250 | fail-loud-Test + Reconcile | pytest |
| 1249 | Compose-Contract-Test (Restart-Policies) | pytest |
| 1251 | Doku (Capability-Matrix) | Doku |
| 1240 | malformed-LLM-Output-Test (×5 Call-Sites) | pytest |
| 1241 | Workspace-Delete-mit-Inhalt-Test | pytest |
| 1242 | Reimport-Test (leerer ATTR-UID) | pytest |
| 1243 | Choices-Guard + Async-Timeout-Test | pytest |
| 1244 | Workspace-ETag/412-Test + OpenAPI-412 | pytest |
| 1245 | Inbox-Auffindbarkeits-/Empty-State-Test | Vitest |

---

## 8. Risiken & offene Entscheidungen

### 8.1 Entscheidungen — **getroffen am 2026-10-13**

| # | Entscheidung | Gewählt | Owner / Folge |
|---|---|---|---|
| D1 | `frontend/dist/`-Tracking | **Untracken + gitignoren** (`git rm -r --cached frontend/dist`) | `git` |
| D2 | ADR-ii: führende Autorisierungsachse | **B — Tenant führt, Workspace ist Policy** ⚠️ *korrigiert (s. u.)* | — |
| D3 | 2FA-Residuum | **Risiko-Akzeptanz dokumentieren + Roadmap-Tracking** | `se-architect` (ADR-021-Nachtrag) + `requirements` (eigenes Vorhaben) |
| D4 | `+ 74 APIViews` | **Zusatz entfernen; nur ViewSet-Zahl (28) führen** | `git` (Meta-Edit an `.meta-config/project.yaml`) |
| D5 | #1267-Gate-Statuscode | **400 `VALIDATION_ERROR`** | `developer` (W4) |
| D6 | #1255 Löschen-Semantik | **Hard-Delete-Button entfernen; nur „Veralten" (`deprecated`)** | `developer` (W1, §4.4) |

> **Offener Restpunkt (nicht Teil der 6 Entscheidungen):** `frontend/test-results/` braucht für
> den CI-Upload einen Job-scoped Ablageort. Der Ansatz ist entschieden (Pfad je Job), aber noch
> nicht implementiert — kleiner `devops-engineer`-Task außerhalb der Bugwellen.

### 8.2 Umsetzung der Entscheidungen (konkrete Folgeaufgaben)

> **Korrektur D2 (2026-10-14, verifiziert):** Die Autorisierungsachse war **bereits entschieden**.
> `docs/se/ADR/ADR-011_autorisierungsachse_workspace_tenant.md` ist **`accepted`** und wählt
> **Option C** — *„Tenant bleibt Isolationshülle, Workspace wird objektabgeleitete Achse mit
> explizitem Ressourcen-Scope"*. Option B („Tenant führend, Workspace als Policy") ist dort
> ausdrücklich **VERWORFEN** (`ADR-011` §Alternativen). Die hier unter D2 notierte Wahl „B" war
> eine **Fehlzuordnung** (der Kandidat war vor ADR-011 offen, danach nicht mehr). Es wird **kein**
> neues ADR angelegt; **ADR-011 gilt**. #1275 (Admin-Gate) richtet sich nach ADR-011; 2FA bleibt
> dokumentierte Risiko-Akzeptanz (ADR-021 O5-Nachtrag).

1. **D1 (dist):** `git rm -r --cached frontend/dist`, `frontend/dist/` in `.gitignore`;
   prüfen, dass die Docker-Build-Stufe das Frontend aus der Quelle baut (kein Checkout von
   `dist/` vorausgesetzt). Bricht nichts an einer laufenden Instanz.
2. **D2 (ADR-ii):** `se-architect` legt einen ADR nach MADR-Minimal an (Optionen A/B/C,
   gewählt **B**), `affected_reqs` aus SEC-02/03/04, verlinkt #1275. Danach ist das
   Admin-Gate aus #1275 entblockt (bleibt bis dahin hinter dem Lockout, kein stiller
   Zusatzschutz).
3. **D3 (2FA):** Nachtrag an ADR-021 (O5) mit dokumentierter Risiko-Akzeptanz (LAN, Lockout
   vorhanden, kein Kompensations-Anspruch) **und** ein eigenständiges Roadmap-/Feature-Issue
   „2FA/TOTP für Staff-Konten" (`requirements`). Kein Produktcode in dieser Runde.
4. **D4 (APIViews):** In `.meta-config/project.yaml` die Teilklausel „+ 74 APIViews" aus der
   Projektbeschreibung entfernen (ViewSet-Zahl **28** ist die kanonische); `AGENTS.md`/
   `CLAUDE.md` per Meta-Sync regenerieren. Drift-Gate aus Runde 2 (#1104) bleibt grün.
5. **D5 (Gate 400):** siehe §4.12 — im Umsetzungsschritt W4.
6. **D6 (Löschen):** siehe §4.4 — im Umsetzungsschritt W1.

### 8.3 Zu verifizierende Annahmen

| Annahme | Verifikationsweg |
|---|---|
| #1239 reproduziert auf `main` (und ist nicht Beobachtungsartefakt der QA) | Playwright-Netzwerk-Trace, 2 Presets |
| Scope-Default-Änderung (#1248) bricht keine bestehenden Reads | bestehende Memory-Tests + neuer Test |
| Steps-Pflicht (#1269) bricht keine Bestandsdaten | Migration/Backfill-Prüfung auf Seed-Workspace |
| Workspace-ETag (#1244) bricht keine Clients ohne `If-Match` | Semantik „fehlend = erlaubt" explizit testen |

### 8.4 Risiken

| Risiko | Issue(s) | Gegenmaßnahme |
|---|---|---|
| #1239-Ursache nicht in-repo reproduzierbar | 1239 | Re-Messung + Falsifikation + Guard-Test statt Blindflug |
| Gate ändert Freigabe systemweit | 1267 | nur `extended`, Feature-Flag, Test „Flag aus = alt" |
| Import-Verhaltensänderung bricht Suiten | 1242 | bestehende Import-Tests als Guards; neuer Fall additiv |
| Fokus-Standard regressiert andere Dialoge | 1264 | Fokus-Owner-Test über die **31** Consumer |
| Button-Ratchet wird aufgeweicht statt gesenkt | 1258 | Zielwerte fix; Baseline **senken**, Green als Fortschritt |
| Memory-Scope-Änderung macht alte Facts sichtbar/unsichtbar | 1248 | Scope-Matrix + Tests vor Merge |
| Vendor-Grenze (#1247) nicht in-repo lösbar | 1247 | Eskalation dokumentieren; Issue wieder öffnen |
| „Veralten"-Aktion nur wo Transition erlaubt | 1255 | Aktion an Transitions-API koppeln (kein toter Button) |

---

## 9. Out-of-scope

| # | Grund |
|---|---|
| 1257, 1260, 1263, 1265, 1266 | BluePencil-**Features** — eigene Planung; andocken an Attribut-Epic #934/#941 |
| 1230, 1171 | Roadmap |
| 934, 941, 946, 879, 878, 877, 801, 792, 598, 587, 378, 272, 186, 92, 89, 85, 50, 18 | Enhancement/Epic/Feature — eigene Roadmap |
| 1104 (Rest) | Entscheidungsspur D4 |
| 1275 | Entscheidungsspur D2/D3 |

> **Summe:** 24 bugfix-relevante Issues (W1–W6) + 6 Entscheidungen (D1–D6) = vollständig
> erfasst. Kein Issue der Runde 2 wiederholt; die 5 BluePencil-Features und die Roadmaps
> bleiben bewusst außen vor.

---

## 10. Self-Review des Plans

- **Auftrag erfüllt:** „Unmenge neuer Bugs" gebündelt nach **geteilter Komponente**
  (holistisch), mit **Tiefenanalyse** je Issue (§2: Behauptung vs. Verifikation).
- **Fakten vs. Annahmen:** Jede Kernaussage ist mit `file:line` belegt; Hypothesen sind als
  Annahme markiert (§2, §8.2). 7 Issues mit ungenauer Ursache sind explizit korrigiert.
- **Holistik belegt:** W1 flickt **alle 7** Detailtypen über `ArtifactForm`/`ArtifactInspector`;
  W2 standardisiert **Dialog (31 Consumer), Buttons, Katalog-Einstiege**; W6 vereinheitlicht
  **eine** JSON-Extraktion für 5 Call-Sites und **drei** Provider.
- **Shippability:** 6 unabhängige `fix/*`-Branches + Entscheidungsspur; kein Commit auf `main`.
- **Messbarkeit:** Jedes Issue hat testbare Akzeptanzkriterien (§4) + Proof-Test (§7.3).
- **Entscheidungen getroffen:** §8.1 listet alle sechs (D1–D6, getroffen 2026-10-13),
  darunter D1–D4 aus den Residuen der Runde 2.
- **Nicht implementiert:** Dieser Plan enthält **keine** Code-Änderungen und löst **keine**
  Commits/Pushes aus.

---

*Erstellt vom Haupt-Thread am 2026-10-13. Basis `origin/main @ 1b3e85af`; 24 bugfix-relevante
beta.20-Issues in 6 Wellen, 6 Entscheidungen (D1–D6). Kein Issue der Runde 2 wiederholt.*
