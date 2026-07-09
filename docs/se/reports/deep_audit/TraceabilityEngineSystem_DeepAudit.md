# TraceabilityEngineSystem - Deep Audit Report

**Datum:** 2026-07-09
**System:** TraceabilityEngineSystem
**Audit-Typ:** L2 Requirements vs. Test Implementation (Deep/Shallow Analysis)

Dieses Dokument analysiert jeden Test im Ordner `backend/traceability/tests/` im Abgleich mit den Akzeptanzkriterien aus `L2_TraceabilityEngineSystem_Requirements.md`.

---

## 1. test_trace_link_manager.py

*   **test_create_valid_link**
    *   **REQ-L2 ID:** REQ-L2-TE-001
    *   **Aktuelles Verhalten:** Erstellt Link und prüft UUID, Source und Target. (Nicht Shallow)
    *   **AC-Forderung:** Erstelle TraceLink -> TraceLink mit UUID.
    *   **Refactoring-Bedarf:** Keiner.

*   **test_create_all_8_link_types**
    *   **REQ-L2 ID:** REQ-L2-TE-001
    *   **Aktuelles Verhalten:** Prüft 8 Link-Typen (inkl. `documents`, `realizes`). (Shallow / Abweichung)
    *   **AC-Forderung:** Die Engine SHALL exakt 6 Typen unterstützen (`parent-child`, `derives-from`, `satisfies`, `verifies`, `implements`, `refines`).
    *   **Refactoring-Bedarf:** Die Liste der `valid_types` im Test auf die 6 spezifizierten Typen reduzieren. Andere Typen müssen in Fehler-Tests überführt werden.

*   **test_create_invalid_link_type**
    *   **REQ-L2 ID:** REQ-L2-TE-001
    *   **Aktuelles Verhalten:** Prüft Wurf von `InvalidLinkTypeError`. (Shallow)
    *   **AC-Forderung:** Fehler exakt als `"Invalid link type"` formuliert.
    *   **Refactoring-Bedarf:** Ergänzung von `.match("Invalid link type")` bei der Exception-Behandlung.

*   **test_create_missing_source**
    *   **REQ-L2 ID:** REQ-L2-TE-001
    *   **Aktuelles Verhalten:** Prüft `SourceNotFoundError`. (Shallow)
    *   **AC-Forderung:** Fehler exakt als `"Source entity not found"`.
    *   **Refactoring-Bedarf:** Ergänzung von `.match("Source entity not found")`.

*   **test_create_missing_target**
    *   **REQ-L2 ID:** REQ-L2-TE-001
    *   **Aktuelles Verhalten:** Prüft `TargetNotFoundError`. (Nicht Shallow)
    *   **AC-Forderung:** Logische Implikation von fehlendem Target.
    *   **Refactoring-Bedarf:** Keiner, analog Source Error Match ergänzen falls sinnvoll.

*   **test_read_link, test_update_link_type, test_delete_link**
    *   **REQ-L2 ID:** REQ-L2-TE-001
    *   **Aktuelles Verhalten:** Standard-CRUD-Validierung. (Nicht Shallow)
    *   **AC-Forderung:** Delete -> TraceLink entfernt.
    *   **Refactoring-Bedarf:** Keiner.

*   **test_cross_tenant_link_rejected**
    *   **REQ-L2 ID:** REQ-L2-TE-011
    *   **Aktuelles Verhalten:** Wirft `CrossTenantLinkError`. (Shallow)
    *   **AC-Forderung:** Fehler `"Cross-tenant link not allowed"`.
    *   **Refactoring-Bedarf:** Ergänzen der exakten String-Überprüfung `.match("Cross-tenant link not allowed")`.

*   **test_tenant_b_cannot_read_tenant_a_link, test_get_trace_links_scoped_to_tenant**
    *   **REQ-L2 ID:** REQ-L2-TE-011
    *   **Aktuelles Verhalten:** Strikte Isolation auf Tenant-Ebene. (Nicht Shallow)
    *   **AC-Forderung:** Tenant-Isolation für alle Leseoperationen.
    *   **Refactoring-Bedarf:** Keiner.

*   **test_direct_cycle_rejected**
    *   **REQ-L2 ID:** REQ-L2-TE-002
    *   **Aktuelles Verhalten:** A->B->A wirft `CycleDetectedError`. (Shallow)
    *   **AC-Forderung:** Fehler `"Cycle detected in parent-child chain"`.
    *   **Refactoring-Bedarf:** Exakten Exception-String per `.match("Cycle detected in parent-child chain")` absichern.

*   **test_indirect_cycle_rejected**
    *   **REQ-L2 ID:** REQ-L2-TE-002
    *   **Aktuelles Verhalten:** A->B->C->A (`derives-from`) wirft Fehler. (Shallow)
    *   **AC-Forderung:** Fehler `"Cycle detected in derives-from chain"`.
    *   **Refactoring-Bedarf:** Exakten Exception-String per `.match("Cycle detected in derives-from chain")` absichern.

*   **test_fan_out_no_cycle, test_previous_links_survive_rejected_cycle**
    *   **REQ-L2 ID:** REQ-L2-TE-002
    *   **Aktuelles Verhalten:** Fan-out erlaubt, bisherige Links bleiben nach Rollback. (Nicht Shallow)
    *   **AC-Forderung:** A->B, A->C OK. Nach abgelehntem Zyklus existieren vorherige Links unverändert.
    *   **Refactoring-Bedarf:** Keiner.

*   **test_batch_create_all_valid**
    *   **REQ-L2 ID:** REQ-L2-TE-003, REQ-L2-TE-012
    *   **Aktuelles Verhalten:** Batch-Erstellung mit 4 Items ohne Zeitmessung. (Shallow)
    *   **AC-Forderung:** Batch von 100 TraceLinks in < 500ms.
    *   **Refactoring-Bedarf:** Erhöhung des Batch-Umfangs auf genau 100 Elemente und Hinzufügen einer Performance-Messung (`time.perf_counter() < 0.5s`).

*   **test_batch_create_with_invalid_link_type_rolls_back**
    *   **REQ-L2 ID:** REQ-L2-TE-003
    *   **Aktuelles Verhalten:** Atomarer Rollback bei Teilfehler. (Nicht Shallow)
    *   **AC-Forderung:** Bei Teilfehler SHALL die gesamte Batch-Operation zurückgesetzt werden.
    *   **Refactoring-Bedarf:** Keiner.

*   **test_batch_create_cycle_triggers_full_rollback**
    *   **REQ-L2 ID:** REQ-L2-TE-003
    *   **Aktuelles Verhalten:** Rollback und Check auf Vorhandensein von `cycle_path`. (Shallow)
    *   **AC-Forderung:** Vollständiger Rollback mit Fehlerbericht, der den Zyklus-Pfad enthält (z.B. `"Cycle: Req-A -> Req-B -> Req-C -> Req-A"`).
    *   **Refactoring-Bedarf:** Validierung der String-Struktur des Attributs `exc_info.value.cycle_path` auf den exakten Knotenpfad (z.B. `"Cycle: ..."`).

*   **test_batch_delete_atomic, test_delete_source_artifact_cascades, test_delete_target_artifact_cascades**
    *   **REQ-L2 ID:** REQ-L2-TE-009, REQ-L2-TE-003
    *   **Aktuelles Verhalten:** Batch-Delete und Cascade-Funktionalität arbeiten wie gewünscht. (Nicht Shallow)
    *   **AC-Forderung:** Atomare Batch-Löschung, referenzielle Integrität (CASCADE).
    *   **Refactoring-Bedarf:** Keiner.

*   **test_created_by_captured, test_modified_by_updated_on_update**
    *   **REQ-L2 ID:** REQ-L2-TE-010
    *   **Aktuelles Verhalten:** Capture von User-IDs für Audit-Felder. (Nicht Shallow)
    *   **AC-Forderung:** `created_by` / `modified_by` korrekt gesetzt.
    *   **Refactoring-Bedarf:** Keiner.

---

## 2. test_query_engine.py

*   **test_query_downstream_returns_direct_targets, test_query_upstream_returns_direct_sources**
    *   **REQ-L2 ID:** REQ-L2-TE-004
    *   **Aktuelles Verhalten:** Funktionale Traversierung über kleine 3-Knoten-Graphen. (Shallow)
    *   **AC-Forderung:** Vollständiger Graph in ≤ 200ms (p95) bei 10.000 Items.
    *   **Refactoring-Bedarf:** Hinzufügen eines Skalierungstests, der ein Query-Szenario (ggf. gemockt oder bulk-eingefügt) mit großer Item-Zahl unter Performance-Aspekten (< 200ms) misst.

*   **test_result_includes_entity_type, test_query_via_facade_direction, test_no_links_returns_empty**
    *   **REQ-L2 ID:** REQ-L2-TE-004
    *   **Aktuelles Verhalten:** Validierung von Entity-Metadaten und Edge-Cases. (Nicht Shallow)
    *   **AC-Forderung:** Ergebnis enthält u.a. Entity-Typ. Leere Links ok.
    *   **Refactoring-Bedarf:** Keiner.

*   **test_transitive_downstream_two_levels, test_transitive_upstream, test_transitive_via_query_facade**
    *   **REQ-L2 ID:** REQ-L2-TE-005
    *   **Aktuelles Verhalten:** Funktionale korrekte Transitiv-Traversierung mit `depth` Angabe. (Shallow bzgl. Performance)
    *   **AC-Forderung:** ≤ 200ms bei 10.000 Items.
    *   **Refactoring-Bedarf:** Integration eines großen Dummy-Graphen mit Zeitmessung (< 200ms).

*   **test_collect_all_links_in_workspace**
    *   **REQ-L2 ID:** REQ-L2-TE-008
    *   **Aktuelles Verhalten:** Testet Sammlung mit exakt 5 Links. (Shallow)
    *   **AC-Forderung:** "Workspace mit 50 TraceLinks → Graph mit exakt 50 Links".
    *   **Refactoring-Bedarf:** Iteration im Setup anpassen, sodass exakt 50 Links erzeugt und verifiziert werden, um AC 1:1 zu decken.

*   **test_collect_empty_workspace, test_graph_is_serializable**
    *   **REQ-L2 ID:** REQ-L2-TE-008
    *   **Aktuelles Verhalten:** JSON-Serialisierung und leere Rückgabe sichergestellt. (Nicht Shallow)
    *   **AC-Forderung:** Graph maschinenlesbar, leerer Workspace liefert leeren Graphen.
    *   **Refactoring-Bedarf:** Keiner.

*   **test_payload_too_large_raises**
    *   **REQ-L2 ID:** REQ-L2-TE-008
    *   **Aktuelles Verhalten:** Wirft `PayloadTooLargeError` beim Mock-Limit-Überschreiten. (Shallow)
    *   **AC-Forderung:** Fehler-String `"Payload too large"`.
    *   **Refactoring-Bedarf:** Hinzufügen von `.match("Payload too large")`.

*   **FEHLENDER TEST: Query Timeout**
    *   **REQ-L2 ID:** REQ-L2-TE-004, REQ-L2-TE-005, REQ-L2-TE-012
    *   **Aktuelles Verhalten:** Kein Test für Abfrage-Timeouts existiert. (Missing)
    *   **AC-Forderung:** "Query-Timeout nach 5 Sekunden → Abbruch mit Fehler 'Query timeout'".
    *   **Refactoring-Bedarf:** Implementierung eines Timeout-Mocks in `test_query_engine.py` der überprüft ob die `QueryTimeoutError` mit Message `"Query timeout"` geworfen wird.

---

## 3. test_coverage_calculator.py

*   **test_coverage_7_of_10**
    *   **REQ-L2 ID:** REQ-L2-TE-006
    *   **Aktuelles Verhalten:** Berechnet 70% Abdeckung für 10 Requirements. (Shallow bzgl. Performance)
    *   **AC-Forderung:** Coverage für 10.000 Requirements in ≤ 500ms.
    *   **Refactoring-Bedarf:** Neuer oder erweiterter Test, der eine Menge von 10.000 Requirements simuliert und misst, dass die Coverage in < 500ms erfolgt.

*   **test_coverage_empty_workspace, test_coverage_zero_percent, test_coverage_100_percent, test_percentage_one_decimal_place, test_to_dict_serializable**
    *   **REQ-L2 ID:** REQ-L2-TE-006
    *   **Aktuelles Verhalten:** Funktionale Verifikation von Coverage-Prozentsätzen und JSON-Serialisierung. (Nicht Shallow)
    *   **AC-Forderung:** Prozentwerte, Dictionary Formate.
    *   **Refactoring-Bedarf:** Keiner.

*   **test_invalid_artifact_type_raises**
    *   **REQ-L2 ID:** REQ-L2-TE-007
    *   **Aktuelles Verhalten:** Wirft `InvalidFilterError`. (Nicht Shallow)
    *   **AC-Forderung:** Gefilterter Report nach Artefakttyp.
    *   **Refactoring-Bedarf:** Keiner.

*   **test_custom_link_type_filter**
    *   **REQ-L2 ID:** REQ-L2-TE-007
    *   **Aktuelles Verhalten:** Filtert nur nach Argument `link_type="satisfies"`. (Shallow)
    *   **AC-Forderung:** Kombination aus beiden Filtern verlangt: `coverage(workspace_id, artifact_type='ArchitectureElement', link_type='satisfies')`.
    *   **Refactoring-Bedarf:** Das Test-Setup so modifizieren, dass Architektur-Elemente angebunden sind, und beim Callable-Aufruf beide Parameter (`artifact_type` und `link_type`) mitschicken und validieren.

*   **test_tenant_isolation_in_coverage**
    *   **REQ-L2 ID:** REQ-L2-TE-011
    *   **Aktuelles Verhalten:** Testet Mandantenisolation für den Coverage-Report. (Nicht Shallow)
    *   **AC-Forderung:** Report enthält nur Tenant-eigene Links.
    *   **Refactoring-Bedarf:** Keiner.

*   **test_returns_entries_for_all_requirements, test_requirement_with_verifies_link_has_test_case, test_empty_workspace_returns_empty_entries**
    *   **REQ-L2 ID:** (IF-TE-INT-004 intern)
    *   **Aktuelles Verhalten:** Liefert Rohdaten für VCRM. (Nicht Shallow)
    *   **AC-Forderung:** Datengrundlage.
    *   **Refactoring-Bedarf:** Keiner.

---

## 4. test_services_facade.py

*   **test_create_and_get_via_facade, test_update_via_facade, test_delete_via_facade, test_batch_create_via_facade, test_invalid_link_type_via_facade**
    *   **REQ-L2 ID:** IF-TE-EXT-IN-003
    *   **Aktuelles Verhalten:** Leitet CRUD Anfragen an den Link Manager durch. (Nicht Shallow für Facade)
    *   **AC-Forderung:** Facade-Integration.
    *   **Refactoring-Bedarf:** Keiner.

*   **test_query_downstream_via_facade, test_query_upstream_via_facade**
    *   **REQ-L2 ID:** IF-TE-EXT-IN-001
    *   **Aktuelles Verhalten:** Delegiert Graph-Queries. (Nicht Shallow)
    *   **AC-Forderung:** Facade-Integration.
    *   **Refactoring-Bedarf:** Keiner.

*   **test_coverage_via_facade**
    *   **REQ-L2 ID:** IF-TE-EXT-IN-002
    *   **Aktuelles Verhalten:** Delegiert Coverage Reports. (Nicht Shallow)
    *   **AC-Forderung:** Facade-Integration.
    *   **Refactoring-Bedarf:** Keiner.

*   **test_collect_trace_graph_via_facade, test_graph_integrity_via_facade**
    *   **REQ-L2 ID:** IF-TE-EXT-IN-004
    *   **Aktuelles Verhalten:** Delegiert Baseline-Graph Collections. (Nicht Shallow)
    *   **AC-Forderung:** Facade-Integration.
    *   **Refactoring-Bedarf:** Keiner.

*   **test_export_csv_via_facade, test_export_pdf_returns_bytes_via_facade**
    *   **REQ-L2 ID:** REQ-L2-TE-013, REQ-L2-AS-016
    *   **Aktuelles Verhalten:** Delegiert VCRM Generator. (Nicht Shallow)
    *   **AC-Forderung:** Facade-Integration.
    *   **Refactoring-Bedarf:** Keiner.

---

## 5. test_vcrm_report_generator.py

*   **test_empty_workspace_returns_empty_matrix**
    *   **REQ-L2 ID:** REQ-L2-TE-013
    *   **Aktuelles Verhalten:** Leerer Workspace gibt leere Matrix. (Nicht Shallow)
    *   **AC-Forderung:** Leerer Workspace -> leere Matrix ohne Fehler.
    *   **Refactoring-Bedarf:** Keiner.

*   **test_requirement_without_test_case_gets_not_run**
    *   **REQ-L2 ID:** REQ-L2-TE-013
    *   **Aktuelles Verhalten:** Zeile ohne Link liefert "Not Run". (Nicht Shallow)
    *   **AC-Forderung:** Zeile ohne TestCase-Verknüpfung -> "Not Run".
    *   **Refactoring-Bedarf:** Keiner.

*   **test_requirement_with_test_case_link_appears, test_to_dict_returns_serializable_structure**
    *   **REQ-L2 ID:** REQ-L2-TE-013
    *   **Aktuelles Verhalten:** Testcase-Verlinkung landet in der Matrix. (Nicht Shallow)
    *   **AC-Forderung:** Matrix mit korrekten Zeilen, flache Ausgabe.
    *   **Refactoring-Bedarf:** Keiner.

*   **test_csv_has_header_row, test_csv_has_data_row_per_requirement, test_csv_is_valid_parseable_csv, test_csv_empty_workspace_is_header_only**
    *   **REQ-L2 ID:** REQ-L2-TE-013
    *   **Aktuelles Verhalten:** Valides CSV mit Headern und Body wird generiert. `test_csv_has_data_row_per_requirement` prüft IDs. (Shallow für Daten)
    *   **AC-Forderung:** Flache Matrix mit explizitem Wert `test_result` auch im CSV-Export.
    *   **Refactoring-Bedarf:** In `test_csv_has_data_row_per_requirement` den exakten Inhalt einer ganzen Zeile überprüfen (z.B. ob die Spalte `test_result` im CSV explizit "Not Run" abbildet).

*   **test_pdf_export_returns_valid_pdf, test_pdf_requirement_document_contains_workspace_title, test_pdf_traceability_matrix_contains_all_requirements, test_pdf_invalid_layout_raises, test_pdf_tenant_isolation**
    *   **REQ-L2 ID:** REQ-L2-AS-016
    *   **Aktuelles Verhalten:** Testet Pypdf-Parsing von PDFs aus Reportlab. (Nicht Shallow)
    *   **AC-Forderung:** PDF Export.
    *   **Refactoring-Bedarf:** Keiner.

*   **FEHLENDER TEST: VCRM Baseline Filter**
    *   **REQ-L2 ID:** REQ-L2-TE-013
    *   **Aktuelles Verhalten:** `baseline_id` wird im Generator in keinem Test angesprochen. (Missing)
    *   **AC-Forderung:** `baseline_id` angegeben -> Matrix spiegelt Zustand zum Snapshot-Zeitpunkt wider.
    *   **Refactoring-Bedarf:** Neuen Testfall `test_vcrm_baseline_filtering` schreiben. Einen Baseline-Status mocken, das Generator-Flag `baseline_id` mitgeben und überprüfen, dass der Snapshot-Zustand (und nicht der Live-Zustand) extrahiert wird.

---
## 6. Zusammenfassung der komplett ungetesteten Anforderungen

Die folgenden ACs sind vollständig ungetestet, da das Feature im Backlog liegt oder nicht implementiert wurde (Missing Coverage):
- **REQ-L2-TE-014 / 015:** Cross-Projekt-TraceLinks & Queries.
- **REQ-L2-TE-016:** Suspect-Link-Propagation Engine (Event-Listener).
- **REQ-L2-TE-017:** `cross-level` Link-Typ mit Begründungspflicht.
- **REQ-L2-TE-018:** Link-Typ `allocated-to` + Allocation Coverage Reporter.
