---
adr_id: ADR-026
title: "Dokument-Artefakt mit eigenem Lebenszyklus"
status: proposed
date: 2026-11-02
deciders: [user, documenter]
affected_reqs: [REQ-L2-PL-004, REQ-L2-PL-005, REQ-L2-PL-009, REQ-L2-PL-010, REQ-L2-TE-001]
superseded_by: null
type: ADR
scope: documents
author_agent: documenter
---

# ADR-026: Dokument-Artefakt mit eigenem Lebenszyklus

**Status:** proposed (Entwurf 2026-11-02). Der Wechsel auf `accepted` ist eine
Nutzerentscheidung und nicht Teil dieses Dokuments.
**Entscheider:** `user`; **Text:** `documenter` (Rollen laut ENT-X4 = A).
**Betroffene REQs:** REQ-L2-PL-004 (Entitäten/Schema), REQ-L2-PL-005 (Auditfelder),
REQ-L2-PL-009 (on_delete-Regeln), REQ-L2-PL-010 (RLS), REQ-L2-TE-001 (TraceLink-Verwaltung).
**Bezug:** Issue #1374; Konzept `docs/concepts/2026-10-16-dokument-artefakte-workitem.md`;
Plan F `docs/plans/Archive/2026-10-21-plan-f-dokumente-baselines.md` §WP F2; Entscheidungen
ENT-F0/F2/F4/F5 in `docs/plans/2026-10-21-entscheidungen-offen.md` §0b.
**Design:** `docs/superpowers/specs/Archive/2026-11-02-f2-document-design.md`.

---

## Kontext

**1. Das Problem.** Dokumente (Specs, Pläne, Audit-Berichte, Konzepte) leben heute als
Markdown-Dateien in Repositories. Sie haben dort weder eine stabile Identität im
Artefaktgraphen noch einen Lebenszyklus, keinen Feld-Freeze nach Freigabe und keine
Kanten zu den Requirements, die sie beschreiben. `Baseline.scope="document"` existiert
zwar als Name, löst aber nur einen beliebigen `Artifact.parent`-Teilbaum auf; ein
eigenständiges Dokumentobjekt gibt es nicht.

**2. Die vorhandene Maschinerie.** `persistence.Artifact` trägt bereits Identität,
Workspace, `lifecycle_status` (das einzige Soft-Delete-Flag), Auditfelder und die
TraceLink-Fähigkeit. Spezialisierte Artefakttypen (`Requirement`, `Adr`, `Risk`, …)
besitzen je eine eigene Tabelle mit `OneToOne(Artifact)`, lokalem `uid` (G1.1/G1.3) und
einer RLS-Policy. Die Workflow-Engine liefert Zustände und Übergänge als
`item_type`-konfigurierbare Schemas. Das Konzept verlangt ausdrücklich „kein neuer
Workflow-Mechanismus".

**3. Der Namenskonflikt.** Die alte Dokumentensicht-Spec (2026-09-03) definiert ebenfalls
ein `Document` — aber als schreibgeschützte Sicht mit `DocumentSection`-Untergliederung,
ohne Lifecycle und ohne Freeze. ENT-F2 = b entscheidet die Koexistenz: Das #1374-Artefakt
behält den Namen `Document`, die Sicht wird zur **`DocumentView`** (schreibgeschützte
Projektion). `Baseline.scope="document"` akzeptiert zusätzlich ein `Document`
(Dokument + `decomposes`-Kinder).

**4. Der Umfang.** F2 baut das Artefakt und seinen Lifecycle. Projektion, Adoption und
Source-Bindung sind nach ENT-F5 = a ein eigenes WP F5. Das ADR entscheidet daher nur
das Artefakt-Rückgrat, nicht den `.md`-Generator.

## Alternativen

### (a) Nur `Artifact` mit `artifact_type="Document"` — VERWORFEN

**Beschreibung:** Kein eigenes Modell; ein Dokument ist eine `Artifact`-Zeile mit dem
Typ-String `Document`, Inhalt und Metadaten in `custom_fields`.

**Abwägung:** Verworfen. `Artifact` ist bewusst die gemeinsame Hülle, nicht der Inhalt:
Titel, `kind`, Markdown-Body, `frozen_at`/`frozen_fields` und `doc_date` wären
untypisierte JSON-Werte ohne Constraints, ohne Index und ohne Feld-Freeze auf
DB-Ebene. Der UID-Mechanismus (G1.1) und `ARTIFACT_TYPE_MODELS` erwarten ein Modell mit
`artifact`-FK. Eine Lifecycle-Integration wäre möglich, aber jede Schreibprüfung müsste
auf untypisierte Felder zugreifen — genau die Klasse Fehler, die die
Datenmodell-Konsolidierung beseitigt hat.

**Risiko:** HOCH — Datenintegrität und Freeze wären nur in Anwendungscode durchsetzbar,
nicht im Schema.

### (b) Die Dokumentensicht-Spec übernehmen (`Document` + `DocumentSection`) — VERWORFEN

**Beschreibung:** Das neue Artefakt ist das `Document` der Sicht-Spec; Abschnitte werden
`DocumentSection`-Zeilen mit `content_type` (query/fixed/subtree).

**Abwägung:** Verworfen. Die Sicht-Spec ist eine **Lese-/Projektionsidee**: Sie
beschreibt, wie vorhandene Artefakte als Dokument dargestellt werden, nicht wie ein
Dokument entsteht, freigegeben und eingefroren wird. Ihre `DocumentSection`-Mechanik
(Filter-DSL, fixe Listen, Subtree) ist eine Funktion der späteren `DocumentView`, nicht
des Artefakts. Ein Zusammenlegen würde zwei Achsen (Inhalt vs. Darstellung) in ein Modell
zwingen und den Lifecycle an eine UI-Spezifikation koppeln, die nie implementiert wurde.

**Risiko:** MITTEL — die Sicht-Funktionen würden den Artefakt-Kern verwässern; die
spätere Projektion (F5) müsste gegen ein falsches Modell bauen.

### (c) Eigenes `Document`-Artefakt in `persistence`, `DocumentView` bleibt Sicht — GEWÄHLT

**Beschreibung:** `Document(TenantScopedModel)` in `persistence/models.py`, Tabelle
`pl_document`, `OneToOne(Artifact)` als Rückgrat, `workspace`-FK, lokale `uid`
`DOC-NNN`, `kind`, `title`, `description`, Markdown-`body`, `doc_date`,
`frozen_at`/`frozen_fields`, geerbtes `version`. Zustand ausschließlich in
`WorkflowItemState`; Soft-Delete ausschließlich über `Artifact.lifecycle_status`;
RLS-Policy im selben PR wie die Tabelle.

**Abwägung:** Folgt dem Hausmuster aller anderen Artefakttypen und erfüllt die
Konzept-Anforderungen (Lifecycle, Freeze, Link-Fähigkeit, UID, RLS) ohne einen zweiten
Mechanismus. Der Name `Document` bleibt für das Artefakt reserviert; die schreibgeschützte
Sicht heißt `DocumentView` und wird später als Frontend/Projektion gebaut. Preis: ein
weiteres Modell und eine weitere Tabelle — dafür sind alle Constraints (UID-Eindeutigkeit,
`kind`-Check, RLS, Cascade) deklarativ.

**Risiko:** NIEDRIG — additiv, reversibel, ohne Änderung an `Artifact` oder bestehenden
Typen.

## Entscheidung

**Entschieden: Das Dokument wird ein eigenes Artefakt `Document` in `persistence`, mit
`Artifact`-Rückgrat, Workflow-Zustand in `WorkflowItemState` und RLS im selben Release.**

**R1 — Modell und Tabelle.** `persistence.models.Document` mit `db_table="pl_document"`,
`artifact = OneToOneField(Artifact, on_delete=CASCADE, related_name="document")`,
`workspace = ForeignKey(Workspace, on_delete=CASCADE, related_name="documents")`
(nicht null; `ArtifactWorkspaceMirrorMixin` füllt sie aus dem Artefakt). Keine Änderung an
`persistence.Artifact`.

**R2 — Felder.** `uid`, `title` (255), `kind` (`Spec`, `Plan`, `AuditReport`, `Review`,
`Conclusion`, `Concept`, `Guide`), `description`, `body` (Markdown), `doc_date`,
`frozen_at`, `frozen_fields` (JSON-Liste), geerbtes `version` als Optimistic-Lock.
**Kein** `lifecycle_state`-Feld; der Zustand lebt in `WorkflowItemState` und wird als
`status` ausgeliefert (Hausmuster, REQ-143).

**R3 — Lokale Identität.** `uid` ist `DOC-NNN`, atomar je Workspace über `UidSequence`
vergeben, mit partieller Unique-Constraint `uq_document_workspace_uid`. Die
Konzept-Form `doc:<repo>:<pfad>` ist Herkunftsidentität und gehört zu ENT-F5; sie wird
nicht mit dem lesbaren Identifier vermischt.

**R4 — Lebenszyklus und Freeze.** Zustände `Entwurf → In Prüfung → Freigegeben →
Abgelöst` plus `Archiviert`; der Eintritt in `Freigegeben` setzt `frozen_at` und
`frozen_fields = ["title","description","body","kind"]`. Ein Schreibversuch auf ein
eingefrorenes Feld endet mit `409 FIELD_FROZEN`; die Freigabe-Erkennung läuft über
`state_meta.freeze_on_enter`, nicht über `_APPROVAL_TARGET_STATES`. Freigabe-Gates
G-1…G-4 werden als Vorbedingungsregel umgesetzt.

**R5 — RLS.** `pl_document` erhält `ENABLE` + `FORCE ROW LEVEL SECURITY` und eine
Tenant-Isolations-Policy in derselben Release wie die Tabelle (KA-F-13). Ein nicht
gesetztes `app.current_tenant` matcht keine Zeile (fail-closed).

**R6 — Link-Fähigkeit.** Das Artefakt ist TraceLink-Endpunkt über das `Artifact`-Rückgrat.
F2 führt genau drei Link-Typen ein (`documented-in`, `evidences`, `depends-on`) und
erweitert `references` additiv um `Document`; die Kind-Einschränkung von `evidences` läuft
über das generische Subtyp-Register (`Document:<kind>`). Diese Typen sind F2-T3, nicht
Teil des Modell-PRs.

**R7 — Soft-Delete.** Einziges Flag bleibt `Artifact.lifecycle_status` (G1.5 V1).
`Document` hat kein eigenes Statusfeld; `DELETE`/`GET`/`reactivate` folgen dem
V1–V6-Vertrag über die vorhandenen Mixins.

**R8 — ETag.** `Document` ist ETag-fähig: `version` + `expected_version` +
`optimistic_lock_response`. Ein Konflikt endet mit `412`/`409`, nie mit stillem
Last-Write-Wins.

**R9 — Scopes.** ENT-F4 = a: `documents:read` → `read_only`, `documents:write` →
`author`, `documents:project`/`documents:adopt` → `admin`. Keine `ApiKey`-Schemaänderung.

**R10 — Abgrenzung F5.** Projektion, Adoption, Source-Bindung und `owner_mode` sind
ENT-F5 = a (eigenes WP). Bis dahin sind F-4/F-7/G-3 inert spezifiziert; `Closes #1374`
erfolgt erst mit dem F5-PR.

**R11 — Baseline-Scope.** `Baseline.scope="document"` akzeptiert künftig zusätzlich ein
`Document` (Dokument + `decomposes`-Kinder). Das ist ein Vertrag für F4, nicht Teil des
F2-Modells.

## Konsequenzen

**Positiv:**

- Dokumente werden vollwertige Artefakte: identifizierbar, verlinkbar, baseline-fähig,
  auditierbar, mit einem Freigabestand, der nicht still überschrieben werden kann.
- Alle Integritätszusagen (UID-Eindeutigkeit, `kind`-Check, RLS, Cascade) liegen im
  Schema, nicht nur im Anwendungscode.
- Kein zweiter Workflow-, Soft-Delete- oder Link-Mechanismus; `Document` erbt die
  vorhandenen Pfade und bleibt mit ihnen kompatibel.
- Die Trennung von Artefakt (`Document`) und Sicht (`DocumentView`) hält die späteren
  Projektionsarbeiten (F5) aus dem Datenmodell heraus.

**Negativ:**

- Eine weitere Tabelle und ein weiterer Typ in allen fünf Item-Typ-Registries; jede
  künftige Oberfläche (Suche, Baum, Baseline, Attribute) muss `Document` mitführen —
  der Preis der Vollständigkeit.
- Bis F2-T4 gibt es keinen Service: Das Modell ist direkt per ORM erreichbar, aber
  Freeze und Gates sind noch nicht durchsetzbar. Das ist bewusst sequenziert und im
  Spec §12 dokumentiert.
- Das Konzept nennt `doc:<repo>:<pfad>` als `uid`; die lokale `DOC-NNN`-Form weicht
  davon ab. Die Abweichung ist bewusst (Hausmuster G1.1) und wird erst mit der
  Source-Bindung (F5) um die Herkunftsidentität ergänzt.
- `workspace` ist nicht null. Pfade, die nur ein `artifact` setzen, verlassen sich auf
  den Mixin; ein künftiger `bulk_create`-Pfad müsste die Spalte selbst füllen.
