# Datenarchitektur-Strategie ReqFlow

> Stand: Juli 2026 — nach Batches A–C implementiert
>
> Architektur-Entscheidungsdokument (Senior Engineering). Status: **Entwurf zur Entscheidung**.
> Autor: senior-developer · Datum: 2026-07-10 · Branch: `feat/se-implementation`
> Scope: reine Analyse, keine Code-Änderung. Verbindliche Entscheidung durch Tech-Lead ausstehend.

---

## 1. Einleitung

### Ziel
Dieses Dokument legt die künftige Datenarchitektur von ReqFlow fest. Es beantwortet fünf
Kernfragen, die bisher implizit und teils widersprüchlich beantwortet wurden, und leitet daraus
eine verbindliche Richtung sowie einen phasierten Migrationspfad ab.

### Entscheidungskontext
ReqFlow ist ein AI-natives Requirements- und Test-Management-Tool mit MBSE/V-Modell-Anspruch
(L0–L4). Der Kern des Datenmodells — `Artifact` als zentraler Knoten, `TraceLink` als Kante —
ist tragfähig, aber drei Bereiche verursachen wiederkehrende Bugs und begrenzen die Roadmap:

1. **Versionierung** war fehleranfällig (uid/version-Handling, race conditions).
2. **Traces** sind schwer lesbar — es fehlt ein anzeigefreundliches Trace-Query-Modell.
3. **Baseline-Reconstruction ist konzeptionell kaputt**: gespeichert wird nur eine Versions-*Nummer*,
   nicht der Zustand. Der historische Stand lässt sich damit nicht rekonstruieren.

Gleichzeitig fordert der "AI-native"-Anspruch Fähigkeiten, die das aktuelle Modell nicht hat:
Ähnlichkeitssuche, Duplikaterkennung, LLM-gestützte Impact-Analyse. Die zentrale Frage lautet
daher nicht "welche neue Datenbank", sondern: **Wie weit trägt PostgreSQL, und wo lohnt Polyglot?**

### Kernaussage vorab
Die Empfehlung ist **Option A: pragmatische Postgres-Evolution**. Kein Neo4j, keine MongoDB, kein
Event Sourcing. PostgreSQL 16 mit JSONB, `pgvector` und rekursiven CTEs deckt alle Anforderungen
ab. Die eigentlichen Probleme sind Modellierungsfehler (fehlende State-Snapshots, fehlendes
Trace-Read-Model), keine Fähigkeitslücken der Datenbank.

---

## 2. IST-Zustand

### 2.1 Datenmodell-Überblick

**Abstrakte Basis**
- `AuditableModel`: `id:UUID(PK)`, `created_at/by`, `modified_at/by`, `version:int`.
- `TenantScopedModel(AuditableModel)`: + `tenant`, Thread-Local-Auto-Inject via `TenantManager`.

**Artifact als zentraler Knoten**
- `Artifact(parent→self CASCADE, workspace, artifact_type)`, BTree-Index auf `parent` (rekursive CTEs).
- Alle Domänen-Entitäten (`Requirement`, `ArchitectureElement`, `StakeholderNeed`, `TestCase`)
  haben eine `OneToOne`-FK auf `Artifact` — **jede Entität IST ein Artifact**. Sauberes,
  polymorphes Fundament.

**TraceLink (die kritische Kante)**
- `source→Artifact(CASCADE)`, `target→Artifact(CASCADE)`, `link_type:char(64)`.
- Composite-BTree-Index auf `(source, target)`.
- 12 `link_type`-Werte: `parent-child, derives-from, satisfies, verifies, implements, refines,
  documents, realizes, traces, copy-of, allocated-to, uses-term`.
- **Keine Versionierungsfelder** auf TraceLink selbst.
- In Baselines nur indirekt erfasst via `BaselineDeltaIndexEntry(entity_type='trace_link')`.
- `traceability/models.py` ist ein leerer TODO-Stub — TraceLink lebt in `persistence/models.py`.
  Das ist die Wurzel der "Traces kaum lesbar"-Beschwerde: es gibt keine Domänen-Schicht, die
  Kanten anzeigefreundlich (mit uid, Titel, Richtung, Typ-Label) aufbereitet.

**Baseline / Versionierung — Two-Table-Delta-Index**
- `BaselineSnapshot`: immutabler Header (`workspace_id`, `scope: document/project/global`, `name`,
  `description`), DB-Trigger verhindern UPDATE/DELETE.
- `BaselineDeltaIndexEntry`: `item_id:char(64)` (UUID als String, von FK entkoppelt),
  `version:int` (Version der Entität zum Snapshot-Zeitpunkt), `entity_type: item/icd/trace_link`.
- Version-Capture: `AuditableModel.version` als Counter, inkrementiert mit `F('version')+1` in
  atomaren Blöcken.
- **Kein Event Sourcing** — nur Nummer-Capture, kein Full-State-Snapshot.

**JSONField-Einsatz (bestehend)**
`Workspace.preset/ai_prompts`, `TestCase.steps`, `Issue.tags`, `Role.permissions`,
`IcdVersion.pre/post/invariants`, `WorkflowEngineDefinition.workflow_json`,
`MetricCache.result_json`, `AuditLogEntry.payload` (legacy), `UserWorkspacePreference.*`.
Kein HStore. Kein JSONField für dynamische, benutzerdefinierte Attribute auf Kern-Entitäten.

**Dynamische Attribute**
- `AttributeVisibilityConfig` steuert nur *Sichtbarkeit/Pflicht* pro `entity_type`/Tenant.
- Kein EAV, kein Custom-Field-Mechanismus, kein dynamisches Feld-Anlegen.

**Volltextsuche**
- GIN-tsvector-Index auf `Requirement` (title+description, deutsche FTS-Config, Expression-Index).
- Kein pgvector, keine Embeddings.

**Audit (dual)**
- Legacy `AuditLogEntry` (JSONField-payload) + produktives `AuditEntry` (First-Class-Spalten,
  monatliche RANGE-Partition, DB-Trigger).
- `AuditEntry` hält `op/entity_type/entity_id/entity_version/change_reason/source/...` —
  **kein Field-Level-Diff, kein Full-State**. Damit ist Audit als Rekonstruktionsquelle untauglich.

**Weitere Patterns**
- Immutabilität via DB-Trigger: `BaselineSnapshot`, `BaselineDeltaIndexEntry`, `IcdVersion`, `AuditEntry`.
- Mutable-Header + Immutable-Versions: `Icd/IcdVersion`, `Diagram/DiagramVersion` — **das ist das
  richtige Muster**, das für Baselines fehlt.
- Optimistic Locking: `WorkflowItemState.version` als OCC-Counter.
- `suspect:bool` auf Kern-Entitäten (Review-Flag nach Upstream-Änderung).
- `uid:char(64,null)` als stabile Kurz-Anzeige-ID.
- `DomainEventOutbox` in `application` (21 Event-Typen) — bereits vorhanden, unterschätzt.

### 2.2 Bekannte Probleme und ihre Ursache im Datenmodell

| Symptom | Ursache im Modell | Klasse |
|---|---|---|
| Versionierung buggy | `version` als nackter Counter, an mehreren Stellen manuell inkrementiert; ohne konsequentes `F()`+OCC race-anfällig | Konsistenz |
| Traces kaum lesbar | Kein Trace-Domain-Layer; `TraceLink` roh mit UUID-FKs, kein Read-Model mit uid/Titel/Label | Fehlende Schicht |
| uid/Version fehleranfällig | `uid` nullable, Vergabe nicht zentralisiert; Version und uid in verschiedenen Codepfaden gesetzt | Konsistenz |
| Baseline nicht rekonstruierbar | Delta-Index speichert nur `version:int`, kein serialisierter Zustand; Audit hat keinen Full-State → nichts, woraus man den Stand rekonstruieren könnte | **Design-Fehler** |

Nur das letzte Problem ist ein echter Architekturfehler. Die übrigen sind Umsetzungs- und
Schichtungsmängel, die ohne Datenbankwechsel behebbar sind.

---

## 3. Architektur-Fragen

### Frage 1 — Graph-DB vs. relational für Traceability

**Einleitung.** Traces bilden einen gerichteten Graphen: Impact-Analyse (welche Downstream-Artefakte
sind betroffen?), Pfadfindung (L0→L4-Kette), Zyklenerkennung. Kandidaten: Neo4j (dedizierte
Graph-DB), Apache AGE (Postgres-Extension, Cypher), `ltree` (Materialized Path), rekursive CTEs.

**Analyse.**
- **`ltree` fällt sofort raus.** Es modelliert *Bäume* — jeder Knoten hat genau einen Pfad/Elternteil.
  ReqFlow-Traces sind ein **DAG mit 12 Kantentypen** (ein Requirement kann mehrere `satisfies`- und
  `derives-from`-Kanten haben). Multi-Parent ist mit einem Materialized-Path-Feld nicht abbildbar.
- **Apache AGE** speichert Graphdaten in normalen Postgres-Heap-Tabellen mit B-Tree-Lookup pro Hop —
  *keine* index-free adjacency wie Neo4j/Memgraph. Bei tiefen Traversierungen daher nicht
  grundsätzlich schneller als eine gute CTE; Benchmarks zeigen CTEs teils um Faktor 40 vorn.
  Killer-Kriterium: **AGE ist auf AWS RDS/Aurora und den meisten Managed-Postgres nicht verfügbar** —
  das bindet ReqFlow an selbstverwaltetes Postgres.
- **Neo4j** wäre technisch stark, bedeutet aber eine zweite Datenbank, Dual-Write, eigene Backups,
  Konsistenzgrenzen und Betriebslast. Für ein Tool, dessen Graph in den nächsten Jahren im
  Bereich 10⁴–10⁶ Kanten liegt, ist das massiv überdimensioniert.
- **Rekursive CTEs** in Postgres 16 lösen Impact-Analyse, Pfadfindung und Zyklenerkennung
  (`WITH RECURSIVE ... UNION` bricht Zyklen über einen besuchten-Pfad-Array). Bei Millionen Kanten
  helfen Partitionierung und `EXPLAIN ANALYZE`-Tuning. Der Composite-Index `(source, target)` ist
  bereits vorhanden; ein zusätzlicher Index auf `(target, source)` beschleunigt Rückwärts-Traces.

**Antwort.** **Rekursive CTEs auf der bestehenden relationalen Struktur.** Kein Neo4j, kein AGE,
kein ltree. Das Lesbarkeitsproblem ist **kein Graph-DB-Problem**, sondern ein fehlendes Read-Model:
`traceability/` muss aus dem Stub eine echte Query-Schicht werden, die Traces mit uid, Titel,
Richtung und Typ-Label liefert. Falls Traversierungen je zum Hotspot werden, ist eine
materialisierte Transitive-Closure-Tabelle (per Trigger/Outbox gepflegt) der nächste Schritt —
nicht ein Datenbankwechsel.

### Frage 2 — Dynamische/erweiterbare Attribute

**Einleitung.** Kunden mit Extended-Rigor brauchen eigene Attribute (z. B. `ASIL`, `Verification
Method`, `Compliance-Ref`) auf Requirements/Testfällen, ohne dass das Kern-Schema pro Tenant
geändert wird. Kandidaten: EAV (`django-eav2`), JSONB, Document-Store (MongoDB), Schema-Registry.

**Analyse.**
- **EAV (`django-eav2`)** verteilt jedes Attribut auf eine eigene Zeile. Folge: Join-Explosion
  (jede zusätzliche Filterbedingung = ein weiterer `EXISTS`/Self-Join), Table-Bloat, alles als TEXT
  (Cast-Zwang), langsame Schreibpfade. Einziger Vorteil — granulares Locking — ist für ReqFlows
  Schreibprofil irrelevant.
- **MongoDB** würde Polyglot-Betrieb, verlorene FK-Integrität und Zwei-Quellen-Wahrheit einführen,
  um ein Problem zu lösen, das Postgres nativ kann. Abgelehnt.
- **JSONB** ist der moderne Default: ein `custom_attributes:JSONField` pro Kern-Entität, GIN-Index
  für den `@>`-Containment-Operator, geschachtelte/Array-Werte nativ, Multi-Attribut-Update in einem
  Write. Django unterstützt das First-Class über `django.db.models.JSONField` (Postgres-jsonb).
- **Fehlende Typsicherheit** von JSONB wird durch **JSON-Schema-Validierung** in der Service-Schicht
  (`application/`) gelöst — die Schema-Definition liegt ohnehin schon konzeptionell in
  `AttributeVisibilityConfig`, die zur **Schema-Registry pro Tenant/entity_type** ausgebaut werden
  sollte (Attribut-Name, Typ, Pflicht, Enum-Werte).

**Antwort.** **JSONB + JSON-Schema-Registry.** `custom_attributes:JSONField(default=dict)` auf den
Kern-Entitäten, GIN-Index, Validierung gegen ein pro Tenant/`entity_type` hinterlegtes Schema in
der Service-Schicht. `AttributeVisibilityConfig` wird von "Sichtbarkeit" zur vollen Attribut-Registry
erweitert. **Kein `django-eav2`.**

### Frage 3 — Polyglot Persistence für AI-native Features

**Einleitung.** Für Ähnlichkeitssuche, Duplikaterkennung und LLM-gestützte Impact-Analyse braucht
ReqFlow Embeddings + Vektorsuche. Kandidaten: `pgvector`, Qdrant, Weaviate, Chroma, managed Services.

**Analyse.**
- Realistische Größenordnung: Requirements + Testfälle + Architektur-Elemente pro Tenant liegen weit
  unter 10⁷ Vektoren — meist im fünfstelligen Bereich. In dieser Klasse ist **die Operations-Last,
  nicht die reine Latenz** das Unterscheidungskriterium.
- **`pgvector`** lebt in derselben Datenbank: gleiche Backups, gleiche Transaktion, gleiche
  Tenant-Isolation (Row-Level-Security greift automatisch auch auf Embeddings!), kein Dual-Write,
  kein zusätzlicher Dienst. HNSW-Index seit pgvector 0.5, iterative Index-Scans seit 0.8 verbessern
  das Verhalten bei selektiven Filtern — genau der Fall bei Multi-Tenancy (`WHERE tenant_id = ...`).
- **Qdrant** (Rust) ist bei hohem Durchsatz und niedriger Latenz messbar schneller — relevant erst
  bei latenzkritischen, nutzer-sichtbaren Echtzeit-Suchen über Millionen Vektoren. Das ist nicht
  ReqFlows Profil (Analyse-Workloads, LLM-Roundtrips dominieren die Latenz ohnehin).
- **Weaviate/Chroma** lösen kein Problem, das `pgvector` hier nicht löst; Weaviate hat in der Praxis
  hohe Betriebslast. Managed Vektor-Services (Pinecone) brechen die Tenant-Isolation und erhöhen
  Kosten/Compliance-Fläche.

**Antwort.** **`pgvector` im bestehenden Postgres.** Embedding-Spalte(n) auf `Requirement` (und
später weiteren Entitäten), HNSW-Index, RLS-Filter inklusive. Migration zu Qdrant bleibt eine
Option für später — sie ist datenmodell-neutral (Embeddings sind abgeleitet, nicht Source-of-Truth)
und kann jederzeit ohne Schema-Bruch nachgezogen werden.

### Frage 4 — Event Sourcing vs. Versions-Nummer-Capture

**Einleitung.** Das aktuelle Modell erfasst nur `version:int`. Reicht das, oder braucht ReqFlow
Event Sourcing bzw. temporale Tabellen (`django-simple-history`)?

**Analyse.**
- **Event Sourcing** macht den Event-Log zur Wahrheit, der State wird durch Replay abgeleitet.
  Mächtig für "Warum"-Fragen und beliebige neue Projektionen — aber teuer: Event-Versionierung,
  Replay-Kosten, Snapshotting, schwierige Duplikat-/Gleichheitsprüfung, hohe Umbaulast. Für ReqFlow
  ein Overkill: der Bedarf ist "zeige den Stand zu Baseline X", nicht "leite beliebige Read-Models
  aus der Historie ab".
- **Temporale Tabellen / `django-simple-history`** speichern pro Save einen **vollen Snapshot** der
  Zeile. Genau dieses Muster (Full-State pro Version) fehlt ReqFlow — und es ist im Projekt schon
  vorhanden: `Icd/IcdVersion` und `Diagram/DiagramVersion` machen es richtig. Das aktuelle
  Baseline-Modell dagegen speichert nur die Nummer.
- **Postgres hat keine nativen System-Versioned Temporal Tables** (kein `AS OF SYSTEM TIME`);
  Extensions existieren, sind aber nicht Managed-tauglich. Deshalb: Snapshot-Muster in der
  Anwendungsschicht abbilden, nicht auf DB-Extension setzen.
- `DomainEventOutbox` (21 Event-Typen) existiert bereits — das ist genug "event-driven" für
  Read-Model-Aktualisierung und Suspect-Propagation, ohne Full Event Sourcing.

**Antwort.** **Weder Full Event Sourcing noch DB-Temporal-Extension.** Stattdessen das im Projekt
bereits bewährte **Mutable-Header + Immutable-Full-State-Version**-Muster (wie `IcdVersion`) auf
die Baseline anwenden: beim Baselining den **serialisierten Vollzustand** jeder Entität einfrieren.
Für laufende Feld-Level-Historie optional `django-simple-history` auf ausgewählten Kern-Entitäten —
aber das ist Kür, nicht Pflicht.

### Frage 5 — Baseline-Reconstruction

**Einleitung.** Der kritische Defekt: Baseline speichert `version:int`, aber es gibt keine Quelle
für den *Zustand* dieser Version. Wie lösen etablierte Tools (Polarion, DOORS Next, Jira) das?

**Analyse.**
- **Polarion** versioniert jede Änderung in einem Repository (SVN-artig). Eine Baseline/Collection
  ist ein **immutabler Snapshot konkreter Revisionen** von Dokumenten und Work-Items — der Zustand
  ist über die Repository-Revision jederzeit voll rekonstruierbar ("Time Machine").
- **DOORS Next** friert beim Baseline die **exakten Versionen der Requirements, ihrer Attribute und
  Beziehungen** auf Komponentenebene ein — Full-State, nicht nur eine Nummer.
- **Gemeinsamer Nenner:** Beide speichern den *tatsächlichen Zustand* (bzw. eine dereferenzierbare
  Revision), nicht bloß eine Zahl, aus der man den Zustand nicht ableiten kann.
- ReqFlows Fehler: `BaselineDeltaIndexEntry.version` ist eine Zahl ohne Backing-Store. Es gibt weder
  ein Repository, das Revision X materialisiert, noch einen Full-State-Snapshot, noch einen
  Field-Level-Audit-Diff. Der Zustand ist **verloren**.

**Antwort.** Die Baseline muss den **serialisierten Vollzustand** jeder erfassten Entität speichern
(Requirement/AE/StakeholderNeed/TestCase/ICD **und** die TraceLinks). Konkret: `BaselineDeltaIndexEntry`
(oder eine neue `BaselineSnapshotItem`-Tabelle) erhält ein `state:JSONField` mit dem vollen
serialisierten Artefakt-Zustand zum Snapshot-Zeitpunkt, immutabel per DB-Trigger. `version:int`
bleibt als schneller Vergleichsschlüssel für die Diff-Engine erhalten. Das ist exakt das
`IcdVersion`-Muster, konsequent auf Baselines angewandt.

---

## 4. Bewertete Optionen

### Option A — Pragmatische Postgres-Evolution *(empfohlen)*

Ein System of Record: PostgreSQL 16. Erweiterung um JSONB (dynamische Attribute), `pgvector`
(Embeddings), rekursive CTEs + Trace-Read-Model (Traceability), Full-State-Snapshots (Baselines).

**Vorteile**
- Eine Datenbank, eine Transaktion, eine Backup-Strategie, eine Tenant-Isolation (RLS gilt überall).
- Nutzt vorhandene Stärken: `IcdVersion`-Muster, `DomainEventOutbox`, GIN/tsvector, DB-Trigger.
- Behebt alle vier bekannten Probleme ohne Datenbankwechsel.
- Geringes Risiko, inkrementell auslieferbar, keine Dual-Write-Konsistenzprobleme.

**Nachteile**
- Tiefe Graph-Traversierungen jenseits ~10⁶ Kanten brauchen später ggf. eine Closure-Tabelle.
- Vektorsuche bei extremer Latenz-/Skalenanforderung nicht so schnell wie Qdrant.

**Eignung Django/DRF/ReqFlow:** hoch. Alles über Standard-Django-Bordmittel (`JSONField`,
Migrations, Services in `application/`, Serializer-Validierung). Kein neuer Betriebsbaustein.

**Migrations-Aufwand:** mittel. Neue Felder + Backfill-Migrationen, Trace-Read-Model, Baseline-
Snapshot-Umbau. Keine Datenmigration in ein Fremdsystem.

### Option B — Polyglot Persistence

Postgres als System of Record + Neo4j für Traces + `pgvector`/Qdrant für Embeddings.

**Vorteile**
- Native Graph-Algorithmen (Shortest Path, Centrality) bei Bedarf.
- Beste Vektor-Performance bei sehr großer Skala.

**Nachteile**
- Dual-Write und Konsistenzgrenzen zwischen Postgres und Neo4j (Trace-Kanten in beiden Welten
  synchron halten — genau die Fehlerklasse, die ReqFlow gerade *reduzieren* will).
- Zwei bis drei Betriebssysteme statt einem; RLS/Tenant-Isolation muss in jedem separat gelöst werden.
- Kein aktueller Workload rechtfertigt es.

**Eignung:** niedrig bei aktueller Skala. Führt Komplexität ein, um Probleme zu lösen, die ReqFlow
noch nicht hat.

**Migrations-Aufwand:** hoch (Sync-Layer, Betrieb, Monitoring, Backup-Koordination).

### Option C — Event Sourcing + CQRS

Vollständige Neuarchitektur: Event-Log als Wahrheit, Read-Models als Projektionen.

**Vorteile**
- Perfekte Historie, beliebige neue Projektionen, "Warum"-Nachvollziehbarkeit.
- Baseline-Reconstruction fiele als Nebenprodukt ab (Replay bis Zeitpunkt X).

**Nachteile**
- Größter Umbau; berührt jede Entität und jeden Service.
- Event-Versionierung, Replay-Kosten, Snapshotting, schwierige Duplikatprüfung.
- Team-Ramp-up hoch; hohes Projektrisiko für einen Nutzen, den Full-State-Snapshots günstiger liefern.

**Eignung:** niedrig. Löst genau ein reales Problem (Reconstruction), das Option A mit einem
Bruchteil des Aufwands ebenfalls löst.

**Migrations-Aufwand:** sehr hoch (De-facto-Rewrite der Persistenz- und Service-Schicht).

---

## 5. Empfehlung

### Klare Empfehlung: **Option A — Pragmatische Postgres-Evolution**

*Siehe auch: [Implementierungsstand (Juli 2026)](#7a-implementierungsstand-juli-2026) — Batches A–C wurden umgesetzt.*

Begründung:
1. **Die Probleme sind Modellierungs-, keine Technologiefragen.** Reconstruction scheitert nicht,
   weil Postgres es nicht kann, sondern weil kein Zustand gespeichert wird. Traces sind nicht
   unlesbar, weil relational, sondern weil die Read-Schicht fehlt.
2. **Das richtige Muster existiert bereits im Code** (`IcdVersion`, `DiagramVersion`,
   `DomainEventOutbox`). Konsequente Anwendung schlägt Neuerfindung.
3. **Tenant-Isolation über RLS** ist ein starkes Argument gegen jede zweite Datenbank — sie müsste
   dort neu und fehleranfällig repliziert werden.
4. **Inkrementell auslieferbar** ohne Big-Bang, jede Phase liefert eigenständigen Wert.

### Nicht empfohlen
- **Option B (Polyglot):** verfrüht. Löst nicht-existente Skalenprobleme, verschärft die
  Konsistenz-Fehlerklasse, die ReqFlow reduzieren will. *Später wieder aufgreifen*, falls Traces
  >10⁶ Kanten oder Vektorsuche latenzkritisch wird — dann isoliert Qdrant/Closure-Tabelle ergänzen.
- **Option C (Event Sourcing):** unverhältnismäßig. Der einzige echte Gewinn (Reconstruction) ist
  mit Full-State-Snapshots deutlich billiger zu haben.
- **`django-eav2`, MongoDB, `ltree`, Neo4j, Pinecone:** je oben begründet abgelehnt.

### Quick Wins (sofort, ohne Architekturwechsel)
1. **`version`-Handling zentralisieren:** eine einzige Stelle (Service/Model-Save) mit `F('version')+1`
   und OCC-Check; manuelle Inkremente in anderen Codepfaden entfernen. Behebt die Race-Bugs.
2. **`uid`-Vergabe zentralisieren** und `uid` mittelfristig `NOT NULL` machen (Backfill vorausgesetzt).
3. **Trace-Read-Model** in `traceability/` (Stub füllen): eine Query-Funktion, die für ein Artefakt
   Vorwärts-/Rückwärts-Traces mit `uid`, Titel, `link_type`-Label und Richtung liefert. Löst
   "Traces kaum lesbar" ohne Schemaänderung.
4. **Index `(target, source)`** auf `TraceLink` für schnelle Rückwärts-Impact-Analyse.
5. **Legacy-`AuditLogEntry` einfrieren**, nur noch `AuditEntry` schreiben (Doppel-Audit beenden).

---

## 6. Migrationspfad (phasiert)

### Phase 1 — Quick Wins & Baseline-Fix *(höchste Priorität)*
- Version-/uid-Handling zentralisieren (Quick Wins 1–2).
- **Baseline-Full-State:** `state:JSONField` auf `BaselineDeltaIndexEntry` (oder neue
  `BaselineSnapshotItem`), immutabel per Trigger; Snapshot-Service serialisiert den Vollzustand aller
  erfassten Entitäten **inklusive TraceLinks**. Diff-Engine liest künftig `state` statt nur `version`.
- Trace-Read-Model (`traceability/`) + Rückwärts-Index.
- **Testabdeckung:** Reconstruction-Roundtrip-Test (Baseline anlegen → Entität ändern → historischer
  Stand exakt rekonstruierbar), Version-Race-Test (nebenläufige Updates), Trace-Read-Model-Tests.
- *Kein Datenmodell-Bruch, rückwärtskompatibel* (neues Feld additiv; Alt-Baselines bleiben lesbar,
  aber ohne rekonstruierbaren State — als "legacy, state-less" markieren).

### Phase 2 — Datenmodell-Erweiterung
- `custom_attributes:JSONField(default=dict)` auf Kern-Entitäten + GIN-Index; JSON-Schema-Validierung
  in `application/`; `AttributeVisibilityConfig` → Attribut-Registry (Name/Typ/Pflicht/Enum) ausbauen.
- `pgvector` aktivieren; Embedding-Spalte auf `Requirement`, HNSW-Index, RLS-Filter; Async-Embedding
  via Celery + `DomainEventOutbox`; erste Feature: Duplikaterkennung/Ähnlichkeitssuche.
- DRF-Serializer + Frontend-Masken um dynamische Attribute erweitern (`data-testid`, i18n).
- **Testabdeckung:** Schema-Validierungs-Tests, Vektorsuche-Tests (mock-Embeddings), RLS-Isolation
  auf Embeddings.

### Phase 3 — Optionale Graph-/Skalierungs-Erweiterung *(nur bei nachgewiesenem Bedarf)*
- Materialisierte **Transitive-Closure-Tabelle** für Traces (per Outbox/Trigger gepflegt), falls
  rekursive CTEs zum Hotspot werden (EXPLAIN-ANALYZE-getrieben, nicht spekulativ).
- Optional **Qdrant** auslagern, falls Vektor-Latenz/Skala es erzwingt — Embeddings sind abgeleitet,
  daher schema-neutral migrierbar.
- Trigger für Phase 3 sind Messwerte (Traversierungs-Latenz, Vektor-QPS), keine Annahmen.

---

## 7. Risiken und Gegenmaßnahmen

| Risiko | Wahrscheinlichkeit | Wirkung | Gegenmaßnahme |
|---|---|---|---|
| Baseline-State-JSON bläht DB auf (großer Payload pro Snapshot) | mittel | mittel | Nur relevante Felder serialisieren; TOAST-Kompression (Postgres native) nutzt; Snapshots sind selten (bewusster Akt) |
| Alt-Baselines ohne State bleiben nicht-rekonstruierbar | hoch | niedrig | Als "legacy, state-less" flaggen; keine False-Confidence in UI; einmaliger Best-Effort-Backfill aus Live-State wo unverändert |
| JSONB-`custom_attributes` erodiert zu Wildwuchs ohne Schema | mittel | mittel | Schema-Registry-Validierung verpflichtend in Service-Schicht; kein direkter Model-Write ohne Validierung |
| Version-Zentralisierung bricht bestehende Codepfade | mittel | hoch | Blast-Radius vorab per Grep (`F('version')`, manuelle Inkremente); OCC-Konflikt sauber als HTTP 409 mappen; Regressionstests vor Merge |
| pgvector-Performance bei selektiven Tenant-Filtern | niedrig | mittel | pgvector ≥0.8 (iterative Index-Scans); HNSW-Parameter tunen; bei Bedarf partitionieren |
| Rekursive CTE zum Performance-Hotspot | niedrig | mittel | `EXPLAIN ANALYZE`-Monitoring; Closure-Tabelle (Phase 3) als vorbereiteter Fallback |
| Dual-Audit-Umstellung verliert Legacy-Reads | niedrig | niedrig | `AuditLogEntry` read-only behalten, nur Schreibpfad kappen |

---

## 7a. Implementierungsstand (Juli 2026)

Diese Architektur-Analyse wurde in **Batches A–C** implementiert. Nachfolgend Übersicht des
IST-Zustands, Abweichungen vom ursprünglichen Plan und ausstehende Items.

### Status-Übersicht

| Req-ID | Feature | Batch | Status | Abweichungen |
|---|---|---|---|---|
| REQ-L2-BL-012 | Baseline Full-State-Snapshot | A | ✅ implementiert | Kein REST Diff-Endpoint (Backend ready, ViewSet-Action ausstehend) |
| REQ-L2-TE-019 | TraceLink Read-Model + CTE | B | ✅ implementiert | URL `/tracelinks/` statt `/traceability/`; Duplex-Cycle-Detection (CTE + Tarjan) |
| REQ-L2-AS-037 | JSONB Custom Fields | C | ✅ implementiert | Frontend-Editor nur in 2/5 Forms (Requirement, Architecture — StakeholderNeed/TestCase ausstehend) |
| REQ-L2-VS-004 | pgvector Embeddings | E | ⏸️ **BLOCKED** | Pending: docker-compose/Dockerfile infra changes |

### Batch A: Baseline Full-State-Snapshot (d49860b)

**Implementiert:**
- `BaselineDeltaIndexEntry.state:JSONField(null=True)` für serialisierten Artefakt-Zustand.
- Migration `0005` (backward-compatible, kein Backfill nötig).
- `backend/baseline/state_capture.py`: batched entity serialization (max 5–7 DB-Queries, unabhängig von Item-Count).
- `DeltaIndexBuilder.build()` ruft `capture_states()` auf, übergeben an Store.
- `DiffEngine` emittiert `field_changes` für geänderte Items, Fallback zu Version-Vergleich für Legacy-Baselines (state=null).
- REST-API: `BaselineDeltaEntrySerializer` mit state als read-only Feld; Frontend zeigt Field-Werte pro Delta-Entry an.

**Abweichung:**
- Kein REST-Endpoint für End-to-End-Field-Diff (Backend-DiffEngine ist bereit; ViewSet-Action `@action` fehlt). Markiert als Follow-up.

### Batch B: TraceLink Read-Model + CTE (d74f9f5)

**Kontext-Überraschung:**
- `backend/traceability/` war NICHT leer — enthielt bereits vollständigen TraceabilityEngine (query_engine.py, trace_link_manager.py mit Tarjan-Zyklenerkennung, services.py, CRUD).

**Implementiert:**
- `backend/traceability/service.py` mit 3 CTE-basierten Funktionen:
  - `impact_analysis()` → gerichtete Downstream-Traversierung mit `ImpactNode`-Hierarchie.
  - `find_path()` → kürzester Pfad zwischen zwei Artefakten.
  - `detect_cycles()` → Zyklenerkennung via CTE `UNION ... WHERE cycle`.
- 3 neue `@action`-Endpoints auf existierendem `TraceLinkViewSet`:
  - `GET /api/v1/tracelinks/impact/?artifact_id=...&direction=...`
  - `GET /api/v1/tracelinks/path/?source_id=...&target_id=...`
  - `GET /api/v1/tracelinks/cycles/`
- CTE depth hard-capped auf 20, Limit-Default 200 (max 1000), `X-Result-Truncated`-Header.
- Frontend: Cycle-Warning-Banner + Depth-indented Impact-Panel.

**Abweichungen:**
- URL `/tracelinks/` (nicht `/traceability/`) — Entscheidung zur Erweiterung existierender ViewSet pro Constraint.
- `detect_cycles` läuft parallel zur besteheneden `TraceLinkManager.validate_graph_integrity` (Tarjan). Redundanz erkannt, Konsolidierung optional.

### Batch C: JSONB Custom Fields (24ef7bc)

**Implementiert:**
- `Artifact.custom_fields:JSONField(default=dict)` mit GIN-Index (`pl_artifact_custom_fields_gin`, Migration `0023`).
- `backend/persistence/custom_fields.py`: Validierung (max 50 Keys, String-Keys, max 128 Chars, Wert-Typen: str/int/float/bool/None).
- `CustomFieldsSerializerMixin` in 5 Serializern (Requirement, ArchElement, StakeholderNeed, TestCase, Artifact).
- Wiring durch 5 Application-Services.
- Frontend: `CustomFieldsEditor.tsx` (Key–Value–Type-Rows), `CustomFieldsDisplay.tsx` (Read-Only-Table), integriert in RequirementForm und ArchitectureForm.

**Abweichung:**
- Frontend-Editor NICHT in StakeholderNeed- und TestCase-Forms (Backend vollständig wired). Optional als Phase-2-Nachbessering.

### Batch E: pgvector (BLOCKED)

- **Status:** ⏸️ Pending Infra-Approval (docker-compose, Dockerfile, pgvector-Extension-Setup).
- **Plan:** Embedding-Spalte auf `Requirement`, HNSW-Index, RLS-Filter, Async-Embedding via Celery.
- **Trigger:** User-Bestätigung für Container-Änderungen.

### Key Decisions — Abweichung vom ursprünglichen Plan

1. **Traceability-URL:** Erwiterung von `TraceLinkViewSet` statt neue `@viewset`-Klasse; minimiert API-Surface, renutzt Authentifizierung/RLS.
2. **Batch A State-Feld Placement:** State auf `BaselineDeltaIndexEntry` (nicht neue Tabelle), spart eine Join; Migration null-safe.
3. **Custom Fields auf `Artifact`, nicht Individual-Entitäten:** Konzept empfohlen, implementiert konsistent — alle 5 Entitäten profitieren durch one-to-one-Beziehung.
4. **Duplex-Cycle-Detection:** `detect_cycles()` (CTE) + bestehende Tarjan-Implementierung nebeneinander. Ausstehend: Prüfung auf Konsolidierung (kein Performance-Nachteil erkannt).

### Migration & Deployment-Hinweise

```bash
# Phase 1–3 Migrationen ausführen
docker-compose exec backend python manage.py migrate

# Baseline-Legacy (state=null) in UI als "state-less, nicht rekonstruierbar" flaggen
# — Alt-Baselines bleiben lesbar, aber Reconstruction-Feature ist neu.

# Traceability-Endpoints jetzt verfügbar
# — /api/v1/tracelinks/impact/, /path/, /cycles/ (siehe OpenAPI-Spezifikation)

# Custom Fields per RequirementForm/ArchitectureForm nutzbar
# — Backend akzeptiert beliebige custom_fields, Validierung prüft JSON-Schema
```

---

## 8. Referenzen

**Graph vs. relational / Traceability**
- PuppyGraph — PostgreSQL Graph Database Overview: https://www.puppygraph.com/blog/postgresql-graph-database
- Snowflake Engineering — Graph Queries in Postgres with Apache AGE: https://www.snowflake.com/en/blog/engineering/graph-queries-postgres-apache-age/
- Medium (S. Singh) — PostgreSQL Showdown: Joins vs. Apache AGE: https://medium.com/@sjksingh/postgresql-showdown-complex-joins-vs-native-graph-traversals-with-apache-age-78d65f2fbdaa
- Cybertec — PostgreSQL: ltree vs. WITH RECURSIVE: https://www.cybertec-postgresql.com/en/postgresql-ltree-vs-with-recursive/
- Cybertec — Speeding up recursive queries and hierarchical data: https://www.cybertec-postgresql.com/en/postgresql-speeding-up-recursive-queries-and-hierarchic-data/

**Dynamische Attribute (EAV vs. JSONB)**
- jazzband/django-eav2: https://github.com/jazzband/django-eav2
- BSWEN — JSONB vs EAV in PostgreSQL: https://docs.bswen.com/blog/2026-04-24-jsonb-vs-eav-postgresql/
- Raz Samuel — PostgreSQL JSONB vs. EAV for Dynamic Data: https://www.razsamuel.com/postgresql-jsonb-vs-eav-dynamic-data/
- zostera/django-jeaves (JSONB-basiertes EAV): https://github.com/zostera/django-jeaves

**Vektor-Datenbanken / pgvector**
- OpenHelm — Pinecone vs Weaviate vs Qdrant vs pgvector: https://www.openhelm.ai/blog/pinecone-vs-weaviate-vs-qdrant-vs-pgvector
- Tensoria — Vector Database Comparison in Production: https://tensoria.fr/en/blog/vector-database-comparison
- Kalvium Labs — pgvector vs Pinecone vs Qdrant vs Weaviate (2026): https://www.kalviumlabs.ai/blog/vector-databases-compared-pgvector-pinecone-qdrant-weaviate/

**Event Sourcing / Versionierung / temporale Tabellen**
- Event-Driven.io — Are Temporal Tables an alternative to Event Sourcing?: https://event-driven.io/en/temporal_tables_and_event_sourcing/
- RisingStack — Event Sourcing vs CRUD: https://blog.risingstack.com/event-sourcing-vs-crud/
- BayTech — Event Sourcing Explained (2025): https://www.baytechconsulting.com/blog/event-sourcing-explained-2025

**Baseline-Reconstruction (Industrie-Tools)**
- Siemens — Polarion REQUIREMENTS: https://www.siemens.com/en-us/products/polarion/requirements/
- Polarion Blog — Working with baselined content to create a variant: https://polarion.code.blog/2020/07/27/use-case-how-to-work-with-baselined-content-to-create-a-new-variant/
- SodiusWillert — Best practices for Managing Baselines with IBM DOORS Next: https://www.sodiuswillert.com/en/blog/best-practices-for-managing-baselines-with-ibm-doors-next

---

## Anhang — Entscheidungs-Notiz

```
DECISION
context: ReqFlow braucht eine tragfähige Datenstrategie für Traceability, dynamische Attribute,
         AI-Features und (defektes) Baselining, ohne die wiederkehrenden Versions-/Trace-Bugs zu
         perpetuieren.
choice:  Option A — Pragmatische Postgres-Evolution: ein System of Record (Postgres 16) + JSONB
         (dynamische Attribute, Schema-Registry) + pgvector (Embeddings) + rekursive CTEs mit
         Trace-Read-Model + Full-State-Snapshots für Baselines (IcdVersion-Muster).
alternatives:
  - Polyglot (Postgres+Neo4j+Qdrant): verworfen — Dual-Write-Konsistenz und Betriebslast ohne
    aktuellen Skalenbedarf; RLS-Isolation müsste dupliziert werden.
  - Event Sourcing + CQRS: verworfen — De-facto-Rewrite für einen Nutzen (Reconstruction), den
    Full-State-Snapshots billiger liefern.
  - django-eav2 / MongoDB: verworfen — Join-Explosion bzw. verlorene FK-Integrität; JSONB löst es nativ.
  - ltree / Neo4j / Apache AGE: verworfen — DAG mit 12 Kantentypen (nicht Baum), AGE nicht managed-fähig,
    Neo4j überdimensioniert; CTEs schlagen AGE oft und reichen für die Skala.
consequences:
  leichter: Reconstruction wird korrekt; Traces werden lesbar; AI-Features (Ähnlichkeit/Duplikate)
            möglich; ein Backup/eine Transaktion/eine Tenant-Isolation; inkrementell auslieferbar.
  schwerer: sehr tiefe Graph-Traversierungen (>10^6 Kanten) und latenzkritische Vektorsuche brauchen
            später gezielte Ergänzung (Closure-Tabelle / Qdrant) — bewusst als Phase 3 aufgeschoben.
```
