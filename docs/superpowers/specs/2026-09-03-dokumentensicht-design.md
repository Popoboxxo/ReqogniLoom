# Dokument-Sicht — Design

**Status:** Draft, pending user review
**Quelle:** `docs/SYSTEMAUDIT_2026-09-02_GROB.md`, Kap. Q1.4 ("Der UI-Leitgedanke heißt
'lebendes Spezifikationsdokument'"). Zehnte von mehreren unabhängigen Folge-Specs aus
demselben Audit — baut auf
[2026-09-03-tabellenansicht-design.md](2026-09-03-tabellenansicht-design.md)
(Filter-DSL für dynamische Sektionen) und
[2026-09-03-mcp-modernisierung-design.md](2026-09-03-mcp-modernisierung-design.md)
(gemeinsamer Markdown-Renderer für Lesemodus und `resources/read`).

## 1. Problem

Der UI-Leitgedanke des Produkts ("lebendes Spezifikationsdokument") hat kein Gegenstück
im Datenmodell. Kein Dokument-Objekt, keine Kapitelstruktur, kein Lesemodus, kein Druck.
`Baseline.scope="document"` existiert als Name, aber löst in Wahrheit nur den
Artefakt-Teilbaum unter einer beliebigen Root-`artifact_id` auf (`_resolve_document()`,
`baseline/delta_index_builder.py:74-77`) — kein echtes Dokument-Objekt dahinter. Export
ist PDF-Report und ReqIF, kein Lastenheft mit Nummerierung. Für Mid-Market-SE ist das
Dokument das Lieferobjekt an Kunden und Auditoren.

## 2. Ziel

Ein echtes `Document`-Objekt mit Kapitelstruktur, ein Lesemodus, Markdown-Export mit
Nummerierung, und `Baseline.scope="document"` an dieses Objekt gebunden statt an eine
beliebige Artefakt-ID.

## 3. Datenmodell

```python
class Document(TenantScopedModel):
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE)
    title = models.CharField(max_length=255)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class DocumentSection(TenantScopedModel):
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="sections")
    # Optionale Verschachtelung (1, 1.1, 1.1.1, ...) — dasselbe Muster wie Artifact.parent.
    parent_section = models.ForeignKey("self", on_delete=models.CASCADE, null=True, blank=True, related_name="children")
    title = models.CharField(max_length=255)
    order = models.IntegerField(default=0)
    content_type = models.CharField(max_length=16, choices=[
        ("query", "Query"), ("fixed", "Fixed List"), ("subtree", "Artifact Subtree"),
    ])
    # content_type="query": dieselbe Filter-DSL wie SavedView (Tabellenansicht-Spec,
    # Abschnitt 4.1) — {"item_type": ..., "filters": {...}, "sort": [...]}.
    query = models.JSONField(null=True, blank=True)
    # content_type="fixed": explizit kuratierte, geordnete Artefakt-Liste.
    fixed_artifact_ids = models.JSONField(default=list, blank=True)
    # content_type="subtree": deckt den heutigen Baseline-Verhalten ab (Artifact.parent-Baum).
    subtree_root_artifact = models.ForeignKey("persistence.Artifact", on_delete=models.SET_NULL, null=True, blank=True)
```

**Drei Wiederverwendungen statt drei neuer Mechanismen:** `query` ist exakt die
Filter-DSL aus der Tabellenansicht-Spec (kein zweites Filter-Format), `subtree` bewahrt
das heutige Baseline-Document-Scope-Verhalten für die Migration (Abschnitt 6),
`parent_section` ist dasselbe Selbstreferenz-Muster wie `Artifact.parent`
(Datenmodell-Konsolidierung-Spec-Kontext).

## 4. Lesemodus

`GET documents/<id>/read` — löst alle Sektionen (rekursiv über `parent_section`) in
`order` auf, jede referenzierte Query/Fixed-Liste/Subtree-Section liefert eine geordnete
Artefaktliste. Jedes Artefakt wird über denselben Markdown-Renderer dargestellt, den
`McpArtifactProvider` (MCP-Modernisierung-Spec, Abschnitt 4: `resources/read`) bereits
für Artefakt-Markdown nutzt — ein Renderer, zwei Zugriffswege (MCP-Resource,
REST-Lesemodus), keine zweite Implementierung.

**Nummerierung:** hierarchisch nach Sektions- und Artefakt-Reihenfolge (1, 1.1, 1.2, 2,
...), analog einer klassischen Lastenheft-Gliederung.

**Route:** `/documents/<id>/read` im Frontend — Vollbild-Lesefläche statt Split-View,
mit `@media print`-optimiertem Stylesheet (schließt die im Audit genannte Lücke "keinen
Druck").

## 5. Export

Markdown-Download der Lesemodus-Ausgabe (`GET documents/<id>/export?format=markdown`) —
kein neuer Dependency, reine Serialisierung des bereits gerenderten Lesemodus-Inhalts.
DOCX-Export (bräuchte `python-docx`, neuer Dependency) ist eine natürliche
Folge-Erweiterung, nicht Teil dieser Spec — Markdown erfüllt "Export als DOCX **oder**
Markdown" aus dem Audit-Wortlaut bereits.

## 6. Baseline-Bindung

`Baseline.scope="document"` referenziert künftig eine echte `Document.id` statt einer
beliebigen `artifact_id` — `document_id`-Parameter in
`baseline/delta_index_builder.py`/`baseline/services.py` wird zur echten
Document-Fremdreferenz. `_resolve_document()` löst alle Sektionen eines Dokuments auf
(Query + Fixed + Subtree kombiniert, dedupliziert) statt nur einen einzelnen Teilbaum —
Erweiterung der bestehenden Resolver-Funktion, kein Ersatz der Baseline-Infrastruktur
selbst (Snapshot, Diff, `VersionReconstructor` bleiben unverändert).

**Migration bestehender Document-Scope-Baselines:** für jede vorhandene
`scope="document"`-`BaselineSnapshot`-Historie mit einer Root-`artifact_id` wird ein
neues `Document` mit genau einer `subtree`-Sektion erzeugt, die diese Root-Artifact-ID
kapselt — Kontinuität ohne Funktionsverlust, alte Baselines bleiben unter ihrer neuen
`document_id` referenzierbar.

## 7. REST/MCP

**REST:** `GET/POST/PATCH/DELETE documents/`, `documents/<id>/sections/` (CRUD, Reorder),
`documents/<id>/read/`, `documents/<id>/export/`.
**MCP:** `document.list`, `document.get`, `document.read` (liefert denselben
Lesemodus-Markdown) — ein Agent kann ein Dokument als Ganzes lesen, nicht nur Artefakt für
Artefakt.

## 8. Migration

Additiv bis auf die Baseline-Umbindung (Abschnitt 6):

1. `Document`, `DocumentSection` als neue Tabellen.
2. `Baseline.document_id` von "beliebige Artifact-ID" auf echte `Document`-FK umstellen,
   inkl. Migration bestehender Zeilen (Abschnitt 6).
3. `documents/*`-REST-Routen, `document.*`-MCP-Tool-Gruppe.
4. Lesemodus-Route + `@media print`-Stylesheet im Frontend.

## 9. Risiken

- **`query`-Sektionen sind zur Lesezeit ausgewertet**, nicht zum Zeitpunkt der
  Dokumenterstellung — ein Dokument "lebt" (neue passende Artefakte tauchen automatisch
  auf), was dem Leitgedanken entspricht, aber bedeutet: zwei Aufrufe von
  `documents/<id>/read` im Abstand können unterschiedliche Ergebnisse liefern. Für eine
  stabile Momentaufnahme ist genau dafür die Baseline-Bindung (Abschnitt 6) da — Lesemodus
  ohne Baseline ist bewusst "live", nicht eingefroren.
- **Rekursive `parent_section`** ohne Tiefenbegrenzung könnte theoretisch einen Zyklus
  bekommen (Sektion A als Parent von B, B als Parent von A) — braucht eine
  Zyklus-Prüfung beim Speichern, analog zur bestehenden `TraceLink`-Zyklenprüfung
  ("Cycle detected", Kap. U1).
- **Migration bestehender Document-Scope-Baselines** (Abschnitt 6) betrifft
  Produktivdaten — Dry-Run gegen eine Kopie vor dem Rollout, wie bei den anderen
  harten Migrationen dieser Spec-Reihe.
