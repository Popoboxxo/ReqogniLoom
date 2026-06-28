# ADR-001: Sandbox-Mechanismus für Artefakt-Branching & Merging

**Status:** PROPOSED
**Datum:** 2026-06-28
**Entscheider:** Architekt + Tech-Lead
**Betroffene REQs:** REQ-L1-045, REQ-L2-BL-010, REQ-L2-RF-017
**Übergeordneter Need:** REQ-L0-033 (SN-33 — Isolierte Requirement-Sandboxes)

---

## Kontext

REQ-L1-045 fordert isolierte, parallele Arbeitszweige (Sandboxes) für Anforderungsartefakte
mit kontrolliertem Merge. Die Anforderung ist lösungsneutral formuliert. Es wurden
drei konkurrierende Mechanismen identifiziert, die im Folgenden verglichen werden.

---

## Entscheidungsalternativen

### Option A: Git-interner Branching-Mechanismus (Datenbankzeilen als Git-Objekte)

**Beschreibung:** Jede Artefakt-Änderung wird als unveränderliches Git-Objekt persistiert.
Sandbox-Zweige sind Git-Branches auf einer dedizierten Git-Repository-Schicht (z. B. libgit2).

**Vorteile:**
- Bewährte Merge-Semantik (3-Way-Merge, Konfliktmarkierung)
- Vollständige Versionshistorie automatisch
- Offline-Fähigkeit, Branching kostenlos

**Nachteile:**
- Erfordert Git-Expertise im Backend-Team (Python + libgit2)
- Serialisierung von Django-Objekten zu Git-Blobs: Konversions-Overhead
- Schwer in PostgreSQL-Transaktionen integrierbar
- Testaufwand hoch (Merge-Konflikte, Octopus-Merges)

**Risiko:** MITTEL — Komplexe Integration, aber bewährtes Konzept

---

### Option B: Event-Sourcing-basierte Parallelzweige

**Beschreibung:** Das Datenmodell speichert ausschließlich Events (Commands/Events).
Ein Sandbox-Zweig ist ein isolierter Event-Stream. Der Merge repliziert Events aus dem
Sandbox-Stream in den Hauptstream mit Konfliktprüfung (Lamport-Timestamps).

**Vorteile:**
- Vollständiges Audit-Log inhärent
- Reaktiv und gut parallelisierbar
- Grundlage für zukünftiges CQRS

**Nachteile:**
- Grundlegende Architekturumstellung erforderlich (aktuell kein Event-Sourcing)
- Hoher initialer Aufwand (Wochen bis Monate Migration)
- Komplexe Konfliktauflösung bei gleichzeitigen Events

**Risiko:** HOCH — Paradigmenwechsel, schließt kurzfristige Umsetzung aus

---

### Option C: Copy-on-Write Snapshots mit Merge-Logik (EMPFOHLEN)

**Beschreibung:** Ein Sandbox-Zweig ist eine physische Kopie des Artefakt-Unterbaums
(Scope-spezifisch) in einer neuen Datenbanktabelle sandbox_artefacts. Änderungen
im Sandbox schreiben nur in sandbox_artefacts. Der Merge vergleicht sandbox_artefacts
mit dem aktuellen Hauptstand (3-Field-Diff) und wendet nicht-konfliktive Änderungen
automatisch an. Konflikte werden als Liste zurückgegeben (User-Resolution).

**Vorteile:**
- Implementierbar auf Basis des bestehenden Django ORM
- Klare Datentrennung (kein Eingriff in Haupt-Tabellen)
- 3-Field-Diff einfach implementierbar (JSON-Vergleich)
- Baseline-Kompatibilität gewährleistet (Snapshots unberührt)
- Proof-of-Concept in 1-2 Sprints realisierbar

**Nachteile:**
- Kein vollständiges Versionshistorie innerhalb des Sandbox (nur End-Diff)
- Speicher-Overhead bei großen Workspaces (Vollkopie)
- Kein Support für Sub-Branching (Sandbox eines Sandboxes)

**Risiko:** NIEDRIG — Keine Architekturumstellung, konservative Erweiterung

---

## Entscheidung

**OPTION C (Copy-on-Write) wird empfohlen** als initiale Implementierung für v1.

**Begründung:**
1. Passt zum bestehenden Django + PostgreSQL Stack ohne Paradigmenwechsel
2. Erfüllt alle AC aus REQ-L1-045 und REQ-L2-BL-010
3. Geringster Risikofaktor bei vertretbarem Speicher-Overhead
4. Option A (Git) kann als späteres Upgrade evaluiert werden, wenn Sub-Branching benötigt wird

**Konsequenzen:**
- Neue Tabelle sandbox_artefacts (spiegelt equirements, rchitecture_elements, 	est_cases)
- Neue Tabelle sandboxes (Metadaten: owner, scope, status: open/merged/discarded)
- Neue Django-Service-Klasse SandboxService
- Merge-Algorithmus: 3-Field-Diff + Conflict-Report-Datenstruktur
- Speicher-Limit-Warnung bei Sandbox > 10.000 Artefakten (UX-Guideline)

**Review-Datum:** Vor Implementierungsbeginn (ADR-Review durch 2 Architekten)

---

*Erstellt: 2026-06-28 | Autor: se-architect | Für: REQ-L1-045, REQ-L2-BL-010*
