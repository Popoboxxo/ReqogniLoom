# ReqFlow — Detaillierte Handlungsempfehlungen

Dieses Dokument enthält die detaillierten, ausgearbeiteten Handlungsempfehlungen (sowohl auf technischer als auch auf methodischer Ebene), die sich aus der Architekturanalyse und dem Deep-Dive der 13 Subsysteme ergeben. 

Es dient als reine Dokumentation und detaillierte Spezifikation für zukünftige Umsetzungsschritte.

---

## 1. Technische Handlungsempfehlungen (Architektur & Skalierbarkeit)

### 1.1 Ablösung des Custom Managers durch PostgreSQL Row-Level Security (RLS)
* **Problemstellung:** Die aktuelle Architektur verlässt sich im `PersistenceLayerSystem` auf einen Custom Django Manager (`TenantIsolationManager`), um Daten mandantenspezifisch (über `tenant_id`) zu filtern. Wird dieser Manager im Code umgangen (z. B. durch `.objects.raw()` oder Drittanbieter-Module), kommt es sofort zu Mandanten-Datenlecks (Cross-Tenant Leakage).
* **Detaillierte Lösung:** 
  1. Aktivierung von Row-Level Security (RLS) direkt in PostgreSQL für alle Tabellen.
  2. Implementierung einer Django-Middleware, die bei jedem HTTP/MCP-Request die `tenant_id` als Session-Variable in der Datenbank setzt (z. B. via `SET LOCAL app.current_tenant = 'UUID'`).
  3. Erstellung von PostgreSQL-Policies (`CREATE POLICY`), die strikt `WHERE tenant_id = current_setting('app.current_tenant')` erzwingen.
* **Ergebnis:** Isolierung ist auf Datenbankebene garantiert und kann von der Applikationsschicht nicht mehr versehentlich umgangen werden.

### 1.2 Entkopplung der "Gott-Fassade" durch eine interne Event-Bus Architektur
* **Problemstellung:** Der `ApplicationService` ruft derzeit nach jeder Mutation synchron das `AuditLogSystem`, das `TraceabilityEngineSystem` und eventuell das `WebhookDispatcher` auf. Dies verlängert die Antwortzeiten der API massiv und erzeugt starre Kopplungen.
* **Detaillierte Lösung:**
  1. Einführung eines internen Message Brokers (z.B. Redis Pub/Sub oder RabbitMQ) oder im einfachsten Fall robuster Django Signals gekoppelt mit asynchronen Workern.
  2. Der `ApplicationService` feuert nur noch ein Domain-Event ab (z.B. `RequirementUpdatedEvent(req_id, user_id, changes)`).
  3. `AuditLogWriter`, `SeMetrics` und `WebhookDispatcher` abonnieren diese Events und verarbeiten die Daten asynchron außerhalb des Main-Threads.

### 1.3 Asynchrone Background-Worker für kritische L2-Systeme
* **Problemstellung:** Mehrere Subsysteme (u.a. `LlmAdapterSystem`, `SeMetricsSystem`, `McpServerSystem`) blockieren bei Langläufer-Aufgaben (Massenzerlegung von Anforderungen, Berechnung von Volatilität) den WSGI/ASGI-Worker von Django.
* **Detaillierte Lösung:**
  1. Integration von **Celery** als asynchronen Task-Queue-Manager.
  2. MCP-Tools, die LLMs aufrufen (wie `requirement.decompose`), müssen einen Job in die Queue legen und einen `task_id` an den Agenten zurückgeben. Der Agent kann den Status dann über ein neues Tool (`task.status`) abfragen.
  3. Metrik-Aggregatoren müssen nachts oder in festen Intervallen per Celery-Beat berechnet und in den Cache gelegt werden, statt sie "on-the-fly" bei einem Cache-Miss zu berechnen (Verhinderung des "Thundering Herd" Effekts).

### 1.4 Umbau des Baseline-Speichers auf Deltas / Event-Sourcing
* **Problemstellung:** Der `BaselineServiceSystem` zieht einen kompletten JSON-Snapshot eines Workspaces. Bei 10.000 Items inklusive TraceLinks führt dies bei jeder neuen Baseline zu massivem Datenbankwachstum und RAM-Überlastung (OOM) während der Serialisierung.
* **Detaillierte Lösung:**
  1. **Delta-Storage:** Speichere nur die IDs und die exakte Revisions-Nummer (`version`) jedes Elements zum Zeitpunkt der Baseline, nicht den gesamten Payload.
  2. Um den Zustand einer Anforderung zum Baseline-Zeitpunkt zu rekonstruieren, wird die Versionshistorie (AuditLog oder eine dezidierte `RequirementVersion` Tabelle) herangezogen.

### 1.5 DRF N+1 Query Optimierung im API-Adapter
* **Problemstellung:** Der `RestApiAdapterSystem` leidet bei der Auslieferung verschachtelter Objekte (z. B. Requirement inkl. aller TraceLinks und Testfälle) unter dem N+1-Query-Problem.
* **Detaillierte Lösung:**
  1. Überschreiben der DRF-Querysets in den Views durch explizite `select_related` (für ForeignKeys) und `prefetch_related` (für ManyToMany / Reverse ForeignKeys).
  2. Serverseitiges Caching häufig gelesener, tief verschachtelter Baumstrukturen.

---

## 2. Methodische Handlungsempfehlungen (Systems Engineering Deep Dive)

Diese Empfehlungen heben das System auf das nächste Level, um die geplante Compliance-Norm (IEC 61508 in v2) zu erreichen.

### 2.1 AuditLog-Archivierungsstrategie (Cold Storage)
* **Methodisches Ziel:** Compliance-Normen verlangen lückenlose Nachverfolgbarkeit, verbieten aber oft aus Performance- oder Datenschutzgründen eine Endlos-Speicherung im heißen System.
* **Detaillierte Spezifikation:**
  1. Das `AuditLogSystem` benötigt eine Table-Partitioning Strategie auf PostgreSQL-Ebene (z.B. Partitionierung pro Monat).
  2. Implementierung eines Data-Lifecycle-Jobs, der Logs, die älter als 2 Jahre sind, in einen "Cold Storage" (z.B. AWS S3 Glacier als gepackte CSV/JSON-Archive) exportiert und anschließend aus der Primärdatenbank löscht.

### 2.2 Elektronische Signaturen für Phasenübergänge
* **Methodisches Ziel:** In der funktionalen Sicherheit (Safety-Critical) reicht es nicht, einfach einen Status auf "Approved" zu setzen. Es bedarf einer qualifizierten elektronischen Signatur (QES) oder einer 2-Faktor-Freigabe, um den Übergang abzusichern.
* **Detaillierte Spezifikation:**
  1. Die `WorkflowEngine` wird um das Konzept `SignatureGate` erweitert.
  2. Wenn eine Transition (z. B. `draft` → `approved`) ein SignatureGate besitzt, muss der API-Call zwingend das aktuelle User-Passwort oder einen 2FA-Token (TOTP) enthalten. 
  3. Der AuditLog-Eintrag für diese Transition speichert das kryptografische Prüfsiegel, welches den Statuswechsel rechtssicher und fälschungssicher macht.

### 2.3 Verification Cross Reference Matrix (VCRM)
* **Methodisches Ziel:** SE-Reviewer benötigen eine Matrix, die beweist, dass jedes System-Requirement durch Komponenten umgesetzt und durch Tests verifiziert wurde.
* **Detaillierte Spezifikation:**
  1. Die `TraceabilityEngine` wird um einen spezialisierten Report-Generator erweitert.
  2. Die Ausgabe ist eine flache Matrix (VCRM), die zeilenweise die Hierarchie auflöst: `Requirement ID -> Component ID -> Test Case ID -> Test Result (Passed/Failed)`.
  3. Diese Matrix muss exportierbar (PDF/Excel) und an eine bestimmte Baseline knüpfbar sein.

### 2.4 Zyklen-Verhinderung in der Traceability (Azyklische Graphen)
* **Methodisches Ziel:** Eine fehlerfreie Auswirkungsanalyse (Impact Analysis) setzt voraus, dass Anforderungen nicht in Endlosschleifen voneinander abhängen. 
* **Detaillierte Spezifikation:**
  1. Der `TraceLinkManager` muss vor dem Speichern eines neuen `TraceLink` den entstehenden Graphen auf Zyklen (Cycles) prüfen.
  2. Handelt es sich um Massenimporte (Bulk), sollte die Validierung via Tarjan-Algorithmus am Ende der DB-Transaktion erfolgen, um Performance-Einbrüche zu vermeiden. Zyklen führen zum Rollback der gesamten Transaktion mit einem detaillierten Fehlerbericht für den User oder KI-Agenten.
