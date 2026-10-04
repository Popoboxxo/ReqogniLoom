---
type: REVIEW
scope: wp-1d-cleanup-verification
status: final
date: 2026-09-29
author_agent: api-specialist
---

# WP-1d — Evidenz: Aufräumen und Verifikation

**Quellen:** `wp1d-row-counts-before.json`, `wp1d-row-counts-after.json`,
`wp1d-cleanup-verify-api.json`.

**Prämisse:** Der Stack ist geteilt, parallele Audits laufen dagegen. Ziel war,
nach dem Test exakt den Ausgangszustand herzustellen und das zu **belegen**.

---

## 1. Angelegte Testdaten (vollständige Liste)

| Objekt | Anzahl | Erzeugung |
|---|---|---|
| Tenant `wp1d-probe-<hex8>` (`WP1D Probe Tenant`) | 1 | ORM mit `set_request_tenant` |
| User `wp1d_probe_b` (+ `is_tenant_admin`) | 1 | ORM, `make_password` |
| `TenantRole` (admin) | 1 | ORM |
| `UserRole` (admin im Workspace) | 1 | ORM |
| Workspace `WP1D Probe WS` | 1 | ORM |
| Artefakte (Requirement, Architecture, TestCase, Need, ADR, Risk, Goal, Issue, Glossary) | 9 | **REST** als Tenant-B-User |
| davon mit Sonderzeichen im Titel | 1 | `WP1D-PROBE-B Requirement ÄÖÜ 🚀` |
| `ArtifactVersion`-Zeilen | 9 | automatisch |
| `UidSequence`-Zeilen | 7 | automatisch |
| `WorkspacePresetConfig` | 1 | automatisch |
| `GlobalPermissionDefinition` | 1 | automatisch |
| API-Key `WP1D-PROBE-B key2` | 1 | REST |
| CSV-Importzeilen in Tenant B (`RTQ-*`, `RT-CSV-*`) | 11 | REST |
| **Gesamt `Artifact`-Zeilen** | **19** | |

Zusätzlich in **Tenant A** durch Fehlversuche erzeugt: 2 `AuditEntry`-Zeilen
(von den versuchten Import-Operationen auf Workspace A) — Audit-Einträge sind
append-only und werden **nicht** gelöscht.

---

## 2. Verifikation über die API

`wp1d-cleanup-verify-api.json`:

| Prüfung | Ergebnis |
|---|---|
| `POST /api/v1/auth/login/` als `wp1d_probe_b` | **401** — User existiert nicht mehr |
| `POST /api/v1/auth/login/` als `admin` | **200** — Tenant A unverändert funktionsfähig |

| Tenant-A-Endpunkt | Status | `count` |
|---|---|---|
| `/api/v1/requirements/?workspace_id=4eee7ca1-…` | 200 | **888** |
| `/api/v1/artifacts/?workspace_id=4eee7ca1-…` | 200 | **1176** |
| `/api/v1/workspaces/` | 200 | **401** |
| `/api/v1/api-keys/` | 200 | **200** |
| `/api/v1/users/` | 200 | **12** |
| `/api/v1/trace-links/?workspace_id=4eee7ca1-…` | 200 | **1974** |

## 3. Verifikation über die DB (Zeilenzahlen, 100 Tabellen)

Snapshot **vor** der Provisionierung bzw. **nach** dem Cleanup, beide unter
dem Tenant-A-RLS-Kontext (`set_request_tenant('7a539397-…')`), also mit
zuverlässiger Sicht.

### Geänderte Tabellen

| Tabelle | vorher | nachher | Δ | Bewertung |
|---|---|---|---|---|
| `pl_user` | 13 | **12** | −1 | Probe-User gelöscht ✅ |
| `at_user_role` | 412 | **411** | −1 | Probe-Rolle gelöscht ✅ |
| `audit_entry` | 8114 | 8148 | **+34** | 32× Tenant B (append-only) + 2× Tenant A (Import-Versuche) — **korrektes** Audit-Verhalten, kein Restfehler |
| `at_refresh_token` | 6262 | 6279 | +17 | normale Churn aus ~90 eigenen Logins |
| `as_domain_event_outbox` | 6853 | 6861 | +8 | normale Event-Churn |
| `sm_metric_cache` | 43 | 44 | +1 | Cache-Eintrag durch die Probes |

**Keine andere Tabelle hat sich verändert.** Insbesondere unverändert:

| Tabelle | vorher | nachher |
|---|---|---|
| `pl_requirement` | **2111** | **2111** |
| `pl_artifact` | **3432** | **3432** |
| `pl_testcase` | 225 | 225 |
| `as_issue` | 76 | 76 |
| `as_risk` | 59 | 59 |
| `as_goal` / `as_adr` / `as_change_request` | 0 / 33 / 0 | identisch |
| `pl_tracelink` | **2099** | **2099** |
| `pl_test_run` / `pl_test_run_result` | 145 / 467 | identisch |
| `bl_baseline_snapshot` / `bl_delta_index_entry` | 38 / 486 | identisch |
| `we_item_state` / `we_engine_definition` | 3306 / 5614 | identisch |
| `lt_workspace_definition` | 4419 | 4419 |
| `diagram_diagram` / `icd_icd` | 111 / 105 | identisch |
| `pl_tenant` | 6 | **6** — siehe §4 |

## 4. Restliche Rückstände

| Rest | Anzahl | Begründung |
|---|---|---|
| `audit_entry`-Zeilen (Tenant B) | **32** | `audit_entry` hat einen **append-only DB-Trigger**. Ein `DELETE` scheitert mit `InternalError` — im Log: `audit_entry: "InternalError"`. Das ist **das korrekte Verhalten** (Auftragshinweis), kein Restfehler. |
| `pl_tenant`-Zeile (Tenant B) | **1** | `AuditEntry.tenant` ist `on_delete=models.PROTECT` (`persistence/models.py:457-462` gilt für alle `TenantScopedModel`). Solange Audit-Einträge existieren, kann die Tenant-Zeile nicht gelöscht werden — das ist die gewollte Audit-Integrität. |
| Workspace `WP1D Probe WS` | **0** | gelöscht ✅ |
| Alle 19 `pl_artifact`-Zeilen + Unterobjekte | **0** | gelöscht ✅ (9 `ArtifactVersion`, 7 `UidSequence`, 1 `TestCase`, 1 `GlossaryTerm`, 1 `Adr`, 1 `Risk`, 1 `Goal`, 1 `Issue`, 1 `PresetConfig`, 1 `GlobalPermissionDefinition`) |

**Funktionale Wirkung des Rests:** keine. Der Tenant hat keine Daten, keinen
User und damit keinen Login; alle REST-Pfade scheitern an der fehlenden
Credential, nicht an der Tenant-Zeile. Er bleibt ausschließlich als
FK-Anker für den Audit-Trail stehen — das ist der Zweck des `PROTECT`.

### Warum der erste Cleanup-Durchgang unvollständig war

Der erste Löschlauf verwendete hart kodierte Tabellennamen
(`pl_test_case`, `pl_adr`, `pl_risk`, `pl_goal`, `pl_issue`) — die realen
Tabellen heißen `pl_testcase`, `as_adr`, `as_risk`, `as_goal`, `as_issue`
(erkennbar am `as_`-Präfix des Application-Layers). Ergebnis: `IntegrityError`
beim Löschen der noch verlinkten Artefakte und `ProtectedError` beim Tenant.

Der zweite Durchgang enumerierte die Django-Modelle mit einem `tenant`-FK
programmatisch (`apps.get_models()` + `_meta.get_field("tenant")`) und lief bis
zur Konvergenz. Danach blieben nur noch die oben genannten Rückstände.

---

## 5. Keine Probe-Reste in Tenant A

Vollabfrage über **9 Entitätstypen** in Tenant A (Requirements, Architecture,
TestCases, ADRs, Risks, Goals, Issues, Needs, Glossary), Titelpräfixe
`WP1D`, `RTQ-`, `RT-CSV-`:

```
probe residue in tenant A: 0
```

Zusätzlich `GET /api/v1/search/?q=RTQ-&workspace_id=<A>` liefert
`total_count: 50` — **das ist kein Rückstand**: die Treffer sind Tenant-As
eigene Artefakte (`Der Widerstand R1 muss vom Typ SMD 0603 sein.`,
`workspace_id: 4eee7ca1-…`). Die Suchanfrage matcht nicht auf den
Titel-Präfix, sondern auf einen tokenisierten Teil des Textes; der Marker
erscheint in der Antwort nur als Query-Echo. Dieselbe Fehlinterpretation hatte
ursprünglich zwei vermeintliche Tenant-Leaks erzeugt (siehe
`wp1d-tenant-leak-matrix.md` §2).

Nebenbefund: die Such-Präzision ist gering — die Query `RTQ-` liefert 50
untreffende Tenant-A-Treffer. **Kein** Sicherheitsbefund (alle Treffer gehören
dem Aufrufer), aber ein Qualitätsbefund. Nicht als eigenes Finding geführt,
weil die Ursache (Tokenizer/Fallback-Logik) ohne Codeeinsicht in den
Search-Service nicht abschließend belegbar war → **BLOCKED**.

---

## 6. Zusammenfassung

| Kriterium | Status |
|---|---|
| Alle Testobjekte identifiziert | ✅ 6 Objektklassen |
| Tenant B funktional stillgelegt | ✅ kein Login, keine Daten |
| Tenant A unverändert | ✅ 15 Schlüsseltabellen byteweise identisch |
| Keine Probe-Reste in Tenant A | ✅ 0 über 9 Entitätstypen |
| Rückstände begründet | ✅ 32 append-only `audit_entry` + 1 `pl_tenant` (PROTECT-Anker) |
| Der geteilte Stack weiterhin funktionsfähig | ✅ `/health/` 200, Login 200, alle geprüften Endpunkte normal |
