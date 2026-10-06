---
type: REVIEW
scope: adr-019
status: final
date: 2026-10-06
author_agent: concept-reviewer
review_id: RVW-2026-10-06-001
target_files:
  - docs/se/ADR/ADR-019_generischer_vorschlag_lebenszyklus.md
  - docs/plans/2026-10-05-bugfix-hub-integrationen.md
branch: feat/bugfix-hub-integrations
---

# Concept-Review: ADR-019 — Generischer Vorschlags-Lebenszyklus (Entscheidungsvorlage)

## Scope

Prüfgegenstand ist **ADR-019** (`status: proposed`) und der zugehörige Konzeptabschnitt
**AP-B5.4** in `docs/plans/2026-10-05-bugfix-hub-integrationen.md:262-313`. Es handelt sich
ausdrücklich um eine **Entscheidungsvorlage** (kein MVP, kein Code) unter einem STOP-Gate.

**Prüfstandard:** AGENTS.md „SE-Kaskade: ADR-Standard" (MADR-Minimal) + Präzedenz
`docs/se/reports/concept-review-ADR-016-018_2026-10-03.md`. **Read-only:** ADR und Plan wurden
nicht verändert, kein Commit, kein Push.

**Verdict: CHANGES_REQUESTED** (2× major, davon 1 blocking; 4× minor, 2× info).

---

## Verifizierte Belege (Stichprobe, alle bestätigt)

- Vier Mechanismen: M1 `workflow/definition_store.py:605,628,644-711` (PROPOSED_STATE,
  `SCHEMAS_WITHOUT_PROPOSED={minimal, interview_default}`); M2 `persistence/models.py:1965-1976`
  (+ Kommentar `:1957-1960` „TraceLinks … no WorkflowItemState"); M3
  `interview_service.py:2088-2091`; M4 `context_graph/models.py:56-64` (`llm-suggested`).
- Kein `draft → proposed`: `ai_proposal_service.py:45-55` bestätigt; Rule 0
  `transition_validator.py:288-306` bestätigt.
- Transiente Produzenten: `traceability_suggest_service.py:237-338` gibt `SuggestLinksResult`
  zurück, **ohne** TraceLink zu persistieren; `architecture_decompose_service.py:21-27`
  bestätigt „draft NOT server-persisted"; `audit_service.py:992-1012` read-only.
- **M2-Befüllung** erfolgt ausschließlich in `trace_link_service.py:601-617`: nur wenn
  `ctx.actor_type=="agent"` **und** `ctx.api_key_id` gesetzt, werden `proposed_by_id`/`proposed_at`
  beim **Create** gestempelt. `confirm_proposed_link` (`:637-676`) leert nur vorhandene Felder,
  legt aber **keine** Zeile an; `discard_proposed_link` (`:678-728`) löscht die Zeile.
- `batch_create_trace_links` existiert (`traceability/services.py:324`), setzt aber keine
  Proposal-Stempel (nur Layer-2 `create_trace_link` tut das).
- Manifest: `docs/agent-templates/tool-manifest.json:3` `tool_count = 223` — konsistent mit
  der ADR-Angabe „223 Tools". RLS-Gate `persistence/tests/test_rls_coverage.py` existiert und
  erzwingt eine Policy pro `TenantScopedModel`.
- `affected_reqs` stichprobenartig belegt (REQ-L2-WE-002, -AI-007, -AS-012, -PC-006, -RA-020);
  `open_adrs` repo-weit weiterhin nicht vorhanden — ADR weist die Zuordnung korrekt als
  „belegte Näherung" aus (Kontext 6 / Konsequenzen).

---

## Prüfmatrix

| Kriterium | Ergebnis |
|---|---|
| Frontmatter-Pflichtfelder (adr_id, title, status, date, deciders, affected_reqs, superseded_by) | ✅ alle vorhanden/valide (`status: proposed`, `date` ISO, `deciders` ≥1) |
| ≥2 Alternativen inkl. Abwägung + rejected | ✅ A (gewählt/Zielrichtung), B/C/D (VERWORFEN), je mit Abwägung + Risiko |
| Entscheidung präzise/testbar | ⚠️ überwiegend ja (7 testbare Kern-Zusagen); **ein** MVP-Pfad nicht eindeutig (siehe 001-01) |
| Konsequenzen positiv UND negativ | ✅ beide Blöcke substantiell |
| Threat-Model (4 Fragen) | ⚠️ vorhanden, aber **Payload-/Provenienz-Integrität fehlt** (siehe 001-02) |
| `affected_reqs` belegt / nicht leer | ✅ 16 IDs; Näherung ehrlich flagged |
| ADR-ID-Muster / keine Wiederverwendung | ✅ `ADR-019` einmalig |

---

## Findings

| ID | Severity | Blocking | Dimension | Category | Beschreibung | Suggested Fix |
|----|----------|----------|-----------|----------|--------------|---------------|
| **RVW-2026-10-06-001-01** | **major** | **ja** | Logik/Konsistenz | MVP-Accept-Pfad widersprüchlich | Die MVP-Wahl von `TraceabilitySuggestService.suggest_links` wird mit „(c) der Accept-Pfad (M2) bereits existiert" begründet (ADR:248-249). `suggest_links` liefert jedoch nur flüchtige DTOs und persistiert **keine** TraceLink-Zeile (`traceability_suggest_service.py:237-338`). M2s `confirm_proposed_link` (`trace_link_service.py:637-676`) setzt aber eine **bereits existierende** vorgeschlagene Zeile voraus; die einzige Quelle des `proposed_by`/`proposed_at`-Stempels ist der Layer-2-Create `create_trace_link` bei Agenten-Prinzipal (`:601-617`). Decision 3 lässt den Pfad mit „confirm_proposed_link **bzw.** Anlage über den atomaren Batch-Pfad" offen (ADR:236-238) — damit ist der zentrale Accept-Pfad des „testbaren" MVP nicht definiert, und Kern-Zusage 7(b) („Accept ruft den bestehenden Mechanismus auf") ist für den MVP unklar. | Genau **einen** Pfad festlegen: entweder (i) MVP-Produzent auf `create_trace_link` (Agent) umstellen, sodass M2-confirm real greift, **oder** (ii) `trace_link`-Accept = `batch_create_trace_links`/`create_trace_link` mit Domain-Revalidierung (kein M2-confirm) und Begründung (c) korrigieren. Decision 3 auf eine Aussage pro `kind` reduzieren. |
| **RVW-2026-10-06-001-02** | **major** | nein | Risiko | Threat-Model unvollständig (Payload/Provenienz) | Die neue Entität persistiert ein LLM-erzeugtes `payload`-JSON (ADR:220,143) und materialisiert es später. Das Threat-Model (2)(a)-(d) nennt Agent-Self-Confirm, Tenant-Leak, State-Bypass und Retention (ADR:120-124), aber **nicht** Payload-Injection/-Tampering noch Provenienz-Fälschung (`producer`/`proposed_by`). Die Checklist fordert genau diese Punkte. Der Kontrollmechanismus existiert zwar de facto (delegierter Accept re-validiert, z. B. `trace_link_service._check_link_pair:537-544`), ist aber nicht benannt. | Threat-Model um einen Punkt ergänzen: `payload` ist untrusted; Accept re-validiert über den delegierten Domain-Pfad; `producer`/`proposed_by`/`decided_by` sind server-gesetzte Audit-Fakten, nie caller-supplied. Retention abgelehnter Payloads an O9 koppeln. |
| **RVW-2026-10-06-001-03** | minor | nein | Konsistenz | Guard-Zitat ungenau | Decision 3 (ADR:242) sagt, der Adapter „erbt den Agent-Guard (`transition_validator.py:288-308`)". Rule 0 greift nur bei **Workflow-State-Transitions**; der `trace_link`-Pfad hat einen **eigenen** Guard (`AgentSelfConfirmError`, `trace_link_service.py:658-661`). M1 erbt Rule 0, M2 nicht. | Klarstellen, dass der Guard **je Adapter** greift: Rule 0 für `artifact_create`, Service-Guard für `trace_link`; jeder Adapter muss die Agent-Sperre explizit assertion. |
| **RVW-2026-10-06-001-04** | minor | nein | Logik/Konsistenz | M4 hat keinen Accept-Pfad | Die Kontext-Tabelle weist M4 selbst als „Origin-Feld, **kein** eigener Accept-Endpoint" aus (ADR:69). Decision 3 („`context_edge` → M4 … Accept hebt `llm-suggested` auf", ADR:240-241) beschreibt damit **neue** Logik (Origin-Update), was der Kernzusage „reimplementiert keine … Logik" widerspricht. | Entweder M4 aus der „bestehenden Accept-Mechanismen"-Liste herausnehmen (nur Provenienz-Träger, kein Accept) oder den Origin-Update explizit als kleinen neuen Adapter deklarieren. |
| **RVW-2026-10-06-001-05** | minor | nein | Vollständigkeit/Logik | Idempotenz-Spannung | Kern-Zusage 7(a) verspricht „genau eine `open`-Suggestion", während O7 (Idempotenz/Dedup) vertagt ist (ADR:266-267,330-331). Zwei Produzenten-Läufe erzeugen zwei offene Zeilen. | Zusage auf „pro erfolgreicher Produzenten-Ausführung genau eine" schärfen und explizit auf O7 verweisen. |
| **RVW-2026-10-06-001-06** | minor | nein | Konsistenz | Zitat-/Pfadungenauigkeit | `auth_enforcer.py:60` (ADR:258, Plan:304) → tatsächlich `rest_api/auth_enforcer.py:60`. `review_queue_service.py:1-101` (ADR:41) deckt nur Docstring/DTO; die Union-Logik liegt bei `:200-264`. Decision 1 nennt `TenantScopedModel` **und** `AuditableModel` (ADR:213-214), obwohl `TenantScopedModel` bereits von `AuditableModel` erbt (`persistence/models.py:446`). | Pfade/Zeilen präzisieren; als Basis nur `TenantScopedModel` nennen. |
| **RVW-2026-10-06-001-07** | info | nein | Prozess/Kaskade | Autor-Rolle | ADR-019 wurde durch `ideation` erstellt (ADR:341); der SE-ADR-Standard weist Erstellung/Statuswechsel `se-architect` zu. Der ADR dokumentiert den deaktivierten SE-Kaskaden-Schalter ehrlich als Annahme, macht die Rollenabweichung aber nicht explizit. | Analog ADR-016 §Lifecycle-Vermerk die Abweichung als user-getragen festhalten oder Rollenkonformität herstellen. |
| **RVW-2026-10-06-001-08** | info | nein | Konsistenz | Plan-Match | Plan AP-B5.4 (Plan:262-313) gibt die ADR-Entscheidung korrekt wieder, verlinkt sie (`../se/ADR/ADR-019_…`), markiert UI klar als eigenes Follow-up (Plan:307-309) und nennt O1-O9 deckungsgleich. Keine Diskrepanz zur ADR. | Keine. |

---

## STOP-Gate / Phase-1-only — Bewertung

**Grundsätzlich tragfähig, aber teilweise über-konservativ.** Die vier Mechanismen sind
nachweislich strukturell unvereinbar, und O2 (Komposition vs. Zustands-Hoheit), O3
(`minimal`-Semantik), O4 (Migration der TraceLink-Felder) und O8 (Entity vs. Generic-Artifact)
sind echte **Produkt**entscheidungen — ein Gesamtmodell in einem Durchgang ist damit
plausibel nicht entscheidbar; die Entscheidungsvorlage ist gerechtfertigt.

**Aber:** Für den *MVP* sind O5 (MCP-Surface), O7 (Idempotenz) und O9 (Retention) keine
Produkt-, sondern überwiegend Engineering-Entscheidungen, und Finding 001-01 ist ein
**technischer**, kein produktseitiger Widerspruch. Solange dieser offen ist, ist der MVP
*nicht* „testbar wie beschrieben", und der STOP-Vorwand wirkt für den MVP breiter als nötig.
Empfehlung: entweder die Empfehlungen zu O5/O7/O9 im ADR als Default festschreiben oder die
MVP-Testbarkeitszusage explizit relativieren.

---

## Gesamtbewertung

**Reif für `proposed → accepted`? Nein — vor Freigabe nachbessern.**
Es liegen **keine critical**-Befunde vor; ein BLOCKED ist nicht angezeigt. Blockierend ist
allein **001-01** (major): die zentrale MVP-Begründung und der Accept-Pfad passen nicht zum
gewählten Produzenten. **001-02** (major, Threat-Model) ist vor der Umsetzung, nicht
zwingend vor der Freigabe zu schließen. Die minors/ infos sind Präzisierungen.

**Was konkret blockiert:** 001-01. **Empfohlene Reihenfolge:** 001-01 → 001-02 → 001-03/04/05/06.
Nach Behebung steht der User-Freigabe nichts entgegen; der Statuswechsel erfolgt durch
`se-architect`/User, nicht durch den Autor.

**Faktische Widersprüche zu den Recon-Fakten:** keine — alle vier Mechanismen, die
Transienz der Produzenten, das Fehlen der `draft → proposed`-Kante, die
`minimal`/`interview_default`-Ausnahme, 223 Tools und das RLS-/Manifest-Gate sind belegt und
von der ADR korrekt zitiert. Der einzige inhaltliche Fehlschluss ist 001-01 (Accept-Pfad).
