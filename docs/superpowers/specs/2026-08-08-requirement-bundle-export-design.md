# Requirement Bundle Export — Design

**Status:** Approved by user, ready for implementation planning
**Date:** 2026-08-08

## 1. Ziel

Eine flexible Schnittstelle zur gebündelten Ausgabe von Systemanforderungen
und -strukturen, gruppiert nach Architektur-Elementen, nutzbar über UI, REST
API und MCP (LLM-Agenten). Ziel ist es, sowohl Menschen (UI) als auch
externen Systemen (REST) als auch KI-Agenten (MCP) einen einzigen,
konsistenten Weg zu geben, "alle Requirements zu System/Komponente X" —
wahlweise roh oder KI-komprimiert für Token-Effizienz — abzurufen.

## 2. Gruppierung: `ALLOCATED_TO`-Trace-Links

Requirements werden Architektur-Elementen über den bestehenden Trace-Link-Typ
`ALLOCATED_TO` zugeordnet (`Requirement → ArchitectureElement`,
`ArchitectureElement → ArchitectureElement` für Subsystem-Zuordnung). Dies
ist die semantische, nicht die strukturelle (`parent_id`-Artifact-Baum)
Beziehung — bewusste Entscheidung, da `ALLOCATED_TO` das V-Modell-Allokations-
Muster (L0-L4) abbildet, während `parent_id` für andere Zwecke (z.B.
Requirement-Dekomposition) genutzt wird.

## 3. Scope: Tiefenparameter statt zwei fester Modi

Statt zweier getrennter Modi ("Knoten-Ebene" vs. "System-Ebene komplett")
gibt es einen einzigen `depth`-Parameter:

- `depth=0`: nur die Requirements, die direkt am gewählten Root-Knoten
  per `ALLOCATED_TO` hängen.
- `depth=N`: zusätzlich alle Requirements der Subsysteme, die (rekursiv via
  `ALLOCATED_TO` Arch→Arch) bis zur Tiefe N unter dem Root liegen.
- `depth=full` (oder `null`): komplette Hierarchie, unbegrenzt (mit
  System-Cap, siehe §7).

Jeder Requirement-Eintrag im Ergebnis trägt an, unter welchem
Architektur-Knoten er gefunden wurde (Pfad/Zuordnung), damit die Hierarchie
im flachen Ergebnis nicht verloren geht.

## 4. Attribut-Filterung: drei Modi + Discovery-Endpoint

- **`all`**: alle Attribute des Requirements.
- **`visible`**: nur die Attribute, die laut bestehender
  `AttributeVisibilityConfigService`-Konfiguration im aktuellen Workspace
  sichtbar sind (REQ-066).
- **`custom`**: explizite Feldliste im Request (`fields=title,status,...`).
  Unbekannte Feldnamen → `400` mit Angabe der ungültigen Felder.

**Neuer Discovery-Endpoint** (`attribute_schema` — REST + MCP): listet pro
Artefakttyp alle verfügbaren Attribute mit Typ, Beschreibung und
Workspace-Sichtbarkeits-Flag. Wird als reine Lese-Erweiterung von
`AttributeVisibilityConfigService` umgesetzt (kein neuer Service), damit
sowohl UI-Formulare als auch MCP-Agenten vorab wissen, welche Felder für
`custom` zur Verfügung stehen.

## 5. Ausgabemodi

### Raw

1:1-Ausgabe der gefilterten Daten, kein LLM-Beteiligung. Formate:

- **JSON** (Default) — für REST-Clients, MCP-Rohantworten, UI-Konsum.
- **Markdown** — hierarchische, tokenarme Darstellung.
- **CSV** — nur für flache Requirement-Listen sinnvoll (ein Datensatz pro
  Requirement inkl. Spalte für den zugehörigen Architektur-Pfad); bei
  `depth>0` mit mehreren Knoten entsprechend denormalisiert.

### Compressed (KI-gestützt)

Das Rohergebnis durchläuft eine KI-gestützte Komprimierung mit dem Ziel
maximaler Token-Effizienz bei absoluter inhaltlicher Treue (kein
Informationsverlust an Kerninhalten, keine Halluzination). Default-Format
für komprimierte Ausgabe ist **Markdown** (passt zum
Token-Optimierungsziel; JSON-Syntax-Overhead wäre hier kontraproduktiv).

Zwei Ausführungsmodi, beide unterstützt:

- **Synchron**: Kompression läuft im selben Request, Antwort enthält das
  fertige Ergebnis. Für MCP-Agenten und kleine/mittlere Scopes gedacht.
- **Asynchron**: Request liefert sofort eine Job-ID zurück (`202`), Ergebnis
  wird über den bestehenden Polling-Mechanismus (wie andere
  LLM-Hintergrund-Operationen im System) abgerufen. Für große Scopes.

Ein System-Guard (konfigurierbare Grenze über Requirement-Anzahl/Token-
Schätzung) erzwingt asynchron statt synchron, wenn der Scope zu groß für
eine sinnvolle synchrone Antwortzeit ist.

### Caching (compressed)

Kompression ist teuer (Zeit, Geld) — Ergebnisse werden gecacht. Cache-Key:

```
hash(root_id, depth, filter_mode, fields, format)
  + hash(sortierte Liste [(artifact_id, version), ...] aller im Bundle
    enthaltenen Requirements UND Architektur-Elemente)
```

Der zweite Hash nutzt das bereits im System vorhandene
`AuditableModel.version`-Feld (Versions-Zähler, erhöht sich bei jeder
Feld-Änderung — bereits produktiv genutzt für optimistisches Locking).
Ändert sich irgendein im Bundle enthaltenes Artefakt, ändert sich der
Hash → Cache-Miss → Neukompression. Ein aus dem Bundle entferntes
(soft-deleted/outdated) Artefakt zählt ebenfalls als Invalidierungs-Trigger
(nicht nur Versionssprünge lebender Artefakte).

Speicherung: Redis (bereits vorhandene Infrastruktur, kein neuer Dienst).

## 6. Architektur: zwei getrennte Services

**`RequirementBundleQueryService`** (`backend/application/`) — reine
Datenaggregation, kein LLM-Zugriff:

- Rekursiver `ALLOCATED_TO`-Walk ab Root-`ArchitectureElement`, begrenzt
  durch `depth`.
- Attribut-Filterung (drei Modi).
- Serialisierung nach JSON/Markdown/CSV.

**`BundleCompressionService`** (`backend/application/`) — nur
LLM/Cache-Zuständigkeit:

- Nimmt das Rohergebnis von `RequirementBundleQueryService` entgegen.
- Cache-Lookup (Hit → sofort zurück).
- Bei Miss: holt den passenden `PromptTemplate` über den bestehenden
  Phase-4-Lookup-Mechanismus (Global-Default + Workspace-Override, wie die
  7 existierenden AI-Derive-Methoden) — **kein hartkodierter Prompt-String
  im Code**. Neuer PromptTemplate-Typ, z.B. `bundle_compression`.
- Ruft den LLM-Adapter auf (bestehende Capability-Abstraktion, ADR-02,
  graceful degradation wenn kein Provider konfiguriert).
- Schreibt Ergebnis in den Cache.

Begründung für die Trennung in zwei Services statt eines gemeinsamen: klare
Verantwortungsgrenze zwischen reiner Datenabfrage (testbar ohne LLM-Mocking)
und KI-Orchestrierung (testbar ohne Datenbank-Fixtures) — explizite
Nutzerentscheidung gegen die anfangs vorgeschlagene Ein-Service-Lösung.

**Wichtig:** Der `bundle_compression`-PromptTemplate muss zwingend in der
bestehenden Prompt-Template-Übersicht (Frontend, Phase-4-UI) sichtbar sein,
zur Systemlaufzeit editierbar und workspace-spezifisch überschreibbar sein —
identisches Verhalten zu den 7 bestehenden Derive-Prompt-Typen, keine
Sonderbehandlung.

## 7. API-Oberfläche

### REST

```
GET /api/v1/architecture-elements/{id}/requirement-bundle/
    ?depth=<int|full>
    &filter_mode=<all|visible|custom>
    &fields=<comma-list>        (nur bei filter_mode=custom)
    &format=<json|markdown|csv>
    &mode=<raw|compressed>
    &async=<bool>                (nur bei mode=compressed relevant)

GET /api/v1/attribute-schema/
    ?artifact_type=<optional>
```

### MCP (neue Tool-Gruppe `requirement_bundle.*`)

```
requirement_bundle.export(root_id, depth, filter_mode, fields, format, mode)
requirement_bundle.attribute_schema(artifact_type?)
```

Erfordert Ergänzung von `.claude/rules/mcp-reqogniloom.md` (erlaubte
Tool-Liste) — Governance-Schritt, kein Code-Bestandteil dieses Plans.

### UI

Lazy-Load-Panel/Modal in der bestehenden Architecture View, pro
ausgewähltem Knoten aktivierbar. **Kein Fetch beim Öffnen der Architecture
View selbst** — Daten werden erst geladen, wenn der Nutzer das Panel für
einen konkreten Knoten aktiviert. Zwingend für Skalierbarkeit bei Systemen
mit mehreren tausend Architektur-Elementen. Controls für Tiefe, Filter-Modus,
Format, Raw/Compressed.

## 8. Fehlerbehandlung & Grenzfälle

| Fall | Verhalten |
|---|---|
| Root-Knoten nicht gefunden / kein `ArchitectureElement` | `404` |
| `depth` überschreitet System-Cap | Cap analog zum bestehenden `get_tree`-CTE-Limit (Tiefe 20), verhindert Runaway-Queries bei pathologischen Allokations-Graphen |
| `custom`-Filter mit unbekannten Feldnamen | `400`, nennt die ungültigen Felder |
| Kompression angefragt, kein LLM-Provider konfiguriert | Graceful Degradation über bestehendes Capability-Interface (ADR-02) |
| Scope zu groß für synchrone Kompression | Server erzwingt `async` (Fehler mit Hinweis, falls Client `async=false` explizit erzwingen wollte) |
| Im Bundle enthaltenes Artefakt wird nach Cache-Erstellung gelöscht/outdated | Zählt als Invalidierungs-Trigger, nicht nur Versionssprung |

## 9. Testing-Strategie

- `RequirementBundleQueryService`: `depth` 0/1/N/full, Cap-Grenze, alle drei
  Filter-Modi, alle drei Formate, Pfad-Zuordnung bei mehreren Ebenen.
- `BundleCompressionService`: Cache Hit/Miss/Invalidierung bei
  Versionssprung UND bei Artefakt-Löschung, PromptTemplate-Lookup
  (Global+Workspace-Override), LLM-Adapter gemockt, graceful-degradation-Pfad.
- REST- und MCP-Integrationstests nach bestehendem Projektmuster
  (Auth/Tenancy, Serializer-Contract).
- E2E: Lazy-Load-Panel — kein Netzwerk-Request beim Öffnen der Architecture
  View, Request erst bei Panel-Aktivierung; Performance-Sanity-Check mit
  großer Elementanzahl (kein UI-Block).

## 10. Out of Scope (nicht Teil dieses Plans)

- PDF-Export der Bundle-Ausgabe (bestehender `ExportService` bleibt
  zuständig für klassische Dokument-Exporte, unabhängig von diesem Feature).
- `IMPLEMENTS`-Link (Arch→Req, umgekehrte Richtung von `ALLOCATED_TO`) als
  zusätzliche Gruppierungsquelle — explizit nicht Teil dieses Scopes,
  könnte als Folge-Issue evaluiert werden.
- Persistente (nicht Cache-, sondern echte) Historisierung von komprimierten
  Bundles.
