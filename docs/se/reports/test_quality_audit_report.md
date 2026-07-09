# SE-Kaskade Test-Quality Audit Report

> **Datum:** 2026-07-09
> **Methode:** Parallele statische Analyse der L2-Requirements vs. Testcode-Implementierung durch einen Schwarm von `se-testreviewer`-Agenten.
> **Scope:** Überprüfung von ca. 1130 Unit- und Integrationstests auf Erfüllung der konkreten Boundary-Conditions und Akzeptanzkriterien.

## 1. Executive Summary

Der Audit hat ein **systemweises Muster von "Shallow Testing" (Scheinabdeckung)** aufgedeckt.
Während die Codebase auf dem Papier (Coverage-Metriken, pytest run) grün ist und strukturell sauber aussieht, werden die in der Systems Engineering Kaskade (L2) definierten, harten nicht-funktionalen und architektonischen Invarianten von den Tests **nicht real geprüft**. Das Problem zieht sich durch das Backend bis in das React-Frontend.

**Die Hauptprobleme:**
1. **Aggressives Mocking:** Datenbankzugriffe (ORM), Transaktionen (`transaction.atomic`), Celery-Background-Tasks und externe Provider werden rigoros weggemockt. Dadurch werden Integrationsfehler und Datenbank-Constraints nicht abgeprüft.
2. **Fehlende Performance- & Skalierungstests:** Harte Metriken (z.B. "500 Artefakte < 200ms", "Batch-Limits von 100 Items") werden in den Tests durch triviale Mini-Datensätze (2 bis 5 Items) simuliert oder komplett ignoriert.
3. **Ausbleibende Datenbank-Validierung:** PostgreSQL-spezifische Features wie Row-Level Security (RLS), Indizes und Append-Only-Constraints (AuditLog) werden nur auf Applikationsebene geprüft, echte SQL/Bypass-Sicherheitstests fehlen.
4. **False Positives im Frontend:** Frontend-Tests claimen Requirement-Abdeckung für komplexe Editoren, testen aber de facto nur irrelevante Layout-Eigenschaften (z.B. Split-Pane-Resizing anstatt Markdown-Editing).

---

## 2. Detaillierte System-Befunde (Kernsysteme)

### 2.1 PersistenceLayerSystem 🔴 (Kritisch)
- **RLS-Isolation (REQ-L2-PL-010):** Die Tests prüfen nur, ob `relrowsecurity = true` in den Metadaten steht. Es fehlt ein echter SQL-Bypass-Test, der beweist, dass eine Query ohne `SET LOCAL app.current_tenant` fehlschlägt.
- **ACID & Transaktionen (REQ-L2-PL-002):** Es werden nur künstliche Python-Exceptions geworfen, um Rollbacks zu testen. Echte `IntegrityError` auf Datenbankebene werden nicht stimuliert.

### 2.2 ApplicationServiceSystem 🔴 (Kritisch)
- **Tree-Query (REQ-L2-AS-002):** Die Anforderung fordert eine performante Abfrage von 500 Artefakten in 5 Ebenen (<200ms). Die dazugehörige `get_tree`-Methode wird im Testcode **komplett ausgelassen**.
- **Mocking von Decomposition:** Beim Zerlegen von Requirements (`decompose()`) werden alle Sub-Methoden gemockt. Ob die rekursiven Entitäten korrekt in der relationalen DB landen, bleibt ungetestet.

### 2.3 ReactFrontendSystem 🔴 (Kritisch)
- **Extreme False Positives (REQ-L2-RF-003):** Der Requirements-Editor-Test referenziert das Requirement, testet aber de facto nur, ob der Resize-Handle der UI verschiebbar ist. Das eigentliche Inline-Editing, Markdown-Rendering und State-Transitions bleiben ungetestet.
- **Massive Lücken:** Kernfunktionen wie das Dashboard, Tree-View Navigation, Visuelles Diffing und Sprachwechsel (i18n) haben keinerlei Tests im `src`-Ordner.

### 2.4 RestApiAdapterSystem 🔴 (Kritisch)
- **Mocking von CRUD (REQ-L2-RA-001):** API-Endpunkte werden nur auf Routing/HTTP-Codes getestet. Der ApplicationService darunter ist komplett weggemockt (`_svc_mock()`), JSON-Payloads und DB-Persistierung bleiben ungetestet.
- **OpenAPI & Pagination:** Swagger/Schema-Generierung wird nur strukturell geprüft. N+1-Vermeidung wird nur über das Vorhandensein des Strings `"select_related"` geprüft, nicht über echte Query-Count-Asserts.

### 2.5 McpServerSystem 🔴 (Kritisch)
- **Fehlende Tools (REQ-L2-MC-014, 016):** `semantic_search` und `get_system_announcement` sind gänzlich ungetestet bzw. fehlen.
- **Shallow Tool-Testing (REQ-L2-MC-015):** Das Tool `record_test_result` wird nur über generische Schleifen (HTTP 200 OK Check) abgedeckt. Es wird **nicht verifiziert**, ob der TestRun in der Datenbank wirklich korrekt an den TestCase verknüpft wurde.
- *Positiv:* Basismechanismen wie Protokoll-Envelopes und RBAC sind exzellent getestet.

### 2.6 AuditLogSystem & BaselineServiceSystem 🔴 (Kritisch)
- **Append-Only / Immutability:** Das Append-Only-Konzept (AuditLog) und die Baseline-Immutability werden nur in der Django-Klasse durchkreuzt. Auf Datenbankebene ist es ungetestet.
- **Diff-Logik:** Baseline-Deltas werden für den Test künstlich als Mock-Tuple erzeugt. Ein Ende-zu-Ende Test mit echten Datenbank-Snapshots existiert nicht.

### 2.7 SeMetricsSystem 🔴 (Kritisch)
- **Asynchrone Caches & Side-Effects:** Es gibt keine Integrationstests, die beweisen, dass die Metrik-GET-Requests wirklich nebenwirkungsfrei (ohne DB-Writes) ablaufen. Der "Thundering-Herd"-Schutz (Waiting auf Celery-Task) ist flach gemockt.

### 2.8 WorkflowEngineSystem & PresetConfigEngineSystem 🟡 (Verbesserungswürdig)
- **Atomarität (REQ-L2-WE-005):** Es fehlen echte Abbruch-Tests, die nachweisen, dass eine unvollständige Transition komplett zurückgerollt wird.
- **Konfiguration vs. Enforcement:** Die Preset-Engine wird exzellent auf Rückgabe korrekter Werte getestet. Es fehlt aber der Integrationstest, der nachweist, dass das *konsumierende* System diese Limits auch strikt erzwingt.

### 2.9 AuthAndTenancySystem 🟢 (Solide)
- **Gute Abdeckung:** JWT-Verifikation, API-Key Constant-Time-Comparison (REQ-L2-AT-002), und Tenant-Isolation im Cache sind sehr stark und physisch abgetestet.

---

## 3. Handlungsempfehlung (Nächste Schritte)

Das Projekt benötigt dringend einen Shift von reinen Unit-Tests hin zu **echten Integrationstests**.

1. **Test-Container einführen:** Weg von `unittest.mock` auf DB-Ebene, hin zu echtem I/O mit `pytest.mark.django_db(transaction=True)`.
2. **Performance-Fixtures:** Ein Skript `generate_test_volume.py` einsetzen, um Lasttests (10.000 Items) für Tree-Building, Diffing und Volltextsuche physisch nachzuweisen.
3. **API-E2E-Suite:** Endpunkte (insbesondere MCP-Tools und Middleware) müssen über den Django/Rest Test-Client real angesprochen werden, um Seiteneffekte (wie Audit-Erstellung und RLS) zu belegen.
4. **React Testing Library:** Frontend-Tests müssen von reinem Render-Testing auf Interaction-Testing (Simulation von User-Typing und Assertion von DOM-Änderungen) umgestellt werden.
