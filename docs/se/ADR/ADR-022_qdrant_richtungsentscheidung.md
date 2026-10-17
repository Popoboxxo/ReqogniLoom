---
adr_id: ADR-022
title: "Qdrant-Richtungsentscheidung — Abkündigung (Option A) vs. Vollbetrieb (Option B) des optionalen Vektor-Backends; Revision von ADR-020"
status: proposed
date: "2026-10-17"
deciders: [user, se-architect]
affected_reqs: [REQ-L1-038, REQ-L2-VS-001, REQ-L2-VS-002, REQ-L2-VS-003, REQ-L2-VS-004]
superseded_by: null
---

# ADR-022: Qdrant-Richtungsentscheidung — Abkündigung vs. Vollbetrieb (Revision von ADR-020)

**Status:** proposed (2026-10-17) — **Entscheidung offen**; dieses ADR implementiert nichts.
**Blockiert:** Die Umsetzung von **#1334** (Artefakt-Indexer) und **#1314** (Qdrant-Konfiguration)
ist bis zur Annahme dieses ADR **blockiert** — kein Code vor der Richtungsentscheidung
(Runde-5-Plan, Entscheidungsspur D5, `docs/audit/2026-10/bugfix-round-5-plan.md`).
**Datum:** 2026-10-17
**Entscheider (vorgeschlagen):** `user`, `se-architect`; **Autor:** `concept-specifier`
(Entscheidungsvorbereitung D5, Branch `docs/round5-decision-prep-d5-d7`, Basis
`origin/main @ 12cce237`; kein Commit).
**Betroffene REQs:** REQ-L1-038 (Vektorsuche),
REQ-L2-VS-001…-004 (`docs/se/L1/Gesamtsystem/L2/VectorSearchServiceSystem/L2_VectorSearchServiceSystem_Requirements.md`).
**Bezug (Issues):** #1314 (Qdrant-Konfiguration nutzt das Backend nicht aus), #1334 (Artefakt-
Indexer fehlt, `_artifacts`-Collections leer), #1316 (Hybrid-Suche), #1250 (geschlossen —
Qdrant-Write fail-loud), #1251 (geschlossen — Qdrant-Doku), #1204 (ADR-020-Umsetzung),
#1178 (Duplikaterkennung), #1300 (Lern-Kreislauf). **Vorgänger:** ADR-020 (`accepted`,
2026-10-07) — bei Annahme von Option A wird ADR-020 in seinen Qdrant-Teilen durch dieses ADR
abgelöst; der Statuswechsel (`superseded_by: ADR-022`) erfolgt **ausschließlich durch
`se-architect`/`user`** und ist Folgeaufgabe, nicht Teil dieses Entwurfs.

**Bezug zum Code** (verifiziert am 2026-10-17 im Arbeitsbaum, `origin/main @ 12cce237`):

- `backend/application/vector_port.py:1-45` — Vektor-Port für die Artefakt-Suche (ADR-020 V2);
  `:82` `DEFAULT_ARTIFACT_VECTOR_BACKEND = "pgvector"`; Qdrant-Adapter nur bei explizitem
  Opt-in (`ARTIFACT_VECTOR_BACKEND=qdrant` **und** effektivem `MEMORY_BACKEND=qdrant` **und**
  importierbarem `qdrant_client` **und** konfigurierter Base-URL; die Doku im Modul benennt
  selbst: „the per-workspace `_artifacts` collections are populated by an artifact indexer
  that is *out of scope* for this port; without one the collections are empty".
- `backend/persistence/qdrant_config.py` — `QdrantConfig`, `resolve_qdrant_config`,
  `build_collection_name` (Collection-Schema `<prefix>_<tenant>_<workspace>`, `_artifacts`,
  `_user`).
- `backend/memory/qdrant_backend.py` — `QdrantMemoryBackend` (`MemoryBackend`-Registry);
  fail-loud/-degraded-Verhalten aus #1250-Fix vorhanden.
- `backend/memory/models.py:186-194` — `SystemMemorySettings.qdrant_*`-Felder (bewusst **kein**
  Dimensionsfeld; Dimension spiegelt `EMBEDDING_VECTOR_DIMENSIONS`).
- `deploy/docker-compose.yml:1518-1545` — Service `qdrant` hinter Profil `["qdrant"]`,
  `qdrant/qdrant:v1.19.2@sha256:b7b0444c…` (Tag **und** Digest), Volume `qdrant_data`,
  Healthcheck, **kein** Host-Port.
- `backend/application/search_service.py:20-26, 1017-1029, 1118-1128` — **drei Suchpässe**
  (Full-Text, lexikalisch, semantisch) mit **RRF-Fusion** (`_rrf_fuse`), eingeführt am
  2026-08-26 (Commit `32bf40be`, #746) und dimensionell nachgezogen für #794; Tests:
  `backend/application/tests/test_search_semantic_fusion.py`.
- Tests zur Qdrant-Optionalität: `backend/memory/tests/test_qdrant_backend.py`,
  `backend/application/tests/test_vector_port.py`,
  `backend/reqogniloom/tests/test_health_qdrant_optional_adr020.py`.

**Gegenprüfung zu den Issue-Aussagen** (Abweichungen sind entscheidungsrelevant und hier
offengelegt):

1. **#1250/#1251 sind geschlossen.** Der Fix aus Runde 3 (fail-loud statt stillem Drop,
  Health-Signal, Reconcile-Pfad; Runde-3-Plan §4.18) ist auf `main`. Formulierungen in
  #1314/#1334, die #1250 als offene Voraussetzung zitieren, sind **historisch** (Stand
  beta.20) und vor Umsetzung zu aktualisieren.
2. **#1316 „sie werden nie kombiniert" trifft auf diesen Stand nicht zu.** Ein RRF-
   Fusionspfad existiert bereits (semantisch + FTS + lexikalisch, `search_service.py`, siehe
   oben). Der verbleibende Delta laut Code: `_EMBEDDABLE_TYPES = {Requirement, TraceLink, Icd}`,
   aber nur `Requirement` ist heute über den öffentlichen `type_filter` verdrahtet; ein
   expliziter `mode`-Parameter (`vector|keyword|hybrid`) fehlt; eine Recall-Messung fehlt.
   → #1316 ist **umzuformulieren/präzisieren**, bevor daraus Umsetzung wird.

**Vermerk zur Ablage:** `docs/se/ADR/` ist die gelebte Konvention (ADR-001…021 + ADR-DS-02).
Dieses ADR folgt ihr (vgl. ADR-020/021). Es ändert keine REQ-Datei, keine Kaskaden-Datei und
keinen Code.

---

## Entscheidungsvorlage

- **Was ist zu entscheiden:** Ob der mit ADR-020 eingeschlagene Qdrant-Pfad **weiterverfolgt
  (Option B: Vollbetrieb inkl. Artefakt-Indexer und Store-seitiger Hybrid-Suche)** oder
  **abgekündigt wird (Option A: pgvector trägt; Rückbau als eigener Schnitt)**. Der heutige
  Zwischenzustand (Qdrant optional vorhanden, aber ohne Nutzen) ist keine dauerhafte Lösung.
- **Empfehlung (Entwurf):** **Option A — Qdrant abkündigen**, mit benannter Wiedervorlage.
  Begründung: pgvector trägt die gesamte **gemessene** Last (3.074 Vektoren in 52 MB inkl.
  HNSW + FTS + Scope-Indizes); Qdrant hält 1 Punkt und hat 0 Artefakt-Punkte; der Nutzen von
  Option B hängt an einem **nicht existenten Artefakt-Indexer** (#1334 = Embedding-Erzeugung
  für 11 von 14 Typen + Hooks + Backfill) und an Store-Fähigkeiten, die heute niemand nutzt.
  Hybrid-Suche (das stärkste B-Argument) existiert bereits pgvector-seitig (RRF) und ist dort
  erweiterbar.
- **Konsequenz bei Annahme (Option A):** ADR-020 wird in seinen Qdrant-Teilen abgelöst;
  #1334/#1314 werden geschlossen bzw. auf „nicht weiterverfolgt" gestellt; #1316 wird auf den
  pgvector-Delta reduziert; ein Rückbau-Schnitt (Scope-Skizze unten) wird als eigenes Issue
  geplant; die Qdrant-Komponenten bleiben bis dahin **eingefroren** (keine weitere Investition).
- **Konsequenz bei Annahme (Option B):** Multi-Issue-Programm (Größe L): #1250-Verifikation,
  Payload-Indizes, Sparse Vectors/Hybrid, Quantization, Snapshot-Pfad, #1334-Indexer,
  #1316-Qdrant-Variante, Doku — siehe Umsetzungsschnitt unten.
- **Grober Aufwand:** Entscheidung = klein; Option A (Rückbau) = mittel, gut schneidbar;
  Option B = groß (v. a. #1334). Belastbare Zahlen bei `effort-estimator`.
- **Offene Punkte:** s. §Offene Entscheidungen (O1–O5).

---

## Kontext

**1. ADR-020 hat Qdrant als optionale zweite Betriebsart zugelassen — und die Umsetzung ist
weitgehend gebaut.** ADR-020 (accepted 2026-10-07, User-Freigabe) revidierte die L2-Festlegung
„pgvector-only" zugunsten eines optionalen Qdrant-Backends (V1 = Memory über
`MemoryBackend`, V2 = Artefakt-Suche über einen neuen Vektor-Port; Collection-Strategie A;
Default bleibt pgvector; kein Auto-Fallback). Der V1-Backend, der V2-Port, die Compose-
Rückendeckung (Profil, Tag+Digest-Pin, Volume) und die Health-/Guard-Pfade existieren im
Arbeitsbaum (siehe „Bezug zum Code"). Was **fehlt**, ist die Befüllung: Die
`_artifacts`-Collections werden von **niemandem** beschrieben — ein Artefakt-Indexer ist
laut Port-Doku bewusst außerhalb des Ports und existiert nicht.

**2. Die Messlage (beta.20/QS, Issues #1314/#1334):** Drei Collections mit zusammen 1 Punkt
(Testartefakt), 768d, Cosine, HNSW gesetzt; **kein** Payload-Index, **keine** Sparse Vectors,
**keine** Quantization. `PointStruct`/`upsert` kommt im gesamten Backend nur in
`backend/memory/qdrant_backend.py` vor (eigene Gegenprüfung: `PointStruct` außerhalb von
Tests ausschließlich dort) — die Artefakt-Collections sind strukturell leer. Gleichzeitig:
pgvector hält 3.074 Vektoren in 52 MB mit HNSW **und** GIN/FTS **und** Scope-Indizes.

**3. Der Zwischenzustand ist der schlechteste Zustand.** Qdrant kostet einen optionalen
Container, ein Volume, eine zweite Vektor-Wahrheit (ADR-020 §5) und eine Backup-Lücke
(ADR-012 deckt das Volume nicht), liefert aber heute keinen Produktnutzen — und verleitet zu
der Annahme, man habe einen skalierbaren Vektor-Store.

**4. Drei Randbedingungen des Entwurfs:**

- **„Abkündigen" ≠ sofort löschen.** Option A wird hier als *Richtungsentscheidung* definiert:
  keine weitere Investition, kein Ausbau; der eigentliche Rückbau ist ein eigener, schneidbarer
  Folgeschnitt (O1). Bis dahin bleiben Code/Profil wie sie sind — funktionsfähig, aber
  eingefroren.
- **Hybrid ist keine Qdrant-Frage (mehr).** Der RRF-Pfad in `search_service.py` fusioniert
  bereits pgvector-Semantik + FTS + lexikalische Treffer. Der offene Delta (TraceLink/Icd-
  Verdrahtung, `mode`-Parameter, Messung) ist unabhängig von dieser Entscheidung als
  pgvector-Arbeit beschreibbar.
- **Die Sicherheits-/Betriebsgrenzen von ADR-020 gelten fort.** Sollte Option B (oder später
  ein Re-Entry) gewählt werden, bleiben die dort festgelegten Leitplanken bindend
  (Collection-Isolation als app-erzwungene Grenze + Guard-Test, kanonische Quelle Postgres,
  kein Auto-Fallback, Dimension gespiegelt, kein Host-Port).

---

## Alternativen

### Option A: Qdrant abkündigen — pgvector trägt (EMPFOHLEN)

**Beschreibung:** Qdrant wird als nicht weiterverfolgter Optional-Pfad abgekündigt. Keine
Umsetzung von #1334/#1314. #1316 wird auf den pgvector-Delta reduziert (präzisieren, dann
`mode`-Parameter + Messung, ggf. TraceLink/Icd-Verdrahtung). ADR-020 wird in seinen
Qdrant-Teilen abgelöst. Ein Rückbau-Schnitt entfernt (oder friert dauerhaft ein) die
Qdrant-Komponenten: Compose-Service `qdrant` + `x-qdrant-env` + Volume, `qdrant_config.py`,
`qdrant_backend.py`, Qdrant-Adapter und `ARTIFACT_VECTOR_BACKEND`-Selektor in `vector_port.py`,
`SystemMemorySettings.qdrant_*` (+ Migration), Health-Sonderfall
(`test_health_qdrant_optional_adr020.py`), Qdrant-Tests, Doku-Abschnitte (deploy/README).
Der **Vektor-Port selbst bleibt** als Naht bestehen (pgvector-Adapter); er ist die
Einbaustelle für einen späteren Re-Entry.

**Abwägung:** Ein Vektor-Store statt zwei; ein Backup-Pfad statt zweier; RLS-starke Isolation
bleibt überall erhalten (Qdrant-Isolation war app-erzwungen); minimaler Betrieb. Kosten:
Der Weg zu einem externen Store wäre bei späterem Bedarf **neu** zu beschreiten (Dienstwahl,
Backup, Isolation) — allerdings mit dem Vorteil, dann gegen **gemessenen** Bedarf zu planen
statt gegen eine Option. Der gebaute Code wird teilweise wertlos (Rückbau) oder bleibt als
tote, gepflegte Fläche stehen (Einfrieren).

**Risiko:** NIEDRIG–MITTEL. Verzichtet heute auf eine Option, deren Nutzen unbelegt ist;
Wiedervorlage-Kriterium ist benannt (unten).

### Option B: Qdrant vollständig betreiben (Artefakt-Indexer + Store-Hybrid)

**Beschreibung:** Qdrant wird der zweite, ernsthaft betriebene Vektor-Store:

1. **#1250 nachverifizieren** (Fix ist gemergt): Punkt-Writes live prüfen, fail-loud bleibt.
2. **Payload-Indizes** (`scope`, `workspace_id`, `artifact_id`) idempotent beim
   Collection-Anlegen (`_ensure_collection`) — der Filterpfad (`qdrant_backend.py`
   Filter-Query) bekommt seinen Index.
3. **Sparse Vectors** (BM25/miniCOIL) + `prefetch`/`fuse` für Store-seitige Hybrid-Suche.
4. **Quantization** (Scalar int8) inkl. RAM-/Betriebs-Doku.
5. **Snapshot-/Restore-Pfad** für das Qdrant-Volume (ADR-012-Bezug; Index ist aus Postgres
   re-generierbar, der Wiederaufbau muss dokumentiert und getestet sein).
6. **#1334 Artefakt-Indexer:** generischer Indexer, Quelle = Artefakt-Datensatz, Ziel = ein
   Punkt mit Payload `artifact_type`/`artifact_id`/`workspace_id`/`tenant_id`; Embedding-
   Erzeugung für **alle 14 Typen** (11 Typen haben heute keine Vektor-Spalte), Hooks in allen
   Artefakt-Services (anlegen/**ändern**/**löschen** — Lösch-Hooks sind Pflicht), Backfill für
   den Bestand (2.338 Artefakte; bereits eingebettete Zeilen nur upserten), idempotente
   Punkt-IDs.
7. **#1316-Qdrant-Variante:** Hybrid dann über Sparse Vectors — **eine** der beiden Welten,
   nicht beide halb (die pgvector-RRF-Arbeit entfällt dann bzw. bleibt auf pgvector-Only-
   Deployments beschränkt).
8. `ARTIFACT_VECTOR_BACKEND=qdrant` wird erst nach dem Indexer als *supported* markiert;
   Guard-Tests + Doku mitziehen.

**Abwägung:** Einzige Option, die (a) typübergreifende Artefakt-Suche in **einer** Collection
ermöglicht (das kann pgvector ohne generische Vektor-Ablage nicht), (b) hybride Suche auf
Store-Ebene freischaltet und (c) den Weg zu Skalierung jenseits RAM-bound pgvector offen hält.
Preis: ein Multi-Issue-Programm mit Index-Konsistenz, zwei Vektor-Wahrheiten, zusätzlicher
Betriebslast (Snapshot, Monitoring, Collection-Sprawl) und dem Backfill über den Bestand —
gegen einen heute **nicht gemessenen** Bedarf (die Collections sind leer, pgvector trägt).

**Risiko:** GROSS (Umfang, dauerhafte Betriebslast) — aber architektonisch abgesichert durch
ADR-020 (Isolation, kein Auto-Fallback, kanonische Quelle).

### Option C: Zwischenzustand beibehalten (heute) — VERWORFEN

**Beschreibung:** Alles bleibt wie es ist; weder Ausbau noch Rückbau.

**Abwägung:** Verworfen. Er kostet Betrieb und Aufmerksamkeit, liefert keinen Nutzen und
verschleiert die Richtungsfrage, statt sie zu beantworten (ausdrücklich als „nicht empfohlen"
in #1314 benannt). Eine dauerhafte Entscheidung „Qdrant bleibt eingefroren, ohne je genutzt zu
werden" wäre nur als zeitlich befristeter Teil von Option A sinnvoll, nicht als Endzustand.

**Risiko:** NIEDRIG im Aufwand, HOCH darin, die eigentliche Frage offen zu lassen.

---

## Entscheidung

**Vorgeschlagene Entscheidung: Option A — Qdrant abkündigen (pgvector trägt); Rückbau als
eigener, schneidbarer Folgeschnitt nach Annahme.**

Begründung (zur Prüfung durch die Entscheider):

1. **Evidenz statt Option:** Die einzige vorliegende Messung zeigt die gesamte Last auf
   pgvector (3.074 Vektoren/52 MB) und Qdrant praktisch leer (1 Punkt). ADR-020 hat Qdrant
   als *Option* zugelassen — eine Option, die nicht genutzt wird und deren Nutzbarmachung
   ein großes Programm (#1334) voraussetzt, ist Kandidat für eine bewusste Abkündigung.
2. **Das stärkste Pro-B-Argument ist bereits eingelöst:** Hybrid-Suche existiert
   pgvector-seitig als RRF-Fusion (`search_service.py`, seit #746). Option B würde sie
   *zusätzlich* (Store-seitig) bauen — nach der #1316-Regel „eine der beiden Welten, nicht
   beide halb" also nicht additiv, sondern als Ersatz, dessen Mehrwert bei leerem Artefakt-
   Index nicht belegbar ist.
3. **Option B ist kein Betrieb, sondern ein Neubau:** 11 von 14 Artefakt-Typen haben heute
   kein Embedding; ein Indexer samt Hooks, Backfill und Konsistenzpfad ist der eigentliche
   Aufwand — zu rechtfertigen nur aus einem gemessenen Bedarf, der heute nicht vorliegt.
4. **Kosten der Abkündigung sind begrenzt und steuerbar:** Rückbau ist schneidbar; bis dahin
   bleibt alles funktionsfähig. Der Vektor-Port bleibt als Naht für einen Re-Entry.
5. **Wiedervorlage (Re-Entry-Kriterium):** Wenn ein **gemessener** Bedarf belegt ist — z. B.
   typübergreifende Artefakt-Suche über die 14 Typen in einer Collection, Duplikaterkennung
   (#1178) außerhalb der pgvector-Grenzen, oder Last-/Recall-Ziele, die pgvector nachweislich
   verfehlt — wird ein **neues ADR** eröffnet; der Vektor-Port ist die vorbereitete
   Einbaustelle. Die Abkündigung ist damit eine Richtungs-, keine Endgültigkeitsentscheidung.

**Bei Annahme (Option A) sofort und als Folgeaufgaben:**

- Dieses ADR `proposed → accepted` (Review-Pfad s. §Review-Round-Trail) — dann ADR-020 in den
  Qdrant-Teilen auf `superseded_by: ADR-022` setzen (nur `se-architect`).
- #1334 und #1314: schließen mit Verweis auf ADR-022 („nicht weiterverfolgt"); #1316:
  umformulieren auf den verifizierten pgvector-Delta (TraceLink/Icd-Verdrahtung,
  `mode`-Parameter, Messung).
- Rückbau-Issue anlegen (Scope-Skizze siehe Option A), Priorität nachgelagert; bis zur
  Umsetzung Code/Profil **eingefroren** (keine Änderungen außer Security-Fixes).
- Doku: deploy/README-Qdrant-Abschnitt auf „abgekündigt, Rückbau geplant" bzw. nach Rückbau
  entfernen.

**Falls Option B angenommen wird:** Der Umsetzungsschnitt aus §Option B (Punkte 1–8) gilt;
#1334 wird zum Leit-Issue, #1314 liefert die Store-Fähigkeiten (2–5), #1316 die Qdrant-
Hybrid-Variante (7); `vector_port.py` bleibt unverändert die Naht, `ARTIFACT_VECTOR_BACKEND`
wird erst nach dem Indexer als supported markiert. Dieses ADR wäre dann mit Option B
`accepted` zu stellen (die Alternativen-/Kontext-Analyse bleibt gültig).

---

## Konsequenzen

**Positiv (Option A):**

- Ein Vektor-Store, eine Wahrheit, ein Backup-Pfad; RLS-starke Isolation bleibt überall.
- Kein Betriebsaufwand für Container/Volume/Index-Konsistenz; keine zweite
  Konfigurationsfläche (`qdrant_*`).
- Der RRF-Pfad wird die *einzige* Hybrid-Implementierung (keine Parallelwelten).
- Die Entscheidung ist evidenzbasiert und mit klarem Re-Entry-Kriterium versehen.

**Negativ (Option A):**

- **Revision einer akzeptierten Entscheidung:** ADR-020 wird teilweise abgelöst; bis zum
  Rückbau besteht ein bewusster Doku-Zwischenstand (ADR-020 accepted, ADR-022 weist ab).
- **Option geht verloren** (bewusst): typübergreifende Artefakt-Suche in einer Collection und
  Skalierung jenseits pgvector sind später **neu** zu erschließen (Dienstwahl, Backup,
  Isolation) — dann aber gegen gemessenen Bedarf.
- **Sunk Cost wird sichtbar:** Der gebaute Qdrant-Anteil (V1/V2-Code, Compose, Tests) wird
  eingefroren oder zurückgebaut — Aufwand ohne Produktnutzen.
- **#1316 bleibt dennoch Arbeit:** Der pgvector-Delta (Verdrahtung, Messung) ist real und
  wird durch die Abkündigung nicht kleiner.

**Positiv (Option B, falls gewählt):** Eine Collection für alle 14 Artefakt-Typen;
Store-seitige Hybrid-Suche; Skalierungsperspektive; ADR-020 bleibt unangetastet gültig.

**Negativ (Option B):** Großes Programm (v. a. Indexer/Backfill); zwei Vektor-Wahrheiten +
Reconcile; dauerhafte Betriebs-/Backup-Last; Quantization/RAM-Doku; Risiko des Aufbaus auf
unbelegten Nutzen.

---

## Abnahmekriterien

> Bezogen auf die **Entscheidung und ihre Folgeschritte**, nicht auf Produktcode.

- [ ] **AC-ADR:** Ein Verdict zu Option A/B ist dokumentiert; dieses ADR steht auf `accepted`
      (oder ist mit Option B entsprechend fortgeschrieben) — Freigabe durch `user`/`se-architect`.
- [ ] **AC-Block-Aufhebung:** Erst mit Annahme dürfen #1334/#1314 (bzw. deren Nachfolger)
      implementiert werden; vorher wurde **kein** Code dazu geschrieben.
- [ ] **AC-Vorgänger (bei A):** ADR-020 trägt `superseded_by: ADR-022` (bzw. eine dokumentierte
      Teil-Ablösung in seinen Qdrant-Teilen); die L2-REQ-Fortschreibung aus ADR-020 wird auf
      den neuen Stand geprüft (Folgeaufgabe).
- [ ] **AC-Issues (bei A):** #1334/#1314 sind geschlossen (Verweis ADR-022); #1316 ist
      umformuliert (verifizierter Delta); Rückbau-Issue existiert mit benanntem Scope.
- [ ] **AC-Issues (bei B):** #1250-Verifikation, Payload-Indizes, Sparse/Quantization-Entscheidung,
      Snapshot-Pfad, #1334-Indexer und #1316-Variante sind als Pakete geschnitten und terminiert.
- [ ] **AC-Doku:** deploy/README und ADR-020-Verweise entsprechen dem Entscheidungsstand.

---

## Offene Entscheidungen

1. **O1 — Rückbau vs. Einfrieren (bei Option A):** Sofortiger Rückbau in einem Schnitt vs.
   dauerhaftes Einfrieren des Qdrant-Codes als „zweite Betriebsart ohne Support". Empfehlung
   des Entwurfs: Rückbau als eigenes Issue planen; bis dahin eingefroren.
2. **O2 — Zukunft des Vektor-Ports:** Der Port bleibt als Naht bestehen (Empfehlung). Ob er
   bei Rückbau auf pgvector reduziert (Qdrant-Adapter entfernt) oder unverändert gelassen wird,
   entscheidet der Rückbau-Schnitt.
3. **O3 — #1316-Präzisierung:** Der verifizierte Delta (TraceLink/Icd im öffentlichen
   `type_filter`, `mode`-Parameter, Recall-Messung) ist vor Umsetzung mit dem Team zu
   bestätigen — die Issue-Beschreibung entspricht nicht dem Codestand.
4. **O4 — Re-Entry-Trigger:** Das qualitative Kriterium („gemessener Bedarf") ist bei Annahme
   mit konkreten Schwellen zu unterlegen (z. B. Recall-Ziel, Datenvolumen, Latenzbudget).
5. **O5 — L2-REQ-Nachführung:** ADR-020 hat die L2-Fortschreibung als Folgeaufgabe markiert;
   mit der Abkündigung ist zu prüfen, welche Teile der damaligen Revision zurückgenommen
   werden müssen (nur Doku, keine Kaskaden-Datei wird durch dieses ADR geändert).

---

## Review-Round-Trail

**Kein Review durchgeführt.** Dieses ADR ist ein **Entwurf** (Entscheidungsvorbereitung D5);
es liegt kein `concept-reviewer`-/`se-critic`-RVW-Protokoll vor, und es wird keines
vorgetäuscht. Verbindlicher Pfad zur Annahme: `concept-reviewer`-Review (Protokoll unter
`docs/se/reviews/`) → Findings/Iterationen → User-Freigabe → `se-architect` setzt den Status.

| Review | Iter. | Verdict | Findings | Handling |
|---|---|---|---|---|
| — | — | nicht durchgeführt (Entwurf, 2026-10-17) | — | — |

---

*Erstellt durch `concept-specifier` am 2026-10-17 als Entscheidungsvorbereitung D5 der
Bugfix-Runde 5 (`docs/audit/2026-10/bugfix-round-5-plan.md`). Enthält keinen Produktcode,
keine Migration, keine Config-Änderung, keine REQ-Datei-Änderung und keinen Commit.*
