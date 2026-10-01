---
type: PLAN
scope: effort-estimates
status: final
author_agent: effort-estimator
date: 2026-10-01
source: [docs/audit/2026-09/review/IMPLEMENTATION_PLAN.md]
---

# EFFORT_ESTIMATES — Verbindliche Aufwandsschätzung zum Umsetzungsplan 2026-09

> **Gegenstand.** Schätzung aller **49 Arbeitseinheiten** aus
> `IMPLEMENTATION_PLAN.md` §4 (IDs `SEC-01…08`, `RES-01…08`, `DATA-01…10`,
> `INT-01…07`, `PLUG-01…05`, `DOC-01…06`, `SECTRACK-01…05`) in **Personentagen (PT,
> 1 PT = 8 h fokussierte Arbeit)** als **Spanne min–max** plus **T-Shirt-Size**
> (S/M/L/XL).
>
> **Rolle.** Diese Datei ist die von `IMPLEMENTATION_PLAN.md` §4 geforderte
> „verbindliche" Zahl und **Voraussetzung für den Start von W2**. Sie ist
> **Schätzung**, keine Zusage und kein Produktcode. Keine bestehenden Plan-/Code-
> Dateien wurden geändert, kein Git-Commit.

---

## 0. Methodik

- **Einheit der Schätzung:** min = optimistischer Fall (Zielverhalten erreicht,
  keine Überraschung), max = pessimistischer Fall (verdeckte Kopplungen,
  Migrationsdaten-Audit, Live-Setup-Mehrarbeit). Der **realistische** bzw.
  **Erwartungswert** ist der Mittelwert der Spanne (`(min+max)/2`); die Epic- und
  Gesamtsummen werden zusätzlich als Erwartungswert ausgewiesen.
- **Berücksichtigte Arbeit je Einheit:** Code-Fix, Tests (Regression rot-bewiesen
  nach Projekt-DoD), Doku/Frontmatter, **Live-Nachtest** (wo im Detailplan
  verlangt) und **ADR-Arbeit** (wo die Einheit eine ADR schreibt oder von ihr
  abhängt).
- **Buffer:** Die pessimistische Obergrenze enthält den Risikopuffer (≈ 1,3–1,5×
  über dem realistischen Wert) gemäß Schätz-Workflow.
- **LLM-Kalibrierung:** Laufendes Modell (`deepseek-v4.1-flash`) ist **keiner**
  der kalibrierten Tiers zugeordnet → neutraler Faktor **1,0×** (konservativ, keine
  Auf-/Abwertung). `rapid-prototyping`-DoD (`req-traceability=false`,
  `tests-required=false`) ist eingerechnet — Regressionstests bleiben dennoch pro
  Einheit Pflicht, da sie in der Detaildatei als Akzeptanz stehen.
- **Abkürzungen** in der Spalte „Aspekte": `CF` Code-Fix · `T` Tests ·
  `D` Doku/Frontmatter · `L` Live-Nachtest · `ADR` ADR-Arbeit/-Abhängigkeit.

---

## 1. Schätzungen je Arbeitseinheit

### Epic A — SEC (Security & Authorization)

| ID | PT-Spanne | Size | Aspekte | Treiber / Anmerkung |
|---|---|---|---|---|
| SEC-01 | 0.5–1.5 | S | ADR, D | ADR ii; Analyse von 3 Codeorten + `se-critic`-Review-Loop, Entscheidung ist User-Sache |
| SEC-02 | 2.0–4.0 | L | CF, T, L | objekt-abgeleiteter Workspace-Fence auf Detailrouten; Live-Nachtest Scoped-User; Kollateral-Regressionen |
| SEC-03 | 1.5–3.0 | M | CF, T, L | zentrale Fence in `RbacPermission`/Auth, `expires_at`/`workspace_ids` default-deny; Policy-Migrationsfenster |
| SEC-04 | 1.5–3.0 | M | CF, T, L | Admin-Gate + Brute-Force-Schutz + Tenant-`get_queryset` + Secret-Maskierung |
| SEC-05 | 0.25–0.75 | S | CF, T | tote CORS-Konfiguration: aktivieren **oder** entfernen |
| SEC-06 | 0.25–0.5 | S | CF, T | `NUM_PROXIES`/`USE_X_FORWARDED_FOR`; hängt an RES-02 |
| SEC-07 | 0.25–0.75 | S | CF, T | Fail-open sichtbar machen; Kopplung an RES-03 |
| SEC-08 | 1.5–3.0 | M | CF, T, D | CI-Supply-Chain: SHA-Pinning, SBOM/Signing, Staging-/Approval-Gate |

### Epic B — RES (Resilience & Health)

| ID | PT-Spanne | Size | Aspekte | Treiber / Anmerkung |
|---|---|---|---|---|
| RES-01 | 0.5–1.5 | S | CF, T, L | Cache-Timeouts + Live Redis-Stop (bounded `curl`) |
| RES-02 | 1.5–3.0 | M | CF, T, L | AuthN **vor** Throttle, Bucket-Amplifikation gegen `noeviction`; Live-`redis-cli --scan` |
| RES-03 | 2.0–4.0 | L | ADR, CF, T, L, D | ADR i + `/health/live`+`/health/ready` + Compose/CI-Gates; zu strikte Readiness ⇒ LB-Risiko |
| RES-04 | 1.5–3.0 | M | ADR, CF, T, L | ADR iv Celery-Topologie + `acks_late`; Live-`_kombu.binding`-Isolation |
| RES-05 | 1.0–2.0 | M | CF, T, L | Beat-Health funktionsbasiert (Dispatch-Age) + Memory-Limit; Schwellwert-Tuning |
| RES-06 | 0.5–1.5 | S | CF, T, L | Task-Registrierung + `celery inspect registered`; Retention-Trockenlauf |
| RES-07 | 1.5–3.0 | M | CF, T, D | Log-Level, `request_id` im Body, Metrics-Exporter; Log-Rauschen |
| RES-08 | 0.5–1.5 | S | CF, T | Keyset-Pagination statt Deep-Offset; `n_live_tup`-Evidenz korrigieren |

### Epic C — DATA (Datenintegrität & Recovery)

| ID | PT-Spanne | Size | Aspekte | Treiber / Anmerkung |
|---|---|---|---|---|
| DATA-01 | 1.5–3.0 | M | ADR, CF, T, L | ADR iii + atomarer Restore; Smoke 15/15; `REQ-L2-BL-011`-Status |
| DATA-02 | 1.5–3.5 | M | CF, D, L | Format-/Ortsvertrag, Off-Host, Retention, Verschlüsselung, Medien-Volume |
| DATA-03 | 2.5–5.0 | L | CF, T | **größte Einzelposition:** State-Bypass/Version-Bump über CSV/ReqIF/Interview/`force_transition`/2 Sonderrouten; CAS + 409 |
| DATA-04 | 0.75–1.5 | S | CF, T, L | `UNIQUE(lineage_id, seq)` + `select_for_update`; Migration + Bestandsdaten-Audit |
| DATA-05 | 0.5–1.5 | S | CF, T | Self-Link-Guard (App+DB) + `link_type`-CHECK |
| DATA-06 | 1.5–3.0 | M | CF, T, L | `we_item_state`-FK + State-CHECK; Datenmigration |
| DATA-07 | 1.5–3.5 | M | CF, T, L | RLS auf 4 `as_*`-Tabellen; Pre-Auth-Trennung = Outage-Risiko |
| DATA-08 | 0.5–1.5 | S | CF, T | TestCase-Tag-Migration + Frontend-Route |
| DATA-09 | 1.5–3.0 | M | CF, T | Outbox-Idempotenz 3 Abonnenten; Dedup-Fenster |
| DATA-10 | 1.5–3.0 | M | ADR, CF, T | ADR vi Preset-SSOT; Downgrade-Gate fail-closed statt `except: pass` |

### Epic D — INT (Externe Schnittstellen & LLM)

| ID | PT-Spanne | Size | Aspekte | Treiber / Anmerkung |
|---|---|---|---|---|
| INT-01 | 1.5–3.0 | M | ADR, CF, T, L | ADR v + `success`-Vertrag + wirksamer Savepoint; Live-ReqIF-Mutation |
| INT-02 | 1.5–3.0 | M | CF, T | Provider-Defaults, `azure` in Enum/REST/UI, Env-Typparsing, korrekter Env-Name |
| INT-03 | 1.5–3.0 | M | CF, T | Parser-Fallback, Retry-Amplifikation (12→4), Usage-/Mock-Trennung |
| INT-04 | 1.5–3.0 | M | CF, T, L | CSV-Dedupe/Idempotenz (`Idempotency-Key` o. fachlich), BOM, Fehlerursache |
| INT-05 | 1.0–2.5 | M | CF, T, L | 4 Listen paginieren; 404 statt 500; Client-Breaking |
| INT-06 | 1.5–3.0 | M | CF, T, D | OpenAPI-Fehlerkontrakt, `requestBody`, `cookieAuth`, ReqIF-XSD |
| INT-07 | 1.5–3.0 | M | CF, T | MCP-Fehlervertrag (int `code`), `params`-Validierung, Manifest-Drift |

### Epic E — PLUG (Native Plugins)

| ID | PT-Spanne | Size | Aspekte | Treiber / Anmerkung |
|---|---|---|---|---|
| PLUG-01 | 0.5–1.0 | S | CF, T | `_fmt_state`-`TypeError` + Fixture auf echten Serververtrag; POC-Isolation |
| PLUG-02 | 0.5–1.5 | S | CF, T, L | `next`/`count` in beiden Clients; Live gegen 401-Workspace |
| PLUG-03 | 1.0–2.5 | M | CF, T, L | `resulting_artifact_ids`, `count`, Whitelist, Error im `connected`-State |
| PLUG-04 | 1.5–3.0 | M | ADR, CF, T, D | ADR vii Versions-SSOT + Install-Doku; Host bleibt BLOCKED |
| PLUG-05 | 0.25–0.75 | S | CF, T | Timeout- vs. Connection-Fehler unterscheidbar |

### Epic F — DOC (Traceability / Doku / i18n / CI / UI)

| ID | PT-Spanne | Size | Aspekte | Treiber / Anmerkung |
|---|---|---|---|---|
| DOC-01 | 1.5–3.5 | M | D, ADR(teil) | Matrix kanonisch, ADR-Frontmatter-Lifecycle, `refines`; viele Fundstellen |
| DOC-02 | 1.5–3.0 | M | ADR, CF, T, D | ADR viii i18n-Ratchet; tote Keys 536; Migrationsfenster |
| DOC-03 | 1.0–2.5 | M | CF, D | Zahlen **messen** statt behaupten; Woodpecker-`pytest`; CI-Skip begründen |
| DOC-04 | 1.0–2.5 | M | CF, T, D | Skip-Link, accessible names, Fokus-Scroll, N+1; e2e+Vitest |
| DOC-05 | 0.5–1.0 | S | D | kanonische Tool-/Gruppen-Zahl (219/35) + Drift-Gate |
| DOC-06 | 0.5–1.5 | S | D | Register-Hygiene + Teil-FALSCH-Präzisierung; kein Code-Fix |

### Epic G — SECTRACK (Offener Secret-Vorgang, P0)

| ID | PT-Spanne | Size | Aspekte | Treiber / Anmerkung |
|---|---|---|---|---|
| SECTRACK-01 | 0.5–1.5 | S | CF, T, L, D | Rotation 9 Keys (1× `ff77bbd0…` + 8 `admin`), Expiry/Fence-Policy; Live-401+DB-Beleg |
| SECTRACK-02 | 0.5–1.5 | S | CF, L, D | History-Rewrite (Option A) + Bundle + SHA-Refs; **hohes Risiko** trotz kleinem PT (Push-Blocker) |
| SECTRACK-03 | 0.5–1.5 | S | CF, T, D | `gitleaks`-Gate + Custom-Regel `reqlo_[A-Za-z0-9]{40}` + Allowlist |
| SECTRACK-04 | 1.0–2.0 | M | CF, T, D | Evidenz-Redactor + Cleanup-Checkliste; Redactor-Unit-Test |
| SECTRACK-05 | 0.25–0.75 | S | CF, T | `${VAR:?}`-Pflichtvariablen statt Klartext-Deploy-Credentials |

---

## 2. Summen je Epic und Gesamtsumme

| Epic | Einheiten | Min (PT) | Realistisch (PT) | Max (PT) |
|---|---|---|---|---|
| A `SEC` | 8 | 7.75 | 12.1 | 16.5 |
| B `RES` | 8 | 9.0 | 14.3 | 19.5 |
| C `DATA` | 10 | 13.25 | 20.9 | 28.5 |
| D `INT` | 7 | 10.0 | 15.25 | 20.5 |
| E `PLUG` | 5 | 3.75 | 6.25 | 8.75 |
| F `DOC` | 6 | 6.0 | 10.0 | 14.0 |
| G `SECTRACK` | 5 | 2.75 | 5.0 | 7.25 |
| **Gesamt** | **49** | **52.5** | **≈ 83.75** | **115.0** |

- **Gesamtspanne: 52,5 – 115,0 PT** (Erwartungswert ≈ **84 PT**, ~16–17
  Personenwochen bei 1 Dev).
- **Wellenanteil (grob):** W1 (P0-Kern) trägt den größten Block (SEC-01/02/03,
  RES-01/02/03, DATA-01…04, INT-01, PLUG-01, SECTRACK-01…04) — ca. **30–60 PT**;
  W2 ca. **17–37 PT**; W3 (P2) ca. **9–18 PT**.
- **Optionale/isolierte Anteile:** `PLUG` (3,75–8,75 PT) ist ein POC-Modul ohne
  Server-Regression und könnte bei Bedarf am ehesten entkoppelt/entfallen.

---

## 3. Top-5-Aufwandstreiber

1. **DATA-03 — State-Bypass & Version-Bump (2,5–5,0 PT, L).** Größte
   Einzelposition: fünf+ Pfade (CSV, ReqIF, Interview-GET, `force_transition`,
   ADR-`supersede`, Change-Request-Transition) müssen CAS-korrekt bzw.
   nebenwirkungsfrei werden; jeder Pfad braucht einen eigenen Regressionstest.
2. **Tenant-/Workspace-Fence-Kaskade `SEC-02/03` + `DATA-06/07` (6,5–13,5 PT
   zusammen).** Cross-cutting AuthZ + DB-FK + RLS; ADR ii blockiert alle vier;
   höchstes Kollateral-Regressions- und Outage-Risiko (Pre-Auth-RLS).
3. **Health-/Recovery-Verträge `RES-03` + `DATA-01/02` (5,0–10,5 PT).** Zwei ADRs
   (i, iii) mit Live-Gates, Compose/CI-Kopplung, Restore-Smoke 15/15 und neuen
   Infrastruktur-Entscheidungen (Off-Host/Verschlüsselung/Medien).
4. **Celery-/Observability-Umbau `RES-04/05/07` (4,0–8,0 PT).** Topologie-ADR iv,
   Queue-Isolation, funktionsbasierter Beat-Healthcheck und Telemetrie; viele
   Live-Messungen (`_kombu.binding`, Memory, Dispatch-Age).
5. **CI-/Supply-Chain-Härtung `SEC-08` + `DOC-03` (2,5–5,5 PT).** SHA-Pinning,
   SBOM/Signing, Staging-Gate, Woodpecker-`pytest` und das „Messen statt
   Behaupten" der Test-/CI-Zahlen sind breit, aber wenig tief.

> **Sonderfall Risiko (nicht PT-Treiber):** `SECTRACK-02` (History-Rewrite) ist
> mit 0,5–1,5 PT klein, aber **Push-Blocker** und der riskanteste Vorgang
> (SHA-Neuschreibung, nur per Bundle revertierbar).

---

## 4. Hauptannahmen

1. **Teamgröße implizit 1 Dev**, sequentielle Abarbeitung, **keine
   Parallelisierung**; Wartezeiten aus ADR-Blockierern sind **nicht** eingerechnet.
2. **ADR-Entscheidungen (i)–(viii) liegen vor bzw. werden schnell getroffen.**
   Die ADR-Einheiten (SEC-01, RES-03, DATA-01, RES-04, INT-01, DATA-10/DOC-01,
   PLUG-04, DOC-02) schätzen das **Schreiben/Belegen**, nicht die
   Management-Entscheidung.
3. Das Team kennt die Codebase; keine Einarbeitungs-/Onboarding-Zeit.
4. `rapid-prototyping`-DoD: Regressionstest + Doku pro Einheit, aber keine
   formale REQ-Traceability und kein erzwungener Volltest-Lauf pro Einheit.
5. Der Docker-Compose-Stack ist lauffähig; Live-Nachtest-Szenarien
   (Redis-Stop, Scoped-User, ReqIF-Mutation) sind durchführbar.
6. Nur die korrigierten Criticals/Highs/Lücken werden umgesetzt; widerlegte
   Findings bleiben unverändert (reine Registerkorrektur in DOC-06).
7. Externe Werkzeuge (GitHub Actions, `gitleaks`, `git filter-repo`,
   `django-axes`) sind verfügbar und dürfen eingeführt werden.
8. Max. **eine** Review-/Critic-Iteration je Einheit ist eingerechnet.
9. PT = 8 h fokussierte Netto-Arbeit; Meetings, Kontextwechsel und
   Push-/Release-Freigaben zählen nicht.
10. Keine zusätzlichen Anforderungen aus den 143 nicht vollständig geprüften
    Medium/Low/Info-Findings.

---

## 5. Wo die Schätzung besonders unsicher ist

- **Live-Nachtest-Setup (RES-01/02/03, RES-04/05, DATA-01, SEC-02/03, INT-01/04/05,
  PLUG-02):** Der eigentliche Aufwand steckt oft im reproduzierbaren Szenario
  (Redis-Stop, Scoped-User, 401-Workspace-Stack, ReqIF-Mutation), nicht im Fix →
  obere Spanne kann überschritten werden.
- **`SECTRACK-02` (History-Rewrite):** Varianz durch Bundle-Backup,
  `refs/original`/`reflog`, parallele Agents und Aktualisierung aller SHA-Verweise;
  kleiner PT-Wert, große operative Sprengkraft.
- **`DATA-07` (RLS auf `as_*`-Tabellen):** Pre-Auth-Chicken-Egg kann zu
  Teil-Lösungen mit Folgeänderungen zwingen; Bestands- und Deckungstestaufwand
  schwer vorab messbar.
- **`DATA-02`/`DATA-01`:** Off-Host-, Verschlüsselungs- und Medien-Entscheidung
  (ADR iii) ist noch offen; die Infrastrukturvariante (Sidecar vs. Skripte vs.
  Vergleichs-Smoke) verschiebt den Aufwand deutlich.
- **`INT-01`/`INT-04`:** Savepoint-/Transaktionssicherheit und
  Idempotenz-Vertrag (ADR v) können tiefere Service-Refactorings auslösen als
  der Einzelfix vermuten lässt.
- **`DOC-01`/`DOC-02`/`DOC-03`/`DOC-05`:** Die kanonischen Zahlen (Matrix, 116
  i18n-Keys, 443 Tests, 219/35 Tools) sind teils noch **nicht gemessen**; der
  Aufwand wächst mit der Zahl der zu korrigierenden Fundstellen.
- **ADR-Kopplungen:** Der kritische Pfad (ADR ii → SEC-02/03 → DATA-06/07)
  erzeugt Wartezeit, die in einer 1-Dev-Annahme nicht abgebildet ist; bei
  verzögerter Entscheidung verschiebt sich der P0-Block als Ganzes.
- **`PLUG-04`:** Host-Integration bleibt BLOCKED; nur HTTP-/Code-Ebene ist
  belastbar schätzbar.

---

*Erstellt durch `effort-estimator` am 2026-10-01. Schätzung auf Basis von
`IMPLEMENTATION_PLAN.md` §4 und den sieben Detaildateien. Kein Produktcode,
keine Änderung bestehender Dateien, kein Git-Commit. Die Stufen
`S/M/L/XL` sind Orientierung; verbindlich sind die PT-Spannen.*

---

STATUS: done
RESULT: Verbindliche Schätzung aller 49 Arbeitseinheiten erstellt (Gesamtspanne 52,5–115,0 PT, Erwartungswert ≈84 PT, 1 Dev), inkl. T-Shirt-Sizes, Epic-Summen, Top-5-Treiber, Hauptannahmen und Unsicherheiten; Datei neu angelegt, keine bestehende Datei/kein Code/kein Commit verändert. Nächster Schritt: Orchestrator konsumiert die Schätzung als W2-Voraussetzung und committed die neue Datei.
ARTIFACTS: docs/audit/2026-09/review/plan/EFFORT_ESTIMATES.md
