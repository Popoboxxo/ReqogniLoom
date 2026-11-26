---
type: PLAN
title: "REST/MCP Review-Findings: vollständiger Umsetzungsplan"
status: umgesetzt_mit_restpunkten
date: 2026-11-25
author_agent: main_chat
language: de
branch_basis: "fix/document-workflow-reading-view"
review_sources:
  - ".tmp/code-review-rest-mcp.md"
  - ".tmp/security-audit-rest-mcp-2026-11-25.md"
  - "Aggregierter REST/MCP-Review vom 2026-11-25"
---

# REST/MCP Review-Findings: vollständiger Umsetzungsplan

- **Stand:** 2026-11-25
- **Status:** zur Freigabe
- **Basis-Branch:** `fix/document-workflow-reading-view`

**Ziel:** Alle belegten Review-Befunde priorisiert, nachvollziehbar und ohne Regressionen umsetzen.

## 1. Zusammenfassung

Der Review hat **1 Blocker, 16 Major und 18 Minor** gemeldet. In den ausformulierten Einzelbefunden sind **15 Minor** mit eigener ID belegt; die Differenz zu 18 wird im ersten Arbeitspaket gegen die Fachberichte geschlossen. Dieser Plan bildet alle 32 einzeln belegten Befunde auf **27 Arbeitspakete** ab und reserviert ein explizites Gate für die drei nicht separat ausformulierten Minor-Positionen.

Schwerpunkte:

1. OpenAPI-Vertrag des Workflow-Editors vervollständigen.
2. Produktions-Sicherheitsdefaults und MCP-Workspace-Scoping härten.
3. REST/MCP-Parität bei Workflow-Defaults, Transitionen, Soft-Delete und Filtern herstellen.
4. Fehlercodes, Serializer und Fehlerbehandlung konsistent machen.
5. Minor-Tech-Debt und Frontend-Typduplikate aufräumen.

## 2. Befundbasis und Zählabweichung

| Quelle | Inhalt |
|---|---|
| REST-/MCP-Aggregat | 1 Blocker, 16 Major, 18 Minor, 8 Info |
| `.tmp/code-review-rest-mcp.md` | 5 Major, 8 Minor, 3 Info |
| `.tmp/security-audit-rest-mcp-2026-11-25.md` | 7 Security-Befunde |
| Einzelaufstellung dieses Plans | 1 Blocker, 16 Major, 15 Minor |

> **Nachtrag 2026-11-25:** Gate P0.2 abgeschlossen — die Zählung wurde auf 15 belegte Minor korrigiert; Begründung und Belegmatrix siehe Abschnitt „P0.2 — Gate-Ergebnis".

**Gate P0.2:** Vor Beginn der Minor-Umsetzung werden die drei im Aggregat gezählten, aber nicht einzeln ausformulierten Minor-Befunde aus den Fachberichten nachgezogen. Fehlt eine belastbare Quelle, wird die Zählabweichung im Review-Nachtrag korrigiert; es wird kein Befund erfunden.

### P0.2 — Gate-Ergebnis (2026-11-25, abgeschlossen)

**Verdikt:** Die im Aggregat gezählten **18 Minor** sind durch keine vorliegende Quelle belegt. Belastbar sind **15 Minor** mit eigener ID (m-1 … m-15, §6). Die dritte im Frontmatter genannte Quelle („Aggregierter REST/MCP-Review vom 2026-11-25") liegt nicht als Datei im Repository und war nicht prüfbar. **Es wurde kein Befund erfunden.**

**Beleglage der prüfbaren Berichte:** `.tmp/code-review-rest-mcp.md` liefert fünf Major-Befunde (1–5, im Plan M-11 … M-15) sowie die Minor-Befunde 6–12. `.tmp/security-audit-rest-mcp-2026-11-25.md` liefert sieben Befunde (1 HIGH, 4 MEDIUM, 2 LOW); Finding #1–#5 münden in M-1 … M-5, Finding #6 (LOW) in den Major M-10, Finding #7 (LOW) in m-14. Beide Berichte zusammen ergeben neun Minor-Klassen-Einträge: acht davon sind auf m-IDs abgebildet, einer auf M-10. Diese Belegmatrix betrifft ausschließlich die Minor-Positionen; Blocker und Major sind nicht Gegenstand von P0.2.

| ID | Kurzinhalt | Paket | Belegquelle |
|---|---|---|---|
| m-1 | `read_only_reason` fälschlich required | P1.6 | nur Aggregat (nicht separat belegt) |
| m-2 | `help_text` für Reading-Felder fehlt | P1.6 | nur Aggregat (nicht separat belegt) |
| m-3 | `operationId reviews_retrieve` für List-Operation | P2.11 | nur Aggregat (nicht separat belegt) |
| m-4 | Doppelte Document-Serialisierung | P2.2 | `.tmp/code-review-rest-mcp.md`, Befund 6 |
| m-5 | `WorkflowEditorPage` vermischt Scopes | P2.4 | `.tmp/code-review-rest-mcp.md`, Befund 7 |
| m-6 | `DocumentReadingViewProps.onEdit` required | P2.12 | `.tmp/code-review-rest-mcp.md`, Befund 8 |
| m-7 | Mehrfache `WorkflowTransitionResult`-Typen | P2.3 | `.tmp/code-review-rest-mcp.md`, Befund 9 |
| m-8 | `include_deleted` vs. `include_outdated` | P2.1 | `.tmp/code-review-rest-mcp.md`, Befund 10 |
| m-9 | `useWorkflowMutations` repetitiv | P2.5 | `.tmp/code-review-rest-mcp.md`, Befund 11 |
| m-10 | Workspace-`setStateFreeze` ist No-Op | P2.6 | `.tmp/code-review-rest-mcp.md`, Befund 12 |
| m-11 | Workflow-Definition-Cache nicht threadsicher | P2.7 | nur Aggregat (nicht separat belegt) |
| m-12 | Dokument-/WorkItem-Create verschluckt Workflow-Init-Fehler | P2.13 | nur Aggregat (nicht separat belegt) |
| m-13 | WorkItem-MCP ohne Soft-Delete/Restore | P2.8 | nur Aggregat (nicht separat belegt) |
| m-14 | HSTS/SSL/CSP nur auskommentiert | P2.9 | `.tmp/security-audit-rest-mcp-2026-11-25.md`, Finding #7 (LOW) |
| m-15 | `DocumentViewSet.transitions` verschluckt Exceptions | P2.10 | nur Aggregat (nicht separat belegt) |

Für sieben m-Positionen (m-1, m-2, m-3, m-11, m-12, m-13, m-15) enthält keiner der prüfbaren Berichte einen Einzelbefund; sie sind ausschließlich im Aggregat gezählt. Sie bleiben in §6 mit ID und Paket geführt, damit die Zuordnung nachvollziehbar bleibt, werden aber nicht als belegt ausgegeben.

Zählung korrigiert: 1 Blocker + 16 Major + 15 Minor = 32 belegte Befunde (+ 8 Info). Die drei im Aggregat zusätzlich gezählten Minor-Positionen bleiben unbelegt und werden nicht umgesetzt; es wird kein Befund erfunden.

## 3. Ziele und Nicht-Ziele

### Ziele

- OpenAPI 3.0 beschreibt alle Workflow-Endpunkte vollständig und wahrheitsgemäß.
- Produktionskonfiguration ist fail-closed und enthält keine schwachen Defaults.
- MCP-Write-Tools können bei unbekanntem Workspace-Scope nicht auf Tenant-Rollen zurückfallen.
- REST und MCP verwenden für gleiche Operationen gleiche Parameter und Semantik.
- Alle neuen oder geänderten Verträge sind durch gezielte Tests und Drift-Gates abgesichert.
- Jede Änderung ist einzeln reviewbar und rückrollbar.

### Nicht-Ziele

- Kein Redesign der gesamten REST- oder MCP-Architektur.
- Keine Änderung der fachlichen Workflow-Zustände ohne separaten Bedarf.
- Keine automatische Rotation realer Deployment-Secrets durch den Code.
- Keine pauschale Umbenennung bestehender öffentlicher APIs ohne Alias-/Migrationspfad.

## 4. Globale Constraints

- **Secrets:** Reale Werte aus `.env` werden nie committed. Sie werden lokal/deploymentseitig rotiert; Templates enthalten nur Platzhalter oder leere Pflichtfelder.
- **Rückwärtskompatibilität:** MCP-Parameter werden, wo sinnvoll, mit Alias und Deprecation-Hinweis umgestellt.
- **Schichtgrenzen:** DRF-Views enthalten keine direkten Model-Queries; Fachlogik läuft über Services.
- **OpenAPI:** Dekorationen beschreiben das tatsächliche Verhalten inklusive Fehlerstatus und Query-Parameter.
- **Tests:** Jedes Paket enthält mindestens einen positiven und einen negativen Test.
- **DoD:** gezielte Tests grün, Typecheck/Lint grün, `git diff --check` sauber, keine neuen Secrets, keine unbeabsichtigten öffentlichen Vertragsänderungen.
- **Reihenfolge:** Schema- und Backend-Verträge vor Frontend-Anpassungen; Snapshot-Updates erst nach stabiler Implementierung.

## 5. Tatsächliche Datei-/Modulbasis

| Bereich | Relevante Dateien |
|---|---|
| Workflow-REST | `backend/rest_api/views_governance.py`, `backend/rest_api/serializers_governance.py` |
| Entity-/Document-/Baseline-REST | `backend/rest_api/views_entity_core.py`, `backend/rest_api/preset_guard.py`, `backend/rest_api/views_trace_baseline.py` |
| Globale Workflow-Defaults | `backend/rest_api/global_default_views.py`, `backend/rest_api/urls.py` |
| MCP-Scope | `backend/mcp_server/workspace_scope.py`, `backend/mcp_server/tests/test_mcp_workspace_scope.py` |
| MCP-Tools | `backend/mcp_server/tools/document.py`, `work_items.py`, `requirements.py` |
| Auth | `backend/auth_tenancy/services/authentication.py`, `backend/reqogniloom/settings.py` |
| Bootstrap/Konfiguration | `backend/application/self_init.py`, `backend/auth_tenancy/management/commands/bootstrap_admin.py`, `scripts/setup.sh`, `.env.example`, `deploy/.env.example` |
| Workflow-Engine | `backend/workflow/transition_validator.py`, `backend/workflow/services.py` |
| Anwendungs-Services | `backend/application/document_service.py`, `backend/application/work_item_service.py` |
| Frontend-API | `frontend/src/api/index.ts`, `workflows.ts`, `workflow-defaults.ts`, `workflow-transitions.ts`, `documents.ts` |
| Frontend-Editor | `frontend/src/components/WorkflowEditor/WorkflowEditorPage.tsx`, `useWorkflowMutations.ts` |
| Frontend-Dokumente | `frontend/src/components/Documents/DocumentReadingView.tsx` |
| Vertrags-Gates | `backend/rest_api/tests/test_openapi_contract_snapshot.py`, `backend/mcp_server/tests/test_tool_manifest_drift.py`, `backend/mcp_server/tests/test_entity_surface_parity.py` |

## 6. Befund-zu-Arbeitspaket-Matrix

| Befund | Kurzinhalt | Paket |
|---|---|---|
| B-1 | `WorkflowDefinitionViewSet` ohne `@extend_schema` | P0.1 |
| — | Drei nicht separat ausformulierte Minor-Befunde | P0.2 |
| M-1 | Reale Secrets und schwaches Admin-Passwort | P1.1 |
| M-2 | Auth-Cookies nicht `Secure` | P1.1 |
| M-3 | CORS-Allowlist mit `localhost` in Produktion | P1.1 |
| M-4 | MCP-Workspace-Scope fail-soft | P1.2 |
| M-5 | API-Key ohne Pepper/HMAC | P1.3 |
| M-6 | `GET /workflows/` suggeriert CRUD-List | P1.4 |
| M-7 | WorkItem `preset: null` | P1.5 |
| M-8 | Reading-View dokumentiert nur 200 | P1.6 |
| M-9 | `DocumentReadingSerializer` unvollständig | P1.6 |
| M-10 | Baseline-Flat-Route 404 statt 400 | P1.7 |
| M-11 | Keine MCP-Oberfläche für globale Workflow-Defaults | P1.8 |
| M-12 | `workflowDefaultsApi` nicht exportiert | P1.8 |
| M-13 | Transitionstypen ohne `document`/`work-item` | P1.9 |
| M-14 | `change_reason` vs. `reason` | P1.10 |
| M-15 | `document.query` filtert `uid` clientseitig | P1.11 |
| M-16 | MCP-Handler maskieren Fehler ohne Logging | P1.12 |
| m-1 | `read_only_reason` fälschlich required | P1.6 |
| m-2 | `help_text` für Reading-Felder fehlt | P1.6 |
| m-3 | `operationId reviews_retrieve` für List-Operation | P2.11 |
| m-4 | Doppelte Document-Serialisierung | P2.2 |
| m-5 | `WorkflowEditorPage` vermischt Scopes | P2.4 |
| m-6 | `DocumentReadingViewProps.onEdit` required | P2.12 |
| m-7 | Mehrfache `WorkflowTransitionResult`-Typen | P2.3 |
| m-8 | `include_deleted` vs. `include_outdated` | P2.1 |
| m-9 | `useWorkflowMutations` repetitiv | P2.5 |
| m-10 | Workspace-`setStateFreeze` ist No-Op | P2.6 |
| m-11 | Workflow-Definition-Cache nicht threadsicher | P2.7 |
| m-12 | Dokument-/WorkItem-Create verschluckt Workflow-Init-Fehler | P2.13 |
| m-13 | WorkItem-MCP ohne Soft-Delete/Restore | P2.8 |
| m-14 | HSTS/SSL/CSP nur auskommentiert | P2.9 |
| m-15 | `DocumentViewSet.transitions` verschluckt Exceptions | P2.10 |

## 7. Arbeitspakete

### P0.1 — WorkflowDefinitionViewSet vollständig dokumentieren

- **Priorität:** Blocker · **Größe:** S · **Risiko:** niedrig
- **Dateien:** `backend/rest_api/views_governance.py`, neuer Test `backend/rest_api/tests/test_workflow_definition_openapi.py`
- **Umsetzung:** Alle Actions (`list`, `definition`, `create_state`, `modify_state`, `delete_state`, `create_transition`, `modify_transition`, `delete_transition`, `initialize`) mit `@extend_schema` typisieren. Request-/Response-Serializer, Query-Parameter sowie 200/400/403/404 dokumentieren.
- **Tests:** Schema enthält echte Serializer und Fehlerantworten; bestehende Workflow-API-Tests bleiben grün.
- **DoD:** Keine generische Operation mehr; OpenAPI-Generierung und Snapshot-Diff geprüft.

### P0.2 — Befund-Inventar schließen

- **Priorität:** Blocker-Gate · **Größe:** XS · **Risiko:** niedrig
- **Umsetzung:** Die drei im Aggregat gezählten, aber nicht einzeln belegten Minor-Befunde aus den Fachberichten nachziehen; Mapping-Tabelle ergänzen. Falls keine Quelle existiert, Review-Zählung korrigieren.
- **DoD:** Jeder gezählte Befund hat entweder eine ID und ein Paket oder eine dokumentierte Korrektur der Zählung.

### P1.1 — Produktionskonfiguration und Secrets härten

- **Priorität:** Security · **Größe:** M · **Risiko:** hoch
- **Betrifft:** M-1, M-2, M-3
- **Dateien:** `.env.example`, `deploy/.env.example`, `backend/reqogniloom/settings.py`, `backend/application/self_init.py`, `backend/auth_tenancy/management/commands/bootstrap_admin.py`, `scripts/setup.sh`, Runbook `docs/runbooks/secret-rotation.md`
- **Umsetzung:**
  - Reale lokale `.env`-Secrets außerhalb des Codes rotieren; `SYSTEM_ADMIN_PASSWORD=admin` sofort ersetzen.
  - Templates ohne echte Secrets, ohne `admin`-Passwort und mit leeren Pflichtfeldern.
  - Production-Checks: fehlende/schwache Secrets, unsichere Cookie-Flags, `localhost` in CORS/CSRF-Origins ablehnen oder deutlich warnen.
  - `setup.sh` generiert starke Zufallswerte und schreibt sie nur in die lokale, ignorierte `.env`.
- **Tests:** Settings-Checks für Produktion; Bootstrap lehnt schwache Passwörter ab; CORS-/Cookie-Negativtests; Secret-Scan über den Diff.
- **DoD:** Keine Secrets im Diff; Produktionsstart mit unsicherer Konfiguration schlägt kontrolliert fehl; Dev-Konfiguration bleibt nutzbar.

### P1.2 — MCP-Workspace-Scope fail-closed

- **Priorität:** Security · **Größe:** M · **Risiko:** hoch
- **Betrifft:** M-4
- **Dateien:** `backend/mcp_server/workspace_scope.py`, `backend/mcp_server/tests/test_mcp_workspace_scope.py`
- **Umsetzung:** Write-Tools ohne auflösbaren Ziel-Workspace geben `PERMISSION_DENIED` zurück, statt auf Tenant-Rollen zurückzufallen. Jedes Write-Tool muss entweder `workspace_id` verlangen, in `_TOOL_TARGETS` stehen oder explizit als tenant-scoped begründet sein. Ratchet-Test aus `tool-manifest.json` ableiten.
- **Tests:** fehlende, malformed, fremde und gelöschte `workspace_id`; unbekanntes Write-Tool; Read-Tool-Ausnahmen.
- **DoD:** Kein fail-open-Pfad für Writes; Fehlermeldung ohne interne Details; Manifest-Ratchet grün.

### P1.3 — API-Key-Pepper im Produktionsbetrieb erzwingen

- **Priorität:** Security · **Größe:** S · **Risiko:** mittel
- **Betrifft:** M-5
- **Dateien:** `backend/reqogniloom/settings.py`, `backend/auth_tenancy/services/authentication.py`, `scripts/setup.sh`, bestehende `backend/auth_tenancy/tests/test_api_key_pepper.py`
- **Umsetzung:** `API_KEY_PEPPER` in Produktion verpflichtend; Setup generiert ihn. Bestehende Legacy-Hashes bleiben lesbar, werden aber als Rotationskandidaten behandelt. Kein unnötiger Schema-Umbau, da das Hash-Präfix die Variante bereits unterscheidet.
- **Tests:** Produktions-Check ohne Pepper schlägt fehl; HMAC-Erzeugung und Alt-Hash-Verifikation; Pepper-Rotation dokumentiert.
- **DoD:** Neue Deployments verwenden HMAC; Rotation ist im Runbook beschrieben.

### P1.4 — Workflow-Listenvertrag ehrlich machen

- **Priorität:** Major · **Größe:** S/M · **Risiko:** mittel
- **Betrifft:** M-6
- **Dateien:** `backend/rest_api/views_governance.py`, `backend/rest_api/tests/test_workflow_definition_views_rest.py`
- **Umsetzung:** Entscheidung dokumentieren und umsetzen: entweder echte Workspace-Workflow-Liste oder explizit leere, nicht als CRUD-List dokumentierte Antwort. Bestehenden Vertrag nicht still brechen.
- **Tests:** Listet vorhandene Definitionen korrekt oder dokumentiert die leere Semantik; OpenAPI passt zum Verhalten.
- **DoD:** Kein Schema, das eine nicht vorhandene CRUD-Funktion verspricht.

### P1.5 — WorkItem-Preset in uninitialisierter Definition korrekt auflösen

- **Priorität:** Major · **Größe:** S · **Risiko:** niedrig
- **Betrifft:** M-7
- **Dateien:** `backend/rest_api/views_governance.py`, `backend/workflow/item_types.py`, vorhandener zentraler Preset-Resolver in `backend/workflow/services.py`
- **Umsetzung:** Bei `WorkItem` den aus dem Workspace-Tier abgeleiteten `work_item_<tier>`-Namen zurückgeben, nicht `null`. Denselben Resolver wie die Initialisierung nutzen.
- **Tests:** `definition`-Antwort für alle drei Tiers; Fallback auf `standard`; bestehende Preset-Initialisierungstests.
- **DoD:** Kein `preset: null` für WorkItem in einer auswertbaren Workspace-Konfiguration.

### P1.6 — Document-Reading-Vertrag und Serializer vervollständigen

- **Priorität:** Major · **Größe:** M · **Risiko:** mittel
- **Betrifft:** M-8, M-9, m-1, m-2
- **Dateien:** `backend/rest_api/views_entity_core.py`, `backend/rest_api/serializers_governance.py`
- **Umsetzung:**
  - `GET /documents/{id}/view/` dokumentiert 200, 400, 403 und 404.
  - Kapitel-, Projektions- und Frozen-Felder vollständig typisieren und mit `help_text` versehen.
  - `read_only_reason` als `required=False` markieren.
- **Tests:** Schema-/Serializer-Tests, Reader-/Writer-Berechtigungen, leerer Body, fehlendes Dokument.
- **DoD:** Kein undokumentierter Fehlerpfad; OpenAPI und tatsächliche Responses stimmen überein.

### P1.7 — Baseline-Flat-Route validiert vor dem Preset-Gate

- **Priorität:** Major · **Größe:** S · **Risiko:** niedrig
- **Betrifft:** M-10
- **Dateien:** `backend/rest_api/views_entity_core.py`, `backend/rest_api/preset_guard.py`, `backend/rest_api/tests/`
- **Umsetzung:** Fehlende oder ungültige `workspace_id` vor der Preset-Auflösung als `400 VALIDATION_ERROR` behandeln. Preset-deaktiviert, fremder Workspace und fehlender Parameter getrennt unterscheiden.
- **Tests:** fehlende/ungültige/fremde Workspace-ID; gültiger Request.
- **DoD:** Kein irreführendes 404 für einen Client-Fehler.

### P1.8 — Globale Workflow-Defaults über MCP und Frontend-Index bereitstellen

- **Priorität:** Major · **Größe:** M · **Risiko:** mittel
- **Betrifft:** M-11, M-12
- **Dateien:** `backend/mcp_server/tools/` (neue Tool-Gruppe), `backend/mcp_server/tests/test_tool_manifest_drift.py`, `docs/agent-templates/tool-manifest.json`, `frontend/src/api/index.ts`
- **Umsetzung:**
  - MCP-Gruppe `workflow_default.*` für Read und Mutationen auf denselben Service wie REST legen.
  - Falls bewusst keine Mutationen exponiert werden, die Asymmetrie in `docs/api/MCP-SURFACE.md` begründen.
  - `workflowDefaultsApi`, `WorkflowPresetKey`, `GlobalWorkflowMutationResult` aus dem API-Index exportieren.
- **Tests:** MCP-Tool-Smoke, Manifest-Drift, Frontend-Import/Typecheck.
- **DoD:** Kein Deep-Import nötig; MCP/REST-Verhalten deckungsgleich oder dokumentiert.

### P1.9 — Document und WorkItem in generische Transitionstypen aufnehmen

- **Priorität:** Major · **Größe:** L · **Risiko:** hoch
- **Betrifft:** M-13
- **Dateien:** `frontend/src/api/workflow-transitions.ts`, `frontend/src/api/workflows.ts`, `frontend/src/api/documents.ts`, `backend/rest_api/views_entity_core.py`, `backend/mcp_server/tools/document.py`, `work_items.py`
- **Umsetzung:** Prüfen, ob die generischen `/{resource}/{id}/transitions/`-Routen Document und WorkItem bereits bedienen. Wenn ja, Union und Ressourcen-Mapping ergänzen und Spezialwrapper darauf zurückführen. Wenn nein, typisierte Endpunkte oder dokumentierte Ausnahme festlegen; keine stillschweigende Lücke.
- **Tests:** Transition über REST und MCP für beide Typen; ungültige Transition; Frontend-Typecheck.
- **DoD:** Ein konsistenter Transition-Vertrag oder eine explizit begründete, getestete Ausnahme.

### P1.10 — Soft-Delete-Parameter vereinheitlichen

- **Priorität:** Major · **Größe:** M · **Risiko:** mittel
- **Betrifft:** M-14
- **Dateien:** `backend/mcp_server/tools/document.py`, `work_items.py`, weitere `*_outdate`/`*_reactivate`-Tools, `frontend/src/api/documents.ts`, Tool-Dokumentation
- **Umsetzung:** `change_reason` als kanonischen Parameter einführen. `reason` für mindestens ein Release als Deprecated-Alias akzeptieren. Reactivate konsistent prüfen.
- **Tests:** beide Parameternamen; Vorrang bei gleichzeitiger Angabe; Audit-Trail enthält den Grund.
- **DoD:** Kein 500er und keine widersprüchliche Audit-Semantik.

### P1.11 — `document.query` filtert `uid` serverseitig

- **Priorität:** Major · **Größe:** S · **Risiko:** niedrig
- **Betrifft:** M-15
- **Dateien:** `backend/mcp_server/tools/document.py`, `backend/application/document_service.py`, `backend/mcp_server/tests/`
- **Umsetzung:** `uid` an den Service bzw. die Datenbankabfrage durchreichen; clientseitige Nachfilterung entfernen.
- **Tests:** exakter Treffer, unbekannte UID, RLS-/Workspace-Isolation, `include_outdated`-Kombination.
- **DoD:** Kein vollständiges Laden aller Dokumente für einen UID-Filter.

### P1.12 — MCP-Handler loggen maskierte Fehler

- **Priorität:** Major · **Größe:** M · **Risiko:** mittel
- **Betrifft:** M-16
- **Dateien:** `backend/mcp_server/tools/document.py`, `work_items.py`, `requirements.py` und weitere Handler
- **Umsetzung:** Unerwartete Exceptions vor der maskierten Client-Antwort mit `logger.exception` protokollieren. Erwartete Validierungsfehler weiterhin knapp und ohne Traceback behandeln. Keine Secrets, Tokens, Bodies oder PII loggen.
- **Tests:** Exception erzeugt Logeintrag; Response bleibt maskiert; Secret wird nicht geloggt.
- **DoD:** Diagnose möglich, ohne interne Details an Clients zu leaken.

### P2.1 — `include_deleted` und `include_outdated` harmonisieren

- **Priorität:** Minor · **Größe:** S · **Risiko:** niedrig
- **Betrifft:** m-8
- **Dateien:** REST-Views, MCP-Document-Tools, `frontend/src/api/documents.ts`
- **Umsetzung:** `include_outdated` kanonisch; `include_deleted` als Alias befristet beibehalten.
- **Tests:** beide Namen, kombinierte Filter, Deprecation-Hinweis.
- **DoD:** Keine gemischte Semantik in neuen Aufrufen.

### P2.2 — Document-Serialisierung deduplizieren

- **Priorität:** Minor · **Größe:** S · **Risiko:** niedrig
- **Betrifft:** m-4
- **Dateien:** `backend/rest_api/views_entity_core.py`, `backend/mcp_server/tools/document.py`, gemeinsamer Service-/Serializer-Helper
- **Umsetzung:** Eine gemeinsame kanonische Document-Darstellung extrahieren; REST und MCP konsumieren sie.
- **Tests:** Paritätsvergleich REST/MCP für dieselben Dokumente.
- **DoD:** Keine doppelte Status-/Datumsformatierung.

### P2.3 — WorkflowTransitionResult konsolidieren

- **Priorität:** Minor · **Größe:** S · **Risiko:** niedrig
- **Betrifft:** m-7
- **Dateien:** `frontend/src/api/workflows.ts`, `workflow-transitions.ts`, `documents.ts`, zentraler Typ
- **Umsetzung:** Gemeinsames Basis-Interface definieren; spezifische Results erweitern es.
- **Tests:** Typecheck und bestehende Transition-Tests.
- **DoD:** Ein kanonischer Typ, keine strukturellen Kopien.

### P2.4 — WorkflowEditorPage in Scope-Container aufteilen

- **Priorität:** Minor · **Größe:** M · **Risiko:** mittel
- **Betrifft:** m-5
- **Dateien:** `frontend/src/components/WorkflowEditor/WorkflowEditorPage.tsx`, neue Wrapper/Hooks
- **Umsetzung:** Workspace- und Global-Scope in getrennte Container oder mindestens scope-spezifische Wrapper trennen; gemeinsamen Editor unverändert nutzen.
- **Tests:** beide Routen, Scope-Wechsel, Fehler-/Leerzustände.
- **DoD:** Seite enthält keine doppelte Scope-Fachlogik; Tests bleiben grün.

### P2.5 — `useWorkflowMutations` entduplizieren

- **Priorität:** Minor · **Größe:** S · **Risiko:** niedrig
- **Betrifft:** m-9
- **Dateien:** `frontend/src/components/WorkflowEditor/useWorkflowMutations.ts`
- **Umsetzung:** Internen Dispatcher für Workspace/Global einführen; Verhalten und Fehlermeldungen unverändert.
- **Tests:** bestehende Mutationstests, beide Scopes.
- **DoD:** Keine funktionale Änderung, weniger Verzweigungsduplikate.

### P2.6 — Workspace-`setStateFreeze` bereinigen

- **Priorität:** Minor · **Größe:** XS · **Risiko:** niedrig
- **Betrifft:** m-10
- **Dateien:** `frontend/src/components/WorkflowEditor/useWorkflowMutations.ts`, Aufrufer
- **Umsetzung:** Toten No-Op entfernen oder explizit als nicht unterstützt typisieren, statt still `false` zurückzugeben.
- **Tests:** Workspace-Editor bietet die Aktion nicht an; Global-Editor funktioniert.
- **DoD:** Kein stiller No-Op mehr.

### P2.7 — Workflow-Definition-Cache threadsicher machen

- **Priorität:** Minor · **Größe:** S · **Risiko:** mittel
- **Betrifft:** m-11
- **Dateien:** `backend/workflow/transition_validator.py`
- **Umsetzung:** Cache-Zugriffe mit Lock schützen oder auf eine threadsichere, begrenzte Struktur wechseln.
- **Tests:** paralleler Zugriff ohne Race; Cache-Invalidierung.
- **DoD:** Concurrency-Test grün, kein globaler Performanceeinbruch.

### P2.8 — WorkItem-MCP um Soft-Delete/Restore ergänzen

- **Priorität:** Minor · **Größe:** M · **Risiko:** mittel
- **Betrifft:** m-13
- **Dateien:** `backend/mcp_server/tools/work_items.py`, `docs/agent-templates/tool-manifest.json`, `backend/mcp_server/tests/entity_surface_matrix.py`
- **Umsetzung:** `work_item.outdate` und `work_item.reactivate` mit derselben Semantik wie REST ergänzen.
- **Tests:** Outdate/Reactivate, Audit-Grund, Manifest-Drift, Entity-Surface-Parität.
- **DoD:** WorkItem ist auf REST- und MCP-Seite lifecycle-vollständig.

### P2.9 — Sichere Header-Defaults dokumentieren und prüfen

- **Priorität:** Minor · **Größe:** S · **Risiko:** niedrig
- **Betrifft:** m-14
- **Dateien:** `.env.example`, `deploy/.env.example`, `backend/reqogniloom/settings.py`, Security-Checkliste
- **Umsetzung:** Produktions-Checkliste mit `SECURE_SSL_REDIRECT`, HSTS, Cookie-Flags und CSP; Dev-Ausnahmen klar getrennt.
- **Tests:** Production-Check schlägt bei fehlenden TLS-Headern fehl; Dev bleibt startbar.
- **DoD:** Keine sicheren Pflichtwerte mehr nur als Kommentar.

### P2.10 — `DocumentViewSet.transitions` Fehler sauber behandeln

- **Priorität:** Minor · **Größe:** S · **Risiko:** niedrig
- **Betrifft:** m-15
- **Dateien:** `backend/rest_api/views_entity_core.py`, Tests
- **Umsetzung:** Nur erwartete Fehler fangen; unerwartete loggen und als konsistenten 5xx-Fehler zurückgeben.
- **Tests:** Permission-Fehler, Not-Found, unerwartete Exception.
- **DoD:** Keine verschluckten Fehler.

### P2.11 — `reviews`-Listen-`operationId` korrigieren

- **Priorität:** Minor · **Größe:** XS · **Risiko:** niedrig
- **Betrifft:** m-3
- **Dateien:** `backend/rest_api/review_views.py`, `openapi_contract_snapshot.json`
- **Umsetzung:** List-Operation erhält `reviews_list`; Snapshot nach Schema-Regeneration aktualisieren.
- **Tests:** OpenAPI-Contract-Snapshot, Schema-Generierung.
- **DoD:** Kein irreführendes `reviews_retrieve` für eine Liste.

### P2.12 — `DocumentReadingViewProps.onEdit` optional machen

- **Priorität:** Minor · **Größe:** XS · **Risiko:** niedrig
- **Betrifft:** m-6
- **Dateien:** `frontend/src/components/Documents/DocumentReadingView.tsx`, Tests
- **Umsetzung:** Callback optional typisieren und nur rendern, wenn vorhanden.
- **Tests:** Read-Modus ohne Handler; Edit-Modus mit Handler.
- **DoD:** Keine No-Op-Handler für reine Leser nötig.

### P2.13 — Workflow-Initialisierungsfehler nicht verschlucken

- **Priorität:** Minor · **Größe:** M · **Risiko:** mittel
- **Betrifft:** m-12
- **Dateien:** `backend/application/document_service.py`, `backend/application/work_item_service.py`
- **Umsetzung:** Fehler bei der Workflow-Initialisierung als harten Fehler behandeln oder mindestens mit Fehlermetrik und klarer Teilzustands-Semantik eskalieren. Kein stilles Warning-only.
- **Tests:** Create mit fehlschlagender Workflow-Initialisierung; Transaktions-/Konsistenzverhalten.
- **DoD:** Kein Artefakt ohne Workflow-State, ohne dass der Fehler sichtbar wird.

## 8. Abhängigkeiten und Ausführungsreihenfolge

### Welle 0 — Sofort

1. P0.1 OpenAPI-Blocker.
2. P0.2 Befund-Inventar.
3. P1.1 Produktionskonfiguration.
4. P1.2 MCP-Scope fail-closed.
5. P1.3 API-Key-Pepper.

### Welle 1 — Vertragskorrekturen

1. P1.4, P1.5, P1.6, P1.7.
2. P1.11, P1.12.
3. Snapshot-Gates nach P0.1/P1.4/P1.6 ausführen.

### Welle 2 — REST/MCP-Parität

1. P1.8 globale Workflow-Defaults und Frontend-Export.
2. P1.9 Transitionstypen.
3. P1.10 Soft-Delete-Parameter.
4. P2.8 WorkItem-Soft-Delete.

### Welle 3 — Minor und Tech-Debt

P2.1–P2.7 sowie P2.9–P2.13, jeweils nach den abhängigen Major-Paketen.

### Welle 4 — Gesamtverifikation

1. OpenAPI generieren und Contract-Snapshot prüfen.
2. Tool-Manifest und Entity-Surface-Parität prüfen.
3. Backend- und Frontend-Suiten.
4. Security-Scan und `git diff --check`.
5. Abschlussreview durch Backend, Security und Code-Review.

## 9. Test- und Gate-Matrix

| Bereich | Gate |
|---|---|
| OpenAPI | Schema-Generierung, `test_openapi_contract_snapshot.py`, neue ViewSet-Schema-Tests |
| MCP | `test_tool_manifest_drift.py`, `test_entity_surface_parity.py`, `test_mcp_workspace_scope.py` |
| Workflow | `backend/workflow/tests/`, `frontend/src/api/workflows.test.ts` |
| Dokumente | `backend/rest_api/tests/test_document_views.py`, `backend/application/tests/test_document_reading_service.py`, `frontend/src/test/DocumentsView.test.tsx`, `frontend/src/test/DocumentReadingView.test.tsx` |
| Security | Production-Settings-Checks, Auth-/API-Key-Tests, Secret-Scan |
| Frontend | `npm test`, `npm run typecheck`, ESLint |
| Gesamt | fokussierte Läufe zuerst, danach vollständige Backend-/Frontend-Suiten; keine Regression |

## 10. Branch- und Commit-Strategie

**Empfohlener Sammelbranch:** `fix/rest-mcp-review-findings`, abgezweigt nach Abschluss des aktuellen Dokument-/Workflow-Branches.

Alternativ vier parallele Branches:

| Branch | Pakete |
|---|---|
| `security/rest-mcp-hardening` | P1.1–P1.3 |
| `fix/rest-mcp-contracts` | P0.1, P1.4–P1.7, P1.11, P1.12 |
| `feat/rest-mcp-parity` | P1.8–P1.10, P2.8 |
| `refactor/rest-mcp-minor` | P2.1–P2.7, P2.9–P2.13 |

**Commit-Reihenfolge im Sammelbranch:**

1. `fix(rest_api): document workflow definition endpoints`
2. `security(config): harden production defaults and secrets`
3. `fix(mcp): enforce fail-closed workspace scope`
4. `security(auth): require api key pepper in production`
5. `fix(rest_api): align workflow and document contracts`
6. `feat(mcp): expose global workflow defaults`
7. `fix(rest_api,mcp): align transitions and soft-delete semantics`
8. `fix(mcp): improve document filtering and error logging`
9. `refactor(rest_api,mcp,frontend): resolve review minor findings`
10. `docs: document rest mcp review remediation`

## 11. Risiken und Gegenmaßnahmen

| Risiko | Auswirkung | Gegenmaßnahme |
|---|---|---|
| Fail-closed MCP-Scope bricht bestehende Clients | hoch | Übergangsphase mit klarer Fehlermeldung, Release-Note, Tests aller Manifest-Tools |
| OpenAPI-Snapshot ändert sich breit | mittel | Schema-Diff reviewen; nur beabsichtigte Operationen aktualisieren |
| Secret-Rotation unterbricht laufende Sessions | hoch | Rotationsrunbook, koordinierter Neustart, Rollback-Werte außerhalb des Repos |
| Parameter-Aliasse bleiben zu lange | mittel | Deprecation-Frist und Entfernungs-Issue dokumentieren |
| Frontend-Typänderungen brechen Consumer | mittel | Zentraler Export, Typecheck, schrittweise Migration |
| Zu große Sammeländerung | mittel | Ein Commit pro Paket; Reviews pro Welle |

## 12. Aufwand und Freigabe

- **Grobe Schätzung:** 22–32 Personentage für Umsetzung, Tests und Reviews.
- **Bei einem Entwickler:** ca. 5–7 Kalenderwochen.
- **Bei zwei parallelen Strängen:** ca. 3–4 Kalenderwochen.
- **Freigabe:** Der Plan ist umsetzungsbereit, sobald P0.2 die Zählabweichung geschlossen hat und die Secret-Rotation als operativer Schritt bestätigt ist.

## 13. Definition of Done für das Gesamtvorhaben

- [ ] Alle 32 belegten Befunde sind einem Paket zugeordnet und geschlossen; die drei im Aggregat zusätzlich gezählten, unbelegten Minor-Positionen sind als Zählfehler dokumentiert (siehe P0.2-Nachtrag) und nicht umzusetzen.
- [ ] Kein offener Blocker oder Major-Befund.
- [ ] OpenAPI, Tool-Manifest und Entity-Surface-Parität sind konsistent.
- [ ] REST und MCP verwenden für gleiche Operationen gleiche Parameter und Fehlercodes.
- [ ] Produktionskonfiguration ist ohne explizite Secrets nicht startfähig.
- [ ] Backend- und Frontend-Suiten sowie Typecheck/Lint sind grün.
- [ ] `git diff --check` ist sauber und der Secret-Scan findet keine neuen Secrets.
- [ ] Reviews von Backend, Security und Code sind APPROVED.
