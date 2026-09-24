---
type: REVIEW
scope: system-audit-2026-09
status: final
date: 2026-09-24
author_agent: api-specialist
---

# Systemaudit 2026-09 — API-/UI-/Datenmodell-Vertragsdrift

**Revisionsstand:** `66e21f56`  
**Branch:** `feat/1031-bluepencil-host-bridge`  
**Auditdatum:** 2026-09-24  
**Scope:** REST-API (`/api/v1/`), MCP-Tool-Adapter, React-Frontend, ORM-/Application-Services und ausgewählte Cross-Adapter-Pfade.  
**Nicht im Scope:** Implementierung von Fixes, allgemeine Test-Coverage, CVE-/SBOM-Prüfung, Cloud-IAM und Performance-Audit.

## 1. Management-Summary

Die Adapter sind nicht vollständig veraltet, aber die Verträge sind an mehreren Grenzen nicht mehr deckungsgleich. Die höchste Risikoklasse entsteht nicht durch einzelne Tippfehler, sondern durch unterschiedliche, jeweils plausibel aussehende Quellen für dieselbe fachliche Eigenschaft:

- `Workspace.language` wird im Service in `Workspace.preset` geschrieben, während ORM-/AI-/MCP-/Memory-Pfade teils die eigene Spalte lesen.
- API-Keys können serverseitig sicher eingeschränkt werden, der UI-Wrapper bietet diese Felder jedoch nicht an und erzeugt damit den historischen Admin-/Unfenced-Default.
- Die MCP-Beschreibung verspricht Multi-Interview-Formalize, das MCP-Schema und der Handler übergeben aber keine bestätigte Proposal.
- Die generierte OpenAPI-Dokumentation ist für mehrere aktive Aktionen nicht ausführbar: 437 Operationen enthalten nur 3 explizite `400`- und 1 `401`-Antwort, während Interview-/TestRun-Aktionen teilweise keinen Request- oder Response-Schema haben.
- TraceLink-CRUD-Operationen werden generiert, obwohl Detail-GET immer 404 und PATCH immer 405 liefert.

**Befundverteilung:** 0× P0, 4× P1, 5× P2, 1× P3.  
**Gesamtbewertung:** Der primäre REST-Produktpfad ist funktionsfähig, aber die veröffentlichte Vertrags- und Sicherheitssemantik ist nicht zuverlässig genug, um als alleinige Integrationsquelle für externe Clients oder AI-Agenten verwendet zu werden.

### Befundübersicht

| ID | Schwere | Status | Kurzfassung | Confidence |
|---|---|---|---|---|
| CD-001 | P2 | bestätigt | Runtime-Fehlerdetails können ein Objekt sein; OpenAPI/Frontend verlangen ein Array. | Hoch |
| CD-002 | P1 | bestätigt | OpenAPI-Aktionen für Interview und TestRun haben falsche oder fehlende Schemas; Fehleroperationen fehlen fast vollständig. | Hoch |
| CD-003 | P1 | bestätigt | Workspace-Sprache wird zwischen JSON-Blob und ORM-Spalte aufgespalten. | Hoch |
| CD-004 | P1 | bestätigt | API-Key-UI erzeugt standardmäßig Admin-/Unfenced-/unbefristete Keys. | Hoch |
| CD-005 | P1 | bestätigt | MCP `interview.formalize` kann Multi-Sessions mangels `confirmed_proposal` nicht abschließen. | Hoch |
| CD-006 | P2 | bestätigt | TraceLink OpenAPI verspricht GET/PATCH, die Runtime liefert 404/405. | Hoch |
| CD-007 | P2 | bestätigt | TestRun-Ergebnis-Response und Frontend-Typen bilden zwei verschiedene Teilverträge ab. | Hoch |
| CD-008 | P2 | bestätigt | ChangeRequest-Lifecycle ist im Backend vorhanden, im Frontend nur als Create-Shortcut erreichbar. | Mittel |
| CD-009 | P2 | bestätigt | Optimistic-Concurrency ist nur im Requirement-Editor durchgängig verdrahtet. | Hoch |
| CD-010 | P3 | bestätigt | `VerificationMethod` und einige Request-Typen sind hinter dem Backend zurückgeblieben. | Hoch |

### Positive Kontrollen

- Das MCP-Manifest und die Live-Registry stimmen für 218 Tools, 35 Präfixe, Write-Klassifikation, Beschreibungen und Input-Schemata überein (`backend/mcp_server/tests/test_tool_manifest_drift.py:83-157`; `docs/agent-templates/tool-manifest.json:2-4`).
- API-Key unbekannte Felder werden serverseitig nicht stillschweigend ignoriert (`backend/rest_api/tests/test_readonly_and_unknown_field_rejection_915_916.py:238-260`).
- Requirement- und TestCase-ETag/`If-Match`- sowie `expected_version`-Pfade sind serverseitig mit echten DB-Integrationstests abgesichert (`backend/rest_api/tests/test_etag_optimistic_locking_868.py:1-17`; `backend/rest_api/tests/test_optimistic_locking.py:1-17`).
- Workspace-Preset-Legacyformen werden beim Lesen normalisiert (`backend/rest_api/tests/test_workspace_preset_normalization.py:43-100`); der Frontend-Kontext besitzt dafür aktuell einen expliziten Normalisierungsadapter (`frontend/src/context/WorkspaceContext.tsx:63-87`).
- Die gezielten Frontend-Tests `interviews`, `ApiKeysSection` und `requirements-etag` liefen erfolgreich (3 Dateien, 19 Tests). Der Frontend-Build lief erfolgreich; die dabei erzeugten Änderungen unter `frontend/dist/**` wurden anschließend zurückgesetzt.

## 2. Methodik und Evidenzregeln

### 2.1 Vorgehen

1. REST-Routen, Serializer, View-/Action-Methoden und ORM-Modelle gelesen.
2. Frontend-API-Wrapper, Domain-Typen und die tatsächlich aufrufenden UI-Komponenten abgeglichen.
3. MCP-Tool-Schemas und Handler gegen die Application-Service-Signatur geprüft.
4. `drf-spectacular` mit `DJANGO_SETTINGS_MODULE=reqogniloom.settings_test` und `SchemaGenerator().get_schema(request=None, public=True)` ausgeführt.
5. Vorhandene Regressionstests als Beleg, nicht als Ersatz für einen Contract-Test verwendet.

Die Schema-Erzeugung wurde read-only ausgeführt. Der Generator meldete u. a. nicht auflösbare Authenticator- und Serializer-Typen sowie untypisierte Pfadparameter. Die konkrete Ausgabe zeigte unter anderem:

- 437 Operationen;
- nur 3 Operationen mit explizitem `400`, 1 mit `401`, 6 mit `404` und 1 mit einer Fehler-Schema-Referenz;
- `/api/v1/interviews/{id}/formalize/`: kein Request-Body und `200` mit „No response body“;
- `/api/v1/test-runs/{id}/results/`: Request `TestRunRequest`, Response `TestRun` statt Result-Serializer;
- `/api/v1/test-runs/{id}/results/bulk/`: Request und Response ebenfalls auf `TestRun`/`TestRunRequest` abgebildet;
- `/api/v1/tracelinks/{id}/`: generiert `GET` und `PATCH` mit `200 TraceLink`.

### 2.2 Tatsache versus Hypothese

- **Tatsache:** direkt aus aktuellem Quelltext, generiertem Schema, Test oder Route ersichtlich.
- **Hypothese/Risiko:** mögliche Auswirkung der belegten Abweichung; kein behaupteter Produktionsschaden ohne Runtime-Beleg.
- **Confidence:** Vertrauen in Ursache und Auswirkungskette, nicht in die Schwere allein.
- Historische Berichte wurden als Kontext gelesen, aber nicht ungeprüft als aktueller Befund übernommen.

### 2.3 Schweregrade

- **P0:** Systemweiter Ausfall oder unmittelbarer schwerwiegender Daten-/Security-Schaden.
- **P1:** Wesentliche Korrektheits-, Security- oder Integrationsauswirkung auf einem aktiven Standardpfad.
- **P2:** Materielle, aber begrenzte Vertrags-, Zuverlässigkeits- oder Abdeckungslücke.
- **P3:** Lokale, geringe Auswirkung.

### 2.4 Prüfgrenzen

- Backend-DB-Tests konnten in dieser Umgebung nicht vollständig ausgeführt werden, weil der PostgreSQL-Host `postgres` nicht erreichbar war. Schema- und statische Befunde sind davon unabhängig.
- Der Standard-`pytest`-Aufruf war unter Windows zunächst durch ein automatisch geladenes Plugin mit `fcntl`-Bezug blockiert. Das ist eine Testumgebungsgrenze, kein API-Befund.
- ProjectAtlas meldete `refresh_required`; der Index wurde nicht verändert, um den Audit nicht über einen Cache-/Infra-Schreibvorgang zu erweitern.
- Es wurden keine Secrets, `.env`-Dateien oder Rohantworten mit Zugangsdaten ausgegeben.

## 3. Vertragskarte

| Grenze | Primärer Vertrag | Abweichung |
|---|---|---|
| Workspace → REST | `WorkspaceSerializer`/`WorkspaceViewSet` | `preset` wird als Objekt serialisiert, Frontend-Typ deklariert String. |
| Workspace → AI/MCP/Memory | `Workspace.language` | Service schreibt primär in `preset.language`; Spalte bleibt auf Model-Default `en`. |
| API-Key → UI | `ApiKeyViewSet` | Backend akzeptiert Scope/Fence/Expiry; UI sendet nur `name`. |
| Interview → REST | `InterviewViewSet.formalize` | `confirmed_proposal` wird korrekt weitergereicht. |
| Interview → MCP | `interview.formalize` | Schema/Handler kennen nur `session_id`; Multi-Proposal fehlt. |
| TestRun → REST/UI | `TestRunResultSerializer` | REST liefert verschachtelte Spec-Felder; UI typisiert nur Legacy-Felder. |
| TraceLink → REST/OpenAPI | `TraceLinkViewSet` | ID-Raum wird in einem List-Zweig bewusst echoed; Detail-GET/PATCH sind nicht implementiert. |
| ChangeRequest → UI | `ChangeRequestViewSet` | Vollständiger Backend-Lifecycle, nur Create-Shortcut im Frontend. |

### 3.1 Interface- und QoS-Verträge

| Quelle → Ziel | Protokoll/Auth | Datenvertrag | QoS-/Verfügbarkeitsangabe |
|---|---|---|---|
| Browser → REST `/api/v1/` | HTTP/JSON; HttpOnly-Cookie bzw. Bearer/JWT | DTOs, Pagination- und Fehler-Envelope; Action-Responses sind nicht vollständig typisiert | Für die geprüften Endpunkte ist kein verbindlicher Latenz-, Durchsatz- oder Verfügbarkeits-SLO im API-Vertrag hinterlegt. |
| MCP-Client → MCP-Server | JSON-RPC 2.0 über HTTP/SSE; API-Key/Bearer | Manifest- und Tool-spezifische Input-Schemata; fachliche Parität zum Application-Service ist nicht automatisiert geprüft | Rate-/Session-Grenzen existieren, ein einheitlicher Latenz-/Durchsatz-/Verfügbarkeitsvertrag ist nicht Teil des publizierten Manifests. |
| REST/MCP → Application-Service | Interner Service-Aufruf mit `AuthContext`/`TenantContext` | Python-DTOs und Service-Exceptions; Statuscode- und Fehler-Mapping liegt im Adapter | Transaktions- und Tenant-Grenzen sind serverseitig definiert; ein Ende-zu-Ende-SLO ist nicht dokumentiert. |
| Frontend-Typen → REST | TypeScript-Statik ohne Runtime-Schema-Validierung | Handgepflegte `frontend/src/types/index.ts` und API-Wrapper | Compile-Zeit schützt nur bekannte Felder; unbekannte Runtime-Abweichungen werden nicht zuverlässig abgewiesen. |

## 4. Befunde

### CD-001 — Fehlerdetails: Runtime-Objekt versus Arrayvertrag

**Schwere:** P2  
**Status:** bestätigt  
**Confidence:** Hoch

**Tatsache**

- Der globale DRF-Exception-Handler setzt `details` auf das unveränderte `response.data`: `backend/rest_api/error_envelope.py:18-37`. Bei einer `ValidationError({"title": [...]})` ist dieses Ergebnis ein Dictionary; der Regressionstest erwartet genau diesen Fall in `backend/rest_api/tests/test_error_envelope.py:30-38`.
- Der OpenAPI-Errorvertrag definiert `details` als Liste von `ErrorDetailSerializer`: `backend/rest_api/openapi.py:43-64`.
- Das Frontend typisiert denselben Wert als `ApiErrorDetail[]`: `frontend/src/types/index.ts:699-709`.
- Die UI-Fehlerzuordnung prüft ausdrücklich `Array.isArray(details)` und fällt nur dann auf die bereits abgeflachte Message zurück: `frontend/src/components/shared/ArtifactForm/field-errors.ts:41-77`.

**Auswirkung**

Ein nicht vorab normalisierter DRF-Fehler kann die strukturierten Feldfehler im Frontend verlieren. Der Benutzer sieht dann nur `error.message` oder einen unspezifischen Formularfehler; bei einem generischen Message-Text ist die Zuordnung zum fehlerhaften Feld nicht mehr möglich. OpenAPI-Validatoren und TypeScript-Consumenten akzeptieren die tatsächliche Antwort außerdem nicht als den veröffentlichten Vertrag.

**Root Cause**

Es existieren zwei bewusst bzw. historisch unterschiedliche Fehlerrepräsentationen: `build_error_response(...)` erzeugt standardmäßig eine Liste, der globale Exception-Handler reicht dagegen beliebige DRF-Daten unverändert weiter. Es gibt keine Normalisierungsgrenze zwischen Handler und Schema.

**Gegenmaßnahme**

- Eine kanonische interne Fehlerstruktur festlegen und alle Handler auf `details: list[ErrorDetail]` normalisieren.
- Für Nicht-Validierungsfehler eine leere Liste oder ein bewusst typisiertes `meta`-Feld verwenden; keine ungeprüften beliebigen Dictionaries nach außen geben.
- `build_error_response`, den globalen Handler und die OpenAPI-Serializer gemeinsam testen.
- Frontend defensiv auf Array und Objekt behandeln, bis die API major-versioniert umgestellt ist.

**Alternativen**

- Nur den OpenAPI-Schema-Shape erweitern: schwächt die maschinenlesbare Feldfehler-API und wird abgelehnt.
- Das Feld `details` entfernen: Breaking Change und Verlust strukturierter Fehlerdiagnostik; nicht empfohlen.

**Verifikation**

Ein Test mit einer nativen `ValidationError`, einer nicht validierten `NotFound` und einer expliziten `build_error_response`-Antwort muss für alle drei denselben maschinenlesbaren Vertrag liefern. Der Frontend-Test muss beide Representations bis zur API-Umstellung korrekt behandeln.

### CD-002 — Generiertes OpenAPI ist für aktive Aktionen nicht ausführbar

**Schwere:** P1  
**Status:** bestätigt  
**Confidence:** Hoch

**Tatsache**

Die read-only Schema-Erzeugung mit `SchemaGenerator` ergab 437 Operationen, aber nur 3 explizite `400`-Antworten, 1 `401`, 6 `404` und 1 Operation mit einer Fehler-Schema-Referenz. `COMMON_ERROR_RESPONSES` ist in `backend/rest_api/openapi.py:68-98` definiert, wird aber nicht als globale Operation-Deklaration verwendet; die Repository-Suche findet außerhalb der Definition und `backend/rest_api/tests/test_openapi.py` keine Verwendung.

Konkrete Ausgaben:

- `GET/POST /api/v1/interviews/{id}/propose/` bzw. `.../formalize/`: kein Request-Body und `200` „No response body“.
- `GET/POST /api/v1/test-runs/{id}/results/`: Request-Schema `TestRunRequest`, Response-Schema `TestRun`; die tatsächliche GET-Antwort ist eine Liste von Result-DTOs und die POST-Antwort ein Result-DTO.
- `POST /api/v1/test-runs/{id}/results/bulk/`: Request-Schema `TestRunRequest` statt `TestRunResultBulkSerializer`, Response-Schema `TestRun` statt `{results, count}`.
- Mehrere UUID-Pfadparameter werden als untypisierte `string` generiert, u. a. für TestRun, TestCase und TraceLink.

Die vorhandenen OpenAPI-Tests prüfen Serializer-Deklarationen und einige selektive Query-Parameter, aber nicht die oben genannten Action-Operationen (`backend/rest_api/tests/test_openapi.py:19-112`).

**Auswirkung**

Ein aus dem OpenAPI-Dokument generierter Client oder Contract-Validator kann TestRun-Ergebnisse falsch serialisieren, Interview-Multi-Formalize ohne Body aufrufen und Fehler nicht korrekt behandeln. Das Dokument ist damit keine verlässliche Integrationsquelle, obwohl die Routen produktiv erreichbar sind.

**Root Cause**

Die View-Methoden validieren und serialisieren manuell, geben aber für die Action-Methoden keine `request`/`responses`-Metadaten an. `serializer_class = TestRunSerializer` beschreibt nur die CRUD-Ressource, nicht die abweichenden Result-Action-Verträge.

**Gegenmaßnahme**

- Für jede Action `@extend_schema` mit explizitem Request-/Response-Serializer und `COMMON_ERROR_RESPONSES` ergänzen.
- Für `results`, `results/bulk`, `formalize`, `propose` und vergleichbare Aktionen eigene Schema-Komponenten definieren.
- UUID-Pfadparameter explizit als UUID typisieren.
- Einen Schema-Snapshot- oder Contract-Test einführen, der jede ausgewählte Operation gegen Request- und Response-Serializer prüft.
- Die globale Fehlerregistrierung nur über einen tatsächlich wirksamen Hook verwenden; die ungenutzte Konstante nicht als Schutz dokumentieren.

**Alternativen**

- `APIView` statt `ViewSet` für alle Actions: größere Umbauten mit höherem Regressionsrisiko.
- Nur die Dokumentation entfernen: verschlechtert die Auffindbarkeit und beseitigt die Drift nicht.

**Verifikation**

Nach jeder Generierung müssen die ausgewählten Pfade maschinell auf Request-Body, Success-Schema, Statuscodes und Fehler-Schemata geprüft werden. Der Test muss zusätzlich prüfen, dass jede generierte Operation tatsächlich eine erreichbare View-Methode mit demselben Vertrag besitzt.

### CD-003 — Workspace-Sprache wird zwischen zwei Quellen aufgespalten

**Schwere:** P1  
**Status:** bestätigt  
**Confidence:** Hoch

**Tatsache**

- `Workspace` besitzt sowohl `preset = JSONField` als auch `language = CharField(default="en")`: `backend/persistence/models.py:719-760`.
- Migration `backend/persistence/migrations/0036_workspace_language.py:1-27` sagt ausdrücklich, dass die Spalte eingeführt wurde, nachdem die Sprache zuvor nur im JSON-Blob lag; für bestehende Zeilen wurde kein Backfill durchgeführt.
- `WorkspaceService.create_workspace` schreibt `language` in `preset` (`{"tier", "terminology_profile", "language"}`), legt aber `Workspace.language` nicht explizit fest: `backend/application/workspace_service.py:171-177,221-273`.
- `update_metadata` schreibt eine PATCH-Sprache ebenfalls nur in `preset["language"]`: `backend/application/workspace_service.py:639-748`.
- `_workspace_to_dict` liest für REST/MCP-nahe Workspace-Ausgabe `language` aus dem Blob und nicht aus der ORM-Spalte: `backend/rest_api/views.py:4895-4932`.
- Gleichzeitig lesen `AiDerivationService` die Spalte über `Workspace.language` (`backend/application/ai_derivation_service.py:84-96,1731-1749`), der MCP-Admin-Adapter ebenfalls (`backend/mcp_server/tools/admin.py:342-356`) und Memory-Tasks ebenfalls (`backend/memory/tasks.py:131-145`).
- Der Serializer dokumentiert noch immer, `language` sei „reserved“ und habe keine dedizierte Spalte: `backend/rest_api/serializers.py:1686-1694`; die Modellstruktur widerspricht dieser Beschreibung.

**Auswirkung**

Ein REST- oder UI-Set auf `de` kann in derselben Workspace-Zeile als `language="de"` im JSON-Blob erscheinen, während AI-Derivation, MCP-Admin und Memory-Kontext weiterhin den Spalten-Default `en` lesen. Sprache wird dann abhängig vom aufrufenden Adapter unterschiedlich interpretiert. Das ist ein fachlicher Cross-Adapter-Drift, kein kosmetischer JSON-Unterschied.

**Root Cause**

Eine Migration hat die dedizierte Spalte eingeführt, aber Service- und Serializer-Dokumentation/Read-/Write-Pfade nicht auf eine einzige Source of Truth umgestellt. Der Read-only-Normalisierungsfix für `preset` konserviert zusätzlich die historische Mehrfachquelle.

**Gegenmaßnahme**

- Eine kanonische persistierte Quelle festlegen, vorzugsweise `Workspace.language`; `preset.language` nur während einer versionierten Übergangsphase als Fallback lesen.
- Create/Update atomar in Spalte und ggf. kompatiblen Blob schreiben und einen Konflikt-/Migrationsplan für Altbestände festlegen.
- Alle Reader auf denselben Service/Projection-Endpunkt umstellen.
- Einen Contract-Test ergänzen: Create/GET/PATCH mit `de`, anschließend AI-/MCP-/Memory-Read im selben Tenant/Workspace.

**Alternativen**

- Nur die Spalte verwenden und den Blob-Key entfernen: wire-breaking für Clients, die `preset.language` lesen; nur mit Major-Version und Migrationsplan.
- Nur den Blob verwenden: Model-Felder und direkte ORM-Leser bleiben irreführend; nicht empfohlen.

**Verifikation**

Ein Integrationstest muss die REST-Antwort, den ORM-Wert und die von AI/MCP/Memory verwendete Sprache vergleichen. Altbestände mit nur `preset.language` und nur `Workspace.language` müssen in einer Testmatrix berücksichtigt werden.

### CD-004 — API-Key-UI erzeugt den fail-open Legacy-Default

**Schwere:** P1  
**Status:** bestätigt  
**Confidence:** Hoch

**Tatsache**

- Das Modell unterstützt `principal_type`, `agent_label`, `scope`, `workspace_ids` und `expires_at`: `backend/auth_tenancy/models.py:144-162`.
- Der Service-Default bleibt `scope="write"`; im Legacy-Modell bedeutet `write` ausdrücklich Admin-Tier: `backend/auth_tenancy/models.py:72-90`; `backend/auth_tenancy/services/authentication.py:561-572`.
- Leere `workspace_ids` bedeutet historisch „kein Workspace-Fence“, `expires_at=None` bedeutet „nie ablaufen“ (`backend/auth_tenancy/models.py:153-162`).
- Die REST-View akzeptiert und validiert alle Felder (`backend/rest_api/api_key_views.py:205-365`), und die Service-Tests pinnen die Defaults explizit (`backend/rest_api/tests/test_api_key_agent_fields.py:45-55`).
- Der Frontend-Client kennt nur `name` und sendet bei Create ausschließlich `{name}`: `frontend/src/api/api-keys.ts:15-45`.
- `ApiKeysSection` bietet nur ein Namensfeld und keine Scope-, Workspace-Fence-, Principal- oder Expiry-Auswahl: `frontend/src/components/UserProfileSettings/ApiKeysSection.tsx:39-82,120-149`.
- Die Create-Response liefert `principal_type`, `agent_label` und `scope`, aber nicht `workspace_ids`/`expires_at`; die List-Response liefert alle Felder: `backend/rest_api/api_key_views.py:355-365`; `backend/auth_tenancy/services/authentication.py:640-658`.

**Auswirkung**

Ein über die UI erstellter Key kann maximalen Legacy-Admin-Scope, alle Workspaces des Owners und unbegrenzte Gültigkeit erhalten. Der Benutzer hat keine Möglichkeit, den sicheren Vertrag zu erzwingen oder die tatsächliche Reichweite nach der Erstellung zu prüfen. Bei einem Tenant-Admin ist der Key damit deutlich mächtiger als ein fachlich benötigter Author-Key.

**Root Cause**

Die UI wurde auf die alte PAT-Metadaten-Oberfläche nachgeführt, nicht auf die Agent-Key-Felder. Die sichere Fähigkeit bleibt im Backend nur optional; ein fehlender Request-Wert fällt auf einen historischen, nicht fail-closed Default zurück.

**Gegenmaßnahme**

- Für neue Keys im UI verpflichtende Felder für `principal_type`, `scope`, `workspace_ids` und `expires_at` anbieten oder einen bewusst dokumentierten sicheren Default explizit anzeigen.
- Den Backend-Default für neue Keys fail-closed ändern und bestehende Legacy-Keys nur über einen versionierten Migrations-/Rotationsplan umstellen.
- Create-Response um die sicherheitsrelevanten Felder ergänzen und die UI nach dem Erstellen/bei List anzeigen.
- Keine Workspace-Fence-Leere als implizite Vollfreigabe in einem AI-Key-Erstellungsdialog verwenden.

**Alternativen**

- Nur UI-Felder ergänzen und Serverdefault unverändert lassen: schützt nur neue UI-Nutzer, nicht API-/MCP-Clients.
- Bestehende Keys ungeändert und ohne Rotationshinweis weiterlaufen lassen: verschlechtert die bereits vorhandene Reichweite; nicht empfohlen.

**Verifikation**

REST- und UI-Integrationstest müssen prüfen, dass ein über die Oberfläche erzeugter Key den ausgewählten Scope, die Workspace-Menge und eine explizite Ablaufzeit tatsächlich speichert. Danach ist ein MCP-Aufruf mit einem read-only/fenced Key gegen dieselbe Ressource zu verifizieren.

### CD-005 — MCP kann Multi-Interview-Formalize nicht ausführen

**Schwere:** P1  
**Status:** bestätigt  
**Confidence:** Hoch

**Tatsache**

- Der Application-Service akzeptiert `confirmed_proposal` und verlangt es für Multi-Sessions: `backend/application/interview_service.py:900-949,1149-1169`.
- REST reicht das Feld weiter: `backend/rest_api/interview_views.py:288-305`; der REST-Multi-Test bestätigt den Erfolg: `backend/rest_api/tests/test_interview_views_multi.py:21-46`.
- Das Frontend sendet `confirmedProposal` und verarbeitet das Multi-Ergebnis, allerdings über einen unsicheren Cast: `frontend/src/api/interviews.ts:200-227`; `frontend/src/components/InterviewWidget/InterviewChatPane.tsx:100-113`.
- Das MCP-Tool beschreibt Multi-Formalize ausdrücklich als caller-confirmed proposal, aber `inputSchema` enthält nur `session_id`: `backend/mcp_server/tools/interview.py:181-202`.
- `_handle_formalize` liest nur `session_id` und ruft `self._service.formalize(auth_context, session_id)` ohne Proposal auf: `backend/mcp_server/tools/interview.py:408-427`.

**Auswirkung**

Ein MCP-Agent kann eine Multi-Session starten, Vorschläge lesen und sie nicht bestätigen/atomar materialisieren. Der Service antwortet für jeden solchen Aufruf mit `confirmed_proposal is required`. Das ist ein direkt sichtbarer Funktionsausfall auf einem publizierten AI-Integrationspfad.

**Root Cause**

REST- und Frontend-Multi-Erweiterung wurden nicht in den MCP-Adapter gespiegelt. Der Manifest-Drift-Test prüft nur, dass MCP-Schema und MCP-Live-Registry identisch sind; die fachliche Parität zum Application-Service ist nicht Teil dieses Tests.

**Gegenmaßnahme**

- `confirmed_proposal` als konditional erforderliches Array im MCP-Schema ergänzen, mit Item-Schema für `type`, `fields` und `links`.
- Den Handler mit dem Proposal-Parameter versehen und die Antwortform (`created` versus `resulting_artifact_ids`) dokumentieren.
- Einen REST/MCP-Paritätstest mit identischer Multi-Proposal-Struktur ergänzen.
- Single-Mode weiterhin ohne Proposal zulassen, damit bestehende MCP-Aufrufe nicht unnötig brechen.

**Alternativen**

- Multi-Mode im MCP explizit deaktivieren und Tool-Beschreibung/Manifest ändern: verhindert falsche Erwartungen, ist aber funktionale Regression.
- Proposal serverseitig automatisch aus dem pending State übernehmen: verändert die Bestätigungs- und Transaktionssemantik und ist ohne explizite Sicherheitsentscheidung nicht empfohlen.

**Verifikation**

Ein MCP-Test muss Multi starten, ein Proposal übergeben, mehrere Artefakte atomar erzeugen und `created` zurückgeben. Ein Negativtest muss fehlende/ungültige Proposals als kontrollierten `VALIDATION_ERROR` behandeln.

### CD-006 — TraceLink-CRUD-Operationen und ID-Raum sind nicht konsistent publiziert

**Schwere:** P2  
**Status:** bestätigt  
**Confidence:** Hoch

**Tatsache**

- Das Modell speichert TraceLink-Endpunkte als Artifact-FKs: `backend/persistence/models.py:1808-1823`.
- Der Service akzeptiert bei Create Artifact-, Requirement- oder ArchitectureElement-IDs und normalisiert sie auf Artifact-IDs: `backend/application/trace_link_service.py:378-420`.
- Die Frontend-Dokumentation beschreibt die zwei disjunkten ID-Räume und den Resolver-Bridge ausdrücklich: `frontend/src/api/artifactRefs.ts:7-23`.
- Im `artifact_id`-Listenzweig echoed der View bewusst die vom Client abgefragte Entity-ID an der nahen Endpoint-Seite zurück: `backend/rest_api/views.py:3024-3040,3041-3085`. Das ist für die bestehende UI-Klassifikation notwendig, aber nicht als OpenAPI-Semantik beschrieben.
- `retrieve` antwortet für jeden `GET /api/v1/tracelinks/{id}/` mit 404, weil kein `get_by_id` existiert: `backend/rest_api/views.py:3127-3130`.
- `partial_update` antwortet immer mit 405, weil TraceLinks unveränderlich sind: `backend/rest_api/views.py:3160-3165`.
- OpenAPI generiert für denselben Pfad trotzdem `GET 200` und `PATCH 200`: generierte Schema-Ausgabe zu `/api/v1/tracelinks/{id}/`.

**Auswirkung**

Externe Clients, die das Schema als CRUD-Vertrag verwenden, erhalten bei Detailabfragen und Updates unerwartete 404/405-Antworten. Die List-Antwort kann außerdem je nach Abfrage-ID einen anderen Endpoint-Schlüssel zurückgeben als das Modell speichert; das ist für die UI beabsichtigt, für generische Konsumenten aber nicht eindeutig.

**Root Cause**

Die ViewSet-Methoden wurden als unveränderliche, listenorientierte Ressource implementiert, während der Router/OpenAPI-Generator die Standard-CRUD-Annahmen des Viewsets beibehält. Die Endpoint-Echo-Semantik ist nur in internen Kommentaren und UI-Helfern dokumentiert.

**Gegenmaßnahme**

- Wenn Detailabruf/PATCH nicht unterstützt werden sollen, die Operationen explizit aus dem OpenAPI-Schema entfernen und die verbleibende List/Create/Delete-Semantik dokumentieren.
- Andernfalls `get_by_id` im Service ergänzen und PATCH entweder implementieren oder als 405 korrekt im Schema ausweisen.
- `source_id`/`target_id` im Schema als Artifact-UUIDs dokumentieren und Entity-ID-Eingang nur für Create als Kompatibilitätsalias beschreiben.
- Den Endpoint-Echo-Zweig als versionierte List-Response-Variante kennzeichnen und mit der `resolve`-Bridge testen.

**Verifikation**

Ein Route-/Schema-Paritätstest muss für jede generierte Operation Statuscode und Response-Schema gegen die View-Methode prüfen. Zusätzlich ist ein Test mit Requirement-Entity-ID, Artifact-ID und gemischter Abfrage erforderlich.

### CD-007 — TestRun-Ergebnisvertrag ist zwischen Server, OpenAPI und UI uneinheitlich

**Schwere:** P2  
**Status:** bestätigt  
**Confidence:** Hoch

**Tatsache**

- `TestRunResultSerializer` akzeptiert `test_case_id` und Choice-Werte `passed|failed|blocked|not_run`: `backend/rest_api/serializers.py:1978-2004`.
- Die GET-Action liefert eine Liste, die POST-Action ein Result-DTO und die Bulk-Action `{results, count}`: `backend/rest_api/views.py:7467-7565`.
- `_test_run_result_to_dict` liefert verschachtelte Spec-Felder `testcase`, `result`, `notes`, `executed_by` zusätzlich zu Legacy-Feldern: `backend/rest_api/views.py:4495-4544`.
- Der Frontend-Typ `TestRunResult` enthält nur Legacy-Felder und markiert `test_case_id` nullable: `frontend/src/types/index.ts:861-871`.
- `testRunsApi.addResult`/`addResultsBulk` akzeptieren `status: string` statt einer Choice-Union: `frontend/src/api/test-runs.ts:46-80`.
- Das Grid nutzt bewusst die Legacy-Felder und sendet `duration_ms` zurück, um Upsert-Datenverlust zu vermeiden: `frontend/src/components/TestRuns/TestRunResultEntryGrid.tsx:203-247`.

**Auswirkung**

Die UI funktioniert auf dem Legacy-Teilvertrag, kann aber die veröffentlichten Spec-Felder nicht typisiert nutzen. Andere Clients, die OpenAPI oder das kanonische Result-DTO verwenden, erhalten ein anderes Modell. Ungültige Statuswerte können TypeScript-Compilation nicht verhindern und werden erst serverseitig mit 400 abgewiesen.

**Root Cause**

Die Serverantwort enthält während einer Rückwärtskompatibilitätsphase zwei Shapes, während Serializer, OpenAPI und Frontend jeweils nur einen Teil als kanonisch behandeln. Die Status-Choice ist im konkreten Grid separat korrekt, aber nicht im gemeinsamen API-Typ verankert.

**Gegenmaßnahme**

- Ein explizites kanonisches `TestRunResultResponse` festlegen und die Legacy-Felder als `deprecated`/additive Kompatibilität dokumentieren.
- Frontend-Typen um `testcase`, `result`, `notes`, `executed_by` und `status`-Union erweitern.
- Request-Typen auf dieselbe Union begrenzen und einen Contract-Test für GET/POST/Bulk verwenden.
- Entscheiden, ob die verschachtelten Felder dauerhaft Teil des Vertrags bleiben; Entfernen wäre eine Breaking Change und benötigt Versionierung.

**Verifikation**

Ein Test vergleicht die drei HTTP-Antworten mit `TestRunResultSerializer` und stellt sicher, dass ein gültiger Request ungültige Statuswerte bereits im Client-/OpenAPI-Contract ausschließt.

### CD-008 — ChangeRequest-Lifecycle ist im Frontend nicht erreichbar

**Schwere:** P2  
**Status:** bestätigt, Scope-Bewertung erforderlich  
**Confidence:** Mittel

**Tatsache**

- Das Backend publiziert List, Create, Detail, PATCH, Delete, Legacy-Transition, generische Transitions und Workflow-History: `backend/rest_api/views.py:7036-7050`.
- Der Backend-Test deckt CRUD und Transition ab: `backend/rest_api/tests/test_change_request_api.py:1-13`.
- Der Frontend-Client besitzt nur `create()` und einen minimalen Response-Typ: `frontend/src/api/change-requests.ts:16-38`.
- Der einzige UI-Einstieg ist der Raise-Change-Request-Shortcut im Baseline-Drift-Badge; es gibt keine NavigationShell-Route `/change-requests` und keine sichtbare CR-Liste/Detail-/Transition-Fläche: `frontend/src/components/shared/BaselineDriftBadge/BaselineDriftBadge.tsx:105-151`; `frontend/src/components/NavigationShell/NavigationShell.tsx:135-217`.

**Auswirkung**

Ein Benutzer kann einen ChangeRequest erzeugen, aber nicht zuverlässig auffinden, prüfen, kommentieren, einem Reviewer zuweisen oder über die CCB-Transition abschließen. Der vollständige Backend-Vertrag bleibt für UI-Nutzer praktisch unerreichbar.

**Root Cause**

Das Frontend hat den auf Incident/Baseline bezogenen Create-Shortcut vor dem vollständigen ChangeRequest-Workflow implementiert; Routing, Query-Cache und Statusdarstellung wurden nicht nachgezogen.

**Gegenmaßnahme**

- Entweder eine vollständige CR-Route mit Liste, Detail, Status/Transition und Audit-History ergänzen,
- oder den Scope explizit als MCP/API-only dokumentieren und die UI-Shortcut-Aktion entsprechend als „erstellt, aber nicht verwaltet“ kennzeichnen.

**Alternativen**

- Nur die Backend-Dokumentation entfernen: API-Funktion bleibt bestehen, die UI-Lücke bleibt bestehen.
- Backend-CR-Funktionalität reduzieren: größere fachliche Regression; nicht empfohlen.

**Verifikation**

Ein End-to-End-Test muss Create → Liste → Detail → erlaubte Transition → History über die UI ausführen. Bei bewusstem API-only-Scope muss ein Produkt-/Anforderungsentscheid die fehlende UI-Fläche als out of scope dokumentieren.

### CD-009 — Optimistic Concurrency ist nicht über alle Formularpfade verdrahtet

**Schwere:** P2  
**Status:** bestätigt  
**Confidence:** Hoch für Codebefund, mittel für Produkt-Einstufung

**Tatsache**

- Das Backend bietet `expected_version` und ETag/`If-Match`; `If-Match` hat Vorrang und wird in der Service-Transaktion geprüft: `backend/rest_api/mixins/etag.py:150-207`.
- Requirement GET/PATCH liefert und erzwingt den Guard; die UI sendet die zuletzt gelesene Version: `backend/rest_api/views.py:970-993,1048-1147`; `frontend/src/components/RequirementEditors/RequirementArtifactForm.tsx:160-173`.
- TestCase PATCH akzeptiert ebenfalls den Guard: `backend/rest_api/views.py:2685-2760`.
- Architecture PATCH liest `expected_version` aus dem Body: `backend/rest_api/views.py:2021-2079`; der Architecture-Formular-Client nimmt jedoch nur ein untypisiertes Patch-Bag und übergibt keinen Guard: `frontend/src/api/architecture.ts:80-93`; `frontend/src/components/ArchitectureEditors/ArchitectureArtifactForm.tsx:109-114`.
- TestCase-UI ruft `testcasesApi.update` ohne Version/Header auf: `frontend/src/components/TestCaseEditors/TestCaseArtifactForm.tsx:241-258`; `frontend/src/api/testcases.ts:169-182`.

**Auswirkung**

Bei parallelen Bearbeitungen bleiben Architecture- und TestCase-Änderungen im UI-Pfad beim historischen Last-writer-wins-Verhalten. Das ist kein Serververstoß, wenn der Guard optional ist, aber eine nicht sichtbare Abweichung vom einheitlichen Requirement-Vertrag und kann übersehene Änderungen erzeugen.

**Root Cause**

Der Guard wurde Ressourcenweise eingeführt, aber nicht in den gemeinsamen `ArtifactForm`-Save-Adapter oder in alle API-Wrapper-Signaturen überführt.

**Gegenmaßnahme**

- Version aus dem Detail-Objekt in den generischen Save-Pfad aufnehmen und pro Ressource den korrekten Transport wählen.
- Alternativ die UI-Verträge explizit als Last-writer-wins dokumentieren und die verfügbaren Guard-Funktionen nicht vortäuschen.
- Konfliktstatus `409/412` in beiden Formularen sichtbar behandeln.

**Verifikation**

Ein Zwei-Tab-Test für Architecture und TestCase muss stale Writes kontrolliert ablehnen oder die gewählte Last-writer-wins-Entscheidung explizit belegen.

### CD-010 — Kleine Enum-/Request-Typdrift

**Schwere:** P3  
**Status:** bestätigt  
**Confidence:** Hoch

**Tatsache**

- Backend und REST-Serializer akzeptieren `VerificationMethod="Demonstration"`: `backend/persistence/models.py:282-292`; `backend/rest_api/serializers.py:965-972`.
- Der Frontend-Union-Typ enthält nur `Test`, `Review`, `Analysis`, `Inspection`: `frontend/src/types/index.ts:121-124`.
- `frontend/src/api/test-runs.ts:46-80` typisiert Request-Status als `string`; das konkrete UI-Grid besitzt zwar eine korrekte lokale Union (`frontend/src/components/TestRuns/TestRunResultEntryGrid.tsx:48-60`), diese ist aber nicht der gemeinsame API-Vertrag.
- Die Frontend-TestCase-Typen existieren doppelt: `frontend/src/types/index.ts:235-261` und der vollständigere API-Typ in `frontend/src/api/testcases.ts:73-110`.

**Auswirkung**

Ein gültiger Backend-Wert kann nicht verlustfrei in der TypeScript-Domänenmodellierung ausgedrückt werden; Request-Typen lassen ungültige Statuswerte bis zum Serverlauf zu. Die doppelten TestCase-Typen machen die tatsächliche Vertragsoberfläche unklar.

**Gegenmaßnahme**

- Enums aus einer gemeinsamen, versionierten Contract-Definition beziehen und die UI-lokale Union entfernen oder als Aliass definieren.
- Einen Generator-/Contract-Test verwenden, der REST-Serializer-Choices gegen Frontend-Typen prüft.
- Die doppelte TestCase-Domäne auf eine kanonische Schnittstelle zusammenführen.

**Verifikation**

Ein statischer Test liest die OpenAPI-Enums bzw. Serializer-Choices und prüft die generierten Frontend-Typen; mindestens `Demonstration` und alle vier Result-Statuswerte müssen enthalten sein.

## 5. Priorisierte Gegenmaßnahmen

### Priorität 0 — vor externer Vertragsfreigabe

1. **CD-005:** MCP-Multi-Formalize vervollständigen oder den MCP-Multi-Modus ausdrücklich deaktivieren.
2. **CD-004:** sichere API-Key-Erstellung mit explizitem Scope/Fence/Expiry und Rotationsplan einführen.
3. **CD-003:** eine kanonische Workspace-Sprachquelle festlegen und alle Reader migrieren.
4. **CD-002:** Interview-/TestRun-Actions per OpenAPI explizit beschreiben; keine ungeprüfte Standard-CRUD-Annahme mehr veröffentlichen.

### Priorität 1 — nächste Iteration

1. **CD-001:** Fehlerdetails normalisieren und einen gemeinsamen Contract-Test für Runtime/OpenAPI/Frontend ergänzen.
2. **CD-006:** TraceLink-Detail-/PATCH-Routen entweder implementieren oder aus dem Schema entfernen; ID-Raum und Endpoint-Echo explizit dokumentieren.
3. **CD-007:** TestRun-Result-Shape, Choices und Bulk-Response als einen versionierten Vertrag definieren.
4. **CD-008:** ChangeRequest-UI-Scope entscheiden und entweder die Lifecycle-Fläche ergänzen oder API-only dokumentieren.
5. **CD-009:** Guard-Weitergabe im generischen Formular-Save vereinheitlichen.

### Priorität 2 — nachgelagerte Hygiene

1. **CD-010:** Enum- und Request-Typen generieren bzw. zentralisieren.
2. Workspace-Preset-Objektform und Sprache gemeinsam in einen Read-/Write-Contract überführen.
3. `artifactRefs`-Bridge und Endpoint-Echo-Verhalten als eigenes TraceLink-API-Kapitel in der öffentlichen OpenAPI-Dokumentation beschreiben.

## 6. Versionierungs- und Migrationshinweise

- **Workspace-Sprache:** Eine Entfernung von `preset.language` oder ein Wechsel der Wire-Form ist für bestehende Clients breaking. Eine Übergangsphase mit Dual-Read, explizitem Konfliktverhalten und anschließendem Major-Contract ist erforderlich.
- **Fehlerdetails:** Die Umstellung von Dictionary auf Array ist ebenfalls wire-relevant. Bis zur Umstellung sollte ein Kompatibilitätsadapter beide Shapes akzeptieren, ohne die kanonische Response zu verschleiern.
- **API-Key-Defaults:** Eine Änderung des Legacy-`write`-Defaults verändert Sicherheitssemantik. Bestehende Keys müssen inventarisiert, rotiert und mit einem expliziten Migrations-/Rollback-Plan behandelt werden.
- **MCP-Multi-Formalize:** Ein optionales/konditionales `confirmed_proposal` erhält Single-Mode-Kompatibilität; ein Required-Feld ohne Versionsstrategie wäre für bestehende Multi-Aufrufe breaking.
- **TraceLink:** Das Entfernen einer bereits generierten GET/PATCH-Operation ist breaking. Eine Implementierung oder eine bewusst versionierte Schema-Schränkung ist erforderlich.

## 7. Empfohlene Verifikations-Gates

Vor einer erneuten Veröffentlichung der API sollten mindestens folgende Gates existieren:

1. **Schema-Snapshot-Gate:** Jede ausgewählte Operation besitzt Request-, Success- und Fehler-Schema; kein generiertes `No response body` für eine Response mit DTO.
2. **Runtime/Schema-Parität:** Statuscodes und Feldtypen der ausgewählten Endpunkte werden mit einem APIClient-/Schema-Validator-Test verglichen.
3. **Frontend-Contract-Test:** TypeScript-Typen decken alle Enum-Werte und Response-Felder ab; Request-Statuswerte sind nicht `string`.
4. **MCP-Paritätstest:** REST und MCP liefern für Single-/Multi-Interview dieselben fachlichen Resultate; der Manifest-Test wird um Service-Contract-Assertions ergänzt.
5. **Cross-Adapter-Workspace-Test:** Sprache, Preset und Terminology-Profile stimmen zwischen REST, ORM, AI, MCP und Memory überein.
6. **API-Key-Security-Test:** Jeder neu erzeugte Key hat expliziten Scope, Workspace-Fence und Ablauf-/Bewusst-nicht-ablaufend-Entscheid; bestehende Legacy-Keys werden reportet.

## 8. Abschlussstatus

STATUS: done  
RESULT: Der Bericht ist eine statische, evidenzbasierte Vertragsprüfung für REST, MCP, Frontend und Datenmodell. Zehn Befunde wurden bestätigt; die wichtigsten Integritätslücken liegen in der Workspace-Sprachquelle, API-Key-Sicherheitssemantik, MCP-Multi-Formalize und der OpenAPI-Abdeckung. Backend-DB-Tests und ein vollständiger Schema-Paritätstest bleiben als Umgebungs-/Folgearbeit offen.

SPEC_FILE: `docs/se/reports/deep_audit/system-audit-2026-09/03-api-ui-data-contract-drift.md`  
PROTOCOL: REST  
ENDPOINTS: 8  
BREAKING_CHANGES: 0  
CONFORMANCE: drift  
RECOMMENDATIONS: 12  
ARTIFACTS: `docs/se/reports/deep_audit/system-audit-2026-09/03-api-ui-data-contract-drift.md`
