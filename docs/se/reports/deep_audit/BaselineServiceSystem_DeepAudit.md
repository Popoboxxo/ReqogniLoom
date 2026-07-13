# Deep Audit Report: BaselineServiceSystem (ARCH-L1-006)

## 1. Executive Summary
Dieser Bericht enthält einen detaillierten Test-Coverage-Audit für das `BaselineServiceSystem`. Es wurde geprüft, inwiefern die Tests in `backend/baseline/tests/` die Anforderungen aus `L2_BaselineServiceSystem_Requirements.md` valide abdecken.

**Fazit:** Ein Großteil der Tests leidet stark unter **Shallow Testing** (falsche Positives, übermäßiger Einsatz von Mocks, reine Python-Objekt-Prüfungen statt Datenbank/System-Grenzen-Prüfungen). Die L2-Anforderungen sind zwar formal „gecovered", aber die tatsächliche Geschäftslogik und Datenintegrität sind unzureichend verifiziert.

## 2. Analyse der Requirements (Akzeptanzkriterien)

Das Anforderungsdokument (`L2_BaselineServiceSystem_Requirements.md`) definiert harte funktionale Kriterien:
- **REQ-L2-BL-001**: Delta Storage, Scope Resolution (10 Requirements + 3 ArchElements = 13 Einträge), keine Payload in der Baseline.
- **REQ-L2-BL-002**: Immutability (Unveränderlichkeit der DB-Einträge nach Erstellung).
- **REQ-L2-BL-003**: Diff-Kalkulation (added/removed/changed).
- **REQ-L2-BL-004**: Gatekeeping durch Presets (Minimal/Standard/Extended).
- **REQ-L2-BL-007**: Atomic Creation & Rollback bei Fehlern.
- **REQ-L2-BL-009**: Rekonstruktion alter Item-Stände via AuditLog.

## 3. Deep-Dive: `test_baseline.py`

### 3.1. `TestBaselineStoreImmutability`
- **Verknüpfte REQ-L2 ID**: REQ-L2-BL-002
- **Test-Name**: `test_update_raises_immutable_error`, `test_delete_raises_immutable_error`
- **Aktueller Stand (Shallow)**: Die Tests rufen lediglich `store.update()` und `store.delete()` auf der reinen Python-Service-Klasse auf, die direkt einen Fehler werfen. Die eigentliche DB-Sicherheit wird umgangen.
- **Forderung (Acceptance Criteria)**: "Ein persistierter Baseline-Snapshot DARF NICHT modifiziert, gelöscht oder überschrieben werden."
- **Exakter Refactoring-Bedarf**: Die Tests müssen eine Baseline mittels echtem ORM-Befehl speichern und anschließend versuchen, via `BaselineSnapshot.objects.get(id=...).delete()` oder `.update()` bzw. `.save()` Änderungen in der Datenbank vorzunehmen. Das Django-Model (bzw. Signale oder die `save`-Methode) muss die Immutability erzwingen, nicht nur die Service-Hülle.

### 3.2. `TestBaselineStorePersistence`
- **Verknüpfte REQ-L2 ID**: REQ-L2-BL-001
- **Test-Name**: `test_persist_and_get_returns_entries`
- **Aktueller Stand (Shallow)**: Es wird `_make_delta_tuples(3)` genutzt, um Dummy-Tupel zu erzeugen und abzuspeichern. Die eigentliche Scope-Resolution wird gar nicht getestet.
- **Forderung (Acceptance Criteria)**: "Baseline scope=project mit 10 Requirements, 3 ArchElements → Baseline enthält 13 (item_id, version)-Einträge"
- **Exakter Refactoring-Bedarf**: Die Mock-Tupel müssen entfernt werden. Der Test muss via Model-Factory genau 10 Requirements und 3 ArchElements in der Test-Datenbank generieren. Anschließend muss der `DeltaIndexBuilder` (bzw. Service) für `scope="project"` aufgerufen werden. Zuletzt wird assertiert, dass exakt 13 DB-Einträge entstanden sind.

- **Verknüpfte REQ-L2 ID**: REQ-L2-BL-001
- **Test-Name**: `test_persist_no_payload_in_entries`
- **Aktueller Stand (Shallow)**: Es wird auf dem zurückgegebenen Python-Objekt geprüft: `hasattr(entry, "title")`.
- **Forderung (Acceptance Criteria)**: Payload darf nicht in der Baseline persistiert werden (verhindert OOM).
- **Exakter Refactoring-Bedarf**: Der Test muss die Daten direkt via SQL oder ORM-Values aus dem Serialisierungsfeld der Datenbank holen (z. B. `BaselineSnapshot.objects.values('entries')`) und per `json.loads()` prüfen, ob der JSON-String `title` oder `description` Keys enthält.

- **Verknüpfte REQ-L2 ID**: REQ-L2-BL-007
- **Test-Name**: *Fehlt komplett!* (Obwohl im Docstring als "Atomic creation mocked rollback path" erwähnt)
- **Aktueller Stand (Shallow)**: Transaktionssicherheit wird nicht verifiziert.
- **Forderung (Acceptance Criteria)**: "DB-Fehler während Snapshot → Rollback: keine Baseline in DB / Baseline mit 1000 Items → entweder alle 1000 oder keine"
- **Exakter Refactoring-Bedarf**: Es muss ein neuer Test `test_atomic_creation_rollback` geschrieben werden. Dieser muss z. B. bei der Speicherung des 500. Items einen Fehler (`Exception`) induzieren. Danach muss per `BaselineSnapshot.objects.count()` geprüft werden, dass der Zähler 0 ist (kein Commit der Partial-Daten).

### 3.3. `TestDiffEngine`
- **Verknüpfte REQ-L2 ID**: REQ-L2-BL-003
- **Test-Name**: `test_diff_added`, `test_diff_removed`, `test_diff_changed`
- **Aktueller Stand (Shallow)**: Massiver Einsatz von `MagicMock` und `@patch`. Die Datenbank und der Store werden komplett gemockt. Es werden nur In-Memory Arrays verglichen.
- **Forderung (Acceptance Criteria)**: Diff(A, B) liefert korrekte Kategorisierung über gespeicherte Baselines.
- **Exakter Refactoring-Bedarf**: Sämtliche `@patch` und `MagicMock`-Referenzen müssen aus dieser Test-Klasse entfernt werden. Es müssen zwei echte Baselines (A und B) via ORM erzeugt werden. Danach muss die echte `DiffEngine` initialisiert werden, die Daten aus der SQLite/Postgres Test-DB liest und das Diff kalkuliert.

### 3.4. `TestVersionReconstructor`
- **Verknüpfte REQ-L2 ID**: REQ-L2-BL-009
- **Test-Name**: Alle Tests dieser Klasse
- **Aktueller Stand (Shallow)**: Interne Methoden wie `_try_live_entity` und `_load_from_audit_log` werden gepatcht. Das AuditLog wird nie wirklich gelesen.
- **Forderung (Acceptance Criteria)**: "Funktion liefert den vollständigen Item-Payload zur zum Baseline-Zeitpunkt gespeicherten Version zurück (über AuditLog)."
- **Exakter Refactoring-Bedarf**: Mocks komplett entfernen. Testablauf muss sein: (1) Anlegen eines echten Requirements (Version 1). (2) Erstellen der Baseline. (3) Updaten des Requirements auf Version 2 (was das echte `AuditLog` befüllt). (4) Aufruf von `get_item_at_baseline()`. (5) Assertion, dass Version 1 inklusive Payload sauber aus dem echten `AuditLog`-Model deserialisiert wurde.

### 3.5. `TestDeltaIndexBuilderPresetGate`
- **Verknüpfte REQ-L2 ID**: REQ-L2-BL-004
- **Test-Name**: Alle Gate-Tests
- **Aktueller Stand (Shallow)**: Das Check-Gate `_check_preset_gate` wird gepatcht (`side_effect=ScopeNotAllowedError(...)`). Die eigentliche Logik der `PresetConfigEngine` wird ignoriert.
- **Forderung (Acceptance Criteria)**: "Standard → `scope="project"` OK, `scope="global"` → Fehler"
- **Exakter Refactoring-Bedarf**: Mocks/Patches entfernen. Stattdessen müssen echte `WorkspacePresetConfig`-Einträge in der Test-DB angelegt werden (`active_tier="minimal"`, `standard`, `extended`). Der Service muss diese via DB-Query auswerten und entsprechend das Scoping erlauben oder blockieren.

---

## 4. Deep-Dive: `test_scope_preview.py`

### 4.1. `TestPreviewScopeItems`
- **Verknüpfte REQ-L2 ID**: REQ-L1-049
- **Test-Name**: `test_sample_items_have_id_title_type`
- **Aktueller Stand (Shallow)**: Ruft `preview_scope_items` für einen leeren Workspace auf. Ergebnis ist `count=0` und `sample=[]`. Anschließend läuft der Code `for item in result.sample: assert "id" in item`. Da die Liste leer ist, läuft der Loop 0-mal. Der Test ist ein **False Positive** ("Passes by doing nothing").
- **Forderung (Acceptance Criteria)**: Das DTO des Samples muss strukturiert sein (id, title, type).
- **Exakter Refactoring-Bedarf**: Dieser Test muss in die Klasse `TestPreviewScopeItemsWithData` verschoben werden, wo via `Artifact.unscoped.create` echte Testdaten erzeugt werden. So ist garantiert, dass das `sample`-Array gefüllt ist und die Schleife die Keys real anhand echter zurückgegebener Items überprüft.

## 5. Zusammenfassung & Next Steps

Die Tests im `BaselineServiceSystem` weisen zwar eine formale Code-Coverage auf, leiden aber stark unter Mock-Abuse. Um das Shallow-Testing zu beenden, MUSS die gesamte Test-Suite von Mock-basierten Unit-Tests zu echten Integrationstests gegen die Test-Datenbank umgebaut werden. Besonders die Schnittstellen (TraceabilityEngine, AuditLogEngine, und BaselineStorage) müssen nahtlos in der DB integrieren, anstatt durch `MagicMock` isoliert zu werden.
