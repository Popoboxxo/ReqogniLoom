# Deep Test Coverage Audit: RestApiAdapterSystem

Dieses Dokument liefert einen detaillierten Audit der Testabdeckung für das `RestApiAdapterSystem`. Es basiert auf den L2-Anforderungen (`L2_RestApiAdapterSystem_Requirements.md`) und einer zeilengenauen Analyse aller Testdateien im Verzeichnis `backend/rest_api/tests/`.

## Zusammenfassung der Befunde

Die Analyse zeigt, dass viele Tests im `RestApiAdapterSystem` **zu oberflächlich (shallow)** sind. Anstatt das tatsächliche Verhalten der API (Integration-Tests) zu überprüfen, testen viele Dateien isolierte Dictionaries, Mocks oder statische Klasseneigenschaften. Dies steht im direkten Widerspruch zu den Akzeptanzkriterien der Requirements, die oft explizite HTTP/Integration-Tests fordern.
Insbesondere fehlen **N+1 Query-Assertions**, **echte Request-Integrationstests** und **OpenAPI-Response Validierungen**.

---

## Detaillierte Datei-Analyse

### 1. `backend/rest_api/tests/test_auth_enforcer.py`

**Testklasse: `TestBearerTokenAuthentication`**
- **Test:** `test_is_auth_tenancy_authentication`
- **REQ-L2 ID:** REQ-L2-RA-005
- **Aktueller Zustand (Shallow?):** **JA**. Der Test prüft lediglich eine statische Klassen-Identität (`assert BearerTokenAuthentication is AuthTenancyAuthentication`).
- **Akzeptanzkriterium:** Request ohne Token → HTTP 401, ungültiger Token → 401.
- **Refactoring-Bedarf:** Dieser Unit-Test muss durch API-Integrationstests (mit DRF `APIClient`) ersetzt oder ergänzt werden, die echte Requests ohne Header, mit falschem Header und mit abgelaufenem Token senden und prüfen, ob ein `HTTP 401` zurückkommt.

**Testklasse: `TestMethodToOperationMapping`**
- **Tests:** `test_get_maps_to_read`, `test_post_maps_to_write`, etc.
- **REQ-L2 ID:** REQ-L2-RA-006 (RBAC)
- **Aktueller Zustand (Shallow?):** **JA**. Es wird lediglich der Inhalt des Dictionaries `_METHOD_TO_OPERATION` geprüft.
- **Akzeptanzkriterium:** Rollenbasierte Zugriffskontrolle für jede API-Operation (Viewer darf GET, POST → 403).
- **Refactoring-Bedarf:** Löschen oder als irrelevant markieren. Stattdessen echte API-Anfragen mit authentifizierten Usern (Rolle Viewer, Editor, Admin) simulieren und die entsprechenden Statuscodes (200, 403) bei unterschiedlichen HTTP-Methoden prüfen.

**Testklasse: `TestRbacPermission`**
- **Tests:** `test_no_auth_context_denies`, `test_viewer_role_get_allowed`, `test_viewer_role_post_denied`, `test_admin_role_all_methods_allowed`, `test_editor_read_and_write_allowed`
- **REQ-L2 ID:** REQ-L2-RA-006 (RBAC)
- **Aktueller Zustand (Shallow?):** **TEILWEISE**. Testet zumindest das `has_permission`-Interface, arbeitet aber mit massiv gemockten DRF-Requests. 
- **Akzeptanzkriterium:** Viewer: GET erlaubt, POST/PATCH/DELETE → HTTP 403. Editor: GET/POST/PATCH/DELETE auf eigene Ressourcen. Admin: Alle Operationen erlaubt. Approver: workflow_state transition.
- **Refactoring-Bedarf:** Die Permission-Klasse sollte nicht an gemockten Request-Objekten isoliert getestet werden, sondern an Dummy-Views (oder echten Views) über den DRF `APIRequestFactory` oder `APIClient`. Zudem fehlt der spezifische Test für "Editor auf fremden Workspace → 403", der im AC gefordert wird, sowie der Approver-Test.

**Testklasse: `TestGetAuthContext`**
- **Tests:** `test_raises_when_context_absent`, `test_returns_context_when_present`, `test_tenant_id_immutable_in_context`
- **REQ-L2 ID:** REQ-L2-RA-011
- **Aktueller Zustand (Shallow?):** **JA**. Prüft lediglich, ob eine Funktion ein Attribut an einem Mock-Objekt findet oder ob Dataclasses "frozen" sind.
- **Akzeptanzkriterium:** Adapter extrahiert Tenant-ID und übergibt sie im Auth-Kontext. DB-Abfragen sind danach gefiltert.
- **Refactoring-Bedarf:** Erstellen eines E2E-Tests, der prüft, dass ein Request mit dem Token eines Tenants A nur die Daten von Tenant A liefert und keinen Zugriff auf Tenant B hat.

---

### 2. `backend/rest_api/tests/test_auth_login.py`

**Tests:** Alle Tests (`test_login_success_returns_token_and_user`, `test_login_wrong_password_returns_401`, etc.)
- **REQ-L2 ID:** REQ-L2-RA-005, REQ-L1-010
- **Aktueller Zustand (Shallow?):** **NEIN**. Dies sind solide Integrationstests mittels `APIClient` und Datenbank.
- **Akzeptanzkriterium:** Login, Authentifizierung, 401 bei Fehler.
- **Refactoring-Bedarf:** Keiner. Die Tests decken das Szenario sehr gut und realistisch ab.

---

### 3. `backend/rest_api/tests/test_csv_import.py`

**Tests:** CSV Import E2E Tests
- **REQ-L2 ID:** REQ-L2-AS-014 / REST-API Randbereich (REQ-L2-RA-001)
- **Aktueller Zustand (Shallow?):** **NEIN**. Nutzt den `APIClient` für Datei-Uploads und prüft die DB-Zustände sowie Validation Errors realitätsnah.
- **Refactoring-Bedarf:** Keiner. Gute Testabdeckung.

---

### 4. `backend/rest_api/tests/test_diagram_canvas_views.py`

**Tests:** GET/POST/PUT für Canvas und Mermaid
- **REQ-L2 ID:** REQ-L2-RA-001 (allgemeine Endpunkte), REQ-L1-056
- **Aktueller Zustand (Shallow?):** **JA (extrem)**. Jeder einzelne Test (`mock_auth`, `mock_verify`, `mock_get_canvas`, `mock_save`) mockt die gesamte Business-Logik und DB. Die Tests validieren nur, dass ein Mock-Objekt aufgerufen wurde (`mock_save.assert_called_once()`).
- **Akzeptanzkriterium:** Funktionierende Endpunkte für Canvas- und Mermaid-Operationen.
- **Refactoring-Bedarf:** Entfernen der extensiven Mocks. Die Tests müssen echte Datensätze in der Datenbank nutzen und überprüfen, ob der Controller Payloads korrekt weiterreicht und das geänderte SVG/Source im Response Body zurückgibt.

---

### 5. `backend/rest_api/tests/test_openapi.py`

**Testklassen:** `TestErrorResponseSerializer`, `TestCommonErrorResponses`, `TestSettingsBearerAuthScheme`, `TestPublicExports`
- **REQ-L2 ID:** REQ-L2-RA-002, REQ-L2-RA-009
- **Aktueller Zustand (Shallow?):** **JA (absolut)**. Es wird geprüft, ob eine Konstante `400` in einem Dictionary-Array existiert, ob Django-Settings bestimmte statische Strings enthalten und ob Serializer-Klassen bestimmte Keys deklarieren.
- **Akzeptanzkriterium:** `GET /api/v1/schema/` liefert valides OpenAPI-3.0-JSON. `GET /api/v1/schema/swagger-ui/` rendert interaktive UI.
- **Refactoring-Bedarf:** Alle bisherigen Tests sind nutzlos für das AC. Es muss ein Integrationstest geschrieben werden: `APIClient().get('/api/v1/schema/')` aufrufen, `status_code == 200` prüfen und asserten, dass die JSON-Antwortstruktur ein OpenAPI-Dokument mit allen CRUD-Pfaden (`/api/v1/requirements/`, etc.) ist. Ebenso HTTP-Erreichbarkeit für `/api/v1/schema/swagger-ui/` prüfen.

---

### 6. `backend/rest_api/tests/test_pdf_report_endpoint.py`

**Tests:** Alle (PDF Generierung Endpunkte)
- **REQ-L2 ID:** REQ-L2-AS-016
- **Aktueller Zustand (Shallow?):** **NEIN**. Testet Endpunkte per `APIClient` und validiert, dass die Response die korrekten PDF-Magic-Bytes (`%PDF-`) enthält.
- **Refactoring-Bedarf:** Keiner.

---

### 7. `backend/rest_api/tests/test_preference_views.py`

**Tests:** Alle (User Preferences REST-API)
- **REQ-L2 ID:** REQ-L1-027
- **Aktueller Zustand (Shallow?):** **NEIN**. APIClient, reale Datenbank-Interaktion, saubere Assertions auf Response-JSON.
- **Refactoring-Bedarf:** Keiner.

---

### 8. `backend/rest_api/tests/test_preset_guard.py`

**Testklassen:** `TestPresetGuardCheckEndpoint`, `TestPresetGuardGetFieldFilter`
- **REQ-L2 ID:** REQ-L2-RA-008
- **Aktueller Zustand (Shallow?):** **JA**. Die Tests instanziieren Dataclasses und mocken die zugrundeliegende Engine (`@patch("rest_api.preset_guard.is_feature_enabled")`). Es wird rein logisch auf Objektebene getestet, aber nicht, ob die DRF-Views dadurch korrekt abgeschirmt werden.
- **Akzeptanzkriterium:** Minimal-Preset: Baseline-Endpunkte → HTTP 404. Nicht erlaubte Felder aus Serialization ausgeschlossen.
- **Refactoring-Bedarf:** Echte Integrationstests für den PresetGuard an den Views sind zwingend erforderlich. 
  1. Workspace mit "minimal" Preset erstellen → API-Request auf `/api/v1/baselines/` senden → Prüfen auf `404 Not Found`.
  2. Workspace mit "extended" Preset erstellen → Request auf `/api/v1/baselines/` senden → Prüfen auf `200` oder `403`.
  3. Prüfen, dass exklusive Felder (wie `change_reason`) im Minimal-Preset nicht im JSON-Response enthalten sind.

---

### 9. `backend/rest_api/tests/test_serializers.py`

**Testklasse: `TestI18nErrorMessages` & `TestDetectLang`**
- **REQ-L2 ID:** REQ-L2-RA-004
- **Aktueller Zustand (Shallow?):** **JA**. Es wird lediglich eine Python-Methode `get_error_message` aufgerufen oder der Request-Header isoliert geparst.
- **Akzeptanzkriterium:** Request mit `Accept-Language: de` → Fehlermeldung auf Deutsch (via API Response).
- **Refactoring-Bedarf:** Ein echter Request über den `APIClient` (mit ungültigem Payload) und gesetztem `HTTP_ACCEPT_LANGUAGE: de` Header. Validieren, dass das Response-JSON die deutsche Fehlermeldung enthält.

**Testklasse: `TestBuildErrorResponse` & `TestStandardPagination`**
- **REQ-L2 ID:** REQ-L2-RA-009, REQ-L2-RA-010
- **Aktueller Zustand (Shallow?):** **JA**. Prüft nur Output von Generator-Funktionen und Properties an Klassen.
- **Refactoring-Bedarf:** Integrieren mit echten API-Requests, um die Pagination-Parameter (page_size, count, next) im echten JSON Output zu validieren.

**Testklasse: `TestQuerysetOptimizations`**
- **Tests:** `test_trace_link_has_source_target_select_related` etc.
- **REQ-L2 ID:** REQ-L2-RA-013 (N+1-Query-Vermeidung)
- **Aktueller Zustand (Shallow?):** **SEHR SHALLOW**. Der Test verifiziert nur, ob in einem statischen Dictionary die richtigen Strings (z.B. `"artifact"`) konfiguriert sind und ob `apply_queryset_optimizations` auf einem gemockten Objekt `.select_related()` aufruft. 
- **Akzeptanzkriterium:** Kein N+1-Query-Muster auf List- und Detail-Endpunkten (verifizierbar via Query-Count-Messung).
- **Refactoring-Bedarf:** Die Dummy-Dict-Checks lösen das Problem nicht. Es muss ein echter Datenbank-Test geschrieben werden: Datensätze erstellen (z.B. 10 Requirements mit TraceLinks). Den List-Endpunkt abrufen und mit `self.assertNumQueries(...)` (DRF/Django) assertieren, dass die Anzahl der SQL-Queries konstant bleibt.

---

### 10. `backend/rest_api/tests/test_views.py`

**Testklassen:** `TestRequirementViewSetRouting`, `TestArchitectureElementViewSetRouting`, etc.
- **REQ-L2 ID:** REQ-L2-RA-001 (REST-CRUD-Endpunkte)
- **Aktueller Zustand (Shallow?):** **JA**. Die Tests nutzen zwar `APIRequestFactory`, **mocken aber systematisch den gesamten Application-Service-Layer weg** (`patch("rest_api.views.RequirementViewSet._svc")`). Es sind reine "Structural Tests".
- **Akzeptanzkriterium:** "Integration-Test: POST `/api/v1/requirements/` → 201 + JSON"
- **Refactoring-Bedarf:** Mocks radikal entfernen. Echten `APIClient` nutzen und einen sauberen POST-Request mit validem JSON an die API schicken. Überprüfen, ob `201` zurückkommt, das Element real in der Datenbank liegt (`Requirement.objects.count() == 1`) und ein GET `/api/v1/requirements/{id}/` die erstellten Daten liefert.

**Testklasse: `TestRequirementHistoryView`**
- **REQ-L2 ID:** REQ-L2-RA-007 (Audit-Log-Auslösung)
- **Aktueller Zustand (Shallow?):** **JA**. Mockt das AuditLog-Resultset.
- **Refactoring-Bedarf:** Keine API-Endpunkte testen, ob POST/PATCH Schreiboperationen auch tatsächlich das Audit-Log (AuditLogEntry) generieren. Hier muss in den CRUD-Tests sichergestellt werden, dass nach dem POST/PATCH im Audit-Log ein entsprechender Eintrag vorhanden ist.

**Testklasse: `TestNoBusinessLogicInViews`**
- **REQ-L2 ID:** REQ-L2-RA-012
- **Aktueller Zustand (Shallow?):** **JA**. Ein Linter-Test (`inspect.getsource`), der Strings wie `if status == 'approved'` im Quellcode sucht.
- **Refactoring-Bedarf:** Dies ist eher eine Spielerei als ein Test. Der Test auf korrekte Delegation an den Service ergibt sich implizit durch gute Integrationstests.

---

## Fazit & Nächste Schritte

Um die Test-Schulden im `RestApiAdapterSystem` abzubauen und echtes Vertrauen in den Code zu gewinnen, müssen folgende Refactorings im Test-Code durchgeführt werden:

1. **Abkehr vom "Mocking-Anti-Pattern":** Views und Serializer in `test_views.py` und `test_diagram_canvas_views.py` dürfen nicht länger den Service-Layer und die Datenbank wegmocken. Sie müssen als echte HTTP-Integrationstests (`APIClient`) umgeschrieben werden.
2. **Implementierung echter N+1 Query Tests:** In `test_serializers.py` (oder einem dedizierten E2E Test) müssen `assertNumQueries`-Messungen für die Listen-Endpunkte integriert werden.
3. **OpenAPI Schema E2E-Validierung:** `test_openapi.py` so umschreiben, dass die HTTP-Endpunkte abgrufen werden, um das Schema strukturell zu prüfen.
4. **Preset Guard Integration:** In `test_preset_guard.py` echte HTTP-Routen mit verschiedenen konfigurierten Workspaces abrufen und `404`/`403` vs. `200` testen.
5. **i18n Header Test:** Ein Test mit dem `Accept-Language` Header an die echte API, um die Lokalisierung der Fehler-JSONs end-to-end zu verifizieren.
