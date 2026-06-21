# ReqFlow — Architektur-Analyse & Review

Dieses Dokument bietet eine detaillierte Analyse der ReqFlow-Architektur basierend auf der Dokumentation im Verzeichnis `docs/se`. Es bewertet die Grundstruktur und identifiziert potenzielle Verbesserungen sowie architektonische Risiken und Fehler.

## 1. Grundstruktur

ReqFlow ist als modularer Monolith auf Basis von Django (Python) und React konzipiert und wird über Docker Compose bereitgestellt. Die Architektur definiert 16 logische Subsysteme (L2) innerhalb einer einzigen Systemgrenze.

**Wesentliche Stärken:**
* **Dual-Interface-Architektur (REST & MCP):** Sowohl die REST-API als auch der MCP-Server kommunizieren direkt mit dem `ApplicationService` (Domain Service Fassade). Dies ist eine hervorragende Designentscheidung für ein "AI-natives" Tool, da so sichergestellt ist, dass KI-Agenten und menschliche Nutzer (über die UI) über exakt dieselben Funktionen und Geschäftslogik-Regeln verfügen.
* **Modularer Monolith (In-Process Python):** Die Entscheidung, Zuständigkeiten in logische Subsysteme (z.B. `WorkflowEngine`, `BaselineService`, `TraceabilityEngine`) aufzuteilen, diese aber in einem einzigen Prozess (Django Apps) zu belassen, ist ideal für Version 1. Es vermeidet den operativen Mehraufwand von Microservices und behält dennoch saubere Grenzen bei.
* **Konfigurierbare Strenge (`PresetConfigEngine`):** Die Nutzung einer zentralen Engine, um die Prozessstrenge des Systems über alle Module hinweg zu diktieren, verhindert die Duplizierung von Logik für unterschiedliche Nutzergruppen (z.B. Agile Teams vs. klassische Systems Engineering Teams).
* **LLM-Abstraktion (`LlmAdapter`):** Die Kapselung der LLM-Anbieter-Spezifika hinter einem Adapter verhindert einen Vendor-Lock-in und ermöglicht eine saubere Fehlerbehandlung (Graceful Degradation), falls kein LLM verfügbar ist.

## 2. Identifizierte Risiken und Fehler

Obwohl die Architektur gut strukturiert ist, gibt es einige wesentliche Risiken und potenzielle Designfehler:

### 2.1. Sicherheitsrisiko bei der Mandanten-Isolierung (Tenant Isolation) (ADR-03)
* **Risiko:** Die Architektur verlässt sich auf einen "Custom Django Manager", um die Isolierung auf Zeilenebene (Row-Level) für Mandanten (Tenants) durchzusetzen. Wenn ein Entwickler versehentlich eine direkte Datenbankabfrage ausführt oder den Manager umgeht (z.B. durch Nutzung von `.objects` anstelle des mandantenspezifischen `.objects`), kann dies zu massiven Datenlecks zwischen Mandanten führen.
* **Fehler/Schwachstelle:** Sich bei einem System, das hochsensible Anforderungs- und Architekturdaten speichert, rein auf Applikations-Ebenen-Filter zu verlassen, ist ein großes Sicherheitsrisiko.

### 2.2. Synchrone Flaschenhälse (Bottlenecks)
* **Risiko:** Die Dokumentation impliziert, dass die meisten Operationen synchron ("In-Process Python" Aufrufe) ablaufen. Das Erstellen einer projektweiten Baseline (`BaselineService`) oder die Berechnung komplexer Traceability-Matrizen (`SeMetrics`, `TraceabilityEngine`) kann bei vielen Daten mehrere Sekunden dauern. Wenn dies synchron im HTTP/MCP-Request-Zyklus geschieht, führt dies unweigerlich zu Timeouts.
* **Fehler/Schwachstelle:** Es fehlt die explizite Erwähnung einer asynchronen Task-Queue (z.B. Celery oder Django-Q) für ressourcenintensive Operationen.

### 2.3. Über-Abstraktion der Ausfallsicherheit (`ResilienceOrchestrator` / ARCH-L1-016)
* **Risiko:** Die Auslagerung von Retries, Circuit Breakern und Timeouts in ein dediziertes, eigenständiges Subsystem (`ResilienceOrchestrator`) ist sehr wahrscheinlich Over-Engineering (zu starke Abstraktion).
* **Fehler/Schwachstelle:** Resilienz ist typischerweise ein Querschnittsanliegen (Cross-Cutting Concern), das besser über Decorators (z.B. mit der Python-Bibliothek `tenacity`) oder ein API-Gateway gelöst wird, anstatt als eigenes Geschäfts-Subsystem. Wenn der `ApplicationService` alles durch ein separates Resilienz-System leiten muss, entsteht unnötige Komplexität.

### 2.4. Strategie zur Baseline-Speicherung
* **Risiko:** Der `BaselineService` persistiert Snapshots als "JSON-Snapshot" in der Datenbank.
* **Fehler/Schwachstelle:** Wenn ein Projekt 10.000 Items und unzählige TraceLinks hat, kann ein vollständiger JSON-Snapshot des gesamten Workspaces enorm groß werden (zig oder hunderte Megabytes pro Snapshot). Wenn dies jedes Mal in einer einzigen PostgreSQL-Zeile (JSONB) gespeichert wird, bläht das die Datenbank auf und verschlechtert die Performance rapide.

## 3. Empfohlene Verbesserungen

Um die Architektur zu stärken, empfehle ich die folgenden Anpassungen vor Beginn der Implementierungsphase:

### Verbesserung 1: PostgreSQL Row-Level Security (RLS) nutzen
Anstatt sich ausschließlich auf den Django Custom Manager zu verlassen, sollte **PostgreSQL Row-Level Security (RLS)** implementiert werden. Indem der Tenant-Kontext direkt auf Datenbank-Session-Ebene gesetzt wird, ist garantiert, dass keine Abfrage fremde Mandantendaten auslesen kann – selbst dann nicht, wenn der ORM-Manager umgangen wird.

### Verbesserung 2: Einführung einer asynchronen Worker-Ebene (Async-Layer)
Füge der Architektur explizit ein asynchrones Worker-Subsystem (z.B. Celery + Redis oder RabbitMQ) hinzu. Intensive Aufgaben müssen zwingend ausgelagert werden:
* **LLM-Aufrufe:** Die Antworten der LLM-APIs können 10-30 Sekunden dauern.
* **Baseline-Snapshots:** Das Berechnen und Speichern großer Projekt-Baselines.
* **Metrik-Berechnung:** `SeMetrics` sollte schwere Aggregationen asynchron im Hintergrund berechnen und cachen.

### Verbesserung 3: Ereignisgesteuerte interne Kommunikation (Event-Driven)
Anstatt dass der `ApplicationService` alles synchron orchestriert (Aufruf von `WorkflowEngine`, dann `AuditLog`, dann `TraceabilityEngine`), sollte ein interner **Event-Bus** (z.B. Django Signals oder ein leichtgewichtiger Event-Dispatcher) eingeführt werden.
* *Beispiel:* Wenn der `ApplicationService` ein Item aktualisiert, feuert er ein `ItemUpdated`-Event. Das `AuditLog` und `SeMetrics` lauschen auf dieses Event und verarbeiten es unabhängig. Das entkoppelt die Systeme und verbessert die Antwortzeiten drastisch.

### Verbesserung 4: Speicherung von Snapshot-Deltas
Für den `BaselineService` gilt: Anstatt bei jeder Baseline komplette JSON-Snapshots zu speichern, sollten nur die **Deltas (Änderungen/Diffs)** gegenüber der vorherigen Baseline gespeichert werden. Alternativ bietet sich ein Event-Sourcing-Ansatz an, bei dem die Baseline lediglich eine Markierung (Marker) auf dem Zeitstrahl des `AuditLog` darstellt. Dies reduziert den Speicherbedarf erheblich.

### Verbesserung 5: Resilienz vereinfachen
Entferne den `ResilienceOrchestrator` als eigenständiges L2-System. Implementiere Resilienz-Muster (Retries, Circuit Breaker) stattdessen direkt als Bibliotheks-Utilities oder Decorators innerhalb der Adapter (`LlmAdapter`, `WebhookDispatcher`), die die tatsächlichen ausgehenden HTTPS-Anfragen durchführen. So bleiben die Adapter in sich geschlossen und verständlich.
