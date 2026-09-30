---
type: REVIEW
scope: wp5-evidence-widersprueche
status: final
date: 2026-09-29
author_agent: validator
---

# WP-5 Evidenz 4 — Widersprüche REQ ↔ Implementierung

> Kernfrage des WP-5. Jeder Eintrag: REQ-ID + REQ-Zitat + `datei.py:zeile` +
> Bezug zum belegten Zustand. „Marker" = Spalte *Impl. State* in
> `docs/se/traceability-matrix.md` §2/§3 (Selbstauskunft der SOLL-Dokumente).

## A. Belegte Widersprüche — Verhalten versprochen, nicht eingehalten

### A1 · `REQ-L1-046` Instanz-Backup/DR/Restore — Critical

| | |
|---|---|
| REQ-Zitat | *„Das System MUSS vollständige, automatisierbare Instanz-Snapshots (Backup) aller …"* (`L1_Gesamtsystem_Requirements.md`, Block `### REQ-L1-046`) |
| Marker | **Implemented** / Test Status **Covered** / Review Findings: *„Anforderung ist durch Tests verifiziert und im Code auffindbar."* |
| Widerspruch 1 (Dokument-intern) | Einziges Kind `REQ-L2-BL-011` *„Instanz-Backup, Full Restore & Baseline-Soft-Restore"* ist in der Matrix **Not Implemented / Missing** (`traceability-matrix.md:331`). Ein `Implemented`-Parent mit 100 % nicht-implementierten Kindern. |
| Widerspruch 2 (Code) | `backend/Dockerfile:154` ist `COPY . .` mit Build-Context `backend/`. `scripts/restore.sh` liegt **außerhalb** dieses Contexts; weder `backend/Dockerfile` noch `deploy/docker-compose.yml` referenzieren `restore.sh` (`rg -n 'restore' backend/Dockerfile deploy/docker-compose.yml` → **0 Treffer**). Das Skript existiert (`scripts/restore.sh`, `Test-Path` → True) und ist damit **nicht ausführbar**. |
| Verknüpft | `AUD-2026-09-123` (Critical) |
| Status | **WIDERSPRUCH** |

### A2 · `REQ-L1-013` LLM-Capabilities konfigurierbar — Critical

| | |
|---|---|
| REQ-Zitat | *„… wobei der LLM-Anbieter und API-Key pro Deployment konfigurierbar sind und das System ohne LLM-Zugang vollständig funktionsfähig bleibt."* |
| Marker | **Implemented** / Covered |
| Widerspruch | `backend/llm_adapter/providers.py:1080` — `MODEL_NAME = "claude-3-opus-20240229"`. Anthropic hat dieses Modell am 2026-01-05 abgeschaltet. Da `LLM_MODEL` in allen Compose-Dateien leer ist (`.env.example:184` führt nur einen **auskommentierten** Vorschlag `# LLM_MODEL=claude-3-5-sonnet-20241022`), scheitert mit `LLM_PROVIDER=anthropic` **jeder** LLM-Aufruf. |
| Zusatz | Der Wert ist als **Erwartungswert in Tests fixiert**: `backend/rest_api/tests/test_llm_settings.py:248` — `"model_name": "claude-3-opus-20240229"`. Der Testlauf reproduziert den Defekt nicht, er konserviert ihn. |
| Verknüpft | `AUD-2026-09-052` (Critical) |
| Status | **WIDERSPRUCH** |

### A3 · `REQ-L2-LA-007` Azure-OpenAI Provider — High

| | |
|---|---|
| REQ-Zitat | Titel in `L2_LlmAdapterSystem_Requirements.md`: *„Azure-OpenAI Provider-Unterstützung"* |
| Marker | **Implemented** / Test Status **Missing** |
| Widerspruch | Implementiert ist nur die Python-Seite: `backend/llm_adapter/providers.py:1674` `PROVIDER_NAME = "azure"`, Felder `:84-85`, Env-Binding `:123-124`. **Nicht wählbar** ist der Provider: `frontend/src/api/llm-settings.ts:22` — `export type LlmProvider = "anthropic" \| "openai" \| "ollama" \| "opencode_go" \| "mock";` → `azure` fehlt im Typ **und** in der Options-Liste (`:25`). |
| Werbung | `README.md:333`, `.env.example:197` führen `azure` als unterstützt. |
| Verknüpft | `AUD-2026-09-058` (High) |
| Status | **WIDERSPRUCH** |

### A4 · `REQ-L1-016` Zweisprachige Benutzeroberfläche — High

| | |
|---|---|
| REQ-Zitat | *„Das System muss alle UI-Texte und Backend-Fehlermeldungen in Deutsch und Englisch bereitstellen, **wobei fehlende Translation-Keys als Build-Fehler behandelt werden (Lint-Regel)** …"* |
| Marker | **Implemented** / Covered (Matrix `:114`), `REQ-L2-RF-001` **Implemented / Missing** (`:470`) |
| Widerspruch | 112 `t()`-Keys fehlen in **beiden** Locale-Dateien. Die in der REQ zugesagte Lint-Regel („Build-Fehler") existiert nicht als wirksame Schranke — der Parity-Ratchet bleibt grün. 7 einschlägige Issues sind **geschlossen** (#676, #421, #595, #610, #651, #653, #654). |
| Verknüpft | `AUD-2026-09-002`/`-016` (High) |
| Status | **WIDERSPRUCH** |

### A5 · `REQ-L1-021` CSV-Bulk-Import — High

| | |
|---|---|
| REQ-Zitat | *„Das System MUSS einen CSV-Import für Requirements, ArchitectureElements und TestCases bereitstellen, der **Validierung gegen das Datenmodell durchführt**, Fehler mit Zeilennummer zurückmeldet und erfolgreich importierte Items mit regulären UUIDs versieht."* |
| Marker | **Implemented** / Covered (Matrix `:119`), `REQ-L2-AS-014` **Implemented / Covered** (`:240`) |
| Widerspruch | Der Validierungskanal existiert, meldet aber nur `warnings`, nie `success=false`: `backend/application/import_service.py:226-233` baut die Unbekannte-Spalten-Meldung in `warnings`; `ImportResult.success: bool` (`:149`) bleibt `True`. Ein Import, der eine **ganze Spalte** verwirft, wird damit als Erfolg berichtet. Round-Trip-Defekt: `AUD-2026-09-070`. |
| Code-Beleg | `backend/application/import_service.py:136` — Docstring *„success: True if all valid rows were persisted"*; der Spaltenverlust ist genau ein solcher Fall „valid rows". |
| Verknüpft | `AUD-2026-09-070` (Critical) |
| Status | **WIDERSPRUCH** |

### A6 · `REQ-L2-RO-001` / `REQ-L2-AS-029` / `REQ-L2-LA-008` Asynchronie — High

| | |
|---|---|
| REQ-Zitat | `REQ-L2-RO-001` *„Asynchrone Entkopplung"* — Marker **Implemented / Covered** (Matrix `:521`) |
| Widerspruch | Jede Celery-Task läuft 4× (Fanout); Beat-Dispatch und Health-Verhalten sind inkonsistent. Der Celery-Worker im Stack ist `healthy`, die Aufgaben werden aber vervielfacht ausgeführt. |
| Reconciliation | Der **Beat-Teil** des Parallelbefunds ist **nicht reproduzierbar**: `backend/reqogniloom/settings.py:817-831` registriert `audit-monthly-archive` → `audit.archive_lifecycle_manager`; die `PeriodicTask`-Zeile existiert live (`SELECT name,task,enabled FROM django_celery_beat_periodictask` → 4 Zeilen, alle `enabled=t`). `AUD-2026-09-121` ist damit für den Live-Stack **widerlegt**. |
| Verknüpft | `AUD-2026-09-120` (Fanout) — bestätigt; `-121` (Archivierung) — **widerlegt** |
| Status | **WIDERSPRUCH** (Fanout) / **RECONCILED** (Beat) |

### A7 · MCP-Transport stdio — High (Doku vs. Code)

| | |
|---|---|
| REQ-Bezug | `REQ-L2-MC-019` *„MCP Protocol Compliance & Schemas"* — Matrix `:417`, Status **Planned / Untested** |
| Doku-Zusage | `AGENTS.md` Projektbeschreibung: *„Transports: HTTP, SSE, stdio"* |
| Widerspruch | Der stdio-**Handler** existiert: `backend/mcp_server/protocol_handler.py:345` *„stdio transport — reads newline-delimited JSON from stdin"*. Der stdio-**Transport** existiert nicht: `backend/mcp_server/views.py:425` *„'stdio' is deliberately absent"* (bewusst aus der beworbenen Liste entfernt); `/mcp/stdio/` → 404. Zusätzlich `backend/mcp_server/models.py:17`: `TODO(COMP-MCP-003): Implement transport handlers: stdio, SSE, HTTP.` — die TODO steht also noch offen, obwohl SSE/HTTP laufen. |
| Verknüpft | `AUD-2026-09-030…043` (MCP-Bereich) |
| Status | **WIDERSPRUCH** (Doku) |

### A8 · `REQ-L2-AL-009` Cold-Storage-Archivierung — Reconciliation (widerlegt)

| | |
|---|---|
| REQ/Marker | `REQ-L2-AL-009` *„Cold-Storage-Archivierung (Datenlebenszyklus)"* — Matrix `:286`, **Implemented / Untested** |
| Parallelbefund | `AUD-2026-09-121` behauptete, die Archivierung sei „nie registriert". |
| Messung | `backend/reqogniloom/settings.py:822-825` registriert `audit-monthly-archive` mit `crontab(day_of_month="1", hour=0, minute=0)`. `backend/audit/tests/test_sa39_append_guard_and_schedule.py:73-79` prüft die Registrierung. Live-DB: `django_celery_beat_periodictask` enthält `audit-monthly-archive | audit.archive_lifecycle_manager | t`. |
| Status | **RECONCILED — Befund nicht reproduzierbar.** Bleibt: Test Status `Untested` (Matrix), d. h. kein Test des Archivierungs-*Verhaltens*. |

### A9 · Health überwacht Abhängigkeiten — Reconciliation

| | |
|---|---|
| REQ-Bezug | `REQ-L1-026` *„Übergreifende Performance-Anforderung"* / `admin_ops`-Health. |
| Parallelbefund | `AUD-2026-09-129` — Health meldet `ok` bei Totalausfall. |
| Code | `backend/admin_ops/health_rest.py:72` `STATUS_OK = "ok"`; `:434` `"status": STATUS_OK if ok else STATUS_DOWN`; `:459-461` dreistufig `ok/degraded/down`; `:481` `"ok": False`. |
| Bewertung | Der Code **kennt** ein `down`-Vokabular. Ob der Aggregationspfad bei Totalausfall `ok` liefert, ist aus statischer Sicht nicht entscheidbar → **BLOCKED**, Messung gehört an den laufenden Stack (Phase 2). |
| Status | **BLOCKED** |

### A10 · `REQ-L1-039` Item-Level-Zugriffskontrolle — Doppelbefund

| | |
|---|---|
| REQ-Zitat | *„Das System muss Projekt-Administratoren ermöglichen, Sichtbarkeits- und Bearbeitungsrechte auf Subsystem- oder Artefakt-Ebene zu konfigurieren …"* |
| Marker | Parent **Implemented** (Matrix `:137`); Kinder: `REQ-L2-AT-017` Implemented/Covered, **`REQ-L2-AT-018` „Item-Level Permission Enforcement" Not Implemented / Missing**, `REQ-L2-AT-019` Not Implemented / Missing (`:310-312`) |
| Code | Implementiert ist mehr als die Matrix sagt: `backend/auth_tenancy/models.py:371` *„Item-level permission rule (COMP-AT-005, REQ-L1-039)"*, `:47` *„Item-level permission levels"*, `:13`/` :21` Vererbung der Rollenmatrix; `backend/application/effective_permission_service.py:5`; `backend/auth_tenancy/tests/test_item_permission.py`, `test_item_permission_rest.py`. |
| Bewertung | **Zwei Fehler in entgegengesetzter Richtung.** (a) Der Parent `REQ-L1-039` behauptet `Implemented`, während 2 von 3 Kindern `Not Implemented` sind → Widerspruch im SOLL. (b) Der Marker `REQ-L2-AT-018 Not Implemented` ist **veraltet** — Enforcement-Code und Tests existieren. Die Matrix untertreibt. |
| Status | **WIDERSPRUCH** (a) + **MATRIX-STALE** (b) |

## B. Dokument-interner Widerspruch: Parent `Implemented`, Kind nicht

Mechanisch aus der Matrix abgeleitet (`Impl. State` §2 gegen §3):

| REQ-L1 | Titel | `#` Kinder | nicht-`Implemented` Kinder |
|---|---|---|---|
| REQ-L1-001 | Artefakt-Hierarchie | 5 | REQ-L2-AS-039 |
| REQ-L1-003 | Traceability-Engine | 10 | REQ-L2-TE-019, REQ-L2-TE-020 |
| **REQ-L1-005** | **MCP Server Vollzugriff** | 12 | **8** (MC-001…006, MC-009, MC-011) |
| REQ-L1-007 | Rigor-Presets | 17 | REQ-L2-MC-008 |
| REQ-L1-008 | Multi-Level-Baselines | 13 | AS-011, BL-008, BL-012 |
| REQ-L1-009 | Item-Level-Workflow | 8 | REQ-L2-AS-012 |
| REQ-L1-010 | RBAC | 12 | REQ-L2-MC-007 |
| REQ-L1-011 | Audit-Trail | 13 | REQ-L2-MC-012 |
| REQ-L1-012 | Testmanagement | 4 | REQ-L2-AS-005 |
| REQ-L1-013 | LLM-Capabilities | 12 | LA-009, LA-010 |
| REQ-L1-020 | Volltextsuche | 2 | REQ-L2-AS-008 |
| REQ-L1-026 | Performance | 16 | BL-008, MC-010, PL-007 |
| REQ-L1-029 | ADR/Risiko/Issue | 3 | AS-027, AS-028 |
| REQ-L1-030 | Cross-Projekt-Traceability | 2 | REQ-L2-TE-014 |
| **REQ-L1-039** | **Item-Level-Zugriffskontrolle** | 3 | **2** (AT-018, AT-019) |
| **REQ-L1-046** | **Backup/DR/Restore** | 1 | **1** (BL-011) |
| REQ-L1-057 | Mermaid Live Preview | 2 | REQ-L2-AS-033 |

**17 REQ-L1** mit Marker `Implemented` haben ≥1 nicht-implementiertes Kind.
Davon sind 3 **vollständig** widersprüchlich (REQ-L1-005 zu 8/12, REQ-L1-039 zu
2/3, REQ-L1-046 zu 1/1).

**Zusätzlich: 4 `Implemented`-REQ-L1 ohne jede L2-Zerlegung**

| REQ-L1 | Titel | Primäre L2-Systeme |
|---|---|---|
| REQ-L1-042 | Workspace-Lifecycle-Operationen mit RBAC | `—` |
| REQ-L1-100 | Node Graph Diagram Payload Format | `—` |
| REQ-L1-101 | DIAGRAM_REF Trace Link Type | `—` |
| REQ-L1-046 | Instanz-Backup/DR/Restore | (1 Kind, nicht implementiert) |

`REQ-L1-042` ist besonders kritisch: die REQ fordert transaktionale
Kaskaden-Löschung **aller** Workspace-Daten plus Captcha-Bestätigung
(`L1_Gesamtsystem_Requirements.md`, Block `### REQ-L1-042`) und ist
trotzdem `Implemented` — ohne ein einziges L2-Kind, das diese Zusicherung
trägt. Auch §5 der Matrix führt REQ-L1-042 unter „REQ-L1 ohne REQ-L2-Zerlegung".

## C. Umgekehrter Widerspruch: Marker veraltet (REQ sagt „nicht implementiert", Code existiert)

| REQ | Marker | Beleg |
|---|---|---|
| `REQ-L1-034` | Not Implemented | ReqIF-Import/-Export, Matrix `:132` |
| `REQ-L2-RQ-001` | Not Implemented / Missing, Matrix `:512` | `backend/application/reqif_import_service.py`, `backend/application/reqif_export_service.py`; **9 Testdateien**: `application/tests/test_reqif_import_service.py`, `test_reqif_export_service.py`, `test_reqif_optional_import.py`, `rest_api/tests/test_reqif_import.py`, `rest_api/tests/test_reqif_export.py` + 4 weitere |
| `REQ-L2-RQ-002` | Not Implemented / Missing, Matrix `:513` | dito |
| `REQ-L2-AT-018` | Not Implemented / Missing, Matrix `:311` | `backend/auth_tenancy/models.py:371`, `backend/application/effective_permission_service.py`, 2 Testdateien |
| `REQ-L2-AS-015` (GitHub Integration) | Not Implemented / Missing, Matrix `:241` | Parent `REQ-L1-022` ebenfalls `Not Implemented`, Kind aber `Implemented` — Matrix-interner Widerspruch |

Zusätzlich aus dem Matrix-Parent/Kind-Abgleich:

| REQ-L1 | Marker | Kinder |
|---|---|---|
| REQ-L1-022 GitHub-Integration | Not Implemented | 1/1 Kind `Implemented` (REQ-L2-AS-015) |
| REQ-L1-033 Credential-basierte Authentifizierung | Not Implemented | **6/6** Kinder `Implemented` (REQ-L2-AT-011…016) |
| REQ-L1-036 Test-Ergebnis-Einspeisung | Not Implemented | 1/2 Kinder `Implemented` (REQ-L2-AS-031) |

`REQ-L1-033` ist der stärkste Fall: alle sechs Kinder (Constant-Time-Credential-
Verification, Token-Ausgabe, Login-Endpoint-Exemption, Password-Hash-Storage,
Self-Identity-Endpoint, No-Account-Enumeration) sind als `Implemented/Covered`
markiert, der Parent als `Not Implemented`.

## D. Tot-subsysteme — 100 % aspirational, mit Code-Nachweis der Abwesenheit

| L2-System | REQ-L2 | Backend-App | Frontend-Component | Tests | Marker |
|---|---|---|---|---|---|
| **AiOrchestrationSystem** | 8 (AI-001…008) | ✘ `backend/ai_orchestration` existiert nicht (0 py) | ✘ keine `AiOrchestration`-Komponente in `frontend/src/components` | 0 | 0 Implemented, 0 Covered |
| **CommentServiceSystem** | 3 (CM-001…003) | ✘ keine App; `rg 'class Comment' backend/persistence/models.py` → **0 Treffer** | ✘ keine Comment-Komponente | 0 | 0/0 |
| **VectorSearchServiceSystem** | 4 (VS-001…004) | ⚠ `backend/memory` existiert (38 py, 344 Tests) — ist aber `MemoryEntry`/`WorkspaceMemorySettings` (`backend/memory/models.py:36,137,156`), **nicht** Vektorsuche über Artefakte | — | — | 0/0 |

Beide dritten Fälle bestätigen die Matrix-Marker — hier ist die Matrix
**richtig** und der Code fehlt tatsächlich.

## E. Zusammenfassung Widersprüche

| Kategorie | Anzahl | Schwere |
|---|---|---|
| A: Verhalten versprochen, Code widerspricht | **7** (A1–A7) | 4× Critical, 3× High |
| Reconciliation: Parallelbefund nicht reproduzierbar | 1 (A8) | — |
| BLOCKED (nicht entscheidbar) | 1 (A9) | — |
| B: `Implemented`-Parent ↔ nicht-`Implemented`-Kind | **17** REQ-L1 (davon 3 vollständig) | High |
| B: `Implemented`-REQ-L1 ohne L2-Zerlegung | 4 | High |
| C: Marker veraltet (Code existiert, REQ sagt nein) | 5 REQ + 3 Parent/Child | Medium |
| D: Tot-subsysteme (100 % aspirational) | 3 (17 REQ-L2) | Info/High |
