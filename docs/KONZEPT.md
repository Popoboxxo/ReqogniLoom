# ReqFlow — Konzept-Dokument

> Status: In Bearbeitung — Runde 1 entschieden, Runde 2 offen | Letzte Aktualisierung: 2026-06-17
>
> Dieses Dokument konsolidiert Entscheidungen aus den Ideation-Runden.
> Basis: VISION.md (Commit d73a99e)
>
> Entscheidungsstatus:
> - Runde 1 (Zielgruppe, Lizenz, Deployment): ENTSCHIEDEN
> - Runde 2 (MCP-Tools, SE-Tiefe, Compliance, Multi-Tenancy, i18n/Echtzeit): OFFEN — Fragen unten
> - Runde 3 (Details): AUSSTEHEND

---

## 1. Kernidee (aus VISION.md)

ReqFlow ist das erste Requirements-Management-Tool, das AI-Agenten als native
Prozess-Teilnehmer über MCP einbindet — nicht als Texthelfer, sondern als vollständige,
strukturierte Schnittstelle für den gesamten Anforderungslebenszyklus.

---

## 2. Zielgruppe

> ENTSCHIEDEN — Runde 1, Frage 1

### 2.1 Dual-Zielgruppen-Strategie: BEIDE gleichwertig in v1

ReqFlow bedient zwei gleichwertige Primärzielgruppen in v1:

**Zielgruppe A: AI-first Software Teams**
Software-Teams mit modernen Agile/Scrum-Workflows, die bereits AI-Agenten (Claude Code,
Cursor, GitHub Copilot) einsetzen und einen strukturierten, maschinenlesbaren
Anforderungskontext benötigen.

**Zielgruppe B: Systems Engineers (Embedded / Safety-Critical)**
Engineers mit Bedarf an formalen Artefakt-Hierarchien, Traceability und strukturierter
Anforderungszerlegung — die jedoch heute zwischen zu einfachen Agile-Tools und zu schweren
Enterprise-Lösungen (DOORS, Polarion) stecken.

### 2.2 Technische Umsetzung der Dual-Strategie

**Fundament: Ein gemeinsames generisches Artefakt-Datenmodell**

Beide Zielgruppen arbeiten auf demselben Datenmodell. Es gibt keine parallelen Code-Pfade
oder doppelten Entitäten. Die Unterschiede sind ausschließlich auf Präsentations- und
Konfigurationsebene.

```
Gemeinsames Datenmodell
├── Artifact (hierarchisch, beliebige Tiefe)
├── Requirement (mit Typ, Status, Kategorie)
├── TraceLink (Beziehungstypen: parent-child, derives-from, satisfies, verifies)
└── TestCase (verknüpft mit Requirements)
```

**Terminologie-Presets per Workspace-Profil**

Über ein konfigurierbares Workspace-Setting wählt das Team sein Terminologie-Profil.
Die Daten bleiben identisch — nur Labels und UI-Texte ändern sich:

| Generische Entität | Dev-Modus (Software Teams) | SE-Modus (Systems Engineering) |
|-------------------|---------------------------|--------------------------------|
| Artifact (L1) | Epic | System Requirement |
| Artifact (L2) | Story | Function |
| Artifact (L3) | Task | Component |
| Requirement | Acceptance Criterion | Verification Criterion |
| TraceLink.verifies | Test covers Story | Test verifies Requirement |
| Status: draft | Draft | Draft |
| Status: approved | Done | Approved |

**Implementierung:** Terminologie-Mapping als JSON-Konfiguration im Workspace-Model,
React-UI liest Labels aus aktivem Workspace-Profil. Keine Datenbank-Änderung beim Wechsel.

**Geteilte Traceability-Engine**

Relationships (TraceLinks) sind universell — die Traceability-Engine ist für beide
Zielgruppen identisch. Upstream/Downstream-Queries, Impact-Analysen und Coverage-Reports
funktionieren unabhängig vom aktiven Terminologie-Profil.

### 2.3 Terminologie-Konflikt-Risiko und Gegenmaßnahmen

**Risiko:** Nutzer, die zwischen Profilen wechseln oder in gemischten Teams arbeiten,
könnten durch inkonsistente Terminologie verwirrt werden.

**Gegenmaßnahmen:**
- Workspace-Profil ist sichtbar persistiert (Header-Anzeige: "Dev-Modus" / "SE-Modus")
- Profilwechsel erfordert explizite Bestätigung mit Hinweis "Nur Labels ändern sich,
  keine Daten gehen verloren"
- API und MCP Server nutzen immer die generischen Entitätsnamen (keine Profilabhängigkeit)
- Exporte enthalten das aktive Profil als Metadatum

### 2.4 Explizit NICHT für ReqFlow (v1)

- Teams ohne jegliche Requirements-Disziplin → Jira/Linear
- Hochregulierte Programme mit Zertifizierungspflicht (ISO 26262 ASIL-D, DO-178C Level A) → v2+
- Primärer Fokus auf Dokument-Management → Confluence/SharePoint

---

## 3. Lizenzmodell und Open-Source-Strategie

> ENTSCHIEDEN — Runde 1, Frage 2

**Modell: Vollständig Open Source — MIT oder Apache 2.0**
*(finale Wahl zwischen MIT und Apache 2.0 folgt — Empfehlung: Apache 2.0 für Patent-Schutz)*

**Begründung und Konsequenzen:**
- Open Source beschleunigt die Adoption in Developer-Communities, insbesondere für den
  MCP-Integration-Anwendungsfall
- Community-getriebenes MCP-Ökosystem wird ermöglicht: Dritte können eigene MCP-Tool-Sets
  auf Basis der ReqFlow-API entwickeln und veröffentlichen
- Eine öffentliche MCP-Tool-Registry ist denkbar (Community contributed Tools für spezifische
  Domains: Automotive, Medical, Aerospace)
- Monetarisierung über nachgelagerte Kanäle: Managed Hosting, Support-Contracts,
  Enterprise-Add-ons (kein Open-Core in v1)
- Apache 2.0 empfohlen gegenüber MIT: bietet expliziten Patent-Schutz für Nutzer und
  Contributors, was bei einem Tool für regulierte Branchen relevant ist

---

## 4. Deployment-Modell

> ENTSCHIEDEN — Runde 1, Frage 3

**v1: Ausschließlich Self-Hosted via Docker Compose**

- Kein SaaS in v1
- Docker Compose als primäres Deployment-Modell (bereits im Stack angelegt)
- Vorteil: Datenschutz und Datensouveränität für regulierte Umgebungen,
  kein Vendor-Lock-in, einfaches Community-Onboarding

**v2+:**
- Managed Hosting / SaaS-Option (Monetarisierung)
- Kubernetes-Deployment für Enterprise-Instanzen

**Auswirkung auf Datenmodell — Multi-Tenancy-Vorbereitung:**

Das Datenmodell wird in v1 auf Multi-Tenancy vorbereitet, auch wenn v1 nur Single-Tenant
betrieben wird. Details zum konkreten Ansatz (tenant_id vs. Schema-per-Tenant) werden in
Runde 2 entschieden (siehe Cluster D unten).

---

## 5. AI-Integration — MCP-Prioritäten

> TEILWEISE OFFEN — Runde 2, Fragen 4+5

### 5.1 Primäre MCP-Zielclients

- Claude Code (Anthropic) — nativer MCP-Support, führender Use Case
- Cursor — MCP-kompatibel, breite Developer-Adoption
- Dedicated Requirements-Agenten / Orchestrators (beliebige MCP-kompatible Clients)
- CI/CD-Agenten (GitHub Actions + MCP-Tool-Runner)

### 5.2 MCP-Tools Scope v1 — Vorschlag zur Entscheidung

Die finale Tool-Liste und der Write-Scope sind Gegenstand von Runde 2 (Cluster A).

Folgende Tools sind gesetzt (kein Entscheidungsbedarf):

| Tool | Beschreibung | Begründung |
|------|-------------|------------|
| `requirement.get(id)` | Einzelabruf mit vollständigem Kontext (Traces, Tests, History) | Core Use Case: Coding-Agent prüft vor Implementierung |
| `requirement.query(filters)` | Suche/Filter mit Facetten (Artefakt, Status, Typ, Kategorie) | Core Use Case: Test-Agent ermittelt Abdeckungslücken |
| `requirement.create(title, description, type, parent_id?)` | Anforderung anlegen | Core Use Case: Requirements-Elicitation-Agent |
| `requirement.update(id, fields)` | Felder aktualisieren | Core Use Case: Änderungs-Agent pflegt nach Change Request |
| `requirement.decompose(id, children[])` | Zerlegung in Kind-Artefakte (Batch-Operation) | Ermöglicht strukturierte SE-Zerlegung durch Agenten |
| `traceability.query(artifact_id, direction?)` | Impact-Analyse Upstream/Downstream | Core Use Case: Blast-Radius-Analyse bei Änderungen |
| `test.create(title, type, linked_req_id?)` | Testfall anlegen | Core Use Case: Test-Generierungs-Agent |
| `test.link(test_id, req_id)` | Verknüpfung Testfall ↔ Anforderung | Coverage sicherstellen |
| `workspace.get_context()` | Workspace-Status: offene REQs, unverknüpfte Tests, Coverage-Summary | Orientierung für AI-Agenten beim Einstieg |
| `artifact.get_tree(root_id?)` | Gesamte Artefakt-Hierarchie abrufen | Strukturüberblick für Agenten |

Offene Entscheidungen zu MCP: siehe Runde-2-Fragen, Cluster A.

### 5.3 LLM-Anbindung

> OFFEN — Runde 2

ReqFlow selbst ruft in v1 keine externen LLMs auf. AI-Features entstehen dadurch, dass
externe Agenten (Claude Code, Cursor etc.) via MCP mit ReqFlow interagieren. Die Frage
ob ReqFlow optional eine eigene LLM-Anbindung anbietet (z.B. für `requirement.validate`)
ist Gegenstand von Runde 2.

---

## 6. Systems Engineering Tiefe v1

> OFFEN — Runde 2, Cluster B

Aktueller Stand aus VISION.md: Artefakt-Hierarchie + Traceability als Must-Have.
Baselines und Change-History als Should-Have.

Konkreter Entscheidungsbedarf: siehe Runde-2-Fragen, Cluster B.

MBSE/SysML: explizit v2+ (Begründung: Fügt erhebliche Modell-Komplexität hinzu, die den
Fokus des MVP verwässert und die Zielgruppe A aktiv abschreckt. Artefakt-Hierarchie mit
Traceability ist das 80%-Äquivalent für 20% des Aufwands).

---

## 7. Compliance-Roadmap

> OFFEN — Runde 2, Cluster C

v1 ist bewusst compliance-frei, aber das Datenmodell wird vorbereitet.
Details: siehe Runde-2-Fragen, Cluster C.

---

## 8. Technische Architektur-Entscheide

### 8.1 Multi-Tenancy

> OFFEN — Runde 2, Cluster D

Strategie wird in Runde 2 entschieden. Feststand: Vorbereitung im Datenmodell in v1.

### 8.2 Internationalisierung

> OFFEN — Runde 2, Cluster E

### 8.3 Echtzeit-Kollaboration

> OFFEN — Runde 2, Cluster E

---

## 9. MVP-Scope (zu finalisieren nach Runde 2)

### Must Have v1 (Konsens aus VISION.md + Runde-1-Entscheidungen)

- [x] Gemeinsames generisches Artefakt-Datenmodell mit Terminologie-Presets
- [x] Requirements CRUD mit Artefakt-Hierarchie (beliebige Tiefe)
- [x] Traceability-Engine: TraceLinks zwischen Requirements und Tests
- [x] MCP Server mit Basis-Tool-Set (mindestens: get, query, create, update, traceability.query)
- [x] REST API mit vollständiger CRUD-Unterstützung und OpenAPI-Spec
- [x] React-UI: Dashboard, Requirements-Editor, Artefakt-Navigation
- [x] Docker Compose Deployment (Self-Hosted)
- [x] Workspace-Profile (Dev-Modus / SE-Modus Terminologie)
- [x] Multi-Tenancy-Vorbereitung im Datenmodell (Strategie: Runde 2)

### Out of Scope v1

- [ ] SaaS / Managed Hosting
- [ ] MBSE / SysML-Elemente
- [ ] Echtzeit-Kollaboration (CRDT / OT) — voraussichtlich v2
- [ ] Formale Compliance-Zertifizierung (ISO 26262, DO-178C)
- [ ] SSO (SAML/OIDC)
- [ ] Jira-Synchronisation bidirektional
- [ ] ReqIF-Import/Export
- [ ] AI-gestützte Qualitätsprüfung (`requirement.validate`) — Entscheidung Runde 2

---

## 10. Offene Risiken und Abhängigkeiten

**R1 — Terminologie-Verwirrung:** Dual-Profil kann Nutzer verwirren, wenn nicht klar
kommuniziert wird, was sich beim Profilwechsel ändert (und was nicht). Mitigiert durch
explizite UI-Anzeige und Bestätigungs-Dialog.

**R2 — Scope-Creep durch zwei Zielgruppen:** "Beide gleichwertig" verleitet dazu,
zielgruppen-spezifische Features sofort zu bauen. Gegenmaßnahme: Datenmodell generisch,
UI-Anpassungen minimal (nur Labels + Default-Views).

**R3 — MCP Write-Access-Risiko:** Wenn AI-Agenten Requirements direkt schreiben können,
drohen unkontrollierte Änderungen. Mitigiert durch Suggestion-Mode-Option (Runde-2-Entscheidung).

**R4 — Multi-Tenancy-Migration:** Falsche Strategie in v1 kann spätere SaaS-Option
erheblich verteuern. Entscheidung in Runde 2 ist daher zeitkritisch.

---

## Anhang: Runde-2-Entscheidungsfragen

> Diese Fragen sind die nächste Tranche für den User. Ausgearbeitet durch den ideation-Agenten.

---

### Cluster A — MCP-Server: Finale Tool-Liste und Write-Scope

Die folgende Tool-Liste ist für v1 vorgeschlagen (Basis-Set ist gesetzt, zwei Punkte
erfordern Entscheidung):

**Gesetztes Basis-Tool-Set v1:**

| Tool | Beschreibung |
|------|-------------|
| `requirement.get(id)` | Einzelabruf mit vollständigem Kontext |
| `requirement.query(filters)` | Suche/Filter |
| `requirement.create(title, description, type, parent_id?)` | Anlegen |
| `requirement.update(id, fields)` | Aktualisieren |
| `requirement.decompose(id, children[])` | Zerlegung in Kind-Artefakte |
| `traceability.query(artifact_id, direction?)` | Upstream/Downstream Impact-Analyse |
| `test.create(title, type, linked_req_id?)` | Testfall anlegen |
| `test.link(test_id, req_id)` | Verknüpfung Testfall ↔ Requirement |
| `workspace.get_context()` | Workspace-Status für AI-Agenten-Orientierung |
| `artifact.get_tree(root_id?)` | Gesamte Artefakt-Hierarchie |

**Frage A1 — AI-gestützte Anforderungsvalidierung:**

Soll v1 `requirement.validate(id)` anbieten — eine AI-gestützte Qualitätsprüfung,
ob eine Anforderung vollständig, eindeutig und testbar formuliert ist?

- **Option A (Ja, in v1):** ReqFlow ruft intern ein konfigurierbares LLM an und gibt
  ein strukturiertes Qualitätsfeedback zurück (Score + Verbesserungsvorschläge).
  Aufwand: mittel-hoch (LLM-Anbindung, Prompt-Engineering, Konfiguration).
  Vorteil: klares AI-natives Differenzierungsmerkmal das sofort demonstrierbar ist.

- **Option B (Nein, v2):** `requirement.validate` kommt erst in v2. Fokus in v1 bleibt
  auf strukturiertem Datenzugriff. Externe Agenten können Validierung selbst implementieren,
  da sie über MCP vollen Zugriff haben.

*Empfehlung: Option B (v2).* Begründung: Externe Agenten (z.B. Claude Code als
Requirements-Reviewer) können `requirement.get` nutzen und selbst validieren — ReqFlow
muss dafür kein LLM hosten. Das hält v1 fokussiert und vermeidet eine API-Schlüssel-
Verwaltungs-Komplexität für lokale/regulierte Deployments.

---

**Frage A2 — MCP Write-Scope:**

Soll der MCP-Server in v1 vollen Write-Access haben (create/update/decompose) oder nur
im Read-only + Suggestion-Mode?

- **Option A (Full Read+Write):** AI-Agenten können Requirements direkt anlegen, ändern
  und zerlegen. Maximaler Nutzen für Automatisierungs-Workflows. Höheres Risiko:
  unkontrollierte oder fehlerhafte Änderungen durch Agenten, kein menschlicher Review-Schritt.

- **Option B (Read-only + Suggestion-Mode):** AI-Agenten können alles lesen und
  "Vorschläge" als Draft-Requirements anlegen (Status: "ai-suggested"). Ein Mensch
  bestätigt im UI (Approve / Reject). Write-Access bleibt auf die REST API beschränkt.
  Geringeres Risiko, weniger Automatisierungspotenzial.

*Empfehlung: Option A (Full Read+Write), aber mit Audit-Log.* Begründung: Der Mehrwert
von MCP entsteht gerade durch agentengesteuertes Schreiben. Das Risiko wird durch ein
vollständiges Audit-Log (wer/was/wann) und ggf. eine Rollen-basierte Einschränkung
(MCP-API-Key mit Write-Permission, optional deaktivierbar) beherrschbar gemacht.

---

### Cluster B — Systems Engineering Tiefe v1

Wie tief soll Systems Engineering in v1 implementiert sein?

- **Option A (Minimal-SE):** Nur Artefakt-Hierarchie (Parent-Child-Beziehungen) +
  Traceability-Links zwischen Requirements und Tests. Keine Baselines, keine
  Versionierung, kein Approval-Workflow. Maximale Einfachheit, schnellster MVP.

- **Option B (Standard-SE) — empfohlen:** Zusätzlich zu Option A:
  - **Baselines:** Snapshots einer Anforderungsmenge zu einem Zeitpunkt (unveränderlich,
    benannt z.B. "Sprint-3-Release", "CDR-Baseline"). Ermöglicht Vergleich zwischen
    Ständen. Implementierungskomplexität: mittel.
  - **Change-Tracking:** Wer hat was wann geändert (created_by, modified_by,
    modified_at, change_reason als optionales Freitext-Feld). Kein vollständiges
    Versionierungs-System — nur flaches Audit-Log.

- **Option C (Extended-SE):** Wie B, zusätzlich:
  - **Impact-Analyse-Workflow:** Wenn Requirement X geändert wird, zeigt ReqFlow
    automatisch alle abhängigen Tests, Sub-Requirements und verknüpften Artefakte
    (Blast-Radius-Visualisierung im UI).
  - **Approval-Status:** Requirements können Zustände haben: Draft → In Review →
    Approved → Deprecated. Workflow mit Rollen (Editor schreibt, Approver bestätigt).

*Empfehlung: Option B (Standard-SE).* Begründung: Baselines sind das kritische
Feature für Systems Engineers — ohne Baselines ist ReqFlow für SE nicht ernsthaft
nutzbar. Change-Tracking ist bei regulierten Umgebungen ein Must-Have-Signal für
die Zielgruppe. Option C (Impact-Analyse-UI, Approval-Workflow) ist wertvoll, aber
durch den MCP-Server bereits partiell abgedeckt (ein Agent kann `traceability.query`
nutzen und einen Blast-Radius-Report generieren). Option C daher als v2.

MBSE/SysML: Explizit v2+ — Begründung: SysML-Elemente (Blöcke, Ports, Flows)
erfordern ein fundamentals anderes Metamodell und würden den MVP-Scope sprengen.
Artefakt-Hierarchie mit Traceability ist das 80%-Äquivalent für 20% des Aufwands.
Die Zielgruppe A würde durch MBSE aktiv abgeschreckt.

---

### Cluster C — Compliance-Roadmap

v1 ist bewusst compliance-frei. Das Datenmodell wird jedoch vorbereitet.

**Frage C1 — Minimum-Datenmodell-Felder für spätere Compliance:**

Folgende Felder sind empfohlen — Zustimmung erbeten:

| Feld | Entität | Zweck |
|------|---------|-------|
| `created_by` (FK → User) | Requirement, TraceLink, Test | Autor-Nachweis |
| `created_at` (Timestamp) | Requirement, TraceLink, Test | Erstellungszeitpunkt |
| `modified_by` (FK → User) | Requirement | Letzter Bearbeiter |
| `modified_at` (Timestamp) | Requirement | Letzter Änderungszeitpunkt |
| `version` (Integer, auto-increment) | Requirement | Optimistic Locking + spätere Versionierung |
| `change_reason` (Text, optional) | Requirement | Begründung für Änderungen |
| `status` (Enum: draft/approved/deprecated) | Requirement | Lifecycle für Compliance-Workflows |

Diese Felder sind leichtgewichtig, erzeugen kaum Overhead und ermöglichen später
formale Audit-Trails ohne Datenmodell-Migration.

**Frage C2 — Zielnorm für erste Compliance-Erweiterung (v2):**

Welche Norm soll als erster Compliance-Zielmarkt angegangen werden?

- **ISO 26262 (Automotive Functional Safety):** Breiter Markt (Tier-1/2-Zulieferer,
  OEM-interne Teams), gut dokumentiert, starke Community. Anforderungen: ASIL-Level,
  Hazard-Analysis-Tracing, Verification-Matrizen, elektronische Signaturen. Markt-
  größe: sehr groß.

- **DO-178C (Avionics Software):** Nischenmarkt, extrem strenge Anforderungen
  (Software Level A–D), kaum Spielraum für Tool-Improvisation. Zertifizierung der
  Tools selbst (Tool Qualification) erforderlich — sehr hoher Aufwand für ReqFlow.

- **IEC 61508 (General Functional Safety) — empfohlen:** Breiteste Basis aller
  Funktionssicherheitsnormen. Gilt direkt und als Eltern-Norm für ISO 26262 (Auto),
  IEC 62061 (Maschinensicherheit), EN 50128 (Bahn). Wer IEC 61508 abdeckt, hat die
  Grundlage für alle abgeleiteten Normen. Markt: Industrial Automation, Energy,
  Medical (teilweise).

*Empfehlung: IEC 61508.* Begründung: Als übergeordnete Norm erschließt sie mehrere
Märkte gleichzeitig. ISO 26262 ist attraktiv, aber als erster Schritt unnötig spezifisch.
DO-178C zu aufwändig für eine Open-Source-Positionierung.

---

### Cluster D — Multi-Tenancy-Modell

Das Datenmodell muss in v1 auf Multi-Tenancy vorbereitet werden, auch wenn v1
nur Single-Tenant läuft. Drei klassische Ansätze:

**Option A (Row-Level / tenant_id) — empfohlen:**
Jede Tabelle bekommt eine `tenant_id` Foreign Key-Spalte (FK auf eine `Tenant`-Tabelle).
Alle Queries enthalten automatisch einen `tenant_id`-Filter.

Django-Umsetzungsskizze:
```python
# models.py
class Tenant(models.Model):
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

class TenantAwareModel(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, db_index=True)
    class Meta:
        abstract = True

class Requirement(TenantAwareModel):
    # alle Felder wie gehabt
    ...

# middleware.py — setzt Request-Tenant aus JWT/API-Key
class TenantMiddleware:
    def __call__(self, request):
        request.tenant = resolve_tenant_from_request(request)
        ...

# managers.py — automatischer Filter
class TenantAwareManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(
            tenant=get_current_tenant()
        )
```

In v1 gibt es genau einen Tenant ("default"). Multi-Tenancy-Vorbereitung kostet
minimal extra, verhindert aber eine teure Migration später.

Vorteile: Einfachste Migration, geringstes Django-Setup-Overhead, kein zusätzliches
Package erforderlich, gut verständlich.

Nachteile: Alle Tenants in derselben Datenbank — Query-Filter-Disziplin erforderlich.
Risiko: Vergessener `tenant_id`-Filter in einem Query = Datenleck. Mitigiert durch
Custom Manager + automatisches Filter-Enforcement in Middleware.

**Option B (Schema-per-Tenant):** Jeder Tenant bekommt eigenes PostgreSQL-Schema.
Stärkere Datenisolation. Erfordert `django-tenants`-Package oder erhebliche
Eigenentwicklung. Für v1 (Single-Tenant) überdimensioniert.

**Option C (Database-per-Tenant):** Maximale Isolation. Operativ extrem aufwändig für
Self-Hosted-Deployments. Kommt nur für Enterprise-On-Premises-Szenario infrage.

*Empfehlung: Option A (Row-Level / tenant_id).* Begründung: Minimale Komplexität,
maximale Kompatibilität mit Standard-Django, kein zusätzliches Package. Für ein
Open-Source-Projekt mit Self-Hosted-Fokus der pragmatisch beste Einstieg.

**Abstimmung erbeten:** Stimmt ihr Option A zu, oder gibt es Präferenzen für B?

---

### Cluster E — i18n und Echtzeit-Kollaboration

**Frage E1 — Internationalisierung (i18n):**

Soll v1 mehrsprachig sein?

- **Option A (Ja, i18n in v1):** Django i18n-Framework (gettext) für Backend-Messages,
  react-i18next für Frontend. DE und EN als initiale Sprachen. Aufwand: mittel
  (alle UI-Strings müssen in Translation-Keys extrahiert werden). Vorteil: Später
  sehr günstig neue Sprachen hinzufügen.

- **Option B (Englisch-only in v1) — empfohlen:** Vollständig englischsprachige UI in v1.
  i18n als v2-Feature. Aufwand: null. Risiko: Nachträgliche i18n-Migration ist
  aufwändig (alle Strings müssen extrahiert werden), aber machbar.

*Empfehlung: Option B.* Begründung: i18n-Setup früh zu machen ist zwar günstiger als
nachträglich, aber in der MVP-Phase ist English-only der Standard für Developer-Tools.
ReqFlows Primärzielgruppe (AI-first Dev Teams + SE-Engineers mit AI-Affinität) ist
international und erwartet englische UIs. Aufwand in v1 besser in Core-Features investieren.

---

**Frage E2 — Echtzeit-Kollaboration:**

Soll v1 Echtzeit-Kollaboration unterstützen (mehrere Nutzer bearbeiten gleichzeitig)?

- **Option A (Echtzeit in v1):** Django Channels (ASGI + WebSockets) für
  Live-Updates. Operational Transform (OT) oder CRDT für konfliktfreies gleichzeitiges
  Editieren. Erhebliche Komplexität: neues ASGI-Layer, Conflict-Resolution-Logik,
  Frontend-Sync-State.

- **Option B (v2 — Polling/Refresh in v1) — empfohlen:** v1 nutzt Standard HTTP mit
  manuellem Refresh oder optionalem Short-Polling für Dashboard-Updates. Keine
  WebSocket-Infrastruktur. Echtzeit-Kollaboration in v2 mit Django Channels.

*Empfehlung: Option B.* Begründung: Echtzeit-Kollaboration ist ein erheblicher
Architektur-Komplexitätsmultiplikator. Requirements-Editing ist kein Google-Docs-
Szenario — die meisten Änderungen werden sequenziell vorgenommen, nicht gleichzeitig.
Ein einfaches "Zuletzt gespeichert: X vor 2 Minuten" mit Refresh-Button reicht für v1.

---

*Letzte Aktualisierung durch ideation-Agenten (Runde 2 Aufbereitung) | 2026-06-17*
