# ADR: Workflow-Engine als einzige Quelle der Wahrheit für den Lifecycle-Status

**Status:** ACCEPTED
**Datum:** 2026-07-15
**Entscheider:** Architekt + Tech-Lead (Senior-Review vor Merge)
**Betroffene REQ:** REQ-143
**Bezug:** REQ-L2-WE-002/003/005/006 (WorkflowEngine), REQ-L2-AS-003 (Requirement CRUD),
REQ-L2-RA-001 (REST-Contract), REQ-L2-MC-001 (MCP-Tools)

---

## Kontext

Der Lifecycle-Zustand eines Artefakts (Requirement, StakeholderNeed) wird derzeit an
**zwei** Stellen gehalten:

1. **Freitext-Feld `status`** (`CharField`, Default `"draft"`) auf `Requirement` und
   `StakeholderNeed` in `backend/persistence/models.py`. Das Feld ist über die REST-
   Serializer (`RequirementSerializer`, `StakeholderNeedSerializer`) und die MCP-Tools
   (`requirement.update` — schematisch, `needs.update` — tatsächlich) frei beschreibbar.
   Beliebige Zeichenketten werden akzeptiert.

2. **Zustandsmaschine der WorkflowEngine** in `backend/workflow/`:
   `WorkflowItemState.current_state` je Item, Definitionen je Preset
   (`definition_store.py`): minimal `draft→done`; standard `draft→approved→deprecated`;
   extended `draft→in_review→approved→deprecated`. Übergänge laufen über
   `lifecycle_manager.perform_transition` (atomar, Optimistic Locking, Append-only
   History), Approval-Übergänge werden per `signature_gate.py` versiegelt.

Beide Quellen driften auseinander: Ein PATCH auf `status` ändert das Freitext-Feld,
ohne die Zustandsmaschine zu berühren; ein Workflow-Übergang ändert `current_state`,
ohne `status` zu aktualisieren. Das Frontend verschärft die Divergenz zusätzlich mit
einer komplett eigenen, zur Engine inkompatiblen Enum-Liste
(`WORKFLOW_STATES = ['Draft','Review','Approved','In Progress',...]`).

Folgen: inkonsistente Anzeige, Umgehung der Rollen-/Signaturprüfungen der Engine,
nicht auditierbare Statusänderungen, falsche Baseline-Diffs.

---

## Entscheidung

Die **WorkflowEngine wird die einzige Quelle der Wahrheit** für den Lifecycle-Status.

- `WorkflowItemState.current_state` ist maßgeblich.
- Das persistente Feld `status` wird zu einem **denormalisierten, read-only Spiegel
  (Mirror)**. Es wird **ausschließlich** durch Workflow-Übergänge fortgeschrieben.
- Schreibzugriffe auf `status` über REST und MCP werden **ignoriert** (nicht als Fehler
  abgewiesen), damit Clients während der Übergangsphase weiterhin `status` mitsenden
  dürfen, ohne 4xx zu erhalten. Die Antwort enthält stets den **wahren** Wert.
- Statusänderungen erfolgen nur noch über die Transition-Endpoints, die die Rollen-,
  change_reason- und Signature-Gate-Prüfungen der Engine durchlaufen.

### Alternativen (verworfen)

- **`status` als schreibbare Bequemlichkeits-Spiegelung behalten** (Sync in beide
  Richtungen): verworfen — genau das erzeugt die Race-/Divergenz-Probleme und umgeht
  die Gates.
- **`status` ersatzlos entfernen**: verworfen — zu invasiv (Serializer, Indizes
  `idx_req_tnt_status`, CSV-Export/-Import, se_metrics, Frontend). Ein Mirror hält die
  bestehenden Lese-/Filterpfade stabil und ermöglicht eine schrittweise Migration.

---

## Wert-Mapping (Freitext → Workflow-State)

Bei der Migration und beim Anlegen fehlender Zustände wird der bestehende Freitext-Wert
auf einen gültigen Workflow-State abgebildet:

| Bestehender `status`-Wert                 | Ziel-State                          |
| ----------------------------------------- | ----------------------------------- |
| Wert ist gültiger State der Definition    | unverändert übernommen              |
| `draft`, `in_review`, `approved`, `deprecated`, `done` (bekannte Engine-States, aber ohne Definition im Workspace) | unverändert übernommen (nur `status`-Normalisierung, keine State-Row) |
| **alle übrigen / unbekannten Werte**      | **`draft`** (bzw. `initial_state` der Definition) |

Der `initial_state` einer Definition ist per Konvention der erste Eintrag der
`states`-Liste (`WorkflowDefinitionDTO.initial_state`), für alle Presets `"draft"`.

Es findet **kein** semantisches Umbenennen statt (z. B. Frontend-`"Review"` wird **nicht**
auf `"in_review"` geraten): frei erfundene Werte sind nicht vertrauenswürdig und werden
konservativ auf `draft` zurückgesetzt, damit kein Artefakt fälschlich als „freigegeben"
erscheint.

---

## Änderung des API-Contracts

### REST

- `RequirementSerializer.status` und `StakeholderNeedSerializer.status` werden
  `read_only`. Eingehende `status`-Felder werden von DRF still verworfen (kein 400).
- Die ViewSets leiten `status` **nicht** mehr an die Service-Schicht weiter.
- **Neuer Endpoint** `GET /api/v1/requirements/{pk}/transitions/`:
  liefert `current_state`, die vollständige `states`-Liste und die vom aktuellen Zustand
  aus **erlaubten** Übergänge (inkl. `requires_change_reason`, `signature_gate`).
- **Neuer Endpoint** `POST /api/v1/requirements/{pk}/transitions/`:
  führt einen Übergang aus (`target_state`, optional `change_reason`, `credential`).
  Delegiert an `WorkflowFacade.transition(item_type="Requirement")` und aktualisiert den
  `status`-Mirror atomar.

Begründung der Endpoint-Wahl: Der bestehende `WorkflowDefinitionViewSet`
(`/api/v1/workflows/`) arbeitet fest mit `item_type="Artifact"` und liefert **keine**
erlaubten Übergänge zurück (GET ist bewusst leer). Ein Requirement-naher Sub-Resource-
Endpoint ist für Frontend und MCP eindeutiger, respektiert die Ressourcenidentität
(`requirement_id == WorkflowItemState.item_id`, `item_type="Requirement"`) und vermeidet
eine Umdeutung des vorhandenen, artifact-basierten Endpoints.

### MCP

- `requirement.update`: leitete `status` **bereits heute nicht** an den Service weiter;
  das Input-Schema wird um einen Hinweis ergänzt, dass `status` read-only/ignoriert ist.
- `needs.update`: `status` wird aus den weitergereichten Feldern entfernt und im Schema
  als ignoriert dokumentiert.

Die Antwort-DTOs (`_requirement_to_dict`, `_need_to_dict`) enthalten weiterhin `status`
— jetzt garantiert den wahren, engine-gespiegelten Wert.

---

## Konsequenzen

- Statusänderungen sind nur noch über die Transition-Endpoints möglich und damit
  vollständig auditiert, rollen- und signaturgeprüft.
- `status` bleibt für Filter/Index/CSV/se_metrics als Lesewert erhalten und ist garantiert
  konsistent zum Workflow.
- Das Frontend wird von der Transition-API getrieben (Dropdown = erlaubte Übergänge;
  read-only-Anzeige, wenn kein Übergang erlaubt ist), statt einer freien Enum.

### Grenzfall: Artefakte ohne Workflow-Definition

Die Workflow-Initialisierung bei `create_requirement` ist best-effort (fehlt eine
Definition im Workspace, wird sie übersprungen). Für `StakeholderNeed` existiert heute
**keine** Workflow-Initialisierung. Für solche Items ohne `WorkflowItemState`:

- Die Migration kann keine State-Row anlegen (die FK auf `WorkflowEngineDefinition` ist
  `PROTECT` und erfordert eine vorhandene Definition). In diesem Fall wird lediglich der
  `status`-Wert gemäß Mapping **normalisiert** (unbekannt → `draft`).
- Sobald für den Workspace/Item-Type eine Definition existiert und die Engine ein Item
  initialisiert, wird der Mirror wieder ausschließlich über Übergänge geführt.

`StakeholderNeed` wird in dieser Arbeit ebenfalls schreibgeschützt (API ignoriert
`status`), damit keine neue Divergenz entsteht; die vollständige Anbindung von Need-
Workflows (Initialisierung + eigene Definition) ist bewusst **außerhalb** des Scopes von
AP-09 und als Folgearbeit vorgesehen.

---

## Rollout

1. Migration `workflow/0003_reconcile_status_mirror` gleicht bestehende Daten ab:
   Item mit State-Row → `status := current_state`; Item ohne State-Row, aber mit
   Definition → State-Row anlegen (gemapptes `status`) und `status` spiegeln;
   Item ohne Definition → `status` normalisieren.
2. Deploy Backend (Serializer read-only, Transition-Endpoints, Mirror-Sync im
   `lifecycle_manager`).
3. Deploy Frontend (Transition-getriebenes Dropdown). Alte Clients, die weiterhin
   `status` in PATCH senden, funktionieren unverändert (Feld wird ignoriert).

## Rollback

- Frontend/Backend-Code sind rückrollbar; der Serializer wieder `status`-schreibbar zu
  machen genügt, um das alte Verhalten wiederherzustellen.
- Die Migration ist **nicht datenverlustbehaftet in der Struktur** (keine Spalten/Tabellen
  entfernt). Ihre Rückwärts-Operation ist ein `no-op` (`migrations.RunPython.noop`): die
  reconciled/normalisierten `status`-Werte bleiben gültige Werte; ein exaktes
  Wiederherstellen der vorherigen Freitext-Werte ist weder möglich noch erwünscht.

---

*Erstellt: 2026-07-15 | Für: REQ-143 (AP-09)*
