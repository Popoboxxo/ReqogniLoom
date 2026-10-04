---
type: REVIEW
scope: audit-review-corrected-top
status: final
date: 2026-10-01
author_agent: documenter
branch: chore/audit-review-2026-09
source:
  - docs/audit/2026-09/review/AUDIT_REVIEW_FINDINGS.md
  - docs/audit/2026-09/review/AUDIT_REVIEW_METHOD.md
  - docs/audit/2026-09/review/evidence/REVIEW_WP1A.md
  - docs/audit/2026-09/review/evidence/REVIEW_WP1B.md
  - docs/audit/2026-09/review/evidence/REVIEW_WP1C.md
  - docs/audit/2026-09/review/evidence/REVIEW_WP1C_SUPP.md
  - docs/audit/2026-09/review/evidence/REVIEW_WP1D.md
  - docs/audit/2026-09/review/evidence/REVIEW_WP2.md
  - docs/audit/2026-09/review/evidence/REVIEW_WP3.md
  - docs/audit/2026-09/review/evidence/REVIEW_WP4.md
  - docs/audit/2026-09/review/evidence/REVIEW_WP5.md
  - docs/audit/2026-09/review/evidence/REVIEW_WP6A.md
  - docs/audit/2026-09/review/evidence/REVIEW_WP6B.md
  - docs/audit/2026-09/review/evidence/REVIEW_LIVE_CRITICALS.md
---

# AUDIT_REVIEW_CORRECTED_TOP — korrigierte Top-Liste der echten ReqogniLoom-Probleme

> **Rolle dieses Dokuments.** Entscheider-Fassung der verifizierten Problem-Rangfolge
> und der vom Audit übersehenen Lücken. **Keine neue Fachanalyse** — aggregiert
> ausschließlich `AUDIT_REVIEW_FINDINGS.md` und die `REVIEW_*`-Evidenz.
> Schweregrade sind die **korrigierten** der Zweitprüfung, nicht die Register-Originale.

---

## 1. Korrigierte Top-Liste der echten ReqogniLoom-Probleme

Rangfolge nach Wirkung (Verfügbarkeit → Datenintegrität → Sicherheit → Funktionalität).
„Live" = am laufenden Stack reproduziert; „statisch" = Code-/Config-belegt (Live
durch Vorgabe „keine Datenmutation"/fehlenden Host blockiert).

| # | ID | Korr. Schwere | Wirkung (1 Satz) | Verifikation |
|---:|---|---|---|---|
| 1 | **AUD-030** | Critical | Bei Redis-Ausfall hängt **jeder** MCP-Request ohne Timeout (Client-Abbruch nach 8 s) — die „fail-open"-Drossel greift nicht gegen einen blockierenden Socket. | **live** BESTAETIGT |
| 2 | **AUD-221** | Critical | Der Rate-Limit-Zähler läuft **vor** der Authentifizierung und legt pro vorgestellter Credential einen Cache-Bucket an — 401-Requests füllen den Store. | **live** BESTAETIGT |
| 3 | **AUD-031** | Critical | `/health/` prüft Cache, Worker und Beat **nicht** — bei Redis-Ausfall meldet es weiter `200 ok` in 0,024 s und tarnt den Ausfall aus 1/2. | **live** BESTAETIGT |
| 4 | **AUD-222** | High | Die Workspace-Fence wird ausschließlich client-gesteuert (Query/Body) ausgelöst; Detailrouten ohne Workspace-Pfad filtern nur tenant- und id-skopiert — Bearer/API-Key-Clients können fremde Workspaces treffen. | statisch BESTAETIGT (live blockiert: Scoped-User/Mutation) |
| 5 | **AUD-071** | Critical | Der ReqIF-Import liefert **hart kodiert `success:true`**, obwohl die per-Objekt-Savepoint-Rettung unwirksam ist und Objektfehler auflaufen — ein gescheiterter Import wird als Erfolg gemeldet. | statisch BESTAETIGT (live: Mutation nötig) |
| 6 | **AUD-120** | Critical | Alle vier Celery-Queues binden an exchange/routing-key `default`; jede ungeroutete Task wird **4×** zugestellt und ausgeführt. | **live** BESTAETIGT |
| 7 | **AUD-123** | Critical | Das Restore-Skript wird **nie in den Container kopiert** (`/tmp/backup.*` existiert dort nie) — der dokumentierte Wiederherstellungspfad ist funktionslos. | statisch BESTAETIGT |
| 8 | **AUD-115** | Critical | Der Hermes-Plugin-Hauptpfad bricht mit `TypeError` (`', '.join(missing)` über Server-**Dicts**), der `except ReqogniLoomError` fängt ihn nicht — der Docstring „Never raises" ist gebrochen. | statisch BESTAETIGT |
| 9 | **AUD-270** | High | `audit.archive_lifecycle_manager` wird nie importiert/registriert (`autodiscover_tasks()` sieht nur `<app>/tasks.py`) — die monatliche Audit-Retention läuft nie. | **live** BESTAETIGT (`celery inspect registered` = 6 Tasks) |
| 10 | **AUD-281** | High | `Goal.sequence_number` wird als `MAX+1` ohne Lock gezogen und hat **kein** UNIQUE-Constraint (asymmetrisch zum Main-Goal) — Race auf doppelte Sequenznummern. | live BESTAETIGT (Constraint fehlt) |

**Nachgeordnet/unverändert wichtig:** **AUD-122** (Critical→High: `backup.sh`
toter Legacy-Pfad, kein aktiver Datenverlustpfad), **AUD-031/129**-Gesundheits-
Blindheit, **AUD-169** (GET mutiert), **AUD-168** (CAS-Blindstelle ohne
`version`-Bump), **AUD-055/057** (LLM-Retry-Amplifikation ×12; `decompose`-
Parser ungehärtet), **AUD-109** (Plugin erreicht Ziel-Workspace Rang 400/401 nie),
**AUD-160/162/175** (Presets nur teil-SSOT, `except: pass`-Fail-open).

---

## 2. Neu gefundene Audit-Lücken (`NEU-AUDIT-LUECKE`)

Klår als vom Audit **nicht** erfasste ReqogniLoom-Lücken markiert; Belege in den
jeweiligen `REVIEW_*`-Evidenzen.

| Kennung | Sev | Lücke | Evidenz |
|---|---|---|---|
| **NEU-AUDIT-LUECKE** | High | **Workspace-gefencete API-Keys werden auf REST nicht durchgesetzt.** `workspace_ids` wird nur in MCP (`tool_registry.py`) geprüft; auf `rest_api/` und in `auth_enforcer.py` wird `api_key_workspace_ids` **nirgends** konsumiert. Ein auf WS A beschränkter Agent-Key kann über REST-Detailrouten in WS B agieren. | WP-6a N2 |
| **NEU-AUDIT-LUECKE** | Medium/High | **`as_webhook_subscription.secret` im Klartext + Admin-Cross-Tenant.** `secret` ist ungehashter `CharField`, Tabelle ohne RLS, und `WebhookSubscriptionAdmin` hat weder `get_queryset`-Tenant-Filter noch `readonly_fields` → für **jeden** Tenant im Django-Admin sichtbar/editierbar; kombiniert mit offenem `/admin/` (AUD-223) HMAC-Fälschung möglich. | WP-6a N1 |
| **NEU-AUDIT-LUECKE** | Medium | **Beat-Healthcheck ist `pgrep`-blind.** `pgrep -f 'celery.*beat'` ist grün, obwohl Beat (bei 97 % Memory-Limit) stundenlang nichts dispatcht; weder Log noch Healthcheck liefern eine Funktionsaussage. | Live N2 / WP-1c-Supp |
| **NEU-AUDIT-LUECKE** | Medium | **Per-Credential-Bucket-Amplifikation.** `McpApiKeyRateThrottle(credential or "")` erzeugt für **jede** (auch ungültige) Credential einen eigenen Bucket (`throttle_mcp_key_<sha256[:32]>`); Angreifer erzeugen unbegrenzt Cache-Keys gegen `maxmemory 256mb`/`noeviction`. | Live N1 |
| **NEU-AUDIT-LUECKE** | Medium | **Tool-Zahl 218 vs. 219.** `.meta-config/project.yaml` (und generierte Agent-Prompts) nennt „35 Präfixe / **218** Tools", das Manifest `tool_count=219` — dritte Doku-Drift neben AGENTS.md (215/31) und README (25/35). | WP-1a N1 |
| **NEU-AUDIT-LUECKE** | High | **Idempotenz der realen Outbox-Abonnenten ungeprüft.** `application.event_bus` fordert at-least-once; die Abonnenten `ContextGraphProjector`, `MemoryProjector`, `WebhookDispatcher` wurden nie auf `event_id`-Dedup geprüft — Doppelzustellung könnte doppelt schreiben. | WP-6b N1 |
| **NEU-AUDIT-LUECKE** | Medium | **Optimistic-Locking nur auf Sonderrouten umgangen.** Die generische Transitions-Route ist geschützt; `/adrs/{pk}/supersede/` und `/change-requests/{pk}/transition/` akzeptieren kein `expected_version` (Last-writer-wins). | WP-6b N2 |
| **NEU-AUDIT-LUECKE** | Low/Medium | **LLM-Default-Falle im Detail:** fehlerhafter Env-Variablenname in der Ollama-Fehlermeldung (`OLLAMA_BASE_URL` statt `LLM_BASE_URL`); stiller Env-Fallback bei DB-/RLS-Ausfall; zweiter `gpt-4`-Default (Azure) unbenannt; ungeschütztes `int()`/`float()`-Env-Parsing. | WP-1b N1–N5 |
| **NEU-AUDIT-LUECKE** | Low | **Weitere:** `preset_guard` substituiert Tenant-ID als Workspace-ID; `UserViewSet.list` N+1 ohne Pagination; BOM-Wurzelort in der View; `refines` aus 4 Hierarchie-Definitionen ausgeschlossen; Minimal-Workflow nie live getestet. | WP-6a N3, WP-1d, WP-4 |

---

## 3. Top-Fehlbefunde des Audits

| ID | Verdikt | Korrektur / Begründung |
|---|---|---|
| **AUD-121** | **FALSCH** | Headline „Beat dispatcht nie" ist live widerlegt: DB-Zähler schreiten voran, Worker führt `dispatch_outbox_events` alle 5 s aus; „0× Sending due task" ist ein **Log-Artefakt**. Rest (a) Healthcheck, (b) Duplikat 125/270 bleibt (→ Low). |
| **AUD-042** | **FALSCH** | Multi-Interview ist über MCP startbar (`session_kind="multi"`, seit 2026-08-25); das Zitat `interview.py:181-202` ist `formalize`, nicht `start` — Aussage **und** Ort falsch. |
| **AUD-283** | **FALSCH** | Verwechslung zweier gleichnamiger `DomainEventBus` (in-process `audit.events` vs. Transactional Outbox `application.event_bus`); der Audit-Writer wird synchron direkt geschrieben, die behauptete Redelivery-Duplikat-Kette existiert nicht. |
| **AUD-204** | **FALSCH** (Register-Sync) | Master-Zeile behauptet weiter „nicht reproduzierbar", obwohl der WP-Report die Aussage zurücknimmt und 121/270 bestätigt — stale Registerzeile, kein Analyse-Fehler. |
| **AUD-101** | ÜBERZOGEN | „VS-Code-Schema statt Hermes-Vertrag" verwechselt Desktop-Plugin-Manifest (`hermes-plugin.json`, belegt am Referenzplugin) mit Agent-Dashboard-Manifest (`manifest.json`) → High → **Low**. |
| **AUD-110** | ÜBERZOGEN | Der Server antwortet bei falschem `artifact_type` mit klarem `400 VALIDATION_ERROR` — Doku-/UX-Fehler → High → **Medium**. |
| **AUD-117** | ÜBERZOGEN | Fehler ist im `connected`-Zustand unsichtbar (stiller Button-Fehlschlag), aber ohne Daten-/Sicherheitsfolge → High → **Medium**. |
| **AUD-180** | ÜBERZOGEN / Flaggschiff widerlegt | Zähler 26 korrekt, aber `pl_artifact` **und** `pl_requirement` **haben** einen `workspace_id`-FK — die Prämisse „DB schützt nichts" und die Beispiele sind falsch → High → **Medium**. |
| **AUD-129** | TEILWEISE | „`degraded` liefert HTTP 200" ist gegen den Code **falsch** (`status="degraded"` setzt immer 503); der echte Defekt ist die fehlende Cache-/Worker-/Beat-Probe. |
| **AUD-345 / AUD-346** | Duplikate | 345 = **Duplikat AUD-123** (Restore-Skript), 346 = **Duplikat AUD-052** (identische `providers.py:1080`); beide erhöhen die Critical-Zählung ohne neuen Defekt. |
| **AUD-222** | TEILWEISE (Zitat) | Kern bestätigt, aber zwei Audit-Belege irreführend: die Regressionssuite existiert doch; `preset_guard` ist nicht fail-open (Tenant-ID-Fallback). |

*(Weitere Schweregrad-Korrekturen: 034, 056, 060, 061, 062, 063, 065, 066, 077,
122, 130, 134, 142, 147, 161, 228, 273, 282, 327 — siehe `AUDIT_REVIEW_FINDINGS.md` §1.3.)*

---

## 4. Was das Audit übersehen hat (Lückenliste konsolidiert)

**A. Neue Produktdefekte** — siehe §2 (Webhook-Secret-Admin-Pfad,
REST-Workspace-Fence, Outbox-Idempotenz, Beat-Blindheit,
Bucket-Amplifikation, LLM-Fallen, `preset_guard`, N+1, `refines`).

**B. Prozess-/Register-Lücken** (aus WP-Methodenkritik):
- **Register-Sync 204** — Korrektur existiert nur im WP-Report, nicht in der
  kanonischen Master-Zeile.
- **Doppelzählung 345/346** — dieselben Defekte wie 123/052, aber als eigene
  Criticals geführt.
- **Stale-Zahlen** — `AUD-193` nennt 511 statt kanonisch 443; `AUD-348` baut auf
  112 statt 116.
- **Etiketten-Verwechslung** — `AUD-192` „3,6 % der Tests" ist die Zahl
  eindeutiger REQ-IDs, nicht der Testdefinitionen (31,9 %).
- **`AUD-197`-Checkbox-Behauptung** — 3 der 11 Abnahmeberichte enthalten
  Checkboxen.
- **`AUD-083`-Wurzelort** — BOM-Ursache liegt in der View (`decode("utf-8")`),
  nicht nur im Service.
- **Tote Querverweise** — 349 → widerlegtes AUD-070; 348 → 112.

**C. Messmethodik-Lücken** (WP-4/WP-3):
- FK-Constraints über Namensgleichheit statt `pg_constraint.conkey/confkey`
  aufgelöst → „DB schützt nichts"-Aussagen teils falsch.
- Audit-Snapshot (Migrations-/Datenstand) nicht festgehalten → Absolutzahlen
  (3062 vs. 3442 Artefakte, 44 vs. 42 Tabellen) nicht reproduzierbar.
- i18n-Phantom-Key `permissionMatrix.capability.` zählt die Baseline 116 um ≥1 zu
  hoch; „41 Dateien" tatsächlich 34.
- E2E-Selektor-Liste teils phantomhaft (`login-form`, `main-header`,
  `todo-item` existieren nicht); nur 3 `visibility-*-diagrams` nachweislich stale.
- Ungetestete a11y-Lücke bei AUD-005 (Select-accessible-names).

**D. Blindstellen ohne Produktbezug:** Audit-eigene Evidenz als „Beweis" nur
eingeschränkt zulässig — die Review musste mehrfach Log-Artefakte (121) und
Snapshot-Werte (130/132/147) verwerfen.

---

## 5. Was das Audit richtig machte (kurz)

- **Live-Reichweite:** Zehn Kern-Behauptungen wurden am laufenden Stack
  gegengeprüft; 030/031/073/074/120/221 und (DB-gestützt) 281/285/287/288 halten
  live — das Audit adressiert reale Betriebszustände.
- **AUD-120 gestärkt:** Die 4-fache Celery-Zustellung ist mit projekt-eigener
  Celery/kombu-Version isoliert und live exakt reproduziert.
- **AUD-222 und AUD-071 korrekt:** Beide tragen statisch, obwohl live nicht
  prüfbar (Scoped-User/Mutation) — die Code-Ursachen sind zweifelsfrei.
- **WIDERLEGT-Disziplin:** Der Audit zog vier Befunde selbst zurück (070, 143,
  021, 022/166) und markierte Unentscheidbares sauber als BLOCKED/NICHT
  VERIFIKABAR (190, 205) — methodisch vorbildlich.
- **Kanonische Zahlen präzise:** Die belastbaren Kernzahlen (401 Workspaces,
  200 Items/54 KB, 835/511/324, 116, 219, 443) wurden exakt reproduziert.

---

*Entscheider-Fassung, erstellt durch `documenter` am 2026-10-01. Aggregation der
Review-Evidenz; keine neue Fachanalyse, kein Produktcode geändert, kein Push,
keine Secrets (nur maskierte Referenzen). `.kimi-code/` und `stack-seeds.md`
unangetastet.*
