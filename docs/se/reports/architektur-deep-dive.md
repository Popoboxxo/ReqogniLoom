# ReqFlow — Architektur Deep-Dive & SE-Treue

Dieses Dokument liefert eine extrem detaillierte Analyse der 13 ReqFlow-Subsysteme (L2) auf Basis ihrer tiefsten L3-Komponenten, Datenflüsse und technischen Flaschenhälse. Zudem bewertet es die methodische Ausrichtung des Systems.

---

## 1. Statement zur Treue zum Systems Engineering (SE Fidelity)

ReqFlow beweist ein überraschend tiefes Verständnis für echtes Systems Engineering. Es verfällt nicht dem Fehler, Jira mit ein paar neuen Labels zu überziehen, sondern implementiert fundamentale SE-Konzepte tief in der Architektur.

**Die größten SE-Stärken:**
1. **Configurable Rigor (Extended Preset):** Die Möglichkeit, das System in einen strikten SE-Modus zu schalten, aktiviert Features, die für Safety-Critical-Entwicklung unverzichtbar sind: strikte Approval-Gates (Vier-Augen-Prinzip), zwingende Begründungen (`change_reason`) für Änderungen und lückenlose Auditierbarkeit.
2. **Generisches Artefakt-Modell:** Anstatt nur "Story" oder "Epic" zu kennen, nutzt das Datenmodell eine beliebige Artefakt-Hierarchie. Dies erlaubt die klassische Zerlegung nach ISO/IEC 15288 (System → Subsystem → Komponente) und die saubere Trennung zwischen Requirements, Architektur-Elementen und Testfällen.
3. **Multi-Level-Baselines:** Dass Snapshots nicht nur auf Projekt-, sondern auch auf Dokument- und globaler Release-Ebene eingefroren werden können, ist ein Feature, das sonst nur Enterprise-ALM-Systemen vorbehalten ist.
4. **Vollwertige Traceability Engine:** Die Unterstützung komplexer, gerichteter Graphen mit spezifischen Link-Typen (`derives-from`, `satisfies`, `verifies`) ermöglicht echte Impact-Analysen (Blast Radius) über das gesamte V-Modell hinweg.

**Wo das System (noch) Kompromisse macht:**
Für v1 ist das System laut Konzept "audit-ready", aber nicht zertifizierbar. Es fehlen vordefinierte formale Verification-Matrizen, elektronische Signaturen für Phasenübergänge und komplexe Approval-Matrizen (z.B. delegierte Approvals). Der Plan, in v2 die Grundnorm **IEC 61508** anzuvisieren, ist jedoch strategisch exzellent gewählt, da sie das Fundament für Automotive (ISO 26262) und Industrieautomation bildet.

**Fazit:** ReqFlow ist methodisch extrem treu zum Systems Engineering. Es ist ein modernes, pragmatisches SE-Werkzeug, das die methodische Strenge von Enterprise-Tools (wie DOORS oder Polarion) mit der Agilität moderner Softwareentwicklung und KI-Integration vereint.

---

## 2. Deep-Dive: Die 13 Subsysteme im Detail

Die folgende Analyse zerlegt jedes der 13 L2-Subsysteme in seine L3-Komponenten und deckt kritische technische Risiken auf.

### 2.1 ApplicationServiceSystem
* **L3-Komponenten:** ArtifactService, RequirementService, ArchitectureService, TestService, TraceLinkService, BaselineFacade, WorkflowFacade, ExportService, ImportService, SearchService, WebhookDispatcher, PresetPolicyService.
* **Datenfluss:** Dies ist die zentrale Domain-Fassade ("God-Facade"). Sie orchestriert alle Anfragen der APIs (REST/MCP) und ruft die tieferen Engines (Workflow, Traceability) synchron auf.
* **Risiken & Bottlenecks:** Synchrone Aufrufe an externe Module (wie AuditLog oder Persistenz) blockieren den Main Thread. Webhooks erfordern robuste Retry-Logiken, um Memory Leaks durch Warteschlangen-Bloat zu vermeiden.

### 2.2 AuditLogSystem
* **L3-Komponenten:** AuditLogWriter, AuditLogQuery.
* **Datenfluss:** Unidirektional. Schreibvorgänge laufen synchron innerhalb der Haupt-Geschäftstransaktion.
* **Risiken & Bottlenecks:** Da Schreibvorgänge synchron stattfinden, verlangsamt jede Datenbank-Latenz den gesamten Request. Zudem wächst die "Append-only"-Tabelle endlos. Ohne Archivierungsstrategie wird die Query-Performance (z.B. für Metriken) massiv einbrechen.

### 2.3 AuthAndTenancySystem
* **L3-Komponenten:** AuthenticationService, AuthorizationService, TenantContextService.
* **Datenfluss:** Validiert API-Keys/Tokens, extrahiert den Mandanten (Tenant), prüft RBAC-Richtlinien und übergibt den Kontext (oft Thread-local) an den Custom Django Manager.
* **Risiken & Bottlenecks:** Stetiges Hashing und Validieren der API-Keys bei jedem MCP-Tool-Aufruf kann zu CPU-Spikes führen. Der größte Risikofaktor ist der Verlust des "Thread-Local"-Mandantenkontexts bei asynchronen Aufgaben, was zu mandantenübergreifenden Datenlecks führen könnte.

### 2.4 BaselineServiceSystem
* **L3-Komponenten:** SnapshotBuilder, DiffEngine, BaselineStore.
* **Datenfluss:** Löst den gewünschten Scope rekursiv über die Traceability Engine auf, baut einen massiven JSON-Snapshot und speichert diesen ab.
* **Risiken & Bottlenecks:** Das Generieren und Vergleichen von gigantischen JSON-Snapshots (bei Tausenden Elementen) komplett im Arbeitsspeicher kann extrem schnell zu CPU-Blockaden und Out-of-Memory (OOM) Abstürzen führen.

### 2.5 LlmAdapterSystem
* **L3-Komponenten:** CapabilityInterface, ProviderRegistry, CapabilityRouter, LlmAuditLogger.
* **Datenfluss:** Leitet Anfragen an konfigurierte Provider (Anthropic, OpenAI) via HTTPS weiter und loggt den Token-Verbrauch synchron.
* **Risiken & Bottlenecks:** Hochgradig anfällig für Netzwerk-Latenzen und Rate-Limits der Drittanbieter. Die synchrone Kopplung an das Audit-Log potenziert die Verzögerung. Positiv: Eingebautes *Graceful Degradation* schützt das System bei Ausfällen.

### 2.6 McpServerSystem
* **L3-Komponenten:** ProtocolHandler, ToolRegistry, RequirementsToolGroup, ArchitectureToolGroup, TestToolGroup, CrossCuttingToolGroup.
* **Datenfluss:** Nimmt MCP-Requests via JSON-RPC an und führt sie als native, In-Process-Python-Aufrufe direkt gegen den ApplicationService aus.
* **Risiken & Bottlenecks:** Die tiefe Kopplung an den monolithischen Backend-Prozess bedeutet, dass jegliche blockierende MCP-Operation direkt den Django-Worker einfriert. Skalierung des MCP-Servers erzwingt die Skalierung des gesamten Monolithen.

### 2.7 PersistenceLayerSystem
* **L3-Komponenten:** EntitySchemaManager, TenantIsolationManager, TransactionCoordinator, SchemaMigrationEngine, PerformanceOptimizationLayer.
* **Datenfluss:** Alle Datenbankanfragen laufen zwingend durch den `TenantIsolationManager` zur Sicherung der `tenant_id` und den `TransactionCoordinator` für ACID-Konformität.
* **Risiken & Bottlenecks:** Die PostgreSQL-Datenbank ist der monolithische Flaschenhals. Massive parallele Transaktionen (z.B. wenn KI-Agenten per Bulk-Befehl 100 Requirements zerlegen) können den Connection Pool der Datenbank rasch ausschöpfen.

### 2.8 PresetConfigEngineSystem
* **L3-Komponenten:** PresetRegistry, TerminologyProfileService, FeatureGateService.
* **Datenfluss:** Liefert zur Laufzeit Berechtigungs- und Sichtbarkeitsregeln für das gesamte System.
* **Risiken & Bottlenecks:** Als extrem stark gelesener Querschnitts-Service ist dieses System vollständig auf In-Memory-Caching angewiesen (<10ms Budget). Ein Cache-Miss unter Last würde die Datenbank sofort überlasten.

### 2.9 ReactFrontendSystem
* **L3-Komponenten:** NavigationShell, DashboardViews, RequirementEditors, ArchitectureEditors, TraceabilityViews, I18nService.
* **Datenfluss:** Interaktionen rufen die REST-API auf, während der I18nService dynamisch Bezeichnungen austauscht (Dev-Modus vs. SE-Modus).
* **Risiken & Bottlenecks:** Das Rendern von tiefen und breiten Traceability-Graphen im Browser kann das DOM massiv überlasten. Die dynamischen Terminologie-Updates können ungewollt aggressive Re-Renders der gesamten React-App auslösen.

### 2.10 RestApiAdapterSystem
* **L3-Komponenten:** HttpEndpointController, DataSerializer, AuthEnforcer, PresetGuard, OpenApiGenerator.
* **Datenfluss:** Pures Übersetzungs-Layer zwischen HTTP, Serializer (Validierung) und ApplicationService.
* **Risiken & Bottlenecks:** Der massive Einsatz von DRF Serializern auf verschachtelten Ressourcen (wie Requirements mit TraceLinks) führt sehr schnell zum berüchtigten "N+1 Query"-Problem, was die API drastisch verlangsamt.

### 2.11 SeMetricsSystem
* **L3-Komponenten:** MetricsQueryController, MetricsAggregator, VolatilityCalculator, CoverageCalculator, WorkflowGapDetector, RiskClassifier, ThresholdEvaluator, MetricsCacheManager.
* **Datenfluss:** Aggregiert parallel Daten aus 4 verschiedenen Systemen, berechnet Schwellenwerte und legt das Ergebnis im Cache ab.
* **Risiken & Bottlenecks:** Das Berechnen der Metriken (insb. Anforderungs-Volatilität über tausende Audit-Log-Einträge) frisst CPU ohne Ende. Ein paralleler Ansturm von Usern bei einem Cache-Miss führt zu einem "Thundering Herd"-Effekt, der die Datenbank lahmlegt.

### 2.12 TraceabilityEngineSystem
* **L3-Komponenten:** TraceLinkManager, QueryEngine, CoverageCalculator.
* **Datenfluss:** Trennt strikt zwischen Schreib- (`TraceLinkManager`) und Lese-Operationen (`QueryEngine`).
* **Risiken & Bottlenecks:** Um Zyklen (Endlosschleifen in der Traceability) zu verhindern, muss bei jedem Bulk-Insert der gesamte Baum validiert werden, was sehr rechenintensiv ist. Massive rekursive CTEs (Common Table Expressions) für tiefe Graph-Queries belasten die PostgreSQL-CPU.

### 2.13 WorkflowEngineSystem
* **L3-Komponenten:** WorkflowDefinitionStore, TransitionValidator, StateLifecycleManager.
* **Datenfluss:** Validiert Statusübergänge dynamisch gegen vordefinierte Regeln und schreibt die Änderungshistorie (Append-only).
* **Risiken & Bottlenecks:** Die Transition-Validierung hat ein Budget von maximal 10ms. Bei gleichzeitigen Statusänderungen am selben Artefakt kommt es durch Optimistic Locking zu endlosen Retry-Schleifen.

---

## 3. Lösungsstrategien & Architektur-Korrekturen

Um die oben identifizierten Risiken in den Subsystemen zu entschärfen, müssen vor der Implementierungsphase folgende Anpassungen an der Architektur vorgenommen werden:

1. **Interne Event-Bus Architektur (Message Broker):**
   Um den `ApplicationService` als blockierende "Gott-Fassade" zu entlasten, sollte ein Event-Bus (z.B. RabbitMQ oder Redis Pub/Sub) eingeführt werden. Modulaufrufe an `AuditLog` oder `SeMetrics` erfolgen dann asynchron über Events (z.B. `RequirementUpdated`), anstatt den HTTP/MCP-Request zu blockieren.

2. **Delta-Snapshots statt JSON-Blobs:**
   Das OOM-Risiko im `BaselineService` wird eliminiert, indem statt kompletter JSON-Snapshots nur noch Delta-Referenzen (Diffs zur vorherigen Baseline) oder Event-Sourcing-Marker aus dem AuditLog gespeichert werden.

3. **Archivierungsstrategie für das AuditLog:**
   Die Append-Only-Tabelle des `AuditLogSystem` benötigt eine automatisierte Cold-Storage-Archivierung (z.B. Partitionierung in PostgreSQL nach Monaten), um die Query-Performance dauerhaft zu sichern.

4. **Background-Worker für Metriken & LLM:**
   Das `SeMetricsSystem` und das `LlmAdapterSystem` müssen schwere Berechnungen und externe HTTPS-Calls in Hintergrund-Worker (z.B. Celery) auslagern. Das verhindert Timeouts und den "Thundering Herd"-Effekt bei Cache-Misses.

5. **Behebung des N+1 Query Problems:**
   Im `RestApiAdapterSystem` muss auf Ebene des Django ORM der strikte Einsatz von `select_related` und `prefetch_related` für verschachtelte Ressourcen (wie Requirements + TraceLinks) erzwungen werden.

6. **Asynchrone MCP-Worker:**
   Da MCP-Agenten-Operationen teils Minuten dauern können (z.B. Massenzerlegung), darf der `McpServerSystem` nicht direkt im Main-Thread an den ApplicationService gekoppelt sein. Langlebige Tool-Aufrufe müssen asynchron verarbeitet werden.
