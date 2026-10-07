---
adr_id: ADR-020
title: "Qdrant als optionales Vektor-Backend — Revision der L2-Festlegung (pgvector-only) für Memory (V1) und Artefakt-Suche (V2)"
status: proposed
date: "2026-10-07"
deciders: [user, se-architect, planner]
affected_reqs: [REQ-L1-038, REQ-L2-VS-001, REQ-L2-VS-002, REQ-L2-VS-003, REQ-L2-VS-004]
superseded_by: null
---

# ADR-020: Qdrant als optionales Vektor-Backend — Revision der L2-Festlegung (pgvector-only) für Memory (V1) und Artefakt-Suche (V2)

**Status:** proposed (2026-10-07) — Entscheidungsvorlage. **User-Freigabe ausstehend**
(Statuswechsel `proposed → accepted` erst nach positivem Review und User-Entscheid).
**Datum:** 2026-10-07
**Entscheider (vorgeschlagen):** `user`, `se-architect`; **Autor:** `planner`; **Freigabe:** `user` (offen).
**Betroffene REQs:** REQ-L1-038 (Vektorsuche, `docs/se/L1/Gesamtsystem/L1_Gesamtsystem_Requirements.md`),
REQ-L2-VS-001/-002/-003/-004
(`docs/se/L1/Gesamtsystem/L2/VectorSearchServiceSystem/L2_VectorSearchServiceSystem_Requirements.md`).
Ergänzend, außerhalb der SE-Kaskade: REQ-192 (`memory.ask`,
`docs/REQUIREMENTS.md:273-279`).
**Bezug (Issues):** #1204 (Leit „Qdrant als optionaler Vektor-Backend"), #1002 (RFC kanonischer
Memory-Store), #1023 (Memory C — Artefakt-Scope + Prompt-Injektion), #1155 (Honcho als
Langzeitgedächtnis), #1178 (Duplikaterkennung), #1132 (celery-beat lädt Embedding-Modell),
#794/#826/#977 (Embedding-Dimension/HNSW/iterativer ANN-Scan).
**Bezug zum Code (stichprobenartig verifiziert):** `backend/persistence/embedding_dimensions.py:132`
(Dimensions-SSOT, Env `EMBEDDING_VECTOR_DIMENSIONS`, Default 384);
`backend/memory/models.py:97` (embedding), `:127-133` (HNSW `m=16`, `ef_construction=64`,
`vector_cosine_ops`); `backend/persistence/models.py:1602`/`:1620` (Requirement),
`:1946`/`:2021` (TraceLink); `backend/icd/models.py:148`/`:182` (Icd);
`backend/memory/backends.py:322` (`MemoryBackend`-ABC), `:523`/`:526` (Registry/Decorator),
`:536`/`:547` (`get_memory_backend`/`_resolve_memory_backend_name`), `:626`/`:638`
(`_tenant_context`), `:662` (`@register_memory_backend("pgvector")`), `:863-879` (`query`);
`backend/memory/apps.py:67` (Pflicht-Import des optionalen Backends);
`backend/memory/migrations/0004_memory_entry.py:32-46` (FORCE RLS der kanonischen Tabelle);
`backend/memory/health.py` (`envelope()`); `backend/memory/management/commands/memory_reconcile.py`;
direkte ORM-ANN-Sites: `backend/application/search_service.py:608/631/661`,
`backend/application/requirement_service.py:1001`, `backend/application/trace_link_service.py:915`,
`backend/icd/icd_manager.py:720`;
Optional-Service-Muster: `deploy/docker-compose.yml:1137` (`profiles: ["honcho"]`),
`:1453` (`profiles: ["bluepencil"]`).

**Vermerk zur Ablage:** `docs/se/ADR/` ist die *gelebte* Konvention (ADR-001…019 + ADR-DS-02).
Dieses ADR folgt ihr (vgl. ADR-019). Es ändert **keine** REQ-Datei und **keine** Kaskaden-Datei.

---

## Entscheidungsvorlage

- **Was ist zu entscheiden:** (1) ob die L2-Festlegung „embedded pgvector, kein externer
  Vektordienst" **bestätigt oder revidiert** wird; (2) bei Revision: die Collection-Strategie
  (eine Collection pro Workspace vs. eine Collection mit Payload-Filter) und der Umfang
  (V1 = Memory über `MemoryBackend`, V2 = Artefakt-Suche über einen neuen Vektor-Port).
- **Empfehlung (vom Auftraggeber bereits entschieden, hier abgebildet):** **Revision** der
  L2-Ablehnung; **Collection-Strategie A** (eine Collection pro Workspace + `user`-Sonderfall +
  separate Artefakt-Collection); **Umfang V1+V2**; **pgvector bleibt Default**, Qdrant nur bei
  aktivem Compose-Profil bzw. `MEMORY_BACKEND=qdrant`.
- **Konsequenzen bei Annahme:** die L2-REQ (`…VectorSearchServiceSystem_Requirements.md:32,36`)
  und die zugehörige Zerlegung (`L2_architectural_decomposition_iter-1.md:55,59`) werden
  aktualisiert; neue optionale Infrastruktur (`qdrant`-Profil) + Volume + Backup-/Restore-Erweiterung;
  app-erzwungene Isolation (ohne RLS) + Guard-Test; V1 mittel, V2 groß.
- **Konsequenzen bei Ablehnung:** pgvector bleibt alternativlos; Option (b) „nur Memory (V1)"
  bliebe als kleinster Schritt; die in §Alternativen genannten Risiken (Skalierung, Hybrid,
  optionale Betriebslast) bleiben bestehen.
- **Grober Aufwand:** ADR = klein; V1 (`QdrantMemoryBackend` + Compose-Profil) = mittel;
  V2 (Vektor-Port über vier ANN-Sites) = groß. Belastbare Zahlen bei `effort-estimator`.
- **Offene Punkte:** Artefakt-Trennung als Collection vs. Payload, `QDRANT_DISTANCE`-Default,
  #1023-Blast-Radius, Qdrant↔kanonische `MemoryEntry`-Mapping, Backup/Restore des Qdrant-Volumes
  (s. §Offene Entscheidungen).

---

## Kontext

**1. Der Ist-Zustand ist pgvector-only — mit vier Vektor-Spalten und einer halb-abstrahierten
Zugriffsschicht.**

| Vektor-Spalte | Modell | HNSW-Index | ANN-Query-Site |
|---|---|---|---|
| `mem_memory_entry.embedding` | `backend/memory/models.py:97` | `:127-133` | **abstrahiert** über `MemoryBackend.query` (`backends.py:863-879`) |
| `pl_requirement.embedding` | `backend/persistence/models.py:1602` | `:1620` | direkt: `search_service.py:608`, `requirement_service.py:1001` |
| `pl_tracelink.embedding` | `backend/persistence/models.py:1946` | `:2021` | direkt: `search_service.py:631`, `trace_link_service.py:915` |
| `icd_icd.embedding` | `backend/icd/models.py:148` | `:182` | direkt: `search_service.py:661`, `icd_manager.py:720` |

Alle vier Spalten beziehen ihre Breite aus der einen SSOT
`persistence/embedding_dimensions.py:132` (Env `EMBEDDING_VECTOR_DIMENSIONS`, Default 384); die
HNSW-Indexe sind einheitlich `m=16`, `ef_construction=64`, `vector_cosine_ops`. **Nur der
Memory-Zugriff ist abstrahiert** (`MemoryBackend`-ABC + Registry `backends.py:322,523,526,536,547`
+ Pflicht-Import `memory/apps.py:67`); die vier Artefakt-Sites nutzen `CosineDistance` direkt
(`from pgvector.django import CosineDistance`).

**2. Es gibt zwei widerstreitende Tendenzen.** Einerseits ist die kanonische Quelle bewusst
Postgres: `mem_memory_entry` ist die *eine* tenant-gescopte Tabelle mit FORCE RLS
(`memory/migrations/0004_memory_entry.py:32-46`), und `MemoryEntry.backend_ref` trägt bereits ein
Feld für die externe Backend-ID („a Honcho nanoid for the honcho backend; NULL for pgvector",
`memory/models.py:51-54`). Andererseits verlangt eine wachsende Workspace-Größe (10.000+ Artefakte,
Artefakt-Scope-Embeddings, Hybrid-Suche) Optionen, die pgvector erkennbar belasten. Der neue
externe Dienst ist deshalb kein Ersatz, sondern eine **optionale zweite Betriebsart**.

**3. Die bestehende Architektur-Entscheidung lehnt genau das ab — und muss deshalb zur
Disposition gestellt werden.**

> `L2_VectorSearchServiceSystem_Requirements.md:32` — „Die Vektorsuche wird auf **embedded
> pgvector** … implementiert. Kein externer Vektordatenbank-Service (Qdrant/Milvus)."
> `:36` — „**Abgelehnte Alternative:** Externer Qdrant-Service — abgelehnt, da dies die
> Deployment-Topologie verkompliziert und Self-Hosted-Betrieb erschwert."

Dieselbe Festlegung steht in der zugehörigen Zerlegung
(`docs/se/L1/Gesamtsystem/L2_architectural_decomposition_iter-1.md:55,59`). Ein optionaler
Qdrant-Backend ist damit **keine additive Neuerung, sondern eine Revision** und braucht dieses
ADR — **vor** jeder Zeile Code (vgl. Plan §4.2/§4.7,
`docs/plans/2026-10-07-umsetzungsplaene-1155-1201-1202-1204.md`).

**4. Abgrenzung zu #1002 / #1023 / #1155.** #1002 hat den *kanonischen* Memory-Store geschaffen
(`mem_memory_entry`, RLS, `MemoryBackend`-ABC). #1023 hat den **Artefakt-Scope** und die
Prompt-Injektion ergänzt (`release v1.8.0-beta.14`). #1155 behandelt **Honcho** als Engine: einen
bereits **akzeptierten** externen Dienst — aber für *Derivation/Dialektik*, nicht für Vektoren.
ADR-020 bringt den *Vektor-Backend*-Austausch in dieselbe Einbaustelle (`MemoryBackend`), ohne
#1002/#1023/#1155 zu berühren: Honcho und Qdrant sind orthogonale Achsen (Derivation vs. ANN-Index).

**5. Treiber.** (a) **Skalierung**: ANN-Last wächst mit Artefakt-Scope-Vektoren und Duplikat-Suche
(#1178). (b) **Optionale Betriebsarten**: das Compose-`profiles`-Muster (honcho `:1137`, bluepencil
`:1453`) existiert bereits; ein optionaler Vektor-Dienst soll nichts am Default kosten. (c)
**Deployment-Last**: #1132 (celery-beat lädt das Embedding-Modell, ~407 MiB) motiviert, die
Vektor-/Embedding-Topologie insgesamt entkoppelbar zu machen.

**6. Threat-Model (4 Fragen, externer Vektor-Dienst):**

1. *Was gebaut?* Ein optionaler Qdrant-Service (Compose-Profil) mit Vektoren für Memory (V1) und
   perspektivisch Artefakte (V2); Steuerung app-seitig über `MemoryBackend`/Vektor-Port; Auth der
   eigener Dienst, kein öffentlicher Host-Port.
2. *Was schiefgeht?* (a) **Cross-Tenant-Leak**: Qdrant kennt kein Postgres-RLS; ein falsch
   gebildeter Collection-Name bzw. fehlender Namensraum könnte fremde Vektoren liefern.
   (b) **Zwei Vektor-Wahrheiten**: Postgres-Zeile und Qdrant-Punkt driften (Write gelingt nur
   lokal oder nur extern). (c) **Silent Fallback**: ein konfigurierter, aber unerreichbarer
   Qdrant-Dienst, der still auf pgvector zurückfällt, verschleiert den Ausfall. (d)
   **Backup-Lücke**: der Qdrant-Vektorindex liegt nicht im Postgres-Sidecar-Dump.
3. *Gegenmaßnahme?* Collection-Isolation wird **harte Namensgrenze** (Strategie A, §Entscheidung);
   jeder Zugriff ist auf **genau eine** Collection beschränkt (Guard-Test, §Entscheidung Punkt 5);
   kanonische Metadaten bleiben in Postgres (`MemoryEntry` etc.), Qdrant hält nur Vektoren +
   Punkt-ID = `MemoryEntry.id`; **kein Auto-Fallback** — ein Ausfall ist `degraded`, nicht „leer";
   Reconciliation analog `memory_reconcile`; Backup-/Restore-Erweiterung als expliziter Punkt.
4. *Konsequenz?* Ohne Gegenmaßnahmen: Tenant-Leak, stille Inkonsistenz, unvollständiges Restore.
   Mit Gegenmaßnahmen: eine zusätzliche, optionale Infrastruktur-Komponente mit benannten
   Betriebsgrenzen — Aufwand und Verantwortung sind sichtbar, statt implizit.

---

## Alternativen

### Option A: pgvector-only bestätigen (die L2-Festlegung bleibt) — VERWORFEN

**Beschreibung:** Keine Revision. Die Vektorsuche bleibt vollständig embedded; die vier
Spalten und die vier direkten ANN-Sites bleiben wie heute.

**Abwägung:** Maximale Einfachheit (ein Deployment-Unit, RLS-stark, ein Backup-Pfad) und volle
Konsistenz mit `REQ-L1-018` (Self-Hosted). Aber sie beantwortet die Wachstums-/Skalierungs- und
Optionsthematik (#1178, Artefakt-Scope, Hybrid) gar nicht und bindet die Architektur dauerhaft
an eine Entscheidung, die ohne Betriebserfahrung mit Qdrant als „abgelehnt" markiert wurde. Als
**reine Absicherung** bleibt sie der Referenzpfad, ist aber als alleinige Festlegung zu eng.

**Risiko:** NIEDRIG im Aufwand, HOCH darin, die eigentliche Frage offen zu lassen.

### Option B: Qdrant nur für Memory (V1), ohne Artefakt-Suche — VERWORFEN (kleinster Schritt)

**Beschreibung:** Neuer `QdrantMemoryBackend` (`@register_memory_backend("qdrant")`) nutzt die
**vorhandene** `MemoryBackend`-Abstraktion; die vier direkten ORM-ANN-Sites bleiben unangetastet.

**Abwägung:** Kleinster Fußabdruck — die Vektor-Port-Abstraktion entfällt, weil
`MemoryBackend.query` schon eine Fassade ist. Deckt aber die eigentliche Skalierungsfrage
(Artefakt-Suche über 10.000+ Requirements/TraceLinks/ICDs) nicht und lässt zwei
ANN-Realitäten nebeneinander bestehen (Memory „portabel", Artefakte „hardcodiert pgvector").
Als Zwischenschritt wertvoll, als Endentscheidung inkonsistent.

**Risiko:** NIEDRIG – MITTEL; löst die Hälfte des Problems und erzeugt eine dauerhafte Asymmetrie.

### Option C: Qdrant V1 (Memory) + V2 (Artefakt-Suche über Vektor-Port) — GEWÄHLT

**Beschreibung:** Zweistufig. **V1** ergänzt einen registrierten `QdrantMemoryBackend` über die
bestehende `MemoryBackend`-Oberfläche. **V2** führt eine **neue Vektor-Port-Abstraktion** ein, die
die vier direkten `CosineDistance`-Sites (`search_service.py:608/631/661`,
`requirement_service.py:1001`, `trace_link_service.py:915`, `icd_manager.py:720`) von der
konkreten Vektordatenbank entkoppelt; Adapter: pgvector (Default) und Qdrant.

**Abwägung:** Einzige Option, die (a) den Default unberührt lässt, (b) die vorhandene
Memory-Abstraktion respektiert statt daneben zu bauen, und (c) die Artefakt-Suche über **einen**
Port vereinheitlicht — womit #1178 denselben Weg mitnutzen kann. Preis: V2 ist strukturell
invasiv (vier Aufrufer, ein neues Interface) und muss als Strangler mit pgvector-Adapter
abgesichert werden.

**Risiko:** MITTEL (V1) / GROSS (V2) — aber additiv, Default-stabil und durch bestehende
Semantik-Tests als Sicherheitsnetz fassbar.

### Option D: anderer externer Dienst (Milvus/Weaviate) — VERWORFEN

**Beschreibung:** Ein anderer externer Vektordienst statt Qdrant.

**Abwägung:** Verworfen. Qdrant ist bereits die in #1204 benannte, in der L2-Ablehnung
explizit adressierte Option; ein weiterer Dienst würde dieselbe Isolations-/Backup-Frage ohne
Mehrwert erneut aufwerfen. Milvus/Weaviate sind schwergewichtiger zu betreiben und in diesem
Projekt nicht verankert. Die Entscheidung bleibt Qdrant-spezifisch; ein Dienstwechsel wäre ein
eigenes ADR.

**Risiko:** HOCH (neue Betriebs- und Bewertungsoberfläche ohne Vorgeschichte).

---

## Entscheidung

**Vorgeschlagene Entscheidung: Option C — Revision der L2-Festlegung, Qdrant optional, V1+V2.**

### 1. Revision der L2-Festlegung (explizit zur Disposition gestellt)

Die in `L2_VectorSearchServiceSystem_Requirements.md:32,36` (und
`L2_architectural_decomposition_iter-1.md:55,59`) festgehaltene Ablehnung eines externen
Vektordienstes wird **revidiert**: pgvector bleibt **Default und Pflichtpfad**, ein externer
Qdrant-Dienst wird als **optionale** zweite Betriebsart zugelassen. Die zugrunde liegende
Rationale der L2 (Self-Hosted, keine Zusatzinfrastruktur) wird **nicht** aufgegeben: Qdrant läuft
nur in einem expliziten, opt-in Compose-Profil und ist im Default „abwesend" (kostet nichts).
Mit Annahme dieses ADR sind die betroffenen REQs (`affected_reqs`) zu aktualisieren; die
L2-REQ-Datei ist entsprechend fortzuschreiben (Architektur-Abschnitt `:32,36`). **Dieses ADR
ändert die REQ-Datei nicht** — die Fortschreibung ist Folgeaufgabe nach `proposed → accepted`.

### 2. Collection-Strategie A — harte Isolationsgrenze über Namensräume

- **Eine Collection pro Workspace:** `<prefix>_<tenant>_<workspace>`.
- **`user`-Scope-Sonderfall:** der `user`-Scope hat keine `workspace_id` → eigene Collection
  `<prefix>_<tenant>_user` (`MemoryEntry.SCOPE_USER`, `memory/models.py:62-69`).
- **Artefakt-Trennung als eigene Collection:** `<prefix>_<tenant>_<workspace>_artifacts`
  (bzw. pro Artefakt-Scope; Granularität: s. §Offene Entscheidungen).
- **Workspace-Löschung = `drop collection`.** Die Collection ist die Isolationsgrenze; ein
  Workspace-Löschen entfernt seine Vektoren vollständig und selektiv, ohne Query über fremde
  Daten.
- `QDRANT_COLLECTION_PREFIX` ist konfigurierbar (Default analog Projekt-Präfix „reqlo").

### 3. Umfang V1 + V2

- **V1 — Memory:** neuer `QdrantMemoryBackend` in `backend/memory/qdrant_backend.py`,
  registriert via `@register_memory_backend("qdrant")`, Import in `backend/memory/apps.py`
  (Muster `import memory.honcho_backend`, `apps.py:67`); nutzt die vorhandene
  `MemoryBackend`-Oberfläche (Fassade `query`/`upsert`/`list_recent`/`forget` + kanonische
  Store-API `write`/`list_entries`/`count`/`delete_entry`/`delete_scope`/`health`/`digest`).
- **V2 — Artefakt-Suche:** neue **Vektor-Port-Abstraktion**; die vier direkten
  `CosineDistance`-Sites werden auf den Port umgestellt. Adapter: pgvector (Default) und
  Qdrant. `enable_iterative_ann_scan` (`backend/application/pgvector_ann.py`) bleibt
  pgvector-spezifisch und wird nicht über den Port verallgemeinert.
- **Reihenfolge:** V1 vor V2; V2 als Strangler mit pgvector-Adapter (bestehende Semantik-Tests
  bleiben grün).

### 4. Default bleibt pgvector — Qdrant nur opt-in

- `MEMORY_BACKEND=pgvector` (Default) ändert sich **nicht**; `SystemMemorySettings.memory_backend`
  gewinnt weiterhin vor der Env (`backends.py:547-556`).
- Qdrant nur aktiv bei `MEMORY_BACKEND=qdrant` **und** aktivem Compose-Profil `qdrant`
  (Service analog honcho `deploy/docker-compose.yml:1137`, bluepencil `:1453`), mit Volume und
  Healthcheck, **ohne** Host-Port nach außen.
- **Kein Auto-Fallback:** ist Qdrant konfiguriert, aber unerreichbar, wird **nicht** still auf
  pgvector ausgewichen. Der Zustand wird als `degraded` gemeldet (`memory/health.py`,
  `envelope()`), konsistent zur F9-Trennung „Backend down" vs. „nichts erinnert".

### 5. Konsistenzmodell und Isolation

- **Kanonische Quelle bleibt Postgres:** `mem_memory_entry` (V1) bzw. `pl_requirement`/
  `pl_tracelink`/`icd_icd` (V2) sind Source of Truth; die RLS-Tabelle bleibt FORCE-RLS
  (`memory/migrations/0004:32-46`). Qdrant ist **nur Vektorindex**.
- **Punkt-ID = `MemoryEntry.id`** (V1). `MemoryEntry.backend_ref` trägt weiterhin die externe
  ID; die Reconciliation erfolgt analog
  `backend/memory/management/commands/memory_reconcile.py` (READ-ONLY Report lokal vs. extern).
- **Isolation ist app-erzwungen, nicht RLS:** Qdrant kennt kein Postgres-RLS. Die Collection-Wahl
  ist daher **sicherheitskritische Anwendungslogik** → ein **Guard-Test** sichert ab, dass jeder
  Zugriff genau eine tenant-/workspace-korrekte Collection adressiert und kein Query
  collection-übergreifend läuft (Cross-Tenant → Fehler, kein stilles Leerergebnis).

### 6. Env-Knöpfe und Settings

- Vorgeschlagene Env-Variablen (analog `HONCHO_*`): `QDRANT_BASE_URL`, `QDRANT_API_KEY`,
  `QDRANT_TIMEOUT`, `QDRANT_DISTANCE`, `QDRANT_COLLECTION_PREFIX`,
  `QDRANT_HNSW_M`/`QDRANT_HNSW_EF_CONSTRUCT`, `QDRANT_PREFER_GRPC`.
- **Kein eigenes `QDRANT_VECTOR_DIMENSIONS`**: die Dimension MUSS
  `EMBEDDING_VECTOR_DIMENSIONS` spiegeln (`persistence/embedding_dimensions.py:132`) — analog zur
  bestehenden Honcho-Dimension-Warnung (`deploy/README.md:237`). Eine Drift ist ein
  Konfigurationsfehler und muss fail-loud sein.
- `SystemMemorySettings`-Override-Felder + Admin-UI (Analogie zu den bestehenden
  Embedding-Overrides, `memory/apps.py:23-46`).

### Was diese Entscheidung *nicht* ist

Sie ist **keine** Ablösung von pgvector und **keine** Pflicht-Zusatzinfrastruktur. Sie ist die
Aussage, dass ein zweiter, **optionaler** Vektor-Backend zulässig ist und die L2-Ablehnung ihm
nicht mehr entgegensteht — ohne den Default, die App-erzwungene Isolation oder die kanonische
Postgres-Wahrheit aufzugeben.

---

## Konsequenzen

**Positiv:**

- **Optionale Skalierung** ohne Default-Last: Qdrant existiert nur hinter dem Profil; ein
  Standard-Deployment ist byte-gleich zu heute.
- **Harte Isolationsgrenze** durch eine Collection pro Workspace; Workspace-Löschung ist ein
  `drop collection` statt einer Massen-Query.
- **Wiederverwendung der bestehenden Abstraktion** (V1 über `MemoryBackend`), minimale neue
  Fläche; Honcho bleibt unberührt (orthogonale Achse).
- **Vereinheitlichung** der Artefakt-Suche über den Vektor-Port (V2) — `#1178` kann denselben Weg
  mitnutzen, statt einen fünften ANN-Pfad zu bauen.
- **Explizite Betriebsgrenzen**: „kein Auto-Fallback" macht einen Ausfall sichtbar, statt ihn zu
  verschleiern.

**Negativ:**

- **Revision einer bestehenden Architektur-Festlegung.** Die L2-Zeilen `:32,36` und die
  Zerlegung `:55,59` verlieren ihre Gültigkeit und müssen fortgeschrieben werden; bis dahin
  besteht ein bewusster Doku-Widerspruch (dieses ADR stellt ihn her und benennt ihn).
- **Collection-Sprawl/Fan-out.** „Eine Collection pro Workspace" erzeugt viele Collections; bei
  vielen Tenants/Workspaces ist das eine Betriebs- und Metadaten-Last, die überwacht werden muss.
- **Weiche Isolation.** Qdrant kennt kein RLS; die Isolation ist **app-erzwungen** und damit nur
  so gut wie der Guard-Test und die Disziplin der Collection-Wahl. Ein Fehler hier ist ein
  Cross-Tenant-Risiko.
- **Zwei Vektor-Wahrheiten.** Postgres-Zeile und Qdrant-Punkt können driften; es braucht
  Reconciliation, Reindex-Workflow und einen `degraded`-Pfad.
- **Backup-/Restore-Erweiterung.** Der Postgres-Sidecar (ADR-012) deckt den Qdrant-Vektorindex
  **nicht** ab. Ohne Erweiterung ist ein Restore unvollständig — der Index ist zwar aus den
  kanonischen Zeilen re-generierbar, aber der Wiederaufbau muss dokumentiert und getestet sein.
- **Dimension-Drift.** Ein eigenes Dimensionsfeld ist verboten; die Kopplung an die SSOT muss
  getestet/erzwungen werden.
- **V2 ist invasiv.** Vier ANN-Aufrufer werden auf einen neuen Port umgestellt; ohne
  pgvector-Adapter + bestehende Tests entsteht ein Regressionsrisiko.
- **`open_adrs`-Feld existiert repo-weit nicht** (vgl. ADR-016 §4, `AUD-2026-09-333`): die
  REQ↔ADR-Verknüpfung bleibt eine belegte Näherung.
- **Freigabe ausstehend:** Status `proposed`; Umsetzung erst nach `proposed → accepted` durch den
  User.

---

## Abnahmekriterien

> Übernommen aus #1204, abgeglichen mit dem code-verifizierten Plan
> `docs/plans/2026-10-07-umsetzungsplaene-1155-1201-1202-1204.md` §4.8. AC beziehen sich auf die
> Umsetzung **nach** `proposed → accepted`; das ADR selbst implementiert nichts.

- [ ] **AC-ADR:** ADR-020 ist entschieden (Collection-Strategie A, Umfang V1+V2, pgvector Default)
      und `accepted`; die L2-REQ-Ablehnung (`:32,36`) ist revidiert.
- [ ] **AC-V1:** `MEMORY_BACKEND=qdrant` funktioniert als optionaler `MemoryBackend`;
      `memory.query`/`digest`/`ask`/`write` verhalten sich vertragskonform
      (`backend/memory/tests/test_backend_contract.py` grün).
- [ ] **AC-V1-Default:** Der pgvector-Default ist unberührt; ohne Profil/`MEMORY_BACKEND=qdrant`
      ändert sich das Deployment-Verhalten nicht.
- [ ] **AC-Isolation:** Collection-Isolation ist app-erzwungen und durch einen Guard-Test
      abgesichert (kein collection-übergreifender Zugriff; Cross-Tenant → Fehler statt Leerlauf).
- [ ] **AC-Konsistenz:** `mem_memory_entry` bleibt Source of Truth; Punkt-ID = `MemoryEntry.id`;
      eine Reconciliation (analog `memory_reconcile`) weist Drift nach.
- [ ] **AC-Fallback:** Kein Auto-Fallback — ein unerreichbarer Qdrant-Dienst meldet `degraded`,
      nicht „leer".
- [ ] **AC-Qdrant-Config:** Env-Knöpfe inkl. `QDRANT_BASE_URL`/`QDRANT_COLLECTION_PREFIX` u. a.;
      **kein** `QDRANT_VECTOR_DIMENSIONS`; Dimension spiegelt `EMBEDDING_VECTOR_DIMENSIONS`.
- [ ] **AC-Compose:** Compose-Profil `qdrant` (Service + Volume + Healthcheck, kein öffentlicher
      Host-Port); `docker compose config` ohne Profil unverändert.
- [ ] **AC-V2:** Vektor-Port existiert; die vier direkten `CosineDistance`-Sites sind überführt;
      bestehende Semantik-Suche-Tests bleiben grün (pgvector-Adapter).
- [ ] **AC-Backup:** Backup-/Restore-Route für den Qdrant-Index ist benannt/umgesetzt (Index
      re-generierbar aus den kanonischen Zeilen).

---

## Offene Entscheidungen

1. **O1 — Artefakt-Trennung: Collection vs. Payload.** Gewählt ist eine eigene
   `_artifacts`-Collection; falls gewünscht, könnte Artefakt-Trennung stattdessen über
   Payload-Filter innerhalb der Workspace-Collection laufen. Granularität ist zu präzisieren:
   **eine** `_artifacts`-Collection pro Workspace vs. eine pro Artefakt-Scope.
2. **O2 — `QDRANT_DISTANCE`-Default.** Cosine (konsistent zu `vector_cosine_ops`) als Default;
   Dot-/Euclid-Betrieb müsste bewusst abweichen.
3. **O3 — #1023-Blast-Radius.** Wie weit wirkt die Artefakt-Scope-/Prompt-Injektionslogik
   (#1023) in die V2-Port-Abstraktion hinein? Vor V2-Umsetzung verifizieren.
4. **O4 — Qdrant ↔ kanonische `MemoryEntry`.** Mapping-/`backend_ref`-Vertrag, Reindex-Workflow
   und der Umgang mit verwaisten Punkten (analog `memory_reconcile`-Findings).
5. **O5 — Backup/Restore des Qdrant-Volumes.** Reine Re-Generierung aus Postgres oder echtes
   Volumen-Backup? (Berührt ADR-012.)
6. **O6 — V2 eigenes ADR?** Ob V2 ein separates ADR braucht oder Teil von ADR-020 bleibt.
7. **O7 — Qdrant je in der Default-Topologie?** Empfehlung: nein, ausschließlich Profil.
8. **O8 — Guard-Test-Design.** Konkrete Form des Isolation-Guards (Collection-Namens-Assertions vs.
   injizierter Tenant-/Workspace-Zwang im Backend/Port).

**STOP-Gate:** Bis zur Klärung von O1–O8 und der User-Freigabe wird **nichts** implementiert —
kein `QdrantMemoryBackend`, keine Compose-Änderung, kein Vektor-Port, keine Migration. Dieses ADR
ist eine Entscheidungsvorlage (Status `proposed`).

---

## Review-Round-Trail

**Ausstehend.** Noch kein Review durchgeführt (Status `proposed`). Geplanter Lifecycle analog
ADR-019: `concept-reviewer`-/`se-critic`-Review → Findings → Iteration(en) → Review-Protokoll/
-Report unter `docs/se/reviews/` bzw. `docs/se/reports/`. Tabelle wird nach dem ersten Review
befüllt.

| Review | Iter. | Verdict | Findings | Handling |
|---|---|---|---|---|
| — | — | ausstehend | — | — |

---

*Erstellt durch `planner` am 2026-10-07 als Entscheidungsvorlage (Status `proposed`).*
*Kein Produktcode, keine Migration, keine Compose-/Config-Änderung, keine REQ-Datei-Änderung,
kein Commit. Die L2-Fortschreibung erfolgt erst nach `proposed → accepted`.*
