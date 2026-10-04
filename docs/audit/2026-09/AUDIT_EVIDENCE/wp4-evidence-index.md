---
type: EVIDENCE
scope: wp4-evidence-index
status: success
date: 2026-09-29
author_agent: data-engineer
---

# WP-4 Evidenz-Index

## Dateien

| Datei | Inhalt | Kernaussage |
|---|---|---|
| `wp4-link-type-4level-matrix.md` | Verifizierte Link-Typ-Zahl, 4-Ebenen-Matrix, Tenant-Extensibility, Regeldurchsetzung | **11** Typen; Primärkatalog auf allen 4 Ebenen konsistent; 3 abweichende Hierarchie-Listen; 3 Validierungs-Bypässe |
| `wp4-state-bypass-inventory.md` | **Kernstück.** Alle `current_state`-Schreibstellen, CR-08-Verifikation, Terminalzustände | **4** Bypass-Pfade; CR-08 **WIDERLEGT** |
| `wp4-preset-hardcoding-inventory.md` | 12 Preset-Achsen, Zählung, Live-Wirkungsnachweis | 7 datengetrieben / 5+ hartkodiert in 6 Modulen; `stage_mandatory` ohne Konsument |
| `wp4-bootstrap-fieldkind-proof.md` | Codepfad-Beweis `--reset` / `kind`, Idempotenz, Transaktion, Rollback | **Prämisse #1112 BESTÄTIGT**; dreifache Sperre |
| `wp4-constraints-and-migrations.md` | Constraint-Lücken, Migrationskette, Tenant-Isolation | 26/44 Tabellen ohne `workspace_id`-FK; 2 live Orphans; **0** `.raw()` |
| `wp4-baseline-and-artifact-model.md` | 3 Scopes, Scope-Trennung, 3 Typ-Registries | Scopes konsistent, `global` ungenutzt; DiffEngine **BLOCKED** |

## Messumgebung

| Punkt | Wert |
|---|---|
| Branch | `chore/system-audit-2026-09` (== main @ `abd61aed`) |
| Commit | `75beb750` (WP-2) |
| Backend | `http://localhost:8001` (Container `ai-native-reqflow-poc-backend-1`, Up 7 h, healthy) |
| PostgreSQL | 16.15, `pgvector/pgvector:pg16`, DB `reqflow` |
| Migrationen | 294, neueste `persistence.0102_adr_deciders_issue_assignee_artifact_stakeholder` |
| Tenants | 6 (1 mit Daten: `Demo Tenant` = 401 Workspaces; 3 mit leeren globalen Katalogen) |
| Artefakte | 3062 (`pl_artifact`) |
| TraceLinks | 2099 |
| Workspaces | 401 |
| Zustandszeilen | 3316 `we_item_state` / 175 `we_history_entry` |
| Baselines | 38 (17 document, 21 project, **0 global**) |
| Link-Typ-Katalog | 44 global / 4419 workspace (402 Workspaces, davon 1 Orphan mit 8 Keys) |
| Attribut-Katalog | 132 global (11 Typen × 3 Presets × 4 Tenants) / 421 workspace (268 Workspaces, 8 Typen) |
| Rigor-Verteilung | 89 extended / 311 standard / 1 ohne Config / **0 minimal** |
| RLS | 71 Policies auf 71 Tabellen; 29/31 `pl_*` |

## Durchgeführte Operationen

**Ausschließlich lesend:**

- `SELECT` (aggregiert) gegen `reqflow` via `docker exec … psql -At -F"|"`
- `information_schema`-, `pg_constraint`-, `pg_policies`-, `pg_class`-, `pg_attribute`-Katalogabfragen
- `GET http://localhost:8001/api/schema/` (read-only, 613 769 Bytes, lokal zwischengespeichert)
- `POST /api/v1/auth/login/` (admin/admin12345) + 4 read-only GETs
- `rg` / `read` / `grep` gegen das Arbeitsverzeichnis
- `git log` / `git branch` (read-only)

**Ausdrücklich NICHT:**

- Keine Migration (`migrate`, `makemigrations`, `showmigrations`, `sqlmigrate`)
- Kein `pytest`, kein `npm test`, kein E2E-Lauf
- Kein INSERT / UPDATE / DELETE / DDL / TRUNCATE
- Kein `bootstrap_attribute_definitions`, kein `seed_demo`, kein `seed_*`
- Keine Code-Änderung
- `.kimi-code/` nicht angefasst

**Reads, die 5xx/404 waren** (transparent protokolliert, kein Finding daraus abgeleitet):

- `GET /api/v1/openapi/` → 404 (die Schema-Route ist `/api/schema/`, `urls.py:35`)
- `GET /api/v1/presets/`, `/presets/feature-flags/`, `/workspace-preset/` → 404 (existieren nicht)
- `GET /api/v1/workspaces/{id}/preset/` → **405 Method Not Allowed** (nur POST/PATCH — ein
  read-only Preset-Abfrage-Endpunkt existiert nicht; der Wirksamkeitsnachweis in
  `wp4-preset-hardcoding-inventory.md` §3 musste deshalb über
  `GET /api/v1/workflow-defaults/{item_type}/{preset}/` geführt werden)

## Nicht verifizierbar (BLOCKED, ausdrücklich kein PASS)

| # | Punkt | Grund |
|---|---|---|
| 1 | **Diff-Engine-Korrektheit** | Braucht zwei Snapshots + Mutation. `CR-16` unbestätigt. |
| 2 | `migrate` auf frischer DB | Auftragsverbot. |
| 3 | `migrate` auf gefüllter DB / Reversibilität | Auftragsverbot. |
| 4 | **Ursache** der 99 getaggten TestCase-Artefakte | Restore vs. Reseed nicht read-only unterscheidbar. Der *Zustand* ist gemessen, die *Ursache* ist Hypothese. |
| 5 | Warum 134/401 Workspaces keine Attribut-Definition haben | Provisioning-Lücke oder bewusster Auslass — read-only nicht entscheidbar. |
| 6 | Ob die 4 Bypass-Pfade in der Praxis ausgeführt wurden | Kein Log-Zugriff auf historische Requests; 0 `refines`/`satisfies`/`realizes`-Links legen nahe, dass die Paar-Prüfung bisher nichts verhindern musste. |
| 7 | `MINIMAL`-Preset-Pfade | 0 Workspaces auf `minimal` — alle 5 `minimal`-Zweige ungetestet auf Live-Daten. |
| 8 | Tenant-Isolation unter der **App-Rolle** | `CR-02` nennt das; WP-1c/WP-1d haben es behandelt, hier nicht wiederholt (kein neuer Befund, kein Duplikat). |
| 9 | `.reqif`-Import mit manipuliertem Inhalt | Würde Daten mutieren. Die Bypass-Wirkung ist **statisch** belegt (`reqif_import_service.py:886-897`), nicht dynamisch. |
