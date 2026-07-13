# Deep Audit: ApplicationServiceSystem Test Coverage

Dieser Report analysiert alle Tests im ApplicationServiceSystem auf Shallow-Testing und listet konkrete Refactoring-Maßnahmen auf.

## Datei: `test_adr_service.py`

### Test: `test_valid_create_passes`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_title_too_short_raises`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_title_too_long_raises`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_description_too_long_raises`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_invalid_status_raises`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_valid_statuses_all_pass`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_from_orm_maps_fields`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_creates_adr_and_emits_event`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.adr_service.Adr.objects, application.adr_service.AdrService._set_tenant_context, application.adr_service.AdrService._assert_write_permission, application.adr_service.AdrService._audit, application.adr_service.AdrService._emit_event, workflow.services.initialize_workflow_states. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`. Verwendet Behavior Verification (`assert_called_...`) anstatt den echten Systemzustand zu verifizieren.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.adr_service.Adr.objects, application.adr_service.AdrService._set_tenant_context, application.adr_service.AdrService._assert_write_permission, application.adr_service.AdrService._audit, application.adr_service.AdrService._emit_event, workflow.services.initialize_workflow_states` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Tausche `assert_called_...` gegen State Verification aus (z.B. prüfe `Entity.objects.count()`, lade das Objekt neu aus der DB und prüfe veränderte Felder).
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_viewer_role_raises_permission_denied`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_invalid_title_raises_validation_error`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.adr_service.AdrService._set_tenant_context, application.adr_service.AdrService._assert_write_permission.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.adr_service.AdrService._set_tenant_context, application.adr_service.AdrService._assert_write_permission` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_workflow_init_failure_is_swallowed`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.adr_service.Adr.objects, application.adr_service.AdrService._set_tenant_context, application.adr_service.AdrService._assert_write_permission, application.adr_service.AdrService._audit, application.adr_service.AdrService._emit_event. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.adr_service.Adr.objects, application.adr_service.AdrService._set_tenant_context, application.adr_service.AdrService._assert_write_permission, application.adr_service.AdrService._audit, application.adr_service.AdrService._emit_event` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_updates_fields_and_increments_version`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.adr_service.Adr.objects, application.adr_service.AdrService._set_tenant_context, application.adr_service.AdrService._assert_write_permission, application.adr_service.AdrService._audit, application.adr_service.AdrService._emit_event. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`. Verwendet Behavior Verification (`assert_called_...`) anstatt den echten Systemzustand zu verifizieren.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.adr_service.Adr.objects, application.adr_service.AdrService._set_tenant_context, application.adr_service.AdrService._assert_write_permission, application.adr_service.AdrService._audit, application.adr_service.AdrService._emit_event` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Tausche `assert_called_...` gegen State Verification aus (z.B. prüfe `Entity.objects.count()`, lade das Objekt neu aus der DB und prüfe veränderte Felder).
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_not_found_raises`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.adr_service.Adr.objects, application.adr_service.AdrService._set_tenant_context, application.adr_service.AdrService._assert_write_permission.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.adr_service.Adr.objects, application.adr_service.AdrService._set_tenant_context, application.adr_service.AdrService._assert_write_permission` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_audit_entry_written_on_update`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.adr_service.Adr.objects, application.adr_service.AdrService._set_tenant_context, application.adr_service.AdrService._assert_write_permission, application.adr_service.AdrService._audit, application.adr_service.AdrService._emit_event. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`. Verwendet Behavior Verification (`assert_called_...`) anstatt den echten Systemzustand zu verifizieren.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.adr_service.Adr.objects, application.adr_service.AdrService._set_tenant_context, application.adr_service.AdrService._assert_write_permission, application.adr_service.AdrService._audit, application.adr_service.AdrService._emit_event` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Tausche `assert_called_...` gegen State Verification aus (z.B. prüfe `Entity.objects.count()`, lade das Objekt neu aus der DB und prüfe veränderte Felder).
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_deletes_and_cascades_tracelinks`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.adr_service.Adr.objects, application.adr_service.AdrService._set_tenant_context, application.adr_service.AdrService._assert_write_permission, application.adr_service.AdrService._audit, application.adr_service.AdrService._emit_event. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`. Verwendet Behavior Verification (`assert_called_...`) anstatt den echten Systemzustand zu verifizieren.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.adr_service.Adr.objects, application.adr_service.AdrService._set_tenant_context, application.adr_service.AdrService._assert_write_permission, application.adr_service.AdrService._audit, application.adr_service.AdrService._emit_event` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Tausche `assert_called_...` gegen State Verification aus (z.B. prüfe `Entity.objects.count()`, lade das Objekt neu aus der DB und prüfe veränderte Felder).
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_not_found_raises`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.adr_service.Adr.objects, application.adr_service.AdrService._set_tenant_context, application.adr_service.AdrService._assert_write_permission.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.adr_service.Adr.objects, application.adr_service.AdrService._set_tenant_context, application.adr_service.AdrService._assert_write_permission` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_get_adr_not_found_raises`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.adr_service.Adr.objects, application.adr_service.AdrService._set_tenant_context.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.adr_service.Adr.objects, application.adr_service.AdrService._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_list_adrs_filters_by_tenant`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.adr_service.Adr.objects, application.adr_service.AdrService._set_tenant_context. Verwendet Behavior Verification (`assert_called_...`) anstatt den echten Systemzustand zu verifizieren.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.adr_service.Adr.objects, application.adr_service.AdrService._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Tausche `assert_called_...` gegen State Verification aus (z.B. prüfe `Entity.objects.count()`, lade das Objekt neu aus der DB und prüfe veränderte Felder).
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_tenant_isolation_different_tenants`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.adr_service.Adr.objects, application.adr_service.AdrService._set_tenant_context.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.adr_service.Adr.objects, application.adr_service.AdrService._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_valid_link_type_delegates_to_trace_link_service`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.adr_service.Adr.objects, application.adr_service.AdrService._set_tenant_context. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`. Verwendet Behavior Verification (`assert_called_...`) anstatt den echten Systemzustand zu verifizieren.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.adr_service.Adr.objects, application.adr_service.AdrService._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Tausche `assert_called_...` gegen State Verification aus (z.B. prüfe `Entity.objects.count()`, lade das Objekt neu aus der DB und prüfe veränderte Felder).
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_invalid_link_type_raises_validation_error`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.adr_service.AdrService._set_tenant_context.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.adr_service.AdrService._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_all_valid_link_types_accepted`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.adr_service.Adr.objects, application.adr_service.AdrService._set_tenant_context. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.adr_service.Adr.objects, application.adr_service.AdrService._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

## Datei: `test_allocation.py`

### Test: `test_create_allocated_to_tracelink`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_allocate_overwrites_previous_allocation`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_allocation_unique_per_requirement`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_coverage_report_all_allocated`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_coverage_report_partial_allocation`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_coverage_report_no_requirements`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

## Datei: `test_architecture_service.py`

### Test: `test_viewer_cannot_create`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-004, REQ-L2-AS-022
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.architecture_service.ServiceBase._set_tenant_context.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_architecture_element()` → version=1, initialer WorkflowState
  - [ ] `update()` → version=2
  - [ ] Parallel-Update mit stale version → `OptimisticLockError`
  - [ ] Delete → zugehörige TraceLinks gelöscht
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.architecture_service.ServiceBase._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_tenant_not_found_raises`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-004, REQ-L2-AS-022
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.architecture_service.ServiceBase._set_tenant_context.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_architecture_element()` → version=1, initialer WorkflowState
  - [ ] `update()` → version=2
  - [ ] Parallel-Update mit stale version → `OptimisticLockError`
  - [ ] Delete → zugehörige TraceLinks gelöscht
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.architecture_service.ServiceBase._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_workspace_not_found_raises`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-004, REQ-L2-AS-022
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.architecture_service.ServiceBase._set_tenant_context. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_architecture_element()` → version=1, initialer WorkflowState
  - [ ] `update()` → version=2
  - [ ] Parallel-Update mit stale version → `OptimisticLockError`
  - [ ] Delete → zugehörige TraceLinks gelöscht
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.architecture_service.ServiceBase._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_create_returns_element_with_version_1`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-004, REQ-L2-AS-022
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.architecture_service.ServiceBase._set_tenant_context. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_architecture_element()` → version=1, initialer WorkflowState
  - [ ] `update()` → version=2
  - [ ] Parallel-Update mit stale version → `OptimisticLockError`
  - [ ] Delete → zugehörige TraceLinks gelöscht
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.architecture_service.ServiceBase._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_audit_called_on_create`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-004, REQ-L2-AS-022
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.architecture_service.ServiceBase._set_tenant_context. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`. Verwendet Behavior Verification (`assert_called_...`) anstatt den echten Systemzustand zu verifizieren.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_architecture_element()` → version=1, initialer WorkflowState
  - [ ] `update()` → version=2
  - [ ] Parallel-Update mit stale version → `OptimisticLockError`
  - [ ] Delete → zugehörige TraceLinks gelöscht
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.architecture_service.ServiceBase._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Tausche `assert_called_...` gegen State Verification aus (z.B. prüfe `Entity.objects.count()`, lade das Objekt neu aus der DB und prüfe veränderte Felder).
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_not_found_raises`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-004, REQ-L2-AS-022
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.architecture_service.ServiceBase._set_tenant_context. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_architecture_element()` → version=1, initialer WorkflowState
  - [ ] `update()` → version=2
  - [ ] Parallel-Update mit stale version → `OptimisticLockError`
  - [ ] Delete → zugehörige TraceLinks gelöscht
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.architecture_service.ServiceBase._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_stale_version_raises_optimistic_lock_error`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-004, REQ-L2-AS-022
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.architecture_service.ServiceBase._set_tenant_context. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_architecture_element()` → version=1, initialer WorkflowState
  - [ ] `update()` → version=2
  - [ ] Parallel-Update mit stale version → `OptimisticLockError`
  - [ ] Delete → zugehörige TraceLinks gelöscht
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.architecture_service.ServiceBase._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_update_success_increments_version`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-004, REQ-L2-AS-022
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.architecture_service.ServiceBase._set_tenant_context. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`. Verwendet Behavior Verification (`assert_called_...`) anstatt den echten Systemzustand zu verifizieren.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_architecture_element()` → version=1, initialer WorkflowState
  - [ ] `update()` → version=2
  - [ ] Parallel-Update mit stale version → `OptimisticLockError`
  - [ ] Delete → zugehörige TraceLinks gelöscht
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.architecture_service.ServiceBase._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Tausche `assert_called_...` gegen State Verification aus (z.B. prüfe `Entity.objects.count()`, lade das Objekt neu aus der DB und prüfe veränderte Felder).
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_update_without_expected_version_skips_lock_check`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-004, REQ-L2-AS-022
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.architecture_service.ServiceBase._set_tenant_context. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`. Verwendet Behavior Verification (`assert_called_...`) anstatt den echten Systemzustand zu verifizieren.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_architecture_element()` → version=1, initialer WorkflowState
  - [ ] `update()` → version=2
  - [ ] Parallel-Update mit stale version → `OptimisticLockError`
  - [ ] Delete → zugehörige TraceLinks gelöscht
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.architecture_service.ServiceBase._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Tausche `assert_called_...` gegen State Verification aus (z.B. prüfe `Entity.objects.count()`, lade das Objekt neu aus der DB und prüfe veränderte Felder).
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_viewer_cannot_update`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-004, REQ-L2-AS-022
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.architecture_service.ServiceBase._set_tenant_context.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_architecture_element()` → version=1, initialer WorkflowState
  - [ ] `update()` → version=2
  - [ ] Parallel-Update mit stale version → `OptimisticLockError`
  - [ ] Delete → zugehörige TraceLinks gelöscht
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.architecture_service.ServiceBase._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_delete_not_found_raises`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-004, REQ-L2-AS-022
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.architecture_service.ServiceBase._set_tenant_context. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_architecture_element()` → version=1, initialer WorkflowState
  - [ ] `update()` → version=2
  - [ ] Parallel-Update mit stale version → `OptimisticLockError`
  - [ ] Delete → zugehörige TraceLinks gelöscht
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.architecture_service.ServiceBase._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_delete_cascades_trace_links`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-004, REQ-L2-AS-022
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.architecture_service.ServiceBase._set_tenant_context. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`. Verwendet Behavior Verification (`assert_called_...`) anstatt den echten Systemzustand zu verifizieren.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_architecture_element()` → version=1, initialer WorkflowState
  - [ ] `update()` → version=2
  - [ ] Parallel-Update mit stale version → `OptimisticLockError`
  - [ ] Delete → zugehörige TraceLinks gelöscht
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.architecture_service.ServiceBase._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Tausche `assert_called_...` gegen State Verification aus (z.B. prüfe `Entity.objects.count()`, lade das Objekt neu aus der DB und prüfe veränderte Felder).
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_get_returns_element`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-004, REQ-L2-AS-022
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.architecture_service.ServiceBase._set_tenant_context. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_architecture_element()` → version=1, initialer WorkflowState
  - [ ] `update()` → version=2
  - [ ] Parallel-Update mit stale version → `OptimisticLockError`
  - [ ] Delete → zugehörige TraceLinks gelöscht
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.architecture_service.ServiceBase._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_get_not_found_raises`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-004, REQ-L2-AS-022
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.architecture_service.ServiceBase._set_tenant_context. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_architecture_element()` → version=1, initialer WorkflowState
  - [ ] `update()` → version=2
  - [ ] Parallel-Update mit stale version → `OptimisticLockError`
  - [ ] Delete → zugehörige TraceLinks gelöscht
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.architecture_service.ServiceBase._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_list_returns_all_elements`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-004, REQ-L2-AS-022
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.architecture_service.ServiceBase._set_tenant_context. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_architecture_element()` → version=1, initialer WorkflowState
  - [ ] `update()` → version=2
  - [ ] Parallel-Update mit stale version → `OptimisticLockError`
  - [ ] Delete → zugehörige TraceLinks gelöscht
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.architecture_service.ServiceBase._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_set_tenant_context_called_on_get`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-004, REQ-L2-AS-022
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`. Verwendet Behavior Verification (`assert_called_...`) anstatt den echten Systemzustand zu verifizieren.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_architecture_element()` → version=1, initialer WorkflowState
  - [ ] `update()` → version=2
  - [ ] Parallel-Update mit stale version → `OptimisticLockError`
  - [ ] Delete → zugehörige TraceLinks gelöscht
- **Exakter Refactoring-Bedarf:**
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Tausche `assert_called_...` gegen State Verification aus (z.B. prüfe `Entity.objects.count()`, lade das Objekt neu aus der DB und prüfe veränderte Felder).
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_create_with_all_valid_element_types`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-004, REQ-L2-AS-022
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_architecture_element()` → version=1, initialer WorkflowState
  - [ ] `update()` → version=2
  - [ ] Parallel-Update mit stale version → `OptimisticLockError`
  - [ ] Delete → zugehörige TraceLinks gelöscht
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_create_normalizes_pascal_case_to_lowercase`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-004, REQ-L2-AS-022
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_architecture_element()` → version=1, initialer WorkflowState
  - [ ] `update()` → version=2
  - [ ] Parallel-Update mit stale version → `OptimisticLockError`
  - [ ] Delete → zugehörige TraceLinks gelöscht
- **Exakter Refactoring-Bedarf:**
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_create_with_invalid_element_type_raises_validation_error`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-004, REQ-L2-AS-022
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.architecture_service.ServiceBase._set_tenant_context.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_architecture_element()` → version=1, initialer WorkflowState
  - [ ] `update()` → version=2
  - [ ] Parallel-Update mit stale version → `OptimisticLockError`
  - [ ] Delete → zugehörige TraceLinks gelöscht
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.architecture_service.ServiceBase._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_create_with_empty_string_raises_validation_error`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-004, REQ-L2-AS-022
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.architecture_service.ServiceBase._set_tenant_context.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_architecture_element()` → version=1, initialer WorkflowState
  - [ ] `update()` → version=2
  - [ ] Parallel-Update mit stale version → `OptimisticLockError`
  - [ ] Delete → zugehörige TraceLinks gelöscht
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.architecture_service.ServiceBase._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_update_with_valid_element_type`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-004, REQ-L2-AS-022
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.architecture_service.ServiceBase._set_tenant_context. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_architecture_element()` → version=1, initialer WorkflowState
  - [ ] `update()` → version=2
  - [ ] Parallel-Update mit stale version → `OptimisticLockError`
  - [ ] Delete → zugehörige TraceLinks gelöscht
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.architecture_service.ServiceBase._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_update_with_invalid_element_type_raises_validation_error`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-004, REQ-L2-AS-022
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.architecture_service.ServiceBase._set_tenant_context. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_architecture_element()` → version=1, initialer WorkflowState
  - [ ] `update()` → version=2
  - [ ] Parallel-Update mit stale version → `OptimisticLockError`
  - [ ] Delete → zugehörige TraceLinks gelöscht
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.architecture_service.ServiceBase._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_update_normalizes_pascal_case_element_type`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-004, REQ-L2-AS-022
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.architecture_service.ServiceBase._set_tenant_context. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_architecture_element()` → version=1, initialer WorkflowState
  - [ ] `update()` → version=2
  - [ ] Parallel-Update mit stale version → `OptimisticLockError`
  - [ ] Delete → zugehörige TraceLinks gelöscht
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.architecture_service.ServiceBase._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_default_element_type_is_component`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-004, REQ-L2-AS-022
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_architecture_element()` → version=1, initialer WorkflowState
  - [ ] `update()` → version=2
  - [ ] Parallel-Update mit stale version → `OptimisticLockError`
  - [ ] Delete → zugehörige TraceLinks gelöscht
- **Exakter Refactoring-Bedarf:**
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_default_rigor_preset_mapping`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-004, REQ-L2-AS-022
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_architecture_element()` → version=1, initialer WorkflowState
  - [ ] `update()` → version=2
  - [ ] Parallel-Update mit stale version → `OptimisticLockError`
  - [ ] Delete → zugehörige TraceLinks gelöscht
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_for_tier_builds_gated_validator`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-004, REQ-L2-AS-022
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_architecture_element()` → version=1, initialer WorkflowState
  - [ ] `update()` → version=2
  - [ ] Parallel-Update mit stale version → `OptimisticLockError`
  - [ ] Delete → zugehörige TraceLinks gelöscht
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_for_tier_unknown_falls_back_to_standard`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-004, REQ-L2-AS-022
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_architecture_element()` → version=1, initialer WorkflowState
  - [ ] `update()` → version=2
  - [ ] Parallel-Update mit stale version → `OptimisticLockError`
  - [ ] Delete → zugehörige TraceLinks gelöscht
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_for_workspace_resolves_tier_via_feature_gate`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-004, REQ-L2-AS-022
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`. Verwendet Behavior Verification (`assert_called_...`) anstatt den echten Systemzustand zu verifizieren.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_architecture_element()` → version=1, initialer WorkflowState
  - [ ] `update()` → version=2
  - [ ] Parallel-Update mit stale version → `OptimisticLockError`
  - [ ] Delete → zugehörige TraceLinks gelöscht
- **Exakter Refactoring-Bedarf:**
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Tausche `assert_called_...` gegen State Verification aus (z.B. prüfe `Entity.objects.count()`, lade das Objekt neu aus der DB und prüfe veränderte Felder).
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_for_workspace_falls_back_to_minimal_on_resolution_error`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-004, REQ-L2-AS-022
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_architecture_element()` → version=1, initialer WorkflowState
  - [ ] `update()` → version=2
  - [ ] Parallel-Update mit stale version → `OptimisticLockError`
  - [ ] Delete → zugehörige TraceLinks gelöscht
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_self_parent_raises`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-004, REQ-L2-AS-022
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_architecture_element()` → version=1, initialer WorkflowState
  - [ ] `update()` → version=2
  - [ ] Parallel-Update mit stale version → `OptimisticLockError`
  - [ ] Delete → zugehörige TraceLinks gelöscht
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_indirect_cycle_raises`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-004, REQ-L2-AS-022
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_architecture_element()` → version=1, initialer WorkflowState
  - [ ] `update()` → version=2
  - [ ] Parallel-Update mit stale version → `OptimisticLockError`
  - [ ] Delete → zugehörige TraceLinks gelöscht
- **Exakter Refactoring-Bedarf:**
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_acyclic_chain_passes`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-004, REQ-L2-AS-022
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_architecture_element()` → version=1, initialer WorkflowState
  - [ ] `update()` → version=2
  - [ ] Parallel-Update mit stale version → `OptimisticLockError`
  - [ ] Delete → zugehörige TraceLinks gelöscht
- **Exakter Refactoring-Bedarf:**
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_i1_skipped_on_minimal`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-004, REQ-L2-AS-022
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_architecture_element()` → version=1, initialer WorkflowState
  - [ ] `update()` → version=2
  - [ ] Parallel-Update mit stale version → `OptimisticLockError`
  - [ ] Delete → zugehörige TraceLinks gelöscht
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_child_level_2_with_parent_level_5_raises`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-004, REQ-L2-AS-022
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_architecture_element()` → version=1, initialer WorkflowState
  - [ ] `update()` → version=2
  - [ ] Parallel-Update mit stale version → `OptimisticLockError`
  - [ ] Delete → zugehörige TraceLinks gelöscht
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_equal_levels_raise`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-004, REQ-L2-AS-022
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_architecture_element()` → version=1, initialer WorkflowState
  - [ ] `update()` → version=2
  - [ ] Parallel-Update mit stale version → `OptimisticLockError`
  - [ ] Delete → zugehörige TraceLinks gelöscht
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_valid_ordering_passes`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-004, REQ-L2-AS-022
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_architecture_element()` → version=1, initialer WorkflowState
  - [ ] `update()` → version=2
  - [ ] Parallel-Update mit stale version → `OptimisticLockError`
  - [ ] Delete → zugehörige TraceLinks gelöscht
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_i2_skipped_on_minimal`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-004, REQ-L2-AS-022
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_architecture_element()` → version=1, initialer WorkflowState
  - [ ] `update()` → version=2
  - [ ] Parallel-Update mit stale version → `OptimisticLockError`
  - [ ] Delete → zugehörige TraceLinks gelöscht
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_i2_skipped_on_create_path_without_element`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-004, REQ-L2-AS-022
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_architecture_element()` → version=1, initialer WorkflowState
  - [ ] `update()` → version=2
  - [ ] Parallel-Update mit stale version → `OptimisticLockError`
  - [ ] Delete → zugehörige TraceLinks gelöscht
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_dangling_parent_raises_on_all_tiers`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-004, REQ-L2-AS-022
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_architecture_element()` → version=1, initialer WorkflowState
  - [ ] `update()` → version=2
  - [ ] Parallel-Update mit stale version → `OptimisticLockError`
  - [ ] Delete → zugehörige TraceLinks gelöscht
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_cross_workspace_parent_raises`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-004, REQ-L2-AS-022
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_architecture_element()` → version=1, initialer WorkflowState
  - [ ] `update()` → version=2
  - [ ] Parallel-Update mit stale version → `OptimisticLockError`
  - [ ] Delete → zugehörige TraceLinks gelöscht
- **Exakter Refactoring-Bedarf:**
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_valid_parent_is_returned_for_reuse`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-004, REQ-L2-AS-022
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_architecture_element()` → version=1, initialer WorkflowState
  - [ ] `update()` → version=2
  - [ ] Parallel-Update mit stale version → `OptimisticLockError`
  - [ ] Delete → zugehörige TraceLinks gelöscht
- **Exakter Refactoring-Bedarf:**
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_none_parent_is_always_valid_root`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-004, REQ-L2-AS-022
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_architecture_element()` → version=1, initialer WorkflowState
  - [ ] `update()` → version=2
  - [ ] Parallel-Update mit stale version → `OptimisticLockError`
  - [ ] Delete → zugehörige TraceLinks gelöscht
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_allocation_to_direct_parent_raises_on_extended`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-004, REQ-L2-AS-022
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_architecture_element()` → version=1, initialer WorkflowState
  - [ ] `update()` → version=2
  - [ ] Parallel-Update mit stale version → `OptimisticLockError`
  - [ ] Delete → zugehörige TraceLinks gelöscht
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_allocation_to_transitive_ancestor_raises`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-004, REQ-L2-AS-022
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_architecture_element()` → version=1, initialer WorkflowState
  - [ ] `update()` → version=2
  - [ ] Parallel-Update mit stale version → `OptimisticLockError`
  - [ ] Delete → zugehörige TraceLinks gelöscht
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_allocation_to_unrelated_element_passes`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-004, REQ-L2-AS-022
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_architecture_element()` → version=1, initialer WorkflowState
  - [ ] `update()` → version=2
  - [ ] Parallel-Update mit stale version → `OptimisticLockError`
  - [ ] Delete → zugehörige TraceLinks gelöscht
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_i4_skipped_below_extended`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-004, REQ-L2-AS-022
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_architecture_element()` → version=1, initialer WorkflowState
  - [ ] `update()` → version=2
  - [ ] Parallel-Update mit stale version → `OptimisticLockError`
  - [ ] Delete → zugehörige TraceLinks gelöscht
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_create_with_parent_runs_validator`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-004, REQ-L2-AS-022
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Verwendet Behavior Verification (`assert_called_...`) anstatt den echten Systemzustand zu verifizieren.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_architecture_element()` → version=1, initialer WorkflowState
  - [ ] `update()` → version=2
  - [ ] Parallel-Update mit stale version → `OptimisticLockError`
  - [ ] Delete → zugehörige TraceLinks gelöscht
- **Exakter Refactoring-Bedarf:**
  - Tausche `assert_called_...` gegen State Verification aus (z.B. prüfe `Entity.objects.count()`, lade das Objekt neu aus der DB und prüfe veränderte Felder).
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_create_without_parent_skips_validator`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-004, REQ-L2-AS-022
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_architecture_element()` → version=1, initialer WorkflowState
  - [ ] `update()` → version=2
  - [ ] Parallel-Update mit stale version → `OptimisticLockError`
  - [ ] Delete → zugehörige TraceLinks gelöscht
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_create_with_invalid_parent_raises_validation_error`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-004, REQ-L2-AS-022
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_architecture_element()` → version=1, initialer WorkflowState
  - [ ] `update()` → version=2
  - [ ] Parallel-Update mit stale version → `OptimisticLockError`
  - [ ] Delete → zugehörige TraceLinks gelöscht
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_update_with_parent_id_validates_and_persists`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-004, REQ-L2-AS-022
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`. Verwendet Behavior Verification (`assert_called_...`) anstatt den echten Systemzustand zu verifizieren.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_architecture_element()` → version=1, initialer WorkflowState
  - [ ] `update()` → version=2
  - [ ] Parallel-Update mit stale version → `OptimisticLockError`
  - [ ] Delete → zugehörige TraceLinks gelöscht
- **Exakter Refactoring-Bedarf:**
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Tausche `assert_called_...` gegen State Verification aus (z.B. prüfe `Entity.objects.count()`, lade das Objekt neu aus der DB und prüfe veränderte Felder).
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_update_detach_parent_persists_none_without_validation`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-004, REQ-L2-AS-022
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_architecture_element()` → version=1, initialer WorkflowState
  - [ ] `update()` → version=2
  - [ ] Parallel-Update mit stale version → `OptimisticLockError`
  - [ ] Delete → zugehörige TraceLinks gelöscht
- **Exakter Refactoring-Bedarf:**
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_update_without_parent_id_leaves_parent_untouched`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-004, REQ-L2-AS-022
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_architecture_element()` → version=1, initialer WorkflowState
  - [ ] `update()` → version=2
  - [ ] Parallel-Update mit stale version → `OptimisticLockError`
  - [ ] Delete → zugehörige TraceLinks gelöscht
- **Exakter Refactoring-Bedarf:**
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

## Datei: `test_artifact_diff_service.py`

### Test: `test_diff_first_to_current_version`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-032
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.artifact_diff_service.Artifact. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] REST-API-Endpunkt GET /artifacts/{id}/diff?from=v1&to=v2 gibt strukturiertes JSON-Diff zurück
  - [ ] Diff enthält: hinzugefügte Felder, geänderte Felder (alt→neu), gelöschte Felder
  - [ ] Vergleich beliebiger Versionen (nicht nur aufeinanderfolgende) ist möglich
  - [ ] Markdown-Felder werden als Text-Diff dargestellt
  - [ ] Diff-Berechnung ≤ 500ms für Artefakte mit bis zu 50 Feldern
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.artifact_diff_service.Artifact` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_diff_scalar_field_change`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-032
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] REST-API-Endpunkt GET /artifacts/{id}/diff?from=v1&to=v2 gibt strukturiertes JSON-Diff zurück
  - [ ] Diff enthält: hinzugefügte Felder, geänderte Felder (alt→neu), gelöschte Felder
  - [ ] Vergleich beliebiger Versionen (nicht nur aufeinanderfolgende) ist möglich
  - [ ] Markdown-Felder werden als Text-Diff dargestellt
  - [ ] Diff-Berechnung ≤ 500ms für Artefakte mit bis zu 50 Feldern
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_diff_markdown_field_line_diff`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-032
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] REST-API-Endpunkt GET /artifacts/{id}/diff?from=v1&to=v2 gibt strukturiertes JSON-Diff zurück
  - [ ] Diff enthält: hinzugefügte Felder, geänderte Felder (alt→neu), gelöschte Felder
  - [ ] Vergleich beliebiger Versionen (nicht nur aufeinanderfolgende) ist möglich
  - [ ] Markdown-Felder werden als Text-Diff dargestellt
  - [ ] Diff-Berechnung ≤ 500ms für Artefakte mit bis zu 50 Feldern
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_diff_unchanged_field_marked`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-032
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] REST-API-Endpunkt GET /artifacts/{id}/diff?from=v1&to=v2 gibt strukturiertes JSON-Diff zurück
  - [ ] Diff enthält: hinzugefügte Felder, geänderte Felder (alt→neu), gelöschte Felder
  - [ ] Vergleich beliebiger Versionen (nicht nur aufeinanderfolgende) ist möglich
  - [ ] Markdown-Felder werden als Text-Diff dargestellt
  - [ ] Diff-Berechnung ≤ 500ms für Artefakte mit bis zu 50 Feldern
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_diff_invalid_version_raises_not_found`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-032
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.artifact_diff_service.Artifact.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] REST-API-Endpunkt GET /artifacts/{id}/diff?from=v1&to=v2 gibt strukturiertes JSON-Diff zurück
  - [ ] Diff enthält: hinzugefügte Felder, geänderte Felder (alt→neu), gelöschte Felder
  - [ ] Vergleich beliebiger Versionen (nicht nur aufeinanderfolgende) ist möglich
  - [ ] Markdown-Felder werden als Text-Diff dargestellt
  - [ ] Diff-Berechnung ≤ 500ms für Artefakte mit bis zu 50 Feldern
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.artifact_diff_service.Artifact` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_diff_unsupported_artifact_type`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-032
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.artifact_diff_service.Artifact.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] REST-API-Endpunkt GET /artifacts/{id}/diff?from=v1&to=v2 gibt strukturiertes JSON-Diff zurück
  - [ ] Diff enthält: hinzugefügte Felder, geänderte Felder (alt→neu), gelöschte Felder
  - [ ] Vergleich beliebiger Versionen (nicht nur aufeinanderfolgende) ist möglich
  - [ ] Markdown-Felder werden als Text-Diff dargestellt
  - [ ] Diff-Berechnung ≤ 500ms für Artefakte mit bis zu 50 Feldern
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.artifact_diff_service.Artifact` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_diff_tenant_isolation`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-032
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.artifact_diff_service.Artifact. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`. Verwendet Behavior Verification (`assert_called_...`) anstatt den echten Systemzustand zu verifizieren.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] REST-API-Endpunkt GET /artifacts/{id}/diff?from=v1&to=v2 gibt strukturiertes JSON-Diff zurück
  - [ ] Diff enthält: hinzugefügte Felder, geänderte Felder (alt→neu), gelöschte Felder
  - [ ] Vergleich beliebiger Versionen (nicht nur aufeinanderfolgende) ist möglich
  - [ ] Markdown-Felder werden als Text-Diff dargestellt
  - [ ] Diff-Berechnung ≤ 500ms für Artefakte mit bis zu 50 Feldern
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.artifact_diff_service.Artifact` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Tausche `assert_called_...` gegen State Verification aus (z.B. prüfe `Entity.objects.count()`, lade das Objekt neu aus der DB und prüfe veränderte Felder).
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_diff_architecture_element`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-032
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.artifact_diff_service.Artifact. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] REST-API-Endpunkt GET /artifacts/{id}/diff?from=v1&to=v2 gibt strukturiertes JSON-Diff zurück
  - [ ] Diff enthält: hinzugefügte Felder, geänderte Felder (alt→neu), gelöschte Felder
  - [ ] Vergleich beliebiger Versionen (nicht nur aufeinanderfolgende) ist möglich
  - [ ] Markdown-Felder werden als Text-Diff dargestellt
  - [ ] Diff-Berechnung ≤ 500ms für Artefakte mit bis zu 50 Feldern
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.artifact_diff_service.Artifact` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_diff_testcase_json_field`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-032
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] REST-API-Endpunkt GET /artifacts/{id}/diff?from=v1&to=v2 gibt strukturiertes JSON-Diff zurück
  - [ ] Diff enthält: hinzugefügte Felder, geänderte Felder (alt→neu), gelöschte Felder
  - [ ] Vergleich beliebiger Versionen (nicht nur aufeinanderfolgende) ist möglich
  - [ ] Markdown-Felder werden als Text-Diff dargestellt
  - [ ] Diff-Berechnung ≤ 500ms für Artefakte mit bis zu 50 Feldern
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_diff_note_when_from_version_unavailable`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-032
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.artifact_diff_service.Artifact. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] REST-API-Endpunkt GET /artifacts/{id}/diff?from=v1&to=v2 gibt strukturiertes JSON-Diff zurück
  - [ ] Diff enthält: hinzugefügte Felder, geänderte Felder (alt→neu), gelöschte Felder
  - [ ] Vergleich beliebiger Versionen (nicht nur aufeinanderfolgende) ist möglich
  - [ ] Markdown-Felder werden als Text-Diff dargestellt
  - [ ] Diff-Berechnung ≤ 500ms für Artefakte mit bis zu 50 Feldern
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.artifact_diff_service.Artifact` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_list_versions_returns_baseline_and_current`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-032
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.artifact_diff_service.Artifact. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] REST-API-Endpunkt GET /artifacts/{id}/diff?from=v1&to=v2 gibt strukturiertes JSON-Diff zurück
  - [ ] Diff enthält: hinzugefügte Felder, geänderte Felder (alt→neu), gelöschte Felder
  - [ ] Vergleich beliebiger Versionen (nicht nur aufeinanderfolgende) ist möglich
  - [ ] Markdown-Felder werden als Text-Diff dargestellt
  - [ ] Diff-Berechnung ≤ 500ms für Artefakte mit bis zu 50 Feldern
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.artifact_diff_service.Artifact` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

## Datei: `test_artifact_service.py`

### Test: `test_create_success_returns_artifact`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-001, REQ-L2-AS-002, REQ-L2-AS-018, REQ-L2-AS-022
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.artifact_service.TenantContext, application.artifact_service.ServiceBase._set_tenant_context, application.artifact_service.ServiceBase._assert_write_permission, application.artifact_service.ServiceBase._audit, application.artifact_service.ServiceBase._emit_event. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] Kette A→B→C, versuche C.parent=A → Exception `"Cycle detected: A→B→C→A"`
  - [ ] Versuche A.parent=A → Exception `"Cycle detected: self-reference"`
  - [ ] Gültige Parent-Änderung → erfolgreich
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.artifact_service.TenantContext, application.artifact_service.ServiceBase._set_tenant_context, application.artifact_service.ServiceBase._assert_write_permission, application.artifact_service.ServiceBase._audit, application.artifact_service.ServiceBase._emit_event` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_viewer_cannot_create`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-001, REQ-L2-AS-002, REQ-L2-AS-018, REQ-L2-AS-022
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.artifact_service.ServiceBase._set_tenant_context.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] Kette A→B→C, versuche C.parent=A → Exception `"Cycle detected: A→B→C→A"`
  - [ ] Versuche A.parent=A → Exception `"Cycle detected: self-reference"`
  - [ ] Gültige Parent-Änderung → erfolgreich
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.artifact_service.ServiceBase._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_workspace_not_found_raises`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-001, REQ-L2-AS-002, REQ-L2-AS-018, REQ-L2-AS-022
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.artifact_service.ServiceBase._set_tenant_context, application.artifact_service.ServiceBase._assert_write_permission.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] Kette A→B→C, versuche C.parent=A → Exception `"Cycle detected: A→B→C→A"`
  - [ ] Versuche A.parent=A → Exception `"Cycle detected: self-reference"`
  - [ ] Gültige Parent-Änderung → erfolgreich
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.artifact_service.ServiceBase._set_tenant_context, application.artifact_service.ServiceBase._assert_write_permission` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_audit_called_on_create`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-001, REQ-L2-AS-002, REQ-L2-AS-018, REQ-L2-AS-022
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.artifact_service.ServiceBase._set_tenant_context, application.artifact_service.ServiceBase._assert_write_permission. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`. Verwendet Behavior Verification (`assert_called_...`) anstatt den echten Systemzustand zu verifizieren.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] Kette A→B→C, versuche C.parent=A → Exception `"Cycle detected: A→B→C→A"`
  - [ ] Versuche A.parent=A → Exception `"Cycle detected: self-reference"`
  - [ ] Gültige Parent-Änderung → erfolgreich
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.artifact_service.ServiceBase._set_tenant_context, application.artifact_service.ServiceBase._assert_write_permission` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Tausche `assert_called_...` gegen State Verification aus (z.B. prüfe `Entity.objects.count()`, lade das Objekt neu aus der DB und prüfe veränderte Felder).
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_event_emitted_on_create`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-001, REQ-L2-AS-002, REQ-L2-AS-018, REQ-L2-AS-022
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.artifact_service.ServiceBase._set_tenant_context, application.artifact_service.ServiceBase._assert_write_permission. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`. Verwendet Behavior Verification (`assert_called_...`) anstatt den echten Systemzustand zu verifizieren.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] Kette A→B→C, versuche C.parent=A → Exception `"Cycle detected: A→B→C→A"`
  - [ ] Versuche A.parent=A → Exception `"Cycle detected: self-reference"`
  - [ ] Gültige Parent-Änderung → erfolgreich
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.artifact_service.ServiceBase._set_tenant_context, application.artifact_service.ServiceBase._assert_write_permission` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Tausche `assert_called_...` gegen State Verification aus (z.B. prüfe `Entity.objects.count()`, lade das Objekt neu aus der DB und prüfe veränderte Felder).
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_self_reference_raises_validation_error`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-001, REQ-L2-AS-002, REQ-L2-AS-018, REQ-L2-AS-022
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] Kette A→B→C, versuche C.parent=A → Exception `"Cycle detected: A→B→C→A"`
  - [ ] Versuche A.parent=A → Exception `"Cycle detected: self-reference"`
  - [ ] Gültige Parent-Änderung → erfolgreich
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_no_parent_is_noop`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-001, REQ-L2-AS-002, REQ-L2-AS-018, REQ-L2-AS-022
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] Kette A→B→C, versuche C.parent=A → Exception `"Cycle detected: A→B→C→A"`
  - [ ] Versuche A.parent=A → Exception `"Cycle detected: self-reference"`
  - [ ] Gültige Parent-Änderung → erfolgreich
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_chain_cycle_detected`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-001, REQ-L2-AS-002, REQ-L2-AS-018, REQ-L2-AS-022
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] Kette A→B→C, versuche C.parent=A → Exception `"Cycle detected: A→B→C→A"`
  - [ ] Versuche A.parent=A → Exception `"Cycle detected: self-reference"`
  - [ ] Gültige Parent-Änderung → erfolgreich
- **Exakter Refactoring-Bedarf:**
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_detect_cycle_returns_none_when_no_cycle`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-001, REQ-L2-AS-002, REQ-L2-AS-018, REQ-L2-AS-022
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.artifact_service.Artifact.unscoped. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] Kette A→B→C, versuche C.parent=A → Exception `"Cycle detected: A→B→C→A"`
  - [ ] Versuche A.parent=A → Exception `"Cycle detected: self-reference"`
  - [ ] Gültige Parent-Änderung → erfolgreich
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.artifact_service.Artifact.unscoped` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_update_not_found_raises`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-001, REQ-L2-AS-002, REQ-L2-AS-018, REQ-L2-AS-022
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.artifact_service.ServiceBase._set_tenant_context, application.artifact_service.ServiceBase._assert_write_permission. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] Kette A→B→C, versuche C.parent=A → Exception `"Cycle detected: A→B→C→A"`
  - [ ] Versuche A.parent=A → Exception `"Cycle detected: self-reference"`
  - [ ] Gültige Parent-Änderung → erfolgreich
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.artifact_service.ServiceBase._set_tenant_context, application.artifact_service.ServiceBase._assert_write_permission` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_update_type_success`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-001, REQ-L2-AS-002, REQ-L2-AS-018, REQ-L2-AS-022
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.artifact_service.ServiceBase._set_tenant_context, application.artifact_service.ServiceBase._assert_write_permission. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`. Verwendet Behavior Verification (`assert_called_...`) anstatt den echten Systemzustand zu verifizieren.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] Kette A→B→C, versuche C.parent=A → Exception `"Cycle detected: A→B→C→A"`
  - [ ] Versuche A.parent=A → Exception `"Cycle detected: self-reference"`
  - [ ] Gültige Parent-Änderung → erfolgreich
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.artifact_service.ServiceBase._set_tenant_context, application.artifact_service.ServiceBase._assert_write_permission` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Tausche `assert_called_...` gegen State Verification aus (z.B. prüfe `Entity.objects.count()`, lade das Objekt neu aus der DB und prüfe veränderte Felder).
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_delete_not_found_raises`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-001, REQ-L2-AS-002, REQ-L2-AS-018, REQ-L2-AS-022
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.artifact_service.ServiceBase._set_tenant_context, application.artifact_service.ServiceBase._assert_write_permission. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] Kette A→B→C, versuche C.parent=A → Exception `"Cycle detected: A→B→C→A"`
  - [ ] Versuche A.parent=A → Exception `"Cycle detected: self-reference"`
  - [ ] Gültige Parent-Änderung → erfolgreich
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.artifact_service.ServiceBase._set_tenant_context, application.artifact_service.ServiceBase._assert_write_permission` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_delete_cascades_trace_links`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-001, REQ-L2-AS-002, REQ-L2-AS-018, REQ-L2-AS-022
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.artifact_service.ServiceBase._set_tenant_context, application.artifact_service.ServiceBase._assert_write_permission. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`. Verwendet Behavior Verification (`assert_called_...`) anstatt den echten Systemzustand zu verifizieren.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] Kette A→B→C, versuche C.parent=A → Exception `"Cycle detected: A→B→C→A"`
  - [ ] Versuche A.parent=A → Exception `"Cycle detected: self-reference"`
  - [ ] Gültige Parent-Änderung → erfolgreich
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.artifact_service.ServiceBase._set_tenant_context, application.artifact_service.ServiceBase._assert_write_permission` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Tausche `assert_called_...` gegen State Verification aus (z.B. prüfe `Entity.objects.count()`, lade das Objekt neu aus der DB und prüfe veränderte Felder).
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_get_returns_artifact`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-001, REQ-L2-AS-002, REQ-L2-AS-018, REQ-L2-AS-022
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.artifact_service.ServiceBase._set_tenant_context. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] Kette A→B→C, versuche C.parent=A → Exception `"Cycle detected: A→B→C→A"`
  - [ ] Versuche A.parent=A → Exception `"Cycle detected: self-reference"`
  - [ ] Gültige Parent-Änderung → erfolgreich
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.artifact_service.ServiceBase._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_get_not_found_raises`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-001, REQ-L2-AS-002, REQ-L2-AS-018, REQ-L2-AS-022
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.artifact_service.ServiceBase._set_tenant_context. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] Kette A→B→C, versuche C.parent=A → Exception `"Cycle detected: A→B→C→A"`
  - [ ] Versuche A.parent=A → Exception `"Cycle detected: self-reference"`
  - [ ] Gültige Parent-Änderung → erfolgreich
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.artifact_service.ServiceBase._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_set_tenant_context_called_on_get`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-001, REQ-L2-AS-002, REQ-L2-AS-018, REQ-L2-AS-022
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`. Verwendet Behavior Verification (`assert_called_...`) anstatt den echten Systemzustand zu verifizieren.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] Kette A→B→C, versuche C.parent=A → Exception `"Cycle detected: A→B→C→A"`
  - [ ] Versuche A.parent=A → Exception `"Cycle detected: self-reference"`
  - [ ] Gültige Parent-Änderung → erfolgreich
- **Exakter Refactoring-Bedarf:**
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Tausche `assert_called_...` gegen State Verification aus (z.B. prüfe `Entity.objects.count()`, lade das Objekt neu aus der DB und prüfe veränderte Felder).
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_set_tenant_context_called_on_create`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-001, REQ-L2-AS-002, REQ-L2-AS-018, REQ-L2-AS-022
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.artifact_service.ServiceBase._assert_write_permission. Verwendet Behavior Verification (`assert_called_...`) anstatt den echten Systemzustand zu verifizieren.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] Kette A→B→C, versuche C.parent=A → Exception `"Cycle detected: A→B→C→A"`
  - [ ] Versuche A.parent=A → Exception `"Cycle detected: self-reference"`
  - [ ] Gültige Parent-Änderung → erfolgreich
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.artifact_service.ServiceBase._assert_write_permission` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Tausche `assert_called_...` gegen State Verification aus (z.B. prüfe `Entity.objects.count()`, lade das Objekt neu aus der DB und prüfe veränderte Felder).
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

## Datei: `test_baseline_facade.py`

### Test: `test_delegates_to_baseline_build`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-006
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.baseline_facade.TenantContext, application.baseline_facade.ServiceBase._audit, application.baseline_facade.ServiceBase._emit_event. Verwendet Behavior Verification (`assert_called_...`) anstatt den echten Systemzustand zu verifizieren.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `export(format="json", scope=workspace)` → gültige JSON-Datei
  - [ ] `export(format="csv", scope=workspace)` → CSV mit Header-Zeile
  - [ ] 1.000 Requirements in < 5 Sekunden exportiert
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.baseline_facade.TenantContext, application.baseline_facade.ServiceBase._audit, application.baseline_facade.ServiceBase._emit_event` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Tausche `assert_called_...` gegen State Verification aus (z.B. prüfe `Entity.objects.count()`, lade das Objekt neu aus der DB und prüfe veränderte Felder).
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_scope_not_allowed_raises_validation_error`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-006
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.baseline_facade.TenantContext.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `export(format="json", scope=workspace)` → gültige JSON-Datei
  - [ ] `export(format="csv", scope=workspace)` → CSV mit Header-Zeile
  - [ ] 1.000 Requirements in < 5 Sekunden exportiert
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.baseline_facade.TenantContext` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_viewer_cannot_create`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-006
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.baseline_facade.TenantContext.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `export(format="json", scope=workspace)` → gültige JSON-Datei
  - [ ] `export(format="csv", scope=workspace)` → CSV mit Header-Zeile
  - [ ] 1.000 Requirements in < 5 Sekunden exportiert
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.baseline_facade.TenantContext` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_audit_called_after_create`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-006
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.baseline_facade.TenantContext, application.baseline_facade.BaselineFacade._check_scope_allowed. Verwendet Behavior Verification (`assert_called_...`) anstatt den echten Systemzustand zu verifizieren.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `export(format="json", scope=workspace)` → gültige JSON-Datei
  - [ ] `export(format="csv", scope=workspace)` → CSV mit Header-Zeile
  - [ ] 1.000 Requirements in < 5 Sekunden exportiert
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.baseline_facade.TenantContext, application.baseline_facade.BaselineFacade._check_scope_allowed` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Tausche `assert_called_...` gegen State Verification aus (z.B. prüfe `Entity.objects.count()`, lade das Objekt neu aus der DB und prüfe veränderte Felder).
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_domain_event_emitted`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-006
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.baseline_facade.TenantContext, application.baseline_facade.BaselineFacade._check_scope_allowed. Verwendet Behavior Verification (`assert_called_...`) anstatt den echten Systemzustand zu verifizieren.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `export(format="json", scope=workspace)` → gültige JSON-Datei
  - [ ] `export(format="csv", scope=workspace)` → CSV mit Header-Zeile
  - [ ] 1.000 Requirements in < 5 Sekunden exportiert
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.baseline_facade.TenantContext, application.baseline_facade.BaselineFacade._check_scope_allowed` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Tausche `assert_called_...` gegen State Verification aus (z.B. prüfe `Entity.objects.count()`, lade das Objekt neu aus der DB und prüfe veränderte Felder).
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_delegates_to_baseline_diff`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-006
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.baseline_facade.TenantContext. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`. Verwendet Behavior Verification (`assert_called_...`) anstatt den echten Systemzustand zu verifizieren.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `export(format="json", scope=workspace)` → gültige JSON-Datei
  - [ ] `export(format="csv", scope=workspace)` → CSV mit Header-Zeile
  - [ ] 1.000 Requirements in < 5 Sekunden exportiert
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.baseline_facade.TenantContext` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Tausche `assert_called_...` gegen State Verification aus (z.B. prüfe `Entity.objects.count()`, lade das Objekt neu aus der DB und prüfe veränderte Felder).
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_remaps_scope_not_allowed`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-006
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `export(format="json", scope=workspace)` → gültige JSON-Datei
  - [ ] `export(format="csv", scope=workspace)` → CSV mit Header-Zeile
  - [ ] 1.000 Requirements in < 5 Sekunden exportiert
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_remaps_baseline_not_found`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-006
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `export(format="json", scope=workspace)` → gültige JSON-Datei
  - [ ] `export(format="csv", scope=workspace)` → CSV mit Header-Zeile
  - [ ] 1.000 Requirements in < 5 Sekunden exportiert
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_passes_through_unknown`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-006
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `export(format="json", scope=workspace)` → gültige JSON-Datei
  - [ ] `export(format="csv", scope=workspace)` → CSV mit Header-Zeile
  - [ ] 1.000 Requirements in < 5 Sekunden exportiert
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_calls_preset_policy`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-006
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`. Verwendet Behavior Verification (`assert_called_...`) anstatt den echten Systemzustand zu verifizieren.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `export(format="json", scope=workspace)` → gültige JSON-Datei
  - [ ] `export(format="csv", scope=workspace)` → CSV mit Header-Zeile
  - [ ] 1.000 Requirements in < 5 Sekunden exportiert
- **Exakter Refactoring-Bedarf:**
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Tausche `assert_called_...` gegen State Verification aus (z.B. prüfe `Entity.objects.count()`, lade das Objekt neu aus der DB und prüfe veränderte Felder).
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_raises_when_denied`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-006
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `export(format="json", scope=workspace)` → gültige JSON-Datei
  - [ ] `export(format="csv", scope=workspace)` → CSV mit Header-Zeile
  - [ ] 1.000 Requirements in < 5 Sekunden exportiert
- **Exakter Refactoring-Bedarf:**
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

## Datei: `test_event_bus.py`

### Test: `test_construction_with_defaults`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-017, REQ-L2-AS-019, REQ-L2-AS-029
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] Requirement erstellt → HTTP POST an Webhook-URL mit JSON-Payload
  - [ ] Dispatch asynchron → `create_requirement()` kehrt zurück bevor Webhook-Response
  - [ ] Ziel-URL nicht erreichbar → Retry-Logik, ursprüngliche Operation nicht blockiert
  - [ ] Webhook deaktiviert → kein Dispatch
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_to_dict_contains_all_fields`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-017, REQ-L2-AS-019, REQ-L2-AS-029
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] Requirement erstellt → HTTP POST an Webhook-URL mit JSON-Payload
  - [ ] Dispatch asynchron → `create_requirement()` kehrt zurück bevor Webhook-Response
  - [ ] Ziel-URL nicht erreichbar → Retry-Logik, ursprüngliche Operation nicht blockiert
  - [ ] Webhook deaktiviert → kein Dispatch
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_to_dict_payload_merged_at_top_level`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-017, REQ-L2-AS-019, REQ-L2-AS-029
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] Requirement erstellt → HTTP POST an Webhook-URL mit JSON-Payload
  - [ ] Dispatch asynchron → `create_requirement()` kehrt zurück bevor Webhook-Response
  - [ ] Ziel-URL nicht erreichbar → Retry-Logik, ursprüngliche Operation nicht blockiert
  - [ ] Webhook deaktiviert → kein Dispatch
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_register_and_get_subscribers`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-017, REQ-L2-AS-019, REQ-L2-AS-029
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] Requirement erstellt → HTTP POST an Webhook-URL mit JSON-Payload
  - [ ] Dispatch asynchron → `create_requirement()` kehrt zurück bevor Webhook-Response
  - [ ] Ziel-URL nicht erreichbar → Retry-Logik, ursprüngliche Operation nicht blockiert
  - [ ] Webhook deaktiviert → kein Dispatch
- **Exakter Refactoring-Bedarf:**
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_register_same_subscriber_twice_is_idempotent`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-017, REQ-L2-AS-019, REQ-L2-AS-029
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] Requirement erstellt → HTTP POST an Webhook-URL mit JSON-Payload
  - [ ] Dispatch asynchron → `create_requirement()` kehrt zurück bevor Webhook-Response
  - [ ] Ziel-URL nicht erreichbar → Retry-Logik, ursprüngliche Operation nicht blockiert
  - [ ] Webhook deaktiviert → kein Dispatch
- **Exakter Refactoring-Bedarf:**
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_unregister_removes_subscriber`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-017, REQ-L2-AS-019, REQ-L2-AS-029
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] Requirement erstellt → HTTP POST an Webhook-URL mit JSON-Payload
  - [ ] Dispatch asynchron → `create_requirement()` kehrt zurück bevor Webhook-Response
  - [ ] Ziel-URL nicht erreichbar → Retry-Logik, ursprüngliche Operation nicht blockiert
  - [ ] Webhook deaktiviert → kein Dispatch
- **Exakter Refactoring-Bedarf:**
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_unregister_nonexistent_is_noop`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-017, REQ-L2-AS-019, REQ-L2-AS-029
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] Requirement erstellt → HTTP POST an Webhook-URL mit JSON-Payload
  - [ ] Dispatch asynchron → `create_requirement()` kehrt zurück bevor Webhook-Response
  - [ ] Ziel-URL nicht erreichbar → Retry-Logik, ursprüngliche Operation nicht blockiert
  - [ ] Webhook deaktiviert → kein Dispatch
- **Exakter Refactoring-Bedarf:**
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_get_subscribers_for_unknown_type_returns_empty`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-017, REQ-L2-AS-019, REQ-L2-AS-029
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] Requirement erstellt → HTTP POST an Webhook-URL mit JSON-Payload
  - [ ] Dispatch asynchron → `create_requirement()` kehrt zurück bevor Webhook-Response
  - [ ] Ziel-URL nicht erreichbar → Retry-Logik, ursprüngliche Operation nicht blockiert
  - [ ] Webhook deaktiviert → kein Dispatch
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_multiple_subscribers_per_event_type`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-017, REQ-L2-AS-019, REQ-L2-AS-029
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] Requirement erstellt → HTTP POST an Webhook-URL mit JSON-Payload
  - [ ] Dispatch asynchron → `create_requirement()` kehrt zurück bevor Webhook-Response
  - [ ] Ziel-URL nicht erreichbar → Retry-Logik, ursprüngliche Operation nicht blockiert
  - [ ] Webhook deaktiviert → kein Dispatch
- **Exakter Refactoring-Bedarf:**
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_all_subscribers_returns_copy`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-017, REQ-L2-AS-019, REQ-L2-AS-029
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] Requirement erstellt → HTTP POST an Webhook-URL mit JSON-Payload
  - [ ] Dispatch asynchron → `create_requirement()` kehrt zurück bevor Webhook-Response
  - [ ] Ziel-URL nicht erreichbar → Retry-Logik, ursprüngliche Operation nicht blockiert
  - [ ] Webhook deaktiviert → kein Dispatch
- **Exakter Refactoring-Bedarf:**
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_get_subscribers_returns_snapshot`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-017, REQ-L2-AS-019, REQ-L2-AS-029
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] Requirement erstellt → HTTP POST an Webhook-URL mit JSON-Payload
  - [ ] Dispatch asynchron → `create_requirement()` kehrt zurück bevor Webhook-Response
  - [ ] Ziel-URL nicht erreichbar → Retry-Logik, ursprüngliche Operation nicht blockiert
  - [ ] Webhook deaktiviert → kein Dispatch
- **Exakter Refactoring-Bedarf:**
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_get_event_bus_returns_same_instance`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-017, REQ-L2-AS-019, REQ-L2-AS-029
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] Requirement erstellt → HTTP POST an Webhook-URL mit JSON-Payload
  - [ ] Dispatch asynchron → `create_requirement()` kehrt zurück bevor Webhook-Response
  - [ ] Ziel-URL nicht erreichbar → Retry-Logik, ursprüngliche Operation nicht blockiert
  - [ ] Webhook deaktiviert → kein Dispatch
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_domain_event_bus_is_singleton`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-017, REQ-L2-AS-019, REQ-L2-AS-029
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] Requirement erstellt → HTTP POST an Webhook-URL mit JSON-Payload
  - [ ] Dispatch asynchron → `create_requirement()` kehrt zurück bevor Webhook-Response
  - [ ] Ziel-URL nicht erreichbar → Retry-Logik, ursprüngliche Operation nicht blockiert
  - [ ] Webhook deaktiviert → kein Dispatch
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_register_and_unregister_subscriber`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-017, REQ-L2-AS-019, REQ-L2-AS-029
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] Requirement erstellt → HTTP POST an Webhook-URL mit JSON-Payload
  - [ ] Dispatch asynchron → `create_requirement()` kehrt zurück bevor Webhook-Response
  - [ ] Ziel-URL nicht erreichbar → Retry-Logik, ursprüngliche Operation nicht blockiert
  - [ ] Webhook deaktiviert → kein Dispatch
- **Exakter Refactoring-Bedarf:**
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_get_subscriber_registry_returns_dict`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-017, REQ-L2-AS-019, REQ-L2-AS-029
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] Requirement erstellt → HTTP POST an Webhook-URL mit JSON-Payload
  - [ ] Dispatch asynchron → `create_requirement()` kehrt zurück bevor Webhook-Response
  - [ ] Ziel-URL nicht erreichbar → Retry-Logik, ursprüngliche Operation nicht blockiert
  - [ ] Webhook deaktiviert → kein Dispatch
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_publish_registers_on_commit_callback`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-017, REQ-L2-AS-019, REQ-L2-AS-029
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.event_bus.transaction.on_commit. Verwendet Behavior Verification (`assert_called_...`) anstatt den echten Systemzustand zu verifizieren.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] Requirement erstellt → HTTP POST an Webhook-URL mit JSON-Payload
  - [ ] Dispatch asynchron → `create_requirement()` kehrt zurück bevor Webhook-Response
  - [ ] Ziel-URL nicht erreichbar → Retry-Logik, ursprüngliche Operation nicht blockiert
  - [ ] Webhook deaktiviert → kein Dispatch
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.event_bus.transaction.on_commit` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Tausche `assert_called_...` gegen State Verification aus (z.B. prüfe `Entity.objects.count()`, lade das Objekt neu aus der DB und prüfe veränderte Felder).
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_on_commit_callback_inserts_outbox_row`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-017, REQ-L2-AS-019, REQ-L2-AS-029
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Verwendet Behavior Verification (`assert_called_...`) anstatt den echten Systemzustand zu verifizieren.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] Requirement erstellt → HTTP POST an Webhook-URL mit JSON-Payload
  - [ ] Dispatch asynchron → `create_requirement()` kehrt zurück bevor Webhook-Response
  - [ ] Ziel-URL nicht erreichbar → Retry-Logik, ursprüngliche Operation nicht blockiert
  - [ ] Webhook deaktiviert → kein Dispatch
- **Exakter Refactoring-Bedarf:**
  - Tausche `assert_called_...` gegen State Verification aus (z.B. prüfe `Entity.objects.count()`, lade das Objekt neu aus der DB und prüfe veränderte Felder).
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_on_commit_callback_logs_exception_on_db_error`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-017, REQ-L2-AS-019, REQ-L2-AS-029
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.event_bus.logger. Verwendet Behavior Verification (`assert_called_...`) anstatt den echten Systemzustand zu verifizieren.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] Requirement erstellt → HTTP POST an Webhook-URL mit JSON-Payload
  - [ ] Dispatch asynchron → `create_requirement()` kehrt zurück bevor Webhook-Response
  - [ ] Ziel-URL nicht erreichbar → Retry-Logik, ursprüngliche Operation nicht blockiert
  - [ ] Webhook deaktiviert → kein Dispatch
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.event_bus.logger` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Tausche `assert_called_...` gegen State Verification aus (z.B. prüfe `Entity.objects.count()`, lade das Objekt neu aus der DB und prüfe veränderte Felder).
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_all_subscribers_called`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-017, REQ-L2-AS-019, REQ-L2-AS-029
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`. Verwendet Behavior Verification (`assert_called_...`) anstatt den echten Systemzustand zu verifizieren.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] Requirement erstellt → HTTP POST an Webhook-URL mit JSON-Payload
  - [ ] Dispatch asynchron → `create_requirement()` kehrt zurück bevor Webhook-Response
  - [ ] Ziel-URL nicht erreichbar → Retry-Logik, ursprüngliche Operation nicht blockiert
  - [ ] Webhook deaktiviert → kein Dispatch
- **Exakter Refactoring-Bedarf:**
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Tausche `assert_called_...` gegen State Verification aus (z.B. prüfe `Entity.objects.count()`, lade das Objekt neu aus der DB und prüfe veränderte Felder).
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_failing_subscriber_does_not_block_others`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-017, REQ-L2-AS-019, REQ-L2-AS-029
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`. Verwendet Behavior Verification (`assert_called_...`) anstatt den echten Systemzustand zu verifizieren.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] Requirement erstellt → HTTP POST an Webhook-URL mit JSON-Payload
  - [ ] Dispatch asynchron → `create_requirement()` kehrt zurück bevor Webhook-Response
  - [ ] Ziel-URL nicht erreichbar → Retry-Logik, ursprüngliche Operation nicht blockiert
  - [ ] Webhook deaktiviert → kein Dispatch
- **Exakter Refactoring-Bedarf:**
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Tausche `assert_called_...` gegen State Verification aus (z.B. prüfe `Entity.objects.count()`, lade das Objekt neu aus der DB und prüfe veränderte Felder).
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_no_subscribers_is_noop`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-017, REQ-L2-AS-019, REQ-L2-AS-029
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] Requirement erstellt → HTTP POST an Webhook-URL mit JSON-Payload
  - [ ] Dispatch asynchron → `create_requirement()` kehrt zurück bevor Webhook-Response
  - [ ] Ziel-URL nicht erreichbar → Retry-Logik, ursprüngliche Operation nicht blockiert
  - [ ] Webhook deaktiviert → kein Dispatch
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_marks_event_published_on_success`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-017, REQ-L2-AS-019, REQ-L2-AS-029
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.event_bus.DomainEventOutbox, application.event_bus.DomainEventDLQ, application.event_bus.transaction.atomic. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`. Verwendet Behavior Verification (`assert_called_...`) anstatt den echten Systemzustand zu verifizieren.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] Requirement erstellt → HTTP POST an Webhook-URL mit JSON-Payload
  - [ ] Dispatch asynchron → `create_requirement()` kehrt zurück bevor Webhook-Response
  - [ ] Ziel-URL nicht erreichbar → Retry-Logik, ursprüngliche Operation nicht blockiert
  - [ ] Webhook deaktiviert → kein Dispatch
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.event_bus.DomainEventOutbox, application.event_bus.DomainEventDLQ, application.event_bus.transaction.atomic` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Tausche `assert_called_...` gegen State Verification aus (z.B. prüfe `Entity.objects.count()`, lade das Objekt neu aus der DB und prüfe veränderte Felder).
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_retry_count_incremented_on_dispatch_failure`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-017, REQ-L2-AS-019, REQ-L2-AS-029
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`. Verwendet Behavior Verification (`assert_called_...`) anstatt den echten Systemzustand zu verifizieren.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] Requirement erstellt → HTTP POST an Webhook-URL mit JSON-Payload
  - [ ] Dispatch asynchron → `create_requirement()` kehrt zurück bevor Webhook-Response
  - [ ] Ziel-URL nicht erreichbar → Retry-Logik, ursprüngliche Operation nicht blockiert
  - [ ] Webhook deaktiviert → kein Dispatch
- **Exakter Refactoring-Bedarf:**
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Tausche `assert_called_...` gegen State Verification aus (z.B. prüfe `Entity.objects.count()`, lade das Objekt neu aus der DB und prüfe veränderte Felder).
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_dlq_created_after_max_retries`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-017, REQ-L2-AS-019, REQ-L2-AS-029
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.event_bus.DomainEventDLQ. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`. Verwendet Behavior Verification (`assert_called_...`) anstatt den echten Systemzustand zu verifizieren.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] Requirement erstellt → HTTP POST an Webhook-URL mit JSON-Payload
  - [ ] Dispatch asynchron → `create_requirement()` kehrt zurück bevor Webhook-Response
  - [ ] Ziel-URL nicht erreichbar → Retry-Logik, ursprüngliche Operation nicht blockiert
  - [ ] Webhook deaktiviert → kein Dispatch
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.event_bus.DomainEventDLQ` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Tausche `assert_called_...` gegen State Verification aus (z.B. prüfe `Entity.objects.count()`, lade das Objekt neu aus der DB und prüfe veränderte Felder).
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

## Datei: `test_export_service.py`

### Test: `test_returns_valid_json`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-016
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.export_service.TenantContext.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `export_pdf(scope=workspace, type="requirement_document")` → gültige PDF
  - [ ] `export_pdf(scope=baseline, type="traceability_matrix")` → PDF mit Matrix
  - [ ] PDF enthält Metadaten: Version, Baseline-Referenz, Workflow-State
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.export_service.TenantContext` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_invalid_entity_type_raises`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-016
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.export_service.TenantContext.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `export_pdf(scope=workspace, type="requirement_document")` → gültige PDF
  - [ ] `export_pdf(scope=baseline, type="traceability_matrix")` → PDF mit Matrix
  - [ ] PDF enthält Metadaten: Version, Baseline-Referenz, Workflow-State
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.export_service.TenantContext` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_metadata_contains_workspace_id`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-016
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.export_service.TenantContext.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `export_pdf(scope=workspace, type="requirement_document")` → gültige PDF
  - [ ] `export_pdf(scope=baseline, type="traceability_matrix")` → PDF mit Matrix
  - [ ] PDF enthält Metadaten: Version, Baseline-Referenz, Workflow-State
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.export_service.TenantContext` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_first_line_is_terminology_comment`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-016
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.export_service.TenantContext.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `export_pdf(scope=workspace, type="requirement_document")` → gültige PDF
  - [ ] `export_pdf(scope=baseline, type="traceability_matrix")` → PDF mit Matrix
  - [ ] PDF enthält Metadaten: Version, Baseline-Referenz, Workflow-State
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.export_service.TenantContext` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_csv_has_header_and_data_rows`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-016
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.export_service.TenantContext.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `export_pdf(scope=workspace, type="requirement_document")` → gültige PDF
  - [ ] `export_pdf(scope=baseline, type="traceability_matrix")` → PDF mit Matrix
  - [ ] PDF enthält Metadaten: Version, Baseline-Referenz, Workflow-State
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.export_service.TenantContext` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_media_type_is_csv`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-016
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.export_service.TenantContext.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `export_pdf(scope=workspace, type="requirement_document")` → gültige PDF
  - [ ] `export_pdf(scope=baseline, type="traceability_matrix")` → PDF mit Matrix
  - [ ] PDF enthält Metadaten: Version, Baseline-Referenz, Workflow-State
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.export_service.TenantContext` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_contains_title_and_workspace`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-016
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.export_service.TenantContext.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `export_pdf(scope=workspace, type="requirement_document")` → gültige PDF
  - [ ] `export_pdf(scope=baseline, type="traceability_matrix")` → PDF mit Matrix
  - [ ] PDF enthält Metadaten: Version, Baseline-Referenz, Workflow-State
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.export_service.TenantContext` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_media_type_is_markdown`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-016
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.export_service.TenantContext.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `export_pdf(scope=workspace, type="requirement_document")` → gültige PDF
  - [ ] `export_pdf(scope=baseline, type="traceability_matrix")` → PDF mit Matrix
  - [ ] PDF enthält Metadaten: Version, Baseline-Referenz, Workflow-State
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.export_service.TenantContext` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_returns_pdf_result`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-016
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.export_service.TenantContext.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `export_pdf(scope=workspace, type="requirement_document")` → gültige PDF
  - [ ] `export_pdf(scope=baseline, type="traceability_matrix")` → PDF mit Matrix
  - [ ] PDF enthält Metadaten: Version, Baseline-Referenz, Workflow-State
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.export_service.TenantContext` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_invalid_entity_type_raises`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-016
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.export_service.TenantContext.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `export_pdf(scope=workspace, type="requirement_document")` → gültige PDF
  - [ ] `export_pdf(scope=baseline, type="traceability_matrix")` → PDF mit Matrix
  - [ ] PDF enthält Metadaten: Version, Baseline-Referenz, Workflow-State
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.export_service.TenantContext` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

## Datei: `test_import_service.py`

### Test: `test_parses_valid_csv`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_skips_comment_lines`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_empty_csv_produces_zero_rows`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_valid_row_produces_no_errors`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_missing_title_produces_error`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_title_too_long_produces_error`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_invalid_entity_type_raises`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.import_service.TenantContext.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.import_service.TenantContext` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_row_limit_exceeded_raises`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.import_service.TenantContext, application.import_service.ServiceBase._assert_write_permission.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.import_service.TenantContext, application.import_service.ServiceBase._assert_write_permission` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_csv_with_validation_errors_returns_failure`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.import_service.TenantContext, application.import_service.ServiceBase._assert_write_permission.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.import_service.TenantContext, application.import_service.ServiceBase._assert_write_permission` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_successful_import_returns_ok`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.import_service.TenantContext, application.import_service.ServiceBase._assert_write_permission, application.import_service.transaction.atomic, application.import_service.ServiceBase._audit. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`. Verwendet Behavior Verification (`assert_called_...`) anstatt den echten Systemzustand zu verifizieren.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.import_service.TenantContext, application.import_service.ServiceBase._assert_write_permission, application.import_service.transaction.atomic, application.import_service.ServiceBase._audit` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Tausche `assert_called_...` gegen State Verification aus (z.B. prüfe `Entity.objects.count()`, lade das Objekt neu aus der DB und prüfe veränderte Felder).
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_db_error_triggers_rollback_result`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.import_service.TenantContext, application.import_service.ServiceBase._assert_write_permission.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.import_service.TenantContext, application.import_service.ServiceBase._assert_write_permission` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_exactly_1000_rows_accepted`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.import_service.TenantContext, application.import_service.ServiceBase._assert_write_permission, application.import_service.transaction.atomic, application.import_service.ServiceBase._audit. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.import_service.TenantContext, application.import_service.ServiceBase._assert_write_permission, application.import_service.transaction.atomic, application.import_service.ServiceBase._audit` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

## Datei: `test_issue_service.py`

### Test: `test_valid_create_passes`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_empty_title_raises`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_invalid_severity_raises`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_invalid_category_raises`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_invalid_status_raises`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_all_severities_valid`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_all_categories_valid`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_from_orm_maps_fields`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_creates_issue_with_workflow_init`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.issue_service.Issue.objects, application.issue_service.IssueService._set_tenant_context, application.issue_service.IssueService._assert_write_permission, application.issue_service.IssueService._audit, application.issue_service.IssueService._emit_event, workflow.services.initialize_workflow_states. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`. Verwendet Behavior Verification (`assert_called_...`) anstatt den echten Systemzustand zu verifizieren.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.issue_service.Issue.objects, application.issue_service.IssueService._set_tenant_context, application.issue_service.IssueService._assert_write_permission, application.issue_service.IssueService._audit, application.issue_service.IssueService._emit_event, workflow.services.initialize_workflow_states` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Tausche `assert_called_...` gegen State Verification aus (z.B. prüfe `Entity.objects.count()`, lade das Objekt neu aus der DB und prüfe veränderte Felder).
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_viewer_cannot_create`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_invalid_severity_raises_before_db_write`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.issue_service.IssueService._set_tenant_context, application.issue_service.IssueService._assert_write_permission.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.issue_service.IssueService._set_tenant_context, application.issue_service.IssueService._assert_write_permission` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_workflow_failure_is_swallowed`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.issue_service.Issue.objects, application.issue_service.IssueService._set_tenant_context, application.issue_service.IssueService._assert_write_permission, application.issue_service.IssueService._audit, application.issue_service.IssueService._emit_event. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.issue_service.Issue.objects, application.issue_service.IssueService._set_tenant_context, application.issue_service.IssueService._assert_write_permission, application.issue_service.IssueService._audit, application.issue_service.IssueService._emit_event` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_updates_fields_and_increments_version`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.issue_service.Issue.objects, application.issue_service.IssueService._set_tenant_context, application.issue_service.IssueService._assert_write_permission, application.issue_service.IssueService._audit, application.issue_service.IssueService._emit_event. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`. Verwendet Behavior Verification (`assert_called_...`) anstatt den echten Systemzustand zu verifizieren.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.issue_service.Issue.objects, application.issue_service.IssueService._set_tenant_context, application.issue_service.IssueService._assert_write_permission, application.issue_service.IssueService._audit, application.issue_service.IssueService._emit_event` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Tausche `assert_called_...` gegen State Verification aus (z.B. prüfe `Entity.objects.count()`, lade das Objekt neu aus der DB und prüfe veränderte Felder).
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_not_found_raises`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.issue_service.Issue.objects, application.issue_service.IssueService._set_tenant_context, application.issue_service.IssueService._assert_write_permission.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.issue_service.Issue.objects, application.issue_service.IssueService._set_tenant_context, application.issue_service.IssueService._assert_write_permission` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_audit_entry_written`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.issue_service.Issue.objects, application.issue_service.IssueService._set_tenant_context, application.issue_service.IssueService._assert_write_permission, application.issue_service.IssueService._audit, application.issue_service.IssueService._emit_event. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`. Verwendet Behavior Verification (`assert_called_...`) anstatt den echten Systemzustand zu verifizieren.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.issue_service.Issue.objects, application.issue_service.IssueService._set_tenant_context, application.issue_service.IssueService._assert_write_permission, application.issue_service.IssueService._audit, application.issue_service.IssueService._emit_event` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Tausche `assert_called_...` gegen State Verification aus (z.B. prüfe `Entity.objects.count()`, lade das Objekt neu aus der DB und prüfe veränderte Felder).
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_cascades_tracelinks_and_deletes`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.issue_service.Issue.objects, application.issue_service.IssueService._set_tenant_context, application.issue_service.IssueService._assert_write_permission, application.issue_service.IssueService._audit, application.issue_service.IssueService._emit_event. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`. Verwendet Behavior Verification (`assert_called_...`) anstatt den echten Systemzustand zu verifizieren.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.issue_service.Issue.objects, application.issue_service.IssueService._set_tenant_context, application.issue_service.IssueService._assert_write_permission, application.issue_service.IssueService._audit, application.issue_service.IssueService._emit_event` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Tausche `assert_called_...` gegen State Verification aus (z.B. prüfe `Entity.objects.count()`, lade das Objekt neu aus der DB und prüfe veränderte Felder).
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_not_found_raises`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.issue_service.Issue.objects, application.issue_service.IssueService._set_tenant_context, application.issue_service.IssueService._assert_write_permission.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.issue_service.Issue.objects, application.issue_service.IssueService._set_tenant_context, application.issue_service.IssueService._assert_write_permission` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_filters_by_severity`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.issue_service.Issue.objects, application.issue_service.IssueService._set_tenant_context. Verwendet Behavior Verification (`assert_called_...`) anstatt den echten Systemzustand zu verifizieren.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.issue_service.Issue.objects, application.issue_service.IssueService._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Tausche `assert_called_...` gegen State Verification aus (z.B. prüfe `Entity.objects.count()`, lade das Objekt neu aus der DB und prüfe veränderte Felder).
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_invalid_severity_raises`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.issue_service.IssueService._set_tenant_context.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.issue_service.IssueService._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_no_filters_returns_all`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.issue_service.Issue.objects, application.issue_service.IssueService._set_tenant_context. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.issue_service.Issue.objects, application.issue_service.IssueService._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_status_filter_applied`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.issue_service.Issue.objects, application.issue_service.IssueService._set_tenant_context. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`. Verwendet Behavior Verification (`assert_called_...`) anstatt den echten Systemzustand zu verifizieren.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.issue_service.Issue.objects, application.issue_service.IssueService._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Tausche `assert_called_...` gegen State Verification aus (z.B. prüfe `Entity.objects.count()`, lade das Objekt neu aus der DB und prüfe veränderte Felder).
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_severity_filter_applied`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.issue_service.Issue.objects, application.issue_service.IssueService._set_tenant_context. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.issue_service.Issue.objects, application.issue_service.IssueService._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_assign_updates_assignee_and_date`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.issue_service.Issue.objects, application.issue_service.IssueService._set_tenant_context, application.issue_service.IssueService._assert_write_permission, application.issue_service.IssueService._audit, django.utils.timezone.now", return_value="2026-06-24T10:00:00Z. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`. Verwendet Behavior Verification (`assert_called_...`) anstatt den echten Systemzustand zu verifizieren.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.issue_service.Issue.objects, application.issue_service.IssueService._set_tenant_context, application.issue_service.IssueService._assert_write_permission, application.issue_service.IssueService._audit, django.utils.timezone.now", return_value="2026-06-24T10:00:00Z` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Tausche `assert_called_...` gegen State Verification aus (z.B. prüfe `Entity.objects.count()`, lade das Objekt neu aus der DB und prüfe veränderte Felder).
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_unassign_sets_assignee_to_none`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.issue_service.Issue.objects, application.issue_service.IssueService._set_tenant_context, application.issue_service.IssueService._assert_write_permission, application.issue_service.IssueService._audit, django.utils.timezone.now", return_value="2026-06-24T10:00:00Z. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.issue_service.Issue.objects, application.issue_service.IssueService._set_tenant_context, application.issue_service.IssueService._assert_write_permission, application.issue_service.IssueService._audit, django.utils.timezone.now", return_value="2026-06-24T10:00:00Z` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_list_issues_by_assignee_filters_by_tenant`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.issue_service.Issue.objects, application.issue_service.IssueService._set_tenant_context.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.issue_service.Issue.objects, application.issue_service.IssueService._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_valid_link_type_delegates`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.issue_service.Issue.objects, application.issue_service.IssueService._set_tenant_context. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`. Verwendet Behavior Verification (`assert_called_...`) anstatt den echten Systemzustand zu verifizieren.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.issue_service.Issue.objects, application.issue_service.IssueService._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Tausche `assert_called_...` gegen State Verification aus (z.B. prüfe `Entity.objects.count()`, lade das Objekt neu aus der DB und prüfe veränderte Felder).
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_invalid_link_type_raises`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.issue_service.IssueService._set_tenant_context.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.issue_service.IssueService._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_all_valid_link_types_accepted`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.issue_service.Issue.objects, application.issue_service.IssueService._set_tenant_context. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.issue_service.Issue.objects, application.issue_service.IssueService._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

## Datei: `test_preset_policy_service.py`

### Test: `test_mandatory_returns_true`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-020
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_baseline(scope="global")` im Minimal → Fehler
  - [ ] `update(change_reason=None)` im Extended → Fehler
  - [ ] `update(change_reason=None)` im Minimal → erfolgreich
  - [ ] `downgrade_preset("minimal")` mit Global-Baseline → Fehler
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_optional_returns_false`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-020
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_baseline(scope="global")` im Minimal → Fehler
  - [ ] `update(change_reason=None)` im Extended → Fehler
  - [ ] `update(change_reason=None)` im Minimal → erfolgreich
  - [ ] `downgrade_preset("minimal")` mit Global-Baseline → Fehler
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_failure_returns_false_fail_open`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-020
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_baseline(scope="global")` im Minimal → Fehler
  - [ ] `update(change_reason=None)` im Extended → Fehler
  - [ ] `update(change_reason=None)` im Minimal → erfolgreich
  - [ ] `downgrade_preset("minimal")` mit Global-Baseline → Fehler
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_allowed_scope_returns_true`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-020
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Verwendet Behavior Verification (`assert_called_...`) anstatt den echten Systemzustand zu verifizieren.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_baseline(scope="global")` im Minimal → Fehler
  - [ ] `update(change_reason=None)` im Extended → Fehler
  - [ ] `update(change_reason=None)` im Minimal → erfolgreich
  - [ ] `downgrade_preset("minimal")` mit Global-Baseline → Fehler
- **Exakter Refactoring-Bedarf:**
  - Tausche `assert_called_...` gegen State Verification aus (z.B. prüfe `Entity.objects.count()`, lade das Objekt neu aus der DB und prüfe veränderte Felder).
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_disallowed_scope_returns_false`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-020
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_baseline(scope="global")` im Minimal → Fehler
  - [ ] `update(change_reason=None)` im Extended → Fehler
  - [ ] `update(change_reason=None)` im Minimal → erfolgreich
  - [ ] `downgrade_preset("minimal")` mit Global-Baseline → Fehler
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_failure_returns_false_fail_open`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-020
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_baseline(scope="global")` im Minimal → Fehler
  - [ ] `update(change_reason=None)` im Extended → Fehler
  - [ ] `update(change_reason=None)` im Minimal → erfolgreich
  - [ ] `downgrade_preset("minimal")` mit Global-Baseline → Fehler
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_no_approval_workflows_allows_any_role`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-020
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_baseline(scope="global")` im Minimal → Fehler
  - [ ] `update(change_reason=None)` im Extended → Fehler
  - [ ] `update(change_reason=None)` im Minimal → erfolgreich
  - [ ] `downgrade_preset("minimal")` mit Global-Baseline → Fehler
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_approval_workflows_non_approver_denied`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-020
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_baseline(scope="global")` im Minimal → Fehler
  - [ ] `update(change_reason=None)` im Extended → Fehler
  - [ ] `update(change_reason=None)` im Minimal → erfolgreich
  - [ ] `downgrade_preset("minimal")` mit Global-Baseline → Fehler
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_approver_role_allowed_for_approved_state`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-020
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_baseline(scope="global")` im Minimal → Fehler
  - [ ] `update(change_reason=None)` im Extended → Fehler
  - [ ] `update(change_reason=None)` im Minimal → erfolgreich
  - [ ] `downgrade_preset("minimal")` mit Global-Baseline → Fehler
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_non_approved_target_state_always_allowed`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-020
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_baseline(scope="global")` im Minimal → Fehler
  - [ ] `update(change_reason=None)` im Extended → Fehler
  - [ ] `update(change_reason=None)` im Minimal → erfolgreich
  - [ ] `downgrade_preset("minimal")` mit Global-Baseline → Fehler
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_failure_returns_true_fail_open`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-020
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_baseline(scope="global")` im Minimal → Fehler
  - [ ] `update(change_reason=None)` im Extended → Fehler
  - [ ] `update(change_reason=None)` im Minimal → erfolgreich
  - [ ] `downgrade_preset("minimal")` mit Global-Baseline → Fehler
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_clean_downgrade_returns_true_empty_warnings`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-020
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_baseline(scope="global")` im Minimal → Fehler
  - [ ] `update(change_reason=None)` im Extended → Fehler
  - [ ] `update(change_reason=None)` im Minimal → erfolgreich
  - [ ] `downgrade_preset("minimal")` mit Global-Baseline → Fehler
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_blocked_downgrade_returns_false_with_warnings`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-020
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_baseline(scope="global")` im Minimal → Fehler
  - [ ] `update(change_reason=None)` im Extended → Fehler
  - [ ] `update(change_reason=None)` im Minimal → erfolgreich
  - [ ] `downgrade_preset("minimal")` mit Global-Baseline → Fehler
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_failure_returns_false_with_error`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-020
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_baseline(scope="global")` im Minimal → Fehler
  - [ ] `update(change_reason=None)` im Extended → Fehler
  - [ ] `update(change_reason=None)` im Minimal → erfolgreich
  - [ ] `downgrade_preset("minimal")` mit Global-Baseline → Fehler
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_change_reason_required_key`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-020
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_baseline(scope="global")` im Minimal → Fehler
  - [ ] `update(change_reason=None)` im Extended → Fehler
  - [ ] `update(change_reason=None)` im Minimal → erfolgreich
  - [ ] `downgrade_preset("minimal")` mit Global-Baseline → Fehler
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_baseline_scopes_key`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-020
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_baseline(scope="global")` im Minimal → Fehler
  - [ ] `update(change_reason=None)` im Extended → Fehler
  - [ ] `update(change_reason=None)` im Minimal → erfolgreich
  - [ ] `downgrade_preset("minimal")` mit Global-Baseline → Fehler
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_features_key`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-020
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_baseline(scope="global")` im Minimal → Fehler
  - [ ] `update(change_reason=None)` im Extended → Fehler
  - [ ] `update(change_reason=None)` im Minimal → erfolgreich
  - [ ] `downgrade_preset("minimal")` mit Global-Baseline → Fehler
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_unsupported_key_raises_value_error`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-020
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_baseline(scope="global")` im Minimal → Fehler
  - [ ] `update(change_reason=None)` im Extended → Fehler
  - [ ] `update(change_reason=None)` im Minimal → erfolgreich
  - [ ] `downgrade_preset("minimal")` mit Global-Baseline → Fehler
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_second_call_uses_cached_preset`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-020
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_baseline(scope="global")` im Minimal → Fehler
  - [ ] `update(change_reason=None)` im Extended → Fehler
  - [ ] `update(change_reason=None)` im Minimal → erfolgreich
  - [ ] `downgrade_preset("minimal")` mit Global-Baseline → Fehler
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_invalidate_cache_forces_fresh_fetch`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-020
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_baseline(scope="global")` im Minimal → Fehler
  - [ ] `update(change_reason=None)` im Extended → Fehler
  - [ ] `update(change_reason=None)` im Minimal → erfolgreich
  - [ ] `downgrade_preset("minimal")` mit Global-Baseline → Fehler
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_returns_same_instance`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-020
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_baseline(scope="global")` im Minimal → Fehler
  - [ ] `update(change_reason=None)` im Extended → Fehler
  - [ ] `update(change_reason=None)` im Minimal → erfolgreich
  - [ ] `downgrade_preset("minimal")` mit Global-Baseline → Fehler
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

## Datei: `test_requirement_service.py`

### Test: `test_viewer_cannot_create`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-003, REQ-L2-AS-013, REQ-L2-AS-019, REQ-L2-AS-024
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.requirement_service.ServiceBase._set_tenant_context.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_requirement()` → Requirement mit initialem WorkflowState
  - [ ] `update_requirement(change_reason=None)` im Extended → Fehler `"change_reason required"`
  - [ ] `delete_requirement()` → Requirement + alle TraceLinks gelöscht
  - [ ] Nach Schreiboperation: AuditLog-Eintrag vorhanden
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.requirement_service.ServiceBase._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_tenant_not_found_raises`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-003, REQ-L2-AS-013, REQ-L2-AS-019, REQ-L2-AS-024
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.requirement_service.ServiceBase._set_tenant_context.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_requirement()` → Requirement mit initialem WorkflowState
  - [ ] `update_requirement(change_reason=None)` im Extended → Fehler `"change_reason required"`
  - [ ] `delete_requirement()` → Requirement + alle TraceLinks gelöscht
  - [ ] Nach Schreiboperation: AuditLog-Eintrag vorhanden
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.requirement_service.ServiceBase._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_workspace_not_found_raises`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-003, REQ-L2-AS-013, REQ-L2-AS-019, REQ-L2-AS-024
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.requirement_service.ServiceBase._set_tenant_context. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_requirement()` → Requirement mit initialem WorkflowState
  - [ ] `update_requirement(change_reason=None)` im Extended → Fehler `"change_reason required"`
  - [ ] `delete_requirement()` → Requirement + alle TraceLinks gelöscht
  - [ ] Nach Schreiboperation: AuditLog-Eintrag vorhanden
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.requirement_service.ServiceBase._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_create_success_returns_requirement`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-003, REQ-L2-AS-013, REQ-L2-AS-019, REQ-L2-AS-024
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.requirement_service.ServiceBase._set_tenant_context. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_requirement()` → Requirement mit initialem WorkflowState
  - [ ] `update_requirement(change_reason=None)` im Extended → Fehler `"change_reason required"`
  - [ ] `delete_requirement()` → Requirement + alle TraceLinks gelöscht
  - [ ] Nach Schreiboperation: AuditLog-Eintrag vorhanden
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.requirement_service.ServiceBase._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_audit_entry_on_create`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-003, REQ-L2-AS-013, REQ-L2-AS-019, REQ-L2-AS-024
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.requirement_service.ServiceBase._set_tenant_context. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`. Verwendet Behavior Verification (`assert_called_...`) anstatt den echten Systemzustand zu verifizieren.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_requirement()` → Requirement mit initialem WorkflowState
  - [ ] `update_requirement(change_reason=None)` im Extended → Fehler `"change_reason required"`
  - [ ] `delete_requirement()` → Requirement + alle TraceLinks gelöscht
  - [ ] Nach Schreiboperation: AuditLog-Eintrag vorhanden
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.requirement_service.ServiceBase._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Tausche `assert_called_...` gegen State Verification aus (z.B. prüfe `Entity.objects.count()`, lade das Objekt neu aus der DB und prüfe veränderte Felder).
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_tenant_context_set_on_create`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-003, REQ-L2-AS-013, REQ-L2-AS-019, REQ-L2-AS-024
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Verwendet Behavior Verification (`assert_called_...`) anstatt den echten Systemzustand zu verifizieren.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_requirement()` → Requirement mit initialem WorkflowState
  - [ ] `update_requirement(change_reason=None)` im Extended → Fehler `"change_reason required"`
  - [ ] `delete_requirement()` → Requirement + alle TraceLinks gelöscht
  - [ ] Nach Schreiboperation: AuditLog-Eintrag vorhanden
- **Exakter Refactoring-Bedarf:**
  - Tausche `assert_called_...` gegen State Verification aus (z.B. prüfe `Entity.objects.count()`, lade das Objekt neu aus der DB und prüfe veränderte Felder).
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_update_not_found_raises`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-003, REQ-L2-AS-013, REQ-L2-AS-019, REQ-L2-AS-024
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.requirement_service.ServiceBase._set_tenant_context. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_requirement()` → Requirement mit initialem WorkflowState
  - [ ] `update_requirement(change_reason=None)` im Extended → Fehler `"change_reason required"`
  - [ ] `delete_requirement()` → Requirement + alle TraceLinks gelöscht
  - [ ] Nach Schreiboperation: AuditLog-Eintrag vorhanden
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.requirement_service.ServiceBase._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_change_reason_required_raises_validation_error`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-003, REQ-L2-AS-013, REQ-L2-AS-019, REQ-L2-AS-024
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.requirement_service.ServiceBase._set_tenant_context. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_requirement()` → Requirement mit initialem WorkflowState
  - [ ] `update_requirement(change_reason=None)` im Extended → Fehler `"change_reason required"`
  - [ ] `delete_requirement()` → Requirement + alle TraceLinks gelöscht
  - [ ] Nach Schreiboperation: AuditLog-Eintrag vorhanden
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.requirement_service.ServiceBase._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_change_reason_not_required_allows_update`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-003, REQ-L2-AS-013, REQ-L2-AS-019, REQ-L2-AS-024
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.requirement_service.ServiceBase._set_tenant_context. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_requirement()` → Requirement mit initialem WorkflowState
  - [ ] `update_requirement(change_reason=None)` im Extended → Fehler `"change_reason required"`
  - [ ] `delete_requirement()` → Requirement + alle TraceLinks gelöscht
  - [ ] Nach Schreiboperation: AuditLog-Eintrag vorhanden
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.requirement_service.ServiceBase._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_audit_entry_on_update`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-003, REQ-L2-AS-013, REQ-L2-AS-019, REQ-L2-AS-024
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.requirement_service.ServiceBase._set_tenant_context, application.requirement_service.Requirement.objects.filter. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`. Verwendet Behavior Verification (`assert_called_...`) anstatt den echten Systemzustand zu verifizieren.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_requirement()` → Requirement mit initialem WorkflowState
  - [ ] `update_requirement(change_reason=None)` im Extended → Fehler `"change_reason required"`
  - [ ] `delete_requirement()` → Requirement + alle TraceLinks gelöscht
  - [ ] Nach Schreiboperation: AuditLog-Eintrag vorhanden
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.requirement_service.ServiceBase._set_tenant_context, application.requirement_service.Requirement.objects.filter` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Tausche `assert_called_...` gegen State Verification aus (z.B. prüfe `Entity.objects.count()`, lade das Objekt neu aus der DB und prüfe veränderte Felder).
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_update_status_round_trip`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-003, REQ-L2-AS-013, REQ-L2-AS-019, REQ-L2-AS-024
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.requirement_service.ServiceBase._set_tenant_context, application.requirement_service.Requirement.objects.filter. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_requirement()` → Requirement mit initialem WorkflowState
  - [ ] `update_requirement(change_reason=None)` im Extended → Fehler `"change_reason required"`
  - [ ] `delete_requirement()` → Requirement + alle TraceLinks gelöscht
  - [ ] Nach Schreiboperation: AuditLog-Eintrag vorhanden
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.requirement_service.ServiceBase._set_tenant_context, application.requirement_service.Requirement.objects.filter` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_update_status_none_leaves_status_unchanged`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-003, REQ-L2-AS-013, REQ-L2-AS-019, REQ-L2-AS-024
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.requirement_service.ServiceBase._set_tenant_context, application.requirement_service.Requirement.objects.filter. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_requirement()` → Requirement mit initialem WorkflowState
  - [ ] `update_requirement(change_reason=None)` im Extended → Fehler `"change_reason required"`
  - [ ] `delete_requirement()` → Requirement + alle TraceLinks gelöscht
  - [ ] Nach Schreiboperation: AuditLog-Eintrag vorhanden
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.requirement_service.ServiceBase._set_tenant_context, application.requirement_service.Requirement.objects.filter` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_update_increments_version_atomically`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-003, REQ-L2-AS-013, REQ-L2-AS-019, REQ-L2-AS-024
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.requirement_service.ServiceBase._set_tenant_context, application.requirement_service.ServiceBase._assert_write_permission. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`. Verwendet Behavior Verification (`assert_called_...`) anstatt den echten Systemzustand zu verifizieren.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_requirement()` → Requirement mit initialem WorkflowState
  - [ ] `update_requirement(change_reason=None)` im Extended → Fehler `"change_reason required"`
  - [ ] `delete_requirement()` → Requirement + alle TraceLinks gelöscht
  - [ ] Nach Schreiboperation: AuditLog-Eintrag vorhanden
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.requirement_service.ServiceBase._set_tenant_context, application.requirement_service.ServiceBase._assert_write_permission` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Tausche `assert_called_...` gegen State Verification aus (z.B. prüfe `Entity.objects.count()`, lade das Objekt neu aus der DB und prüfe veränderte Felder).
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_delete_not_found_raises`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-003, REQ-L2-AS-013, REQ-L2-AS-019, REQ-L2-AS-024
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.requirement_service.ServiceBase._set_tenant_context. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_requirement()` → Requirement mit initialem WorkflowState
  - [ ] `update_requirement(change_reason=None)` im Extended → Fehler `"change_reason required"`
  - [ ] `delete_requirement()` → Requirement + alle TraceLinks gelöscht
  - [ ] Nach Schreiboperation: AuditLog-Eintrag vorhanden
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.requirement_service.ServiceBase._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_delete_cascades_trace_links_and_deletes`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-003, REQ-L2-AS-013, REQ-L2-AS-019, REQ-L2-AS-024
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.requirement_service.ServiceBase._set_tenant_context. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`. Verwendet Behavior Verification (`assert_called_...`) anstatt den echten Systemzustand zu verifizieren.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_requirement()` → Requirement mit initialem WorkflowState
  - [ ] `update_requirement(change_reason=None)` im Extended → Fehler `"change_reason required"`
  - [ ] `delete_requirement()` → Requirement + alle TraceLinks gelöscht
  - [ ] Nach Schreiboperation: AuditLog-Eintrag vorhanden
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.requirement_service.ServiceBase._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Tausche `assert_called_...` gegen State Verification aus (z.B. prüfe `Entity.objects.count()`, lade das Objekt neu aus der DB und prüfe veränderte Felder).
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_audit_entry_on_delete`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-003, REQ-L2-AS-013, REQ-L2-AS-019, REQ-L2-AS-024
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.requirement_service.ServiceBase._set_tenant_context. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`. Verwendet Behavior Verification (`assert_called_...`) anstatt den echten Systemzustand zu verifizieren.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_requirement()` → Requirement mit initialem WorkflowState
  - [ ] `update_requirement(change_reason=None)` im Extended → Fehler `"change_reason required"`
  - [ ] `delete_requirement()` → Requirement + alle TraceLinks gelöscht
  - [ ] Nach Schreiboperation: AuditLog-Eintrag vorhanden
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.requirement_service.ServiceBase._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Tausche `assert_called_...` gegen State Verification aus (z.B. prüfe `Entity.objects.count()`, lade das Objekt neu aus der DB und prüfe veränderte Felder).
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_get_returns_requirement`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-003, REQ-L2-AS-013, REQ-L2-AS-019, REQ-L2-AS-024
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.requirement_service.ServiceBase._set_tenant_context. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_requirement()` → Requirement mit initialem WorkflowState
  - [ ] `update_requirement(change_reason=None)` im Extended → Fehler `"change_reason required"`
  - [ ] `delete_requirement()` → Requirement + alle TraceLinks gelöscht
  - [ ] Nach Schreiboperation: AuditLog-Eintrag vorhanden
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.requirement_service.ServiceBase._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_get_not_found_raises`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-003, REQ-L2-AS-013, REQ-L2-AS-019, REQ-L2-AS-024
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.requirement_service.ServiceBase._set_tenant_context. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_requirement()` → Requirement mit initialem WorkflowState
  - [ ] `update_requirement(change_reason=None)` im Extended → Fehler `"change_reason required"`
  - [ ] `delete_requirement()` → Requirement + alle TraceLinks gelöscht
  - [ ] Nach Schreiboperation: AuditLog-Eintrag vorhanden
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.requirement_service.ServiceBase._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_list_requirements_returns_list`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-003, REQ-L2-AS-013, REQ-L2-AS-019, REQ-L2-AS-024
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.requirement_service.ServiceBase._set_tenant_context. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_requirement()` → Requirement mit initialem WorkflowState
  - [ ] `update_requirement(change_reason=None)` im Extended → Fehler `"change_reason required"`
  - [ ] `delete_requirement()` → Requirement + alle TraceLinks gelöscht
  - [ ] Nach Schreiboperation: AuditLog-Eintrag vorhanden
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.requirement_service.ServiceBase._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_decompose_manual_children_creates_child_requirements`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-003, REQ-L2-AS-013, REQ-L2-AS-019, REQ-L2-AS-024
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.requirement_service.ServiceBase._set_tenant_context, application.requirement_service.Workspace.objects.filter. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_requirement()` → Requirement mit initialem WorkflowState
  - [ ] `update_requirement(change_reason=None)` im Extended → Fehler `"change_reason required"`
  - [ ] `delete_requirement()` → Requirement + alle TraceLinks gelöscht
  - [ ] Nach Schreiboperation: AuditLog-Eintrag vorhanden
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.requirement_service.ServiceBase._set_tenant_context, application.requirement_service.Workspace.objects.filter` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_decompose_llm_not_configured_raises`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-003, REQ-L2-AS-013, REQ-L2-AS-019, REQ-L2-AS-024
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.requirement_service.ServiceBase._set_tenant_context. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_requirement()` → Requirement mit initialem WorkflowState
  - [ ] `update_requirement(change_reason=None)` im Extended → Fehler `"change_reason required"`
  - [ ] `delete_requirement()` → Requirement + alle TraceLinks gelöscht
  - [ ] Nach Schreiboperation: AuditLog-Eintrag vorhanden
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.requirement_service.ServiceBase._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_decompose_parent_not_found_raises`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-003, REQ-L2-AS-013, REQ-L2-AS-019, REQ-L2-AS-024
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.requirement_service.ServiceBase._set_tenant_context. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_requirement()` → Requirement mit initialem WorkflowState
  - [ ] `update_requirement(change_reason=None)` im Extended → Fehler `"change_reason required"`
  - [ ] `delete_requirement()` → Requirement + alle TraceLinks gelöscht
  - [ ] Nach Schreiboperation: AuditLog-Eintrag vorhanden
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.requirement_service.ServiceBase._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_decompose_with_target_architecture_elements`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-003, REQ-L2-AS-013, REQ-L2-AS-019, REQ-L2-AS-024
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.requirement_service.ServiceBase._set_tenant_context, application.requirement_service.Workspace.objects.filter. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`. Verwendet Behavior Verification (`assert_called_...`) anstatt den echten Systemzustand zu verifizieren.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_requirement()` → Requirement mit initialem WorkflowState
  - [ ] `update_requirement(change_reason=None)` im Extended → Fehler `"change_reason required"`
  - [ ] `delete_requirement()` → Requirement + alle TraceLinks gelöscht
  - [ ] Nach Schreiboperation: AuditLog-Eintrag vorhanden
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.requirement_service.ServiceBase._set_tenant_context, application.requirement_service.Workspace.objects.filter` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Tausche `assert_called_...` gegen State Verification aus (z.B. prüfe `Entity.objects.count()`, lade das Objekt neu aus der DB und prüfe veränderte Felder).
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_decompose_target_elements_count_mismatch_raises`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-003, REQ-L2-AS-013, REQ-L2-AS-019, REQ-L2-AS-024
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.requirement_service.ServiceBase._set_tenant_context. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_requirement()` → Requirement mit initialem WorkflowState
  - [ ] `update_requirement(change_reason=None)` im Extended → Fehler `"change_reason required"`
  - [ ] `delete_requirement()` → Requirement + alle TraceLinks gelöscht
  - [ ] Nach Schreiboperation: AuditLog-Eintrag vorhanden
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.requirement_service.ServiceBase._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_decompose_target_element_not_found_raises`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-003, REQ-L2-AS-013, REQ-L2-AS-019, REQ-L2-AS-024
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.requirement_service.ServiceBase._set_tenant_context, application.requirement_service.Workspace.objects.filter. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_requirement()` → Requirement mit initialem WorkflowState
  - [ ] `update_requirement(change_reason=None)` im Extended → Fehler `"change_reason required"`
  - [ ] `delete_requirement()` → Requirement + alle TraceLinks gelöscht
  - [ ] Nach Schreiboperation: AuditLog-Eintrag vorhanden
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.requirement_service.ServiceBase._set_tenant_context, application.requirement_service.Workspace.objects.filter` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_decompose_empty_target_elements_raises`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-003, REQ-L2-AS-013, REQ-L2-AS-019, REQ-L2-AS-024
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.requirement_service.ServiceBase._set_tenant_context. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_requirement()` → Requirement mit initialem WorkflowState
  - [ ] `update_requirement(change_reason=None)` im Extended → Fehler `"change_reason required"`
  - [ ] `delete_requirement()` → Requirement + alle TraceLinks gelöscht
  - [ ] Nach Schreiboperation: AuditLog-Eintrag vorhanden
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.requirement_service.ServiceBase._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_from_orm_maps_fields`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-003, REQ-L2-AS-013, REQ-L2-AS-019, REQ-L2-AS-024
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_requirement()` → Requirement mit initialem WorkflowState
  - [ ] `update_requirement(change_reason=None)` im Extended → Fehler `"change_reason required"`
  - [ ] `delete_requirement()` → Requirement + alle TraceLinks gelöscht
  - [ ] Nach Schreiboperation: AuditLog-Eintrag vorhanden
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

## Datei: `test_risk_service.py`

### Test: `test_low_low_score_is_1`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_high_high_score_is_9`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_medium_medium_score_is_4`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_score_to_severity_low`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_score_to_severity_medium`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_score_to_severity_high`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_valid_create_passes`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_empty_title_raises`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_invalid_probability_raises`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_invalid_impact_raises`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_invalid_category_raises`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_all_probability_values_valid`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_all_impact_values_valid`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_from_orm_maps_all_fields`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_creates_risk_with_correct_score`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.risk_service.Risk, application.risk_service.RiskService._set_tenant_context, application.risk_service.RiskService._assert_write_permission, application.risk_service.RiskService._audit, application.risk_service.RiskService._emit_event, workflow.services.initialize_workflow_states. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`. Verwendet Behavior Verification (`assert_called_...`) anstatt den echten Systemzustand zu verifizieren.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.risk_service.Risk, application.risk_service.RiskService._set_tenant_context, application.risk_service.RiskService._assert_write_permission, application.risk_service.RiskService._audit, application.risk_service.RiskService._emit_event, workflow.services.initialize_workflow_states` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Tausche `assert_called_...` gegen State Verification aus (z.B. prüfe `Entity.objects.count()`, lade das Objekt neu aus der DB und prüfe veränderte Felder).
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_viewer_cannot_create`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_workflow_init_failure_does_not_abort`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.risk_service.Risk, application.risk_service.RiskService._set_tenant_context, application.risk_service.RiskService._assert_write_permission, application.risk_service.RiskService._audit, application.risk_service.RiskService._emit_event. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.risk_service.Risk, application.risk_service.RiskService._set_tenant_context, application.risk_service.RiskService._assert_write_permission, application.risk_service.RiskService._audit, application.risk_service.RiskService._emit_event` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_audit_entry_written_on_create`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.risk_service.Risk, application.risk_service.RiskService._set_tenant_context, application.risk_service.RiskService._assert_write_permission, application.risk_service.RiskService._audit, application.risk_service.RiskService._emit_event, workflow.services.initialize_workflow_states. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`. Verwendet Behavior Verification (`assert_called_...`) anstatt den echten Systemzustand zu verifizieren.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.risk_service.Risk, application.risk_service.RiskService._set_tenant_context, application.risk_service.RiskService._assert_write_permission, application.risk_service.RiskService._audit, application.risk_service.RiskService._emit_event, workflow.services.initialize_workflow_states` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Tausche `assert_called_...` gegen State Verification aus (z.B. prüfe `Entity.objects.count()`, lade das Objekt neu aus der DB und prüfe veränderte Felder).
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_score_recalculated_on_probability_change`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.risk_service.Risk.objects, application.risk_service.RiskService._set_tenant_context, application.risk_service.RiskService._assert_write_permission, application.risk_service.RiskService._audit, application.risk_service.RiskService._emit_event. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.risk_service.Risk.objects, application.risk_service.RiskService._set_tenant_context, application.risk_service.RiskService._assert_write_permission, application.risk_service.RiskService._audit, application.risk_service.RiskService._emit_event` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_not_found_raises`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.risk_service.Risk.objects, application.risk_service.RiskService._set_tenant_context, application.risk_service.RiskService._assert_write_permission.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.risk_service.Risk.objects, application.risk_service.RiskService._set_tenant_context, application.risk_service.RiskService._assert_write_permission` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_cascades_tracelinks_and_deletes`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.risk_service.Risk.objects, application.risk_service.RiskService._set_tenant_context, application.risk_service.RiskService._assert_write_permission, application.risk_service.RiskService._audit, application.risk_service.RiskService._emit_event. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`. Verwendet Behavior Verification (`assert_called_...`) anstatt den echten Systemzustand zu verifizieren.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.risk_service.Risk.objects, application.risk_service.RiskService._set_tenant_context, application.risk_service.RiskService._assert_write_permission, application.risk_service.RiskService._audit, application.risk_service.RiskService._emit_event` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Tausche `assert_called_...` gegen State Verification aus (z.B. prüfe `Entity.objects.count()`, lade das Objekt neu aus der DB und prüfe veränderte Felder).
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_filters_by_severity_high`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.risk_service.Risk.objects, application.risk_service.RiskService._set_tenant_context. Verwendet Behavior Verification (`assert_called_...`) anstatt den echten Systemzustand zu verifizieren.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.risk_service.Risk.objects, application.risk_service.RiskService._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Tausche `assert_called_...` gegen State Verification aus (z.B. prüfe `Entity.objects.count()`, lade das Objekt neu aus der DB und prüfe veränderte Felder).
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_filters_by_severity_medium`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.risk_service.Risk.objects, application.risk_service.RiskService._set_tenant_context. Verwendet Behavior Verification (`assert_called_...`) anstatt den echten Systemzustand zu verifizieren.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.risk_service.Risk.objects, application.risk_service.RiskService._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Tausche `assert_called_...` gegen State Verification aus (z.B. prüfe `Entity.objects.count()`, lade das Objekt neu aus der DB und prüfe veränderte Felder).
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_invalid_severity_raises_validation_error`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.risk_service.RiskService._set_tenant_context.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.risk_service.RiskService._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_all_valid_severity_values_pass`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.risk_service.Risk.objects, application.risk_service.RiskService._set_tenant_context.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.risk_service.Risk.objects, application.risk_service.RiskService._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_tenant_isolation_in_severity_query`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.risk_service.Risk.objects, application.risk_service.RiskService._set_tenant_context.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.risk_service.Risk.objects, application.risk_service.RiskService._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_valid_link_type_delegates`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.risk_service.Risk.objects, application.risk_service.RiskService._set_tenant_context. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`. Verwendet Behavior Verification (`assert_called_...`) anstatt den echten Systemzustand zu verifizieren.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.risk_service.Risk.objects, application.risk_service.RiskService._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Tausche `assert_called_...` gegen State Verification aus (z.B. prüfe `Entity.objects.count()`, lade das Objekt neu aus der DB und prüfe veränderte Felder).
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_invalid_link_type_raises`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.risk_service.RiskService._set_tenant_context.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.risk_service.RiskService._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_all_valid_link_types`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.risk_service.Risk.objects, application.risk_service.RiskService._set_tenant_context. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.risk_service.Risk.objects, application.risk_service.RiskService._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

## Datei: `test_search_service.py`

### Test: `test_simple_token`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_and_operator`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_or_operator`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_not_operator`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_prefix_search`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_phrase_search`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_empty_query_raises`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_whitespace_only_raises`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_empty_query_raises`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.search_service.TenantContext.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.search_service.TenantContext` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_invalid_type_filter_raises`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.search_service.TenantContext.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.search_service.TenantContext` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_page_less_than_1_raises`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.search_service.TenantContext.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.search_service.TenantContext` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_limit_exceeds_max_raises`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.search_service.TenantContext.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.search_service.TenantContext` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_limit_zero_raises`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.search_service.TenantContext.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.search_service.TenantContext` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_returns_search_result`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.search_service.TenantContext.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.search_service.TenantContext` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_type_filter_restricts_entity_types`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.search_service.TenantContext.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.search_service.TenantContext` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_all_types_searched_without_filter`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.search_service.TenantContext.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.search_service.TenantContext` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_pagination_slices_results`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.search_service.TenantContext.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.search_service.TenantContext` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_tenant_isolation_passes_tenant_id`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.search_service.TenantContext.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.search_service.TenantContext` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_entity_type_failure_degrades_gracefully`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.search_service.TenantContext.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.search_service.TenantContext` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

## Datei: `test_test_run_service.py`

### Test: `test_valid_result_statuses_contains_expected`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-022, REQ-L2-AS-030, REQ-L2-AS-031
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `get_requirement(id, ctx)` → Query enthält `tenant_id=ctx.tenant_id`
  - [ ] `query_requirements(ctx)` → nur Ergebnisse des aktiven Tenants
  - [ ] Zwei Tenants → Query von T1 liefert ausschließlich T1-Daten
  - [ ] Kein Code-Pfad umgeht Custom Manager
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_viewer_cannot_create`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-022, REQ-L2-AS-030, REQ-L2-AS-031
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.test_run_service.ServiceBase._set_tenant_context.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `get_requirement(id, ctx)` → Query enthält `tenant_id=ctx.tenant_id`
  - [ ] `query_requirements(ctx)` → nur Ergebnisse des aktiven Tenants
  - [ ] Zwei Tenants → Query von T1 liefert ausschließlich T1-Daten
  - [ ] Kein Code-Pfad umgeht Custom Manager
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.test_run_service.ServiceBase._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_tenant_not_found_raises`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-022, REQ-L2-AS-030, REQ-L2-AS-031
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.test_run_service.ServiceBase._set_tenant_context.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `get_requirement(id, ctx)` → Query enthält `tenant_id=ctx.tenant_id`
  - [ ] `query_requirements(ctx)` → nur Ergebnisse des aktiven Tenants
  - [ ] Zwei Tenants → Query von T1 liefert ausschließlich T1-Daten
  - [ ] Kein Code-Pfad umgeht Custom Manager
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.test_run_service.ServiceBase._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_workspace_not_found_raises`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-022, REQ-L2-AS-030, REQ-L2-AS-031
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.test_run_service.ServiceBase._set_tenant_context. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `get_requirement(id, ctx)` → Query enthält `tenant_id=ctx.tenant_id`
  - [ ] `query_requirements(ctx)` → nur Ergebnisse des aktiven Tenants
  - [ ] Zwei Tenants → Query von T1 liefert ausschließlich T1-Daten
  - [ ] Kein Code-Pfad umgeht Custom Manager
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.test_run_service.ServiceBase._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_create_success_returns_test_run`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-022, REQ-L2-AS-030, REQ-L2-AS-031
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.test_run_service.ServiceBase._set_tenant_context. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `get_requirement(id, ctx)` → Query enthält `tenant_id=ctx.tenant_id`
  - [ ] `query_requirements(ctx)` → nur Ergebnisse des aktiven Tenants
  - [ ] Zwei Tenants → Query von T1 liefert ausschließlich T1-Daten
  - [ ] Kein Code-Pfad umgeht Custom Manager
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.test_run_service.ServiceBase._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_invalid_status_raises_validation_error`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-022, REQ-L2-AS-030, REQ-L2-AS-031
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.test_run_service.ServiceBase._set_tenant_context.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `get_requirement(id, ctx)` → Query enthält `tenant_id=ctx.tenant_id`
  - [ ] `query_requirements(ctx)` → nur Ergebnisse des aktiven Tenants
  - [ ] Zwei Tenants → Query von T1 liefert ausschließlich T1-Daten
  - [ ] Kein Code-Pfad umgeht Custom Manager
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.test_run_service.ServiceBase._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_test_run_not_found_raises`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-022, REQ-L2-AS-030, REQ-L2-AS-031
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.test_run_service.ServiceBase._set_tenant_context. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `get_requirement(id, ctx)` → Query enthält `tenant_id=ctx.tenant_id`
  - [ ] `query_requirements(ctx)` → nur Ergebnisse des aktiven Tenants
  - [ ] Zwei Tenants → Query von T1 liefert ausschließlich T1-Daten
  - [ ] Kein Code-Pfad umgeht Custom Manager
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.test_run_service.ServiceBase._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_add_result_success`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-022, REQ-L2-AS-030, REQ-L2-AS-031
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.test_run_service.ServiceBase._set_tenant_context. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `get_requirement(id, ctx)` → Query enthält `tenant_id=ctx.tenant_id`
  - [ ] `query_requirements(ctx)` → nur Ergebnisse des aktiven Tenants
  - [ ] Zwei Tenants → Query von T1 liefert ausschließlich T1-Daten
  - [ ] Kein Code-Pfad umgeht Custom Manager
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.test_run_service.ServiceBase._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_10_results_in_one_call_success`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-022, REQ-L2-AS-030, REQ-L2-AS-031
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.test_run_service.ServiceBase._set_tenant_context. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `get_requirement(id, ctx)` → Query enthält `tenant_id=ctx.tenant_id`
  - [ ] `query_requirements(ctx)` → nur Ergebnisse des aktiven Tenants
  - [ ] Zwei Tenants → Query von T1 liefert ausschließlich T1-Daten
  - [ ] Kein Code-Pfad umgeht Custom Manager
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.test_run_service.ServiceBase._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_invalid_status_in_bulk_raises`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-022, REQ-L2-AS-030, REQ-L2-AS-031
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.test_run_service.ServiceBase._set_tenant_context. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `get_requirement(id, ctx)` → Query enthält `tenant_id=ctx.tenant_id`
  - [ ] `query_requirements(ctx)` → nur Ergebnisse des aktiven Tenants
  - [ ] Zwei Tenants → Query von T1 liefert ausschließlich T1-Daten
  - [ ] Kein Code-Pfad umgeht Custom Manager
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.test_run_service.ServiceBase._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_missing_test_case_id_raises`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-022, REQ-L2-AS-030, REQ-L2-AS-031
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.test_run_service.ServiceBase._set_tenant_context. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `get_requirement(id, ctx)` → Query enthält `tenant_id=ctx.tenant_id`
  - [ ] `query_requirements(ctx)` → nur Ergebnisse des aktiven Tenants
  - [ ] Zwei Tenants → Query von T1 liefert ausschließlich T1-Daten
  - [ ] Kein Code-Pfad umgeht Custom Manager
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.test_run_service.ServiceBase._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_all_passed_returns_passed`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-022, REQ-L2-AS-030, REQ-L2-AS-031
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.test_run_service.ServiceBase._set_tenant_context. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `get_requirement(id, ctx)` → Query enthält `tenant_id=ctx.tenant_id`
  - [ ] `query_requirements(ctx)` → nur Ergebnisse des aktiven Tenants
  - [ ] Zwei Tenants → Query von T1 liefert ausschließlich T1-Daten
  - [ ] Kein Code-Pfad umgeht Custom Manager
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.test_run_service.ServiceBase._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_any_failed_returns_failed`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-022, REQ-L2-AS-030, REQ-L2-AS-031
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.test_run_service.ServiceBase._set_tenant_context. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `get_requirement(id, ctx)` → Query enthält `tenant_id=ctx.tenant_id`
  - [ ] `query_requirements(ctx)` → nur Ergebnisse des aktiven Tenants
  - [ ] Zwei Tenants → Query von T1 liefert ausschließlich T1-Daten
  - [ ] Kein Code-Pfad umgeht Custom Manager
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.test_run_service.ServiceBase._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_any_blocked_returns_partial`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-022, REQ-L2-AS-030, REQ-L2-AS-031
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.test_run_service.ServiceBase._set_tenant_context. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `get_requirement(id, ctx)` → Query enthält `tenant_id=ctx.tenant_id`
  - [ ] `query_requirements(ctx)` → nur Ergebnisse des aktiven Tenants
  - [ ] Zwei Tenants → Query von T1 liefert ausschließlich T1-Daten
  - [ ] Kein Code-Pfad umgeht Custom Manager
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.test_run_service.ServiceBase._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_get_returns_test_run`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-022, REQ-L2-AS-030, REQ-L2-AS-031
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.test_run_service.ServiceBase._set_tenant_context. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `get_requirement(id, ctx)` → Query enthält `tenant_id=ctx.tenant_id`
  - [ ] `query_requirements(ctx)` → nur Ergebnisse des aktiven Tenants
  - [ ] Zwei Tenants → Query von T1 liefert ausschließlich T1-Daten
  - [ ] Kein Code-Pfad umgeht Custom Manager
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.test_run_service.ServiceBase._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_get_not_found_raises`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-022, REQ-L2-AS-030, REQ-L2-AS-031
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.test_run_service.ServiceBase._set_tenant_context. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `get_requirement(id, ctx)` → Query enthält `tenant_id=ctx.tenant_id`
  - [ ] `query_requirements(ctx)` → nur Ergebnisse des aktiven Tenants
  - [ ] Zwei Tenants → Query von T1 liefert ausschließlich T1-Daten
  - [ ] Kein Code-Pfad umgeht Custom Manager
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.test_run_service.ServiceBase._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_list_returns_all`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-022, REQ-L2-AS-030, REQ-L2-AS-031
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.test_run_service.ServiceBase._set_tenant_context. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `get_requirement(id, ctx)` → Query enthält `tenant_id=ctx.tenant_id`
  - [ ] `query_requirements(ctx)` → nur Ergebnisse des aktiven Tenants
  - [ ] Zwei Tenants → Query von T1 liefert ausschließlich T1-Daten
  - [ ] Kein Code-Pfad umgeht Custom Manager
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.test_run_service.ServiceBase._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_set_tenant_context_called_on_get`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-022, REQ-L2-AS-030, REQ-L2-AS-031
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`. Verwendet Behavior Verification (`assert_called_...`) anstatt den echten Systemzustand zu verifizieren.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `get_requirement(id, ctx)` → Query enthält `tenant_id=ctx.tenant_id`
  - [ ] `query_requirements(ctx)` → nur Ergebnisse des aktiven Tenants
  - [ ] Zwei Tenants → Query von T1 liefert ausschließlich T1-Daten
  - [ ] Kein Code-Pfad umgeht Custom Manager
- **Exakter Refactoring-Bedarf:**
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Tausche `assert_called_...` gegen State Verification aus (z.B. prüfe `Entity.objects.count()`, lade das Objekt neu aus der DB und prüfe veränderte Felder).
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

## Datei: `test_test_service.py`

### Test: `test_valid_test_types_contains_expected`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-005, REQ-L2-AS-022, REQ-L2-AS-025
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_test_case()` → TestCase mit test_type und WorkflowState
  - [ ] `update_test_status(id, "Passed")` → execution_status gesetzt
  - [ ] Query mit Filtern → gefilterte Liste
  - [ ] Delete → TraceLinks gelöscht
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_valid_execution_statuses_contains_expected`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-005, REQ-L2-AS-022, REQ-L2-AS-025
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_test_case()` → TestCase mit test_type und WorkflowState
  - [ ] `update_test_status(id, "Passed")` → execution_status gesetzt
  - [ ] Query mit Filtern → gefilterte Liste
  - [ ] Delete → TraceLinks gelöscht
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_viewer_cannot_create`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-005, REQ-L2-AS-022, REQ-L2-AS-025
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.test_service.ServiceBase._set_tenant_context.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_test_case()` → TestCase mit test_type und WorkflowState
  - [ ] `update_test_status(id, "Passed")` → execution_status gesetzt
  - [ ] Query mit Filtern → gefilterte Liste
  - [ ] Delete → TraceLinks gelöscht
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.test_service.ServiceBase._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_invalid_test_type_raises_validation_error`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-005, REQ-L2-AS-022, REQ-L2-AS-025
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.test_service.ServiceBase._set_tenant_context.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_test_case()` → TestCase mit test_type und WorkflowState
  - [ ] `update_test_status(id, "Passed")` → execution_status gesetzt
  - [ ] Query mit Filtern → gefilterte Liste
  - [ ] Delete → TraceLinks gelöscht
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.test_service.ServiceBase._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_tenant_not_found_raises`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-005, REQ-L2-AS-022, REQ-L2-AS-025
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.test_service.ServiceBase._set_tenant_context.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_test_case()` → TestCase mit test_type und WorkflowState
  - [ ] `update_test_status(id, "Passed")` → execution_status gesetzt
  - [ ] Query mit Filtern → gefilterte Liste
  - [ ] Delete → TraceLinks gelöscht
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.test_service.ServiceBase._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_workspace_not_found_raises`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-005, REQ-L2-AS-022, REQ-L2-AS-025
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.test_service.ServiceBase._set_tenant_context. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_test_case()` → TestCase mit test_type und WorkflowState
  - [ ] `update_test_status(id, "Passed")` → execution_status gesetzt
  - [ ] Query mit Filtern → gefilterte Liste
  - [ ] Delete → TraceLinks gelöscht
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.test_service.ServiceBase._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_create_success_returns_test_case`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-005, REQ-L2-AS-022, REQ-L2-AS-025
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.test_service.ServiceBase._set_tenant_context. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_test_case()` → TestCase mit test_type und WorkflowState
  - [ ] `update_test_status(id, "Passed")` → execution_status gesetzt
  - [ ] Query mit Filtern → gefilterte Liste
  - [ ] Delete → TraceLinks gelöscht
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.test_service.ServiceBase._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_audit_called_on_create`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-005, REQ-L2-AS-022, REQ-L2-AS-025
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.test_service.ServiceBase._set_tenant_context. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`. Verwendet Behavior Verification (`assert_called_...`) anstatt den echten Systemzustand zu verifizieren.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_test_case()` → TestCase mit test_type und WorkflowState
  - [ ] `update_test_status(id, "Passed")` → execution_status gesetzt
  - [ ] Query mit Filtern → gefilterte Liste
  - [ ] Delete → TraceLinks gelöscht
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.test_service.ServiceBase._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Tausche `assert_called_...` gegen State Verification aus (z.B. prüfe `Entity.objects.count()`, lade das Objekt neu aus der DB und prüfe veränderte Felder).
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_not_found_raises`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-005, REQ-L2-AS-022, REQ-L2-AS-025
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.test_service.ServiceBase._set_tenant_context. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_test_case()` → TestCase mit test_type und WorkflowState
  - [ ] `update_test_status(id, "Passed")` → execution_status gesetzt
  - [ ] Query mit Filtern → gefilterte Liste
  - [ ] Delete → TraceLinks gelöscht
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.test_service.ServiceBase._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_update_title_success`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-005, REQ-L2-AS-022, REQ-L2-AS-025
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.test_service.ServiceBase._set_tenant_context. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`. Verwendet Behavior Verification (`assert_called_...`) anstatt den echten Systemzustand zu verifizieren.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_test_case()` → TestCase mit test_type und WorkflowState
  - [ ] `update_test_status(id, "Passed")` → execution_status gesetzt
  - [ ] Query mit Filtern → gefilterte Liste
  - [ ] Delete → TraceLinks gelöscht
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.test_service.ServiceBase._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Tausche `assert_called_...` gegen State Verification aus (z.B. prüfe `Entity.objects.count()`, lade das Objekt neu aus der DB und prüfe veränderte Felder).
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_invalid_status_raises_validation_error`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-005, REQ-L2-AS-022, REQ-L2-AS-025
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.test_service.ServiceBase._set_tenant_context.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_test_case()` → TestCase mit test_type und WorkflowState
  - [ ] `update_test_status(id, "Passed")` → execution_status gesetzt
  - [ ] Query mit Filtern → gefilterte Liste
  - [ ] Delete → TraceLinks gelöscht
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.test_service.ServiceBase._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_valid_status_passed_accepted`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-005, REQ-L2-AS-022, REQ-L2-AS-025
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.test_service.ServiceBase._set_tenant_context. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`. Verwendet Behavior Verification (`assert_called_...`) anstatt den echten Systemzustand zu verifizieren.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_test_case()` → TestCase mit test_type und WorkflowState
  - [ ] `update_test_status(id, "Passed")` → execution_status gesetzt
  - [ ] Query mit Filtern → gefilterte Liste
  - [ ] Delete → TraceLinks gelöscht
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.test_service.ServiceBase._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Tausche `assert_called_...` gegen State Verification aus (z.B. prüfe `Entity.objects.count()`, lade das Objekt neu aus der DB und prüfe veränderte Felder).
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_valid_status_failed_accepted`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-005, REQ-L2-AS-022, REQ-L2-AS-025
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.test_service.ServiceBase._set_tenant_context. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_test_case()` → TestCase mit test_type und WorkflowState
  - [ ] `update_test_status(id, "Passed")` → execution_status gesetzt
  - [ ] Query mit Filtern → gefilterte Liste
  - [ ] Delete → TraceLinks gelöscht
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.test_service.ServiceBase._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_not_found_raises`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-005, REQ-L2-AS-022, REQ-L2-AS-025
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.test_service.ServiceBase._set_tenant_context. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_test_case()` → TestCase mit test_type und WorkflowState
  - [ ] `update_test_status(id, "Passed")` → execution_status gesetzt
  - [ ] Query mit Filtern → gefilterte Liste
  - [ ] Delete → TraceLinks gelöscht
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.test_service.ServiceBase._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_delete_not_found_raises`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-005, REQ-L2-AS-022, REQ-L2-AS-025
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.test_service.ServiceBase._set_tenant_context. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_test_case()` → TestCase mit test_type und WorkflowState
  - [ ] `update_test_status(id, "Passed")` → execution_status gesetzt
  - [ ] Query mit Filtern → gefilterte Liste
  - [ ] Delete → TraceLinks gelöscht
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.test_service.ServiceBase._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_delete_cascades_trace_links`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-005, REQ-L2-AS-022, REQ-L2-AS-025
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.test_service.ServiceBase._set_tenant_context. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`. Verwendet Behavior Verification (`assert_called_...`) anstatt den echten Systemzustand zu verifizieren.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_test_case()` → TestCase mit test_type und WorkflowState
  - [ ] `update_test_status(id, "Passed")` → execution_status gesetzt
  - [ ] Query mit Filtern → gefilterte Liste
  - [ ] Delete → TraceLinks gelöscht
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.test_service.ServiceBase._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Tausche `assert_called_...` gegen State Verification aus (z.B. prüfe `Entity.objects.count()`, lade das Objekt neu aus der DB und prüfe veränderte Felder).
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_get_returns_test_case`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-005, REQ-L2-AS-022, REQ-L2-AS-025
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.test_service.ServiceBase._set_tenant_context. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_test_case()` → TestCase mit test_type und WorkflowState
  - [ ] `update_test_status(id, "Passed")` → execution_status gesetzt
  - [ ] Query mit Filtern → gefilterte Liste
  - [ ] Delete → TraceLinks gelöscht
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.test_service.ServiceBase._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_get_not_found_raises`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-005, REQ-L2-AS-022, REQ-L2-AS-025
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.test_service.ServiceBase._set_tenant_context. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_test_case()` → TestCase mit test_type und WorkflowState
  - [ ] `update_test_status(id, "Passed")` → execution_status gesetzt
  - [ ] Query mit Filtern → gefilterte Liste
  - [ ] Delete → TraceLinks gelöscht
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.test_service.ServiceBase._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_list_returns_all`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-005, REQ-L2-AS-022, REQ-L2-AS-025
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.test_service.ServiceBase._set_tenant_context. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_test_case()` → TestCase mit test_type und WorkflowState
  - [ ] `update_test_status(id, "Passed")` → execution_status gesetzt
  - [ ] Query mit Filtern → gefilterte Liste
  - [ ] Delete → TraceLinks gelöscht
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.test_service.ServiceBase._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_set_tenant_context_called_on_get`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-005, REQ-L2-AS-022, REQ-L2-AS-025
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`. Verwendet Behavior Verification (`assert_called_...`) anstatt den echten Systemzustand zu verifizieren.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_test_case()` → TestCase mit test_type und WorkflowState
  - [ ] `update_test_status(id, "Passed")` → execution_status gesetzt
  - [ ] Query mit Filtern → gefilterte Liste
  - [ ] Delete → TraceLinks gelöscht
- **Exakter Refactoring-Bedarf:**
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Tausche `assert_called_...` gegen State Verification aus (z.B. prüfe `Entity.objects.count()`, lade das Objekt neu aus der DB und prüfe veränderte Felder).
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

## Datei: `test_trace_link_service.py`

### Test: `test_all_ten_types_present`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-010
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_tracelink(source, target, "satisfies")` → erstellt wenn beide existieren
  - [ ] Source nicht vorhanden → Fehler `"Source entity not found"`
  - [ ] Ungültiger Link-Typ → Fehler `"Invalid link type"`
  - [ ] Nach Erstellung: AuditLog-Eintrag vorhanden
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_types_is_frozenset`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-010
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_tracelink(source, target, "satisfies")` → erstellt wenn beide existieren
  - [ ] Source nicht vorhanden → Fehler `"Source entity not found"`
  - [ ] Ungültiger Link-Typ → Fehler `"Invalid link type"`
  - [ ] Nach Erstellung: AuditLog-Eintrag vorhanden
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_invalid_link_type_raises_validation_error`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-010
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.trace_link_service.ServiceBase._set_tenant_context.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_tracelink(source, target, "satisfies")` → erstellt wenn beide existieren
  - [ ] Source nicht vorhanden → Fehler `"Source entity not found"`
  - [ ] Ungültiger Link-Typ → Fehler `"Invalid link type"`
  - [ ] Nach Erstellung: AuditLog-Eintrag vorhanden
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.trace_link_service.ServiceBase._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_all_valid_link_types_accepted`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-010
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.trace_link_service.ServiceBase._set_tenant_context. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`. Verwendet Behavior Verification (`assert_called_...`) anstatt den echten Systemzustand zu verifizieren.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_tracelink(source, target, "satisfies")` → erstellt wenn beide existieren
  - [ ] Source nicht vorhanden → Fehler `"Source entity not found"`
  - [ ] Ungültiger Link-Typ → Fehler `"Invalid link type"`
  - [ ] Nach Erstellung: AuditLog-Eintrag vorhanden
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.trace_link_service.ServiceBase._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Tausche `assert_called_...` gegen State Verification aus (z.B. prüfe `Entity.objects.count()`, lade das Objekt neu aus der DB und prüfe veränderte Felder).
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_source_not_found_remapped_to_not_found_error`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-010
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.trace_link_service.ServiceBase._set_tenant_context.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_tracelink(source, target, "satisfies")` → erstellt wenn beide existieren
  - [ ] Source nicht vorhanden → Fehler `"Source entity not found"`
  - [ ] Ungültiger Link-Typ → Fehler `"Invalid link type"`
  - [ ] Nach Erstellung: AuditLog-Eintrag vorhanden
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.trace_link_service.ServiceBase._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_target_not_found_remapped_to_not_found_error`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-010
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.trace_link_service.ServiceBase._set_tenant_context.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_tracelink(source, target, "satisfies")` → erstellt wenn beide existieren
  - [ ] Source nicht vorhanden → Fehler `"Source entity not found"`
  - [ ] Ungültiger Link-Typ → Fehler `"Invalid link type"`
  - [ ] Nach Erstellung: AuditLog-Eintrag vorhanden
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.trace_link_service.ServiceBase._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_cross_workspace_error_remapped_to_validation_error`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-010
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.trace_link_service.ServiceBase._set_tenant_context.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_tracelink(source, target, "satisfies")` → erstellt wenn beide existieren
  - [ ] Source nicht vorhanden → Fehler `"Source entity not found"`
  - [ ] Ungültiger Link-Typ → Fehler `"Invalid link type"`
  - [ ] Nach Erstellung: AuditLog-Eintrag vorhanden
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.trace_link_service.ServiceBase._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_audit_called_on_create`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-010
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.trace_link_service.ServiceBase._set_tenant_context. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`. Verwendet Behavior Verification (`assert_called_...`) anstatt den echten Systemzustand zu verifizieren.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_tracelink(source, target, "satisfies")` → erstellt wenn beide existieren
  - [ ] Source nicht vorhanden → Fehler `"Source entity not found"`
  - [ ] Ungültiger Link-Typ → Fehler `"Invalid link type"`
  - [ ] Nach Erstellung: AuditLog-Eintrag vorhanden
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.trace_link_service.ServiceBase._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Tausche `assert_called_...` gegen State Verification aus (z.B. prüfe `Entity.objects.count()`, lade das Objekt neu aus der DB und prüfe veränderte Felder).
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_tenant_context_set_on_create`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-010
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Verwendet Behavior Verification (`assert_called_...`) anstatt den echten Systemzustand zu verifizieren.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_tracelink(source, target, "satisfies")` → erstellt wenn beide existieren
  - [ ] Source nicht vorhanden → Fehler `"Source entity not found"`
  - [ ] Ungültiger Link-Typ → Fehler `"Invalid link type"`
  - [ ] Nach Erstellung: AuditLog-Eintrag vorhanden
- **Exakter Refactoring-Bedarf:**
  - Tausche `assert_called_...` gegen State Verification aus (z.B. prüfe `Entity.objects.count()`, lade das Objekt neu aus der DB und prüfe veränderte Felder).
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_returns_zero_when_no_links`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-010
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.trace_link_service.ServiceBase._set_tenant_context.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_tracelink(source, target, "satisfies")` → erstellt wenn beide existieren
  - [ ] Source nicht vorhanden → Fehler `"Source entity not found"`
  - [ ] Ungültiger Link-Typ → Fehler `"Invalid link type"`
  - [ ] Nach Erstellung: AuditLog-Eintrag vorhanden
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.trace_link_service.ServiceBase._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_deletes_all_upstream_and_downstream_links`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-010
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.trace_link_service.ServiceBase._set_tenant_context. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`. Verwendet Behavior Verification (`assert_called_...`) anstatt den echten Systemzustand zu verifizieren.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_tracelink(source, target, "satisfies")` → erstellt wenn beide existieren
  - [ ] Source nicht vorhanden → Fehler `"Source entity not found"`
  - [ ] Ungültiger Link-Typ → Fehler `"Invalid link type"`
  - [ ] Nach Erstellung: AuditLog-Eintrag vorhanden
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.trace_link_service.ServiceBase._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Tausche `assert_called_...` gegen State Verification aus (z.B. prüfe `Entity.objects.count()`, lade das Objekt neu aus der DB und prüfe veränderte Felder).
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_query_delegates_to_traceability_engine`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-010
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.trace_link_service.ServiceBase._set_tenant_context. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`. Verwendet Behavior Verification (`assert_called_...`) anstatt den echten Systemzustand zu verifizieren.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_tracelink(source, target, "satisfies")` → erstellt wenn beide existieren
  - [ ] Source nicht vorhanden → Fehler `"Source entity not found"`
  - [ ] Ungültiger Link-Typ → Fehler `"Invalid link type"`
  - [ ] Nach Erstellung: AuditLog-Eintrag vorhanden
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.trace_link_service.ServiceBase._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Tausche `assert_called_...` gegen State Verification aus (z.B. prüfe `Entity.objects.count()`, lade das Objekt neu aus der DB und prüfe veränderte Felder).
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_query_filters_by_link_type`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-010
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.trace_link_service.ServiceBase._set_tenant_context. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`. Verwendet Behavior Verification (`assert_called_...`) anstatt den echten Systemzustand zu verifizieren.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_tracelink(source, target, "satisfies")` → erstellt wenn beide existieren
  - [ ] Source nicht vorhanden → Fehler `"Source entity not found"`
  - [ ] Ungültiger Link-Typ → Fehler `"Invalid link type"`
  - [ ] Nach Erstellung: AuditLog-Eintrag vorhanden
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.trace_link_service.ServiceBase._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Tausche `assert_called_...` gegen State Verification aus (z.B. prüfe `Entity.objects.count()`, lade das Objekt neu aus der DB und prüfe veränderte Felder).
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_query_without_ctx_skips_tenant_context`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-010
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Verwendet Behavior Verification (`assert_called_...`) anstatt den echten Systemzustand zu verifizieren.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_tracelink(source, target, "satisfies")` → erstellt wenn beide existieren
  - [ ] Source nicht vorhanden → Fehler `"Source entity not found"`
  - [ ] Ungültiger Link-Typ → Fehler `"Invalid link type"`
  - [ ] Nach Erstellung: AuditLog-Eintrag vorhanden
- **Exakter Refactoring-Bedarf:**
  - Tausche `assert_called_...` gegen State Verification aus (z.B. prüfe `Entity.objects.count()`, lade das Objekt neu aus der DB und prüfe veränderte Felder).
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_artifact_id_returned_unchanged`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-010
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`. Verwendet Behavior Verification (`assert_called_...`) anstatt den echten Systemzustand zu verifizieren.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_tracelink(source, target, "satisfies")` → erstellt wenn beide existieren
  - [ ] Source nicht vorhanden → Fehler `"Source entity not found"`
  - [ ] Ungültiger Link-Typ → Fehler `"Invalid link type"`
  - [ ] Nach Erstellung: AuditLog-Eintrag vorhanden
- **Exakter Refactoring-Bedarf:**
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Tausche `assert_called_...` gegen State Verification aus (z.B. prüfe `Entity.objects.count()`, lade das Objekt neu aus der DB und prüfe veränderte Felder).
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_requirement_id_resolves_to_artifact_id`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-010
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`. Verwendet Behavior Verification (`assert_called_...`) anstatt den echten Systemzustand zu verifizieren.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_tracelink(source, target, "satisfies")` → erstellt wenn beide existieren
  - [ ] Source nicht vorhanden → Fehler `"Source entity not found"`
  - [ ] Ungültiger Link-Typ → Fehler `"Invalid link type"`
  - [ ] Nach Erstellung: AuditLog-Eintrag vorhanden
- **Exakter Refactoring-Bedarf:**
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Tausche `assert_called_...` gegen State Verification aus (z.B. prüfe `Entity.objects.count()`, lade das Objekt neu aus der DB und prüfe veränderte Felder).
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_architecture_element_id_resolves_to_artifact_id`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-010
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`. Verwendet Behavior Verification (`assert_called_...`) anstatt den echten Systemzustand zu verifizieren.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_tracelink(source, target, "satisfies")` → erstellt wenn beide existieren
  - [ ] Source nicht vorhanden → Fehler `"Source entity not found"`
  - [ ] Ungültiger Link-Typ → Fehler `"Invalid link type"`
  - [ ] Nach Erstellung: AuditLog-Eintrag vorhanden
- **Exakter Refactoring-Bedarf:**
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Tausche `assert_called_...` gegen State Verification aus (z.B. prüfe `Entity.objects.count()`, lade das Objekt neu aus der DB und prüfe veränderte Felder).
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_unknown_id_raises_not_found_error`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-010
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_tracelink(source, target, "satisfies")` → erstellt wenn beide existieren
  - [ ] Source nicht vorhanden → Fehler `"Source entity not found"`
  - [ ] Ungültiger Link-Typ → Fehler `"Invalid link type"`
  - [ ] Nach Erstellung: AuditLog-Eintrag vorhanden
- **Exakter Refactoring-Bedarf:**
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_create_trace_link_resolves_source_and_target`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-010
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.trace_link_service.ServiceBase._set_tenant_context. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`. Verwendet Behavior Verification (`assert_called_...`) anstatt den echten Systemzustand zu verifizieren.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_tracelink(source, target, "satisfies")` → erstellt wenn beide existieren
  - [ ] Source nicht vorhanden → Fehler `"Source entity not found"`
  - [ ] Ungültiger Link-Typ → Fehler `"Invalid link type"`
  - [ ] Nach Erstellung: AuditLog-Eintrag vorhanden
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.trace_link_service.ServiceBase._set_tenant_context` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Tausche `assert_called_...` gegen State Verification aus (z.B. prüfe `Entity.objects.count()`, lade das Objekt neu aus der DB und prüfe veränderte Felder).
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_allocated_to_link_runs_invariant_check`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-010
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Verwendet Behavior Verification (`assert_called_...`) anstatt den echten Systemzustand zu verifizieren.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_tracelink(source, target, "satisfies")` → erstellt wenn beide existieren
  - [ ] Source nicht vorhanden → Fehler `"Source entity not found"`
  - [ ] Ungültiger Link-Typ → Fehler `"Invalid link type"`
  - [ ] Nach Erstellung: AuditLog-Eintrag vorhanden
- **Exakter Refactoring-Bedarf:**
  - Tausche `assert_called_...` gegen State Verification aus (z.B. prüfe `Entity.objects.count()`, lade das Objekt neu aus der DB und prüfe veränderte Felder).
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_other_link_types_skip_invariant_check`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-010
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_tracelink(source, target, "satisfies")` → erstellt wenn beide existieren
  - [ ] Source nicht vorhanden → Fehler `"Source entity not found"`
  - [ ] Ungültiger Link-Typ → Fehler `"Invalid link type"`
  - [ ] Nach Erstellung: AuditLog-Eintrag vorhanden
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_check_delegates_to_validator_for_element_pairs`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-010
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`. Verwendet Behavior Verification (`assert_called_...`) anstatt den echten Systemzustand zu verifizieren.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_tracelink(source, target, "satisfies")` → erstellt wenn beide existieren
  - [ ] Source nicht vorhanden → Fehler `"Source entity not found"`
  - [ ] Ungültiger Link-Typ → Fehler `"Invalid link type"`
  - [ ] Nach Erstellung: AuditLog-Eintrag vorhanden
- **Exakter Refactoring-Bedarf:**
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Tausche `assert_called_...` gegen State Verification aus (z.B. prüfe `Entity.objects.count()`, lade das Objekt neu aus der DB und prüfe veränderte Felder).
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_check_skips_when_endpoint_is_not_an_element`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-010
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `create_tracelink(source, target, "satisfies")` → erstellt wenn beide existieren
  - [ ] Source nicht vorhanden → Fehler `"Source entity not found"`
  - [ ] Ungültiger Link-Typ → Fehler `"Invalid link type"`
  - [ ] Nach Erstellung: AuditLog-Eintrag vorhanden
- **Exakter Refactoring-Bedarf:**
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

## Datei: `test_webhook_dispatcher.py`

### Test: `test_registers_for_all_subscribed_types`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_unsubscribe_removes_all`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_ignores_unsubscribed_event_type`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_no_subscriptions_skips_dispatch`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_dispatches_to_each_subscription`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_payload_contains_required_fields`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.webhook_dispatcher.timezone.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.webhook_dispatcher.timezone` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_no_sensitive_fields_in_payload`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_signature_format`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_consistent_with_known_value`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_different_secret_produces_different_sig`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_success_2xx`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_http_error_4xx`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_url_error`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_signature_header_added_when_secret_provided`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_4xx_does_not_retry`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.models.WebhookDeliveryLog.objects.create.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.models.WebhookDeliveryLog.objects.create` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_5xx_retries_up_to_max`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.models.WebhookDeliveryLog.objects.create, application.webhook_dispatcher.time.sleep.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.models.WebhookDeliveryLog.objects.create, application.webhook_dispatcher.time.sleep` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_success_stops_retrying`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.models.WebhookDeliveryLog.objects.create.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.models.WebhookDeliveryLog.objects.create` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_returns_same_instance`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_returns_webhook_dispatcher_instance`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

## Datei: `test_workflow_facade.py`

### Test: `test_delegates_to_workflow_transition`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-009
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.workflow_facade.TenantContext, application.workflow_facade.transaction. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`. Verwendet Behavior Verification (`assert_called_...`) anstatt den echten Systemzustand zu verifizieren.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `search(query="test", types=["requirement"])` → nur Requirement-Treffer
  - [ ] `search(query="test", workspace_id=X)` → nur Treffer aus Workspace X
  - [ ] Kombination beider Filter → korrekt gefiltert
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.workflow_facade.TenantContext, application.workflow_facade.transaction` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Tausche `assert_called_...` gegen State Verification aus (z.B. prüfe `Entity.objects.count()`, lade das Objekt neu aus der DB und prüfe veränderte Felder).
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_audit_called_on_success`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-009
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.workflow_facade.TenantContext, application.workflow_facade.WorkflowFacade._check_change_reason, application.workflow_facade.WorkflowFacade._check_transition_roles, application.workflow_facade.transaction. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`. Verwendet Behavior Verification (`assert_called_...`) anstatt den echten Systemzustand zu verifizieren.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `search(query="test", types=["requirement"])` → nur Requirement-Treffer
  - [ ] `search(query="test", workspace_id=X)` → nur Treffer aus Workspace X
  - [ ] Kombination beider Filter → korrekt gefiltert
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.workflow_facade.TenantContext, application.workflow_facade.WorkflowFacade._check_change_reason, application.workflow_facade.WorkflowFacade._check_transition_roles, application.workflow_facade.transaction` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Tausche `assert_called_...` gegen State Verification aus (z.B. prüfe `Entity.objects.count()`, lade das Objekt neu aus der DB und prüfe veränderte Felder).
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_workflow_transitioned_event_emitted`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-009
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.workflow_facade.TenantContext, application.workflow_facade.WorkflowFacade._check_change_reason, application.workflow_facade.WorkflowFacade._check_transition_roles, application.workflow_facade.transaction. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`. Verwendet Behavior Verification (`assert_called_...`) anstatt den echten Systemzustand zu verifizieren.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `search(query="test", types=["requirement"])` → nur Requirement-Treffer
  - [ ] `search(query="test", workspace_id=X)` → nur Treffer aus Workspace X
  - [ ] Kombination beider Filter → korrekt gefiltert
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.workflow_facade.TenantContext, application.workflow_facade.WorkflowFacade._check_change_reason, application.workflow_facade.WorkflowFacade._check_transition_roles, application.workflow_facade.transaction` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Tausche `assert_called_...` gegen State Verification aus (z.B. prüfe `Entity.objects.count()`, lade das Objekt neu aus der DB und prüfe veränderte Felder).
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_raises_when_required_and_missing`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-009
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `search(query="test", types=["requirement"])` → nur Requirement-Treffer
  - [ ] `search(query="test", workspace_id=X)` → nur Treffer aus Workspace X
  - [ ] Kombination beider Filter → korrekt gefiltert
- **Exakter Refactoring-Bedarf:**
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_raises_when_required_and_too_long`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-009
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `search(query="test", types=["requirement"])` → nur Requirement-Treffer
  - [ ] `search(query="test", workspace_id=X)` → nur Treffer aus Workspace X
  - [ ] Kombination beider Filter → korrekt gefiltert
- **Exakter Refactoring-Bedarf:**
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_passes_when_not_required`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-009
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `search(query="test", types=["requirement"])` → nur Requirement-Treffer
  - [ ] `search(query="test", workspace_id=X)` → nur Treffer aus Workspace X
  - [ ] Kombination beider Filter → korrekt gefiltert
- **Exakter Refactoring-Bedarf:**
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_passes_when_required_and_provided`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-009
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `search(query="test", types=["requirement"])` → nur Requirement-Treffer
  - [ ] `search(query="test", workspace_id=X)` → nur Treffer aus Workspace X
  - [ ] Kombination beider Filter → korrekt gefiltert
- **Exakter Refactoring-Bedarf:**
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_raises_when_denied`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-009
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `search(query="test", types=["requirement"])` → nur Requirement-Treffer
  - [ ] `search(query="test", workspace_id=X)` → nur Treffer aus Workspace X
  - [ ] Kombination beider Filter → korrekt gefiltert
- **Exakter Refactoring-Bedarf:**
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_passes_when_allowed`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-009
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Ersetzt echte Datenbank-Modelle oder Services durch `MagicMock`.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `search(query="test", types=["requirement"])` → nur Requirement-Treffer
  - [ ] `search(query="test", workspace_id=X)` → nur Treffer aus Workspace X
  - [ ] Kombination beider Filter → korrekt gefiltert
- **Exakter Refactoring-Bedarf:**
  - Ersetze `MagicMock` durch echte Django ORM Model-Factories (z.B. via FactoryBoy) oder echte Service-Instanzen.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_remaps_role_error_to_permission_denied`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-009
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `search(query="test", types=["requirement"])` → nur Requirement-Treffer
  - [ ] `search(query="test", workspace_id=X)` → nur Treffer aus Workspace X
  - [ ] Kombination beider Filter → korrekt gefiltert
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_remaps_other_wf_error_to_validation_error`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-009
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `search(query="test", types=["requirement"])` → nur Requirement-Treffer
  - [ ] `search(query="test", workspace_id=X)` → nur Treffer aus Workspace X
  - [ ] Kombination beider Filter → korrekt gefiltert
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_passes_through_unknown`
- **Verknüpfte REQ-L2 ID:** REQ-L2-AS-009
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  - [ ] `search(query="test", types=["requirement"])` → nur Requirement-Treffer
  - [ ] `search(query="test", workspace_id=X)` → nur Treffer aus Workspace X
  - [ ] Kombination beider Filter → korrekt gefiltert
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

## Datei: `test_workspace_lifecycle.py`

### Test: `test_close_workspace_sets_inactive`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.workspace_service.ServiceBase._audit.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.workspace_service.ServiceBase._audit` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_close_workspace_non_admin_denied`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_close_workspace_not_found`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_close_audit_entry_created`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.workspace_service.ServiceBase._audit. Verwendet Behavior Verification (`assert_called_...`) anstatt den echten Systemzustand zu verifizieren.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.workspace_service.ServiceBase._audit` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Tausche `assert_called_...` gegen State Verification aus (z.B. prüfe `Entity.objects.count()`, lade das Objekt neu aus der DB und prüfe veränderte Felder).
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_reactivate_workspace_sets_active`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.workspace_service.ServiceBase._audit.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.workspace_service.ServiceBase._audit` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_reactivate_workspace_non_admin_denied`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_delete_workspace_with_correct_captcha_succeeds`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.workspace_service.ServiceBase._audit.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.workspace_service.ServiceBase._audit` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_delete_workspace_with_wrong_captcha_raises`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_delete_workspace_cascades_to_requirements`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.workspace_service.ServiceBase._audit.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.workspace_service.ServiceBase._audit` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_delete_workspace_with_baselines_fails`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.workspace_service.ServiceBase._audit.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.workspace_service.ServiceBase._audit` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_delete_workspace_cascades_to_tracelinks`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.workspace_service.ServiceBase._audit.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.workspace_service.ServiceBase._audit` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_delete_workspace_cascades_to_testcases`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.workspace_service.ServiceBase._audit.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.workspace_service.ServiceBase._audit` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_delete_workspace_cascades_to_architecture_elements`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.workspace_service.ServiceBase._audit.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.workspace_service.ServiceBase._audit` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_delete_workspace_is_atomic`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test ist **zu oberflächlich (shallow)**. Isoliert die Testumgebung durch `patch` von: application.workspace_service.ServiceBase._audit, baseline.models.BaselineSnapshot.unscoped.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Entferne die Patches für `application.workspace_service.ServiceBase._audit, baseline.models.BaselineSnapshot.unscoped` und stelle sicher, dass echte Instanzen/Abhängigkeiten im Integrationstest-Kontext genutzt werden.
  - Ergänze `@pytest.mark.django_db` falls fehlend und führe den Test gegen eine Testdatenbank aus.

### Test: `test_delete_workspace_non_admin_denied`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.

### Test: `test_delete_workspace_not_found`
- **Verknüpfte REQ-L2 ID:** UNBEKANNT (Keine REQ-ID verlinkt)
- **Aktuelles Verhalten:** Der Test führt scheinbar keine oberflächlichen Mocks aus. Er nutzt die echte Datenbank oder Services.
- **Anforderung (Akzeptanzkriterien):**
  Keine Akzeptanzkriterien für dieses Requirement gefunden.
- **Exakter Refactoring-Bedarf:**
  - Kein Refactoring für Shallow-Testing notwendig. Sicherstellen, dass DB-Assertions (`.objects.get()`) alle Felder korrekt prüfen.
