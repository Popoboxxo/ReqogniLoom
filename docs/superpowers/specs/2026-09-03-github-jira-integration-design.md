# GitHub- und Jira-Anbindung — Design

**Status:** Draft, pending user review
**Quelle:** `docs/SYSTEMAUDIT_2026-09-02_GROB.md`, Kap. W (eigener, bereits konkreter
3-Stufen-Plan des Audits), E1 (Webhook-Substanz vorhanden, aber nicht self-service),
Q2.10 (Integration ist Einbahnstraße). Siebte von mehreren unabhängigen Folge-Specs aus
demselben Audit — siehe
[2026-09-03-traceability-semantik-design.md](2026-09-03-traceability-semantik-design.md),
[2026-09-03-ki-vorschlag-als-zustand-design.md](2026-09-03-ki-vorschlag-als-zustand-design.md),
[2026-09-03-interview-engine-fix-design.md](2026-09-03-interview-engine-fix-design.md).
**Scope:** GitHub und Jira, wie vom Nutzer benannt — GitLab (im Audit als drittes Beispiel
genannt) ist architektonisch trivial nachrüstbar (`system`-Feld ist erweiterbar), aber
nicht Teil dieser Spec. Webhook-Self-Service als eigenständiges UI-Thema (E2.2) ist nicht
Teil dieser Spec — Stufe 3 nutzt den bestehenden `WebhookDispatcher`/Outbox-Mechanismus
direkt, ohne dessen fehlende Self-Service-Verwaltung (Django-Admin-only) zu beheben.

## 1. Problem

Substanz ist da (Outbox-Pattern mit Idempotenz-Guard, `WebhookSubscription` mit HMAC,
33 EventTypes, MCP mit 172 Tools, REST vollständig für CRUD) — aber Integration ist eine
Einbahnstraße: kein `external_ref`-Feld auf irgendeinem Artefakt, kein
Webhook-**Empfänger** (nur Sender), keine OAuth-App-Registrierung, keine
Idempotenz-Schlüssel auf Create. Die AI-first-Zielgruppe hat ihre Tickets in Jira oder
GitHub; sie wird ReqogniLoom nicht als zweite Wahrheit pflegen, solange es keine Brücke
gibt.

## 2. Ziel

Drei Stufen, wie im Audit selbst vorskizziert, hier konkretisiert und mit dem
inzwischen gebauten Fundament (Artifact-Backing, Traceability-Semantik, Workflow-Engine)
verzahnt:

1. **Link-Only** — Sichtbarkeit ohne Sync.
2. **Inbound-Sync** — externe Events aktualisieren ReqogniLoom-Zustand automatisch.
3. **Outbound + Agent** — ReqogniLoom erzeugt externe Issues, Agenten bekommen Tools.

## 3. Stufe 1 — Link-Only

### 3.1 `ExternalRef` als Artifact-backed Entity

```python
class ExternalRef(TenantScopedModel):
    artifact = models.ForeignKey("persistence.Artifact", on_delete=models.CASCADE, related_name="+")
    backing_artifact = models.OneToOneField("persistence.Artifact", on_delete=models.CASCADE, related_name="external_ref")
    system = models.CharField(max_length=32, choices=[("github", "GitHub"), ("jira", "Jira")])
    external_id = models.CharField(max_length=128)   # z.B. "142" (GitHub) oder "PROJ-42" (Jira)
    url = models.URLField(max_length=2048)
    kind = models.CharField(max_length=16, choices=[("issue", "Issue"), ("pr", "Pull Request"), ("epic", "Epic")])
    last_seen_status = models.CharField(max_length=64, blank=True)
    synced_at = models.DateTimeField(null=True, blank=True)
```

**Warum zwei Artifact-Bezüge:** `artifact` ist das ReqogniLoom-Artefakt (Requirement,
Issue, ...), das extern verknüpft wird. `backing_artifact` ist eine eigene, dedizierte
`Artifact`-Zeile (`artifact_type="ExternalRef"`) — genau das "virtuelle Artefakt vom Typ
ExternalRef", das der Audit für die Traceability-Anbindung vorschlägt. Ohne eigene
Artifact-Zeile kann `TraceLink` (dessen `source`/`target` immer auf `Artifact` zeigen)
nicht auf einen externen Verweis zeigen — dasselbe Muster wie Diagram/Icd/GlossaryTerm in
der Datenmodell-Konsolidierung-Spec, hier für eine neue, kleine Entity von Anfang an
richtig gebaut statt nachgerüstet.

**Cross-Spec-Amendment nötig:** die Traceability-Semantik-Spec (Abschnitt 3.2) definiert
`references` mit den erlaubten Zielen `GlossaryTerm`, `Diagram`, `Icd` — `ExternalRef`
fehlt dort, weil diese Spec zum Zeitpunkt jener Spec noch nicht existierte. Wird als
Amendment nachgetragen (gleiches Vorgehen wie beim GlossaryTerm-Fund in der
Datenmodell-Konsolidierung-Spec): `references`-Zielliste um `ExternalRef` erweitern.

### 3.2 API und UI

**REST:** `artifacts/<id>/external-refs/` (Liste, Anlegen mit URL-Paste — Backend parst
GitHub-/Jira-URLs und extrahiert `system`/`external_id`/`kind`), `external-refs/<id>/`
(Löschen).
**MCP:** `artifact.link_external`, `artifact.list_external`.
**UI:** Chip neben dem Status-Badge ("GH #142 · open"), Dialog "Extern verknüpfen" mit
URL-Paste (Erkennung von GitHub-/Jira-URL-Mustern), Klick öffnet extern. Kein Sync in
dieser Stufe — reine Sichtbarkeit.

## 4. Stufe 2 — Inbound-Sync

### 4.1 Webhook-Empfänger

Neue, öffentlich erreichbare Endpoints (kein bestehender Auth-Mechanismus greift hier,
da GitHub/Jira keine ReqogniLoom-Session haben):

- `POST /api/v1/integrations/github/webhook/` — Signaturprüfung via `X-Hub-Signature-256`
  (HMAC-SHA256, Secret pro Workspace-Integration-Config), Standardverfahren von GitHub.
- `POST /api/v1/integrations/jira/webhook/` — Jira-Webhooks (Server/Data-Center und
  einfache Cloud-Setups) haben kein eingebautes HMAC-Pendant; Absicherung über ein
  Shared-Secret als Query-Parameter (`?token=...`) im konfigurierten Webhook-URL — Standard-
  Workaround für selbstgehostete Jira-Integrationen ohne Atlassian-Connect-App. Volles
  Atlassian-Connect (signierte JWT-Requests) ist ein späterer Ausbau, kein MVP-Blocker.

### 4.2 Ereignisse und Regeln

Verarbeitete Events: `issue.opened`, `issue.closed`, `issue.labeled`,
`pull_request.merged` (GitHub); `jira:issue_updated` mit Statuswechsel (Jira). Jedes
aktualisiert `ExternalRef.last_seen_status`/`synced_at` für den passenden `external_id`.

**Regeln als Erweiterung der Workflow-Engine, nicht als Parallelsystem:** eine Transition
in `WorkflowEngineDefinition.workflow_json` bekommt ein neues optionales Feld
`external_trigger: {"system": "github", "event": "pull_request.merged"}`. Trifft ein
passendes Webhook-Event für ein verknüpftes `ExternalRef` ein, wird die Transition für
das zugehörige Artefakt automatisch ausgeführt — kein `allowed_roles`-Check (die Aktion
kommt nicht von einer Person oder einem Agenten, sondern vom externen System selbst),
aber der `WorkflowHistoryEntry` bekommt `actor_type="system"` (neuer dritter Wert neben
`user`/`agent` in `AuditEntry.ACTOR_TYPE_CHOICES`, siehe KI-Vorschlag-als-Zustand-Spec
Abschnitt 3 für das bestehende `user`/`agent`-Paar) mit `client_name="github-webhook"`
o. ä. für die Nachvollziehbarkeit.

Konfiguration unter System-Einstellungen, Tab "Integrationen": Repo-/Projekt-Liste,
Webhook-Secret, Regeltabelle (welches externe Event löst welche Transition aus) — als
Editor-UI im selben Stil wie Workflow-/Attribut-/Link-Typ-Editor dieser Session
(Liste statt Canvas, da keine Graph-Struktur nötig ist).

## 5. Stufe 3 — Outbound und Agent

### 5.1 Credentials

Neues Modell `ExternalSystemCredential(workspace, system, token_encrypted,
created_by, created_at)` — ein Personal Access Token pro Workspace und System,
verschlüsselt gespeichert nach demselben Muster wie `SystemMemorySettings.honcho_api_key`
(bereits etablierter Verschlüsselungs-Mechanismus im Codebase, kein neuer Baustein).
Verwaltung unter System-Einstellungen, Tab "Integrationen" (derselbe Tab wie 4.2).

### 5.2 Adapter auf dem bestehenden Outbox-Mechanismus

`WebhookDispatcher`/`DomainEventOutbox` (`application/models.py`, bereits produktiv)
bekommt zwei neue Adapter-Klassen, `GitHubIssueAdapter` und `JiraIssueAdapter`, die ein
Outbox-Event in einen API-Call gegen das jeweilige System übersetzen (analog zum
Verhältnis zwischen `ARTIFACT_CREATION_ADAPTERS` und der Interview-Engine — ein Event,
ein Adapter je Zielsystem, keine Spezialcode-Verzweigung im Aufrufer). Beispiel-Regel:
Requirement-Transition nach `approved` erzeugt ein GitHub-Issue mit Link zurück zum
Requirement; TestCase-Ergebnis `failed` erzeugt einen Bug.

**MCP:** `integration.github.create_issue(artifact_id)`,
`integration.jira.sync(artifact_id)` — neue Tool-Gruppe. Ein Agent, der diese Tools
aufruft, braucht laut Agenten-Identität (KI-Vorschlag-als-Zustand-Spec, Abschnitt 3)
`scope="write"` auf seinem `ApiKey` für den betroffenen Workspace — dieselbe
Scope-Prüfung wie jeder andere Agent-Schreibzugriff, kein Sonderfall. Das erzeugte
GitHub-/Jira-Ticket selbst durchläuft **nicht** den `proposed`-Workflow-Zustand (das ist
eine externe Seiteneffekt-Operation, kein internes Artefakt) — der resultierende
`ExternalRef`-Link auf der ReqogniLoom-Seite dagegen schon, wie jeder andere von einem
Agenten erzeugte Link.

### 5.3 Interview-Grounding

`build_memory_context()`/Grounding (Interview-Engine-Fix-Spec) bekommt `ExternalRef`s des
betroffenen Artefakts als zusätzlichen Kontext-Baustein: "Zu diesem Requirement gibt es
PR #142, gemerged am …" — reiner Lese-Zugriff auf Stufe-1/2-Daten, kein neuer Mechanismus.

## 6. UI-Zielbild

- **Im Artefakt:** Sektion "Extern" mit Chips, Status-Spiegel (`last_seen_status`),
  "Öffnen in GitHub/Jira".
- **In der Liste:** Spalte "Extern" mit System-Icon.
- **In den Verknüpfungen:** eigene Gruppe "Extern" (der `references`-Link zum
  `ExternalRef`-Backing-Artefakt).
- **Im Dashboard:** "3 Requirements haben gemergte PRs, aber Status draft" — ein
  Abgleich zwischen `ExternalRef.last_seen_status` und dem eigenen `current_state`.

## 7. Migration

Additiv, keine Bestandsdaten betroffen (das Feature existiert heute nicht):

1. `ExternalRef`, `ExternalSystemCredential` als neue Tabellen.
2. `AuditEntry.ACTOR_TYPE_CHOICES` um `"system"` erweitern (additiv, bestehende
   `user`/`agent`-Werte unverändert).
3. `WorkflowEngineDefinition.workflow_json`-Schema um optionales `external_trigger`
   pro Transition erweitern (additiv, bestehende Definitionen ohne dieses Feld
   funktionieren unverändert weiter).
4. Traceability-Semantik-Spec Abschnitt 3.2 amendieren: `references`-Ziele um
   `ExternalRef` ergänzen.

## 8. Risiken

- **Jira-Webhook-Absicherung über Query-Param-Secret** ist schwächer als HMAC — akzeptabel
  für ein MVP ohne Atlassian-Connect-App, aber ein Secret in der URL kann in Logs landen
  (Empfehlung: URL-Query-Parameter aus Standard-Access-Logs ausschließen, sonst
  Secret-Rotation bei Verdacht auf Leck).
- **PAT-basierte Credentials** sind pro Workspace ein einzelner, breiter Zugriffs-Token
  (kein feingranulares Scope wie bei einer echten GitHub-App) — Risiko, wenn ein Token
  weiterreichende Rechte hat, als ReqogniLoom tatsächlich braucht. Dokumentations-Hinweis:
  "Token mit minimalen Repo-Scopes erzeugen", technische Durchsetzung nicht möglich ohne
  OAuth-App (Stufe 4, nicht diese Spec).
- **`external_trigger`-Transitionen ohne `allowed_roles`-Check** sind ein neuer,
  ungeprüfter Automatisierungspfad — eine falsch konfigurierte Regel (z. B. jedes
  `issue.labeled`-Event löst eine Transition aus) kann unbeabsichtigt Artefakte durch den
  Workflow schieben. Mitigation: Regeln nur von Tenant-/Workspace-Admin konfigurierbar
  (wie jede andere Workflow-Definition), keine zusätzliche technische Sperre in dieser
  Spec vorgesehen.
- Cross-Spec-Abhängigkeit: `references`-Amendment an der Traceability-Semantik-Spec
  (Abschnitt 3.2) muss vor der Stufe-1-Implementierung nachgezogen werden.
