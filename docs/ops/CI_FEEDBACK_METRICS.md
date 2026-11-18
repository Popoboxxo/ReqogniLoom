---
type: STRATEGY
scope: CI-Feedback-Integrität — SLI-Definitionen (S5.3 WP-5)
status: proposed
date: 2026-11-18
author_agent: devops-engineer
reviewer: sre-engineer
branch: fix/s5-3-ops-maturity
base_commit: f60697d
---

# CI-Feedback-Metriken — SLI-Definitionen (S5.3 WP-5)

**Owner:** `devops-engineer` · **SLI-Definition abgestimmt mit:** `sre-engineer`
**Art:** Dokumentation / Mess-Design. Kein Code, keine neuen Dependencies, keine Workflow-Änderung.

> **Wichtige Einordnung vorab:** Dieser Slice **emittiert keine neue Metrik**. Es gibt weder einen
> Skript-, Workflow- noch einen Reporter-Emitter. Dieses Dokument definiert vier SLIs und die
> `gh api`-Rezepte, mit denen sie *von außen* (read-only) berechnet werden können. Ein eigener
> Emitter wurde bewusst abgelehnt — Begründung in [§2](#2-status-quo-verifiziert). Die Schreibhilfe
> `GITHUB_STEP_SUMMARY` ist als **Output-Kanal (Zukunft, nicht implementiert)** vorgesehen, nicht
> als Datenquelle.

---

## 1. Zweck — warum diese SLIs

Der Deep-Dive-Audit (`docs/audit/2026-11-16-deep-dive-findings.md`) hält fest:

- **Zeile 577:** *"No metrics/tracing/alerting artefacts … DORA signals are discussed in comments only; no measurement is collected."*
- **Zeile 580:** *"Flaky handling exists (E2E `retries: 2`, `globalTimeout`) but no quarantine list or flake-rate metric."*
- **Zeile 651 (TEST-009):** *"Track per-shard p95 runtime; split slow specs and/or shard by recorded duration …"*
- **Zeile 1145:** *"Track median PR time-to-green, skipped-test rate, flake quarantine, and 'manual steps per release' as first-class audit signals."*

Die vier SLIs übersetzen diese Befunde in messbare Größen. Sie dienen zwei Zwecken:

1. **DORA-Software-Delivery-Metriken** (Lead Time, Deployment Frequency, Change Failure Rate,
   Failed-Deployment Recovery Time) mit einer *Feedback-nahen* Teilgröße versehen: Ein langer oder
   unzuverlässiger CI-Feedback-Pfad erhöht die Lead Time und verschleiert die Change Failure Rate.
2. **SRE-Toil** („Eliminating Toil", SRE Book, Kap. 6): Manuelle Schritte pro Release sind direkt
   messbare Toil. Was nicht gezählt wird, wird nicht reduziert.

Ziel sind **kleine, häufige, rückholbare Änderungen** — nicht „der Build ist grün".

---

## 2. Status quo (verifiziert)

Verifiziert auf Branch `fix/s5-3-ops-maturity`, Base `f60697d`, Stand 2026-11-18:

| Faktrum | Verifizierter Befund |
|---|---|
| Metrik-Emitter im Code | **0 Treffer** für `flake.?rate`, `shard.?p95`, `gate.?latency`, `time.?to.?green`, `quarantine` in `*.yml/ *.yaml / *.ts / *.py / *.sh`. (5 Treffer auf `p95` stammen ausschließlich aus Backend-Performance-Docstrings: `REQ-L2-PL-008`, `REQ-L2-TE-004`, `REQ-L2-TE-005`, `test_audit_query_budget_1385.py` — keine davon ist eine CI-Feedback-Metrik.) |
| `GITHUB_STEP_SUMMARY` | Nur für Security-/Gate-Summaries: `dependency-audit-extended.yml:81`, `ci.yml:678`, `ci.yml:918` (jeweils `pip-audit`/`npm audit`). Zusätzlich `client-artifacts-check.yml:80` (Artefakt-Gate). **Keine** Metrik-Ausgabe. |
| E2E-Shards | 5 Shards: `playwright.yml:38-41` (`shard: [1, 2, 3, 4, 5]`), ausgeführt `:381-392` (Desktop `--shard=N/4`, Shard 5 = `@mobile`). |
| Flake-Behandlung | `retries: 2` (`e2e/playwright.config.ts:45`), `globalTimeout` 10 min (`:20`), Job-Cap 25 min (`playwright.yml:35`). **Keine** Quarantine-Liste, **keine** Flake-Rate. |
| Shard-Laufzeit | `ci.yml:95-110`: „Noch nicht gemessen" (`set-3-mcp`, `set-4-features` bewusst seriell `-n 0`). Keine p95-Erfassung. |
| Audit-Befunde | `docs/audit/2026-11-16-deep-dive-findings.md:577,580,651,1145`; MTTG-Ziele in `docs/audit/2026-09/AUDIT_EVIDENCE/wp1c-release-deploy-chain.md` §6 (Lint < 5 min, SAST < 10 min, Security < 30 min, Review < 60 min). |

### 2.1 Warum KEIN Emitter in diesem Slice

Ein Metrik-Emitter (z. B. ein täglicher `schedule`-Workflow, der `gh api` aufruft und in
`GITHUB_STEP_SUMMARY` schreibt) wurde **als Over-Engineering abgelehnt**:

- **Token-Wiring:** `actions: read` + `checks: read` bzw. ein GitHub App Token muss beschafft,
  rotiert und geheim gehalten werden — ohne Secret im Code (Paved Road `secret-scanning`).
- **Zustand:** p95 und Flake-Rate sind *Verteilungen über viele Läufe*; ein einzelner Lauf reicht
  nicht. Ein Emitter bräuchte einen persistenten Datenspeicher (oder `gh api`-Abfrage über 50+
  Läufe bei jedem Lauf) — das ist ein eigenes Subsystem.
- **Wartung:** Die `gh api`-Antwortschemas (`jobs`, `check-runs`, Playwright-JSON) sind
  versionsabhängig; jeder Emitter ist eine dauerhafte Wartungslast.
- **Minimal-Variante:** Der Minimal-Variant-Test dieses Arbeitspakets lehnt einen Emitter explizit
  ab. Dokumentation + Rezepte sind der scope-konforme Umfang.

**Konsequenz:** Alle Rezepte unten laufen manuell bzw. in einer zukünftigen, separat freigegebenen
Automatisierung. Sie erzeugen keine Artefakte im Repo und ändern keine Workflows.

---

## 3. Datenverfügbarkeit — wichtige Voraussetzung (zukünftig)

Die designated Datenquellen sind **Playwright JSON Report** und **GitHub Actions REST API**. Für
zwei von ihnen besteht heute eine Erfassungslücke, die *nicht* Teil dieses Slices ist:

- `e2e/playwright.config.ts:47` konfiguriert `reporter: [['html', …], ['list']]` — **kein**
  JSON-Reporter. `report.json` wird also heute nicht erzeugt.
- `.github/workflows/playwright.yml:399-406` lädt den Report nur bei `if: failure()` hoch
  (`retention-days: 7`). Ein *retried-then-passed*-Test landet aber in einem **grünen** Lauf —
  genau diese Fälle wären für SLI 1 relevant und werden heute verworfen.
- `retries: 2` passiert **innerhalb eines einzigen GitHub-Step**. Job-Steps (`gh api …/jobs`)
  zeigen nur das Endergebnis des Steps (`conclusion: success`), nicht die internen Wiederholungen.

> **Für SLI 1 ist daher zwingend (Zukunft, nicht hier umgesetzt):** JSON-Reporter aktivieren
> (`--reporter=json`) und den Upload auf `if: always()` stellen. Bis dahin liefert SLI 1 nur
> einen **coarse Proxy** über Step-Conclusions (siehe Rezept 1b) und ist als *nicht messbar*
> zu führen — analog zur MTTG-Bewertung im Audit („BLOCKED, nicht als PASS").

---

## 4. Die vier SLIs

Alle Rezepte verwenden `gh` (authentifiziert, `GH_TOKEN` mit `actions: read` / `checks: read`)
und `jq`. Platzhalter: `OWNER=Popoboxxo`, `REPO=ReqogniLoom` (aus `git remote -v`). Keine Secrets
im Code — der Token kommt aus der Umgebung.

### SLI 1 — Flake Rate (pro Shard)

| Feld | Wert |
|---|---|
| **Definition** | `flake rate = (retried-then-passed tests) / (total tests)` pro E2E-Shard, bezogen auf einen Zeitfenster (7 Tage). Ein Test gilt als Flake, wenn seine `results`-Liste mehr als einen Eintrag hat **und** der letzte Eintrag `status == "passed"` ist. |
| **Datenquelle** | Playwright JSON Report (`report.json`, `suites[].specs[].tests[].results[]`), bezogen über den Upload-Artifact `playwright-report-<shard>`. Coarse Fallback: `GET /repos/{owner}/{repo}/actions/runs/{run_id}/jobs` → `steps[].conclusion`. |
| **Threshold** | Ziel **< 1 %** pro Shard / Woche · Warnung **> 2 %** · Quarantine-Kandidat bei **> 5 %** über 2 aufeinanderfolgende Wochen (Review durch `sre-engineer`). |
| **Owner** | `devops-engineer` (E2E-Shard-Betreuung), Review mit `sre-engineer`. |
| **Review-Cadence** | Wöchentlich (Montag, Webstorm-Fenster); Quarantine-Entscheidung 14-tägig. |

**Rezept 1a — Artifact finden und Report holen (benötigt `if: always()`-Upload, s. §3):**

```bash
OWNER=Popoboxxo REPO=ReqogniLoom RUN_ID=123456789 SHARD=1
# locate the uploaded Playwright report artifact for this shard
ART_ID=$(gh api "repos/$OWNER/$REPO/actions/runs/$RUN_ID/artifacts?per_page=100" \
  --jq ".artifacts[] | select(.name == \"playwright-report-$SHARD\") | .id" | head -1)
gh api "repos/$OWNER/$REPO/actions/artifacts/$ART_ID/zip" > /tmp/pw-$SHARD.zip
unzip -oq /tmp/pw-$SHARD.zip -d /tmp/pw-$SHARD
```

**Rezept 1a (Forts.) — Flake-Rate aus `report.json` (jq):**

```bash
jq '
  [.. | objects | .tests[]?] as $all
  | [$all[] | select((.results | length) > 1 and .results[-1].status == "passed")] as $flaky
  | {total: ($all | length), flaky: ($flaky | length),
     flake_rate: (if ($all | length) == 0 then 0 else (($flaky | length) / ($all | length)) end)}
' /tmp/pw-$SHARD/playwright-report/report.json
```

**Rezept 1b — Coarse Proxy über Job-Steps (heute verfügbar, aber ohne Playwright-Interna):**

```bash
gh api "repos/$OWNER/$REPO/actions/runs/$RUN_ID/jobs?per_page=100" \
  --jq '.jobs[]
        | select(.name | test("playwright|e2e"; "i"))
        | {job: .name, conclusion,
           steps: [.steps[] | select(.name | test("Playwright|mobile smoke"; "i"))
                             | {name, conclusion, started_at, completed_at}]}'
```

> Grenze: Ein Step, der trotz interner Retries grün wurde, erscheint hier als `success`. Der Proxy
> erkennt nur *neu gestartete Steps* (`gh api …/actions/jobs/{job_id}/rerun`), nicht die internen
> `retries: 2`. Als Alleinindikator ungeeignet.

---

### SLI 2 — Shard p95 Duration

| Feld | Wert |
|---|---|
| **Definition** | 95-Perzentil der Laufzeit (Differenz `completed_at − started_at`, in Minuten) aller E2E-Jobs über die letzten **50 Workflow-Runs** von `playwright.yml`, gruppiert nach Shard-Name. |
| **Datenquelle** | GitHub Actions REST: `GET /repos/{owner}/{repo}/actions/workflows/{workflow_id}/runs` → `workflow_runs[].id`; dann `GET /repos/{owner}/{repo}/actions/runs/{run_id}/jobs` → `jobs[].{name,started_at,completed_at}`. |
| **Threshold** | Ziel **p95 < 18 min** · Warnung **> 20 min** · Hart: **25 min Job-Cap** (`playwright.yml:35`) darf nicht überschritten werden (dann wird der Report-Upload übersprungen — Beweis geht verloren). Testphase allein unterliegt `globalTimeout` 10 min (`:20`). |
| **Owner** | `devops-engineer`. |
| **Review-Cadence** | Wöchentlich **und** nach jeder Änderung an Shards, Specs oder `globalTimeout`. |

**Rezept 2 — p95 über 50 Läufe (gh api + jq):**

```bash
OWNER=Popoboxxo REPO=ReqogniLoom
# 1) Run-IDs der letzten 50 Playwright-Läufe
gh api "repos/$OWNER/$REPO/actions/workflows/playwright.yml/runs?per_page=50" \
  --jq '.workflow_runs[].id' > /tmp/pw-runs.txt

# 2) Job-Laufzeiten sammeln (Sekunden), Shard-Name aus dem Job-Namen
: > /tmp/pw-durations.jsonl
while read -r RUN_ID; do
  gh api "repos/$OWNER/$REPO/actions/runs/$RUN_ID/jobs?per_page=100" \
    --jq '.jobs[]
          | select(.name | test("playwright|e2e"; "i"))
          | {job: .name,
             sec: (((.completed_at // .started_at) | fromdateiso8601)
                   - (.started_at | fromdateiso8601))}' >> /tmp/pw-durations.jsonl
done < /tmp/pw-runs.txt

# 3) p95 je Shard (jq-Index: ceil(0.95*n)-1)
jq -s 'group_by(.job) | map({
  job: .[0].job,
  n: length,
  p95_sec: (map(.sec) | sort | .[((length * 0.95 | ceil) - 1)]),
  p95_min: ((map(.sec) | sort | .[((length * 0.95 | ceil) - 1)] / 60) * 100 | round / 100)
})' /tmp/pw-durations.jsonl
```

> Hinweis: Läufe ohne `completed_at` (abgebrochen) werden über `// .started_at` auf 0 s gesetzt und
> damit als Ausreißer sichtbar — genau die Fälle, die hinter der 25-Min-Cap verschwinden.

---

### SLI 3 — Gate Latency (Commit → erster grüner Check)

| Feld | Wert |
|---|---|
| **Definition** | `gate latency = min(completed_at über alle Checks mit conclusion == "success") − commit.author.date`, in Minuten, für einen gegebenen Commit-SHA. „Erster grüner Check" ist die Feedback-Untergrenze (nicht der vollständige.merge-gate). |
| **Datenquelle** | GitHub REST: `GET /repos/{owner}/{repo}/commits/{sha}` → `commit.author.date`; `GET /repos/{owner}/{repo}/commits/{sha}/check-runs?per_page=100` → `check_runs[].{name,conclusion,started_at,completed_at}`; ergänzend `GET /repos/{owner}/{repo}/actions/runs?head_sha={sha}` → `workflow_runs[].{name,status,conclusion,run_started_at,updated_at}`. |
| **Threshold** | Median **< 30 min** (kompatibel mit MTTG-Ziel „Commit → Security-Scan < 30 min", wp1c §6) · p95 **< 60 min** (MTTG „Commit → Review < 60 min") · Warnung bei **> 60 min**. Für Branch-Protection-relevante Checks separat dieselben Ziele anwenden. |
| **Owner** | `devops-engineer` (Pipeline), Review mit `sre-engineer`. |
| **Review-Cadence** | Pro Release + wöchentlicher Trend; DORA-Auswertung monatlich (Lead-Time-Anteil). |

**Rezept 3 — Gate-Latenz in Minuten (gh api + jq):**

```bash
OWNER=Popoboxxo REPO=ReqogniLoom SHA=abcdef1234567890
# commit timestamp as epoch seconds
COMMIT_TS=$(gh api "repos/$OWNER/$REPO/commits/$SHA" --jq '.commit.author.date | fromdateiso8601')

# earliest green check, in minutes after the commit
gh api "repos/$OWNER/$REPO/commits/$SHA/check-runs?per_page=100" \
  --jq --argjson c "$COMMIT_TS" '
    [ .check_runs[]
      | select(.conclusion == "success")
      | ((.completed_at | fromdateiso8601) - $c) / 60 ]
    | if length == 0 then "no green check" else (min * 100 | round / 100) end
  '

# optional: which workflow runs belong to the commit (context for the gate)
gh api "repos/$OWNER/$REPO/actions/runs?head_sha=$SHA&per_page=100" \
  --jq '.workflow_runs[] | {name, status, conclusion, run_started_at, updated_at}'
```

> Grenze: `author.date` ist die Autorenzeit, nicht der Push-Zeitpunkt. Bei Rebases/Cherry-Picks
> verzerrt das den Wert nach unten; für exakte Messung `committer.date` oder `pushed_at` des PRs
> heranziehen. Solange kein flächendeckendes Branch-Protection-Set existiert, ist „erster grüner
> Check" eine Feedback-, keine Freigabeaussage.

---

### SLI 4 — Manual Steps per Release

| Feld | Wert |
|---|---|
| **Definition** | Anzahl manueller Interventionen pro Release: `workflow_dispatch`-Triggers + `pending_deployments`-Approvals + manuell gesetzte Deployment-Statuses + dokumentierte Runbook-Schritte aus `docs/DEPLOY_RUNBOOK.md`, die ein Mensch ausführt. Gezählt wird pro Release-Fenster (Tag → nächster Tag). |
| **Datenquelle** | GitHub REST: `GET /repos/{owner}/{repo}/actions/runs?event=workflow_dispatch` → `workflow_runs[]`; `GET /repos/{owner}/{repo}/actions/runs/{run_id}/pending_deployments` → `pending_deployments[].{environment,reviewers}`; `GET /repos/{owner}/{repo}/deployments?environment=production` → `deployments[]`. |
| **Threshold** | Ziel **0** · toleriert **≤ 2** · Warnung **> 3** pro Release (jeder Schritt ist Toil + Fehlerquelle). Jeder Schritt über 0 braucht einen Eintrag im Release-Report mit Grund und Automatisierungs-Issue. |
| **Owner** | `devops-engineer` (Release-Pipeline), Review mit `sre-engineer` im Release-Retro. |
| **Review-Cadence** | Pro Release (Retro); quartalsweiser Toil-Trend. |

**Rezept 4 — manuelle Trigger und Approvals im Release-Fenster:**

```bash
OWNER=Popoboxxo REPO=ReqogniLoom SINCE=2026-11-01T00:00:00Z
# a) manual workflow dispatches in the release window
gh api "repos/$OWNER/$REPO/actions/runs?event=workflow_dispatch&per_page=100" \
  --jq --arg since "$SINCE" '
    [.workflow_runs[] | select(.created_at >= $since)
     | {name, created_at, actor: .actor.login, url: .html_url}]'

# b) pending environment approvals for a specific run
RUN_ID=123456789
gh api "repos/$OWNER/$REPO/actions/runs/$RUN_ID/pending_deployments" \
  --jq '.pending_deployments[] | {environment, reviewers: [.reviewers[].login]}'

# c) production deployments with their manual descriptions
gh api "repos/$OWNER/$REPO/deployments?environment=production&per_page=100" \
  --jq '[.[] | select(.created_at >= $since) | {id, sha: .sha[0:7], created_at, description}]'
```

> Die Zählregel ist bewusst konservativ: Ein `workflow_dispatch`, der nur einen Upload bestätigt,
> zählt genauso wie ein Freigabe-Klick. Ziel ist nicht die Bewertung, sondern die **Sichtbarkeit**
> von Toil. `docs/DEPLOY_RUNBOOK.md` bleibt die Referenz für Schritte, die außerhalb von GitHub
> passieren (z. B. manuelles `docker compose up -d`).

---

## 5. Abbildung auf DORA und SRE-Toil

| SLI | DORA-Metrik | Wirkung |
|---|---|---|
| 1 — Flake Rate | Change Failure Rate / Reliability | Ein Flake verwässert die Fail-Rate: grüne Läufe enthalten versteckte Fehler. Quarantine macht Sie wieder eindeutig. |
| 2 — Shard p95 | Deployment Frequency (Enabler) | Langsame, unvorhersehbare Shards senken die Frequenz und erhöhen Batch-Größe — das Gegenteil von kleinen Änderungen. |
| 3 — Gate Latency | Lead Time for Changes | Commit → erster grüner Check ist der untere Anteil der Lead Time; ohne ihn ist DORA-Lead-Time nicht erklärbar. |
| 4 — Manual Steps | Toil (SRE) + Deployment Frequency | Jeder manuelle Schritt ist Toil und ein Serialisierungspunkt; direkter Angriffspunkt für Automatisierung. |

**Failed-Deployment Recovery Time** wird hier nicht als eigener SLI definiert — er ist Gegenstand
des separaten Rollback-/Runbook-Arbeitspakets (`docs/DEPLOY_RUNBOOK.md`, ADR-012/ADR-020) und
würde den Scope dieses Dokuments sprengen.

---

## 6. Output-Kanal (Zukunft, NICHT implementiert)

`GITHUB_STEP_SUMMARY` ist der **vorgeschlagene Ausgabe-Kanal** für eine spätere Automatisierung.
Heute wird es ausschließlich für Security-/Gate-Summaries genutzt:

| Datei | Zeile | Zweck |
|---|---|---|
| `.github/workflows/dependency-audit-extended.yml` | 81 | `npm audit`-Gate |
| `.github/workflows/ci.yml` | 678 | `npm audit`-Gate |
| `.github/workflows/ci.yml` | 918 | `pip-audit`-Gate |
| `.github/workflows/client-artifacts-check.yml` | 80 | Artefakt-Gate (kein Security-Scan) |

Ein künftiger Emitter könnte dort eine Tabelle `SLI | Wert | Threshold | Status` schreiben.
**In diesem Slice geschieht das nicht** — kein Workflow, kein Skript, keine Änderung an
`.github/workflows/`. Die Rezepte in §4 bleiben die einzige Bezugsquelle.

---

## 7. Grenzen und nicht implementiert

- **Keine Metrik wird emitted.** `grep` über Code/Workflows ergibt 0 Emitter-Treffer (s. §2).
- **SLI 1 ist heute nicht messbar** (kein JSON-Reporter, Report nur bei Failure, Retries intern) —
  als `BLOCKED` zu führen, nicht als PASS.
- **Keine Persistenz, kein Dashboard, kein Alerting.** Dieses Dokument ersetzt keine
  Metrik-Infrastruktur; es legt nur fest, *was* gemessen würde und *wie* man es heute manuell
  nachrechnet.
- **Keine Secrets in Code/Config.** `GH_TOKEN` ausschließlich aus der Umgebung; minimale Scopes
  `actions: read`, `checks: read`.
- **Keine Änderung an `.github/workflows/`, kein Code, keine neuen Dependencies.**

---

## 8. Referenzen

- `docs/audit/2026-11-16-deep-dive-findings.md:577,580,651,1145`
- `docs/audit/2026-09/AUDIT_EVIDENCE/wp1c-release-deploy-chain.md` §6 (MTTG-Ziele)
- `.github/workflows/playwright.yml:35,38-41,381-392,399-406`
- `.github/workflows/ci.yml:95-110,678,918`
- `.github/workflows/dependency-audit-extended.yml:81`
- `.github/workflows/client-artifacts-check.yml:80`
- `e2e/playwright.config.ts:20,45,47`
- `docs/DEPLOY_RUNBOOK.md`
- DORA: *Accelerate* (Forsgren, Humble, Kim) — Lead Time, Deployment Frequency, Change Failure
  Rate, Failed Deployment Recovery Time.
- SRE: *Site Reliability Engineering* (Google, Kap. 6 „Eliminating Toil").
