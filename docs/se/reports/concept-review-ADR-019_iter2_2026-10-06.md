---
type: REVIEW
scope: adr-019
status: final
date: 2026-10-06
author_agent: concept-reviewer
review_id: RVW-2026-10-06-002
iteration: 2
target_files:
  - docs/se/ADR/ADR-019_generischer_vorschlag_lebenszyklus.md
  - docs/plans/2026-10-05-bugfix-hub-integrationen.md
previous_review: RVW-2026-10-06-001
branch: feat/bugfix-hub-integrations
---

# Concept-Review Iteration 2 — ADR-019 (Re-Review der Iteration-2-Revisionen)

## Scope

Prüfgegenstand ist **ADR-019** (`status: proposed`, 419 Zeilen) in der Fassung nach
Review `RVW-2026-10-06-001` (Iteration 1, Verdict CHANGES_REQUESTED) sowie der
zugehörige Konzeptabschnitt **AP-B5.4** in `docs/plans/2026-10-05-bugfix-hub-integrationen.md:262-322`.
Geprüft wird, ob die Iteration-2-Revisionen die offenen Befunde schließen, ohne neue
Probleme einzuführen. **Read-only:** ADR und Plan wurden nicht verändert, kein Commit, kein Push.

**Prüfstandard:** AGENTS.md „SE-Kaskade: ADR-Standard" (MADR-Minimal) + Review-Lifecycle.
**Verdict: CHANGES_REQUESTED** (1× major neu; 1× minor neu; 1× info neu; alle 8 Vor-Befunde geschlossen).

---

## Ergebnis der Nachprüfung der Vor-Befunde

| ID (Iter 1) | Severity | Status Iter 2 | Beleg |
|---|---|---|---|
| **001-01** | major/blocking | **RESOLVED** (Kern) — mit neuer Qualifikation 001-09 | ADR:272-294,309-314; Code verifiziert |
| **001-02** | major | **RESOLVED** | ADR:142-146,155-161 |
| **001-03** | minor | **RESOLVED** | ADR:301-307 |
| **001-04** | minor | **RESOLVED** | ADR:296-300 |
| **001-05** | minor | **RESOLVED** (geschärft); Nebenaspekt 001-10 | ADR:332-334 |
| **001-06** | minor | **RESOLVED** | ADR:41-43,248-250,324 |
| **001-07** | info | **ADDRESSED** | ADR:67-69 |
| **001-08** | info | **unverändert korrekt** | Plan:262-322 kongruent |

### Verifikation 001-01 (Accept-Pfad) — Code bestätigt

Alle im ADR zitierten Funktionen/Zeilen existieren und verhalten sich wie beschrieben:

- `TraceLinkService.create_trace_link` **`:489`** ✅ (`@atomic_transaction`).
- M2-Proposal-Stempel **`:601-617`** ✅ — nur wenn `ctx.actor_type == "agent"` **und** `ctx.api_key_id is not None` werden `proposed_by_id`/`proposed_at` gesetzt (`trace_link_service.py:607`).
- `confirm_proposed_link` **`:637-676`** ✅ — leert `proposed_by`/`proposed_at`, legt keine Zeile an; auf einem Nicht-Proposal idempotenter No-op (`:665`).
- `discard_proposed_link` **`:678-728`** ✅ — löscht nur bei `is_proposal` (`:701`), sonst `ValidationError`.
- Agent-Guard `AgentSelfConfirmError` **`:658-661`** ✅ (Klasse `:72` = `PermissionError`); REST mappt sie auf **403** (`rest_api/views.py:218`, `:249`). Zusage 7(c) „nicht still" ist damit belegt.
- REST-Accept-Routen `trace-links/{id}/confirm|discard` **`views.py:3359-3399`** ✅.
- `_check_link_pair` **`:537-544`** ✅; `uq_tracelink_edge`-Mapping `:573-578` ✅.
- `TraceLink.proposed_by`/`proposed_at` **`models.py:1965-1976`**, kein `WorkflowItemState` **`:1957-1959`**, `is_proposal` **`:2068-2070`** ✅.
- `suggest_links`-DTO (`LinkSuggestion`, `traceability_suggest_service.py:162-185`) trägt **tatsächlich kein** `link_type` ✅; Regel→Typ-Ableitung TRACE-P1/P1b → `derives-from`, TRACE-P2 → `allocated-to` deckt sich mit `traceability/audit/rules/trace_derivation_allocation.py:324,374,457`.
- `TenantScopedModel` erbt `AuditableModel` (`models.py:446` erbt `:379`) ✅ — die Iter-1-Kritik (001-06) ist korrekt umgesetzt.
- `rest_api/auth_enforcer.py:60` = `class RbacPermission` ✅; `review_queue_service.py:200-264` = Union-Logik ✅.

**Ergebnis:** Die frühere „confirm bzw. batch-create"-Unschärfe ist beseitigt; der Accept-Pfad
ist für den **agenten-/API-Key-Produzenten** technisch real und widerspruchsfrei. Die
Scope-Änderung ist ausgewiesen (ADR:291-294) und als O10 mit schlankerer Alternative dokumentiert
(ADR:405-409). Ein **verbleibender** Widerspruch betrifft nicht den Accept-Mechanismus als
solchen, sondern seine **Vorbedingung** → neues Finding 001-09.

### Verifikation 001-02 (Threat-Model)

Vollständig adressiert: Payload-Injection/-Tampering (2e, ADR:142-144), Provenienz-Fälschung
(2f, `:145-146`), Tenant-Isolation beim Accept (2b, `:136-137` + Gegenmaßnahme `:150-152`),
No-Bypass von Policy/Workflow/RBAC/Audit (2c, `:138-139` + `:153-154`). Kein Blind-Merge,
kein `eval` (`:158`), Provenienz server-gesetzt (`:159-161`), Retention an O9 gekoppelt (`:162`).
**RESOLVED.**

### Verifikation 001-03..001-06

- **001-03** — Guard je Adapter klar getrennt: Rule 0 (M1, `transition_validator.py:288-306`) vs. Service-Guard (trace_link); `artifact_create` muss die Sperre explizit prüfen (ADR:301-307). ✅
- **001-04** — M4 explizit als **neue, kleine** Origin-Logik deklariert, „erbt keinen bestehenden Accept-Pfad" (ADR:296-300). Die Restspannung zu Decision 2 („reimplementiert keine … Logik", ADR:260-263) ist durch diese Deklaration aufgelöst. ✅
- **001-05** — Zusage 7(a) auf „**Pro erfolgreicher** Produzenten-Ausführung" geschärft + expliziter O7-Verweis (ADR:332-334). ✅ (Nebenaspekt → 001-10.)
- **001-06** — `review_queue_service.py:1-101,200-264` präzisiert (ADR:41-43); `rest_api/auth_enforcer.py:60` korrigiert (ADR:324, Plan:311); nur `TenantScopedModel` als Basis, mit Hinweis auf `AuditableModel`-Vererbung (ADR:248-250). ✅

### 001-07 / 001-08

- **001-07** (info): Rollenabweichung nun als user-getragene Ausnahme bei deaktivierter SE-Kaskade vermerkt (ADR:67-69) — analog ADR-016. **ADDRESSED.**
- **001-08** (info): Plan AP-B5.4 gibt ADR deckungsgleich wieder (Plan:285-297 ↔ ADR:272-294; O1–O10 identisch inkl. O10, Plan:304). **unverändert korrekt.**

---

## Neue bzw. verbleibende Findings

| ID | Severity | Blocking | Dimension | Beschreibung | Suggested Fix |
|----|----------|----------|-----------|--------------|---------------|
| **RVW-2026-10-06-002-09** | **major** | **ja** | Logik/Konsistenz | **Produzenten-Kontext nur für Agent/MCP gültig, nicht für den REST-/Human-Trigger.** Der Fix setzt voraus, dass beim Produzieren `create_trace_link` „unter dem Produzenten-Kontext (Agent + `api_key_id`)" läuft (ADR:275-276) und damit `:601-617` stempelt. Der Stempel greift aber nur bei `ctx.actor_type == "agent"` **und** `ctx.api_key_id is not None` (`trace_link_service.py:607`). Der Produzent ist **beidseitig exponiert**: MCP (`self._trace_suggest_service.suggest_links(workspace_id, auth_context, …)`, `mcp_server/tools/cross_cutting.py:941-943`; Agent/API-Key) **und** REST (`TraceabilitySuggestService().suggest_links(workspace_id, get_auth_context(request), scopes=scopes)`, `rest_api/traceability_suggest_views.py:80-82`; Human-Bearer → `actor_type="user"`, kein `api_key_id`). Auf dem REST-Pfad unterbleibt der Stempel: der „Proposal-TraceLink" ist dann ein **normaler, sofort bestätigter** Link; `confirm_proposed_link` wird zum stillen No-op (`:665`) und `discard` zum `ValidationError` (`:701`). Damit ist genau die Human-in-the-Loop-Garantie der Zusage 7(b)/(c) auf dem REST-Pfad nicht erfüllt. Die Codebasis kennt dieses Muster bereits als echten Bug: `ai_proposal_service.py:13-19` (#1089 — human-getriggerte Ableitung mit `actor_type="user"`). Das ADR adressiert die Kontext-Synthese nur für `artifact_create` (Accept), nicht für den `trace_link`-Produzenten. | Entweder (i) MVP-Produktion **explizit** auf agenten-/API-Key-Kontexte (MCP) begrenzen und den REST-Produzenten als Follow-up markieren, **oder** (ii) die Kontext-Synthese analog `resolve_proposal_authoring` für den `trace_link`-Produzenten benennen — inklusive der Frage, welchem stabilen `ApiKey` ein human-getriggerter Vorschlag zugeordnet wird (M2 verlangt einen `proposed_by_id`). In Decision 3/4 + Zusage 7(b) referenzieren. |
| **RVW-2026-10-06-002-10** | minor | nein | Vollständigkeit/Logik | **Re-Run kollidiert mit `uq_tracelink_edge`.** Mit dem geänderten MVP-Pfad persistiert der Produzent jetzt einen echten TraceLink. `create_trace_link` mappt die Unique-Verletzung auf `ValidationError` (`trace_link_service.py:573-578`); die Constraint liegt auf `(source, target, link_type)` (`persistence/models.py:2037`, Migration `0049_tracelink_unique_edge.py`). Ein erneuter Produzenten-Lauf erzeugt (deterministisch) denselben Top-Kandidaten und scheitert dann **hart**, statt eine zweite Suggestion anzulegen. O7 (ADR:401-402) vertagt nur die Suggestion-Dedup, nicht die Kanten-Kollision. | O7 um den Fall erweitern: Produzent prüft vor `create` auf einen bereits existierenden Proposal-Link (Lookup) und hängt die neue Suggestion an diesen, statt zu scheitern; oder O7 eindeutig als „auch Kanten-Dedup" deklarieren. |
| **RVW-2026-10-06-002-11** | info | nein | Logik | **Atomarität von Proposal-Link + Suggestion-Quittung nicht festgelegt.** `create_trace_link` ist atomar, aber das Anlegen der `Suggestion`-Zeile ist ein separater Write. Bei Teilfehler entsteht ein verwaister Proposal-TraceLink, der in der Suggestion-/`ReviewQueueService`-Inbox unsichtbar ist (ReviewQueueService vereinigt nur Approval-Gate- und `proposed`-Workflow-Items, ADR:113-116). | Festlegen: TraceLink + Suggestion in **einer** Transaktion (oder Suggestion zuerst), und/oder verwaiste Proposals in die Inbox aufnehmen. |

---

## Regressionsprüfung

| Check | Ergebnis |
|---|---|
| MADR-Struktur (Kontext / Alternativen / Entscheidung / Konsequenzen) | ✅ intakt |
| Frontmatter (adr_id, title, status, date, deciders, affected_reqs, superseded_by) | ✅ intakt |
| Keine unaufgelösten Platzhalter (`TODO`/`TBD`/`{{…}}`) | ✅ keine |
| Plan AP-B5.4 ↔ ADR konsistent (Entscheidung, MVP-Pfad, O1–O10 inkl. O10) | ✅ deckungsgleich |
| Kein stale „batch-create"-Text | ✅ entfernt (ADR:292 benennt die Entfernung explizit) |
| Guard-Darstellung ADR ↔ Plan | ✅ konsistent (ADR:301-307 ↔ Plan:287-290) |
| Zitat-/Pfadungenauigkeiten aus 001-06 | ✅ korrigiert und nachgeprüft |

Keine strukturelle Regression; die Revision ist sauber eingearbeitet.

---

## STOP-Gate / Phase-1-only — Bewertung

**Weiterhin tragfähig.** Die vier Mechanismen bleiben strukturell unvereinbar, und O1–O10
bleiben echte Produkt-/Engineering-Entscheidungen. Die Iteration-2-Revision hat den
MVP-Accept-Pfad für den Agenten-Pfad technisch geschlossen. **001-09 ist keine
Modell-, sondern eine Scope-/Kontextpräzisierung** (eine Aussage oder ein Synthese-Regelsatz)
und rechtfertigt **kein** Aufweichen des STOP-Gates. Der 001-05-Nebenaspekt (001-10) ist
O7-adjazent und blockiert nicht.

---

## Gesamtbewertung

**Reif für `proposed → accepted`? Nein — noch nicht; ein major-Punkt offen.**
Derzentrale Iter-1-Blocker **001-01 ist im Kern geschlossen** (Accept-Pfad real, Code belegt),
**001-02 vollständig** (Threat-Model), **001-03…001-06** geschlossen, **001-07/001-08** adressiert.
Neu offen ist **001-09 (major)**: Die im Fix vorausgesetzte Produzenten-Vorbedingung
(`agent` + `api_key_id`) ist auf dem REST-/Human-Pfad nicht erfüllt und nicht durch eine
benannte Kontext-Synthese abgesichert — sonst entsteht auf diesem Pfad ein stiller
Human-in-the-Loop-Bypass. Mit einer einzigen ergänzenden Aussage (Scope-Begrenzung **oder**
Synthese-Regel) ist der Weg frei.

**Es liegen keine critical-Befunde vor; BLOCKED ist nicht angezeigt.**

---

*Erstellt durch `concept-reviewer` am 2026-10-06 (Iteration 2). Read-only — ADR/Plan unverändert,
kein Commit, kein Push.*
