# Problemanalyse-Gates — MVP-Schnitte S0.1–S0.4 (2026-11-16)

**Basis:** `origin/main` `c84f3376` · **Methode:** Plan §0.1, zwei Pass (Beleg → Adversary) ·
**Ergebnis:** 24 bestätigt, 4 angepasst, 1 False Positive, 1 nutzer-blockiert.

> Die Audit-Datei wurde als **Hypothese** behandelt. Jede Entscheidung unten stützt sich auf
> aktuellen Code, Git-History oder eine Laufzeit-Repro — nicht auf die Audit-Behauptung allein.

## S0.1 — Secret-Incident & Security-Baseline

| Finding | Entscheidung | Beleg (Auszug) | Anpassung / nächster Schritt |
|---|---|---|---|
| SEC-001 | **BESTÄTIGT, USER-BLOCKED** | `git show a8cee99e:.env:11,20` = vollständiger `SECRET_KEY`/`DB_PASSWORD`; `git log --all -S '7d7091'` → `a8cee99e`/`bad447fd` | Rotation + History-Rewrite erfordern Produktiv-Zugriff, Owner-Freigabe, Wartungsfenster. **Zuerst rotieren, dann rewiten.** Auch die Audit-Commits `cedb62f8`/`08550995` enthalten gekürzte Präfixe. |
| SEC-003 | BESTÄTIGT | `settings.py:768-770` default `optional`; `.env.example:89`; `auth_views.py:402` | Nicht nur Env-Flip: `mfa_enforce_cutover --dry-run` vor Aktivierung (Staff-Lockout). Repo-Seite implementierbar, Produktiv-Umschaltung = Owner. |
| SEC-004 | **ANPASSEN** | `throttling.py:48-64,205-212,316-362` dokumentiertes Fail-open; `test_rate_limit_runtime.py:203,232` verankert es | Pauschales Fail-closed wäre schädlich. Nur Auth-Scopes fail-closed mit begrenztem In-Memory-Fallback + Alerting; generischer Throttle bleibt fail-open. |
| SEC-005 | BESTÄTIGT (bedingt) | `jwt_tokens.py:42-127` hand-rolled HS256, korrekt implementiert; `requirements*` ohne PyJWT | PyJWT hinter `decode_jwt` mit Äquivalenz- und Negativ-Gates (`alg:none`, fehlendes `exp`, falsche `iss/aud`). Alternative „bewusst akzeptiert" nur mit Owner + Review-Datum. |
| SEC-006 | BESTÄTIGT | `.pre-commit-config.yaml:29`, `ci.yml:1162,1165,1195-1197` — nur Custom-Rules | Identische Root-Cause wie OPS-003 → **in einem Change** lösen. |
| SEC-007 | BESTÄTIGT | `deploy/docker-compose.yml:86,1261,1307` `:‑`-Defaults; kein `ports:` → nur interns Netz | `${HONCHO_DB_PASSWORD:?…}` erzwingen. |
| OPS-003 | BESTÄTIGT | gitleaks-Doku: `--enable-rule` = *nur* diese Rule; `.gitleaks.toml:52-53` `useDefault` wird dadurch neutralisiert | Vierter blockierender Lauf mit Default-Regeln + Allowlists + Canary für `reqlo_`, `SECRET_KEY=` und AWS-/PEM-Typ. Vor dem History-Rewrite landen. |

## S0.2 — Tenant-/RLS-Korrektheit

| Finding | Entscheidung | Beleg | Anpassung |
|---|---|---|---|
| APP-001 | BESTÄTIGT | `quality_auto_assess.py:250-251,254,276` nur Thread-Local; `persistence/middleware.py:35-67` setzt GUC; `0122_quality_assessment_rls_policy.py:40-44` ENABLE+FORCE fail-closed | `set_request_tenant` im `try`, Restore mit `tenant_was_set`-Snapshot im `finally` (Präzedenz `artifact_summary_sweep.py:381-382`). **Nicht** „conditional on rollout". |
| SEC-002 | BESTÄTIGT (Entscheidung E2) | `settings.py:380-397`; `test_rls_coverage.py:240-260` = **genau 7 staged Tabellen**; `rls_hardening.py:15-20` permissiv bei unset | Nur diese 7 Tabellen sind permissiv. Andere tenant-scoped Tabellen haben unbedingte fail-closed Policies. `hard_enforced` = Owner-SQL, nicht Env-Flag. Empfehlung: gestaffelter Rollout + Coverage-Gate. |
| EXT-001 | BESTÄTIGT | `memory/injection_policy.py:125-139` bare `set_tenant`, `enabled is None → True`; `memory/migrations/0002…:31-35` fail-closed | GUC armen + expliziten `tenant_id`-Filter. Zwilling `application/preference_service.py:171` separat erfassen. |
| L1-006 | BESTÄTIGT | `baseline/version_reconstructor.py:274-296` `AuditLogEntry.unscoped` ohne Tenant/Content-Type | `tenant_id` Pflichtparameter + Content-Type-Diskriminator; Caller anpassen. |
| EXT-006 | **ANPASSEN** | `se_metrics/aggregator.py:393,409-424` kein `finally`, kein GUC; Gegenbeispiel `:144/189-190` | Plan-Fix „Tenant-Filter ergänzen" greift zu kurz — der Filter ist bereits thread-local-gescoped. Korrekt: `set_request_tenant` + Restore. |

**Wichtige Korrektur:** Der Meta-Review-Vermerk „alle RLS-abhängigen Findings seien conditional on rollout"
ist **falsch**. Nur die 7 staged Tabellen sind permissiv; APP-001/EXT-001/EXT-006 betreffen
unbedingt fail-closed Policies und sind auch im Default-Deployment echte Fehler.

**Test-Voraussetzung:** Der Test-Stack läuft als Superuser (`testing/docker-compose.test.yml:95,153`)
und umgeht RLS → für belastbare Red/Green-Nachweise ist ein App-Rollen-/Two-Tenant-Fixture Teil des
Schnitts.

## S0.3 — Datenintegrität

| Finding | Entscheidung | Beleg | Anpassung |
|---|---|---|---|
| L0-002 | **BESTÄTIGT — höchste Priorität** | `persistence/migrations/0141_backfill_allocations.py:34,43` `reverse_sql = DELETE FROM pl_allocation;` | `reverse_sql=migrations.RunSQL.noop` + Docstring „one-way door" + Guard-Test. Provenienz-Scoping unmöglich (Drafts ununterscheidbar). |
| L0-001 | BESTÄTIGT | `audit/archive.py:329-358` roher DELETE; `0002_append_only_trigger.py:32-46` BEFORE DELETE-Trigger | `AuditEntry` ist **nicht** nativ partitioniert → kein `DROP PARTITION`; SECURITY-DEFINER-Maintenance-Funktion, die nur diesen Trigger transaktional deaktiviert. **Nicht** `session_replication_role=replica`. |
| L0-003 | **ANPASSEN** | `mcp_server/tools/base.py:386-450` bewusstes Best-Effort (Default `fail_closed=False`) | Pauschales Re-raise bricht den Vertrag. Governance-Call-Sites auf `fail_closed=True` + Op-Vocabulary-Drift-Test. |
| L1-001 | BESTÄTIGT + Zusatz | `version_reconstructor.py:137,145,184,219-220`; `diff_engine.py:43-60`; `state_capture.py:262` | State-first aus `BaselineDeltaIndexEntry.state`; **zwingend** `baseline_id` in den `LruPayloadCache`-Key (`:48-81`), sonst Kollision bei gleicher Artifact-Version. |
| L1-002 | BESTÄTIGT | `trace_link_manager.py:390,394,617` ungelockte Snapshots; Vorbild `lifecycle_manager.py:245-287` | Advisory-Lock-Helper nach `persistence/` heben (nicht aus `application/import_idempotency.py` importieren — ADR-01), in create/batch_create/update/delete vor dem Read. Reproduzierbar mit CR-08-Concurrency-Test-Muster. |
| L1-003 | BESTÄTIGT (latent) | `trace_link_manager.py:504-521` nur Enum-Check; keine Produktionsaufrufer | Shared Validation aus `create()` in `update()`; Level-Recompute bei altem oder neuem Hierarchie-Typ — oder Methode entfernen. |
| L1-004 | BESTÄTIGT | `workflow/transition_validator.py:156-191` prozesslokal; `link_types/catalog.py:15-19,88-114` nutzt `cache_generation` | Eigener Namespace `"workflow"`, Generation bei Read vergleichen, Bump bei Write. |
| L1-005 | BESTÄTIGT (latent) | `lifecycle_manager.py:431,502-510` leere `allowed_roles` → jedermann durch | Leere Menge = Deny für Non-System-Caller; Rule-0-Agent-Guard; Docstring `workflow_facade.py:192` korrigieren. |
| L1-007 | **ANPASSEN** | `coverage_calculator.py:744-745`; `test_coverage_calculator.py:220-235` pinnt `references`-Verhalten bewusst | Pauschale Änderung überzeichnet. Nur `coverage_relevant=True`-Typen mit Evidence-Filtern begrenzen; gepinnten Test grün halten. |
| L1-008 | BESTÄTIGT | `traceability/models.py:16-18` „All 15" vs. 20 Builtins; `field_validation.py:27` vs. `:142`; `workflow_facade.py:192` | Drei Drift-Tests. |

### DECISION — S0.3-A: SECURITY-DEFINER-Purge-Funktion in `audit_ops` (nicht `public`)

**context:** Die Retention-Purge-Funktion (L0-001) muss `SECURITY DEFINER` sein und
vom Tabellen-Owner ausgeführt werden — nur dieser darf
`ALTER TABLE public.audit_entry DISABLE TRIGGER ...`. Der Migration-Runner ist
der Superuser, daher ist der Definer superuser-owned.

**choice:** Die Funktion liegt im eigens angelegten Schema `audit_ops`, nicht in
`public`. EXECUTE wird auf die `archiver`-Rolle beschränkt; das `app`-Role erhält
die Capability über explizite, cluster-weite Membership.

**alternatives:**
- Funktion in `public` **abgelehnt**: der #1180-Inventory-Guard
  (`persistence/tests/test_definer_owner_role_1180.py`) enumeriert *alle*
  `SECURITY DEFINER` in `public` und verlangt, dass deren Owner
  `DEFINER_DB_ROLE` (non-superuser, `NOT rolsuper`) ist. Ein superuser-ownter
  Definer in `public` würde diesen Guard brechen.
- Owner `DEFINER_DB_ROLE` statt Superuser **abgelehnt**: dieser Rolle fehlt die
  Tabellen-Owner-Berechtigung für `DISABLE TRIGGER`; der Zweck des Definers
  (gezieltes Umgehen nur des Append-Only-Triggers) wäre hinfällig.

**consequences:** Die Funktion ist bewusst *nicht* Teil der #1180-Inventarliste —
eine bewusste, hier dokumentierte Abweichung, **kein Review-Bypass**. Da das
`app`-Role die `archiver`-Rolle erbt, ist der arbitrary-cutoff-Aufruf eine
elevated capability; sie wird in der Funktion selbst durch eine
Cutoff-Untergrenze (30 Tage) begrenzt (Migration `audit/0020`). Sowohl die
`archiver`-Rolle als auch die Membership sind cluster-weite Katalogobjekte und
werden auf Reverse bewusst **nicht** entfernt.

**design_vs_speed:** Das eigene Schema kostet eine zusätzliche Migration plus
Dokumentationsaufwand, zahlt sich aber sofort aus: der #1180-Guard bleibt
aussagekräftig (kein `public`-Definer ohne Non-Superuser-Owner) und der
Privilegienpfad bleibt in einer einzigen, prüfbaren Funktion gebündelt.

**Kein S0.3-Finding ist durch E2 blockiert** — die RLS-Korrektur verschärft L0-002 sogar.

## S0.4 — Release-Gates & Lock

| Finding | Entscheidung | Beleg | Anpassung |
|---|---|---|---|
| OPS-001 | **KEIN PROBLEM (False Positive)** | Runtime-Repro am exakten Digest `nginx:1.31-alpine@sha256:785835ea…`: `/usr/bin/curl` vorhanden, Healthcheck-Command exit 0, `healthy`. Der „ships neither nginx nor curl"-Kommentar gilt nur für das Dev-Vite-Image. | **Als `closed as not a problem` dokumentieren**, mit Datum, Digest und Repro-Kommando. Keine Remediation. Shipped-Image-Health-Smoke trotzdem als positives Guard sinnvoll. |
| OPS-002 | BESTÄTIGT | `docker-publish.yml:54-57` needs nur `ci`; `playwright.yml:3-9` kein `workflow_call`; `ci.yml` ohne E2E-Job | `workflow_call` + Aufruf in Gate-Kette. **Zuerst E2E-Skips bereinigen** (18 `test.skip`-Failure-Pfade), sonst False Assurance. |
| OPS-004 | BESTÄTIGT | `docker-publish.yml:57` `secrets: inherit`; `ci.yml:221,264` nutzt nur `FIELD_ENCRYPTION_KEY`, deklariert aber keine `workflow_call.secrets` | Explizites Mapping **und** Deklaration im selben PR, sonst brechen Backend-Tests. |
| DEP-001 | BESTÄTIGT (HIGH→MEDIUM) | `requirements.lock:6,16` CPython 3.12 vs. `backend/Dockerfile:8,63` 3.15; vier Pins unter Floor; `pytest-xdist`/`execnet` fehlen | Regeneration mit echtem Runtime-Interpreter nach `backend/REGENERATING_LOCK_FILE.md`. Nur SBOM-/CVE-Triage betroffen, kein Runtime-Drift. |
| DEP-002 | **ANPASSEN — Plan-Fix ist falsch** | `ci.yml:301-307` hartkodierte Floors 5.2.17/9.1.1 vs. `requirements.txt:39,78` 6.1.3/9.2.0 | „Floors aus `requirements.txt` ableiten" macht das Gate **tautologisch** (Floor == Manifest ⇒ nie rot). Korrekt: unabhängige CVE-Floor-Single-Source, separat `manifest ≥ floor` und `lock konsistent` prüfen. |
| DEP-004 | BESTÄTIGT | `ci.yml:982,1027` nginx 1.27 vs. `frontend/Dockerfile:36` 1.31; Kommentar `:948-949` behauptet fälschlich identischen Digest | Shared Pin aus dem Dockerfile-FROM ableiten, Digest-Gleichheit in CI asserten. |

## Umsetzungsreihenfolge (aus den Gates)

1. **S0.3-A** (L0-002 → L0-001 → L1-001 → L1-002), Review durch `database-engineer`.
2. **S0.4** ohne OPS-001, mit DEP-002-Alternativdesign; OPS-002 erst nach Skip-Cleanup (S4.3) oder mit Zero-Skip-Assertion.
3. **S0.1** Scanner-Schnitt (SEC-006 + OPS-003 + SEC-007) vor dem externen History-Rewrite.
4. **S0.2** APP-001 → EXT-001 → EXT-006 → L1-006 → SEC-002 (E2-Entscheidung).
5. **SEC-001** Rotation/Rewrite: extern, nur nach Owner-Freigabe.
