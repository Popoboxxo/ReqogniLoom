# Deep Audit Report: PersistenceLayerSystem Test Coverage

**Datum:** 2026-07-09
**System:** PersistenceLayerSystem (ARCH-L1-010)
**Scope:** `backend/persistence/tests/`
**Referenz:** `docs/se/L1/Gesamtsystem/L2/PersistenceLayerSystem/L2_PersistenceLayerSystem_Requirements.md`

Dieser Bericht deckt signifikante Shallow-Testing-Probleme (Test-Illusionen, unvollständige Akzeptanzkriterien-Verifikation) in der Persistence-Schicht auf. Viele Tests verifizieren nur die "Happy Paths" auf einer oberflächlichen Ebene oder umgehen die eigentliche Logik durch Mocks und künstliche Exceptions.

---

## 1. `test_architecture_element_hierarchy.py`

### `test_root_element_get_level_returns_0` bis `test_three_level_hierarchy_returns_3`
- **Verknüpfte REQ-L2 ID:** REQ-L2-PL-004 (sowie REQ-L1-041)
- **Aktuelles Verhalten (Shallow-Check):** **Kritische Test-Illusion (Fake-Tests).** Die Tests instanziieren ein `MagicMock(spec=ArchitectureElement)` und überschreiben die Funktion `get_level` explizit mit einer eigenen Mock-Funktion (`el.get_level = mock_get_level`). Diese Tests testen rein gar nichts, außer dass eine von Python Mock erstellte Dummy-Funktion eine hartkodierte Zahl zurückgibt. Das System Under Test (SUT) wird vollständig umgangen.
- **Requirement AC:** Das Entity-Schema (und die Hierarchisierung) muss über Foreign-Key-Beziehungen korrekt abgebildet sein und funktionale Operationen wie das Berechnen der Hierarchieebene durchführen.
- **Exakter Refactoring-Bedarf:** Alle Mocks (`MagicMock`, `patch`) müssen gelöscht werden. Die Tests müssen echte `ArchitectureElement`-Objekte über das Django ORM speichern (`create()`) und verketten (z.B. Root -> Child -> Grandchild). Anschließend muss die tatsächliche `get_level()`-Methode der persistierten ORM-Instanzen aufgerufen und das Ergebnis verifiziert werden.

---

## 2. `test_transactions.py`

### `test_decorator_rolls_back_on_error` & `test_context_manager_batch_rollback`
- **Verknüpfte REQ-L2 ID:** REQ-L2-PL-002
- **Aktuelles Verhalten (Shallow-Check):** **Stark Shallow.** Die Tests prüfen das Rollback-Verhalten, indem sie manuell eine Python-Exception (`_InducedError("boom")`) innerhalb des Transaktionsblocks werfen. Dies testet lediglich das Python Context-Manager-Exception-Handling. Reale Datenbankprobleme, wie Integritätsfehler, werden so nicht verifiziert.
- **Requirement AC:** *Batch-Decomposition: Constraint-Verletzung bei Kind 7 -> gesamter Batch rollbackt* sowie *DB-Fehler nach INSERT Requirement -> Rollback*.
- **Exakter Refactoring-Bedarf:** Die manuell geworfenen Python-Exceptions (`_InducedError`) müssen entfernt werden. Der Test muss stattdessen eine echte Datenbank-Constraint-Verletzung provozieren, z.B. indem er versucht, beim 7. Objekt einen ForeignKey auf eine nicht existierende ID zu setzen oder ein UNIQUE-Constraint zu verletzen. Anschließend muss geprüft werden, ob das RDBMS den Fehler (`IntegrityError`) wirft und die gesamte Transaktion zurückgerollt wird.

---

## 3. `test_entity_schema.py`

### `test_all_13_entities_exist`
- **Verknüpfte REQ-L2 ID:** REQ-L2-PL-004
- **Aktuelles Verhalten (Shallow-Check):** Shallow. Der Test prüft lediglich, ob für 13 Modelle ein `_meta` Attribut existiert.
- **Requirement AC:** *Jede Entität enthält tenant_id-FK zu Tenant* und *Schema-Check bestätigt alle Tabellen und Spalten*.
- **Exakter Refactoring-Bedarf:** Der Test muss über alle 13 Entitäten iterieren und dynamisch verifizieren, ob das Feld `tenant_id` tatsächlich existiert (`_meta.get_field('tenant')`).

### `test_audit_modified_at_updates`
- **Verknüpfte REQ-L2 ID:** REQ-L2-PL-005
- **Aktuelles Verhalten (Shallow-Check):** **Logische Lücke.** Der Test speichert ein Update und prüft am Ende nur `assert artifact.created_at == created_at`. Es wird also nur geprüft, was sich *nicht* ändert.
- **Requirement AC:** *Update -> `modified_at` aktualisiert, `version` inkrementiert*.
- **Exakter Refactoring-Bedarf:** Der Test muss vor dem Speichern die alte `version` und `modified_at` merken. Nach dem Update und `refresh_from_db()` MUSS zwingend geprüft werden: `assert artifact.version == 2` und `assert artifact.modified_at > old_modified_at`. (Letzteres fehlt komplett im Code).

### Fehlender Test für `SET NULL` Audit-Felder
- **Verknüpfte REQ-L2 ID:** REQ-L2-PL-009
- **Aktuelles Verhalten:** Kein Test vorhanden.
- **Requirement AC:** *Lösche User mit Entities -> SET NULL auf Audit-Feldern*.
- **Exakter Refactoring-Bedarf:** Es muss ein neuer Test `test_set_null_on_user_deletion_for_audit_fields` geschrieben werden. Ein User legt ein Artifact an (`created_by=user`). Der User wird gelöscht. Das Artifact darf nicht gelöscht werden (kein Cascade), stattdessen muss `artifact.created_by == None` sein.

---

## 4. `test_tenant_isolation.py`

### `test_all_returns_only_active_tenant_rows` & `test_cross_tenant_access_is_blocked`
- **Verknüpfte REQ-L2 ID:** REQ-L2-PL-001
- **Aktuelles Verhalten (Shallow-Check):** **Scope zu gering.** Die Tests prüfen die Tenant-Isolation ausschließlich anhand der `Requirement`-Entität.
- **Requirement AC:** *Das PersistenceLayer MUSS einen Custom Django Manager auf ALLEN Entitäten implementieren...* sowie *Alle Entity-Modelle verwenden TenantManager*.
- **Exakter Refactoring-Bedarf:** Diese beiden Tests müssen mit `@pytest.mark.parametrize` ausgestattet werden, sodass sie in einer Schleife gegen **alle mandantenfähigen Entitäten** (Artifact, TraceLink, TestCase, Baseline, ...) ausgeführt werden, um zu garantieren, dass nicht bei einer einzigen Entität der Manager vergessen wurde.

### Fehlender Test für Raw-Query Filterung
- **Verknüpfte REQ-L2 ID:** REQ-L2-PL-001
- **Requirement AC:** *Raw-Query via Manager -> Manager injiziert T1-Filter*.
- **Exakter Refactoring-Bedarf:** Ein Test muss nachweisen, dass `Requirement.objects.raw("SELECT * FROM ...")` entweder blockiert wird oder sicher den Tenant filtert, andernfalls wird dieses AC nicht erfüllt.

---

## 5. `test_migrations_and_indexes.py`

### `test_btree_and_graph_indexes_exist` & `test_fulltext_indexes_exist`
- **Verknüpfte REQ-L2 ID:** REQ-L2-PL-003
- **Aktuelles Verhalten (Shallow-Check):** Shallow. Der Test prüft lediglich in den Systemkatalogen (`pg_indexes`), ob der Index dem Namen nach angelegt ist.
- **Requirement AC:** *`EXPLAIN ANALYZE` Tree-Query -> Index-Scan* und *`EXPLAIN ANALYZE` Full-Text-Search -> tsvector-Index*.
- **Exakter Refactoring-Bedarf:** Der Test muss eine reale FTS-Query bzw. Tree-Query aufrufen, den Query-Plan (`EXPLAIN`) über den Cursor auslesen und via Regex oder String-Matching prüfen, dass "Index Scan" oder "Bitmap Index Scan" auf dem entsprechenden FTS/Tree-Index stattfindet.

### `test_rls_enabled_on_tenant_tables`
- **Verknüpfte REQ-L2 ID:** REQ-L2-PL-010
- **Aktuelles Verhalten (Shallow-Check):** **Sehr Shallow.** Der Test checkt in `pg_class`, ob das `relrowsecurity`-Flag auf `true` steht. Er verifiziert nicht, ob die RLS-Policies funktional greifen!
- **Requirement AC:** *ORM-Bypass-Test: Raw SQL ohne App-Kontext liefert keine Fremddaten*.
- **Exakter Refactoring-Bedarf:** Im Test müssen Daten über das ORM in T1 persistiert werden. Anschließend muss eine "pure" psycopg2/Django-Cursor Abfrage `SELECT * FROM pl_requirement` erfolgen (ohne dass vorher die Tenant-Middleware ein `SET LOCAL app.current_tenant` ausführt!). Das Resultat MUSS 0 Zeilen betragen. Dies ist der unanfechtbare Beweis, dass RLS Daten blockiert.

---

## 6. `test_admin_login.py`

### Diverse Admin-Tests
- **Verknüpfte REQ-L2 ID:** REQ-L2-PL-004 (IF-PL-EXT-IN-006)
- **Aktuelles Verhalten:** Ziemlich solide Client-Tests für die Auth-Schnittstelle. Nicht oberflächlich.
- **Requirement AC:** Custom User und Role Modelle existieren.
- **Exakter Refactoring-Bedarf:** Kein zwingender Refactoring-Bedarf, eventuell im Docstring die Traceability auf `REQ-L2-PL-004` (User/Role) ergänzen.

---

## Gesamtfazit & Nicht abgedeckte Bereiche (Missing Tests)

Vollständig fehlende Testabdeckung für folgende Requirements:
- **REQ-L2-PL-007 & REQ-L2-PL-011 (Connection Pooling):** Keine Konfigurations- oder Lasttests für `CONN_MAX_AGE` und Pool-Timeouts vorhanden.
- **REQ-L2-PL-008 (Performance Latenzen):** Keine Benchmark-Tests vorhanden, die Latenzen für CRUD, Tree und FTS < 200ms/< 500ms beweisen.

**Empfehlung an den Developer-Agenten:** Setze den Refactoring-Bedarf Punkt für Punkt um, beginnend bei den kritischen Mocks in `test_architecture_element_hierarchy.py` und den manuellen Exceptions in `test_transactions.py`.
