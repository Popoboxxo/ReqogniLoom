# ADR-002: Event-Bus für interne Systemereignisse

**Status:** PROPOSED
**Datum:** 2026-06-28
**Entscheider:** Architekt + Tech-Lead
**Betroffene REQs:** REQ-L1-043, REQ-L2-TE-016, REQ-L2-VS-002
**Übergeordnete Needs:** REQ-L0-030 (SN-30 — Suspect-Link), REQ-L0-026 (SN-26 — Semantische Suche)

---

## Kontext

REQ-L2-TE-016 (Suspect-Link-Propagation) und REQ-L2-VS-002 (Embedding-Pipeline) benötigen
beide einen Mechanismus, über den Artefakt-Änderungsereignisse (z. B. equirement.updated)
asynchron an Subscriber weitergegeben werden können. Die aktuelle Architektur hat keinen
definierten Event-Bus.

---

## Entscheidungsalternativen

### Option A: Django Signals (Synchron, In-Process)

**Beschreibung:** Django Signals (post_save, post_delete) lösen synchron Receiver-Funktionen
aus. Receiver implementieren Suspect-Propagierung und Embedding-Updates direkt.

**Vorteile:**
- Zero-Dependency (Django built-in)
- Einfach zu testen (Mock-Signals)
- Sofort verfügbar, kein Infrastruktur-Aufwand

**Nachteile:**
- Synchrone Ausführung: Suspect-Propagierung verlangsamt API-Response
- Keine Retry-Logik bei Fehler (Signal-Fehler wird ignoriert oder crasht Request)
- Nicht skalierbar: Bei hohem Schreibvolumen blockiert Signal-Ausführung
- Kein Monitoring / Observability

**Geeignet für:** Kleine Systeme, geringe Ereignisfrequenz

---

### Option B: Celery + Redis (Asynchron, Task-Queue) — EMPFOHLEN

**Beschreibung:** Bei Artefakt-Änderungen wird ein Celery-Task asynchron in eine Redis-Queue
eingereiht. Celery-Worker führen Suspect-Propagierung und Embedding-Updates in separaten
Prozessen aus.

**Vorteile:**
- API-Response-Zeit unberührt (Fire-and-Forget)
- Retry-Logik konfigurierbar (max_retries, exponential backoff)
- Monitoring via Celery Flower oder Prometheus
- Gut bekanntes Django-Ecosystem-Pattern
- Redis ohnehin für Caching geplant → kein zusätzlicher Infrastruktur-Service nötig

**Nachteile:**
- Zusätzliche Abhängigkeit (celery, redis)
- Asynchrone Natur: Suspect-Status sichtbar erst nach Worker-Ausführung (Latenz 1-5 s)
- Lokale Entwicklung benötigt Redis-Instanz (docker-compose-Erweiterung)

**Risiko:** NIEDRIG — Bewährtes Django-Ecosystem-Pattern

---

### Option C: Redis Pub/Sub (Asynchron, Publish-Subscribe)

**Beschreibung:** Artefakt-Änderungen publizieren Events in Redis-Channels. Subscriber
(Suspect-Engine, Embedding-Pipeline) konsumieren Events aus dedizierten Channels.

**Vorteile:**
- Vollständige Entkopplung von Publisher und Subscriber
- Mehrere Subscriber möglich (Suspect + Embedding gleichzeitig)
- Geeignet für zukünftige WebSocket-Notifications

**Nachteile:**
- At-most-once Delivery: Bei Worker-Ausfall gehen Events verloren (kein Persistence)
- Kein Retry-Mechanismus out-of-the-box
- Komplexere Implementierung als Celery

**Risiko:** MITTEL — Message-Loss bei Ausfall ohne zusätzliche Absicherung

---

## Entscheidung

**OPTION B (Celery + Redis) wird empfohlen** als Event-Bus-Implementierung.

**Begründung:**
1. Bereits geplanter Redis-Einsatz (Caching) → kein neuer Service
2. At-least-once Delivery mit Retry (Suspect-Propagierung darf nicht verloren gehen)
3. Django-native Integration via django-celery-results
4. Latenz-Anforderung (< 2 s für AT-Test-016 AC1) mit Celery erfüllbar bei normalem Load

**Konsequenzen:**
- docker-compose.yml erhält Redis-Service und Celery-Worker-Service
- equirements.txt erhält celery, edis, django-celery-results
- Neue Celery-App in ackend/core/celery.py
- Tasks: propagate_suspect_links(requirement_id), update_embedding(artefact_id)
- Django Signals als Trigger: post_save → enqueue Celery-Task
- Monitoring: Celery Flower als optionaler Service in docker-compose.dev.yml

**Review-Datum:** Vor Implementierungsbeginn

---

*Erstellt: 2026-06-28 | Autor: se-architect | Für: REQ-L1-043, REQ-L2-TE-016, REQ-L2-VS-002*
