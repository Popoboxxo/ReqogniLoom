# AuthAndTenancySystem Deep-Audit Report

**Datum:** 2026-07-09
**System:** AuthAndTenancySystem
**Ziel:** Audit der Testabdeckung und Identifikation von "Shallow Testing" basierend auf den REQ-L2-AT Anforderungen.

---

## 1. `test_api_key_rest.py`

### `TestApiKeyList.test_list_returns_metadata_without_plaintext`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AT-009
- **Aktuelles Verhalten (Shallow?):** **JA (Shallow)**. Der Test mockt den `AuthenticationService` und testet nur die View-Schicht (dass der View den Mock aufruft und die Response formatiert).
- **Akzeptanzkriterium:** Auflistung → Metadaten, kein Klartext.
- **Refactoring-Bedarf:** Mock des Services entfernen. Einen echten API-Key über die DB/Service-Schicht anlegen, einen echten GET-Request mittels DRF `APIClient` gegen die Route `/api/v1/api-keys/` ausführen und verifizieren, dass das Feld `plaintext` in der echten Response nicht existiert.

### `TestApiKeyDestroy.test_destroy_returns_204`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AT-009
- **Aktuelles Verhalten (Shallow?):** **JA (Shallow)**. Der Test mockt den Service.
- **Akzeptanzkriterium:** Widerruf → sofort wirksam, nächster Request → 401.
- **Refactoring-Bedarf:** Echte Integration: Key in DB erstellen. `DELETE` Request ausführen. Prüfen, ob `status_code == 204`. Danach prüfen, ob der Key in der DB als `revoked` markiert ist ODER ein weiterer Request mit diesem Key (via Header) nun einen HTTP 401 zurückgibt.

### `TestApiKeyDestroy.test_destroy_invalid_id_returns_404`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AT-009
- **Aktuelles Verhalten (Shallow?):** **JA (Shallow)**. Service gemockt (wirft manuell Exception).
- **Akzeptanzkriterium:** (Implizit: Fehlerbehandlung für unbekannte Keys).
- **Refactoring-Bedarf:** Mock entfernen und echten `DELETE` Request auf einen nicht-existenten Key in einer leeren DB ausführen.

### `TestApiKeyAccessControl.test_unauthenticated_list_returns_error`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AT-007
- **Aktuelles Verhalten (Shallow?):** **JA (Shallow)**. Testet eine manuelle Überprüfung im View (`request.auth_context` check), umgeht aber die echte Auth-Middleware.
- **Akzeptanzkriterium:** Endpunkte ohne Token → HTTP 401.
- **Refactoring-Bedarf:** Test muss über den `APIClient` (inkl. Middleware-Stack) erfolgen. Ohne Header anfragen und prüfen, ob die *echte* Auth-Middleware den 401-Fehler abfängt.

---

## 2. `test_authentication.py`

### `test_valid_jwt_produces_identity_claims`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AT-001
- **Aktuelles Verhalten (Shallow?):** **JA (Shallow bzgl. REST)**. Es ist ein reiner Unit-Test der Methode `validate_bearer_token`.
- **Akzeptanzkriterium:** Gültiges JWT → Auth-Kontext erzeugt.
- **Refactoring-Bedarf:** Unit-Test behalten, aber zwingend einen Middleware-Integrationstest ergänzen, der einen REST-Call mit JWT Header macht und sicherstellt, dass `request.auth_context` wirklich befüllt wird.

### `test_expired_jwt_raises_token_expired` / `test_invalid_signature_raises_invalid_signature` / `test_malformed_jwt_raises_invalid_token`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AT-001
- **Aktuelles Verhalten (Shallow?):** **JA (Shallow bzgl. REST)**. Unit-Tests auf Service-Ebene.
- **Akzeptanzkriterium:** Abgelaufenes JWT → HTTP 401 `{"error": "token_expired"}` (bzw. `invalid_signature`).
- **Refactoring-Bedarf:** REST-Tests mit `APIClient` hinzufügen, die echte abgelaufene/ungültige Tokens senden und den exakten HTTP 401 JSON-Body (`error` field) validieren.

### `test_api_key_comparison_uses_compare_digest`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AT-002
- **Aktuelles Verhalten (Shallow?):** **Teilweise Shallow**. Mockt `hmac.compare_digest` um den Aufruf zu zählen.
- **Akzeptanzkriterium:** Timing-Attack-Resistenz: `hmac.compare_digest`.
- **Refactoring-Bedarf:** Mock-Assertion ist legitim als statische Absicherung, aber es fehlt der E2E-API-Test für den Header: Sende API-Key im Header und prüfe auf 401 bei falschem Key.

### `test_valid_api_key_resolves_user_and_tenant` u.a. Key-DB Tests
- **Verknüpfte REQ-L2 ID:** REQ-L2-AT-002
- **Aktuelles Verhalten (Shallow?):** **Nein (Gute Service-Integration)**. Geht direkt an die DB.
- **Akzeptanzkriterium:** Gültiger API Key → User und Tenant aufgelöst.
- **Refactoring-Bedarf:** Nur der zugehörige REST-Layer-Test (Einsatz des Keys) fehlt, der Service-Test selbst ist solide.

---

## 3. `test_authorization.py`

### `test_viewer_can_read_but_not_write` / `test_editor_cannot_approve` etc.
- **Verknüpfte REQ-L2 ID:** REQ-L2-AT-003
- **Aktuelles Verhalten (Shallow?):** **JA (Shallow bzgl. REST)**. Die Tests testen lediglich die Service-Methode `decide_access` und `enforce`.
- **Akzeptanzkriterium:** Viewer versucht POST → HTTP 403 / Editor versucht Approval-Transition → HTTP 403.
- **Refactoring-Bedarf:** Echte REST-Tests fehlen. Ein eingeloggter "Viewer" muss einen echten `POST` auf einen Endpunkt machen, woraufhin die DRF Permission-Klasse 403 werfen muss.

### `test_assign_approver_in_standard_preset_fails` / `test_admin_assignment_persists`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AT-004 / REQ-L2-AT-006
- **Aktuelles Verhalten (Shallow?):** **Nein (Gute Service-Integration)**. Nutzt die DB.
- **Akzeptanzkriterium:** Nicht-Admin versucht Zuweisung → HTTP 403.
- **Refactoring-Bedarf:** Wiederum fehlen die DRF-View Tests für das Rollenzuweisungs-API. Es muss einen HTTP `POST` Request mit Authentifizierung geben, um 403 als Rückgabe zu erzwingen.

---

## 4. `test_errors.py`

### `test_error_body_has_required_fields` / `test_error_body_localises_german` etc.
- **Verknüpfte REQ-L2 ID:** REQ-L2-AT-010
- **Aktuelles Verhalten (Shallow?):** **Nein (Gute Unit-Tests)**. Testet den Formatter.
- **Akzeptanzkriterium:** 401-Antworten enthalten definierte Error-Codes, sind übersetzbar.
- **Refactoring-Bedarf:** Keiner für diese spezifischen Tests.

---

## 5. `test_item_permission.py`

### Cache & Service Unit- und DB-Integrationstests
- **Verknüpfte REQ-L2 ID:** REQ-L2-AT-017 / REQ-L2-AT-018
- **Aktuelles Verhalten (Shallow?):** **Nein (Deep Integration)**. Dies sind hervorragende Tests, die Cache, TTL, DB-Upserts und Resolution-Logic (Workspace-Wide vs Artifact-Scoped) realitätsnah prüfen.
- **Akzeptanzkriterium:** Admin konfiguriert Regel → Regel gespeichert / Item-Level-Regel überschreibt keine Workspace-RBAC / RLS / Performance.
- **Refactoring-Bedarf:** Für REQ-L2-AT-018 ist das API-Enforcement gar nicht vorhanden. Die Service-Tests sind stark, aber die Middleware-Tests fehlen (wie in REQ-L2-AT-018 angemerkt).

---

## 6. `test_item_permission_rest.py`

### `TestItemPermissionGrant.test_grant_returns_201_with_serialised_permission` u.a.
- **Verknüpfte REQ-L2 ID:** REQ-L2-AT-017
- **Aktuelles Verhalten (Shallow?):** **EXTREM SHALLOW**. Sämtliche REST-Tests in dieser Datei nutzen `@patch("auth_tenancy.rest_item_permission.ItemPermissionService")`.
- **Akzeptanzkriterium:** Konfiguration via API-Endpunkt (POST /permissions/item).
- **Refactoring-Bedarf:**
  Alle Mocks auf den `ItemPermissionService` müssen restlos entfernt werden.
  Stattdessen:
  - Verwende `APIClient`.
  - Mache einen echten DB-Upsert via REST.
  - Prüfe danach in der Datenbank `ItemPermission.objects.filter(...)`, ob die Regel wirklich exakt so angelegt wurde.

### `TestItemPermissionRevoke.test_revoke_returns_204`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AT-017
- **Aktuelles Verhalten (Shallow?):** **JA (Shallow)**. Service gemockt.
- **Akzeptanzkriterium:** Regel-Löschung → Berechtigung sofort widerrufen.
- **Refactoring-Bedarf:** Mock entfernen, Regel in der Test-DB seeden, über den `DELETE` Endpunkt löschen und prüfen, ob die DB-Row verschwindet und HTTP 204 zurückkommt.

### `TestItemPermissionList.test_list_returns_200_with_rules`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AT-017
- **Aktuelles Verhalten (Shallow?):** **JA (Shallow)**.
- **Akzeptanzkriterium:** GET auf Permissions.
- **Refactoring-Bedarf:** Mocks entfernen, DB mit Permission-Regeln vorbereiten, GET Call absenden und das ausgegebene JSON exakt gegen den DB-Inhalt prüfen.

---

## 7. `test_password_authentication.py`

### `test_authenticate_credentials_wrong_password` / `test_authenticate_credentials_unknown_user` etc.
- **Verknüpfte REQ-L2 ID:** REQ-L2-AT-011 / REQ-L2-AT-016
- **Aktuelles Verhalten (Shallow?):** **Teilweise Shallow**. Die Service-Methoden werden sehr gut mit echter DB getestet, jedoch fehlt der HTTP Response Layer.
- **Akzeptanzkriterium:** Kein Response-/Timing-Unterschied zwischen unbekanntem Nutzer und falschem PW. Generischer HTTP 401 Fehler.
- **Refactoring-Bedarf:** Ein echter E2E-API Test für `POST /api/v1/auth/login/` fehlt! Man muss echte POST-Requests senden und exakt dieselben HTTP-Responses verifizieren, anstatt nur `AuthenticationFailed` exceptions auf Service-Level zu fangen.

---

## 8. `test_preference_service.py`
- **Verknüpfte REQ-L2 ID:** REQ-L1-027 (Aus Parent-Dokument)
- **Aktuelles Verhalten (Shallow?):** **Nein (Gute Integration)**. Testet DB-Inserts und Merge-Logiken tiefgehend.
- **Akzeptanzkriterium:** Preferences (Visibility Updates etc.).
- **Refactoring-Bedarf:** Keine Änderungen am Service-Test nötig, lediglich REST-Level Tests sollten auf Existenz geprüft werden.

---

## 9. `test_seed_demo.py` / `test_tenant_context.py`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AT-008, REQ-L1-010
- **Aktuelles Verhalten (Shallow?):** **Nein (Deep)**. Das sind klassische DB- und Command-Integrationstests.
- **Akzeptanzkriterium:** Tenant-Isolation und Seed.
- **Refactoring-Bedarf:** Keine Änderungen notwendig.

---

## Gesamtfazit & Dringlichste Refactorings

Das Test-Design ist extrem service-lastig. Die Domänenlogik (Services) ist sehr gut per DB getestet. **Shallow Testing betrifft fast ausschließlich die REST-API Schicht (die `*_rest.py` Dateien).**

**Konkreter Action-Plan:**
1. **Mock-Bann in REST-Tests:** In `test_api_key_rest.py` und `test_item_permission_rest.py` müssen alle `@patch` Annotations für Services entfernt werden. Tests müssen gegen eine Test-DB laufen (`pytest.mark.django_db`) und über `APIClient` Requests feuern, die tatsächliche Datenveränderungen überprüfen.
2. **Fehlende HTTP/Middleware-Tests:** Für REQ-L2-AT-001, -003, -007 und -016 fehlen die eigentlichen HTTP Middleware-/Permissions-Tests. Es muss nachgewiesen werden, dass die DRF-Middleware und Views tatsächlich `HTTP 401` und `HTTP 403` ausgeben.
