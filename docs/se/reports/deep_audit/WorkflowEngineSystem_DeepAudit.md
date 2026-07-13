# WorkflowEngineSystem - Deep Test-Coverage Audit

## Überblick
Dieses Dokument enthält das Deep-Audit der Testabdeckung für das `WorkflowEngineSystem` (ARCH-L1-005) basierend auf den Anforderungen in `L2_WorkflowEngineSystem_Requirements.md`. Es analysiert Zeile für Zeile die aktuellen Testdateien auf "Shallow Testing" (oberflächliche Tests) und definiert den exakten Refactoring-Bedarf, um eine robuste, anforderungsgerechte Testabdeckung sicherzustellen.

---

## 1. Datei: `backend/workflow/tests/test_definition_store.py`

### Test: `TestPresetDefaultWorkflows.test_minimal_states`
- **Verknüpfte REQ-L2 ID**: REQ-L2-WE-002
- **Aktuelles Verhalten (Shallow)**: Der Test prüft lediglich, ob die States `{"draft", "done"}` im resultierenden DTO vorhanden sind.
- **Anforderung (Akzeptanzkriterium)**: "Minimal: States `[draft, done]`, alle Transitionen für `editor`."
- **Exakter Refactoring-Bedarf**: 
  - Assertions hinzufügen, die prüfen, ob exakt die Transition `draft -> done` im DTO existiert.
  - Prüfen, ob für diese Transition `allowed_roles` ausschließlich `["editor"]` beinhaltet.

### Test: `TestPresetDefaultWorkflows.test_extended_states`
- **Verknüpfte REQ-L2 ID**: REQ-L2-WE-002
- **Aktuelles Verhalten (Shallow)**: Prüft nur, ob die 4 erwarteten States (`draft`, `in_review`, `approved`, `deprecated`) im Set der DTO-States liegen.
- **Anforderung (Akzeptanzkriterium)**: "Extended: ... `in_review → approved` nur für `approver`, `change_reason` Pflicht."
- **Exakter Refactoring-Bedarf**: 
  - Die Transition `in_review -> approved` muss explizit validiert werden.
  - Assertion: `transition.allowed_roles == ["approver"]` (oder enthält approver und keine anderen unberechtigten).
  - Assertion: `transition.requires_change_reason is True`.

### Test: `TestPresetDefaultWorkflows.test_standard_has_approver_role`
- **Verknüpfte REQ-L2 ID**: REQ-L2-WE-002
- **Aktuelles Verhalten (Shallow)**: Checkt nur `approver in allowed_roles` für die `draft -> approved` Transition.
- **Anforderung (Akzeptanzkriterium)**: "Standard: States `[draft, approved, deprecated]`, rollenbasiert."
- **Exakter Refactoring-Bedarf**: 
  - Die Testabdeckung muss sicherstellen, dass nicht nur `approver` berechtigt ist, sondern auch, dass keine falschen Rollen zugewiesen sind. 
  - Es muss geprüft werden, ob alle definierten Standard-Transitionen exakt die erwarteten `allowed_roles` haben.

### Test: `TestCustomDefinitionValidation.test_valid_custom_in_extended`
- **Verknüpfte REQ-L2 ID**: REQ-L2-WE-002
- **Aktuelles Verhalten (Shallow)**: Übergibt einen Custom-Workflow, checkt danach ob die States im DTO sind und `is_custom == True` ist.
- **Anforderung (Akzeptanzkriterium)**: Custom Workflows werden komplett persistiert (inklusive Transitions).
- **Exakter Refactoring-Bedarf**: 
  - Nach dem Persistieren müssen die Transitionen des zurückgegebenen DTOs (und ggf. das resultierende JSON aus der DB) verifiziert werden.
  - Assertion: Prüfen, dass `requires_change_reason`, `allowed_roles` und `to_state`/`from_state` exakt den übergebenen Parametern entsprechen.

### Test: `TestOrphanedStateDetection.test_orphaned_state_blocks_update`
- **Verknüpfte REQ-L2 ID**: REQ-L2-WE-004
- **Aktuelles Verhalten (Shallow)**: Erstellt 5 Items, versucht Update, fängt Exception, prüft `count == 5` und `len(item_ids) == 5`.
- **Anforderung (Akzeptanzkriterium)**: "Item-IDs bis Limit 100 gelistet".
- **Exakter Refactoring-Bedarf**: 
  - Ein zweiter Testfall (oder eine Erweiterung) muss das **Limit von 100** testen.
  - Setup: 105 Items im `in_progress` State erstellen.
  - Assertion: `err.count == 105`, aber `len(err.item_ids) == 100` um zu beweisen, dass die Limitierung korrekt greift.

### Test: `TestPresetDowngradeBlockade.test_downgrade_blocked_by_in_review`
- **Verknüpfte REQ-L2 ID**: REQ-L2-WE-007
- **Aktuelles Verhalten (Shallow)**: Prüft nur, dass die `PresetDowngradeBlockedError` Exception geworfen wird.
- **Anforderung (Akzeptanzkriterium)**: Der Downgrade SHALL blockiert werden, wenn Items in States existieren, die nicht gültig sind.
- **Exakter Refactoring-Bedarf**: 
  - Die Exception muss genauer geprüft werden: Stehen in der Exception der betroffene State (z.B. `in_review`) und die Anzahl der blockierenden Items?
  - Assertion auf die Fehlermeldung der Exception, dass diese dem Entwickler hilfreiche Metadaten liefert.

---

## 2. Datei: `backend/workflow/tests/test_lifecycle_manager.py`

### Test: `TestStateInitialization.test_initializes_three_items`
- **Verknüpfte REQ-L2 ID**: REQ-L2-WE-005
- **Aktuelles Verhalten (Shallow)**: Der Test prüft nur, dass die zurückgegebene Liste 3 Items enthält, die auf "draft" stehen.
- **Anforderung (Akzeptanzkriterium)**: "Alle States MÜSSEN atomar persistiert werden."
- **Exakter Refactoring-Bedarf**: 
  - Die Atomarität (Transaktions-Rollback) wird nicht verifiziert.
  - Erstelle einen neuen Test `test_initializes_items_atomic_rollback`: Mocke das Speichern des 3. Items so, dass eine Exception fliegt (`IntegrityError` o.Ä.).
  - Assertion: Prüfe in der Datenbank, dass *keines* der ersten 2 Items gespeichert wurde, weil die Transaktion komplett zurückgerollt sein muss.

### Test: `TestStateMutation.test_transition_updates_state`
- **Verknüpfte REQ-L2 ID**: REQ-L2-WE-003
- **Aktuelles Verhalten (Shallow)**: Der Test checkt `from_state`, `to_state` und `change_reason` im History-Eintrag.
- **Anforderung (Akzeptanzkriterium)**: "`transitioned_by`, `transitioned_at` (UTC, ms-Präzision) ... Transition und History-Eintrag MÜSSEN atomar persistiert werden."
- **Exakter Refactoring-Bedarf**: 
  1. **Audit-Felder**: Assertions für `entry.transitioned_by` hinzufügen. 
  2. **Timestamp-Prüfung**: Assertions für `entry.transitioned_at` hinzufügen (Ist die Zeitzone UTC? Ist es datetime-aware?).
  3. **Atomarität prüfen**: Ähnlich wie oben muss ein neuer Test beweisen, dass wenn `WorkflowHistoryEntry.save()` fehlschlägt, der `WorkflowItemState` **nicht** im neuen State bleibt (Rollback auf `previous_state`).

### Test: `TestStateMutation.test_history_append_only_raises_on_update`
- **Verknüpfte REQ-L2 ID**: REQ-L2-WE-003
- **Aktuelles Verhalten (Shallow)**: Der Test prüft, ob ein Aufruf von `.save()` nach einem Update einen ValueError wirft ("History is append-only").
- **Anforderung (Akzeptanzkriterium)**: "History-Einträge DÜRFEN NICHT modifiziert **oder gelöscht** werden."
- **Exakter Refactoring-Bedarf**: 
  - Der Test prüft Modifikation, aber nicht Löschung.
  - Ein neuer Test `test_history_append_only_raises_on_delete` muss hinzugefügt werden, der aufruft: `entry.delete()`.
  - Assertion: `delete()` muss ebenfalls eine Exception werfen oder abgelehnt werden, um das Audit-Trail abzusichern.

---

## 3. Datei: `backend/workflow/tests/test_signature_gate.py`

### Test: `TestHmacSeal.test_seal_is_64_hex_chars` & `test_seal_is_deterministic`
- **Verknüpfte REQ-L2 ID**: REQ-L2-WE-009
- **Aktuelles Verhalten (Shallow)**: Prüft nur, dass die Ausgabe ein 64-stelliger Hex-String ist und deterministisch (2x gleicher Input = gleicher Output).
- **Anforderung (Akzeptanzkriterium)**: "`signature_seal` als HMAC-SHA256 aus `transition_id + timestamp + user_id` berechnet".
- **Exakter Refactoring-Bedarf**: 
  - Die kryptografische Implementierung wird nicht validiert (könnte auch einfaches Hashing statt HMAC sein, oder die falsche Reihenfolge der Felder).
  - Im Test muss der HMAC exakt nachgebildet werden:
    ```python
    import hmac
    import hashlib
    expected_msg = f"{transition_id}{timestamp}{user_id}".encode('utf-8')
    expected_seal = hmac.new(b"test-secret-key", expected_msg, hashlib.sha256).hexdigest()
    assert seal == expected_seal
    ```
  - Nur so wird bewiesen, dass der Standard HMAC-SHA256 korrekt und in der vom Requirement geforderten Konkatenation angewendet wurde.

---

## 4. Datei: `backend/workflow/tests/test_transition_validator.py`

### Test: `TestTransitionValidatorRules.test_change_reason_required`
- **Verknüpfte REQ-L2 ID**: REQ-L2-WE-001
- **Aktuelles Verhalten (Shallow)**: Der Test prüft, ob `change_reason=""` (leerer String) mit `CHANGE_REASON_REQUIRED` abgelehnt wird.
- **Anforderung (Akzeptanzkriterium)**: "MUSS ein nicht-leerer `change_reason` vorhanden sein."
- **Exakter Refactoring-Bedarf**: 
  - Es muss ausgeschlossen werden, dass Entwickler "leere" Strings übergeben, die nur aus Leerzeichen bestehen.
  - Erweitere den Test um einen Fall, bei dem `change_reason="   "` (oder `\n`) übergeben wird.
  - Assertion: Auch reine Whitespaces müssen als "leer" gewertet und abgelehnt werden.

### Test: `TestTransitionValidatorRules.test_valid_transition` (und andere Validator-Tests)
- **Verknüpfte REQ-L2 ID**: REQ-L2-WE-001
- **Aktuelles Verhalten (Shallow)**: Testet einen sehr einfachen "Happy Path". Die vier Regeln werden alle isoliert voneinander in separaten Tests getestet.
- **Anforderung (Akzeptanzkriterium)**: "Validierung SHALL vier Regeln durchsetzen".
- **Exakter Refactoring-Bedarf**: 
  - Füge einen holistischen "Happy Path" Test hinzu (`test_valid_transition_with_all_rules_combined`).
  - Dieser muss eine Transition validieren, die eine spezielle Rolle erfordert UND einen `change_reason` erfordert UND ein `signature_gate` hat. 
  - Assertion: Nur wenn alle diese Felder im Request korrekt befüllt sind, darf das Ergebnis `valid=True` sein und das Seal generiert werden. Das beweist, dass die Validierungsregeln kombinierbar sind und keine Kurzschluss-Logik (Early-Return) eine der anderen Regeln fehlerhaft überspringt.
