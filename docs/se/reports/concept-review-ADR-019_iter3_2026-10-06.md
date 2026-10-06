---
type: REVIEW
scope: adr-019
status: final
date: 2026-10-06
author_agent: concept-reviewer
review_id: RVW-2026-10-06-003
iteration: 3
target_files:
  - docs/se/ADR/ADR-019_generischer_vorschlag_lebenszyklus.md
  - docs/plans/2026-10-05-bugfix-hub-integrationen.md
previous_review: RVW-2026-10-06-002
branch: feat/bugfix-hub-integrations
---

# Concept-Review Iteration 3 (final) — ADR-019 (Verifikation der Iteration-3-Revisionen)

## Scope

Prüfgegenstand ist **ADR-019** (`status: proposed`, 486 Zeilen) in der Fassung nach
Review `RVW-2026-10-06-002` (Iteration 2, Verdict CHANGES_REQUESTED) sowie der zugehörige
Konzeptabschnitt **AP-B5.4** in `docs/plans/2026-10-05-bugfix-hub-integrationen.md:262-329`.
Geprüft wird, ob die Iteration-3-Revisionen die drei offenen Befunde (001-09/001-10/001-11)
schließen, alle Vor-Befunde (001-01…001-08) geschlossen bleiben und keine Regression entsteht.
**Read-only:** ADR und Plan wurden nicht verändert; **kein Commit, kein Push.**

**Prüfstandard:** AGENTS.md „SE-Kaskade: ADR-Standard" (MADR-Minimal) + Review-Lifecycle.
**Verdict: APPROVED** (0× critical, 0× major, 0× minor, 1× info).

---

## Nachprüfung der Iteration-2-Befunde

| ID | Severity | Status Iter 3 | Beleg |
|---|---|---|---|
| **001-09** | major/blocking | **RESOLVED** | ADR:304-318, 348-352, 378-380, 420-427; Plan:297-305 |
| **001-10** | minor | **RESOLVED** | ADR:319-325, 373-375, 456-462; Plan:303-305, 311-312 |
| **001-11** | info | **ADDRESSED** (O11) | ADR:428-433, 470-474; Plan:313, 317 |

### Verifikation 001-09 (Produzenten-Kontext / Human-Bypass)

**Fail-closed ist explizit und nicht still.** Der Human-Bearer-REST-Pfad ist **out of MVP
scope**; wird der Produktions-Adapter mit einem Nicht-Produzenten-Kontext aufgerufen, schlägt
er mit dem **benannten** `ProducerContextRequiredError` (→ HTTP 409) fehl — „statt einen
ungestempelten, sofort bestätigten Link anzulegen; es entsteht **kein** Proposal und **kein**
stiller Human-in-the-Loop-Bypass (weder ‚reject ohne Fehler' noch stiller No-op)"
(ADR:310-314). Die Vorbedingung wird korrekt auf **beide** Kriterien bezogen
(`ctx.actor_type == "agent"` **und** `ctx.api_key_id is not None`, `trace_link_service.py:607`;
ADR:304-306). Beide Trigger-Quellen sind mit Code belegt: MCP
`mcp_server/tools/cross_cutting.py:941-943` ✅, REST
`rest_api/traceability_suggest_views.py:80-82` (`get_auth_context(request)`, `actor_type="user"`)
✅.

**Human-in-the-Loop-Bypass eliminiert.** Der ursprüngliche Bypass (REST-Human-Trigger erzeugt
einen ungestempelten, sofort „bestätigten" Link, `confirm_proposed_link` wird No-op) ist durch
die Scope-Begrenzung + Fail-closed geschlossen. Konsistenz des Scope-Satzes an **allen**
Fundstellen bestätigt:

- Decision 3: ADR:304-318 (inkl. Kanten-Dedup)
- Decision 4: ADR:348-352
- Testbare Kern-Zusagen 7(b)/(f): ADR:373-380
- Konsequenzen: ADR:420-427 (advisory REST bleibt „höchstens lesend", kein Proposal)
- Plan AP-B5.4: Plan:297-305

Kein Widerspruch gefunden; die frühere Unschärfe („confirm bzw. batch-create") ist entfernt
(ADR:301-303 benennt die Entfernung ausdrücklich).

### Verifikation 001-10 (Kanten-Dedup)

O7 ist um die Kanten-Dedup erweitert (ADR:456-462). Der Produzent prüft **vor** `create` auf
einen existierenden Proposal-Link derselben Kante `(source, target, link_type)`
(`uq_tracelink_edge`, `persistence/models.py:2035-2038` ✅; Kollisions-Mapping
`trace_link_service.py:573-578` ✅) und hängt die neue `Suggestion` an diesen, statt hart an der
Constraint zu scheitern (ADR:319-325). Als benannter MVP-Kontrollschritt deklariert und mit
Zusage 7(a) (ADR:373-375) konsistent. **RESOLVED.**

### Verifikation 001-11 (Atomarität)

Als neuer offener Punkt **O11** aufgenommen (ADR:470-474) und als Konsequenz mit konkretem
Fehlerbild benannt: Teilfehler hinterlässt einen verwaisten Proposal-TraceLink, der in der
`ReviewQueueService`-Inbox unsichtbar ist (die Union liest nur Approval-Gate- und
`proposed`-Workflow-Items, `review_queue_service.py:200-264`; ADR:428-433). **ADDRESSED.**

---

## Vor-Befunde 001-01…001-08 — bleiben geschlossen

| ID (Iter 1) | Severity | Status |
|---|---|---|
| 001-01 | major/blocking | RESOLVED (Iter 2, Code verifiziert) |
| 001-02 | major | RESOLVED (Iter 2) |
| 001-03 | minor | RESOLVED (Iter 2) |
| 001-04 | minor | RESOLVED (Iter 2) |
| 001-05 | minor | RESOLVED (Iter 2); Nebenaspekt → 001-10 → RESOLVED |
| 001-06 | minor | RESOLVED (Iter 2) |
| 001-07 | info | ADDRESSED (Iter 2) |
| 001-08 | info | unverändert korrekt |

Die Iteration-3-Revisionen berühren nur Decision 3/4, O7, O11, die Konsequenzen und den
Revisionsvermerk — die Trägerstellen der Vor-Befunde (Accept-Pfad, Threat-Model, Guard je
Adapter, M4-Deklaration, Zitat-/Pfadpräzision) sind unverändert. Keine Regression.

---

## Regressionsprüfung

| Check | Ergebnis |
|---|---|
| MADR-Struktur (Kontext:82 / Alternativen:178 / Entscheidung:250 / Konsequenzen:391) | ✅ intakt |
| Frontmatter (adr_id, title, status, date, deciders, affected_reqs, superseded_by) | ✅ valide (`status: proposed`, ISO-`date`, 16 `affected_reqs`) |
| Keine unaufgelösten Platzhalter (`TODO`/`TBD`/`{{…}}`/`<…>`) in ADR-019 | ✅ keine |
| Plan AP-B5.4 ↔ ADR konsistent (Entscheidung, MVP-Pfad, O1–O11) | ✅ „elf Sub-Entscheidungen" (Plan:308) = O1–O11 |
| Kein stale „batch-create"-Text | ✅ nur als benannte Entfernung (ADR:301) |
| Fail-closed / `ProducerContextRequiredError` in ADR **und** Plan referenziert | ✅ ADR:312,351,379,422; Plan:302 |
| Kanten-Dedup in ADR **und** Plan referenziert | ✅ ADR:319-325; Plan:303-305,312 |
| STOP-Gate | ✅ ADR:476-479 + Plan:307-315 |

---

## Neue Findings

| ID | Severity | Blocking | Dimension | Beschreibung | Suggested Fix |
|----|----------|----------|-----------|--------------|---------------|
| **RVW-2026-10-06-003-01** | info | nein | Konsistenz | **HTTP-Status-Mapping `409`.** Der neue `ProducerContextRequiredError` wird auf **409 Conflict** gemappt (ADR:312,351,379,422). Die bestehende Taxonomie mappt fehlenden/verbotenen Kontext systematisch auf **403** — `AgentSelfConfirmError` (Subklasse von `PermissionError`) → 403 (`rest_api/views.py:218,249`), `PermissionDeniedError` → 403 (`traceability_suggest_views.py:89-93`). 409 ist für einen Kontext-/Berechtigungsfehler semantisch unüblich. Nicht blockierend — die Wahl ist verteidigbar („Vorbedingung nicht erfüllt"), aber bei der Umsetzung muss der Fehler einer REST-/MCP-Fehlerklasse zugeordnet werden, die tatsächlich 409 erzeugt. | Bei der Umsetzung `ProducerContextRequiredError` in der REST-/MCP-Fehler-Taxonomie konsistent verankern (403 permission- oder 409 state-semantisch) und die gewählte Klasse in O11-naher Umsetzung dokumentieren. |

**Es liegen keine neuen blocking-Befunde vor.** `BLOCKED` ist nicht angezeigt.

---

## STOP-Gate / Phase-1-only — Bewertung

**Weiterhin tragfähig.** Die Entscheidungsvorlage bleibt eine reine Phase-1-Vorlage: keine
Migration, kein Modell, kein Tool; ADR:476-479 und Plan:307-315 setzen dies explizit.
O1–O11 bleiben echte Produkt-/Engineering-Entscheidungen; die Iteration-3-Revisionen haben
das STOP-Gate nicht aufgeweicht. Der Text-Abschluss („Kein Produktcode, keine Migration, keine
Manifest-Änderung, kein Commit", ADR:486) stützt dies.

---

## Gesamtbewertung

**Reif für `proposed → accepted`? Ja.** Alle Befunde aus `RVW-2026-10-06-001` (001-01…001-08)
und `RVW-2026-10-06-002` (001-09/001-10/001-11) sind geschlossen bzw. adressiert. Der zentrale
Iter-2-Blocker **001-09 ist sauber gelöst**: der Human-Bearer-REST-Pfad ist explizit aus dem
MVP-Scope genommen und fail-closed mit benanntem Fehler (→ 409) belegt — kein stiller
Human-in-the-Loop-Bypass; der Scope-Satz ist über Decision 3/4, Zusagen, Konsequenzen und Plan
konsistent. **001-10** (Kanten-Dedup) und **001-11** (O11 Atomarität) sind eingearbeitet.
Es verbleibt lediglich ein **info**-Befund zum HTTP-Status-Mapping (nicht blockierend).

---

*Erstellt durch `concept-reviewer` am 2026-10-06 (Iteration 3, final). Read-only — ADR/Plan
unverändert, kein Commit, kein Push.*
