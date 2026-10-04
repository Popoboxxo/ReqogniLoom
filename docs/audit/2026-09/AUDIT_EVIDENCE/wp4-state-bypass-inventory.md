---
type: EVIDENCE
scope: wp4-state-bypass-inventory
status: success
date: 2026-09-29
author_agent: data-engineer
---

# WP-4 Evidenz 2 — State-Bypass-Inventar (Kernstück)

Referenzmodell: `WorkflowItemState.current_state` ist der **einzige** Zustandsspeicher
(`backend/workflow/models.py:2059`-Dokumentation in `persistence/models.py`;
`backend/workflow/lifecycle_manager.py:159-166`: *„`WorkflowItemState.current_state` is now the
sole store"*). `Artifact.lifecycle_status` ist die **orthogonale** Soft-Delete-Achse
(Decision D-3) und wird getrennt geführt.

**Gesucht wurde nach jedem Codepfad, der `current_state` schreibt, ohne
`workflow.services.transition` → `transition_validator` → `perform_transition` zu durchlaufen.**

## 0. Ergebniskopf

| Kategorie | Anzahl |
|---|---|
| **Vollständige Bypass-Pfade** (State-Write ohne Transition-Validierung) | **4** |
| davon dokumentiert beabsichtigt (Design-by-Exception) | 2 |
| davon **undokumentiert / unbeabsichtigt** | **2** |
| Legitime Schreibpfade (mit Validierung) | 2 |
| Read-Pfade mit Schreibnebenwirkung | **1** (zusätzlich) |

## 1. Vollständige Inventur aller `current_state`-Schreibstellen

```
$ rg -n "WorkflowItemState\.objects\.(filter|create|bulk_create|update)" backend \
     --glob "!**/tests/**" --glob "!**/migrations/**"
```

| # | Ort | Art | Klassifikation |
|---|---|---|---|
| S1 | `backend/workflow/lifecycle_manager.py:378-384` | `.update(current_state=…, version=F("version")+1)` | **LEGITIM** — der einzige kanonische Write, CAS-geschützt |
| S2 | `backend/workflow/lifecycle_manager.py:141-147` | `objects.create(current_state=initial_state)` (Batch-Init) | LEGITIM — Initialisierung, keine Transition (`lifecycle_manager.py:154-156`: *„a plain initialization is not a transition"*) |
| S3 | `backend/workflow/lifecycle_manager.py:230-236` | `objects.create(current_state=initial_state)` (Lazy-Init) | LEGITIM — idempotent, IntegrityError-gefangen (`:237-242`) |
| S4 | `backend/workflow/lifecycle_manager.py:452-454` | `item_state.current_state = target_state; save(update_fields=[...])` in **`force_transition`** | **BYPASS** (designiert, D-1/D-3) |
| S5 | `backend/application/import_service.py:715-722` | `WorkflowItemState.objects.create(current_state=mapped_status)` — **CSV-Import** | **BYPASS** (unbeabsichtigt) |
| S6 | `backend/application/reqif_import_service.py:791-793` | `state_row.current_state = mapped; save(update_fields=["current_state","definition"])` — **ReqIF-Import** | **BYPASS** (unbeabsichtigt, mit Versionsblindstelle) |
| S7 | `backend/application/reqif_import_service.py:795-802` | `objects.create(current_state=mapped)` — **ReqIF-Import** | wie S5 |

Weitere `current_state`-Treffer sind **reine Lesevorgänge**:
`services.py:310,850,900,917`, `state_reader.py:133,219,223`,
`definition_store.py:1363,1403,1412`, `global_definition_store.py:266`,
`rest_api/mixins/workflow_transitions.py:102,141`,
`se_metrics/aggregator.py:243`, `application/ai_proposal_service.py:310`,
`application/review_queue_service.py:119`, `workflow/admin.py:66`.

**`Artifact.lifecycle_status`-Writes** (orthogonale Achse, kein Bypass):
`workflow/services.py:446` (`_set_lifecycle_status`, einziger Write, `:434` *„this is the only
write left"*), aufgerufen aus `outdate()` `:639` und `reactivate()` `:696`.

## 2. Die vier Bypass-Pfade im Detail

### BYPASS-1 (S4) — `force_transition`: der designierte Escape-Hatch

`backend/workflow/lifecycle_manager.py:416-477`

```python
@transaction.atomic
def force_transition(self, item_id, item_type, workspace_id, target_state,
                     change_reason, actor) -> TransitionOutcome:
    """Transition an item to ``target_state`` bypassing normal
    preset-transition validation.                                    # :426-427
    ...
    item_state = (WorkflowItemState.objects.select_for_update()
                  .get(item_id=item_id, item_type=item_type,
                       workspace_id=workspace_id))                    # :447-450
    previous_state = item_state.current_state
    item_state.current_state = target_state                          # :452
    item_state.version += 1                                           # :453
    item_state.save(update_fields=["current_state", "version"])      # :454
```

Positiv: der Zeilen-Lock **ist** vorhanden (`:448`), ein History-Eintrag **wird** geschrieben
(`:460-469`), `version` **wird** erhöht.

Negativ — was der Validator sonst hinklappen würde, fehlt vollständig:
- **keine** `allowed_roles`-Prüfung
- **kein** `requires_change_reason`-Gate (der `change_reason` wird nur in die History geschrieben)
- **keine** `signature_gate`-Prüfung (`signature_seal=signature_seal or ""` → `None` in `:475`)
- **keine** Graph-Validierung, **kein** Endzustands-Check

**Aufrufer:**
- `backend/application/interview_service.py:337-344` — produktiv, siehe BYPASS-2
- `workflow/services.py:639`/`:696` — **seit Phase 4 (D-3) NICHT mehr**; `outdate()`/`reactivate()`
  schreiben nur noch `Artifact.lifecycle_status`. Die Docstrings von
  `interview_service.py:300-301` und `application/workflow_facade.py:193`, die
  `force_transition` als „the same escape hatch `workflow.services.outdate()` uses"
  beschreiben, sind **veraltet** — `outdate()` nutzt es nicht mehr.

**Dead-Code-Teil:** `StateLifecycleManager.perform_transition` hat laut
`workflow/services.py:375` („This is the only non-test caller") genau **einen**
Produktionsaufrufer. `force_transition` hat mit `interview_service.py:337` **einen**.

→ **AUD-2026-09-170** (Medium). Designiert, aber die beiden Docstrings, die seinen
Sicherheitsumfang bewerben, sind falsch → eigener Unterpunkt.

### BYPASS-2 (S4 via InterviewService) — Auto-Abandon auf einem **Lese**-Pfad

`backend/application/interview_service.py:295-369` — **das gravierendeste Finding dieses Pakets.**

```python
@staticmethod
def _lazily_abandon_if_stale(session: InterviewSession, ctx) -> None:
    """spec §9: flip a stale in_progress session to abandoned on read."""   # :297
    ...
    if timezone.now() - session.modified_at < ABANDONED_TTL:
        return                                                             # :323-324
    current_status = state_reader.current_state("Interview", session.id) or \
                     state_reader.initial_state("Interview")              # :329-331
    if current_status != InterviewSession.STATUS_IN_PROGRESS:
        return                                                             # :332-333
    try:
        StateLifecycleManager().force_transition(...)                      # :337-344
        session.refresh_from_db()
        session.status = state_reader.current_state(...) or ...           # :351-353
    except Exception:                                                      # :354  <<<
        logger.debug("... force_transition unavailable ...")              # :363-366
        session.status = InterviewSession.STATUS_ABANDONED                # :367
        session.version = F("version") + 1                                # :368
        session.save(update_fields=["modified_at", "version"])            # :369
```

Fünf Defekte in einem Block:

1. **GET mutiert Zustand.** Die Methode wird aus `_get_session` (`:293`) aufgerufen, also aus
   jedem Lese-Request. Ein `GET` nimmt damit einen `SELECT … FOR UPDATE` (`:448`) und kann
   `current_state` umschreiben. Das verletzt die REST-Semantik und macht Read-Requests
   nicht-idempotent.
2. **`except Exception:` schluckt alles** (`:354`). Der Kommentar (`:355-362`) beschreibt
   *„No WorkflowItemState row"* — der Handler fängt aber auch `ValidationError`,
   `DatabaseError`, `OperationalError` und jeden Bug. Ein echter DB-Fehler degradiert
   lautlos zu `logger.debug` (`:363`, DEBUG-Level, also im Normalbetrieb unsichtbar).
3. **Der Fallback speichert den Status NICHT** (`:367`). `InterviewSession.status` wurde
   laut `:307-313` und `:357-359` als Spalte **gedroppt** — `current_state` ist der einzige
   Store. Der Client bekommt `"abandoned"` zurück, ein Folge-`GET` liefert wieder
   `in_progress`. **Read-after-write-Inkonsistenz mit Datenverlust.**
4. **`version` wird erhöht, ohne dass sich der State ändert** (`:368-369`). Das bricht den
   Optimistic-Lock-Vertrag in die Gegenrichtung: ein Client, der `expected_version`
   mitschickt, bekommt einen 409, obwohl inhaltlich nichts passiert ist — und weil die
   Methode bei **jedem** veralteten Read feuert, ist der 409 **reproduzierbar wiederholbar**.
5. **`force_transition` umgeht die Rollenprüfung** (BYPASS-1). Der Docstring begründet das
   mit `:299-302` („System-driven, TTL-based, not a user-permission-gated action") — das ist
   für den System-Pfad plausibel, macht den Pfad aber zum Rollen-freien Zustandsschreiber.

**Reconciliation:** CR-07 („Interview-Formalize/Abandon umgehen WorkflowFacade und
**verschlucken Engine-Fehler**; Audit-/Outbox-Seam kann fehlen", Beleg
`interview_service.py:1092-1129,1250-1268,1316-1349`) ist **BESTAETIGT** und durch die
konkreten Zeilen `:337` und `:354` **verschärft**: der Code ist im aktuellen Stand
weiterhin vorhanden, nur an eine andere Zeile gewandert. Punkt 5 der Kette (fehlende
History/Audit) ist allerdings **teilweise widerlegt**: `force_transition:460-469` schreibt
den History-Eintrag. Die Findings 1–4 sind **NEU**.

→ **AUD-2026-09-169** (High), Reconciliation `BESTAETIGT (CR-07) + NEU`.

### BYPASS-3 (S5) — CSV-Bulk-Import schreibt State ohne Transition

`backend/application/import_service.py:714-722`

```python
if definition is not None:
    WorkflowItemState.objects.create(
        item_id=obj.id, item_type=entity_type, workspace_id=workspace_id,
        definition=definition, current_state=mapped_status, tenant=tenant,
    )
```

Was geprüft wird: **nur die Zugehörigkeit** — `mapped_status = _map_status(status_raw, valid_states)`
(`:610`) gegen die `states` der Workspace-Definition (`:577`).
Was **fehlt**:
- **keine** Kantenprüfung (`from → to` gegen `transitions`) — der Import setzt einen
  Endzustand direkt, egal ob der Item-Status dorthin führen dürfte
- **kein** History-Eintrag → die Zustandsänderung ist im Audit-Trail unsichtbar
- **keine** `requires_change_reason`, **keine** Rolle, **kein** Signatur-Gate
- **kein** `version`-Guard: `version` startet bei 1, ein optimistic-lock-BASIS-Konflikt
  ist unmöglich (der Import *erzeugt* die Zeile, statt sie zu bewegen)

Der Kommentar `:706-713` referenziert `REQ-143` und `issue #113` und diskutiert nur den
`definition is None`-Fall — nicht die Validierungslücke.

**Live-Beleg, dass der Importpfad produktiv ist:** `import_service.py` ist der CSV-Import,
 Teil des REST-`/api/v1/*/import/`-Pfads; `reqif_import_service.py:53` importiert `_map_status`
daraus (`:53`), d. h. die beiden Pfade teilen sich die Status-Auflösung.

→ **AUD-2026-09-167** (High). **NEU** — kein CR-Track nennt einen Import-Bypass
(CR-07/CR-08 betreffen Workflow-Transitionen, nicht Importe).

### BYPASS-4 (S6/S7) — ReqIF-Import: Statuswechsel **ohne Versionserhöhung**

`backend/application/reqif_import_service.py:786-802`

```python
state_row = WorkflowItemState.objects.filter(
    item_id=entity.id, item_type=item_type        # :786-788  ← KEIN workspace_id!
).first()
if state_row is not None:
    if state_row.current_state != mapped or state_row.definition_id != definition.id:
        state_row.current_state = mapped
        state_row.definition = definition
        state_row.save(update_fields=["current_state", "definition"])   # :791-793
else:
    WorkflowItemState.objects.create(..., current_state=mapped, ...)  # :795-802
```

1. **Kein `version`-Bump auf dem Update-Pfad** (`:793`). Das ist die kritischste
   Einzelbeobachtung dieses Pakets: `perform_transition` garantiert
   `version = version + 1` in derselben Transaktion wie der State-Write
   (`lifecycle_manager.py:378-384`), und `WorkflowFacade.transition` beantwortet einen
   veralteten `expected_version` mit 409 (`services.py:318-323`). Der ReqIF-Import
   verändert `current_state`, **ohne** `version` zu berühren. Ein Client, der zuvor
   `expected_version=N` gelesen hat, bekommt seinen 409 nicht — er überschreibt
   den Import statt ihn zu erkennen. **Lost Update mit gestrichener Versionshistorie.**
2. **Kein History-Eintrag** (`:791-793`) — der Wechsel ist im Audit-Log unsichtbar.
3. **Keine Kantenprüfung** wie BYPASS-3.
4. **`filter()` ohne `workspace_id`** (`:786-788`). Das ist gegen die Unique-Constraint
   `uq_we_state_tenant_item (tenant_id, item_id, item_type)` (live verifiziert)
   **korrekt** — diese kennt kein `workspace_id` —, bedeutet aber: findet der Filter
   eine Zeile aus einem **anderen** Workspace desselben Tenants, wird sie
   `definition`-fremd überschrieben. Konsistent mit dem Modell, aber ohne
   Workspace-Fence.

**Transaktionsgrenze:** `_apply_relations`/`_apply_status` laufen in `transaction.atomic()`
(`:872` für Relations) — der Status-Write selbst (`:786-802`) ist jedoch eine
`@staticmethod` ohne eigene Transaktion und hängt an der aufrufenden Kette.

→ **AUD-2026-09-168** (High). **NEU**.

## 3. CR-08 verifiziert: validiert **nach** dem Lock (WIDERLEGT)

Die Vor-Audit-Aussage (`CR-08`, `11-consistency-review.md:119`):
*„Öffentliche Transition validiert vor dem Lock; `select_for_update()` schützt Zeile,
nicht die vorherige fachliche Entscheidung."* — Beleg
`workflow/services.py:273-327`, `workflow/lifecycle_manager.py:295-341`.

**Aktueller Code, `backend/workflow/services.py:302-341`:**

```python
# CR-08: the state read, the graph validation and the state write must all
# observe the same row under the same lock.                            # :302-305
with transaction.atomic():                                             # :306
    # CR-08: read the state from the locked row, never from an unlocked read.
    item_state = lifecycle.lock_item_state(item_id_uuid, item_type, workspace_uuid)  # :308
    current_state = item_state.current_state                           # :310
    if expected_version is not None and item_state.version != expected_version:     # :318
        raise WorkflowConflictError(...)                               # :319-323
    ...
    req = ValidationRequest(..., current_state=current_state, ...)    # :335-339
```

`lock_item_state` (`lifecycle_manager.py:246-289`) macht tatsächlich
`select_for_update()` (`:249` Docstring, `:268-275` begründet die
`transaction.atomic`-Pflicht ausführlich) und `perform_transition` bekommt den
**bereits gelockten** Row übergeben (`services.py:362` → `lifecycle_manager.py:354`
`if item_state is None:`), sodass kein zweiter `SELECT FOR UPDATE` nötig ist.

**Ergebnis: die Reihenfolge ist im aktuellen Code korrigiert.** Lock → Versionsprüfung →
Graph-Validierung gegen den gelockten Zustand → Write.

→ **AUD-2026-09-166**: Klassifikation **WIDERLEGT** (CR-08 Race-Anteil),
mit einer **verbleibenden** Teilbeobachtung (siehe unten).

**Verbleibender Rest (neu):** `perform_transition(item_state=None)` ist laut
`lifecycle_manager.py:330-331` ein *dokumentiert unterstützter* Pfad (*„when `None`
(every direct caller, incl. the tests) the row is locked here as before"*). Ein solcher
Direktaufrufer validiert **vor** dem Lock — genau die CR-08-Reihenfolge, nur in einer
anderen Funktion. Heute hat `perform_transition` genau einen Produktionsaufrufer
(`services.py:362`, der die korrigierte Reihenfolge hat), also ist der Restpfad heute
**nicht** produktiv aktiv. Er ist aber die einzige Stelle, an der die korrigierte
Reihenfolge umgangen werden kann, ohne dass ein Linter es bemerkt.

## 4. Was die Live-DB über die Wirksamkeit sagt

```sql
-- 3316 Zustandszeilen, 344 Workspaces, 175 History-Einträge
SELECT count(*), count(DISTINCT workspace_id) FROM we_item_state;   -- 3316 | 344
SELECT count(*) FROM we_history_entry;                             -- 175

-- 0 Zustände außerhalb der deklarierten States ihrer eigenen Definition
SELECT count(*) FROM we_item_state s
  JOIN we_engine_definition d ON d.id = s.definition_id
 WHERE NOT (s.current_state = ANY (SELECT jsonb_array_elements_text(
                                 (d.workflow_json->'states')::jsonb)));
-- 0
```

Lesung: die **Zugehörigkeits**-Invariante (`current_state ∈ states(definition)`) hält auf
der Live-Instanz zu 100 % — die `_map_status`-Normalisierung in beiden Importpfaden
erklärt das. Die **Kanten**-Invariante (`from → to ∈ transitions`) ist damit **nicht**
belegt, weil sie von keinem der drei Bypass-Pfade geprüft wird.

```sql
-- 401 Workspaces, aber nur 343 mit Zustandszeilen → 58 Workspaces ohne jede Zustandszeile
SELECT count(*) FROM pl_workspace pw WHERE NOT EXISTS (
  SELECT 1 FROM we_item_state s WHERE s.workspace_id = pw.id);       -- 58
```

Diese 58 Workspaces fallen auf `lifecycle_manager.ensure_item_state` (`:190-242`) zurück,
das den Zustand **lazy** auf `initial_state` anlegt. Ein Workspace ohne
`WorkflowEngineDefinition` hat dort **keinen** Zustand — `ensure_item_state:221-225`
wirft dann `WorkflowStateError`. Deshalb sind die 58 Workspaces faktisch
„zustandslose" Workspaces, in denen jede Transition in `WorkflowStateError` läuft.

## 4. Terminale Endzustände

Der Auftrag fragt nach dem Verhalten bei Transition in einen **nicht erlaubten Endzustand**.
Antwort, fünfteilig belegt — mit einer **Präzisierung**, die einenTeil meiner ersten
Lesart korrigiert:

1. Die Live-DB zeigt, dass `we_engine_definition.workflow_json` genau **drei** Top-Level-Keys
   hat: `states`, `transitions`, `state_meta`. **Kein `terminal`-Feld:**
   ```sql
   SELECT count(*) FROM we_engine_definition WHERE (workflow_json::jsonb) ? 'terminal';  -- 0
   ```
2. `state_meta` ist ein **echter, konsumierter** Mechanismus — nicht bloß ein Ablageort.
   Er wird gelesen in `workflow/services.py:1096-1097` (`_is_outdated_equivalent`, dort
   `:1096`/`:1130-1147` als Filter gegen aktive Listen), `application/goal_service.py:512`
   und `application/ai_derivation_service.py:1694,1807`. Live-Wert für `Requirement/extended`:
   ```json
   { "rejected":   {"is_outdated_equivalent": true},
     "deprecated": {"is_outdated_equivalent": true} }
   ```
   **Korrektur der ersten Lesart:** es gibt also *kein* tote Metadaten-Feld — es gibt
   eine funktionierende per-State-Metadaten-Schicht.
3. Aber: `state_meta` modelliert **ausschließlich** `is_outdated_equivalent`, nicht
   Terminalität. `definition_store.py:660-662` beschreibt das Flag selbst als
   *„the existing 'treat as terminal / hide from active lists' signal"* — Terminalität ist
   also eine **Interpretation**, die nur beim Aufbau von Sichtbarkeits-/Vorschlagslisten
   gezogen wird (`services.py:1147` `return frozenset(s for s in candidates if not
   _is_outdated_equivalent(s))`), **nicht** im Validator.
4. `transition_validator.py:350-357` prüft **ausschließlich** `from → to ∈ transitions`.
   Es gibt keinen Endzustands-Check. `deprecated` hat in `Requirement/extended` eine
   ausgehende Kante (`verified → deprecated`, live), ist also gar nicht terminal im
   Graphensinne; der einzige graph-theoretische terminale Zustand ist `rejected`
   (0 ausgehende Kanten).
5. Über BYPASS-2/3/4 ist ein Wechsel in einen beliebigen Zustand **von außen** erzwingbar:
   die Importpfade schreiben `current_state` direkt und umgehen damit auch die
   Kantenprüfung, die einen Sprung in eine Sackgasse (oder aus einer heraus) verhindern würde.

→ **AUD-2026-09-172** (Medium, **korrigiert**): `state_meta` ist konsumiert, aber es
modelliert nur `is_outdated_equivalent` (Sichtbarkeit), nicht Terminalität (Graph).
Es existiert **keine prüfbare Terminal-Semantik** im Datenmodell — sie ist eine
abgeleitete, lokal inkonsistente Konvention. Über die Import-Bypass-Pfade ist sie
programmatisch umgehbar.
