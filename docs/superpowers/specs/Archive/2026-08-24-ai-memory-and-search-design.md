# KI-Langzeitgedächtnis (Workspace + Tenant-Global) und verbesserte Suche — Design

## Ziel

ReqogniLoom bekommt ein KI-Langzeitgedächtnis auf zwei Ebenen —
**Workspace-Gedächtnis** (projektspezifisch) und **Tenant-globales
User-Gedächtnis** (userspezifisch, workspace-übergreifend, aber
NICHT tenant-übergreifend) — plus eine erweiterte Suche, die dieses
Gedächtnis und bestehende Embeddings mit einbezieht und optional über
Workspace-Grenzen hinweg (innerhalb desselben Tenants) suchen kann.

**Leitprinzip:** Das System bringt per Default alles mit, was es braucht
(kein Pflicht-externer Service) — kann aber wahlweise an externe,
leistungsfähigere Komponenten angedockt werden (Compose-Profil/ENV),
exakt nach dem bereits etablierten Muster der LLM-Provider-Abstraktion
(`backend/llm_adapter/providers.py`: Anthropic/OpenAI/Ollama/Mock
austauschbar).

## Ausgangslage (Ist-Zustand, verifiziert gegen echten Code)

**Bereits vorhanden — wird wiederverwendet, nicht neu gebaut:**

- **pgvector ist bereits installiert und produktiv genutzt.**
  `Requirement.embedding`, `TraceLink.embedding`, `IcdVersion.embedding`
  (`persistence/models.py:901,1245`, `icd/models.py:182`) sind
  `VectorField(dimensions=1536)` mit HNSW-Index. Docker-Compose nutzt
  bereits `pgvector/pgvector:pg16` (`docker-compose.yml:38`,
  `docker/postgres/initdb/10-pgvector.sh`).
- **`backend/context_graph/`** ist eine bereits implementierte
  Workspace-Enrichment-App: Event-Bus-Subscriber-Projector-Pattern
  (`context_graph/projector.py`, registriert in `apps.py:34` auf
  `application/event_bus.py`s `DomainEventBus`), RLS-Migration nach dem
  `0026_add_llm_settings.py`-Vorbild, ein Celery-Task
  (`context_graph/tasks.py`), REST-Settings-Endpoints, MCP-Tools
  `context.query`/`context.related` (in der bestehenden
  `CrossCuttingToolGroup`, `mcp_server/tools/cross_cutting.py`). Aktuell
  genau EIN Generator (`generators/glossary.py`, reines Textmatching,
  `confidence` immer 1.0) — der im Datenmodell bereits vorgesehene
  `origin="derived-embedding"`-Wert ist nie implementiert worden. Dieses
  Feature liefert den ersten echten Embedding-Generator nach.
- **`backend/application/search_service.py`** (`SearchService`, REST
  `/api/v1/search/`) macht bereits solide Volltextsuche: Postgres
  `to_tsvector('german', ...)`/`ts_rank` plus ein lexikalischer
  ILIKE-Fallback für Titel/UID/ID (weil `tsquery` keine IDs matcht).
  Strikt Workspace-/Tenant-gebunden, `workspace_id` ist Pflichtparameter
  — keine Cross-Workspace-Suche.
- **Celery-Queue-Infrastruktur** ist etabliert: drei Queues (`default`,
  `llm`, `events`, `reqogniloom/celery.py:30-38`), Task-Pattern
  `@shared_task` + `transaction.on_commit(lambda: task.delay(...))`
  bereits mehrfach genutzt.
- **`User`-Model** (`persistence/models.py:416`) ist bereits NICHT
  `TenantScopedModel` (nullable `tenant`-FK) — architektonisch schon auf
  Mandanten-übergreifende Identität vorbereitet. Das einzige bestehende
  Präferenz-Modell, `UserWorkspacePreference`
  (`auth_tenancy/models.py:290`), ist dagegen tenant- UND
  workspace-gebunden — kein tenant-weites, workspace-übergreifendes
  User-Profil existiert bisher.

**Echte Lücken — dieses Feature schließt sie:**

- Embeddings funktionieren heute nur über OpenAI oder Mock
  (`llm_adapter/embedding_service.py:110-134`) — Anthropic/Ollama haben
  keinen Embed-Pfad, das `LlmCapabilityInterface` selbst kennt gar keine
  `embed()`-Methode (Embeddings sind komplett vom normalen
  Provider-Interface getrennt).
- Keine Cross-Workspace-Suche innerhalb eines Tenants.
- Kein tenant-weites, workspace-übergreifendes User-Gedächtnis/-Profil.
- Kein "Context Builder", der Suchergebnisse/Gedächtnis automatisch in
  einen LLM-Prompt einspeist — `prompt_resolver.py` macht nur
  Variablen-Templating (`resolve_and_render`, str.replace-basiert), keine
  dynamische Kontext-Anreicherung.
- **Frühere Produktentscheidung, Honcho nicht ins Produkt zu
  integrieren** (dokumentiert in
  `docs/superpowers/plans/Archive/2026-08-07-workspace-context-graph-scoping.md:533-601`,
  Datenschutz-Vorbehalt §11.6) — diese Spec **revidiert** diese
  Entscheidung bewusst: Honcho wird ein *optionaler*, extern
  andockbarer Memory-Backend, niemals der Default. Der
  Datenschutz-Vorbehalt bleibt dadurch gewahrt, dass die Daten im
  Self-Hosted-Default-Pfad das eigene Postgres nie verlassen.

## Architektur-Überblick

```
Interaktion (Interview-Chat, AI-Derivation, MCP-Tool-Aufruf, ...)
       │
       ▼
Domain Event (bestehender event_bus.py) ──► Memory-Consolidation-Task (Celery, neue "memory"-Queue)
       │                                          │
       │                                          ▼
       │                                    LLM extrahiert dauerhafte Fakten/Präferenzen
       │                                          │
       │                                          ▼
       │                          MemoryBackend.upsert(scope, content, embedding)
       │                             ├─ Widerspruch zu bestehendem Eintrag? → alten Eintrag
       │                             │   als superseded markieren (nicht löschen)
       │                             └─ sonst: neuer Eintrag
       │
       ▼
Nächste Interaktion: Context Builder
       │
       ├─► MemoryBackend.query(scope, query_embedding, top_k) ──► relevante Memory-Treffer
       ├─► SearchService.search(scope=workspace|tenant, hybrid=True) ──► relevante Fakten-Treffer
       │
       ▼
prompt_resolver.resolve_and_render(slot, ctx, workspace_id, memory_context=..., search_context=...)
       │
       ▼
LLM-Antwort (personalisiert, faktisch fundiert)
```

Zwei neue Provider-Abstraktionen, beide nach dem Muster der
bestehenden `get_provider()`/`register_provider()`-Factory in
`llm_adapter/providers.py:1919-1982`:

**`EmbeddingProvider`** (erweitert `embedding_service.py`, ersetzt dessen
heutige if/elif-Verzweigung durch eine echte Registry):
- `SentenceTransformersEmbeddingProvider` — **neuer Default.** Läuft
  in-process im bestehenden `backend`/`celery`-Container (Modellgewichte
  im Docker-Image gebündelt, z. B. `all-MiniLM-L6-v2`, 384 Dimensionen).
  Kein zusätzlicher Container, keine externe Abhängigkeit — das ist der
  "bringt alles mit"-Pfad.
- `OllamaEmbeddingProvider` — **optional, extern andockbar** (z. B.
  `nomic-embed-text`), via `EMBEDDING_PROVIDER=ollama` +
  `OLLAMA_BASE_URL`.
- `OpenAiEmbeddingProvider` — bereits vorhanden, bleibt als
  **optionale, potenziell qualitativ bessere** Alternative erhalten.

**`MemoryBackend`** (neu, `backend/memory/backends.py`):
- `PgvectorMemoryBackend` — **Default.** Nutzt die neuen Modelle
  `WorkspaceMemory`/`UserTenantMemory` (siehe Datenmodell) im eigenen
  Postgres, komplett self-hosted.
- `HonchoMemoryBackend` — **optional, extern andockbar** (via
  `MEMORY_BACKEND=honcho` + `HONCHO_BASE_URL`/`HONCHO_API_KEY`). Mappt
  ReqogniLooms `(tenant, workspace)` auf Honchos `workspace`-Primitive
  und `(tenant, user)` auf Honchos tenant-übergreifenden `peer` —
  ACHTUNG: das ist eine bewusste, im Fehlerfälle-Abschnitt dokumentierte
  Abweichung, weil Honchos `peer` global ist, ReqogniLooms
  "global" aber tenant-begrenzt bleiben MUSS (siehe dort).

Beide Registries werden über Django-Settings konfiguriert
(`EMBEDDING_PROVIDER`, `MEMORY_BACKEND`, Default jeweils der
self-hosted Pfad) — kein Docker-Compose-Service ist für den Default-Pfad
zwingend neu; ein `docker-compose.override.yml`-Beispiel für die
externen Optionen (Ollama-Service, Honcho-Service-Verweis) wird als Teil
der Doku mitgeliefert, aber nicht in `docker-compose.yml` selbst
verdrahtet.

## Datenmodell (Default-Backend: `PgvectorMemoryBackend`)

**Neue App: `backend/memory/`** (Layer 2, wie `context_graph`
platziert — Präzedenzfall für App-Struktur, RLS-Migration, Celery-Task,
Admin-Rebuild-Command).

**`WorkspaceMemory`** (`TenantScopedModel`):
- `workspace`: `ForeignKey[Workspace]`.
- `content`: `TextField` — die verdichtete Erkenntnis/der Fakt im
  Klartext (z. B. "Das Team bevorzugt REST über MCP für neue
  Integrationen").
- `embedding`: `VectorField(dimensions=384)` — 384 statt 1536, weil der
  Default-Provider (`sentence-transformers`/`all-MiniLM-L6-v2`) eine
  andere Dimensionalität als OpenAI hat. **Wichtig:** die Dimension ist
  provider-abhängig — siehe Fehlerfälle für den Umgang mit
  Provider-Wechsel.
- `source_event_id`: `UUIDField`, `null=True` — Referenz auf das
  auslösende Domain-Event (Nachvollziehbarkeit, analog
  `ContextEdge.evidence`).
- `superseded_by`: `ForeignKey["self"]`, `null=True` — bei Widerspruch
  zeigt der alte Eintrag auf den neuen, wird aber nicht gelöscht
  (Audit-Trail, analog Honchos Conclusions-Prinzip).
- `confidence`: `FloatField`, `default=1.0`.
- `created_at`.
- RLS-Migration nach `0026_add_llm_settings.py`-Vorbild.

**`UserTenantMemory`** (`TenantScopedModel`, **kein** `workspace`-FK —
das ist der tenant-weite, workspace-übergreifende Scope):
- `user`: `ForeignKey[User]`.
- `content`, `embedding`, `source_event_id`, `superseded_by`,
  `confidence`, `created_at` — identische Struktur zu `WorkspaceMemory`.

Beide Modelle bekommen einen GIN/HNSW-Index auf `embedding` (gleiches
Muster wie `Requirement.embedding`) und einen B-Tree-Index auf
`(workspace, created_at)` bzw. `(user, created_at)` für die
nicht-semantische Chronologie-Ansicht (z. B. "letzte Erkenntnisse zu
diesem Workspace" ohne Ähnlichkeitssuche).

## Konsolidierungs-Pipeline (async)

Neuer Celery-Task `memory.tasks.consolidate_interaction` auf einer
neuen `memory`-Queue (isoliert von `llm`, da LLM-Calls für Extraktion
selbst dort landen würden — Trennung verhindert, dass Memory-Konsolidierung
zeitkritische LLM-Aufrufe verdrängt).

- **Trigger:** Domain Events aus dem bestehenden `event_bus.py`, gefiltert
  auf "bedeutsame" Interaktionstypen — initial: Interview-`chat`-Turns
  (`InterviewSession.generate_chat_turn`), `formalize()`-Abschlüsse,
  MCP-Tool-Aufrufe mit `write`-Charakter. Kein Trigger auf jede einzelne
  Lese-Anfrage (Kostenkontrolle).
- **Extraktion:** Ein LLM-Call (über die bestehende
  `LlmCapabilityInterface`, kein neuer Provider-Typ) mit einem neuen
  `PromptTemplate`-Slot `memory.extract` (3-Level-Override-Kette wie
  gehabt) — Prompt bittet um eine strukturierte Liste `{"facts": [{"content": str, "scope": "workspace"|"user"}]}`,
  gleiches Parsing-Pattern wie `ai_derivation_service.py`s
  `_complete_json_list()`.
- **Upsert:** Für jeden extrahierten Fakt: Embedding berechnen
  (`EmbeddingProvider.embed(content)`), gegen bestehende Einträge im
  selben Scope per Cosine-Similarity auf Widerspruch/Duplikat prüfen
  (Schwellwert konfigurierbar, Default hoch genug um nur echte
  Near-Duplikate zu fangen) — bei Widerspruch: alten Eintrag
  `superseded_by` setzen, neuen anlegen; bei echtem Duplikat: nichts tun;
  sonst: neuer Eintrag.
- **Tenant-Context:** exakt das gleiche Muster wie
  `context_graph/projector.py` bereits löst (`set_request_tenant`/
  `clear_request_tenant`, `unscoped`-Escape-Hatch) — wird 1:1
  übernommen, nicht neu erfunden.

## Suche

`SearchService.search()` bekommt einen neuen `scope`-Parameter:
- `scope="workspace"` (Default, heutiges Verhalten unverändert) —
  reiner Aufruf wie bisher.
- `scope="tenant"` (neu) — durchsucht alle Workspaces des Tenants, auf
  die der anfragende User laut RBAC Zugriff hat (Filter auf
  Workspace-Mitgliedschaft VOR der eigentlichen Query, nicht danach —
  verhindert Leaken von Treffern aus Workspaces ohne Zugriff).

Zusätzlich zur bestehenden Volltext+ILIKE-Kombination: ein dritter,
**semantischer Pass** — Cosine-Similarity gegen die bereits
existierenden `Requirement.embedding`/`TraceLink.embedding`/
`IcdVersion.embedding` PLUS die neuen `WorkspaceMemory`/
`UserTenantMemory`-Embeddings. Fusion der drei Ranglisten (Volltext,
ILIKE, semantisch) über eine einfache Reciprocal-Rank-Fusion (RRF) —
kein neuer externer Service, reine Python-Logik in `SearchService`.

**Bewusst v1-out-of-scope:** ein dediziertes Cross-Encoder-Re-Ranking
(wie im ursprünglichen Brainstorming vorgeschlagen) — die RRF-Fusion
liefert bereits eine deutliche Verbesserung gegenüber der heutigen
Zwei-Pass-Lösung; ein Re-Ranker ist ein sinnvoller, aber separater
Nachfolge-Task, kein Blocker für v1.

## Prompt-Integration (Context Builder)

Neue, dünne Funktion `backend/memory/context_builder.py:build_memory_context(ctx, workspace_id, query_text)`:
1. Berechnet `query_embedding = EmbeddingProvider.embed(query_text)`.
2. Ruft `MemoryBackend.query(scope="workspace", ...)` und
   `MemoryBackend.query(scope="user", ...)` parallel ab (Top-K
   konfigurierbar, Default 5 je Scope).
3. Formatiert das Ergebnis als kompakten Text-Block.
4. Wird an Aufrufstellen wie `InterviewService.generate_chat_turn()` und
   `AiDerivationService`-Methoden übergeben, die es als
   `memory_context`-`data_kwarg` an `prompt_resolver.resolve_and_render()`
   weiterreichen — **kein neuer Templating-Mechanismus**, nur ein neuer
   Aufrufer des bestehenden.

## API / MCP

Neue `memory`-Tool-Gruppe (`backend/mcp_server/tools/memory.py`,
strukturell nach dem `AuditToolGroup`-Vorbild — eigene Klasse, eigener
Registry-Eintrag, kein Prefix-Sharing):
- `memory.query` (read-only, `_READ_ONLY_TOOL_NAMES`) — semantische
  Suche über Workspace- und/oder User-Memory.
- `memory.list` (read-only) — chronologische Ansicht ohne
  Ähnlichkeitssuche.
- `memory.forget` (write, `_WRITE_TOOL_PREFIXES`) — löscht (hart, nicht
  nur `superseded_by`) einen Memory-Eintrag. Wichtig für DSGVO/Recht auf
  Löschung, da `UserTenantMemory` personenbezogene Daten sammelt.

REST-Äquivalente unter `/api/v1/memory/` (analog zum bestehenden
`context.query`-REST-Pendant), plus ein Settings-Endpoint
`/api/v1/workspaces/{id}/memory-settings/` (on/off-Toggle pro Workspace,
analog `WorkspaceContextSettings`) und ein globaler
`/api/v1/system/memory-settings/` für Provider-Konfiguration
(System-Admin, gleiche Rollen-Prüfung wie Banner/Theme-Presets).

## Fehlerfälle

- **Embedding-Dimensions-Mismatch bei Provider-Wechsel:** Wechselt ein
  Tenant von `sentence-transformers` (384 Dim) zu `openai` (1536 Dim)
  oder umgekehrt, sind bestehende `embedding`-Spaltenwerte inkompatibel.
  Lösung: `EMBEDDING_PROVIDER` ist **pro Tenant fix bei Anlage** (nicht
  zur Laufzeit umschaltbar) für v1 — ein Migrations-Tool zum
  Neu-Embedden aller bestehenden Memory-Einträge bei Provider-Wechsel
  ist bewusst out-of-scope (siehe unten), ein Wechsel erfordert vorerst
  einen kompletten Reset der Memory-Tabellen für diesen Tenant.
- **Honcho-Backend und "tenant-global" vs. Honchos globalem `peer`:**
  Honchos `peer`-Konzept kennt keine Tenant-Grenze — ein `HonchoMemoryBackend`
  MUSS beim Erstellen eines Peers dessen ID mit dem Tenant
  namespacen (`f"{tenant_id}:{user_id}"` statt nur `user_id`), damit ein
  User in zwei verschiedenen ReqogniLoom-Tenants zwei komplett getrennte
  Honcho-Peers bekommt — sonst würde Cross-Tenant-Datenleck über den
  externen Honcho-Service selbst entstehen. Dies ist eine HARTE Vorgabe,
  kein Implementierungsdetail — muss im Implementierungsplan als
  Sicherheits-Constraint mit eigenem Test verifiziert werden.
- **Kein Embedding-Provider erreichbar** (z. B. Ollama-Service down bei
  `EMBEDDING_PROVIDER=ollama`): Konsolidierungs-Task schlägt fehl,
  retried mit Standard-Celery-Retry-Policy; Context-Builder liefert bei
  Fehler einen leeren `memory_context` statt die ganze Anfrage zu
  blockieren (Memory ist ein Enhancement, kein Hard-Requirement für eine
  LLM-Antwort).
- **Cross-Workspace-Suche liefert Treffer aus einem Workspace, dessen
  Mitgliedschaft der User seit der letzten Suche verloren hat:** der
  Mitgliedschafts-Filter läuft bei JEDER Anfrage frisch (kein Caching des
  zugänglichen Workspace-Sets über die Anfrage hinweg) — kein
  Stale-Access-Risiko.
- **Widerspruchs-Erkennung liefert False Positives** (zwei inhaltlich
  unabhängige, aber embedding-ähnliche Fakten werden fälschlich als
  Widerspruch erkannt): der Schwellwert ist konfigurierbar und defensiv
  hoch angesetzt; im Zweifel werden BEIDE Einträge behalten
  (`superseded_by` bleibt `null`) statt fälschlich einen echten Fakt zu
  verstecken — Präzision hat Vorrang vor Kompaktheit.

## Testing (Überblick, Details folgen im Implementierungsplan)

- Backend: `EmbeddingProvider`-Registry (jeder Provider liefert einen
  Vektor korrekter Dimension), `MemoryBackend`-Interface-Konformitätstests
  (beide Backends gegen dieselbe abstrakte Test-Suite, analog wie
  `llm_adapter`s Provider-Contract-Tests), Konsolidierungs-Pipeline
  (Widerspruchs-Erkennung, Superseded-Kette, Tenant-Isolation),
  Cross-Workspace-Suche (RBAC-Filter, kein Leck aus fremden Workspaces),
  Honcho-Peer-Namespacing (dedizierter Sicherheitstest, siehe
  Fehlerfälle).
- MCP: `memory.forget` Berechtigungsmatrix (wer darf wessen Memory
  löschen — mindestens: der User selbst für sein `UserTenantMemory`,
  Workspace-Admin für `WorkspaceMemory` im eigenen Workspace).
- i18n: alle neuen UI-Strings (Memory-Settings-Toggle,
  Such-Scope-Umschalter) brauchen DE/EN-Paare.

## Bewusst außerhalb dieses Scopes (v1)

- Cross-Encoder-Re-Ranking (siehe Suche-Abschnitt) — Nachfolge-Task.
- Laufzeit-Wechsel des `EMBEDDING_PROVIDER` mit automatischem
  Re-Embedding bestehender Daten — v1 erfordert einen manuellen Reset
  bei Provider-Wechsel.
- Cross-**Tenant**-Suche/-Gedächtnis — explizit nicht Teil von "global"
  (siehe Ziel/Ausgangslage), unabhängig vom gewählten Backend.
- Ein UI zum manuellen Editieren einzelner Memory-Einträge (nur Ansicht
  + Löschen für v1, kein Inline-Editor).
- Automatisches Zusammenfassen/Komprimieren sehr langer Memory-Historien
  (Honchos "Representation"-Konzept geht hier weiter als der
  Pgvector-Default v1 — wer das volle Honcho-Verhalten will, nutzt den
  optionalen Honcho-Backend).
