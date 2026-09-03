# Dokument-Sicht Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ein echtes `Document`-Objekt mit Kapitelstruktur, ein nummerierter Lesemodus mit Markdown-Export und Druck-Stylesheet, und `Baseline.scope="document"` zusätzlich an dieses Objekt bindbar statt nur an eine beliebige Artefakt-ID.

**Architecture:** `Document`/`DocumentSection` landen als plain `models.Model` mit `tenant_id`/`workspace_id`-UUIDFields in `application/models.py` (Tabellen `as_document`, `as_document_section`) — dieselbe Konvention wie `Adr`/`Risk`/`Issue`/`ChangeRequest` in derselben App, inkl. separater RLS-Migration. Ein `DocumentService` (Layer 2, ADR-01 Single Entry Point) kapselt CRUD, Sektions-Auflösung und Lesemodus; der Markdown-Renderer wird als freie Funktion aus `ExportService.export_markdown` herausgezogen und von Lesemodus, Export und (später) MCP `resources/read` gemeinsam benutzt. Die Baseline-Bindung erfolgt **additiv** über einen neuen Parameter `document_object_id` neben dem bestehenden, artefakt-basierten `document_id` — keine Bedeutungsänderung an einem bestehenden Parameter.

**Tech Stack:** Python 3.x / Django 5.2+ / DRF 3.15+ / PostgreSQL 16 (RLS, rekursive CTEs, `plpgsql`-Trigger) / pytest / React 18 + TypeScript 5.5 strict / Vite 5 / vitest / react-i18next

**Spec:** docs/superpowers/specs/2026-09-03-dokumentensicht-design.md

## Global Constraints

- `DocumentSection.content_type` ist genau eine von drei Ausprägungen: `"query"`, `"fixed"`, `"subtree"`.
- `content_type="query"` benutzt **exakt** die Filter-DSL aus der Tabellenansicht-Spec, Abschnitt 4.1 — Form `{"item_type": ..., "filters": {...}, "sort": [...]}`. Kein zweites Filter-Format.
- `content_type="fixed"` ist eine explizit kuratierte, geordnete Artefakt-ID-Liste (`fixed_artifact_ids`).
- `content_type="subtree"` bildet das heutige Baseline-Document-Scope-Verhalten ab (`subtree_root_artifact`, Auflösung über `Artifact.parent` **und** `derives-from`/`refines`-TraceLinks).
- Nummerierung im Lesemodus ist hierarchisch nach Sektions- und Artefakt-Reihenfolge (1, 1.1, 1.2, 2, ...), analog klassischer Lastenheft-Gliederung.
- Lesemodus-Route im Frontend: `/documents/<id>/read` — Vollbild-Lesefläche statt Split-View, mit `@media print`-optimiertem Stylesheet.
- Export: `GET documents/<id>/export?format=markdown` — reine Serialisierung des bereits gerenderten Lesemodus-Inhalts, **kein neuer Dependency**. DOCX ist explizit nicht Teil dieser Spec.
- REST-Routen: `GET/POST/PATCH/DELETE documents/`, `documents/<id>/sections/` (CRUD, Reorder), `documents/<id>/read/`, `documents/<id>/export/`.
- MCP-Tools: `document.list`, `document.get`, `document.read` (liefert denselben Lesemodus-Markdown).
- `parent_section` braucht eine Zyklus-Prüfung beim Speichern, analog zur bestehenden TraceLink-Zyklenprüfung ("Cycle detected").
- `query`-Sektionen werden **zur Lesezeit** ausgewertet, nicht zur Dokumenterstellungszeit — der Lesemodus ohne Baseline ist bewusst "live", nicht eingefroren.
- Snapshot, Diff und `VersionReconstructor` der Baseline-Infrastruktur bleiben unverändert.
- Ein Renderer, mehrere Zugriffswege — keine zweite Markdown-Implementierung.
- Jede DRF-View MUSS den Tenant-Kontext setzen (`_set_tenant_context(ctx)` im Service, `get_auth_context(request)` in der View).
- Keine direkten Model-Queries in DRF-Views — immer über `application/`-Services (ADR-01).
- Keine neuen `style={{`-Literale unter `frontend/src/components/` — `frontend/src/test/ui-ratchet.test.ts` erzwingt eine monotone Obergrenze. Neue UI ausschließlich über CSS-Klassen + Custom Properties aus `styles/tokens.css`.
- Keine dotted flat keys in den i18n-Locales (`keySeparator` ist `"."`) — immer verschachtelte Objekte, `de.json` und `en.json` paritätisch (`frontend/src/test/i18n-parity.test.ts`).
- `data-testid` auf allen interaktiven UI-Elementen.
- Keine wildcard imports; Import-Reihenfolge Standard Library → Third-Party → Local.

---

## Verifizierter Ist-Zustand (vor Task 1 lesen)

Diese Punkte wurden gegen den Code auf `main` geprüft und weichen von der Spec ab. Sie sind in die Tasks bereits eingearbeitet — hier zur Begründung.

**V1 — `_resolve_document()` steht nicht bei Zeile 74-77.**
Die Spec zitiert `baseline/delta_index_builder.py:74-77`; dort steht der *Dispatch*:

```python
elif scope == "document":
    if document_id is None:
        raise ValueError("document_id is required for scope='document'")
    return self._resolve_document(document_id, workspace_id, tenant_id)
```

Die Funktion selbst ist `ScopeResolver._resolve_document(self, document_id: uuid.UUID, workspace_id: uuid.UUID, tenant_id: uuid.UUID) -> list[DeltaIndexTuple]` ab **Zeile 249**. `document_id` ist dort eine **Root-Artefakt-UUID**, kein Dokument. Sie löst per rekursiver CTE über zwei Kantenquellen auf (`pl_artifact.parent_id` **und** `derives-from`/`refines`-TraceLinks, Issue #42) und hängt anschließend alle TraceLinks an, deren `source_id` im Scope liegt.

**V2 — Die vollständige Aufruferkette von `document_id` (Blast Radius).**
`BaselineViewSet.create` (`rest_api/views.py:3203-3229`, Feldname nach außen `artifact_id`) → `BaselineFacade.create_baseline(document_id=...)` (`application/baseline_facade.py:81`) → `BaselineFacade._enforce_audit_gate(document_id=...)` (`:222`) → `AuditScope.artifact_id` / `AuditContext.scope_artifact_id` (`traceability/audit/types.py:85,110`) → `baseline.services.build(document_id=...)` (`:76`) → `DeltaIndexBuilder.build(document_id=...)` (`:383`) → `ScopeResolver.resolve(document_id=...)` (`:54`) → `_resolve_document()` (`:249`). Zusätzlich: `mcp_server/tools/baseline.py:176,190` (`document_id`-Parameter im Tool-Schema) und der Preview-Pfad `baseline/views.py:161` → `baseline.services.preview_scope_items(artifact_id=...)` (`:246`) → `baseline.services.resolve_scope_item_ids(artifact_id=...)` (`:307`).
Neun Aufrufstellen. Eine Bedeutungsänderung von `document_id` würde alle neun still brechen — daher Entscheidung D1.

**V3 — `BaselineSnapshot.artifact` wird nie geschrieben. Der Spec-Migrationspfad hat keine Quelldaten.**
`BaselineSnapshot.artifact` existiert als nullable FK (`baseline/models.py:83`, Migration `0003_baselinesnapshot_artifact.py`), aber `BaselineMetadata` (`baseline/types.py:41-55`) hat **kein** `artifact`-Feld, und `BaselineStore.persist_delta_index` konstruiert den Snapshot ohne es (`baseline/store.py:101-113`):

```python
snapshot = BaselineSnapshot(
    workspace_id=metadata.workspace_id,
    scope=metadata.scope,
    name=metadata.name,
    description=metadata.description or "",
    created_by_ref=metadata.created_by,
    tenant_id=tenant_id,
    created_at=created_at,
)
```

Die Spalte ist also auf allen bestehenden Zeilen `NULL`. Konsequenzen:
1. Die Spec-Migration in Abschnitt 6 ("für jede vorhandene `scope="document"`-Historie mit einer Root-`artifact_id` ...") findet **keine** Zeilen. Sie ist faktisch ein No-Op — wird in Task 9 trotzdem defensiv und korrekt implementiert, falls ein Deployment die Spalte anders befüllt hat.
2. Latenter Datenverlust im Bestand: eine heutige Document-Scope-Baseline speichert nirgends, welchen Root sie abgedeckt hat. Task 8 behebt das mit, weil derselbe Schreibpfad ohnehin angefasst wird.

**V4 — `BaselineSnapshot` ist DB-seitig unveränderlich.**
`baseline/migrations/0001_initial.py:163-186` installiert `bl_raise_immutable()` und `trg_baseline_snapshot_immutable BEFORE UPDATE OR DELETE ON bl_baseline_snapshot`. Die Funktion kennt **keinen** GUC-Ausweg — jedes `UPDATE` schlägt mit `Baselines are immutable` fehl. Ein Backfill (Task 9) muss den Trigger deshalb explizit umgehen. Präzedenzfall im Repo: `icd/migrations/0006_icd_version_delete_guard.py` (dokumentiert, dass `ALTER TABLE ... DISABLE TRIGGER` Tabellen-Eigentum verlangt — Migrationen laufen als Owner, die Anwendung dagegen als `persistence.db_roles.APP_DB_ROLE`).

**V5 — Der "gemeinsame Markdown-Renderer" existiert nicht wie beschrieben.**
Die Spec (Abschnitt 4) und die MCP-Modernisierung-Spec (Abschnitt 4) behaupten, `McpArtifactProvider` nutze bereits einen Artefakt-Markdown-Renderer. Tatsächlich ist `backend/diagram/mcp_artifact_provider.py:164` **diagramm-spezifisch**: `McpArtifactProvider.get_artifact(self, diagram_id: str) -> dict[str, Any]` delegiert an `DiagramManager.get_diagram()` und rendert nur Diagramm-Payloads. Für Requirements/ArchitectureElements/TestCases gibt es keinen generischen Renderer.
Der nächstliegende reale Kandidat ist die Pro-Zeile-Schleife in `ExportService.export_markdown` (`application/export_service.py:439-451`). Task 4 zieht genau diese Schleife als freie Funktion heraus. Damit dreht sich die Abhängigkeitsrichtung gegenüber der Spec um: **dieser Plan produziert den geteilten Renderer, die MCP-Modernisierung konsumiert ihn** (statt umgekehrt).

**V6 — Konventionen, die die Tasks binden.**
`ALTER DEFAULT PRIVILEGES` in `persistence/migrations/0048_app_role.py` vergibt CRUD auf künftige Tabellen automatisch an `APP_DB_ROLE` — neue Tabellen brauchen **keinen** eigenen `GRANT`, aber sehr wohl eine eigene RLS-Policy-Migration (Muster: `application/migrations/0009_risk_issue_rls_policies.py`).
`GenericCrudToolGroup` (`mcp_server/tools/generic.py:205`) erzeugt `{prefix}.read` als *Entity-Read* — kollidiert mit `document.read` = *Lesemodus* aus der Spec (Entscheidung D5).
Modelle in `application/models.py` sind plain `models.Model` mit `tenant_id`/`workspace_id`-UUIDFields und `objects`/`unscoped = models.Manager()`, **nicht** `TenantScopedModel` (Entscheidung D8).

---

## Architektur-Entscheidungen

**D1 — Baseline-Bindung additiv über `document_object_id`, nicht durch Umdeutung von `document_id`.**
*Kontext:* `document_id` bedeutet in neun Aufrufstellen (V2) "Root-Artefakt-UUID".
*Wahl:* Neuer, optionaler Parameter `document_object_id: Optional[UUID]` (echte `Document.id`) parallel zum bestehenden `document_id`. Für `scope="document"` muss **genau einer** von beiden gesetzt sein. REST akzeptiert weiterhin `artifact_id` (unverändert) und zusätzlich `document_id` (neu, → `document_object_id`).
*Verworfen:* (a) `document_id` umdeuten — bricht neun Aufrufer still, inklusive des MCP-Tool-Schemas. (b) Anhand der UUID erraten, ob sie in `as_document` oder `pl_artifact` liegt — id-Raum-Verwechslung ist in dieser Codebase bereits eine wiederkehrende 404-Quelle (#414, #237, #264); noch eine implizite Überladung verschärft ein bekanntes Problem. (c) `document_id` in `root_artifact_id` umbenennen — größerer Diff ohne Funktionsgewinn, bricht das MCP-Schema.
*Konsequenzen:* Bestandsverhalten bleibt bitgenau. Preis: ein zusätzlicher Parameter durch vier Schichten und ein Exklusiv-Validator.

**D2 — Der geteilte Markdown-Renderer wird aus `ExportService` extrahiert, nicht aus `McpArtifactProvider`.**
*Kontext:* V5 — der in der Spec genannte Renderer ist diagramm-spezifisch.
*Wahl:* `render_artifact_markdown(row: dict, heading_level: int = 2) -> str` als freie Funktion in `application/artifact_markdown.py`; `ExportService.export_markdown` ruft sie auf (verhaltensgleich), Lesemodus und Export ebenfalls.
*Verworfen:* Einen zweiten Renderer für den Lesemodus schreiben — genau das Divergenz-Risiko, das die MCP-Spec in ihrem Risiko-Abschnitt benennt.
*Konsequenzen:* Ein Renderer, drei Aufrufer. Die MCP-Modernisierung muss `resources/read` an diese Funktion hängen statt an `McpArtifactProvider`.

**D3 — Nummerierung: innerhalb einer Sektion zuerst Artefakte, dann Kindsektionen, ein gemeinsamer Zähler.**
*Kontext:* Die Spec nennt "1, 1.1, 1.2, 2" ohne zu sagen, wie Artefakte und Kindsektionen interagieren.
*Wahl:* Sektion `1.1` mit zwei Artefakten und einer Kindsektion ergibt `1.1.1` (Artefakt), `1.1.2` (Artefakt), `1.1.3` (Kindsektion). Ein Zähler, Inhalt vor Untergliederung.
*Verworfen:* Getrennte Zähler für Artefakte und Sektionen — erzeugt doppelte Nummern (`1.1.1` als Artefakt *und* als Sektion).
*Konsequenzen:* Entspricht der klassischen Lastenheft-Lesereihenfolge; Nummern sind stabil, solange `order` stabil ist.

**D4 — Zyklus-Prüfung als DFS im Service, nicht als DB-Constraint.**
*Kontext:* Spec-Risiko 2 verlangt eine Zyklusprüfung für `parent_section`.
*Wahl:* DFS über die `parent_section`-Kette beim Setzen von `parent_section`, Fehlermeldung `"Cycle detected"` — wie die bestehende TraceLink-Prüfung und `ADR-L3-AS001-01` ("DFS cycle detection before persistence").
*Verworfen:* Rekursiver DB-Trigger — nicht testbar ohne Postgres, kein Präzedenzfall im Repo.

**D5 — Eigene `DocumentToolGroup` statt `GenericCrudToolGroup`.**
*Kontext:* `GenericCrudToolGroup` belegt `{prefix}.read` mit *Entity-Read*; die Spec will `document.read` = *Lesemodus-Markdown* (V6).
*Wahl:* Handgeschriebene `DocumentToolGroup` mit exakt `document.list`, `document.get`, `document.read` wie in der Spec.
*Verworfen:* `GenericCrudToolGroup` + Sonderfall — `document.read` hätte dann zwei Bedeutungen je nach Registrierungsreihenfolge.

**D6 — Filter-DSL wird über genau ein Adapter-Modul konsumiert.**
*Kontext:* Die Tabellenansicht-Spec definiert die DSL und die REST-Form, benennt aber keine Service-Funktion (siehe OFFENE FRAGE 1).
*Wahl:* `application/document_query_adapter.py` mit `run_artifact_query(ctx, workspace_id, query) -> list[dict]`. Nur diese eine Datei kennt den Aufrufweg in die Tabellenansicht-Implementierung.
*Konsequenzen:* Weicht der reale Name ab, ändert sich genau eine Datei.

**D7 — Document-Scope-Baselines nehmen weiterhin die TraceLinks mit, deren Source im Scope liegt.**
*Kontext:* Die Spec sagt zur TraceLink-Aufnahme beim neuen Auflösungsweg nichts.
*Wahl:* Verhaltensparität mit `_resolve_document()` (V1) — dieselbe TraceLink-Anhängung, nur über die vereinigte Artefaktmenge aller Sektionen.

**D8 — `Document`/`DocumentSection` als plain `models.Model` in `application/models.py`.**
*Kontext:* Die Spec schreibt `TenantScopedModel`; alle Nachbarn im selben App/Tabellenpräfix (`as_adr`, `as_risk`, `as_issue`, `as_change_request`) sind plain `models.Model` mit expliziten `tenant_id`/`workspace_id`-UUIDFields (V6).
*Wahl:* Nachbarkonvention. `TenantScopedModel` brächte eine `tenant`-FK auf `pl_tenant` plus tenant-filternden Manager und würde von den `as_*`-RLS-Migrationen abweichen.
*Konsequenzen:* Isolation kommt aus der expliziten RLS-Policy (Task 2) plus dem Service-Filter — dieselbe Verteidigung wie bei `Risk`/`Issue`.

---

## OFFENE FRAGEN

**OFFENE FRAGE 1 (nicht blockierend, mit begründeter Vorgabe umgesetzt) — Service-Einstiegspunkt der Filter-DSL.**
Die Tabellenansicht-Spec (Abschnitt 4.1) definiert die DSL und die REST-Form `GET artifacts/?item_type=&filters=<JSON>&sort=<JSON>`, benennt aber keine Funktion auf Service-Ebene, an die `DocumentSection.query` andocken kann. Dieser Plan legt in Task 6 den Vertrag `run_artifact_query(ctx, workspace_id, query) -> list[dict]` in `application/document_query_adapter.py` fest und implementiert ihn zunächst gegen die bestehende Artefakt-Leseschicht. Landet die Tabellenansicht mit einem anderen Namen, ist ausschließlich dieses Adapter-Modul anzupassen — keine andere Datei dieses Plans kennt die DSL-Ausführung. **Vor Task 6 prüfen:** Existiert `application/artifact_query_service.py` (oder ein gleichwertiger Einstieg) bereits aus Spec 9? Dann Adapter direkt dagegen verdrahten statt gegen den Fallback.

**OFFENE FRAGE 2 (nicht blockierend, in Task 9 defensiv gelöst) — Es gibt nichts zu migrieren.**
Spec Abschnitt 6 beschreibt eine Migration bestehender Document-Scope-Baselines, aber `BaselineSnapshot.artifact` ist auf allen Zeilen `NULL` (V3). Die Migration in Task 9 ist damit im Regelfall ein No-Op. Sie wird trotzdem vollständig und korrekt implementiert (inkl. Trigger-Umgehung), weil sie in einem Deployment mit abweichend befüllter Spalte greifen muss. **Vor dem Rollout gegen Produktivdaten** ist der in Spec Abschnitt 9 geforderte Dry-Run gegen eine Kopie durchzuführen; das Zähl-Ergebnis (erwartet: 0 Zeilen) ist im Rollout-Protokoll festzuhalten.

---

## File Structure

```
backend/
  application/
    models.py                                   MODIFY  + Document, DocumentSection
    migrations/
      0020_document_and_document_section.py     CREATE  Schema
      0021_document_rls_policies.py             CREATE  RLS für as_document, as_document_section
    artifact_markdown.py                        CREATE  render_artifact_markdown() (D2)
    document_query_adapter.py                   CREATE  run_artifact_query() (D6)
    document_service.py                         CREATE  DocumentService (Layer 2)
    export_service.py                           MODIFY  export_markdown ruft den extrahierten Renderer
    baseline_facade.py                          MODIFY  document_object_id durchreichen (D1)
    tests/
      test_document_models.py                   CREATE
      test_artifact_markdown.py                 CREATE
      test_document_service.py                  CREATE
      test_document_read.py                     CREATE
      test_baseline_document_binding.py         CREATE
  baseline/
    delta_index_builder.py                      MODIFY  _resolve_document_object() + Dispatch
    services.py                                 MODIFY  build/resolve_scope_item_ids + document_object_id
    store.py                                    MODIFY  artifact/document FK persistieren
    types.py                                    MODIFY  BaselineMetadata + root_artifact_id/document_id
    models.py                                   MODIFY  + BaselineSnapshot.document
    migrations/
      0007_baselinesnapshot_document.py         CREATE  FK + defensiver Backfill (Trigger-Umgehung)
    tests/
      test_document_object_scope.py             CREATE
  traceability/audit/types.py                   MODIFY  AuditScope/AuditContext + document_object_id
  rest_api/
    serializers.py                              MODIFY  + Document-/Section-Serializer
    views.py                                    MODIFY  + DocumentViewSet, Baseline-create um document_id
    urls.py                                     MODIFY  router.register("documents", ...)
    tests/
      test_document_api.py                      CREATE
  mcp_server/
    tools/document.py                           CREATE  DocumentToolGroup (D5)
    tool_registry.py                            MODIFY  "document": DocumentToolGroup()
    tests/test_document_tool_group.py           CREATE

frontend/src/
  api/documents.ts                              CREATE  API-Wrapper
  components/DocumentReadView/
    DocumentReadView.tsx                        CREATE  Lesemodus (Vollbild)
    DocumentReadView.css                        CREATE  inkl. @media print
  components/NavigationShell/NavigationShell.tsx MODIFY  Route /documents/:id/read
  i18n/locales/de.json                          MODIFY  + documents.*
  i18n/locales/en.json                          MODIFY  + documents.*
  test/
    documentsApi.test.ts                        CREATE
    DocumentReadView.test.tsx                   CREATE
```

---

## Task 1: Document- und DocumentSection-Modelle

**Files:**
- Modify: `backend/application/models.py` (anhängen ans Dateiende, nach `ChangeRequestAffectedItem`)
- Create: `backend/application/migrations/0020_document_and_document_section.py`
- Test: `backend/application/tests/test_document_models.py`

**Interfaces:**
- Consumes: `persistence.models.Artifact` (FK-Ziel für `subtree_root_artifact`)
- Produces: `application.models.Document`, `application.models.DocumentSection` mit den Feldern `Document(id, tenant_id, workspace_id, title, created_by_id, created_at, updated_at)` und `DocumentSection(id, tenant_id, document, parent_section, title, order, content_type, query, fixed_artifact_ids, subtree_root_artifact)`; Konstanten `DocumentSection.CONTENT_TYPE_QUERY = "query"`, `CONTENT_TYPE_FIXED = "fixed"`, `CONTENT_TYPE_SUBTREE = "subtree"`

- [ ] **Step 1: Write the failing test**

Create `backend/application/tests/test_document_models.py`:

```python
"""Document / DocumentSection persistence contract (Dokument-Sicht, Abschnitt 3)."""
from __future__ import annotations

import uuid

import pytest

from application.models import Document, DocumentSection


@pytest.mark.django_db
def test_document_and_section_persist_with_all_three_content_types():
    tenant_id = uuid.uuid4()
    workspace_id = uuid.uuid4()

    doc = Document.objects.create(
        tenant_id=tenant_id, workspace_id=workspace_id, title="Lastenheft"
    )

    query_section = DocumentSection.objects.create(
        tenant_id=tenant_id,
        document=doc,
        title="Funktionale Anforderungen",
        order=0,
        content_type=DocumentSection.CONTENT_TYPE_QUERY,
        query={"item_type": "Requirement", "filters": {}, "sort": []},
    )
    fixed_section = DocumentSection.objects.create(
        tenant_id=tenant_id,
        document=doc,
        title="Kuratiert",
        order=1,
        content_type=DocumentSection.CONTENT_TYPE_FIXED,
        fixed_artifact_ids=[str(uuid.uuid4())],
    )
    child = DocumentSection.objects.create(
        tenant_id=tenant_id,
        document=doc,
        parent_section=query_section,
        title="Unterkapitel",
        order=0,
        content_type=DocumentSection.CONTENT_TYPE_SUBTREE,
    )

    assert doc.sections.count() == 3
    assert query_section.children.get() == child
    assert fixed_section.fixed_artifact_ids != []
    # Defaults must be usable without passing them explicitly.
    assert child.query is None
    assert child.fixed_artifact_ids == []
    assert child.subtree_root_artifact is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend pytest application/tests/test_document_models.py -v`
Expected: FAIL with `ImportError: cannot import name 'Document' from 'application.models'`

- [ ] **Step 3: Write minimal implementation**

Append to `backend/application/models.py`:

```python
class Document(models.Model):
    """Living specification document (Dokument-Sicht spec, section 3).

    Plain ``models.Model`` with explicit ``tenant_id``/``workspace_id`` UUID
    columns, matching the convention of every other ``as_*`` table in this app
    (Adr, Risk, Issue, ChangeRequest). Tenant isolation comes from the RLS
    policy installed in migration 0021 plus the service-layer filter.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True)
    workspace_id = models.UUIDField(db_index=True)
    title = models.CharField(max_length=255)
    created_by = models.ForeignKey(
        "persistence.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="documents",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = models.Manager()
    unscoped = models.Manager()

    class Meta:
        db_table = "as_document"
        indexes = [
            models.Index(fields=["workspace_id"], name="idx_document_ws"),
            models.Index(fields=["tenant_id", "workspace_id"], name="idx_document_tenant_ws"),
        ]

    def __str__(self) -> str:
        return f"Document({self.title!r}, id={self.id})"


class DocumentSection(models.Model):
    """One chapter of a :class:`Document`.

    ``parent_section`` mirrors the ``Artifact.parent`` self-reference pattern
    and yields the 1 / 1.1 / 1.1.1 numbering. Cycle prevention is enforced in
    ``application.document_service`` (D4), not by a DB trigger.
    """

    CONTENT_TYPE_QUERY = "query"
    CONTENT_TYPE_FIXED = "fixed"
    CONTENT_TYPE_SUBTREE = "subtree"
    CONTENT_TYPE_CHOICES = (
        (CONTENT_TYPE_QUERY, "Query"),
        (CONTENT_TYPE_FIXED, "Fixed List"),
        (CONTENT_TYPE_SUBTREE, "Artifact Subtree"),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True)
    document = models.ForeignKey(
        Document, on_delete=models.CASCADE, related_name="sections"
    )
    parent_section = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="children",
    )
    title = models.CharField(max_length=255)
    order = models.IntegerField(default=0)
    content_type = models.CharField(max_length=16, choices=CONTENT_TYPE_CHOICES)
    # content_type="query": the Filter-DSL from the Tabellenansicht spec,
    # section 4.1 — {"item_type": ..., "filters": {...}, "sort": [...]}.
    query = models.JSONField(null=True, blank=True)
    # content_type="fixed": explicitly curated, ordered artifact list.
    fixed_artifact_ids = models.JSONField(default=list, blank=True)
    # content_type="subtree": today's Baseline document-scope behaviour.
    subtree_root_artifact = models.ForeignKey(
        "persistence.Artifact",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="document_sections",
    )

    objects = models.Manager()
    unscoped = models.Manager()

    class Meta:
        db_table = "as_document_section"
        ordering = ["order", "id"]
        indexes = [
            models.Index(fields=["document", "order"], name="idx_docsection_doc_order"),
            models.Index(fields=["parent_section"], name="idx_docsection_parent"),
        ]

    def __str__(self) -> str:
        return f"DocumentSection({self.title!r}, order={self.order})"
```

Then generate the schema migration:

```bash
docker compose exec backend python manage.py makemigrations application --name document_and_document_section
```

Verify the generated file is numbered `0020_document_and_document_section.py` and depends on `("application", "0019_main_goal_sequence_unique")` and on the `persistence` migration providing `Artifact`/`User`.

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec backend pytest application/tests/test_document_models.py -v`
Expected: PASS (2 models created, 3 sections persisted)

- [ ] **Step 5: Commit**

```bash
git add backend/application/models.py backend/application/migrations/0020_document_and_document_section.py backend/application/tests/test_document_models.py
git commit -m "feat: add Document and DocumentSection models"
```

---

## Task 2: RLS-Policies für die neuen Tabellen

**Files:**
- Create: `backend/application/migrations/0021_document_rls_policies.py`
- Test: `backend/application/tests/test_document_models.py` (erweitern)

**Interfaces:**
- Consumes: `as_document`, `as_document_section` (Task 1)
- Produces: RLS-Policies `as_document_tenant_isolation`, `as_document_section_tenant_isolation`

- [ ] **Step 1: Write the failing test**

Append to `backend/application/tests/test_document_models.py`:

```python
@pytest.mark.django_db
def test_rls_is_enabled_and_forced_on_document_tables():
    """REQ-L2-PL-010: both new tables must carry RLS + FORCE + a policy."""
    from django.db import connection

    with connection.cursor() as cur:
        cur.execute(
            """
            SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public'
              AND c.relname IN ('as_document', 'as_document_section')
            ORDER BY c.relname
            """
        )
        rows = cur.fetchall()

    assert rows == [
        ("as_document", True, True),
        ("as_document_section", True, True),
    ]

    with connection.cursor() as cur:
        cur.execute(
            "SELECT tablename, policyname FROM pg_policies "
            "WHERE tablename IN ('as_document', 'as_document_section') "
            "ORDER BY tablename"
        )
        policies = cur.fetchall()

    assert policies == [
        ("as_document", "as_document_tenant_isolation"),
        ("as_document_section", "as_document_section_tenant_isolation"),
    ]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend pytest application/tests/test_document_models.py::test_rls_is_enabled_and_forced_on_document_tables -v`
Expected: FAIL — `assert [('as_document', False, False), ('as_document_section', False, False)] == [...]`

- [ ] **Step 3: Write minimal implementation**

Create `backend/application/migrations/0021_document_rls_policies.py`:

```python
"""PostgreSQL Row-Level Security for as_document and as_document_section.

req_id: REQ-L2-PL-010, ADR-PL-03

Mirrors application/migrations/0009_risk_issue_rls_policies.py exactly: both
new tables carry a ``tenant_id`` column, which is all the policy needs. An
unset ``app.current_tenant`` matches no rows, satisfying REQ-L2-PL-010's
"direct DB access without the setting -> empty result" criterion.

No GRANT is needed: persistence/migrations/0048_app_role.py issued
ALTER DEFAULT PRIVILEGES for future tables in schema public.
"""
from __future__ import annotations

from django.db import migrations

_TENANT_TABLES = [
    "as_document",
    "as_document_section",
]


def _enable_sql() -> str:
    parts = []
    for table in _TENANT_TABLES:
        policy = f"{table}_tenant_isolation"
        parts.append(
            f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;\n"
            f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;\n"
            f"CREATE POLICY {policy} ON {table}\n"
            f"    USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)\n"
            f"    WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);"
        )
    return "\n".join(parts)


def _disable_sql() -> str:
    parts = []
    for table in _TENANT_TABLES:
        policy = f"{table}_tenant_isolation"
        parts.append(
            f"DROP POLICY IF EXISTS {policy} ON {table};\n"
            f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;\n"
            f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;"
        )
    return "\n".join(parts)


class Migration(migrations.Migration):

    dependencies = [
        ("application", "0020_document_and_document_section"),
        ("persistence", "0003_rls_policies"),
    ]

    operations = [
        migrations.RunSQL(sql=_enable_sql(), reverse_sql=_disable_sql()),
    ]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec backend pytest application/tests/test_document_models.py -v --create-db`
Expected: PASS (beide Tests; `--create-db` erzwingt einen frischen Migrationslauf)

- [ ] **Step 5: Commit**

```bash
git add backend/application/migrations/0021_document_rls_policies.py backend/application/tests/test_document_models.py
git commit -m "feat: enable RLS on as_document and as_document_section"
```

---

## Task 3: Geteilter Artefakt-Markdown-Renderer

**Files:**
- Create: `backend/application/artifact_markdown.py`
- Modify: `backend/application/export_service.py:439-451`
- Test: `backend/application/tests/test_artifact_markdown.py`

**Interfaces:**
- Consumes: nichts (reine Funktion)
- Produces: `application.artifact_markdown.render_artifact_markdown(row: dict[str, Any], heading_level: int = 2) -> str`

- [ ] **Step 1: Write the failing test**

Create `backend/application/tests/test_artifact_markdown.py`:

```python
"""Shared artifact-Markdown renderer (D2).

One renderer, three call sites: ExportService.export_markdown, the document
read mode, and (later) the MCP resources/read handler.
"""
from __future__ import annotations

from application.artifact_markdown import render_artifact_markdown


def test_renders_title_as_heading_description_as_body_and_rest_as_fields():
    row = {
        "id": "11111111-1111-1111-1111-111111111111",
        "title": "Bremsweg",
        "description": "Das System muss in 40 m stehen.",
        "priority": "high",
        "status": "Freigegeben",
    }

    out = render_artifact_markdown(row, heading_level=2)

    assert out.startswith("## Bremsweg\n")
    assert "Das System muss in 40 m stehen." in out
    assert "**priority:** high  " in out
    assert "**status:** Freigegeben  " in out
    # title/description must not be repeated in the field list
    assert "**title:**" not in out
    assert "**description:**" not in out


def test_heading_level_is_honoured_and_falsy_fields_are_skipped():
    row = {"id": "abc", "title": "T", "description": "", "note": None, "owner": "me"}

    out = render_artifact_markdown(row, heading_level=4)

    assert out.startswith("#### T\n")
    assert "**note:**" not in out
    assert "**owner:** me  " in out


def test_falls_back_to_id_when_title_is_missing():
    out = render_artifact_markdown({"id": "abc"}, heading_level=2)
    assert out.startswith("## abc\n")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend pytest application/tests/test_artifact_markdown.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'application.artifact_markdown'`

- [ ] **Step 3: Write minimal implementation**

Create `backend/application/artifact_markdown.py`:

```python
"""Shared artifact -> Markdown renderer.

Extracted verbatim from the per-row loop of ``ExportService.export_markdown``
so that the Markdown export, the document read mode (Dokument-Sicht spec,
section 4) and the MCP ``resources/read`` handler (MCP-Modernisierung spec,
section 4) all render an artifact identically.

Note for the MCP-Modernisierung implementation: the spec text names
``McpArtifactProvider`` as the source of this renderer. That class
(``diagram/mcp_artifact_provider.py``) is diagram-specific and renders only
diagram payloads — this module is the generic renderer it should consume.
"""
from __future__ import annotations

from typing import Any

__all__ = ["render_artifact_markdown"]


def render_artifact_markdown(
    row: dict[str, Any], heading_level: int = 2
) -> str:
    """Render one artifact row as a Markdown block.

    Args:
        row: Flat field mapping for a single artifact. ``title`` becomes the
            heading (falling back to ``id``, then the literal ``"Unknown"``),
            ``description`` becomes the body paragraph, every other truthy
            field becomes a bold definition line.
        heading_level: Number of leading ``#`` characters for the title,
            clamped to the Markdown-legal range 1..6 so a deeply nested
            document section cannot emit ``#######``.

    Returns:
        Markdown block ending in a single newline. Never ``None``.
    """
    level = min(6, max(1, int(heading_level)))
    hashes = "#" * level

    lines: list[str] = [
        f"{hashes} {row.get('title', row.get('id', 'Unknown'))}",
        "",
    ]
    if row.get("description"):
        lines.append(str(row["description"]))
        lines.append("")
    for key, value in row.items():
        if key not in ("title", "description") and value:
            lines.append(f"**{key}:** {value}  ")
    lines.append("")

    return "\n".join(lines)
```

Then replace the per-row loop in `backend/application/export_service.py`. The current block is:

```python
        for row in rows:
            lines.append(f"## {row.get('title', row.get('id', 'Unknown'))}")
            lines.append("")
            if row.get("description"):
                lines.append(row["description"])
                lines.append("")
            # remaining fields as definition list
            for k, v in row.items():
                if k not in ("title", "description") and v:
                    lines.append(f"**{k}:** {v}  ")
            lines.append("")
            lines.append("---")
            lines.append("")
```

Replace it with:

```python
        for row in rows:
            # D2: single shared renderer (application/artifact_markdown.py),
            # also used by the document read mode and MCP resources/read.
            lines.append(render_artifact_markdown(row, heading_level=2))
            lines.append("---")
            lines.append("")
```

and add to the local import block of `export_service.py`:

```python
from application.artifact_markdown import render_artifact_markdown
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec backend pytest application/tests/test_artifact_markdown.py application/tests/test_export_service.py -v`
Expected: PASS — the three new tests plus the full pre-existing export suite (proves the extraction is behaviour-preserving)

- [ ] **Step 5: Commit**

```bash
git add backend/application/artifact_markdown.py backend/application/export_service.py backend/application/tests/test_artifact_markdown.py
git commit -m "refactor: extract shared artifact markdown renderer from ExportService"
```

---

## Task 4: DocumentService — Dokument-CRUD

**Files:**
- Create: `backend/application/document_service.py`
- Test: `backend/application/tests/test_document_service.py`

**Interfaces:**
- Consumes: `application.models.Document` (Task 1), `application.base.ServiceBase`, `auth_tenancy` `AuthContext`
- Produces: `DocumentService.create_document(ctx, workspace_id, title) -> Document`, `.get_document(ctx, document_id) -> Document`, `.list_documents(ctx, workspace_id) -> list[Document]`, `.update_document(ctx, document_id, title=None) -> Document`, `.delete_document(ctx, document_id) -> None`

- [ ] **Step 1: Write the failing test**

Create `backend/application/tests/test_document_service.py`:

```python
"""DocumentService CRUD contract (Dokument-Sicht spec, section 7)."""
from __future__ import annotations

import uuid

import pytest

from application.document_service import DocumentService
from application.exceptions import NotFoundError, ValidationError


@pytest.fixture
def svc():
    return DocumentService()


@pytest.mark.django_db
def test_create_get_list_update_delete_roundtrip(svc, admin_ctx, workspace):
    doc = svc.create_document(admin_ctx, workspace.id, "Lastenheft")
    assert doc.title == "Lastenheft"
    assert doc.workspace_id == workspace.id
    assert doc.tenant_id == admin_ctx.tenant_id

    assert svc.get_document(admin_ctx, doc.id).id == doc.id
    assert [d.id for d in svc.list_documents(admin_ctx, workspace.id)] == [doc.id]

    updated = svc.update_document(admin_ctx, doc.id, title="Pflichtenheft")
    assert updated.title == "Pflichtenheft"

    svc.delete_document(admin_ctx, doc.id)
    with pytest.raises(NotFoundError):
        svc.get_document(admin_ctx, doc.id)


@pytest.mark.django_db
def test_blank_title_is_rejected(svc, admin_ctx, workspace):
    with pytest.raises(ValidationError):
        svc.create_document(admin_ctx, workspace.id, "   ")


@pytest.mark.django_db
def test_unknown_document_raises_not_found(svc, admin_ctx):
    with pytest.raises(NotFoundError):
        svc.get_document(admin_ctx, uuid.uuid4())
```

Note: `admin_ctx` and `workspace` are existing fixtures in `backend/application/tests/conftest.py`. Confirm their exact names with
`grep -n "^def admin_ctx\|^def workspace" backend/application/tests/conftest.py` before running; adapt the fixture names in this test if they differ.

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend pytest application/tests/test_document_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'application.document_service'`

- [ ] **Step 3: Write minimal implementation**

Create `backend/application/document_service.py`:

```python
"""COMP-AS-DOC: Document / DocumentSection domain service (Layer 2).

Single entry point for the living-specification document feature (ADR-01).
REST views and MCP tool handlers must go through this class rather than
touching ``application.models.Document`` directly.
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from application.base import ServiceBase
from application.exceptions import NotFoundError, ValidationError
from application.models import Document
from persistence.transactions import atomic_transaction

__all__ = ["DocumentService"]


class DocumentService(ServiceBase):
    """CRUD for :class:`application.models.Document`."""

    # ---------- Documents ----------

    @atomic_transaction
    def create_document(self, ctx, workspace_id: UUID | str, title: str) -> Document:
        """Create a document in *workspace_id*.

        Raises:
            ValidationError: ``title`` is blank.
            PermissionDeniedError: Caller has no write permission.
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)
        clean_title = (title or "").strip()
        if not clean_title:
            raise ValidationError("Document title must not be empty.")
        return Document.objects.create(
            tenant_id=ctx.tenant_id,
            workspace_id=UUID(str(workspace_id)),
            title=clean_title,
            created_by_id=ctx.user_id,
        )

    def get_document(self, ctx, document_id: UUID | str) -> Document:
        """Return one document, or raise :class:`NotFoundError`."""
        self._set_tenant_context(ctx)
        try:
            return Document.objects.get(
                id=UUID(str(document_id)), tenant_id=ctx.tenant_id
            )
        except Document.DoesNotExist as exc:
            raise NotFoundError(f"Document {document_id} not found.") from exc

    def list_documents(self, ctx, workspace_id: UUID | str) -> list[Document]:
        """Return all documents of *workspace_id*, newest last."""
        self._set_tenant_context(ctx)
        return list(
            Document.objects.filter(
                tenant_id=ctx.tenant_id, workspace_id=UUID(str(workspace_id))
            ).order_by("created_at", "id")
        )

    @atomic_transaction
    def update_document(
        self, ctx, document_id: UUID | str, title: Optional[str] = None
    ) -> Document:
        """Update a document's title."""
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)
        doc = self.get_document(ctx, document_id)
        if title is not None:
            clean_title = title.strip()
            if not clean_title:
                raise ValidationError("Document title must not be empty.")
            doc.title = clean_title
        doc.save()
        return doc

    @atomic_transaction
    def delete_document(self, ctx, document_id: UUID | str) -> None:
        """Hard-delete a document; sections cascade."""
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)
        self.get_document(ctx, document_id).delete()
```

Before running, confirm the exact import paths with
`grep -n "class NotFoundError\|class ValidationError" backend/application/exceptions.py` and
`grep -n "def atomic_transaction" backend/persistence/transactions.py`; adjust the two imports if the module layout differs.

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec backend pytest application/tests/test_document_service.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/application/document_service.py backend/application/tests/test_document_service.py
git commit -m "feat: add DocumentService with document CRUD"
```

---

## Task 5: Sektions-CRUD mit Zyklus-Prüfung

**Files:**
- Modify: `backend/application/document_service.py`
- Test: `backend/application/tests/test_document_service.py`

**Interfaces:**
- Consumes: `DocumentService.get_document` (Task 4), `application.models.DocumentSection` (Task 1)
- Produces: `DocumentService.create_section(ctx, document_id, title, content_type, order=0, parent_section_id=None, query=None, fixed_artifact_ids=None, subtree_root_artifact_id=None) -> DocumentSection`, `.list_sections(ctx, document_id) -> list[DocumentSection]`, `.update_section(ctx, section_id, **fields) -> DocumentSection`, `.delete_section(ctx, section_id) -> None`, `.reorder_sections(ctx, document_id, ordered_section_ids) -> list[DocumentSection]`

- [ ] **Step 1: Write the failing test**

Append to `backend/application/tests/test_document_service.py`:

```python
from application.models import DocumentSection


@pytest.mark.django_db
def test_section_crud_and_reorder(svc, admin_ctx, workspace):
    doc = svc.create_document(admin_ctx, workspace.id, "Doc")
    a = svc.create_section(
        admin_ctx, doc.id, "A", DocumentSection.CONTENT_TYPE_FIXED, order=0
    )
    b = svc.create_section(
        admin_ctx, doc.id, "B", DocumentSection.CONTENT_TYPE_FIXED, order=1
    )

    assert [s.id for s in svc.list_sections(admin_ctx, doc.id)] == [a.id, b.id]

    svc.reorder_sections(admin_ctx, doc.id, [b.id, a.id])
    assert [s.id for s in svc.list_sections(admin_ctx, doc.id)] == [b.id, a.id]

    renamed = svc.update_section(admin_ctx, a.id, title="A2")
    assert renamed.title == "A2"

    svc.delete_section(admin_ctx, a.id)
    assert [s.id for s in svc.list_sections(admin_ctx, doc.id)] == [b.id]


@pytest.mark.django_db
def test_self_parent_is_rejected_as_cycle(svc, admin_ctx, workspace):
    doc = svc.create_document(admin_ctx, workspace.id, "Doc")
    a = svc.create_section(
        admin_ctx, doc.id, "A", DocumentSection.CONTENT_TYPE_FIXED
    )
    with pytest.raises(ValidationError, match="Cycle detected"):
        svc.update_section(admin_ctx, a.id, parent_section_id=a.id)


@pytest.mark.django_db
def test_indirect_cycle_is_rejected(svc, admin_ctx, workspace):
    """A -> B -> C, then C as parent of A closes the loop."""
    doc = svc.create_document(admin_ctx, workspace.id, "Doc")
    a = svc.create_section(admin_ctx, doc.id, "A", DocumentSection.CONTENT_TYPE_FIXED)
    b = svc.create_section(
        admin_ctx, doc.id, "B", DocumentSection.CONTENT_TYPE_FIXED,
        parent_section_id=a.id,
    )
    c = svc.create_section(
        admin_ctx, doc.id, "C", DocumentSection.CONTENT_TYPE_FIXED,
        parent_section_id=b.id,
    )
    with pytest.raises(ValidationError, match="Cycle detected"):
        svc.update_section(admin_ctx, a.id, parent_section_id=c.id)


@pytest.mark.django_db
def test_unknown_content_type_is_rejected(svc, admin_ctx, workspace):
    doc = svc.create_document(admin_ctx, workspace.id, "Doc")
    with pytest.raises(ValidationError):
        svc.create_section(admin_ctx, doc.id, "X", "spreadsheet")


@pytest.mark.django_db
def test_parent_section_from_another_document_is_rejected(svc, admin_ctx, workspace):
    doc_a = svc.create_document(admin_ctx, workspace.id, "A")
    doc_b = svc.create_document(admin_ctx, workspace.id, "B")
    foreign = svc.create_section(
        admin_ctx, doc_b.id, "foreign", DocumentSection.CONTENT_TYPE_FIXED
    )
    with pytest.raises(ValidationError):
        svc.create_section(
            admin_ctx, doc_a.id, "X", DocumentSection.CONTENT_TYPE_FIXED,
            parent_section_id=foreign.id,
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend pytest application/tests/test_document_service.py -v -k section or cycle`
Expected: FAIL with `AttributeError: 'DocumentService' object has no attribute 'create_section'`

- [ ] **Step 3: Write minimal implementation**

Append to `backend/application/document_service.py` (and extend the model import to `from application.models import Document, DocumentSection`):

```python
    # ---------- Sections ----------

    def _get_section(self, ctx, section_id: UUID | str) -> DocumentSection:
        try:
            return DocumentSection.objects.get(
                id=UUID(str(section_id)), tenant_id=ctx.tenant_id
            )
        except DocumentSection.DoesNotExist as exc:
            raise NotFoundError(f"DocumentSection {section_id} not found.") from exc

    @staticmethod
    def _assert_no_cycle(section: DocumentSection, parent: DocumentSection) -> None:
        """Raise ValidationError if making *parent* the parent of *section* loops.

        DFS up the parent chain before persistence (D4), mirroring
        ADR-L3-AS001-01. The visited set also terminates on pre-existing
        corrupt data instead of spinning forever.
        """
        if parent.id == section.id:
            raise ValidationError(
                f"Cycle detected: section {section.id} cannot be its own parent."
            )
        seen: set = {section.id}
        cursor: Optional[DocumentSection] = parent
        while cursor is not None:
            if cursor.id in seen:
                raise ValidationError(
                    f"Cycle detected in document section hierarchy at {cursor.id}."
                )
            seen.add(cursor.id)
            cursor = cursor.parent_section

    def _resolve_parent(
        self, ctx, document_id: UUID, parent_section_id: Optional[UUID | str]
    ) -> Optional[DocumentSection]:
        if parent_section_id is None:
            return None
        parent = self._get_section(ctx, parent_section_id)
        if parent.document_id != document_id:
            raise ValidationError(
                "parent_section must belong to the same document."
            )
        return parent

    @atomic_transaction
    def create_section(
        self,
        ctx,
        document_id: UUID | str,
        title: str,
        content_type: str,
        order: int = 0,
        parent_section_id: Optional[UUID | str] = None,
        query: Optional[dict] = None,
        fixed_artifact_ids: Optional[list] = None,
        subtree_root_artifact_id: Optional[UUID | str] = None,
    ) -> DocumentSection:
        """Create one chapter of a document."""
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)
        doc = self.get_document(ctx, document_id)

        valid = {c[0] for c in DocumentSection.CONTENT_TYPE_CHOICES}
        if content_type not in valid:
            raise ValidationError(
                f"content_type must be one of {sorted(valid)}, got {content_type!r}."
            )
        clean_title = (title or "").strip()
        if not clean_title:
            raise ValidationError("Section title must not be empty.")

        parent = self._resolve_parent(ctx, doc.id, parent_section_id)

        return DocumentSection.objects.create(
            tenant_id=ctx.tenant_id,
            document=doc,
            parent_section=parent,
            title=clean_title,
            order=int(order),
            content_type=content_type,
            query=query,
            fixed_artifact_ids=list(fixed_artifact_ids or []),
            subtree_root_artifact_id=(
                UUID(str(subtree_root_artifact_id))
                if subtree_root_artifact_id is not None
                else None
            ),
        )

    def list_sections(self, ctx, document_id: UUID | str) -> list[DocumentSection]:
        """Return all sections of a document in ``(order, id)`` order."""
        self._set_tenant_context(ctx)
        doc = self.get_document(ctx, document_id)
        return list(
            DocumentSection.objects.filter(
                document_id=doc.id, tenant_id=ctx.tenant_id
            ).order_by("order", "id")
        )

    @atomic_transaction
    def update_section(self, ctx, section_id: UUID | str, **fields) -> DocumentSection:
        """Update mutable section fields.

        Accepts ``title``, ``order``, ``content_type``, ``query``,
        ``fixed_artifact_ids``, ``subtree_root_artifact_id`` and
        ``parent_section_id``. Unknown keys are rejected so a typo cannot be
        silently dropped.
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)
        section = self._get_section(ctx, section_id)

        allowed = {
            "title", "order", "content_type", "query",
            "fixed_artifact_ids", "subtree_root_artifact_id", "parent_section_id",
        }
        unknown = set(fields) - allowed
        if unknown:
            raise ValidationError(f"Unknown section fields: {sorted(unknown)}.")

        if "content_type" in fields:
            valid = {c[0] for c in DocumentSection.CONTENT_TYPE_CHOICES}
            if fields["content_type"] not in valid:
                raise ValidationError(
                    f"content_type must be one of {sorted(valid)}."
                )
            section.content_type = fields["content_type"]
        if "title" in fields:
            clean_title = (fields["title"] or "").strip()
            if not clean_title:
                raise ValidationError("Section title must not be empty.")
            section.title = clean_title
        if "order" in fields:
            section.order = int(fields["order"])
        if "query" in fields:
            section.query = fields["query"]
        if "fixed_artifact_ids" in fields:
            section.fixed_artifact_ids = list(fields["fixed_artifact_ids"] or [])
        if "subtree_root_artifact_id" in fields:
            raw = fields["subtree_root_artifact_id"]
            section.subtree_root_artifact_id = (
                UUID(str(raw)) if raw is not None else None
            )
        if "parent_section_id" in fields:
            parent = self._resolve_parent(
                ctx, section.document_id, fields["parent_section_id"]
            )
            if parent is not None:
                self._assert_no_cycle(section, parent)
            section.parent_section = parent

        section.save()
        return section

    @atomic_transaction
    def delete_section(self, ctx, section_id: UUID | str) -> None:
        """Delete a section; child sections cascade."""
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)
        self._get_section(ctx, section_id).delete()

    @atomic_transaction
    def reorder_sections(
        self, ctx, document_id: UUID | str, ordered_section_ids: list
    ) -> list[DocumentSection]:
        """Rewrite ``order`` to match the position in *ordered_section_ids*.

        Every id must belong to *document_id*; the list need not be complete
        (sections not named keep their current ``order``).
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)
        doc = self.get_document(ctx, document_id)
        for position, raw_id in enumerate(ordered_section_ids):
            section = self._get_section(ctx, raw_id)
            if section.document_id != doc.id:
                raise ValidationError(
                    f"Section {raw_id} does not belong to document {doc.id}."
                )
            section.order = position
            section.save(update_fields=["order"])
        return self.list_sections(ctx, doc.id)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec backend pytest application/tests/test_document_service.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/application/document_service.py backend/application/tests/test_document_service.py
git commit -m "feat: add document section CRUD with cycle detection"
```

---

## Task 6: Filter-DSL-Adapter für query-Sektionen

**Files:**
- Create: `backend/application/document_query_adapter.py`
- Test: `backend/application/tests/test_document_read.py`

**Interfaces:**
- Consumes: die Filter-DSL aus der Tabellenansicht-Spec, Abschnitt 4.1 (siehe OFFENE FRAGE 1)
- Produces: `application.document_query_adapter.run_artifact_query(ctx, workspace_id: UUID, query: dict | None) -> list[dict]` — liefert flache Feld-Dicts in Sortierreihenfolge, jedes mit mindestens `id` und `title`

**Vor dem Start prüfen:** `ls backend/application/ | grep -i "artifact_query\|table_view\|saved_view"` — existiert die Tabellenansicht-Implementierung schon, wird der Adapter direkt gegen sie verdrahtet, andernfalls gegen den unten gezeigten Fallback über `ExportService._fetch_entities`.

- [ ] **Step 1: Write the failing test**

Create `backend/application/tests/test_document_read.py`:

```python
"""query-section resolution via the shared Filter-DSL adapter (D6)."""
from __future__ import annotations

import uuid

import pytest

from application.document_query_adapter import run_artifact_query


@pytest.mark.django_db
def test_empty_query_returns_empty_list(admin_ctx, workspace):
    assert run_artifact_query(admin_ctx, workspace.id, None) == []
    assert run_artifact_query(admin_ctx, workspace.id, {}) == []


@pytest.mark.django_db
def test_query_returns_rows_with_id_and_title(admin_ctx, workspace, requirement):
    rows = run_artifact_query(
        admin_ctx,
        workspace.id,
        {"item_type": "Requirement", "filters": {}, "sort": []},
    )
    assert rows, "seeded requirement must be visible to an unfiltered query"
    assert all("id" in r and "title" in r for r in rows)
    assert str(requirement.id) in {str(r["id"]) for r in rows}


@pytest.mark.django_db
def test_sort_is_applied_in_declared_order(admin_ctx, workspace, requirement):
    asc = run_artifact_query(
        admin_ctx,
        workspace.id,
        {
            "item_type": "Requirement",
            "filters": {},
            "sort": [{"field": "title", "dir": "asc"}],
        },
    )
    desc = run_artifact_query(
        admin_ctx,
        workspace.id,
        {
            "item_type": "Requirement",
            "filters": {},
            "sort": [{"field": "title", "dir": "desc"}],
        },
    )
    assert [r["id"] for r in asc] == list(reversed([r["id"] for r in desc]))


@pytest.mark.django_db
def test_unknown_item_type_returns_empty_not_error(admin_ctx, workspace):
    """Fail-soft: a stale section must render as an empty chapter, not a 500."""
    assert run_artifact_query(
        admin_ctx, workspace.id, {"item_type": "Nonexistent", "filters": {}}
    ) == []
```

`requirement` is an existing fixture; confirm with `grep -rn "^def requirement" backend/application/tests/conftest.py` and adapt if needed.

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend pytest application/tests/test_document_read.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'application.document_query_adapter'`

- [ ] **Step 3: Write minimal implementation**

Create `backend/application/document_query_adapter.py`:

```python
"""Single seam between DocumentSection.query and the Filter-DSL (D6).

``DocumentSection.query`` carries exactly the DSL defined by the
Tabellenansicht spec, section 4.1::

    {"item_type": "Requirement",
     "filters": {"priority": {"op": "in", "value": ["high"]}},
     "sort": [{"field": "title", "dir": "asc"}]}

Only this module knows how that DSL is executed. When the Tabellenansicht
implementation lands with a differently named service entry point, this file
is the only one that changes (see OFFENE FRAGE 1 in the plan).

Fail-soft by design: a stale section (unknown item_type, filter on a removed
field) renders as an empty chapter rather than breaking the whole document —
the same fail-soft posture the Tabellenansicht spec prescribes for a broken
SavedView.
"""
from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID

logger = logging.getLogger(__name__)

__all__ = ["run_artifact_query"]

_SORT_DIRECTIONS = {"asc", "desc"}


def _apply_sort(rows: list[dict[str, Any]], sort: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Apply multi-key sorting, least-significant key first (stable sort).

    Rows missing the sort field sort as the empty string so a partially
    populated field cannot raise a TypeError mid-render.
    """
    for spec in reversed(sort or []):
        field = spec.get("field")
        if not field:
            continue
        direction = spec.get("dir", "asc")
        if direction not in _SORT_DIRECTIONS:
            continue
        rows.sort(
            key=lambda r, f=field: ("" if r.get(f) is None else str(r.get(f))),
            reverse=(direction == "desc"),
        )
    return rows


def run_artifact_query(
    ctx, workspace_id: UUID | str, query: Optional[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Resolve a ``content_type="query"`` section to an ordered row list.

    Args:
        ctx: AuthContext of the reading caller.
        workspace_id: Workspace the document belongs to.
        query: The Filter-DSL object, or ``None``/``{}`` for "nothing".

    Returns:
        Flat field mappings in sort order, each carrying at least ``id`` and
        ``title``. Empty list on any resolution problem (fail-soft).
    """
    if not query:
        return []
    item_type = query.get("item_type")
    if not item_type:
        return []

    try:
        # Fallback path: the same read layer ExportService uses. Replace the
        # two lines below with the Tabellenansicht service entry point once it
        # exists — nothing outside this function needs to change.
        from application.export_service import ExportService

        service = ExportService()
        service._set_tenant_context(ctx)
        rows = service._fetch_entities(item_type, UUID(str(workspace_id)), None)
    except Exception:
        logger.warning(
            "Document query section could not be resolved (item_type=%r); "
            "rendering an empty chapter.",
            item_type,
            exc_info=True,
        )
        return []

    filters = query.get("filters") or {}
    if filters:
        rows = _apply_filters(rows, filters)

    return _apply_sort(list(rows), query.get("sort") or [])


def _apply_filters(
    rows: list[dict[str, Any]], filters: dict[str, Any]
) -> list[dict[str, Any]]:
    """Apply the type-aware operator set from the Tabellenansicht DSL.

    Operators per spec section 4.1: ``contains`` (text), ``in`` (enum,
    reference, user, status), ``gte``/``lte`` (number, date), ``eq``
    (boolean). An unknown operator drops the whole filter clause rather than
    the whole section (fail-soft).
    """
    out = rows
    for field, clause in filters.items():
        if not isinstance(clause, dict):
            continue
        op = clause.get("op")
        value = clause.get("value")
        if op == "contains":
            needle = str(value).casefold()
            out = [r for r in out if needle in str(r.get(field, "")).casefold()]
        elif op == "in":
            wanted = {str(v) for v in (value or [])}
            out = [r for r in out if str(r.get(field)) in wanted]
        elif op == "gte":
            out = [r for r in out if _cmp_ok(r.get(field), value, ">=")]
        elif op == "lte":
            out = [r for r in out if _cmp_ok(r.get(field), value, "<=")]
        elif op == "eq":
            out = [r for r in out if r.get(field) == value]
        else:
            logger.warning("Unknown filter operator %r on field %r; ignored.", op, field)
    return out


def _cmp_ok(left: Any, right: Any, op: str) -> bool:
    """Compare two values, falling back to string comparison.

    Returns ``False`` when either side is missing so a null field never
    satisfies a range filter.
    """
    if left is None or right is None:
        return False
    try:
        a, b = (left, right) if type(left) is type(right) else (str(left), str(right))
        return a >= b if op == ">=" else a <= b
    except TypeError:
        return False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec backend pytest application/tests/test_document_read.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/application/document_query_adapter.py backend/application/tests/test_document_read.py
git commit -m "feat: add filter-DSL adapter for document query sections"
```

---

## Task 7: Sektions-Auflösung — query, fixed und subtree zu Artefakt-IDs

**Files:**
- Modify: `backend/application/document_service.py`
- Test: `backend/application/tests/test_document_read.py`

**Interfaces:**
- Consumes: `run_artifact_query` (Task 6), `baseline.services.resolve_scope_item_ids` (bestehend, `backend/baseline/services.py:307`)
- Produces: `DocumentService.resolve_section_rows(ctx, section) -> list[dict]`, `DocumentService.resolve_document_artifact_ids(ctx, document_id) -> list[str]` (dedupliziert, dokumentreihenfolge-stabil)

- [ ] **Step 1: Write the failing test**

Append to `backend/application/tests/test_document_read.py`:

```python
from application.document_service import DocumentService
from application.models import DocumentSection


@pytest.fixture
def doc_svc():
    return DocumentService()


@pytest.mark.django_db
def test_fixed_section_preserves_the_curated_order(
    doc_svc, admin_ctx, workspace, requirement, second_requirement
):
    doc = doc_svc.create_document(admin_ctx, workspace.id, "Doc")
    section = doc_svc.create_section(
        admin_ctx, doc.id, "Kuratiert", DocumentSection.CONTENT_TYPE_FIXED,
        fixed_artifact_ids=[str(second_requirement.id), str(requirement.id)],
    )
    rows = doc_svc.resolve_section_rows(admin_ctx, section)
    assert [str(r["id"]) for r in rows] == [
        str(second_requirement.id),
        str(requirement.id),
    ]


@pytest.mark.django_db
def test_subtree_section_uses_the_baseline_scope_resolver(
    doc_svc, admin_ctx, workspace, requirement
):
    doc = doc_svc.create_document(admin_ctx, workspace.id, "Doc")
    section = doc_svc.create_section(
        admin_ctx, doc.id, "Teilbaum", DocumentSection.CONTENT_TYPE_SUBTREE,
        subtree_root_artifact_id=requirement.artifact_id,
    )
    rows = doc_svc.resolve_section_rows(admin_ctx, section)
    assert str(requirement.artifact_id) in {str(r["id"]) for r in rows}


@pytest.mark.django_db
def test_subtree_section_without_root_is_empty(doc_svc, admin_ctx, workspace):
    doc = doc_svc.create_document(admin_ctx, workspace.id, "Doc")
    section = doc_svc.create_section(
        admin_ctx, doc.id, "Leer", DocumentSection.CONTENT_TYPE_SUBTREE
    )
    assert doc_svc.resolve_section_rows(admin_ctx, section) == []


@pytest.mark.django_db
def test_document_artifact_ids_are_deduplicated_across_sections(
    doc_svc, admin_ctx, workspace, requirement
):
    doc = doc_svc.create_document(admin_ctx, workspace.id, "Doc")
    doc_svc.create_section(
        admin_ctx, doc.id, "A", DocumentSection.CONTENT_TYPE_FIXED, order=0,
        fixed_artifact_ids=[str(requirement.artifact_id)],
    )
    doc_svc.create_section(
        admin_ctx, doc.id, "B", DocumentSection.CONTENT_TYPE_FIXED, order=1,
        fixed_artifact_ids=[str(requirement.artifact_id)],
    )
    ids = doc_svc.resolve_document_artifact_ids(admin_ctx, doc.id)
    assert ids.count(str(requirement.artifact_id)) == 1
```

`second_requirement` may not exist as a fixture. If `grep -rn "second_requirement" backend/application/tests/conftest.py` finds nothing, add it there as a second requirement in the same workspace with a title sorting after the first.

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend pytest application/tests/test_document_read.py -v -k "fixed_section or subtree or deduplicated"`
Expected: FAIL with `AttributeError: 'DocumentService' object has no attribute 'resolve_section_rows'`

- [ ] **Step 3: Write minimal implementation**

Append to `backend/application/document_service.py`:

```python
    # ---------- Section resolution ----------

    def resolve_section_rows(self, ctx, section: DocumentSection) -> list[dict]:
        """Resolve one section to an ordered list of artifact field mappings.

        Three content types, three reuses (spec section 3):
          * ``query``   — the Filter-DSL from the Tabellenansicht spec.
          * ``fixed``   — the curated id list, in exactly its stored order.
          * ``subtree`` — today's baseline document-scope resolver.
        """
        self._set_tenant_context(ctx)

        if section.content_type == DocumentSection.CONTENT_TYPE_QUERY:
            from application.document_query_adapter import run_artifact_query

            doc = self.get_document(ctx, section.document_id)
            return run_artifact_query(ctx, doc.workspace_id, section.query)

        if section.content_type == DocumentSection.CONTENT_TYPE_FIXED:
            return self._load_rows_in_order(
                ctx, [str(i) for i in (section.fixed_artifact_ids or [])]
            )

        if section.content_type == DocumentSection.CONTENT_TYPE_SUBTREE:
            if section.subtree_root_artifact_id is None:
                return []
            from baseline.services import resolve_scope_item_ids

            doc = self.get_document(ctx, section.document_id)
            ids = resolve_scope_item_ids(
                scope="document",
                workspace_id=doc.workspace_id,
                tenant_id=ctx.tenant_id,
                artifact_id=section.subtree_root_artifact_id,
            )
            return self._load_rows_in_order(ctx, [str(i) for i in ids])

        return []

    @staticmethod
    def _load_rows_in_order(ctx, artifact_ids: list[str]) -> list[dict]:
        """Load artifact rows for *artifact_ids*, preserving the given order.

        One query for the whole batch (no N+1); ids that resolve to nothing
        are skipped rather than rendered as empty chapters.
        """
        if not artifact_ids:
            return []
        from persistence.models import Artifact

        by_id = {
            str(a.id): a
            for a in Artifact.objects.filter(
                id__in=artifact_ids, tenant_id=ctx.tenant_id
            )
        }
        rows: list[dict] = []
        for raw_id in artifact_ids:
            artifact = by_id.get(raw_id)
            if artifact is None:
                continue
            row: dict = {
                "id": str(artifact.id),
                "title": getattr(artifact, "title", "") or str(artifact.id),
                "artifact_type": artifact.artifact_type,
            }
            custom = artifact.custom_fields or {}
            if isinstance(custom, dict):
                row.update(custom)
            rows.append(row)
        return rows

    def resolve_document_artifact_ids(self, ctx, document_id: UUID | str) -> list[str]:
        """Return every artifact id in the document, deduplicated, in read order.

        This is the membership set a ``scope="document"`` baseline bound to
        this document snapshots (Task 8).
        """
        self._set_tenant_context(ctx)
        ordered: list[str] = []
        seen: set[str] = set()
        for section in self.list_sections(ctx, document_id):
            for row in self.resolve_section_rows(ctx, section):
                raw_id = str(row["id"])
                if raw_id not in seen:
                    seen.add(raw_id)
                    ordered.append(raw_id)
        return ordered
```

Note: `Artifact` has no guaranteed `title` column — confirm with
`grep -n "title" backend/persistence/models.py | sed -n '1,20p'`. If the title lives on the type-specific row rather than on `Artifact`, extend `_load_rows_in_order` to left-join the same way `baseline.services._load_sample_items` already does, and reuse that helper instead of writing a second one.

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec backend pytest application/tests/test_document_read.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/application/document_service.py backend/application/tests/test_document_read.py
git commit -m "feat: resolve document sections to ordered artifact rows"
```

---

## Task 8: Lesemodus mit hierarchischer Nummerierung

**Files:**
- Modify: `backend/application/document_service.py`
- Test: `backend/application/tests/test_document_read.py`

**Interfaces:**
- Consumes: `render_artifact_markdown` (Task 3), `resolve_section_rows` (Task 7)
- Produces: `DocumentService.read_document(ctx, document_id) -> str` (nummeriertes Markdown)

- [ ] **Step 1: Write the failing test**

Append to `backend/application/tests/test_document_read.py`:

```python
@pytest.mark.django_db
def test_read_document_numbers_sections_and_artifacts_hierarchically(
    doc_svc, admin_ctx, workspace, requirement
):
    """D3: within a section, artifacts come first, then child sections,
    sharing one counter."""
    doc = doc_svc.create_document(admin_ctx, workspace.id, "Lastenheft")
    top = doc_svc.create_section(
        admin_ctx, doc.id, "Allgemeines", DocumentSection.CONTENT_TYPE_FIXED,
        order=0, fixed_artifact_ids=[str(requirement.artifact_id)],
    )
    doc_svc.create_section(
        admin_ctx, doc.id, "Details", DocumentSection.CONTENT_TYPE_FIXED,
        order=0, parent_section_id=top.id,
    )
    doc_svc.create_section(
        admin_ctx, doc.id, "Anhang", DocumentSection.CONTENT_TYPE_FIXED, order=1
    )

    md = doc_svc.read_document(admin_ctx, doc.id)

    assert md.startswith("# Lastenheft\n")
    assert "## 1 Allgemeines" in md
    # the artifact inside section 1 is numbered before the child section
    assert "### 1.1 " in md
    assert "### 1.2 Details" in md
    assert "## 2 Anhang" in md


@pytest.mark.django_db
def test_read_document_of_empty_document_is_just_the_title(
    doc_svc, admin_ctx, workspace
):
    doc = doc_svc.create_document(admin_ctx, workspace.id, "Leer")
    md = doc_svc.read_document(admin_ctx, doc.id)
    assert md.strip() == "# Leer"


@pytest.mark.django_db
def test_read_document_is_deterministic_across_two_calls(
    doc_svc, admin_ctx, workspace, requirement
):
    doc = doc_svc.create_document(admin_ctx, workspace.id, "D")
    doc_svc.create_section(
        admin_ctx, doc.id, "S", DocumentSection.CONTENT_TYPE_FIXED,
        fixed_artifact_ids=[str(requirement.artifact_id)],
    )
    assert doc_svc.read_document(admin_ctx, doc.id) == doc_svc.read_document(
        admin_ctx, doc.id
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend pytest application/tests/test_document_read.py -v -k read_document`
Expected: FAIL with `AttributeError: 'DocumentService' object has no attribute 'read_document'`

- [ ] **Step 3: Write minimal implementation**

Append to `backend/application/document_service.py`:

```python
    # ---------- Read mode ----------

    def read_document(self, ctx, document_id: UUID | str) -> str:
        """Render the whole document as numbered Markdown (spec section 4).

        Numbering is hierarchical over sections and artifacts (1, 1.1, 1.2,
        2, ...). Within one section, artifacts are numbered first and child
        sections continue the same counter (D3), which is the classical
        Lastenheft reading order: content before subdivision.

        Query sections are evaluated **at read time** — two calls may differ
        if the underlying data changed (spec risk 1). A frozen view is what
        the baseline binding is for.
        """
        self._set_tenant_context(ctx)
        doc = self.get_document(ctx, document_id)

        sections = self.list_sections(ctx, doc.id)
        by_parent: dict = {}
        for section in sections:
            by_parent.setdefault(section.parent_section_id, []).append(section)
        for bucket in by_parent.values():
            bucket.sort(key=lambda s: (s.order, str(s.id)))

        lines: list[str] = [f"# {doc.title}", ""]
        self._render_sections(ctx, by_parent, None, prefix=(), lines=lines)
        return "\n".join(lines).rstrip() + "\n"

    def _render_sections(
        self, ctx, by_parent: dict, parent_id, prefix: tuple, lines: list
    ) -> None:
        """Depth-first render of one sibling level.

        ``prefix`` is the numbering path of the parent, e.g. ``(1, 2)`` for
        section 1.2; heading depth is ``len(prefix) + 2`` because ``#`` is
        the document title.
        """
        from application.artifact_markdown import render_artifact_markdown

        for index, section in enumerate(by_parent.get(parent_id, []), start=1):
            number = prefix + (index,)
            label = ".".join(str(n) for n in number)
            heading = "#" * min(6, len(number) + 1)
            lines.append(f"{heading} {label} {section.title}")
            lines.append("")

            # D3: one shared counter — artifacts first, then child sections.
            counter = 0
            for row in self.resolve_section_rows(ctx, section):
                counter += 1
                artifact_label = f"{label}.{counter}"
                block = render_artifact_markdown(
                    row, heading_level=min(6, len(number) + 2)
                )
                head, _, rest = block.partition("\n")
                hashes, _, title = head.partition(" ")
                lines.append(f"{hashes} {artifact_label} {title}")
                if rest:
                    lines.append(rest.rstrip())
                lines.append("")

            children = by_parent.get(section.id, [])
            if children:
                self._render_sections(
                    ctx,
                    {**by_parent, section.id: children},
                    section.id,
                    prefix=number + (counter,) if False else number,
                    lines=lines,
                )
```

The `prefix=` expression above is deliberately simple: child sections continue the counter, so pass the running counter down. Replace the last call with:

```python
            children = by_parent.get(section.id, [])
            if children:
                self._render_child_sections(
                    ctx, by_parent, section.id, number, counter, lines
                )
```

and add:

```python
    def _render_child_sections(
        self, ctx, by_parent: dict, parent_id, number: tuple, offset: int, lines: list
    ) -> None:
        """Render child sections continuing the parent's artifact counter (D3)."""
        from application.artifact_markdown import render_artifact_markdown

        for index, section in enumerate(by_parent.get(parent_id, []), start=1):
            child_number = number + (offset + index,)
            label = ".".join(str(n) for n in child_number)
            heading = "#" * min(6, len(child_number) + 1)
            lines.append(f"{heading} {label} {section.title}")
            lines.append("")

            counter = 0
            for row in self.resolve_section_rows(ctx, section):
                counter += 1
                block = render_artifact_markdown(
                    row, heading_level=min(6, len(child_number) + 2)
                )
                head, _, rest = block.partition("\n")
                hashes, _, title = head.partition(" ")
                lines.append(f"{hashes} {label}.{counter} {title}")
                if rest:
                    lines.append(rest.rstrip())
                lines.append("")

            if by_parent.get(section.id):
                self._render_child_sections(
                    ctx, by_parent, section.id, child_number, counter, lines
                )
```

Finally simplify `_render_sections` to delegate to the same helper for its own children, so only one recursion body exists:

```python
    def _render_sections(
        self, ctx, by_parent: dict, parent_id, prefix: tuple, lines: list
    ) -> None:
        """Render the top level; children go through _render_child_sections."""
        from application.artifact_markdown import render_artifact_markdown

        for index, section in enumerate(by_parent.get(parent_id, []), start=1):
            number = prefix + (index,)
            label = ".".join(str(n) for n in number)
            heading = "#" * min(6, len(number) + 1)
            lines.append(f"{heading} {label} {section.title}")
            lines.append("")

            counter = 0
            for row in self.resolve_section_rows(ctx, section):
                counter += 1
                block = render_artifact_markdown(
                    row, heading_level=min(6, len(number) + 2)
                )
                head, _, rest = block.partition("\n")
                hashes, _, title = head.partition(" ")
                lines.append(f"{hashes} {label}.{counter} {title}")
                if rest:
                    lines.append(rest.rstrip())
                lines.append("")

            if by_parent.get(section.id):
                self._render_child_sections(
                    ctx, by_parent, section.id, number, counter, lines
                )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec backend pytest application/tests/test_document_read.py -v`
Expected: PASS (11 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/application/document_service.py backend/application/tests/test_document_read.py
git commit -m "feat: add numbered document read mode"
```

---

## Task 9: Baseline-Scope-Auflösung über ein Document-Objekt

**Files:**
- Modify: `backend/baseline/delta_index_builder.py:49-79` (Dispatch), neue Methode nach `:351`
- Modify: `backend/baseline/services.py:76-110` (`build`), `:307-...` (`resolve_scope_item_ids`)
- Test: `backend/baseline/tests/test_document_object_scope.py`

**Interfaces:**
- Consumes: `DocumentService.resolve_document_artifact_ids` (Task 7)
- Produces: `ScopeResolver._resolve_document_object(document_object_id, workspace_id, tenant_id) -> list[DeltaIndexTuple]`; erweiterte Signaturen `ScopeResolver.resolve(scope, workspace_id, tenant_id, document_id=None, document_object_id=None)`, `DeltaIndexBuilder.build(..., document_object_id=None)`, `baseline.services.build(..., document_object_id=None)`, `baseline.services.resolve_scope_item_ids(..., document_object_id=None)`

- [ ] **Step 1: Write the failing test**

Create `backend/baseline/tests/test_document_object_scope.py`:

```python
"""scope="document" bound to a real Document object (spec section 6).

D1: the legacy ``document_id`` (root artifact UUID) keeps its meaning; the
new ``document_object_id`` is additive. Exactly one of the two is required.
"""
from __future__ import annotations

import uuid

import pytest

from baseline.delta_index_builder import ScopeResolver


@pytest.mark.django_db
def test_legacy_document_id_still_resolves_the_artifact_subtree(
    workspace, admin_ctx, requirement
):
    """Regression guard: the pre-existing call shape must not change."""
    items = ScopeResolver().resolve(
        scope="document",
        workspace_id=workspace.id,
        tenant_id=admin_ctx.tenant_id,
        document_id=requirement.artifact_id,
    )
    assert str(requirement.artifact_id) in {i.item_id for i in items}


@pytest.mark.django_db
def test_document_object_id_resolves_all_sections(
    workspace, admin_ctx, requirement
):
    from application.document_service import DocumentService
    from application.models import DocumentSection

    svc = DocumentService()
    doc = svc.create_document(admin_ctx, workspace.id, "Doc")
    svc.create_section(
        admin_ctx, doc.id, "S", DocumentSection.CONTENT_TYPE_FIXED,
        fixed_artifact_ids=[str(requirement.artifact_id)],
    )

    items = ScopeResolver().resolve(
        scope="document",
        workspace_id=workspace.id,
        tenant_id=admin_ctx.tenant_id,
        document_object_id=doc.id,
    )
    assert str(requirement.artifact_id) in {i.item_id for i in items}


@pytest.mark.django_db
def test_neither_id_raises(workspace, admin_ctx):
    with pytest.raises(ValueError, match="document_id"):
        ScopeResolver().resolve(
            scope="document",
            workspace_id=workspace.id,
            tenant_id=admin_ctx.tenant_id,
        )


@pytest.mark.django_db
def test_both_ids_raise(workspace, admin_ctx, requirement):
    with pytest.raises(ValueError, match="exactly one"):
        ScopeResolver().resolve(
            scope="document",
            workspace_id=workspace.id,
            tenant_id=admin_ctx.tenant_id,
            document_id=requirement.artifact_id,
            document_object_id=uuid.uuid4(),
        )


@pytest.mark.django_db
def test_document_object_scope_includes_trace_links_of_members(
    workspace, admin_ctx, requirement
):
    """D7: parity with _resolve_document — links whose source is in scope."""
    from application.document_service import DocumentService
    from application.models import DocumentSection

    svc = DocumentService()
    doc = svc.create_document(admin_ctx, workspace.id, "Doc")
    svc.create_section(
        admin_ctx, doc.id, "S", DocumentSection.CONTENT_TYPE_FIXED,
        fixed_artifact_ids=[str(requirement.artifact_id)],
    )
    items = ScopeResolver().resolve(
        scope="document",
        workspace_id=workspace.id,
        tenant_id=admin_ctx.tenant_id,
        document_object_id=doc.id,
    )
    assert {i.entity_type for i in items} <= {"item", "trace_link"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend pytest baseline/tests/test_document_object_scope.py -v`
Expected: FAIL with `TypeError: ScopeResolver.resolve() got an unexpected keyword argument 'document_object_id'`

- [ ] **Step 3: Write minimal implementation**

In `backend/baseline/delta_index_builder.py`, replace the `resolve()` signature and its `document` branch:

```python
    def resolve(
        self,
        scope: str,
        workspace_id: uuid.UUID,
        tenant_id: uuid.UUID,
        document_id: Optional[uuid.UUID] = None,
        document_object_id: Optional[uuid.UUID] = None,
    ) -> list[DeltaIndexTuple]:
        """Return (item_id, version, entity_type) tuples for the given scope.

        Args:
            scope: "document" | "project" | "global"
            workspace_id: Target workspace UUID.
            tenant_id: Active tenant UUID.
            document_id: Legacy document scope — the **root artifact** UUID
                whose subtree is baselined. Kept for backward compatibility
                with all nine existing call sites.
            document_object_id: New document scope — a real
                ``application.models.Document`` UUID whose sections are
                resolved and unioned (Dokument-Sicht spec, section 6).

        Exactly one of ``document_id`` / ``document_object_id`` is required
        for scope="document".
        """
        if scope == "project":
            return self._resolve_project(workspace_id, tenant_id)
        elif scope == "global":
            return self._resolve_global(tenant_id)
        elif scope == "document":
            if document_id is not None and document_object_id is not None:
                raise ValueError(
                    "Pass exactly one of document_id (root artifact) or "
                    "document_object_id (Document); both were given."
                )
            if document_object_id is not None:
                return self._resolve_document_object(
                    document_object_id, workspace_id, tenant_id
                )
            if document_id is None:
                raise ValueError("document_id is required for scope='document'")
            return self._resolve_document(document_id, workspace_id, tenant_id)
        else:
            raise ValueError(f"Unknown scope: {scope!r}")
```

Add after `_resolve_document` (line ~351):

```python
    def _resolve_document_object(
        self,
        document_object_id: uuid.UUID,
        workspace_id: uuid.UUID,
        tenant_id: uuid.UUID,
    ) -> list[DeltaIndexTuple]:
        """All artifacts of a Document's sections + their TraceLinks.

        Extends, rather than replaces, ``_resolve_document``: query, fixed
        and subtree sections are resolved and deduplicated by
        ``DocumentService.resolve_document_artifact_ids``, then the same
        TraceLink attachment as the legacy resolver runs on the union (D7).

        The snapshot/diff/VersionReconstructor machinery is untouched — this
        only widens which items land in the delta index.
        """
        from django.db import connection

        from application.document_service import DocumentService
        from persistence.tenancy import TenantContext

        TenantContext.set_tenant(str(tenant_id))
        service = DocumentService()

        class _ResolverCtx:
            """Minimal AuthContext stand-in: resolution is read-only and the
            caller has already been authorised one layer up (BaselineFacade
            asserts write permission before build())."""

            tenant_id = None
            user_id = None

        ctx = _ResolverCtx()
        ctx.tenant_id = tenant_id
        artifact_ids = service.resolve_document_artifact_ids(ctx, document_object_id)
        if not artifact_ids:
            return []

        placeholders = ",".join(["%s"] * len(artifact_ids))
        sql = f"""
            SELECT a.id::text, a.version
            FROM pl_artifact a
            WHERE a.id::text IN ({placeholders})
              AND a.workspace_id = %s
              AND a.tenant_id = %s
            ORDER BY a.id
        """
        with connection.cursor() as cur:
            cur.execute(sql, artifact_ids + [str(workspace_id), str(tenant_id)])
            rows = cur.fetchall()

        items = [
            DeltaIndexTuple(
                item_id=str(row[0]), version=int(row[1]), entity_type="item"
            )
            for row in rows
        ]

        if items:
            item_ids = [t.item_id for t in items]
            tl_placeholders = ",".join(["%s"] * len(item_ids))
            tl_sql = f"""
                SELECT tl.id::text, tl.version
                FROM pl_tracelink tl
                WHERE tl.source_id::text IN ({tl_placeholders})
                  AND tl.tenant_id = %s
                ORDER BY tl.id
            """
            with connection.cursor() as cur:
                cur.execute(tl_sql, item_ids + [str(tenant_id)])
                tl_rows = cur.fetchall()
            items.extend(
                DeltaIndexTuple(
                    item_id=str(row[0]),
                    version=int(row[1]),
                    entity_type="trace_link",
                )
                for row in tl_rows
            )

        return items
```

Confirm `TenantContext.set_tenant` is the real API with
`grep -n "def set_tenant\|def set\b" backend/persistence/tenancy.py`; if `DocumentService._set_tenant_context(ctx)` already covers it, drop the explicit `TenantContext` call and pass a proper `AuthContext` instead of `_ResolverCtx`.

Then thread the parameter through `DeltaIndexBuilder.build` (add `document_object_id: Optional[uuid.UUID] = None` to the signature and pass it into `self._resolver.resolve(...)`), through `baseline.services.build` (same addition, forwarded to `get_builder().build(...)`), and add the same optional parameter to `baseline.services.resolve_scope_item_ids`, where `scope == "document"` with a `document_object_id` returns `DocumentService().resolve_document_artifact_ids(...)` directly and the existing `artifact_id` branch stays untouched.

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec backend pytest baseline/tests/test_document_object_scope.py baseline/ -v`
Expected: PASS — the five new tests plus the whole pre-existing baseline suite (proves the legacy path is untouched)

- [ ] **Step 5: Commit**

```bash
git add backend/baseline/delta_index_builder.py backend/baseline/services.py backend/baseline/tests/test_document_object_scope.py
git commit -m "feat: resolve baseline document scope from a Document object"
```

---

## Task 10: BaselineSnapshot.document — FK, Persistenz und defensiver Backfill

**Files:**
- Modify: `backend/baseline/models.py` (nach `artifact`, ~Zeile 90)
- Modify: `backend/baseline/types.py:41-55` (`BaselineMetadata`)
- Modify: `backend/baseline/store.py:101-113`
- Modify: `backend/baseline/delta_index_builder.py` (Metadata-Aufbau in `build`)
- Create: `backend/baseline/migrations/0007_baselinesnapshot_document.py`
- Test: `backend/baseline/tests/test_document_object_scope.py`

**Interfaces:**
- Consumes: `application.models.Document` (Task 1)
- Produces: `BaselineSnapshot.document` (nullable FK), `BaselineMetadata.root_artifact_id`, `BaselineMetadata.document_object_id`

- [ ] **Step 1: Write the failing test**

Append to `backend/baseline/tests/test_document_object_scope.py`:

```python
@pytest.mark.django_db
def test_baseline_persists_the_document_reference(workspace, admin_ctx, requirement):
    """V3: the root/document reference used to be dropped on the floor."""
    from application.document_service import DocumentService
    from application.models import DocumentSection
    from baseline.models import BaselineSnapshot
    from baseline.services import build as baseline_build

    svc = DocumentService()
    doc = svc.create_document(admin_ctx, workspace.id, "Doc")
    svc.create_section(
        admin_ctx, doc.id, "S", DocumentSection.CONTENT_TYPE_FIXED,
        fixed_artifact_ids=[str(requirement.artifact_id)],
    )

    baseline_id = baseline_build(
        scope="document",
        workspace_id=workspace.id,
        name="B1",
        tenant_id=admin_ctx.tenant_id,
        document_object_id=doc.id,
    )
    snapshot = BaselineSnapshot.unscoped.get(id=baseline_id)
    assert snapshot.document_id == doc.id


@pytest.mark.django_db
def test_legacy_baseline_persists_the_root_artifact(workspace, admin_ctx, requirement):
    from baseline.models import BaselineSnapshot
    from baseline.services import build as baseline_build

    baseline_id = baseline_build(
        scope="document",
        workspace_id=workspace.id,
        name="B2",
        tenant_id=admin_ctx.tenant_id,
        document_id=requirement.artifact_id,
    )
    snapshot = BaselineSnapshot.unscoped.get(id=baseline_id)
    assert snapshot.artifact_id == requirement.artifact_id
    assert snapshot.document_id is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend pytest baseline/tests/test_document_object_scope.py -v -k persists`
Expected: FAIL with `AttributeError: 'BaselineSnapshot' object has no attribute 'document_id'`

- [ ] **Step 3: Write minimal implementation**

In `backend/baseline/models.py`, after the `artifact` FK:

```python
    # Optional link to the Document this baseline was taken over
    # (Dokument-Sicht spec, section 6). Mutually exclusive with ``artifact``:
    # ``artifact`` is the legacy root-artifact subtree, ``document`` is the
    # real Document object. Both nullable for project/global scope.
    document = models.ForeignKey(
        "application.Document",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="baseline_snapshots",
    )
```

In `backend/baseline/types.py`, add to `BaselineMetadata`:

```python
    # V3 fix: the document-scope reference used to be dropped after scope
    # resolution, leaving every snapshot unable to say what it covered.
    root_artifact_id: Optional[uuid.UUID] = None
    document_object_id: Optional[uuid.UUID] = None
```

In `backend/baseline/delta_index_builder.py`, extend the `BaselineMetadata(...)` construction inside `build()`:

```python
        metadata = BaselineMetadata(
            workspace_id=workspace_id,
            scope=scope,
            name=name,
            description=description,
            created_by=created_by,
            created_at=datetime.now(tz=timezone.utc),
            root_artifact_id=document_id,
            document_object_id=document_object_id,
        )
```

In `backend/baseline/store.py`, extend the `BaselineSnapshot(...)` construction:

```python
            snapshot = BaselineSnapshot(
                workspace_id=metadata.workspace_id,
                scope=metadata.scope,
                name=metadata.name,
                description=metadata.description or "",
                created_by_ref=metadata.created_by,
                tenant_id=tenant_id,
                created_at=created_at,
                artifact_id=metadata.root_artifact_id,
                document_id=metadata.document_object_id,
            )
```

Create `backend/baseline/migrations/0007_baselinesnapshot_document.py`:

```python
"""Add BaselineSnapshot.document and backfill legacy document-scope rows.

Spec: docs/superpowers/specs/2026-09-03-dokumentensicht-design.md, section 6.

Two things happen here:

1. The additive ``document`` FK (nullable) — new document-scope baselines
   point at a real ``application.Document`` instead of a bare artifact id.

2. A defensive backfill: for every existing ``scope='document'`` snapshot
   that carries a root ``artifact_id``, create one Document with exactly one
   ``subtree`` section wrapping that artifact and point the snapshot at it.

   In practice this migrates **zero** rows: ``BaselineSnapshot.artifact`` has
   never been written by any code path (``BaselineMetadata`` had no artifact
   field and ``BaselineStore.persist_delta_index`` never set it), so the
   column is NULL everywhere. The backfill is implemented anyway so a
   deployment that populated the column out-of-band is migrated correctly.

   ``bl_baseline_snapshot`` carries an unconditional BEFORE UPDATE trigger
   (``trg_baseline_snapshot_immutable``, migrations/0001_initial.py) with no
   GUC escape hatch, so the UPDATE is bracketed by ALTER TABLE ... DISABLE /
   ENABLE TRIGGER. That requires table ownership, which the *migration* role
   holds (the application connects as the least-privilege
   ``persistence.db_roles.APP_DB_ROLE`` and keeps the guard fully intact).
   Both statements run inside the migration's transaction, so a failure rolls
   the trigger back on.

req_id: REQ-L2-BL-001, REQ-L2-BL-002
"""
from __future__ import annotations

import uuid

from django.db import migrations, models
import django.db.models.deletion


def _backfill(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return

    BaselineSnapshot = apps.get_model("baseline", "BaselineSnapshot")
    Document = apps.get_model("application", "Document")
    DocumentSection = apps.get_model("application", "DocumentSection")

    legacy = list(
        BaselineSnapshot.objects.filter(
            scope="document", artifact_id__isnull=False, document_id__isnull=True
        )
    )
    if not legacy:
        return

    # One Document per distinct (tenant, workspace, root artifact) triple —
    # several baselines over the same root share one Document.
    created: dict = {}
    for snapshot in legacy:
        key = (snapshot.tenant_id, snapshot.workspace_id, snapshot.artifact_id)
        if key not in created:
            doc = Document.objects.create(
                id=uuid.uuid4(),
                tenant_id=snapshot.tenant_id,
                workspace_id=snapshot.workspace_id,
                title=f"Migrated document scope {snapshot.artifact_id}",
            )
            DocumentSection.objects.create(
                id=uuid.uuid4(),
                tenant_id=snapshot.tenant_id,
                document=doc,
                title="Artifact subtree",
                order=0,
                content_type="subtree",
                fixed_artifact_ids=[],
                subtree_root_artifact_id=snapshot.artifact_id,
            )
            created[key] = doc
        snapshot.document_id = created[key].id

    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            "ALTER TABLE bl_baseline_snapshot "
            "DISABLE TRIGGER trg_baseline_snapshot_immutable"
        )
        try:
            for snapshot in legacy:
                cursor.execute(
                    "UPDATE bl_baseline_snapshot SET document_id = %s WHERE id = %s",
                    [str(snapshot.document_id), str(snapshot.id)],
                )
        finally:
            cursor.execute(
                "ALTER TABLE bl_baseline_snapshot "
                "ENABLE TRIGGER trg_baseline_snapshot_immutable"
            )


def _unbackfill(apps, schema_editor):
    """Reverse: drop the generated Documents; the FK column goes with the
    AddField reversal."""
    if schema_editor.connection.vendor != "postgresql":
        return
    Document = apps.get_model("application", "Document")
    Document.objects.filter(title__startswith="Migrated document scope ").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("baseline", "0006_baseline_snapshot_rls"),
        ("application", "0021_document_rls_policies"),
    ]

    operations = [
        migrations.AddField(
            model_name="baselinesnapshot",
            name="document",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="baseline_snapshots",
                to="application.document",
            ),
        ),
        migrations.RunPython(_backfill, _unbackfill),
    ]
```

Note the `related_name` collision: `BaselineSnapshot.artifact` already uses `related_name="baseline_snapshots"` on `persistence.Artifact`. That is a *different* target model, so the name may be reused — confirm with `docker compose exec backend python manage.py check` before committing.

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec backend python manage.py check && docker compose exec backend pytest baseline/ -v --create-db`
Expected: PASS — `check` reports no issues, both new tests plus the full baseline suite pass on a freshly migrated DB

- [ ] **Step 5: Commit**

```bash
git add backend/baseline/models.py backend/baseline/types.py backend/baseline/store.py backend/baseline/delta_index_builder.py backend/baseline/migrations/0007_baselinesnapshot_document.py backend/baseline/tests/test_document_object_scope.py
git commit -m "feat: bind document-scope baselines to a real Document object"
```

---

## Task 11: BaselineFacade und SE-Auditor-Gate durchreichen

**Files:**
- Modify: `backend/application/baseline_facade.py:76-180` (`create_baseline`), `:222` (`_enforce_audit_gate`)
- Modify: `backend/traceability/audit/types.py:75-150` (`AuditScope`, `AuditContext`)
- Test: `backend/application/tests/test_baseline_document_binding.py`

**Interfaces:**
- Consumes: `baseline.services.build(..., document_object_id=...)` (Task 9)
- Produces: `BaselineFacade.create_baseline(..., document_object_id: Optional[UUID | str] = None)`; `AuditScope(scope, artifact_id=None, document_object_id=None)`; `AuditContext(..., scope_document_object_id: Optional[str] = None)`

- [ ] **Step 1: Write the failing test**

Create `backend/application/tests/test_baseline_document_binding.py`:

```python
"""BaselineFacade + SE-Auditor gate with a Document-bound scope (D1)."""
from __future__ import annotations

import uuid

import pytest

from application.baseline_facade import BaselineFacade
from application.document_service import DocumentService
from application.exceptions import ValidationError
from application.models import DocumentSection


@pytest.fixture
def facade():
    return BaselineFacade()


@pytest.mark.django_db
def test_create_baseline_with_document_object_id(
    facade, admin_ctx, workspace, requirement
):
    svc = DocumentService()
    doc = svc.create_document(admin_ctx, workspace.id, "Doc")
    svc.create_section(
        admin_ctx, doc.id, "S", DocumentSection.CONTENT_TYPE_FIXED,
        fixed_artifact_ids=[str(requirement.artifact_id)],
    )

    baseline_id = facade.create_baseline(
        scope="document",
        workspace_id=workspace.id,
        name="Doc baseline",
        ctx=admin_ctx,
        document_object_id=doc.id,
    )
    assert baseline_id is not None


@pytest.mark.django_db
def test_document_scope_without_any_reference_still_raises(
    facade, admin_ctx, workspace
):
    with pytest.raises(ValidationError, match="document_id"):
        facade.create_baseline(
            scope="document",
            workspace_id=workspace.id,
            name="X",
            ctx=admin_ctx,
        )


@pytest.mark.django_db
def test_passing_both_references_is_rejected(facade, admin_ctx, workspace, requirement):
    with pytest.raises(ValidationError, match="exactly one"):
        facade.create_baseline(
            scope="document",
            workspace_id=workspace.id,
            name="X",
            ctx=admin_ctx,
            document_id=requirement.artifact_id,
            document_object_id=uuid.uuid4(),
        )


@pytest.mark.django_db
def test_audit_scope_carries_the_document_object_id():
    from traceability.audit.types import AuditScope

    scope = AuditScope(scope="document", document_object_id="abc")
    assert scope.artifact_id is None
    assert scope.document_object_id == "abc"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend pytest application/tests/test_baseline_document_binding.py -v`
Expected: FAIL with `TypeError: create_baseline() got an unexpected keyword argument 'document_object_id'`

- [ ] **Step 3: Write minimal implementation**

In `backend/application/baseline_facade.py`, add `document_object_id: Optional[UUID | str] = None` to `create_baseline`'s signature and replace the existing document-scope validation block:

```python
        try:
            doc_id: Optional[UUID] = (
                UUID(str(document_id)) if document_id is not None else None
            )
            doc_obj_id: Optional[UUID] = (
                UUID(str(document_object_id))
                if document_object_id is not None
                else None
            )
        except (ValueError, AttributeError, TypeError) as exc:
            raise ValidationError(
                "Baseline cannot be created: document reference is not a valid UUID."
            ) from exc

        # D1: the two references are mutually exclusive. document_id keeps its
        # legacy meaning (root artifact subtree); document_object_id is the
        # real Document object (Dokument-Sicht spec, section 6).
        if doc_id is not None and doc_obj_id is not None:
            raise ValidationError(
                "Baseline cannot be created: pass exactly one of artifact_id "
                "(root artifact) or document_id (Document)."
            )
        if scope == "document" and doc_id is None and doc_obj_id is None:
            raise ValidationError(
                "Baseline cannot be created: document_id is required when "
                "scope='document' (the root artifact whose subtree is being "
                "baselined, or the Document object)."
            )
```

then forward `document_object_id=doc_obj_id` into both `self._enforce_audit_gate(...)` and `baseline_build(...)`.

In `_enforce_audit_gate`, add the same optional parameter and pass it into the `AuditScope` construction (currently `artifact_id=str(document_id) if document_id is not None else None`, `baseline_facade.py:302`):

```python
            artifact_id=str(document_id) if document_id is not None else None,
            document_object_id=(
                str(document_object_id) if document_object_id is not None else None
            ),
```

In `backend/traceability/audit/types.py`, extend both dataclasses:

```python
@dataclass(frozen=True)
class AuditScope:
    """A concrete baseline scope to audit.

    For ``scope == "document"`` exactly one of ``artifact_id`` (legacy subtree
    root) or ``document_object_id`` (real Document) is set; both are ignored
    for other scopes.
    """

    scope: str
    artifact_id: Optional[str] = None
    document_object_id: Optional[str] = None
```

and on `AuditContext` add `scope_document_object_id: Optional[str] = None` next to `scope_artifact_id`, forwarding it in the `scope_item_ids` property:

```python
        ids = resolve_scope_item_ids(
            scope=self.scope,
            workspace_id=self.workspace_id,
            tenant_id=self.tenant_id,
            artifact_id=self.scope_artifact_id,
            document_object_id=self.scope_document_object_id,
            exclude_diagram_shadow_artifacts=False,
        )
```

Finally grep for every `AuditScope(` and `AuditContext(` construction with
`grep -rn "AuditScope(\|AuditContext(" --include=*.py backend/ | grep -v tests`
and make sure each one either passes the new field or relies on its default.

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec backend pytest application/tests/test_baseline_document_binding.py traceability/ baseline/ -v`
Expected: PASS (4 new tests plus the traceability and baseline suites)

- [ ] **Step 5: Commit**

```bash
git add backend/application/baseline_facade.py backend/traceability/audit/types.py backend/application/tests/test_baseline_document_binding.py
git commit -m "feat: thread document_object_id through baseline facade and audit gate"
```

---

## Task 12: REST — DocumentViewSet mit Sektionen, Lesemodus und Export

**Files:**
- Modify: `backend/rest_api/serializers.py` (anhängen)
- Modify: `backend/rest_api/views.py` (anhängen)
- Modify: `backend/rest_api/urls.py:189` (nach der letzten `router.register`-Zeile)
- Test: `backend/rest_api/tests/test_document_api.py`

**Interfaces:**
- Consumes: `DocumentService` (Tasks 4/5/7/8)
- Produces: Routen `GET/POST /api/v1/documents/`, `GET/PATCH/DELETE /api/v1/documents/<pk>/`, `GET/POST /api/v1/documents/<pk>/sections/`, `POST /api/v1/documents/<pk>/reorder-sections/`, `GET /api/v1/documents/<pk>/read/`, `GET /api/v1/documents/<pk>/export/?format=markdown`

- [ ] **Step 1: Write the failing test**

Create `backend/rest_api/tests/test_document_api.py`:

```python
"""REST surface for documents (spec section 7)."""
from __future__ import annotations

import pytest


@pytest.mark.django_db
def test_document_crud_via_rest(auth_client, workspace):
    resp = auth_client.post(
        "/api/v1/documents/",
        {"workspace_id": str(workspace.id), "title": "Lastenheft"},
        format="json",
    )
    assert resp.status_code == 201, resp.data
    doc_id = resp.data["id"]

    listed = auth_client.get(f"/api/v1/documents/?workspace_id={workspace.id}")
    assert listed.status_code == 200
    assert any(d["id"] == doc_id for d in listed.data["results"])

    patched = auth_client.patch(
        f"/api/v1/documents/{doc_id}/", {"title": "Pflichtenheft"}, format="json"
    )
    assert patched.status_code == 200
    assert patched.data["title"] == "Pflichtenheft"

    assert auth_client.delete(f"/api/v1/documents/{doc_id}/").status_code == 204
    assert auth_client.get(f"/api/v1/documents/{doc_id}/").status_code == 404


@pytest.mark.django_db
def test_section_create_list_and_reorder(auth_client, workspace):
    doc_id = auth_client.post(
        "/api/v1/documents/",
        {"workspace_id": str(workspace.id), "title": "D"},
        format="json",
    ).data["id"]

    a = auth_client.post(
        f"/api/v1/documents/{doc_id}/sections/",
        {"title": "A", "content_type": "fixed", "order": 0},
        format="json",
    )
    assert a.status_code == 201, a.data
    b = auth_client.post(
        f"/api/v1/documents/{doc_id}/sections/",
        {"title": "B", "content_type": "fixed", "order": 1},
        format="json",
    )

    reordered = auth_client.post(
        f"/api/v1/documents/{doc_id}/reorder-sections/",
        {"section_ids": [b.data["id"], a.data["id"]]},
        format="json",
    )
    assert reordered.status_code == 200
    assert [s["id"] for s in reordered.data] == [b.data["id"], a.data["id"]]


@pytest.mark.django_db
def test_read_and_markdown_export(auth_client, workspace):
    doc_id = auth_client.post(
        "/api/v1/documents/",
        {"workspace_id": str(workspace.id), "title": "Lastenheft"},
        format="json",
    ).data["id"]
    auth_client.post(
        f"/api/v1/documents/{doc_id}/sections/",
        {"title": "Allgemeines", "content_type": "fixed"},
        format="json",
    )

    read = auth_client.get(f"/api/v1/documents/{doc_id}/read/")
    assert read.status_code == 200
    assert read.data["markdown"].startswith("# Lastenheft")
    assert "## 1 Allgemeines" in read.data["markdown"]

    exported = auth_client.get(f"/api/v1/documents/{doc_id}/export/?format=markdown")
    assert exported.status_code == 200
    assert exported["Content-Type"].startswith("text/markdown")
    assert b"# Lastenheft" in exported.content


@pytest.mark.django_db
def test_unsupported_export_format_is_400(auth_client, workspace):
    doc_id = auth_client.post(
        "/api/v1/documents/",
        {"workspace_id": str(workspace.id), "title": "D"},
        format="json",
    ).data["id"]
    resp = auth_client.get(f"/api/v1/documents/{doc_id}/export/?format=docx")
    assert resp.status_code == 400


@pytest.mark.django_db
def test_malformed_uuid_detail_route_is_400(auth_client):
    assert auth_client.get("/api/v1/documents/not-a-uuid/").status_code == 400
```

Caution (#271 / DRF negotiation): `format` is a DRF-reserved query parameter. Confirm with `grep -rn "URL_FORMAT_OVERRIDE\|format_kwarg" backend/reqogniloom/settings.py backend/rest_api/`. If DRF still intercepts it, rename the parameter to `export_format` in both the test and the view and note the deviation in the docstring.

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend pytest rest_api/tests/test_document_api.py -v`
Expected: FAIL — all requests return 404 (no `documents/` route registered)

- [ ] **Step 3: Write minimal implementation**

Append to `backend/rest_api/serializers.py`:

```python
class DocumentSectionSerializer(serializers.Serializer):
    """Read serializer for application.models.DocumentSection."""

    id = serializers.UUIDField(read_only=True)
    document_id = serializers.UUIDField(read_only=True)
    parent_section_id = serializers.UUIDField(read_only=True, allow_null=True)
    title = serializers.CharField(max_length=255)
    order = serializers.IntegerField(default=0)
    content_type = serializers.ChoiceField(choices=["query", "fixed", "subtree"])
    query = serializers.JSONField(required=False, allow_null=True)
    fixed_artifact_ids = serializers.JSONField(required=False)
    subtree_root_artifact_id = serializers.UUIDField(
        required=False, allow_null=True
    )


class DocumentSerializer(serializers.Serializer):
    """Read serializer for application.models.Document."""

    id = serializers.UUIDField(read_only=True)
    workspace_id = serializers.UUIDField()
    title = serializers.CharField(max_length=255)
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)
```

Append to `backend/rest_api/views.py`:

```python
class DocumentViewSet(BaseEntityViewSet):
    """Living specification documents (Dokument-Sicht spec, section 7).

    All persistence goes through DocumentService (ADR-01) — no direct model
    access from this view.
    """

    serializer_class = DocumentSerializer

    def _svc(self) -> DocumentService:
        return DocumentService()

    def list(self, request: Request, **kwargs: Any) -> Response:
        ctx = get_auth_context(request)
        lang = detect_lang(request)
        workspace_id, error = parse_workspace_id(
            request.query_params.get("workspace_id"), lang
        )
        if error is not None:
            return error
        try:
            docs = self._svc().list_documents(ctx, workspace_id)
        except Exception as exc:
            return _service_error_response(exc, lang)
        page = self.paginate_queryset(docs)
        data = DocumentSerializer(page if page is not None else docs, many=True).data
        return (
            self.get_paginated_response(data)
            if page is not None
            else Response(data)
        )

    def create(self, request: Request, **kwargs: Any) -> Response:
        ctx = get_auth_context(request)
        lang = detect_lang(request)
        workspace_id, error = parse_workspace_id(
            request.data.get("workspace_id"), lang
        )
        if error is not None:
            return error
        try:
            doc = self._svc().create_document(
                ctx, workspace_id, request.data.get("title", "")
            )
        except Exception as exc:
            return _service_error_response(exc, lang)
        return Response(
            DocumentSerializer(doc).data, status=status.HTTP_201_CREATED
        )

    def retrieve(self, request: Request, pk: str, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        try:
            doc = self._svc().get_document(get_auth_context(request), UUID(pk))
        except Exception as exc:
            return _service_error_response(exc, lang)
        return Response(DocumentSerializer(doc).data)

    def partial_update(self, request: Request, pk: str, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        try:
            doc = self._svc().update_document(
                get_auth_context(request), UUID(pk), title=request.data.get("title")
            )
        except Exception as exc:
            return _service_error_response(exc, lang)
        return Response(DocumentSerializer(doc).data)

    def destroy(self, request: Request, pk: str, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        try:
            self._svc().delete_document(get_auth_context(request), UUID(pk))
        except Exception as exc:
            return _service_error_response(exc, lang)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["get", "post"], url_path="sections")
    def sections(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """GET/POST /api/v1/documents/{pk}/sections/"""
        ctx = get_auth_context(request)
        lang = detect_lang(request)
        try:
            if request.method == "GET":
                items = self._svc().list_sections(ctx, UUID(pk))
                return Response(DocumentSectionSerializer(items, many=True).data)
            section = self._svc().create_section(
                ctx,
                UUID(pk),
                title=request.data.get("title", ""),
                content_type=request.data.get("content_type", ""),
                order=request.data.get("order", 0),
                parent_section_id=request.data.get("parent_section_id"),
                query=request.data.get("query"),
                fixed_artifact_ids=request.data.get("fixed_artifact_ids"),
                subtree_root_artifact_id=request.data.get("subtree_root_artifact_id"),
            )
        except Exception as exc:
            return _service_error_response(exc, lang)
        return Response(
            DocumentSectionSerializer(section).data, status=status.HTTP_201_CREATED
        )

    @action(detail=True, methods=["post"], url_path="reorder-sections")
    def reorder_sections(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """POST /api/v1/documents/{pk}/reorder-sections/ — {"section_ids": [...]}"""
        lang = detect_lang(request)
        try:
            items = self._svc().reorder_sections(
                get_auth_context(request),
                UUID(pk),
                request.data.get("section_ids") or [],
            )
        except Exception as exc:
            return _service_error_response(exc, lang)
        return Response(DocumentSectionSerializer(items, many=True).data)

    @action(detail=True, methods=["get"], url_path="read")
    def read(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """GET /api/v1/documents/{pk}/read/ — numbered read-mode Markdown.

        Live by design: query sections are evaluated now, not at document
        creation time (spec risk 1).
        """
        lang = detect_lang(request)
        try:
            markdown = self._svc().read_document(get_auth_context(request), UUID(pk))
        except Exception as exc:
            return _service_error_response(exc, lang)
        return Response({"markdown": markdown})

    @action(detail=True, methods=["get"], url_path="export")
    def export(self, request: Request, pk: str, **kwargs: Any) -> HttpResponse:
        """GET /api/v1/documents/{pk}/export/?format=markdown

        Pure serialisation of the read-mode output — no new dependency.
        DOCX is deliberately out of scope for this spec.
        """
        lang = detect_lang(request)
        fmt = (request.query_params.get("format") or "markdown").lower()
        if fmt != "markdown":
            return Response(
                build_error_response(
                    "VALIDATION_ERROR",
                    lang,
                    message="format must be 'markdown'",
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            ctx = get_auth_context(request)
            doc = self._svc().get_document(ctx, UUID(pk))
            markdown = self._svc().read_document(ctx, UUID(pk))
        except Exception as exc:
            return _service_error_response(exc, lang)
        response = HttpResponse(markdown, content_type="text/markdown; charset=utf-8")
        response["Content-Disposition"] = (
            f'attachment; filename="{doc.id}.md"'
        )
        return response
```

Add `from application.document_service import DocumentService` and `DocumentSerializer, DocumentSectionSerializer` to the existing import blocks of `views.py`, and confirm `HttpResponse` is already imported (`grep -n "from django.http import" backend/rest_api/views.py`).

Register the route in `backend/rest_api/urls.py` after line 189:

```python
router.register(r"documents", DocumentViewSet, basename="document")
```

and add `DocumentViewSet` to the `from rest_api.views import (...)` block.

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec backend pytest rest_api/tests/test_document_api.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/rest_api/serializers.py backend/rest_api/views.py backend/rest_api/urls.py backend/rest_api/tests/test_document_api.py
git commit -m "feat: add documents REST endpoints with read mode and markdown export"
```

---

## Task 13: REST — Baseline-Erstellung akzeptiert eine Document-ID

**Files:**
- Modify: `backend/rest_api/views.py:3203-3229`
- Test: `backend/rest_api/tests/test_document_api.py`

**Interfaces:**
- Consumes: `BaselineFacade.create_baseline(..., document_object_id=...)` (Task 11)
- Produces: `POST /api/v1/baselines/` akzeptiert zusätzlich `document_id` (echte `Document.id`); `artifact_id` bleibt unverändert

- [ ] **Step 1: Write the failing test**

Append to `backend/rest_api/tests/test_document_api.py`:

```python
@pytest.mark.django_db
def test_baseline_can_be_created_from_a_document_id(
    auth_client, workspace, requirement
):
    doc_id = auth_client.post(
        "/api/v1/documents/",
        {"workspace_id": str(workspace.id), "title": "D"},
        format="json",
    ).data["id"]
    auth_client.post(
        f"/api/v1/documents/{doc_id}/sections/",
        {
            "title": "S",
            "content_type": "fixed",
            "fixed_artifact_ids": [str(requirement.artifact_id)],
        },
        format="json",
    )

    resp = auth_client.post(
        "/api/v1/baselines/",
        {
            "scope": "document",
            "workspace_id": str(workspace.id),
            "name": "From document",
            "document_id": doc_id,
        },
        format="json",
    )
    assert resp.status_code == 201, resp.data


@pytest.mark.django_db
def test_baseline_rejects_both_artifact_id_and_document_id(
    auth_client, workspace, requirement
):
    doc_id = auth_client.post(
        "/api/v1/documents/",
        {"workspace_id": str(workspace.id), "title": "D"},
        format="json",
    ).data["id"]
    resp = auth_client.post(
        "/api/v1/baselines/",
        {
            "scope": "document",
            "workspace_id": str(workspace.id),
            "name": "Both",
            "artifact_id": str(requirement.artifact_id),
            "document_id": doc_id,
        },
        format="json",
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_baseline_document_scope_still_accepts_artifact_id_alone(
    auth_client, workspace, requirement
):
    """Regression guard for the nine legacy call sites (V2)."""
    resp = auth_client.post(
        "/api/v1/baselines/",
        {
            "scope": "document",
            "workspace_id": str(workspace.id),
            "name": "Legacy",
            "artifact_id": str(requirement.artifact_id),
        },
        format="json",
    )
    assert resp.status_code == 201, resp.data
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend pytest rest_api/tests/test_document_api.py -v -k baseline`
Expected: FAIL — the first test returns 400 ("artifact_id is required for document scope"); `document_id` is silently ignored today

- [ ] **Step 3: Write minimal implementation**

In `backend/rest_api/views.py`, replace the document-scope block of `BaselineViewSet.create` (currently lines 3202-3229) with:

```python
            # document scope needs either a root artifact (legacy) or a real
            # Document object (Dokument-Sicht spec, section 6). D1: both names
            # coexist, exactly one may be supplied.
            artifact_id = data.get("artifact_id")
            document_ref = data.get("document_id")
            if artifact_id is not None and document_ref is not None:
                return Response(
                    build_error_response(
                        "VALIDATION_ERROR",
                        lang,
                        message=(
                            "Pass exactly one of artifact_id (root artifact) "
                            "or document_id (Document)."
                        ),
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if scope == "document" and artifact_id is None and document_ref is None:
                return Response(
                    build_error_response(
                        "VALIDATION_ERROR",
                        lang,
                        message=(
                            "artifact_id or document_id is required for "
                            "document scope"
                        ),
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )
            for raw_value, kwarg in (
                (artifact_id, "document_id"),
                (document_ref, "document_object_id"),
            ):
                if raw_value is None:
                    continue
                # GH-724: reject a malformed UUID here with a clean 400
                # instead of letting a raw ValueError escape as a 500.
                try:
                    UUID(str(raw_value))
                except (ValueError, TypeError):
                    return Response(
                        build_error_response(
                            "VALIDATION_ERROR",
                            lang,
                            message=f"{kwarg} must be a valid UUID",
                        ),
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                create_kwargs[kwarg] = str(raw_value)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec backend pytest rest_api/tests/test_document_api.py rest_api/tests/ -v -k "document or baseline"`
Expected: PASS (8 new tests plus all pre-existing baseline REST tests)

- [ ] **Step 5: Commit**

```bash
git add backend/rest_api/views.py backend/rest_api/tests/test_document_api.py
git commit -m "feat: accept a Document id when creating a document-scope baseline"
```

---

## Task 14: MCP-Tool-Gruppe document.*

**Files:**
- Create: `backend/mcp_server/tools/document.py`
- Modify: `backend/mcp_server/tool_registry.py:557-604` (Registrierungs-Dict)
- Test: `backend/mcp_server/tests/test_document_tool_group.py`

**Interfaces:**
- Consumes: `DocumentService` (Tasks 4/5/8)
- Produces: `mcp_server.tools.document.DocumentToolGroup` mit `document.list`, `document.get`, `document.read`

- [ ] **Step 1: Write the failing test**

Create `backend/mcp_server/tests/test_document_tool_group.py`:

```python
"""document.* MCP tools (spec section 7). D5: a hand-written group, because
GenericCrudToolGroup would claim document.read as an entity read."""
from __future__ import annotations

import pytest

from mcp_server.tools.document import DocumentToolGroup


def test_tool_names_match_the_spec():
    names = {schema["name"] for schema in DocumentToolGroup().get_tool_schemas()}
    assert names == {"document.list", "document.get", "document.read"}


def test_every_schema_declares_its_required_parameters():
    for schema in DocumentToolGroup().get_tool_schemas():
        params = schema["inputSchema"]["properties"]
        required = schema["inputSchema"]["required"]
        if schema["name"] == "document.list":
            assert required == ["workspace_id"]
        else:
            assert required == ["document_id"]
        assert all(key in params for key in required)


@pytest.mark.django_db
def test_document_read_returns_the_same_markdown_as_the_service(
    admin_ctx, workspace, requirement
):
    from application.document_service import DocumentService
    from application.models import DocumentSection

    svc = DocumentService()
    doc = svc.create_document(admin_ctx, workspace.id, "Lastenheft")
    svc.create_section(
        admin_ctx, doc.id, "S", DocumentSection.CONTENT_TYPE_FIXED,
        fixed_artifact_ids=[str(requirement.artifact_id)],
    )

    result = DocumentToolGroup().handle(
        "document.read", {"document_id": str(doc.id)}, admin_ctx
    )
    assert result["markdown"] == svc.read_document(admin_ctx, doc.id)
    # MCP payloads must never use a top-level "content" key.
    assert "content" not in result


@pytest.mark.django_db
def test_document_list_and_get(admin_ctx, workspace):
    from application.document_service import DocumentService

    doc = DocumentService().create_document(admin_ctx, workspace.id, "D")
    group = DocumentToolGroup()

    listed = group.handle("document.list", {"workspace_id": str(workspace.id)}, admin_ctx)
    assert str(doc.id) in {d["id"] for d in listed["documents"]}

    got = group.handle("document.get", {"document_id": str(doc.id)}, admin_ctx)
    assert got["document"]["title"] == "D"
```

Confirm the dispatch method name and the ctx-passing convention of `BaseToolGroup` first:
`grep -n "def handle\|def dispatch\|TOOL_MAP\|def get_tool_schemas" backend/mcp_server/tools/base.py`.
Adapt the three `group.handle(...)` calls and the schema accessor to whatever `base.py` actually defines before running.

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend pytest mcp_server/tests/test_document_tool_group.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mcp_server.tools.document'`

- [ ] **Step 3: Write minimal implementation**

Create `backend/mcp_server/tools/document.py`:

```python
"""document.* MCP tool group (Dokument-Sicht spec, section 7).

Hand-written rather than a GenericCrudToolGroup instance (D5): that class
maps ``{prefix}.read`` to an *entity read*, whereas the spec reserves
``document.read`` for the read-mode Markdown. Read-only group — document
mutation stays on the REST surface for now.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from application.document_service import DocumentService
from mcp_server.tools.base import BaseToolGroup

__all__ = ["DocumentToolGroup"]


class DocumentToolGroup(BaseToolGroup):
    """Lets an agent read a whole document, not just artifact by artifact."""

    prefix = "document"

    _TOOL_MAP = {
        "document.list": "_handle_list",
        "document.get": "_handle_get",
        "document.read": "_handle_read",
    }

    _TOOL_SCHEMAS = [
        {
            "name": "document.list",
            "description": "List all living-specification documents in a workspace.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_id": {
                        "type": "string",
                        "description": "Required. UUID of the target workspace.",
                    },
                },
                "required": ["workspace_id"],
            },
        },
        {
            "name": "document.get",
            "description": "Get one document's metadata and its section outline.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "document_id": {
                        "type": "string",
                        "description": "Required. UUID of the document.",
                    },
                },
                "required": ["document_id"],
            },
        },
        {
            "name": "document.read",
            "description": (
                "Render the whole document as numbered Markdown — the same "
                "read-mode output the REST endpoint returns. Query sections "
                "are evaluated at call time, so the result is live."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "document_id": {
                        "type": "string",
                        "description": "Required. UUID of the document.",
                    },
                },
                "required": ["document_id"],
            },
        },
    ]

    def __init__(self) -> None:
        self._service = DocumentService()

    def get_tool_schemas(self) -> list[dict[str, Any]]:
        return list(self._TOOL_SCHEMAS)

    # ---------- Handlers ----------

    def _handle_list(self, params: dict[str, Any], ctx) -> dict[str, Any]:
        workspace_id = UUID(str(params["workspace_id"]))
        docs = self._service.list_documents(ctx, workspace_id)
        return {
            "documents": [
                {
                    "id": str(d.id),
                    "title": d.title,
                    "workspace_id": str(d.workspace_id),
                    "created_at": d.created_at.isoformat() if d.created_at else None,
                }
                for d in docs
            ]
        }

    def _handle_get(self, params: dict[str, Any], ctx) -> dict[str, Any]:
        document_id = UUID(str(params["document_id"]))
        doc = self._service.get_document(ctx, document_id)
        sections = self._service.list_sections(ctx, document_id)
        return {
            "document": {
                "id": str(doc.id),
                "title": doc.title,
                "workspace_id": str(doc.workspace_id),
                "created_at": doc.created_at.isoformat() if doc.created_at else None,
                "sections": [
                    {
                        "id": str(s.id),
                        "title": s.title,
                        "order": s.order,
                        "content_type": s.content_type,
                        "parent_section_id": (
                            str(s.parent_section_id) if s.parent_section_id else None
                        ),
                    }
                    for s in sections
                ],
            }
        }

    def _handle_read(self, params: dict[str, Any], ctx) -> dict[str, Any]:
        document_id = UUID(str(params["document_id"]))
        # Every value here must survive stdlib json.dumps — the MCP transport
        # does not use DRF's encoder, so no UUID/datetime objects may leak.
        return {
            "document_id": str(document_id),
            "markdown": self._service.read_document(ctx, document_id),
        }
```

Register it in `backend/mcp_server/tool_registry.py` inside the `self.register_groups({...})` dict:

```python
            # Dokument-Sicht spec section 7: an agent can read a document as a
            # whole, not just artifact by artifact.
            "document": DocumentToolGroup(),
```

and add `from mcp_server.tools.document import DocumentToolGroup` to the import block.

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec backend pytest mcp_server/tests/test_document_tool_group.py mcp_server/ -v`
Expected: PASS (4 new tests plus the pre-existing MCP suite, including any manifest-size or tool-count assertions — update those counts if a test asserts an exact total)

- [ ] **Step 5: Commit**

```bash
git add backend/mcp_server/tools/document.py backend/mcp_server/tool_registry.py backend/mcp_server/tests/test_document_tool_group.py
git commit -m "feat: add document.* MCP tool group"
```

---

## Task 15: Frontend — API-Wrapper

**Files:**
- Create: `frontend/src/api/documents.ts`
- Test: `frontend/src/test/documentsApi.test.ts`

**Interfaces:**
- Consumes: `apiClient`, `getList` aus `frontend/src/api/client.ts`
- Produces: `listDocuments(workspaceId)`, `getDocument(id)`, `createDocument(workspaceId, title)`, `updateDocument(id, title)`, `deleteDocument(id)`, `listSections(documentId)`, `createSection(documentId, payload)`, `reorderSections(documentId, sectionIds)`, `readDocument(id)`, `documentExportUrl(id)`; Typen `Document`, `DocumentSection`, `DocumentSectionContentType`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/test/documentsApi.test.ts`:

```typescript
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../api/client", () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
  getList: vi.fn(),
}));

import { apiClient, getList } from "../api/client";
import {
  createDocument,
  documentExportUrl,
  listDocuments,
  readDocument,
  reorderSections,
} from "../api/documents";

describe("documents api", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("lists documents scoped to a workspace", async () => {
    vi.mocked(getList).mockResolvedValue({
      count: 0,
      next: null,
      previous: null,
      results: [],
    });
    await listDocuments("ws-1");
    expect(getList).toHaveBeenCalledWith("/documents/", { workspace_id: "ws-1" });
  });

  it("creates a document with workspace_id and title", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({ id: "d1", title: "T" });
    await createDocument("ws-1", "T");
    expect(apiClient.post).toHaveBeenCalledWith("/documents/", {
      workspace_id: "ws-1",
      title: "T",
    });
  });

  it("returns the markdown string from the read endpoint", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ markdown: "# Doc" });
    await expect(readDocument("d1")).resolves.toBe("# Doc");
    expect(apiClient.get).toHaveBeenCalledWith("/documents/d1/read/");
  });

  it("posts the ordered id list when reordering", async () => {
    vi.mocked(apiClient.post).mockResolvedValue([]);
    await reorderSections("d1", ["b", "a"]);
    expect(apiClient.post).toHaveBeenCalledWith("/documents/d1/reorder-sections/", {
      section_ids: ["b", "a"],
    });
  });

  it("builds the markdown export url", () => {
    expect(documentExportUrl("d1")).toBe("/documents/d1/export/?format=markdown");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec frontend npx vitest run src/test/documentsApi.test.ts --testTimeout=30000`
Expected: FAIL with `Failed to resolve import "../api/documents"`

- [ ] **Step 3: Write minimal implementation**

Create `frontend/src/api/documents.ts`:

```typescript
/**
 * ARCH-L1-001 ReactFrontend — Documents API.
 *
 * Wraps /api/v1/documents/ (Dokument-Sicht spec, section 7).
 */

import { apiClient, getList } from "./client";
import type { ISODateTime, PaginatedResponse, UUID } from "../types";

export type DocumentSectionContentType = "query" | "fixed" | "subtree";

export interface Document {
  id: UUID;
  workspace_id: UUID;
  title: string;
  created_at: ISODateTime;
  updated_at: ISODateTime;
}

export interface DocumentSection {
  id: UUID;
  document_id: UUID;
  parent_section_id: UUID | null;
  title: string;
  order: number;
  content_type: DocumentSectionContentType;
  query: Record<string, unknown> | null;
  fixed_artifact_ids: UUID[];
  subtree_root_artifact_id: UUID | null;
}

export interface CreateSectionPayload {
  title: string;
  content_type: DocumentSectionContentType;
  order?: number;
  parent_section_id?: UUID | null;
  query?: Record<string, unknown> | null;
  fixed_artifact_ids?: UUID[];
  subtree_root_artifact_id?: UUID | null;
}

export async function listDocuments(
  workspaceId: UUID
): Promise<PaginatedResponse<Document>> {
  return getList<Document>("/documents/", { workspace_id: workspaceId });
}

export async function getDocument(id: UUID): Promise<Document> {
  return apiClient.get<Document>(`/documents/${id}/`);
}

export async function createDocument(
  workspaceId: UUID,
  title: string
): Promise<Document> {
  return apiClient.post<Document>("/documents/", {
    workspace_id: workspaceId,
    title,
  });
}

export async function updateDocument(id: UUID, title: string): Promise<Document> {
  return apiClient.patch<Document>(`/documents/${id}/`, { title });
}

export async function deleteDocument(id: UUID): Promise<void> {
  await apiClient.delete(`/documents/${id}/`);
}

export async function listSections(documentId: UUID): Promise<DocumentSection[]> {
  return apiClient.get<DocumentSection[]>(`/documents/${documentId}/sections/`);
}

export async function createSection(
  documentId: UUID,
  payload: CreateSectionPayload
): Promise<DocumentSection> {
  return apiClient.post<DocumentSection>(
    `/documents/${documentId}/sections/`,
    payload
  );
}

export async function reorderSections(
  documentId: UUID,
  sectionIds: UUID[]
): Promise<DocumentSection[]> {
  return apiClient.post<DocumentSection[]>(
    `/documents/${documentId}/reorder-sections/`,
    { section_ids: sectionIds }
  );
}

/** Read mode: the numbered Markdown rendering of the whole document. */
export async function readDocument(id: UUID): Promise<string> {
  const response = await apiClient.get<{ markdown: string }>(
    `/documents/${id}/read/`
  );
  return response.markdown;
}

/** Download URL for the Markdown export of the read-mode output. */
export function documentExportUrl(id: UUID): string {
  return `/documents/${id}/export/?format=markdown`;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec frontend npx vitest run src/test/documentsApi.test.ts --testTimeout=30000`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/documents.ts frontend/src/test/documentsApi.test.ts
git commit -m "feat: add documents api wrapper"
```

---

## Task 16: Frontend — Lesemodus mit Druck-Stylesheet

**Files:**
- Create: `frontend/src/components/DocumentReadView/DocumentReadView.tsx`
- Create: `frontend/src/components/DocumentReadView/DocumentReadView.css`
- Modify: `frontend/src/components/NavigationShell/NavigationShell.tsx` (Route-Block ab Zeile 130)
- Modify: `frontend/src/i18n/locales/de.json`, `frontend/src/i18n/locales/en.json`
- Test: `frontend/src/test/DocumentReadView.test.tsx`

**Interfaces:**
- Consumes: `readDocument`, `documentExportUrl` (Task 15); `MarkdownPreview` aus `frontend/src/components/RequirementEditors/MarkdownPreview.tsx`
- Produces: Route `/documents/:id/read`, Komponente `DocumentReadView`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/test/DocumentReadView.test.tsx`:

```typescript
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../api/documents", () => ({
  readDocument: vi.fn(),
  documentExportUrl: vi.fn(() => "/documents/d1/export/?format=markdown"),
}));

import { readDocument } from "../api/documents";
import { DocumentReadView } from "../components/DocumentReadView/DocumentReadView";

function renderAt(id: string) {
  return render(
    <MemoryRouter initialEntries={[`/documents/${id}/read`]}>
      <Routes>
        <Route path="/documents/:id/read" element={<DocumentReadView />} />
      </Routes>
    </MemoryRouter>
  );
}

describe("DocumentReadView", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders the fetched markdown", async () => {
    vi.mocked(readDocument).mockResolvedValue("# Lastenheft\n\n## 1 Allgemeines\n");
    renderAt("d1");
    await waitFor(() =>
      expect(screen.getByTestId("document-read-content")).toBeInTheDocument()
    );
    expect(readDocument).toHaveBeenCalledWith("d1");
  });

  it("exposes a print action and an export link", async () => {
    vi.mocked(readDocument).mockResolvedValue("# D");
    renderAt("d1");
    await waitFor(() =>
      expect(screen.getByTestId("document-read-print")).toBeInTheDocument()
    );
    expect(screen.getByTestId("document-read-export")).toHaveAttribute(
      "href",
      "/documents/d1/export/?format=markdown"
    );
  });

  it("shows an error banner when loading fails", async () => {
    vi.mocked(readDocument).mockRejectedValue(new Error("boom"));
    renderAt("d1");
    await waitFor(() =>
      expect(screen.getByTestId("document-read-error")).toBeInTheDocument()
    );
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec frontend npx vitest run src/test/DocumentReadView.test.tsx --testTimeout=30000`
Expected: FAIL with `Failed to resolve import "../components/DocumentReadView/DocumentReadView"`

- [ ] **Step 3: Write minimal implementation**

Create `frontend/src/components/DocumentReadView/DocumentReadView.css`:

```css
/*
 * Full-bleed reading surface for the document read mode (Dokument-Sicht spec,
 * section 4) — deliberately not a split view. All values come from
 * styles/tokens.css; no hardcoded colours or sizes.
 */

.document-read {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  padding: var(--space-6);
  max-width: 80ch;
  margin: 0 auto;
  color: var(--color-text-primary);
  background: var(--color-surface);
}

.document-read__toolbar {
  display: flex;
  gap: var(--space-2);
  justify-content: flex-end;
}

.document-read__content {
  line-height: var(--line-height-relaxed);
}

.document-read__error {
  padding: var(--space-3);
  border: 1px solid var(--color-danger);
  border-radius: var(--radius-sm);
  color: var(--color-danger);
}

/* Closes the "kein Druck" gap named in the audit. */
@media print {
  .document-read {
    max-width: none;
    padding: 0;
    background: none;
  }

  .document-read__toolbar {
    display: none;
  }

  .document-read__content h1,
  .document-read__content h2,
  .document-read__content h3 {
    break-after: avoid-page;
  }

  .document-read__content pre,
  .document-read__content table {
    break-inside: avoid;
  }
}
```

Before writing, confirm each custom property exists:
`grep -n "\-\-space-4\|--space-6\|--color-surface\|--color-danger\|--radius-sm\|--line-height-relaxed" frontend/src/styles/tokens.css`. Substitute the nearest existing token for any that is missing — `frontend/src/test/design-tokens.test.ts` fails on unknown properties.

Create `frontend/src/components/DocumentReadView/DocumentReadView.tsx`:

```typescript
/**
 * Full-screen read mode for a living specification document.
 *
 * Renders the numbered Markdown produced by GET /documents/<id>/read/ and
 * offers browser print (the @media print rules live in the sibling CSS) plus
 * a Markdown download. No inline styles — the ui-ratchet test forbids new
 * `style={{` literals under components/.
 */
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";

import { documentExportUrl, readDocument } from "../../api/documents";
import { MarkdownPreview } from "../RequirementEditors/MarkdownPreview";
import "./DocumentReadView.css";

export function DocumentReadView(): JSX.Element {
  const { id } = useParams<{ id: string }>();
  const { t } = useTranslation();
  const [markdown, setMarkdown] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(true);

  useEffect(() => {
    if (!id) {
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    readDocument(id)
      .then((content) => {
        if (!cancelled) {
          setMarkdown(content);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setError(t("documents.readError"));
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [id, t]);

  if (error !== null) {
    return (
      <div className="document-read">
        <p className="document-read__error" data-testid="document-read-error">
          {error}
        </p>
      </div>
    );
  }

  return (
    <div className="document-read" data-testid="document-read">
      <div className="document-read__toolbar">
        <button
          type="button"
          onClick={() => window.print()}
          data-testid="document-read-print"
        >
          {t("documents.print")}
        </button>
        <a
          href={id ? documentExportUrl(id) : "#"}
          download
          data-testid="document-read-export"
        >
          {t("documents.exportMarkdown")}
        </a>
      </div>
      <div className="document-read__content" data-testid="document-read-content">
        {loading ? (
          <p data-testid="document-read-loading">{t("loading")}</p>
        ) : (
          <MarkdownPreview value={markdown} />
        )}
      </div>
    </div>
  );
}
```

Confirm the `MarkdownPreview` export shape and prop name with
`grep -n "export\|Props" frontend/src/components/RequirementEditors/MarkdownPreview.tsx`; if it is a default export or takes a differently named prop, adapt the import and usage. Confirm `t("loading")` resolves (it is a top-level locale key).

Add the route in `frontend/src/components/NavigationShell/NavigationShell.tsx` next to the other routes:

```typescript
              <Route path="/documents/:id/read" element={<DocumentReadView />} />
```

plus the matching import.

Add to `frontend/src/i18n/locales/de.json` (nested object, never dotted keys):

```json
  "documents": {
    "print": "Drucken",
    "exportMarkdown": "Als Markdown exportieren",
    "readError": "Das Dokument konnte nicht geladen werden."
  },
```

and to `frontend/src/i18n/locales/en.json`:

```json
  "documents": {
    "print": "Print",
    "exportMarkdown": "Export as Markdown",
    "readError": "The document could not be loaded."
  },
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec frontend npx vitest run src/test/DocumentReadView.test.tsx src/test/i18n-parity.test.ts src/test/ui-ratchet.test.ts src/test/design-tokens.test.ts --testTimeout=30000`
Expected: PASS — the three view tests plus the i18n parity, UI ratchet and design-token gates (the ratchet proves no new inline style was introduced)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/DocumentReadView/ frontend/src/components/NavigationShell/NavigationShell.tsx frontend/src/i18n/locales/de.json frontend/src/i18n/locales/en.json frontend/src/test/DocumentReadView.test.tsx
git commit -m "feat: add document read mode with print stylesheet"
```

---

## Task 17: Integrationslauf und Abschluss

**Files:**
- Test: alle in diesem Plan berührten Verzeichnisse

**Interfaces:**
- Consumes: Tasks 1-16
- Produces: nichts (Verifikationsschritt)

- [ ] **Step 1: Frontend nach jeder Änderung neu starten**

Vite hat auf Windows kein funktionierendes HMR — ohne Neustart testet ein E2E-Lauf stillschweigend alten Code.

Run: `docker compose restart frontend`
Expected: Container läuft, `docker compose logs --tail=20 frontend` zeigt einen frischen Vite-Start

- [ ] **Step 2: Backend-Module der geänderten Dateien gezielt laufen lassen**

Run: `docker compose exec backend pytest application/ baseline/ rest_api/tests/test_document_api.py mcp_server/tests/test_document_tool_group.py traceability/ -v`
Expected: PASS — keine neuen Fehlschläge gegenüber dem Baseline-Stand vor Task 1. Der vollständige sequenzielle Backend-Lauf bleibt der CI überlassen.

- [ ] **Step 3: Frontend-Suite laufen lassen**

Run: `docker compose exec frontend npx vitest run --testTimeout=30000`
Expected: PASS bis auf die lokal bekannten, in CI grünen Vorab-Fehlschläge. Vor Task 1 einmal `npx vitest run` laufen lassen und die Fehlerliste festhalten, damit "neu" von "vorbestehend" unterscheidbar ist.

- [ ] **Step 4: Lesemodus im Browser tatsächlich ansehen**

Run: `docker compose exec backend python manage.py seed_demo`, dann im Browser `http://localhost:5173/documents/<id>/read` öffnen (id aus `GET /api/v1/documents/?workspace_id=<ws>`), ein Dokument mit mindestens zwei Sektionen und einer Kindsektion anlegen.
Expected: Nummerierung 1, 1.1, 1.2, 2 sichtbar; Druckvorschau (Strg+P) zeigt die Toolbar nicht und bricht Überschriften nicht vom Folgeabsatz ab.

- [ ] **Step 5: OpenAPI-Schema gegenprüfen**

Run: `docker compose exec backend python manage.py spectacular --file /tmp/schema.yaml && docker compose exec backend grep -c "documents" /tmp/schema.yaml`
Expected: Exit-Code 0 ohne neue drf-spectacular-Warnungen zu `DocumentViewSet`; die `documents/`-Pfade tauchen im Schema auf.

---

## Self-Review

**1. Spec-Abdeckung.** Abschnitt 3 (Datenmodell) → Tasks 1/2. Abschnitt 4 (Lesemodus, geteilter Renderer, Nummerierung, Route, `@media print`) → Tasks 3/8/16. Abschnitt 5 (Markdown-Export, kein neuer Dependency) → Task 12. Abschnitt 6 (Baseline-Bindung, `_resolve_document()` erweitert statt ersetzt, Migration) → Tasks 9/10/11/13. Abschnitt 7 (REST + MCP) → Tasks 12/13/14. Abschnitt 8 (Migration, 4 Schritte) → Tasks 1/2 (1.), 10 (2.), 12/14 (3.), 16 (4.). Abschnitt 9 Risiko 1 (live vs. eingefroren) → im Docstring von `read_document` und im REST-`read`-Docstring festgehalten. Risiko 2 (Zyklus) → Task 5, drei Tests. Risiko 3 (Dry-Run vor Rollout) → OFFENE FRAGE 2 und der Migrations-Docstring in Task 10. Snapshot/Diff/`VersionReconstructor` bleiben unangetastet — keine Task berührt sie.

**2. Placeholder-Scan.** Kein "TBD"/"TODO", kein "similar to Task N", kein "add error handling" ohne Code. Jeder Testblock ist lauffähiger Code, jede Implementierung ist vollständig ausgeschrieben. Die sechs "vor dem Start prüfen"-Hinweise (Fixture-Namen in Tasks 4/6/7, `TenantContext`-API in Task 9, `BaseToolGroup`-Dispatch in Task 14, Token-Namen und `MarkdownPreview`-Props in Task 16, `format`-Parameter in Task 12) sind ausdrücklich keine Platzhalter: sie nennen den exakten Verifikationsbefehl und die Anpassung, falls die Annahme nicht hält.

**3. Typ-Konsistenz.** `render_artifact_markdown(row: dict, heading_level: int) -> str` (Task 3) wird in Task 8 und im Ausblick auf MCP `resources/read` mit genau dieser Signatur benutzt. `resolve_section_rows -> list[dict]` (Task 7) speist `_render_sections` (Task 8) und `resolve_document_artifact_ids -> list[str]` (Task 7) speist `_resolve_document_object` (Task 9). `document_object_id: Optional[UUID]` behält den Typ über `ScopeResolver.resolve` → `DeltaIndexBuilder.build` → `baseline.services.build` → `BaselineFacade.create_baseline`; nur an der REST-Grenze (Task 13) und im MCP-Schema ist es ein String, dort jeweils mit explizitem `UUID(str(...))`-Guard. `BaselineMetadata.root_artifact_id`/`document_object_id` (Task 10) korrespondieren mit `BaselineSnapshot.artifact_id`/`document_id`. Frontend: `readDocument -> Promise<string>` passt zu `useState<string>`; `DocumentSectionContentType` ist mit den drei Backend-`CONTENT_TYPE_*`-Konstanten identisch.
