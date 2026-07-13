# ADR-003: Glossar-Storage (Semantisches Projekt-Glossar Datenspeicherung)

**Status:** PROPOSED
**Datum:** 2026-06-28
**Entscheider:** Architekt + Tech-Lead
**Betroffene REQs:** REQ-L1-044, REQ-L2-AS-033, REQ-L2-RA-014
**Übergeordneter Need:** REQ-L0-032 (SN-32 — Semantisches Projekt-Glossar)

---

## Kontext

REQ-L2-AS-033 fordert eine Domänen-Entität GlossaryTerm mit Versionierung und
Baseline-Integration. Für die Datenspeicherung gibt es zwei konkurrierende Ansätze,
die sich in Datenmodell-Komplexität, Query-Performance und Versionierungs-Semantik
unterscheiden.

---

## Entscheidungsalternativen

### Option A: Separate Django-Modell-Tabelle GlossaryTerm (EMPFOHLEN)

**Beschreibung:** GlossaryTerm wird als eigenes Django-Modell mit dedizierten
Datenbankfeldern implementiert. Die Versionshistorie wird in einer separaten Tabelle
GlossaryTermVersion (ähnlich dem bestehenden RequirementVersion-Muster) gespeichert.

`python
class GlossaryTerm(models.Model):
    id = models.UUIDField(primary_key=True)
    workspace = models.ForeignKey(Workspace, ...)
    term = models.CharField(max_length=255)
    definition = models.TextField()
    synonyms = models.JSONField(default=list)        # ["Synonym1", "Synonym2"]
    abbreviation = models.CharField(max_length=50, blank=True)
    version = models.PositiveIntegerField(default=1)
    created_by = models.ForeignKey(User, ...)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

class GlossaryTermVersion(models.Model):
    term = models.ForeignKey(GlossaryTerm, related_name="versions", ...)
    version = models.PositiveIntegerField()
    definition = models.TextField()
    synonyms = models.JSONField()
    changed_by = models.ForeignKey(User, ...)
    changed_at = models.DateTimeField()
`

**Vorteile:**
- Konsistent mit bestehendem Requirement/RequirementVersion-Muster
- Volltext-Suche über 	erm und definition via PostgreSQL GIN-Index
- Klare Datenintegrität (Unique-Constraint: 	erm pro workspace)
- Einfache Baseline-Integration: Baseline.snapshot() erfasst alle GlossaryTerm-Objekte
- Django Admin-UI sofort verfügbar

**Nachteile:**
- Zwei neue Tabellen (Migration erforderlich)
- Leicht mehr Entwicklungsaufwand als Option B

**Risiko:** SEHR NIEDRIG — Bewährtes Django-ORM-Muster

---

### Option B: JSONB-Feld im Workspace-Modell

**Beschreibung:** Das Glossar wird als einzelnes glossary-JSONB-Feld im bestehenden
Workspace-Modell gespeichert. Struktur: { "terms": [{ "id": "...", "term": "...", ... }] }.

**Vorteile:**
- Keine neue Tabelle / Migration
- Abruf des gesamten Glossars in einer Query (kein JOIN)

**Nachteile:**
- Kein Unique-Constraint auf Terminus-Ebene (Duplikate möglich)
- Keine Versionshistorie pro Term (nur Gesamthistorie über AuditLog)
- Volltext-Suche auf JSONB komplex (kein GIN-Index ohne Konfiguration)
- Workspace-Dokument wächst unbegrenzt (Performance bei großen Glossaren)
- TraceLinks (uses-term) benötigen stabile Term-IDs → schwieriger bei JSONB

**Risiko:** MITTEL — Datenintegrität und Skalierbarkeit fragwürdig

---

## Entscheidung

**OPTION A (Separate Django-Modell-Tabelle) wird empfohlen.**

**Begründung:**
1. Konsistenz mit dem bestehenden Requirement/RequirementVersion-Muster (minimale Lernkurve)
2. Stabile Term-IDs für TraceLinks (uses-term Typ aus REQ-L2-AS-033 AC6)
3. Volltext-Suche mit PostgreSQL GIN-Index (AC6: "Glossar ist durchsuchbar")
4. Saubere Versionierung pro Term (REQ-L2-AS-033 AC2)
5. Baseline-Integration ohne Sonderbehandlung (AC3)

**Konsequenzen:**
- Neue Django-Migration: GlossaryTerm + GlossaryTermVersion
- Unique-Constraint: (workspace_id, term) — Duplikate auf DB-Ebene verhindert
- GIN-Index auf GlossaryTerm.term und GlossaryTerm.definition für Suche
- Baseline.snapshot() erweitert um GlossaryTerm-Queryset
- Neuer TraceLink-Typ uses-term in TraceLink.link_type-Enum registrieren
- Neue Serializer: GlossaryTermSerializer, GlossaryTermVersionSerializer

**Review-Datum:** Vor Implementierungsbeginn (1 Reviewer ausreichend, kein Board nötig)

---

*Erstellt: 2026-06-28 | Autor: se-architect | Für: REQ-L1-044, REQ-L2-AS-033, REQ-L2-RA-014*
