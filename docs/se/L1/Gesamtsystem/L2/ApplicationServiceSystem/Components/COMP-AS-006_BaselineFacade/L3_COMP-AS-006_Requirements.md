# L3 BaselineFacade Requirements

> **Level:** L3 (Komponenten-Anforderungen)
> **Komponente:** COMP-AS-006 — BaselineFacade
> **Parent-System:** ApplicationServiceSystem (L2)
> **Status:** Entwurf

---

## Verantwortlichkeit

Baseline-Lifecycle-Orchestrierung: Preset-Check -> Snapshot-Delegation -> AuditLog; Diff-Operationen.

## Zugeordnete L2-Anforderungen

| REQ-L2 | Anforderungstext (Kurzform) |
|--------|-----------------------------|
| REQ-L2-AS-011 | Baseline Lifecycle Orchestration: PresetConfigEngine-Konsultation, BaselineService-Delegation, AuditLog |

## Interne Schnittstellen

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-AS-INT-006 | ausgehend | COMP-AS-012 (PresetPolicyService) | `is_scope_allowed(workspace_id, scope)` |
| IF-AS-INT-012 | ausgehend | COMP-AS-013 (DomainEventBus) | `BaselineCreated` — post_commit via Outbox |

## Externe Schnittstellen (falls Komponente an Systemgrenze)

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-AS-EXT-OUT-002 | ausgehend | BaselineService | `build(scope, workspace_id, ctx)`, `diff(a, b)` |
| IF-AS-EXT-OUT-007 | ausgehend | PersistenceLayer | Django ORM — Baseline-Metadaten |

---

## L3 Komponenten-Anforderungen

### REQ-L3-AS006-001: Preset-gesteuerter Scope-Check vor Baseline-Erstellung


**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.


Die BaselineFacade SHALL vor jeder Baseline-Erstellung den PresetPolicyService konsultieren, ob der angeforderte Scope im aktiven Preset des Workspace erlaubt ist. Bei nicht erlaubtem Scope: Operation abbrechen mit erklaerenden Fehler.

**Priority:** mandatory

**Acceptance Criteria:**
- [ ] `create_baseline(scope="global", workspace_id, ctx)` in Minimal preset raises `PolicyError("Scope not permitted")`
- [ ] `create_baseline(scope="project", workspace_id, ctx)` in Standard preset succeeds and delegates to BaselineService
- [ ] Scope check occurs before any call to BaselineService
- [ ] Allowed scope results in BaselineService.build() being called with correct parameters

---

### REQ-L3-AS006-002: Baseline-Erstellung und AuditLog


**Implementation State:** Implemented
**Review Findings:** Implementierung gefunden, aber keine Tests.
**Test Status:** Missing
**Remarks:** Testabdeckung fehlt.


Die BaselineFacade SHALL nach erfolgreicher Baseline-Erstellung durch den BaselineService ein `BaselineCreated`-Domain-Event im selben Transaktionskontext publizieren und sicherstellen, dass die erstellte Baseline immutabel ist.

**Priority:** mandatory

**Acceptance Criteria:**
- [ ] Successful `create_baseline()` results in exactly one `BaselineCreated` event in the outbox
- [ ] Created baseline has immutable flag set — no update operation allowed on its content
- [ ] Rolled-back baseline creation results in zero events published
- [ ] `create_baseline()` returns baseline metadata including id, created_at, scope, workspace_id

---

### REQ-L3-AS006-003: Baseline-Diff-Operation


**Implementation State:** Implemented
**Review Findings:** Implementierung gefunden, aber keine Tests.
**Test Status:** Missing
**Remarks:** Testabdeckung fehlt.


Die BaselineFacade SHALL eine `diff_baseline(baseline_id_a, baseline_id_b, ctx)`-Methode bereitstellen, die den strukturierten Unterschied zweier Baselines zurueckgibt. Die eigentliche Diff-Berechnung delegiert an `BaselineService.diff(a, b)`.

**Priority:** mandatory

**Acceptance Criteria:**
- [ ] `diff_baseline(a, b, ctx)` returns result with sections `added`, `removed`, `changed`
- [ ] Diff of identical baselines returns empty sections (no added/removed/changed)
- [ ] Both baselines must belong to the same workspace — cross-workspace diff raises `ValidationError`
- [ ] Non-existent baseline_id raises `NotFoundError`

---

*Erstellt durch se-requirements-Agent (L3-Component) | ReqFlow SE-Kaskade | 2026-06-21*
