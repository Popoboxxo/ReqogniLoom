---
adr_id: ADR-022
title: "Qdrant-Richtungsentscheidung — Abkündigung (Option A) vs. Vollbetrieb (Option B) des optionalen Vektor-Backends; punktuelle Ablösung von ADR-020 §4"
status: accepted
date: "2026-10-26"
deciders: [user, documenter]
affected_reqs: [REQ-L1-038, REQ-L2-VS-001, REQ-L2-VS-002, REQ-L2-VS-003, REQ-L2-VS-004]
superseded_by: null
---

# ADR-022: Qdrant-Richtungsentscheidung — Abkündigung vs. Vollbetrieb (punktuelle Ablösung von ADR-020 §4)

**Status:** accepted (2026-10-26) — **Entscheidung: Option B (Qdrant-Vollbetrieb mit
pgvector-Fallback)**. Nutzerentscheidung vom 2026-10-26
(`docs/plans/2026-10-21-entscheidungen-offen.md` §0b; ENT-X2 = A, ENT-A2 = a). Dieses ADR
implementiert selbst nichts; es legt die Richtung fest.
**Blockiert (historisch, mit Annahme aufgehoben):** Die Umsetzung von **#1334**
(Artefakt-Indexer) und **#1314** (Qdrant-Konfiguration) war bis zur Annahme dieses ADR
**blockiert** — kein Code vor der Richtungsentscheidung (Runde-5-Plan, Entscheidungsspur D5,
`docs/audit/2026-10/bugfix-round-5-plan.md`). Mit der Annahme am 2026-10-26 ist diese Sperre
**aufgehoben**: #1334/#1314 sind freigegeben (siehe §Entscheidung).
**Datum:** 2026-10-26 (Entwurf: 2026-10-17)
**Entscheider:** `user`; **Text:** `documenter` (ENT-X4 = A: Texte `documenter`, Review
`concept-reviewer`, Status Nutzer). **Autor des Entwurfs:** `concept-specifier`
(Entscheidungsvorbereitung D5, Branch `docs/round5-decision-prep-d5-d7`, Basis
`origin/main @ 12cce237`; kein Commit).
**Betroffene REQs:** REQ-L1-038 (Vektorsuche),
REQ-L2-VS-001…-004 (`docs/se/L1/Gesamtsystem/L2/VectorSearchServiceSystem/L2_VectorSearchServiceSystem_Requirements.md`).
**Bezug (Issues):** #1314 (Qdrant-Konfiguration nutzt das Backend nicht aus), #1334 (Artefakt-
Indexer fehlt, `_artifacts`-Collections leer), #1316 (Hybrid-Suche), #1250 (geschlossen —
Qdrant-Write fail-loud), #1251 (geschlossen — Qdrant-Doku), #1204 (ADR-020-Umsetzung),
#1178 (Duplikaterkennung), #1300 (Lern-Kreislauf). **Vorgänger:** ADR-020 (`accepted`,
2026-10-07). ADR-020 bleibt **`accepted` und unverändert** — es wird **nicht** auf
`superseded` gesetzt (`superseded_by: null`). Die einzige Teil-Ablösung betrifft ADR-020
**§4 „Kein Auto-Fallback"** und ist in §Entscheidung dieses ADR ausdrücklich erklärt
(ENT-A2 = a). Alle übrigen ADR-020-Festlegungen bleiben unverändert gültig.

**Bezug zum Code** (verifiziert am 2026-10-17 im Arbeitsbaum, `origin/main @ 12cce237`):

- `backend/application/vector_port.py:1-45` — Vektor-Port für die Artefakt-Suche (ADR-020 V2);
  `:82` `DEFAULT_ARTIFACT_VECTOR_BACKEND = "pgvector"`; Qdrant-Adapter nur bei explizitem
  Opt-in (`ARTIFACT_VECTOR_BACKEND=qdrant` **und** effektivem `MEMORY_BACKEND=qdrant` **und**
  importierbarem `qdrant_client` **und** konfigurierter Base-URL; die Doku im Modul benennt
  selbst: „the per-workspace `_artifacts` collections are populated by an artifact indexer
  that is *out of scope* for this port; without one the collections are empty".

  > **Änderungsnotiz (2026-10-28, T-A2-1 / PR-A21a):** Der V2-Selektor ist inzwischen vom
  > `MEMORY_BACKEND` entkoppelt — das Gate besteht nur noch aus
  > `ARTIFACT_VECTOR_BACKEND=qdrant`, importierbarem `qdrant_client` und konfigurierter
  > Base-URL. Der ADR-`status` bleibt unverändert (`accepted`); eine Status-/Supersede-Änderung
  > ist ein separates Verfahren.
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

> **Überholt (historischer Wert, Stand Entwurf 2026-10-17).** Diese Vorlage hielt **Option A**
> für empfohlen. Der Nutzer hat am 2026-10-26 **Option B** entschieden
> (`docs/plans/2026-10-21-entscheidungen-offen.md` §0b; ENT-X2 = A, ENT-A2 = a). Die folgende
> Entwurfs-Empfehlung ist damit **vom Nutzer überstimmt** und bleibt nur als Audit-Trail
> stehen; maßgeblich ist §Entscheidung dieses ADR.

- **Was ist zu entscheiden:** Ob der mit ADR-020 eingeschlagene Qdrant-Pfad **weiterverfolgt
  (Option B: Vollbetrieb inkl. Artefakt-Indexer und Store-seitiger Hybrid-Suche)** oder
  **abgekündigt wird (Option A: pgvector trägt; Rückbau als eigener Schnitt)**. Der heutige
  Zwischenzustand (Qdrant optional vorhanden, aber ohne Nutzen) ist keine dauerhafte Lösung.
- **Empfehlung (Entwurf, vom Nutzer überstimmt):** **Option A — Qdrant abkündigen**, mit
  benannter Wiedervorlage. Begründung: pgvector trägt die gesamte **gemessene** Last (3.074
  Vektoren in 52 MB inkl. HNSW + FTS + Scope-Indizes); Qdrant hält 1 Punkt und hat 0
  Artefakt-Punkte; der Nutzen von Option B hängt an einem **nicht existenten Artefakt-Indexer**
  (#1334 = Embedding-Erzeugung für 11 von 14 Typen + Hooks + Backfill) und an
  Store-Fähigkeiten, die heute niemand nutzt. Hybrid-Suche (das stärkste B-Argument) existiert
  bereits pgvector-seitig (RRF) und ist dort erweiterbar. **Entschieden wurde stattdessen
  Option B** (§Entscheidung).
- **Konsequenz bei Annahme (Option A — verworfen):** ADR-020 wird in seinen Qdrant-Teilen
  abgelöst; #1334/#1314 werden geschlossen bzw. auf „nicht weiterverfolgt" gestellt; #1316 wird
  auf den pgvector-Delta reduziert; ein Rückbau-Schnitt (Scope-Skizze unten) wird als eigenes
  Issue geplant; die Qdrant-Komponenten bleiben bis dahin **eingefroren** (keine weitere
  Investition). — *Nicht eingetreten: der Nutzer entschied Option B.*
- **Konsequenz bei Annahme (Option B — gewählt am 2026-10-26):** Multi-Issue-Programm (Größe L):
  #1250-Verifikation, Payload-Indizes, Sparse Vectors/Hybrid, Quantization, Snapshot-Pfad,
  #1334-Indexer, #1316-Qdrant-Variante, Doku — siehe Umsetzungsschnitt unten; zusätzlich der
  **sichtbare pgvector-Fallback** (`degraded:true`, §Entscheidung).
- **Grober Aufwand:** Entscheidung = klein; Option A (Rückbau) = mittel, gut schneidbar;
  Option B = groß (v. a. #1334). Belastbare Zahlen bei `effort-estimator`.
- **Offene Punkte:** s. §Offene Entscheidungen (O1–O5).

---

## Kontext

**1. ADR-020 hat Qdrant als optionale zweite Betriebsart zugelassen — und die Umsetzung ist
weitgehend gebaut.** ADR-020 (accepted 2026-10-07, User-Freigabe) revidierte die L2-Festlegung
„pgvector-only" zugunsten eines optionalen Qdrant-Backends (V1 = Memory über
`MemoryBackend`, V2 = Artefakt-Suche über einen neuen Vektor-Port; Collection-Strategie A;
Default bleibt pgvector; kein Auto-Fallback — §4 hier punktuell abgelöst, s. Punkt 4). Der
V1-Backend, der V2-Port, die Compose-Rückendeckung (Profil, Tag+Digest-Pin, Volume) und die
Health-/Guard-Pfade existieren im
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
- **Die Sicherheits-/Betriebsgrenzen von ADR-020 gelten fort — mit einer Ausnahme.** Mit der
  Wahl von Option B bleiben die dort festgelegten Leitplanken bindend (Collection-Isolation als
  app-erzwungene Grenze + Guard-Test, kanonische Quelle Postgres, Dimension gespiegelt, kein
  Host-Port). **Ausnahme:** Die Regel „kein Auto-Fallback" (ADR-020 §4) ist durch §Entscheidung
  dieses ADR abgelöst — bei unerreichbarem Qdrant fällt der Betrieb sichtbar auf pgvector
  zurück (`degraded:true`).

---

## Alternativen

### Option A: Qdrant abkündigen — pgvector trägt — VERWORFEN

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

*Entwurfs-Empfehlung war Option A; der Nutzer hat am 2026-10-26 **Option B** entschieden
(ENT-X2 = A — der Entwurf wird an die Nutzerentscheidung angepasst, nicht umgekehrt). Diese
Option bleibt als verworfene Alternative dokumentiert.*

### Option B: Qdrant vollständig betreiben (Artefakt-Indexer + Store-Hybrid) — GEWÄHLT

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
ADR-020 (Isolation, kanonische Quelle) und den in §Entscheidung festgelegten **sichtbaren
pgvector-Fallback** (`degraded:true`), der ADR-020 §4 für diesen Punkt ablöst.

### Option C: Zwischenzustand beibehalten (heute) — VERWORFEN

**Beschreibung:** Alles bleibt wie es ist; weder Ausbau noch Rückbau.

**Abwägung:** Verworfen. Er kostet Betrieb und Aufmerksamkeit, liefert keinen Nutzen und
verschleiert die Richtungsfrage, statt sie zu beantworten (ausdrücklich als „nicht empfohlen"
in #1314 benannt). Eine dauerhafte Entscheidung „Qdrant bleibt eingefroren, ohne je genutzt zu
werden" wäre nur als zeitlich befristeter Teil von Option A sinnvoll, nicht als Endzustand.

**Risiko:** NIEDRIG im Aufwand, HOCH darin, die eigentliche Frage offen zu lassen.

---

## Entscheidung

**Entschieden: Option B — Qdrant wird der zweite, ernsthaft betriebene Vektor-Store
(Artefakt-Indexer #1334, Store-seitige Hybrid-Suche/Payload-Indizes/Sparse/Quantization,
Snapshot-Pfad), mit pgvector als sichtbarem Fallback.**

**Grundlage:** Nutzerentscheidung vom 2026-10-26
(`docs/plans/2026-10-21-entscheidungen-offen.md` §0b): **ENT-X2 = A** (Entwurfstexte an die
Nutzerentscheidung anpassen, dann `accepted`; kein Supersede) und **ENT-A2 = a** (ADR-022 löst
ADR-020 §4 ab; Fallback mit `degraded:true` wird umgesetzt). Der Entwurf hatte Option A
empfohlen — der Nutzer hat diese Empfehlung **überstimmt** (Audit-Punkt ENT-X2).

Begründung (Substanz aus der Alternativen-Abwägung, auf B gestellt):

1. **Option B ist die einzige Variante, die (a) typübergreifende Artefakt-Suche über die 14
   Typen in *einer* Collection ermöglicht, (b) hybride Suche auf Store-Ebene freischaltet und
   (c) den Weg zu Skalierung jenseits RAM-bound pgvector offen hält** (§Option B, Abwägung).
2. **Die heutige Lastlage ist Ausgangspunkt, nicht Ziel:** pgvector trägt die gesamte
   gemessene Last (3.074 Vektoren/52 MB), Qdrant ist praktisch leer (1 Punkt). Option B hebt
   genau diese Grenze auf; der Preis ist das Multi-Issue-Programm aus §Option B — vor allem
   #1334 samt Hooks, Backfill über den Bestand (2.338 Artefakte) und Pflicht-Lösch-Hooks.
3. **Option A ist damit bewusst verworfen:** Sie hätte einen Vektor-Store, einen Backup-Pfad
   und minimalen Betrieb geliefert, aber den Weg zu einem externen Store bei späterem Bedarf
   neu eröffnet und die bereits gebaute Qdrant-Fläche (V1/V2-Code, Compose, Tests) entwertet.
4. **Der Rückbau bleibt als Rückfallweg bestehen:** Trägt sich Option B nicht, ist Option A
   (Rückbau als eigener Schnitt) weiterhin möglich; der Vektor-Port bleibt die Naht.

**Teil-Ablösung von ADR-020 §4 (ENT-A2 = a) — ausdrücklich:**

ADR-020 §4 (`docs/se/ADR/ADR-020_qdrant_vektor_backend.md`, Zeilen 257–259) regelt wörtlich:

> „**Kein Auto-Fallback:** ist Qdrant konfiguriert, aber unerreichbar, wird **nicht** still auf
> pgvector ausgewichen. Der Zustand wird als `degraded` gemeldet (`memory/health.py`,
> `envelope()`), konsistent zur F9-Trennung „Backend down" vs. „nichts erinnert"."

Diese Regel wird für diesen Punkt **hiermit abgelöst**. Ab jetzt gilt stattdessen:

- Bei konfiguriertem, aber unerreichbarem Qdrant fällt der Betrieb auf **pgvector zurück**
  **und** meldet `degraded:true` — der Fallback ist **sichtbar, nicht still**.
- Alles Übrige aus ADR-020 bleibt unverändert gültig: Collection-Isolation als
  app-erzwungene Grenze + Guard-Test, kanonische Quelle Postgres, Dimension gespiegelt,
  kein Host-Port.
- **ADR-020 selbst wird nicht auf `superseded` gesetzt und nicht editiert**
  (`superseded_by: null`); die Teil-Ablösung ist ausschließlich hier in ADR-022 erklärt.

**Umsetzungsschnitt (Option B — §Option B Punkte 1–8 gilt):** #1334 wird zum Leit-Issue,
#1314 liefert die Store-Fähigkeiten (Payload-Indizes, Sparse/Hybrid, Quantization,
Snapshot-Pfad), #1316 die Qdrant-Hybrid-Variante; `vector_port.py` bleibt unverändert die
Naht, `ARTIFACT_VECTOR_BACKEND=qdrant` wird erst nach dem Indexer als *supported* markiert.

**Mit Annahme (2026-10-26) sofort und als Folgeaufgaben:**

- Dieses ADR steht auf `accepted` (Review s. §Review-Round-Trail).
- #1334/#1314 sind freigegeben — die frühere Sperre „kein Code vor der Richtungsentscheidung"
  ist **aufgehoben**; #1334 ist Leit-Issue.
- Der **pgvector-Fallback mit `degraded:true`** wird umgesetzt (ENT-A2 = a).
- #1316 wird auf die Qdrant-Variante umgestellt (Hybrid über Sparse Vectors — „eine der beiden
  Welten, nicht beide halb").
- Doku: deploy/README-Qdrant-Abschnitt auf „Option B — Vollbetrieb, pgvector-Fallback"
  fortschreiben.

**Was diese Entscheidung nicht ist:** keine Änderung an ADR-020 (Status/Text bleiben), kein
Rückbau (Option A), kein Supersede (ENT-X2).

---

## Konsequenzen

**Positiv (Option B — gültige Richtung):**

- Eine Collection für alle 14 Artefakt-Typen; Store-seitige Hybrid-Suche; Skalierungsperspektive
  jenseits RAM-bound pgvector.
- Der **sichtbare pgvector-Fallback** (`degraded:true`) hält den Betrieb auch bei
  unerreichbarem Qdrant aufrecht, ohne den Ausfall zu verschweigen (konsistent zur
  F9-Trennung „Backend down" vs. „nichts erinnert").
- ADR-020 bleibt in allen übrigen Punkten gültig — Isolation, kanonische Quelle Postgres und
  Dimension bleiben unberührt; es entsteht kein Supersede-Dschungel.

**Negativ (Option B — gültige Richtung):**

- Großes Programm (v. a. Indexer/Backfill samt Lösch-Hooks); zwei Vektor-Wahrheiten +
  Reconcile; dauerhafte Betriebs-/Backup-Last; Quantization/RAM-Doku.
- Aufbau auf einem heute **nicht gemessenen** Bedarf (die Collections sind leer, pgvector
  trägt) — der Nutzen muss durch Betrieb und Messung erst belegt werden.
- Die punktuelle Ablösung von ADR-020 §4 erzeugt einen bewussten Doku-Zwischenstand: ADR-020
  bleibt `accepted`, §4 ist hier für einen Punkt überholt.

**Positiv (Option A, verworfen):** Ein Vektor-Store, eine Wahrheit, ein Backup-Pfad; kein
Betriebsaufwand für Container/Volume/Index-Konsistenz; der RRF-Pfad wäre die *einzige*
Hybrid-Implementierung.

**Negativ (Option A, verworfen):** Verzichtet auf eine Option, deren Nutzen unbelegt ist;
der gebaute Qdrant-Anteil würde eingefroren oder zurückgebaut (Sunk Cost sichtbar); ein
späterer externer Store wäre neu zu erschließen (Dienstwahl, Backup, Isolation).

---

## Abnahmekriterien

> Bezogen auf die **Entscheidung und ihre Folgeschritte**, nicht auf Produktcode.

- [x] **AC-ADR:** Ein Verdict zu Option A/B ist dokumentiert; dieses ADR steht auf `accepted`
      (Entscheidung Option B, 2026-10-26; Freigabe durch `user`).
- [ ] **AC-Block-Aufhebung:** Mit Annahme (2026-10-26) dürfen #1334/#1314 (bzw. deren
      Nachfolger) implementiert werden; vorher wurde **kein** Code dazu geschrieben.
- [ ] **AC-Vorgänger (bei A) — entfällt mit Option B:** ADR-020 trägt `superseded_by: ADR-022`
      — *nicht eingetreten.* Ergänzend gilt stattdessen: ADR-020 ist **unverändert** `accepted`
      (`superseded_by: null`), und §4 ist in §Entscheidung dieses ADR ausdrücklich für diesen
      Punkt abgelöst (ENT-A2 = a).
- [ ] **AC-Issues (bei A) — entfällt mit Option B:** #1334/#1314 werden geschlossen; #1316 auf
      den pgvector-Delta reduziert; Rückbau-Issue angelegt — *nicht eingetreten.*
- [ ] **AC-Issues (bei B):** #1250-Verifikation, Payload-Indizes, Sparse/Quantization-Entscheidung,
      Snapshot-Pfad, #1334-Indexer und #1316-Variante sind als Pakete geschnitten und terminiert.
- [ ] **AC-Fallback (B):** Ist Qdrant konfiguriert, aber unerreichbar, läuft der Betrieb auf
      pgvector weiter **und** meldet `degraded:true` — der Fallback ist sichtbar, nicht still
      (durch Test/Verhalten belegt; ersetzt ADR-020 §4 „Kein Auto-Fallback").
- [ ] **AC-Doku:** deploy/README und ADR-020-Verweise entsprechen dem Entscheidungsstand
      (Option B, pgvector-Fallback; ADR-020 §4 punktuell abgelöst).

---

## Offene Entscheidungen

1. **O1 — Rückbau vs. Einfrieren (bei Option A) — entfällt mit Option B:** Die Frage stellte
   sich nur im Abkündigungszweig; mit Option B wird nichts zurückgebaut. *Nicht gelöscht, um den
   Entwurfsstand nachvollziehbar zu halten.*
2. **O2 — Zukunft des Vektor-Ports — entfällt mit Option B:** Der Port bleibt mit
   pgvector- **und** Qdrant-Adapter bestehen; die Frage „bei Rückbau auf pgvector reduzieren"
   stellt sich nicht.
3. **O3 — #1316-Präzisierung:** Der verifizierte Delta (TraceLink/Icd im öffentlichen
   `type_filter`, `mode`-Parameter, Recall-Messung) ist vor Umsetzung mit dem Team zu
   bestätigen — die Issue-Beschreibung entspricht nicht dem Codestand.
4. **O4 — Rückfall-Trigger (mit Option B statt Re-Entry):** Das qualitative Kriterium
   („Trägt sich Option B nicht?") ist mit konkreten Schwellen zu unterlegen (z. B. Recall-Ziel,
   Datenvolumen, Latenzbudget); bei Unterschreitung greift Option A (Rückbau).
5. **O5 — L2-REQ-Nachführung:** ADR-020 hat die L2-Fortschreibung als Folgeaufgabe markiert;
   mit Option B ist zu prüfen, ob die damaligen Vektor-Teile unverändert bleiben oder den
   pgvector-Fallback ergänzen (nur Doku, keine Kaskaden-Datei wird durch dieses ADR geändert).

---

## Review-Round-Trail

**Governance-Pfad (ENT-X4 = A):** Texte: `documenter`; Review: `concept-reviewer`; Status:
Nutzer. Diese Textfassung (2026-10-26) setzt die Nutzerentscheidung aus
`docs/plans/2026-10-21-entscheidungen-offen.md` §0b um; das `concept-reviewer`-Review ist
**durchgeführt** (Iteration 1 `CHANGES_REQUESTED`, Iteration 2 `APPROVED`, beide 2026-10-26) und
sein Ergebnis ist **in der Trail-Tabelle dieses Abschnitts** protokolliert; eine separate
Protokoll-Datei wurde bewusst nicht angelegt.
**Accepted vor Review — Reihenfolge bewusst gemäß ENT-X2 = A** („Texte anpassen, dann
`accepted`"); das Review ist nachgelagerte Qualitätssicherung, Korrekturen erfolgen als
Git-Amendment.

| Review | Iter. | Verdict | Findings | Handling |
|---|---|---|---|---|
| `concept-reviewer` | 1 | `CHANGES_REQUESTED` (2026-10-26) | 1 MINOR (m1: Titel-Wortlaut „Revision von ADR-020" überzeichnet die Reichweite), 2 NIT (NIT-1: fehlender §4-Hinweis in §Kontext Punkt 1; NIT-5: Trail-Reihenfolge accepted-vor-Review) | m1 behoben (Titel und H1 auf „punktuelle Ablösung von ADR-020 §4"); NIT-1 und NIT-5 eingearbeitet — in dieser Fassung |
| `concept-reviewer` | 2 | APPROVED (2026-10-26) | — | keine offenen Findings; m1 + NIT-1/NIT-5 bestätigt behoben, keine Regression |

---

*Erstellt durch `concept-specifier` am 2026-10-17 als Entscheidungsvorbereitung D5 der
Bugfix-Runde 5 (`docs/audit/2026-10/bugfix-round-5-plan.md`). Enthält keinen Produktcode,
keine Migration, keine Config-Änderung, keine REQ-Datei-Änderung und keinen Commit.*

*Am 2026-10-26 durch `documenter` an die Nutzerentscheidung (ENT-X2 = A, ENT-A2 = a)
angepasst und auf `accepted` gestellt: Option B ist die getroffene Entscheidung, die
Entwurfs-Empfehlung (Option A) ist als überstimmt gekennzeichnet, ADR-020 §4 ist für diesen
Punkt abgelöst. ADR-020 selbst bleibt unverändert.*
