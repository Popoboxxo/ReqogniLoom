---
type: REVIEW
scope: system-audit-2026-09
status: final
date: 2026-09-24
author_agent: validator
revision: e3df119e52c0cbcc18df02f708567207c0374826
document_type: evidence-validation
---

# Systemaudit 2026-09 — Evidenzvalidierung und Korrekturen

Dieses Addendum validiert die wichtigsten P1-Behauptungen der Synthese gegen den zum Auditzeitpunkt geprüften Code. Es überschreibt keine bereits dokumentierte Evidenz, sondern kennzeichnet ausdrücklich überholte, eingeschränkte oder noch offene Teilaussagen.

## 1. Gesamturteil

Die Grundrichtung des Audits ist belastbar: 10 von 12 geprüften Kernbehauptungen sind bestätigt, zwei sind nur teilweise bestätigt. Die Synthese ist als statische Risikokarte wertvoll, aber noch nicht als Release-Nachweis oder als abschließende Produktbewertung freigegeben.

| Befund | Validierungsstatus | Korrigierte Einordnung |
|---|---|---|
| `CR-03` API-Key-Defaults | Bestätigt | P1 nur für neue Agent-/Automation-Keys; gewöhnliche User-PATs und Legacy-Härtung P2 |
| `CR-04` `comment.resolve` Workspace-Fence | Bestätigt | P1 als intra-tenant Cross-Workspace-Write über MCP; kein Cross-Tenant-Leak behaupten |
| `CR-05` MCP-Multi-Interview | Bestätigt | P1 nur für `formalize` mit mehreren Sessions; Single-MCP nicht als defekt verallgemeinern |
| `CR-06` Single-Interview-Formalize-Race | Bestätigt | P1 Race; kein garantierter automatischer Rollback behaupten, Chat-Atomizität separat P2 |
| `CR-08` Workflow-Transition | Bestätigt | P1 Stale-Validation/Graph-Edge-Race, nicht pauschal Lost Update |
| `CR-09` Global-Definition-Propagation | Teilweise bestätigt | P1 für fehlende Atomizität/Orphan-Schutz; partielle Row-Propagation ist nicht belegt |
| `CR-20` LLM-Budget | Bestätigt, Severity überhöht | P2 oder policyabhängig P1; nur konkrete direkte Call-Sites nennen |
| `CR-26` Workspaceless-Bearer | Bestätigt | P1 für Workspaceless-Authorization; JWT-/Refresh-Familie getrennt bewerten |
| `CR-30` CI-Collection/Integration | Bestätigt, Collection offen | P1; 463 Source-Level-Definitionen, nicht als bereits ausgeführte Collection zählen |
| `CR-31` E2E-Laufzeitparität | Bestätigt | P1 für Runtime/Contract-Parität; API-Script-/Tooling-Teile P2 |
| `CR-32` Release-/Provenienz-Gate | Bestätigt | P1; vorhandene Build-Metadaten nicht als fehlende Provenance bezeichnen, sondern Digest-Bindung prüfen |
| `CR-45` GitHub-Actions-Injection | Teilweise bestätigt | `deployed_url` ist bestätigter Sink; Docker-Tag-Injection nicht als bestätigt ausweisen |

## 2. Korrigierte Kernaussagen

### 2.1 API-Key-Lifecycle (`CR-03`)

`write` ist ein Admin-Scope. Fehlende REST-/Servicefelder führen bei neuen Agent-/Automation-Keys zu `write`, leerem `workspace_ids` und `expires_at=NULL`; die UI sendet standardmäßig nur den Namen. Das ist für neue Automation-/Agent-Keys ein P1-Fail-Open-Default. Für gewöhnliche User-PATs und die Härtung bestehender Legacy-Keys genügt zunächst P2.

Negativtest: `POST /api-keys/` mit `principal_type=agent` ohne Scope/Fence/Expiry muss entweder mit 400 abgewiesen werden oder sichere, explizite Defaults erhalten. `workspace_ids=[]` bedeutet nicht automatisch den gesamten Tenant, sondern den historischen Owner-/Fence-Vertrag und muss separat dokumentiert werden.

### 2.2 Workspace-Fence (`CR-04`)

Der Befund gilt für den MCP-Dispatch von `comment.resolve`: Der Zielworkspace wird nicht aus `comment → artifact → workspace` aufgelöst, wodurch ein unrestringierter Key mit Editor-Rolle in Workspace A einen Kommentar in Workspace B desselben Tenants auflösen kann. Das ist ein P1-Fehler der Workspace-Isolation, aber kein belegter Cross-Tenant-Leak.

Negativtest: Editor nur in Workspace A plus Kommentar in Workspace B ⇒ `PERMISSION_DENIED`, Status unverändert; Editor in Workspace B ⇒ Erfolg.

### 2.3 MCP-Interview (`CR-05`)

Das MCP-Schema enthält nur `session_id` und reicht `confirmed_proposal` nicht an den Application-Service weiter. Dadurch ist der publizierte Multi-Formalize-Pfad nicht ausführbar. Die Formulierung „MCP-Interviews sind defekt“ wäre zu breit; der Befund betrifft die Multi-Formalize-Parität.

Negativtest: Multi-MCP mit gültigem Proposal erzeugt Artefakte; fehlendes oder ungültiges Proposal ergibt kontrolliert `VALIDATION_ERROR`.

### 2.4 Interview-Formalize (`CR-06`)

Der Single-Pfad prüft `in_progress` ohne `select_for_update`; `InterviewSessionArtifact` besitzt keine eindeutige Session-Artefakt-Constraint. Zwei konkurrierende Formalize-Aufrufe können daher mehrfach schreiben. Die Validierung hat außerdem gezeigt, dass ein Transition-Fehler in einem bestehenden Catch-Pfad abgefangen wird; ein garantierter Rollback eines bereits erzeugten Artefakts darf nicht behauptet werden. Der Chat-Loop bleibt ein separates P2-Atomizitätsthema.

Negativtest: Zwei Datenbankverbindungen mit Barrier auf derselben Single-Session; exakt ein Artefakt, ein Abschluss und eine Audit-/Outbox-Korrelation.

### 2.5 Workflow-Transition (`CR-08`)

Die fachliche Validierung erfolgt vor dem Lock. Der Row-Lock allein schützt nicht die zuvor gelesene Graphentscheidung. Das Facade reicht zudem kein durchgängiges `expected_version` durch. Der korrekte Begriff ist Stale-Validation-/Graph-Edge-Race; ein klassischer Lost Update ist nicht allein durch den Befund belegt.

Negativtest: Zwei konkurrierende Requests mit unterschiedlichen Zielen; genau ein Erfolg, der zweite 409, keine History-Kante außerhalb des neu gelesenen Graphen.

### 2.6 Global-Definitionen (`CR-09`)

Der globale Save und die Propagation sind nicht atomar, und der Store prüft keine Live-Items abgeleiteter Workspaces ausreichend. Die Propagation verwendet jedoch einen einzelnen `QuerySet.update()`-Bulk; ein selektives Row-Update ist daraus nicht belegt. Der belegte Kern ist die Divergenz zwischen globaler und abgeleiteter Wahrheit sowie fehlender Fault-/Orphan-Schutz.

Negativtest: ein Item in einem nicht individualisierten Workspace plus State-Delete muss abgewiesen werden; ein injizierter Fehler darf weder globale noch abgeleitete Teilstände erzeugen.

### 2.7 LLM-Kostenkontrolle (`CR-20`)

`context.change_impact`, Memory-Tasks und der Health-Probe umgehen bzw. erfassen zentrale Budgetpfade nicht durchgängig. Andere AI-Services prüfen jedoch Limits, und ein unbegrenztes Verhalten ist als Default dokumentiert. Der Befund sollte daher nicht als „alle LLM-Pfade umgehen Budget“ formuliert werden.

Je nach Produktvertrag ist CR-20 P2 oder policyabhängig P1: Für harte SaaS-Kosten-/Mietergrenzen ist die fehlende zentrale Durchsetzung release-relevant; für QS/self-hosted kann sie zunächst P2 bleiben. Health benötigt ein separates Betriebsbudget.

Negativtest: gesetztes Tenant-/Provider-Budget, Mock-Provider und ein Context-/Memory-/Health-Aufruf ⇒ nach Erreichen des Limits kein weiterer Provider-Request.

### 2.8 Workspaceless-Bearer (`CR-26`)

Bei nichtleerem `claims.roles` verwendet der Workspaceless-Pfad den JWT-Rollen-Snapshot ohne DB-Prüfung von `User.is_active`, Rollenrevision oder Authz-Version. Das ist P1 für Workspaceless-Governance-/Authorization-Pfade. Handgebaute JWT-Validierung und Refresh-Familie-Lifecycle müssen als eigene P2/P3-Themen geführt werden; der aktuelle Befund ist kein vollständiger Auth-Bypass.

Negativtest: Admin-Bearer ausstellen, Benutzer deaktivieren oder Admin-Rolle entziehen, Workspaceless-Governance-Endpunkt ohne Cookie-Refresh aufrufen ⇒ 401/403.

### 2.9 CI, E2E und Release

`CR-30`: Die Zahl 463 bezeichnet Source-Level-Testdefinitionen. Die tatsächliche Collection unter dem Ziel-Image und der Umfang der ausgeführten Tests bleiben offen; Live-MCP-/Redis-Tests werden explizit übersprungen.

`CR-31`: Der Laufzeit-/Contract-Befund bleibt P1: Der E2E-Workflow testet nicht die produktive Uvicorn-/nginx-Laufzeit und darf TraceLink-Fehler skippen. Das kaputte `test:e2e:api`-Script und reine Tooling-Probleme sind P2.

`CR-32`: Es gibt bereits Build-Commit-Metadaten. Der Befund lautet daher nicht „keine Provenance“, sondern: Es fehlt eine erzwungene, digestgebundene Kette aus getestetem Image, Scan, SBOM, Provenance und Signatur. Der konkrete P1-Nachweis ist der fehlende Test-vor-Image-Gate bzw. der nicht nachgewiesene Digest-Identitätsnachweis.

### 2.10 GitHub-Actions-Injection (`CR-45`)

`deployed_url` wird in `version-drift-check.yml` direkt in Shell-Quelltext interpoliert; dieser Sink ist bestätigt. Der behauptete `docker/metadata-action`-Tag-Sink ist nicht gleichwertig belegt, weil der Action-Output für Docker-Tags sanitisiert wird. Der Docker-Tag-Claim muss entfernt oder als offene Reachability-Messung geführt werden.

Negativtest: Dispatch-Metazeichen wie `"; id; #`, Newline und Redirect dürfen keinen Sentinel-Befehl ausführen.

## 3. Korrigierte Priorisierung

### Sofortige P1-Containment-Arbeit

1. `CR-03` mit sicheren Agent-/Automation-Key-Defaults.
2. `CR-04` mit Target-Workspace-Fence und Negativtest.
3. `CR-05` mit REST/MCP-Multi-Formalize-Parität.
4. `CR-06` mit Lock/Unique-Constraint/Idempotenz-Test.
5. `CR-08` mit Lock-gebundener Revalidierung und `expected_version`.
6. `CR-09` mit atomarem Global-/Derived-Store und Fault-Injection.
7. `CR-26` mit aktueller User-/Rollenprüfung für Workspaceless-Governance.
8. `CR-30`/`CR-31` mit verpflichtender Collection, Live-Integration und ASGI-/nginx-SSE-E2E.
9. `CR-32` mit Test-vor-Image und digestgebundener Release-Kette.
10. `CR-45` mit escapten/validierten `workflow_dispatch`-Inputs.

### Policyabhängig

- `CR-20`: P1 bei verbindlichem SaaS-/Tenant-Budget, P2 bei self-hosted/QS.
- `CR-25`: bedingt P1, wenn Bluepencil in Shared-/Produktivprofilen aktiviert wird; Default-off QS bleibt P2.

### Nicht als bestätigte P1 ausweisen

- Selektive Row-Teilpropagation bei `CR-09`.
- Docker-Tag-Injection über `steps.meta.outputs.tags` bei `CR-45`.
- „Alle LLM-Pfade umgehen Budget“ bei `CR-20`.
- „463 Tests wurden gesammelt/ausgeführt“ bei `CR-30`.
- „Keine Provenance vorhanden“ bei `CR-32`.
- Ein garantierter Rollback des Interview-Artefakts bei `CR-06`.

## 4. Erforderliche Messungen vor einer Freigabe

1. Ziel-Commit und vollständige Testcollection unter Linux/CI festhalten.
2. Zwei-Connection-/Barrier-Tests für Interview- und Workflow-Writes.
3. Fault-Injection für globale Definitionen und Outbox/History-Korrelation.
4. Tenant-/Fence-Negativtests für API-Keys, `comment.resolve` und Workspaceless-Bearer.
5. Authentifizierter SSE-Roundtrip gegen Uvicorn/nginx.
6. Kostenbudget-Test für die drei direkten LLM-Call-Sites.
7. Image-Digest-, SBOM-, Provenance- und Signaturidentität im Release-Workflow.
8. Vollständiger Browser-/Keyboard-/Screenreader-/Reflow-Nachweis für die Frontend-P1s.

## 5. Status und Geltung

Die vorherige Health-Score-Synthese bleibt als konservativer Steuerungsindikator nachvollziehbar, ist aber bis zur HEAD-/Runtime-Validierung keine exakte Risikomessung. Dieses Addendum ist für die zwölf geprüften Kernclaims die massgebliche Korrektur- und Severity-Quelle. Die übrigen Themenberichte bleiben Audit-Trail; ihre offenen Messungen und historischen Revisionsangaben gelten unverändert fort.

```text
STATUS: done
RESULT: 10/12 Kernclaims bestätigt, CR-09 und CR-45 teilweise bestätigt; überhöhte Teilformulierungen und Severity-Overrides dokumentiert.
ARTIFACT: docs/se/reports/deep_audit/system-audit-2026-09/12-evidence-validation-and-corrections.md
```
