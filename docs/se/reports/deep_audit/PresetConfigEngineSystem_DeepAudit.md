# PresetConfigEngineSystem Test Coverage Deep Audit

Dieser Audit-Bericht vergleicht die Anforderungen (`REQ-L2-PC-*`) des `PresetConfigEngineSystem` mit der aktuellen Testimplementierung in `backend/presets/tests/`. 
Dabei wird insbesondere auf *Shallow Testing* geprüft, also Tests, die zwar die Methode aufrufen, aber nicht alle im Akzeptanzkriterium geforderten Bedingungen (z.B. Performance, Daten-Immutabilität, vollständige Strukturen) prüfen.

---

## 1. `test_feature_gate_service.py`

### Test: `test_baselines_minimal_false` bis `test_custom_workflows_minimal_false` (7 Tests)
- **REQ-L2 ID:** REQ-L2-PC-002
- **Aktuelles Verhalten (Shallow?):** Ja. Die Tests rufen lediglich `gate.is_feature_enabled` auf und prüfen auf `True` oder `False`.
- **Akzeptanzkriterium:** "Antwortzeit < 10ms pro Query."
- **Refactoring-Bedarf:** Für jeden dieser Tests muss eine Zeitmessung (z.B. über `time.perf_counter()` oder ein Benchmark-Framework) eingebaut werden. Das Ergebnis muss asserten, dass die Antwortzeit (ggf. aus dem Cache) `< 10ms` beträgt.

### Test: `test_get_preset_minimal`
- **REQ-L2 ID:** REQ-L2-PC-003, REQ-L2-PC-004
- **Aktuelles Verhalten (Shallow?):** Ja. Prüft nur partiell, ob `preset == minimal`, `workflow_configurability == fixed`, `change_reason == optional` und `baseline_scopes == []`.
- **Akzeptanzkriterium:** Die vollständige Preset-Konfiguration inklusive *aller* Pflichtfeld-Regeln (`mandatory_fields`) muss korrekt zurückgegeben werden. 
- **Refactoring-Bedarf:** Der Test muss asserten, dass `mandatory_fields` explizit *nur* `title` enthält. Das Dictionary aus `as_dict()` muss vollständig gegen ein Expected-JSON/Dict validiert werden, anstatt nur einzelne Keys zu picken.

### Test: `test_get_preset_standard`
- **REQ-L2 ID:** REQ-L2-PC-003
- **Aktuelles Verhalten (Shallow?):** Ja. Prüft *nur* `tier` und `baseline_scopes`. 
- **Akzeptanzkriterium:** `get_preset(workspace_standard) -> {preset: "standard", mandatory_fields: {...}, features: {...}, baseline_scopes: ["document", "project"], workflow_configurability: "partial", change_reason: "optional"}`
- **Refactoring-Bedarf:** Der Test muss einen Full-Match (Deep Equal) des zurückgegebenen Dictionaries gegen das im AC definierte Ziel-Dictionary durchführen. Momentan werden die meisten Felder ignoriert.

### Test: `test_get_preset_extended`
- **REQ-L2 ID:** REQ-L2-PC-003
- **Aktuelles Verhalten (Shallow?):** Ja. Prüft nur `tier` und ob `"global"` in den Scopes ist.
- **Akzeptanzkriterium:** Es muss die vollständige Konfiguration für Extended zurückgegeben werden.
- **Refactoring-Bedarf:** Deep-Equal Check des gesamten as_dict()-Outputs. Es muss sichergestellt werden, dass `workflow_configurability: "full"` und `change_reason: "mandatory"` gesetzt sind sowie `mandatory_fields` die erweiterten Anforderungen erfüllt.

### Test: `test_minimal_no_scopes` bis `test_extended_global_allowed` (4 Tests)
- **REQ-L2 ID:** REQ-L2-PC-005
- **Aktuelles Verhalten (Shallow?):** Nein. Die Tests prüfen präzise die Booleans für die verschiedenen Scopes ab.
- **Akzeptanzkriterium:** Erlaubte Scopes nach Tier.
- **Refactoring-Bedarf:** Kein zwingender Refactoring-Bedarf. Abdeckung ist hier ausreichend.

### Test: `test_minimal_fixed`, `test_standard_partial`, `test_extended_full`
- **REQ-L2 ID:** REQ-L2-PC-006
- **Aktuelles Verhalten (Shallow?):** Partiell Shallow. Prüft die Strings `"fixed"`, `"partial"`, `"full"`. 
- **Akzeptanzkriterium:** "Custom Workflow im Minimal-Preset → abgelehnt"
- **Refactoring-Bedarf:** Ein neuer Test muss hinzugefügt (oder der Minimal-Test erweitert) werden, der konkret versucht, im Minimal-Preset einen Custom-Workflow anzulegen/zu persistieren und verifiziert, dass dieser mit einer Exception abgelehnt wird.

### Test: `test_upgrade_minimal_to_standard`
- **REQ-L2 ID:** REQ-L2-PC-008
- **Aktuelles Verhalten (Shallow?):** Ja, sehr shallow. Führt den Wechsel durch und prüft, ob die DB-Spalte aktualisiert wurde.
- **Akzeptanzkriterium:** "Minimal mit 50 Requirements → Wechsel zu Standard → alle Requirements unverändert, neue Features verfügbar. Kein DB-Migrationsscript. Wechsel bei 10.000 Artefakten < 1 Sekunde"
- **Refactoring-Bedarf:** Der Test muss in der Setup-Phase 50 Requirements (via DB-Models/Factories) anlegen. Nach dem `switch_preset` muss verifiziert werden, dass alle 50 Requirements (Inhalt/IDs) unverändert existieren. Ferner muss die Ausführungszeit des Switches gemessen werden (< 1 Sekunde). *Ein separater Performance-Test für die 10.000 Artefakte sollte existieren.*

### Test: `test_upgrade_standard_to_extended`
- **REQ-L2 ID:** REQ-L2-PC-008
- **Aktuelles Verhalten (Shallow?):** Ja. Wie zuvor, prüft nur den DB-Status.
- **Akzeptanzkriterium:** "Standard mit 100 Requirements + 2 Baselines → Wechsel zu Extended → alles unverändert"
- **Refactoring-Bedarf:** Setup mit 100 Requirements und 2 verknüpften Baselines. Switch durchführen. Asserten, dass diese Relationen und Daten exakt gleich geblieben sind.

### Test: `test_feature_available_after_upgrade`
- **REQ-L2 ID:** REQ-L2-PC-008
- **Aktuelles Verhalten (Shallow?):** Nein, ausreichender funktionaler Test für die Cache-Invalidation.
- **Refactoring-Bedarf:** Ggf. Performance-Messung anbauen.

### Test: `test_clean_downgrade_standard_to_minimal_allowed` bis `test_switch_downgrade_clean_succeeds`
- **REQ-L2 ID:** REQ-L2-PC-011
- **Aktuelles Verhalten (Shallow?):** Ja, hochgradig shallow. Die Tests arbeiten nur mit leeren Workspaces und prüfen das Policy-Verhalten.
- **Akzeptanzkriterium:** "Extended mit Global-Baseline → Downgrade zu Standard → Fehler 'Downgrade blocked: 1 global baseline exists'. Nach Löschen der Baseline → Downgrade erfolgreich"
- **Refactoring-Bedarf:** Es fehlt ein echter Integrationstest. Es muss ein Workspace auf "Extended" gesetzt werden, eine *Global-Baseline* angelegt werden, und DANN der Downgrade versucht werden. Dieser muss fehlschlagen. Danach die Baseline löschen und erneut versuchen -> Success.

### Test: `test_get_terminology_dev_mode` & `test_get_terminology_se_mode`
- **REQ-L2 ID:** REQ-L2-PC-009
- **Aktuelles Verhalten (Shallow?):** Ja. Prüft nur das Label für `artifact_l1`.
- **Akzeptanzkriterium:** Das vollständige Mapping `{artifact_l1: "Epic", artifact_l2: "Story", requirement: "Acceptance Criterion"}` muss zurückgegeben werden.
- **Refactoring-Bedarf:** Assert gegen das komplette Dictionary erweitern, um partielle Konfigurationen auszuschließen.

### Test: `test_switch_terminology_profile`
- **REQ-L2 ID:** REQ-L2-PC-010
- **Aktuelles Verhalten (Shallow?):** Partiell Shallow. Misst bereits die Zeit (`< 1.0s`), prüft das DB-Feld.
- **Akzeptanzkriterium:** "Alle Requirements inhaltlich unverändert"
- **Refactoring-Bedarf:** Im Setup müssen Requirements angelegt werden. Nach dem Switch muss ein Assert sicherstellen, dass die Requirements in der DB weder gelöscht noch korrumpiert wurden.

### Test: `test_cache_invalidated_after_switch_preset`
- **REQ-L2 ID:** REQ-L2-PC-013
- **Aktuelles Verhalten (Shallow?):** Ja, bezüglich der Performance. Es prüft logisch die Cache-Invalidierung korrekt, aber ignoriert die Latenzanforderung.
- **Akzeptanzkriterium:** "50 gleichzeitige Workspaces, 100 Preset-Queries → p95 < 10ms"
- **Refactoring-Bedarf:** Es muss ein expliziter Load/Performance-Test geschrieben werden, der über 50 Workspaces iteriert/parallelisiert und verifiziert, dass die 95. Perzentile der Queries unter 10ms liegt.


---

## 2. `test_preset_registry.py`

### Test: `test_minimal_config_has_all_fields` bis `test_extended_change_reason_mandatory`
- **REQ-L2 ID:** REQ-L2-PC-004, REQ-L2-PC-007
- **Aktuelles Verhalten (Shallow?):** Nein, die Registry-Tests verifizieren die statische Struktur ausreichend gut auf Unit-Ebene. 
- **Akzeptanzkriterium:** Pflichtfelder und Change-Reason policies sind definiert.
- **Refactoring-Bedarf:** Keine zwingende Änderung, da Integration-Verhalten andernorts getestet wird.

### Test: `test_as_dict_returns_all_keys`
- **REQ-L2 ID:** REQ-L2-PC-003
- **Aktuelles Verhalten (Shallow?):** Ja. Es wird nur auf das Vorhandensein der Keys (`"preset" in d`) geprüft.
- **Akzeptanzkriterium:** Exakter Payload muss stimmig sein.
- **Refactoring-Bedarf:** Anstatt `assert "preset" in d`, sollte das Dictionary deep-compared werden. 

### Test: `test_modify_default_raises` & `test_delete_default_raises`
- **REQ-L2 ID:** REQ-L2-PC-012
- **Aktuelles Verhalten (Shallow?):** Nein, perfekte Abdeckung der Immutabilität.
- **Refactoring-Bedarf:** Keiner.

### Test: `test_create_custom_in_extended_accepted` bis `test_create_custom_in_standard_rejected`
- **REQ-L2 ID:** REQ-L2-PC-014
- **Aktuelles Verhalten (Shallow?):** Partiell Shallow. Die Anlage/Reject-Logik wird getestet.
- **Akzeptanzkriterium:** "Delete Custom Preset → Fallback auf Default"
- **Refactoring-Bedarf:** Es existiert **kein Test** für das Löschen eines Custom Presets. Ein neuer Test `test_delete_custom_preset_falls_back_to_default` muss implementiert werden.


---

## 3. `test_services_facade.py`

### Alle Tests in dieser Datei
- **REQ-L2 ID:** REQ-L2-PC-001, REQ-L2-PC-002, REQ-L2-PC-003, REQ-L2-PC-009
- **Aktuelles Verhalten (Shallow?):** Ja, durch die Natur als Facade-Tests delegieren sie nur und prüfen minimale Ausgaben.
- **Akzeptanzkriterium:** Korrektes Routing und Typisierung (REST/MCP Interface Konsistenz).
- **Refactoring-Bedarf:** Diese Tests dienen als API-Vertrag (Contract-Tests). Um Shallow-Testing zu vermeiden, sollten die `as_dict()` Rückgaben der Facade auf 100%ige Schema-Konformität geprüft werden, da sie die "Schicht" zur REST-API bilden.

---

## 4. `test_terminology_service.py`

### Test: `test_dev_mode_labels` & `test_se_mode_labels`
- **REQ-L2 ID:** REQ-L2-PC-009
- **Aktuelles Verhalten (Shallow?):** Nein. Prüft mehrere spezifische Keys exakt ab. 
- **Refactoring-Bedarf:** Kann optional um einen Deep-Equal-Vergleich des gesamten Default-Dictionaries erweitert werden, um sicherzustellen, dass keine unerwarteten Extra-Keys existieren. Ansonsten guter Test.

### Test: `test_switching_between_profiles_returns_correct_labels`
- **REQ-L2 ID:** REQ-L2-PC-010
- **Aktuelles Verhalten (Shallow?):** Ja. Testet nur das Dictionary-Switching in memory.
- **Akzeptanzkriterium:** Die Datenmigration muss in < 1s laufen und ohne Datenverlust passieren.
- **Refactoring-Bedarf:** Dieser Unit-Test kann so bleiben, aber der Integration-Test in `test_feature_gate_service.py` muss (wie oben erwähnt) zwingend die Persistenz (Requirements bleiben erhalten) absichern.
