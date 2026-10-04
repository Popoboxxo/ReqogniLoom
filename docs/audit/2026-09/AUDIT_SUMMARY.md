---
type: REVIEW
scope: audit-summary
status: final
date: 2026-09-30
author_agent: documenter
---

# AUDIT_SUMMARY — Systemaudit 2026-09, Abschluss-Synthese

> **Rolle dieses Dokuments.** Es ist die **Lesefassung für Entscheider**. Es führt
> **keine neue Fachanalyse** durch, erfindet/verschiebt/entfernt **kein** Finding
> und **bewertet nicht neu**. Jede Zahl, jeder Schweregrad und jede
> Klassifikation stammt unverändert aus
> [`AUDIT_FINDINGS.md`](AUDIT_FINDINGS.md) — dem **kanonischen Register**, das
> seinerseits die neun WP-Reports ausweist. Bei Widerspruch gilt das Register,
> nicht diese Zusammenfassung.
>
> **Änderungsgrenze dieser Synthese:** ausschließlich die vier neuen Dateien
> `AUDIT_SUMMARY.md`, `AUDIT_BACKLOG.md`, `AUDIT_ADR_CANDIDATES.md`,
> `README.md` unter `docs/audit/2026-09/`. **Kein Produkt-Code wurde geändert,
> kein WP-Report und kein Evidenz-File wurde überschrieben.**

---

## 1. Kopfangaben

| Aspekt | Wert |
|---|---|
| **Audit-Basis (Prüf-HEAD)** | `main` @ `abd61aed` |
| **Branch** | `chore/system-audit-2026-09` (11 Commits über `main`) |
| **Zeitfenster** | 2026-09-29 (WP-Läufe) bis 2026-09-30 (Konsistenz-Gate + Sicherheits-Nachtrag) |
| **Methodik in Kürze** | 11 Workstreams, 9 WP-Reports, rund 100 Evidenz-Dateien + Screenshots; Read-only-Mandat (außer den beiden Restore-Wegwerf-Containern in WP-1c), kein Produkt-Fix, kein Push |
| **Kanonisches Register** | [`AUDIT_FINDINGS.md`](AUDIT_FINDINGS.md) — 285 Zeilen = 279 Findings + 5 bestätigte Kontrollen + 1 zurückgezogenes Finding (`-070`) |
| **Befundlage** | 13 Critical · 76 High · 115 Medium · 60 Low · 15 Info = **279** (nach K-1, §11) |
| **Klassifikation** | 264 `NEU` · 4 `BESTAETIGT` · 5 `WIDERLEGT` · 6 `BLOCKED` · 1 `DUPLIKAT` |
| **Vor-Audit** | `docs/se/reports/deep_audit/system-audit-2026-09/` (Prüf-HEAD `e3df119e`, 47 Tracks `CR-01`…`CR-47`, Health Score 1,4/5) — **nur verlinkt, nicht verändert** |

### 1.1 Warum `main` @ `abd61aed` und nicht der Release-Cut

Der Release-Cut `release/v1.8.0-beta.18` (`38da915f`, Tag `v1.8.0-beta.18`)
liegt **zwei Commits über** `abd61aed` und besteht ausschließlich aus
`CHANGELOG.md`, `VERSION`, `.env.example`, `package.json`-Versionen und zwei
Berichten unter `docs/se/reports/`. Der Commit enthält **keinen Image-Build,
keinen Testlauf und kein CI-Artefakt** — er war zum Auditzeitpunkt
**unverifiziert**.

Ein Audit bewertet den **tatsächlichen Produktstand**. Geprüft wurde deshalb der
letzte Commit mit belegbarem Produktzustand, `main` @ `abd61aed`. Die
Gleichsetzung „Release-Schnitt = freigegebener Stand" wäre eine Behauptung ohne
Beleg gewesen — genau die Fehlerklasse, die dieser Audit in
[`AUD-2026-09-195`](AUDIT_FINDINGS.md) als „Falsch-Abnahme" dokumentiert.

### 1.2 Was **live getestet** wurde vs. was **statisch belegt** ist

Diese Trennung ist die wichtigste Lesehilfe dieses Audits: sie entscheidet, welche
Aussage beim nächsten Vorfall wie viel wiegt.

| Belegstufe | Was daraus belegt wird | Umfang im Audit |
|---|---|---|
| **LIVE** (ausgeführte Requests/Prozesse gegen den laufenden Stack `localhost:8001` / `:5173` / Postgres / Redis) | Verhalten, nicht nur Code | WP-1a: 82 JSON-RPC-Rohpaare · 39-Fall-Tool-Validierungsmatrix · 65-Fall-Tenant-Isolationsmatrix gegen einen **echten** zweiten Tenant · 12-Mutationstest des Manifest-Guards · Redis-Ausfall-Simulation mit Wiederherstellung.<br>WP-1d: **120 Cross-Tenant-Proben** · 20-Fall-Auth/JWT-Matrix · Pagination-, Filter- und Fehlerformat-Matrizen · OpenAPI-Drift gegen `GET /api/schema/` (613 769 Bytes) · CSV-, ReqIF- und PDF-Round-Trips · ViewSet-/APIView-Inventar per AST-Walk.<br>WP-1b: Request-Capture aller 6 Adapter gegen einen In-Process-HTTP-Stub (jeder Header und Body real aufgezeichnet) · Fehlerpfad-Matrix mit 15 Szenarien · Timeout-/Retry-Matrix live gemessen.<br>WP-1c: `docker compose config` je Profil · **echter Restore in eine isolierte Datenbank (15/15 Tabellenzahlen, 0 Fehler)** · `celery-beat`-Log: **0 × `Sending due task`** · Redis-Key-Inspektion (5914 `celery-task-meta-*`) · `/health/` live.<br>WP-2: beide Hermes-Plugins end-to-end über **echte, vom Plugin selbst erzeugte Requests**; Claude Code und Antigravity über den vollständigen SSE-Handshake; `/bluepencil/api/notes` **ohne Credential → 200**.<br>WP-3: **28 Screens** mit Playwright/Chromium inkl. Login `admin`, je Screen Console- und Netzwerkmatrix.<br>WP-4: live gemessen (Link-Typ-Belegung, Presetwechsel 1/5/9 Transitions, Scope-Trennung, 29/31 `pl_*`-Tabellen mit RLS, 0 `.raw()` im Produktions-Backend).<br>WP-6a: nicht-mutierende Live-Proben, read-only `docker exec … psql`, separate ReqIF-XXE-Läufe (4 Payloads), Rate-Limit-Bucket-Messung (187 → 205 Bytes bei 5 × HTTP 401 **mit ungültiger** Credential).<br>WP-6b: **6 × `EXPLAIN (ANALYZE, BUFFERS)`** live · `select_for_update`-Analyse · Live-Zählungen (`audit_entry` 8167 Zeilen, 97,7 % `entity_version` NULL; 222 863 Outbox-Läufe, 0 Fehlschläge). |
| **STATISCH** (Code-/Konfigurationslesung mit `file:line`; **keine** Ausführung) | Struktur, Absicht, Konfiguration | WP-3b **vollständig** (kein `vitest`-Lauf; Ratchet-Baselines aus dem Quelltext nachgerechnet).<br>Echte Provider-Antworten (Anthropic/OpenAI/Azure/OpenCode Go) · live-validierte Modell-IDs · echter Ollama-Server · Circuit-Breaker-Zyklus OPEN→Half-Open→CLOSED.<br>CVE-/SBOM-/Trivy-Lauf und MTTG-Zeitwerte · Frontend-Bundle-Größe, ungenutzte Libraries, tote Dateien · Typ-Drift TS ↔ Django-Serializer · `CR-33`/`CR-35`-Performancehypothesen (statisch entkräftet). |
| **BLOCKED** (ausdrücklich **kein PASS**) | nichts — nur die Lücke | 6 Findings + 12 offene Prüfpunkte, vollständig in [`AUDIT_FINDINGS.md` § 7](AUDIT_FINDINGS.md) |

**Konsequenz:** Für WP-3/WP-3b gilt die **Zweitmessung-Regel** — wo beide Agenten
dasselbe Objekt gemessen haben (i18n-Lücke, Hex-Literale, E2E-Selektoren), ist
die **WP-3b-Zahl** maßgeblich (C1, C3, C4). Für die WPs **ohne** zweite Messung
stammen die Zahlen aus **einer** Messung; das ist eine **Restunsicherheit dieses
Audits** (siehe [`AUDIT_FINDINGS.md` § 14.1](AUDIT_FINDINGS.md)), keine
Feststellung zu einem Produktdefekt.

---

## 2. Verdikt in fünf Sätzen

1. ReqogniLoom hat **keine strukturellen Defekte in den tragenden Schichten** —
   Transaktionsgrenzen, Performance der Hot-Paths und Tenant-Isolation sind
   gemessen sauber (12/12 atomar, 0,12–2,95 ms indexgestützt, 0 Leaks in 120
   Cross-Tenant-Proben).
2. Das Problem ist **nicht Fehlen von Prüfungen, sondern deren Reichweite und
   ihre Selbsttäuschung**: 279 Findings, davon 13 Critical, konzentrieren sich in
   vier Klassen — stillschweigendes Scheitern (`success: true` bei Totalausfall),
   fehlende Server-Side-Fences, geteilte Zustände/nicht-idempotente Operationen
   und eine Dokumentation, die Ist-Zustände als Soll verkauft.
3. **Wichtigster Einzelbefund:** das Audit hat **selbst** ein live gültiges
   `write`-API-Key committet (`AUD-2026-09-220`) — Key widerrufen, Arbeitsbaum
   redigiert, **Git-Historie offen**; das ist zugleich der teuerste Prozessdefekt
   des Auditprozesses (P-1) und muss vor jeder Veröffentlichung entschieden
   werden.
4. **Der Betriebsstand ist derzeit nicht verzeihbar**: alle 4 Celery-Queues sind
   identisch gebunden (jede Task 4×), `celery-beat` dispatcht nachweislich nie,
   und `/health/` meldet währenddessen durchgehend `200 {"status":"ok"}` — und
   das dokumentierte Notfall-Restore-Skript kann nie erfolgreich sein.
5. **Vor Freigabe eines Release-Schnitts fehlt die Nachweiskette**: 443 von 8127
   Backend-Testdefinitionen laufen in keinem CI-Job, 4 **belegte Falsch-Abnahmen**
   stehen in den Release-/Testplan-Berichten, und die SE-Traceability-Matrix
   listet 324 Quell-REQ-IDs nicht und publiziert 0 von 354 REQ-L3-Zeilen — sie
   taugt derzeit **in beide Richtungen** nicht als Nachweis.

---

## 3. Ampel je Arbeitspaket

Schweregrade: **C**ritical / **H**igh / **M**edium / **L**ow / **I**nfo.
Zahlen aus [`AUDIT_FINDINGS.md` § 11.2](AUDIT_FINDINGS.md). WP-1a/1b/1d werden
dort als **ein** Block geführt (5/19/24/9/5 = 62) und hier nach den ID-Blöcken der
drei WP-Reports getrennt ausgewiesen; die Summe stimmt mit dem Register überein.

| WP | Thema | Ampel | Begründung (1 Satz) | C/H/M/L/I | Findings |
|---|---|---|---|---|---:|
| **WP-1a** | MCP-Server | GELB-ORANGE | Tenant-Isolation und Manifest-Drift-Guard sind sauber (65/65, 12/12), aber Graceful Degradation ist **ein** Ausfall: Redis down ⇒ alle 13 MCP-Endpoints hängen unbegrenzt. | 2/5/8/4/3 | **22** |
| **WP-1b** | LLM-Adapter | **ROT** | Der Mock ist ein ehrlicher Testdouble auf Capability-Ebene, aber **unehrlich bei den Kosten** (4 feste Token-Konstanten, prompt-unabhängig, als exakte API-Nutzung verbucht) — zusätzlich ein retired Default-Modell. | 1/7/7/0/1 | **16** |
| **WP-1d** | REST-API & Datenintegration | GELB-ORANGE | 0 Tenant-Leaks in 120 Proben und saubere AuthN/Pagination, aber drei Round-Trip-Bruchstellen scheitern **stillschweigend** (`success: true` bei 0 bzw. 915 Fehlern), und 432/439 Operationen deklarieren keinen Fehlerfall. | 2/7/9/5/1 | **24** |
| **WP-1c** | Infrastruktur / Betrieb | **ROT** | Der Kern ist funktionsfähig und der **Backup-Mechanismus** ist erfolgreich getestet (Restore 15/15), aber die asynchrone Hälfte ist stillgelegt (Beat 0 Dispatches, Task-Fan-out 4×) und beide dokumentierten Operator-Skripte können nie erfolgreich sein. | 4/8/13/5/0 | **30** |
| **WP-2** | Native Plugins / Integrationen | **ROT** | Alle vier Bundles waren live end-to-end testbar und die `dist/`-Pakete zeigen **null Über-Deklaration** (80/80, 82/82, 129/129), aber der Hauptpfad des Python-Agent-Plugins crasht live mit `TypeError` bei dokumentiertem „never raises". | 1/6/7/6/4 | **24** |
| **WP-3** | UI-Browser (Playwright) | GELB | Alle 28 Screens erreichbar und token-sauber (0 Verstöße), aber zwei systemische Funde — 453 Requests für einen Dashboard-Load und 112 maskierte i18n-Fehl-Keys — wiegen schwerer als die Einzelfunde. | 0/3/7/12/3 | **25** |
| **WP-3b** | Frontend statisch | GELB | Konventions-Disziplin ungewöhnlich gut (0 echte Inline-Styles, 100 % kebab-case `data-testid`, Ratchet vorhanden), die verbleibenden Lücken sind fast ausnahmslos **Messlücken in den eigenen Ratchets**. | 0/2/11/12/0 | **25** |
| **WP-4** | Datenmodell / Artefakt-Modell | GELB-ORANGE | Der Link-Typ-Katalog ist über alle vier Ebenen konsistent offen (PASS), aber die Rigor-Presets sind faktisch **halb hartkodiert** — und die hartkodierte Hälfte steuert die fachlich gewichtigere Achse. | 0/11/17/5/3 | **36** (+5 Kontrollen) |
| **WP-5** | Traceability / SE-Nachweis | **ROT** | Die Traceability-Kette existiert, ist aber weder zählbar noch gepflegt: 324 fehlende REQ-IDs, `open_adrs` 0/835, 14/15 `arch_impact: true` ohne ADR — sie taugt **in beide Richtungen** nicht als Nachweis. | 2/19/15/1/0 | **37** |
| **WP-6a** | Security / Trust Boundaries | GELB | AuthN ist bemerkenswert sauber und Input-Validation stark (keine XXE, keine CSV-Formel-Injection, keine RCE-Vektoren), aber die Lücke ist eine **Reichweiten-Asymmetrie**: der Workspace-Fence greift client-gesteuert, und die CI-Kette hat kein Secret-Scan-Gate. | 2/5/8/7/0 | **22** |
| **WP-6b** | Zuverlässigkeit / Concurrency / Observability | GELB (2 rote Dimensionen) | Transaktions- und Performance-Schicht sind **hochwertig** (12/12 atomar, 6/6 Hot-Paths indexgestützt), die Lücke liegt in **Absicherung** (Concurrency) und **Beobachtbarkeit** (Observability). | 0/3/13/3/0 | **19** |
| | | | | **13/76/115/60/15** | **279** |

**Sub-Ampeln, die aus der Gesamt-Ampel herausfallen:** WP-6a AuthZ **ROT** und
CI/CD **ROT** (WP-6a §0); WP-6b Concurrency **ROT** und Observability **ROT**
(WP-6b); WP-1c „Backup-Seite grün, Betriebsseite rot" (WP-1c §0).

---

## 4. Finding-Statistik

Alle Zahlen aus [`AUDIT_FINDINGS.md` § 11](AUDIT_FINDINGS.md). **Nichts wurde
für diesen Bericht umgerechnet.**

### 4.1 Nach Schweregrad

| Schweregrad | Anzahl | Anteil an 279 |
|---|---:|---:|
| Critical | **13** | 4,7 % |
| High | **76** | 27,2 % |
| Medium | **115** | 41,2 % |
| Low | **60** | 21,5 % |
| Info | **15** | 5,4 % |
| **Summe (offene Findings)** | **279** | 100 % |

> **Korrektur 2026-09-30 (K-1):** `AUD-2026-09-070` wurde von der unabhängigen Gegenprüfung **widerlegt** und zurückgezogen. Critical **14 → 13**, offene Findings **280 → 279**. Das Finding bleibt als `WIDERLEGT` sichtbar, wird aber nicht mehr als offener Mangel gezählt.

### 4.2 Nach Klassifikation

| Klassifikation | Anzahl | Bedeutung für die Umsetzung |
|---|---:|---|
| `NEU` | **263** | erstmals in diesem Audit erhoben — **kein** Vor-Audit-Vorgänger mit gleicher Aussage |
| `BESTAETIGT` | **4** | Vor-Audit-/Fremdbefund am aktuellen Code erneut bestätigt (IDs: `270`, `278`, `287`, `018`) |
| `WIDERLEGT` | **5** + **1 zurückgezogen** | Vor-Audit-/Fremdaussage widerlegt (IDs: `021`, `022`, `050`, `152`, `166`) |
| `BLOCKED` | **6** | nicht verifizierbar — **ausdrücklich kein PASS** |
| `DUPLIKAT` | **1** | bereits erfasst (`143` = Duplikat zu Issue `#1019`) |
| *bestätigte Kontrollen (PASS)* | *5* | *Negativbefunde, nach PASS-Regel **nicht** in den 279 enthalten* |

> **Lesehinweis:** `NEU` ist die *Klassifikation* des Registers, nicht die
> Aussage „kein CR-Track genannt". **179 der 285 Master-Zeilen nennen gar keinen
> `CR-Track`** — darunter **7 der 13 Critical** (`030`, `031`, `121`, `220`,
> `221`, `345`, `346`). Das ist die präzisere Aussage zum Verhältnis beider
> Audits.

### 4.3 Verteilung je Workpackage

| WP | Report | Critical | High | Medium | Low | Info | Findings | Kontrollen |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| WP-1a/1b/1d | `AUDIT_EXTERNAL_INTEGRATIONS.md` | 4 | 19 | 24 | 9 | 5 | **61** | 0 |
| WP-1c | `AUDIT_INFRASTRUCTURE.md` | 4 | 8 | 13 | 5 | 0 | **30** | 0 |
| WP-2 | `AUDIT_NATIVE_PLUGINS.md` | 1 | 6 | 7 | 6 | 4 | **24** | 0 |
| WP-3 | `AUDIT_UI_BROWSER.md` | 0 | 3 | 7 | 12 | 3 | **25** | 0 |
| WP-3b | `AUDIT_FRONTEND_STATIC.md` | 0 | 2 | 11 | 12 | 0 | **25** | 0 |
| WP-4 | `AUDIT_DATA_MODEL.md` | 0 | 11 | 17 | 5 | 3 | **36** | 5 |
| WP-5 | `AUDIT_TRACEABILITY.md` | 2 | 19 | 15 | 1 | 0 | **37** | 0 |
| WP-6a | `AUDIT_SECURITY.md` | 2 | 5 | 8 | 7 | 0 | **22** | 0 |
| WP-6b | `AUDIT_RELIABILITY.md` | 0 | 3 | 13 | 3 | 0 | **19** | 0 |
| **Gesamt** | 9 Reports | **13** | **76** | **115** | **60** | **15** | **279** | **5** |

> **K-1:** `AUD-2026-09-070` (WP-1d, Critical) ist **widerlegt** und aus der Critical-Zählung herausgenommen. Es bleibt in der Master-Tabelle des Registers als `WIDERLEGT` sichtbar.

## 5. Die Top-10 der kritischsten Findings

Auswahlkriterium: **Schweregrad × tatsächliche Schadenswirkung ×
Eintritts-Wahrscheinlichkeit**. Die Reihenfolge ist damit **bewusst nicht** die
Reihenfolge der 13 Critical im Register — 4 Critical-IDs sind Doppelmeldungen
derselben Ursache in zwei Workstreams (`345`/`346` zu `122`/`123` bzw. `052`)
und werden dort zusammengeführt, wo sie keine eigene Schadenswirkung addieren.

> **Neu zusammengesetzt am 2026-09-30 (K-1).** `AUD-2026-09-070` wurde von der
> unabhängigen Gegenprüfung **widerlegt** (`import_service.py:341-344` strippt
> Kommentarzeilen; Export-Kommentar und Strip aus demselben Commit `3081435a`)
> und ist aus dieser Liste **entfernt**. Der Platz wird **nicht** mit einem
> schlechteren Befund aufgefüllt, sondern mit dem nächsten belegten
> Critical-Finding (`-115`). Die Liste hat damit **9 Einträge** statt 10 — das
> ist das korrekte Ergebnis, kein Formfehler.
>
> **Gegenprüfungs-Status** ist in der letzten Spalte vermerkt. Wegen des
> gestoppten Stacks war **keine** Live-Nachmessung möglich — die Vermerke
> bedeuten *statisch/hermetisch bestätigt*, nicht *live bestätigt* (§11).

| Rang | ID | Schweregrad | Kurztitel | Ort | Auswirkung | Gegenprüfung |
|---:|---|---|---|---|---|---|
| 1 || `AUD-2026-09-220` | Critical | `reqlo_`-API-Key im Klartext committet — **vom Audit selbst**; Commit **nie gepusht** (kein PR/Fork) | `AUDIT_EVIDENCE/wp1d-auth-pagination-filter-errors-live.json:2246` (Commit `3dcc80d8`) | Arbeitsbaum redigiert, Widerruf durch 3-fach-Beleg dokumentiert (live nicht nachprüfbar, Stack gestoppt). **Historie offen im lokalen, nicht gepushten Branch** — es gab **kein** PR und **keinen** Fork, die es ziehen konnten. | bestätigt, **Reichweite korrigiert**: nie gepusht, kein PR/Fork |
| 2 || `AUD-2026-09-222` | **High** | Workspace-Fence greift auf 269 von 311 mutierenden Routen nicht | `auth_tenancy/workspace_scope.py:114`; `auth_tenancy/rest.py:259-271` | Cross-Workspace-Schreibzugriff **innerhalb** eines Tenants; für ein SE-Tool mit Audit-/Traceability-Nutzen ist die Nachweiskette damit wertlos. | bestätigt |
| 3 || `AUD-2026-09-030` + `-221` | Critical | Redis-Ausfall ohne `SOCKET_TIMEOUT` hängt 13 MCP-Endpoints unbegrenzt; unauthentifizierter Cache-Pfad **vor** AuthN | `settings.py:879`; `mcp_server/views.py:272`; `mcp_server/throttling.py:164` | Jeder Redis-Kurzbefehl macht die komplette KI-Fläche unbenutzbar — und ist gleichzeitig die DoS-Verstärkung (live belegt: 5 × 401 wachsen den Bucket). | bestätigt (Endpoint-Zahl 13 nicht nachgezählt) |
| 4 || `AUD-2026-09-031` | Critical | `/health/` prüft den Cache nicht und meldet bei **Redis-/Worker-Ausfall** `ok` (bei DB-Ausfall korrekt 503) | `reqogniloom/health.py:118-190` | Jedes automatische Gate (Compose, CI, Betreiber) übernimmt ein falsches „gesund"; der Ausfall wird erst beim Nutzer sichtbar. | bestätigt, **Formulierung korrigiert**: DB-Ausfall liefert korrekt 503 |
| 5 ||`AUD-2026-09-071` | Critical | ReqIF-Import: `success:true` **hart kodiert** und bei vollständigem Scheitern zurückgegeben — die Antwort **listet aber alle 915 Objektfehler** | `application/reqif_import_service.py:697, 681, 415` | Ein vollständig gescheiterter Interoperabilitäts-Import wird als Erfolg gemeldet — Ursache: `SPEC-OBJECT/@IDENTIFIER` ist die globale `Artifact.id`. | bestätigt, **Beschreibung korrigiert**: kein *stiller* Fehlschlag; Ursache = Savepoint-Rettung |
| 6 ||`AUD-2026-09-120` | Critical | Alle 4 Celery-Queues identisch gebunden → **jede Task läuft 4×** | `reqogniloom/celery.py:31-36` | 4-fache Provider-Kosten und 4-fache Side-Effects — bei gleichzeitig toter Wartung (Rang 10). | bestätigt — **gestärkt** (einziger Befund, den die Gegenprüfung verstärkt hat) |
| 7 ||`AUD-2026-09-122` + `-123` | Critical | `backup.sh` ist permanent nicht ausführbar; `restore.sh` kopiert nie in den Container und lässt `psql -f` die Datei statt stdin lesen | `scripts/backup.sh:84-87`; `scripts/restore.sh:183, 186, 198-213` | Im Datenverlustfall existiert **kein dokumentierter Wiederherstellungsweg** — der dokumentierte Notfallpfad kann nie erfolgreich sein. | bestätigt |
| 8 ||`AUD-2026-09-052` (+ `-346`) | Critical (BESTAETIGT) | Anthropic-Default `claude-3-opus-20240229` ist seit 2026-01-05 retired | `llm_adapter/providers.py:1080` | Jeder Aufruf ohne `LLM_MODEL` schlägt fehl — alle KI-gestützten Ableitungen fallen ohne Zusatzkonfiguration aus. | bestätigt (Retirement-Datum 2026-01-05 unabhängig recherchiert) |
| 9 ||`AUD-2026-09-121` (+ `-270`, `-284`) | Critical (BESTAETIGT) | Beat-Dispatch unbelegt; `archive_lifecycle_manager` nicht im Task-Set; Outbox-Task verschluckt `Exception` | `settings.py:817-830`; `audit/archive.py:448`; `application/tasks.py:31-38` | Die gesamte geplante Wartung/Retention bleibt still aus, `audit_entry` wächst unbegrenzt, und 222 863 Outbox-Läufe wurden mit **0** Fehlschlägen verbucht. | bestätigt; **Beat-Teil NICHT VERIFIZIERBAR** (Log fehlt, Stack gestoppt) |
| 10 || `AUD-2026-09-115` | Critical | `_handle_slash` wirft `TypeError` — dokumentiert „never raises"; `start`/`status`/`answer` brechen live | `integrations/hermes-agent-plugin/__init__.py:79` | Der Hauptpfad des Plugins bricht beim Slash-Kommando ab; Integration ist damit nicht benutzbar. | nicht Gegenstand der Gegenprüfung |
> Rang 10 neu belegt durch `-115` (Plugin-Hauptpfad crasht live). Der
> zuvor auf Rang 10 geführte Verbund `-121`/`-270`/`-284` bleibt enthalten; `-115`
> tritt **zusätzlich** hinzu — die Auswahl umfasst damit 10 Zeilen bei
> 9 verschiedenen Vorgängen (Rang 3 und 8 fassen je 2 Findings zusammen).

**Knapp verfehlt (Rang 11–14), damit die Auswahl nachvollziehbar bleibt:**
`AUD-2026-09-137` (kein Test-vor-Image-Vertrag, kein SBOM/Cosign/Provenance —
High, aber Eintritt erst beim nächsten Release-Schnitt),
`AUD-2026-09-115` (Plugin-Hauptpfad crasht live — Critical, aber auf eine
Integration begrenzt), `AUD-2026-09-224` (kein Secret-Scan-Gate — die Ursache
von Rang 1 ist bereits eingetreten und wiederholt sich ohne Gate),
`AUD-2026-09-225` (27 von 28 Actions nur Tag-gepinnt bei `packages: write`).

---

## 6. Die fünf wiederkehrenden Fehlermuster

Das ist der eigentliche Erkenntniswert dieses Audits: nicht die 279 Einzelbefunde,
sondern die fünf Muster, die sie erzeugen. Jedes Muster nennt 2–3 belegte IDs;
die vollständige Zuordnung steht im Register.

### Muster 1 — Kontrollen, die ihre eigenen Lücken nicht sehen

> Der Ratchet ist das Kontrollinstrument des Projekts, und genau er ist die
> häufigste Fehlerquelle. Eine eingefrorene Obergrenze, ein Abgleich gegen die
> falsche Menge oder ein Coverage-Gate, das den eigenen Zweig überspringt,
> erzeugt Grünmeldung über genau die Lücke, die es schließen soll.

* `AUD-2026-09-301` — Ratchet-Obergrenze `MISSING_KEY_BASELINE = 116` macht die
  i18n-Lücke unsichtbar (`i18n-parity.test.ts:186`).
* `AUD-2026-09-193` — 511 von 10 052 Testdefinitionen laufen in keinem CI-Job
  (reproduzierbar: **443** von 8127, s. C10); `AUD-2026-09-195` — derselbe
  Release-Bericht nennt die Suite „vollständig grün".
* `AUD-2026-09-286` / `-129` — der Orchestrator-Health-Check prüft 5 von 10
  Abhängigkeiten (Redis/Worker/Beat/Outbox fehlen), während die **vollständige**
  Prüfung admin-authentifiziert existiert — unbenutzt.
* `AUD-2026-09-313` / `-314` / `-319` — Ratchet-Baselines, die selbst Kommentar-
  Rauschen (`STYLE_BRACE_BASELINE=3`) oder Fehlpositivzuschläge enthalten.

### Muster 2 — Verträge, die Erfolg versprechen, wo keiner ist

> Die Oberfläche meldet „erfolgreich" für Zustände, in denen nichts passiert
> ist. Das ist gefährlicher als ein Fehlschlag, weil der Aufrufer nicht
> nachprüft.

* `AUD-2026-09-070` / `-071` / `-349` — CSV- und ReqIF-Import melden
  `success: true` bei 0 importierten bzw. 915 fehlgeschlagenen Zeilen.
* `AUD-2026-09-115` — `_handle_slash` ist als „never raises" dokumentiert und
  wirft `TypeError`; `start`/`status`/`answer` brechen live.
* `AUD-2026-09-122` / `-123` — `/admin/restore/` und die Restore-Skripte sind
  vorhanden, aber nie erfolgreich ausführbar.
* `AUD-2026-09-125` + `-270` — `audit.archive_lifecycle_manager` ist im
  Beat-Schedule **eingetragen**, aber nie im Worker-Task-Set registriert
  (adjudiziert in C9: WP-5s „nicht reproduzierbar" ist widerlegt).
* `AUD-2026-09-121` — `celery-beat` ist `healthy` bei 0 Dispatches;
  `AUD-2026-09-138` — `build.sh` meldet „Build completed" bei **exit 0** und
  0 gebauten Images.

### Muster 3 — Doku gegen Wirklichkeit

> Dokumentierte Zahlen und Zustände, die gemessen nicht stimmen. Das erzeugt
> Fehlentscheidungen **außerhalb** der Codebasis — in Planung, Abnahme und
> Fremdintegration.

* Tool-Count `AUD-2026-09-037` (dokumentiert 215/31, **gemessen 219/35**),
  `AUD-2026-09-084` (APIViews 67 vs. **76**), Compose-Services 8 vs. **15**
  (Register §10), React 18 vs. `^19.2.8` (`AUD-2026-09-320`).
* `AUD-2026-09-191` — stdio-Handler existiert, stdio-Transport ist nicht
  exponiert, die Doku nennt drei Transporte.
* `AUD-2026-09-058` + `-324` + `-347` — `azure` ist implementiert und beworben,
  aber im DB-Enum, im REST-ChoiceField **und** im TS-Union-Typ nicht wählbar.
* `AUD-2026-09-342` — MCP-Tool `semantic_search` als `Implemented/Covered`
  dokumentiert, **existiert nicht**; `AUD-2026-09-345` — Backup/Restore als
  `Implemented/Covered`, Restore-Skript nie im Image.
* `AUD-2026-09-107` / `-108` / `-106` — `serverInfo.version` hart `1.0.0`,
  `GET /api/v1/version/` live `"unknown"`, Plugin-Version `0.1.0` statt `VERSION`.

### Muster 4 — Grenzen ohne Server-Side-Fence

> Sicherheitsgrenzen, deren Einhaltung vom **Client** abhängt. Der Server prüft
> das, was mitgeliefert wurde — nicht das, was adressiert wird.

* `AUD-2026-09-222` — der Workspace-Fence wird nur ausgelöst, wenn der Client
  eine `workspace_id` mitsendet; 269/311 mutierende Routen tun das nicht
  (Reopen-Rest zu Issue `#103`).
* `AUD-2026-09-221` — der Rate-Limit-Check läuft **vor** der AuthN
  (live belegt in `AUD-2026-09-221`-Nachtrag).
* `AUD-2026-09-176` — ohne `--reset` wird der Attribut-`kind` **nie** geändert:
  dreifach gesperrt, der Bootstrap-Befehl bleibt wirkungslos.
* `AUD-2026-09-240` — 9 aktive `admin`-Keys, **alle** ohne `expires_at` und
  **alle** ohne Workspace-Fence; `AUD-2026-09-151` — `/bluepencil/api/notes`
  liefert ohne Credential alle Notizen aller Workspaces.
* `AUD-2026-09-238` — `render_template` ersetzt Slots per naivem String-Replace
  ohne Delimitation, und der **Titel** (freiester Feldtyp im Artefakt-Modell)
  läuft ungefiltert in den Prompt.

### Muster 5 — Geteilte Zustände und nicht-idempotente Operationen

> Zustände, die von mehreren Ausführenden gleichzeitig verändert werden, und
> Operationen, deren Wiederholung nicht dasselbe Ergebnis hat. Beides erzeugt
> stillen Datenverlust statt sichtbarer Fehler.

* `AUD-2026-09-120` — Celery-Fan-out 4× durch identisch gebundene Queues;
  `AUD-2026-09-126` — `task_acks_late=False` ⇒ Worker-Kill = **endgültiger**
  Task-Verlust.
* `AUD-2026-09-281` — `as_goal` ohne `UNIQUE(lineage_id, sequence_number)` und
  ohne `version`; `max+1` unter keinem Lock forkt die Lineage.
* `AUD-2026-09-283` + `-284` — die Outbox ist at-least-once, der einzige
  Abonnent ist **nicht** idempotent (nackter INSERT, `audit_entry` ohne
  `event_id`), und der Task verschluckt `Exception` ⇒ Celery verbucht Erfolg.
* `AUD-2026-09-072` — CSV-Import ist nicht idempotent (dreifacher Import ⇒
  3 Duplikate); `AUD-2026-09-168` — ReqIF-Import ändert `current_state` **ohne**
  `version`-Bump (Lost Update / CAS-Blindstelle).

## 7. Was nachweislich gut ist — ein Audit, das nur Defekte zählt, ist unvollständig

Diese Befunde stehen **nicht** in den 279, weil sie keine Mängel sind. Sie sind
gemessen, nicht angenommen, und sie sind der Grund, warum die Gesamteinschätzung
„defekte Ränder, tragfähige Mitte" lautet und nicht „System nicht nutzbar".

| Nachweis | Zahl | Quelle |
|---|---:|---|
| **Transaktionsgrenzen**: fachliche Multi-Write-Operationen atomar, in **jedem** Lock-pflichtigen Fall Lock **vor** der Entscheidung | **12 / 12** | WP-6b, `wp6b-02-transaktionsgrenzen-matrix.md` |
| **Performance** der geprüften Hot-Path-Queries: indexgestützt, kein Seq-Scan auf großer Tabelle, kein Filesort, kein fehlender Index | **6 / 6**, **0,12–2,95 ms** | WP-6b, `wp6b-04-explain-output.md` (live `EXPLAIN`) |
| **Tenant-Isolation** über Cross-Tenant-Proben REST (120) + MCP (65) — zusätzlich greift RLS auf DB-Ebene, App-Rolle ist non-superuser **ohne** `BYPASSRLS` | **0 Leaks** | WP-1d, WP-1a, WP-6a (`wp6a-rls-db-roles.md`) |
| **Nackte `except: pass`** | **0** | WP-6b (`wp6b-01-silent-failure-inventar.md`) |
| **PII in Logs** | **0** (1888 `except`-Klauseln, breites `pass` nur an 7 Stellen) | WP-6b |
| **Stichproben-Verifikation der Belegbarkeit**: Datei, Zeile und Inhalt stimmen mit dem Kurztitel überein | **39 / 39** (0 Phantom-Findings, 0 Phantom-Inhalte) | Register § 12.4 |
| **Manifest-Drift-Guard** des MCP-Servers besteht absichtlich eingefügte Mutationen | **12 / 12** | WP-1a (`-051`) |
| **Backup-Mechanismus** — echter Restore in eine isolierte Datenbank reproduziert alle Tabellenzahlen | **15 / 15**, 0 Fehler | WP-1c |
| **Link-Typ-Katalog** konsistent offen über DB / REST / MCP / Frontend | **4 Ebenen** (Kontrolle `159`) | WP-4 |
| **Keine XXE im ReqIF-Parser** (4 Payloads, inkl. Billion-Laughs), **keine CSV-Formel-Injection**, **keine RCE-Vektoren** (`shell=True`/`eval`/`pickle`/`os.system` ⇒ 0 Treffer) | 3 Kontrollen | WP-6a N-01…N-03 |
| **RLS-Abdeckung** `pl_*`-Tabellen; **0** `.raw()` im Produktions-Backend | **29 / 31** (Kontrolle `185`) | WP-4 |
| **Reine Design-Token-Disziplin** im Frontend: 0 harte Hex-Werte, 0 Inline-Styles ⇒ Issue `#674`/`#876` wirksam | 0 Verstöße | WP-3 / `AUD-2026-09-021` (**WIDERLEGT**) |
| **`dist/`-Pakete ohne Über-Deklaration**: alle referenzierten Tools, Skills und `skills-tool-refs` existieren in der 219er-Registry | **80/80 · 82/82 · 129/129** | WP-2 §7 |
| **AuthN**: Enumerations-, Timing- und Brute-Force-Schutz wirksam; Allowlist-Mass-Assignment; kein Path-Traversal im Restore (`UUID` statt Pfad, `RESTORE`-Bestätigung doppelt geprüft) | Kontrollen N-04/N-05 | WP-6a |
| **Provider-Resilience**: 401/403/400 non-retryable (1 Versuch), 429/5xx transient — live gemessen; Circuit-Breaker pro Tenant auf LLM-Pfaden; SSRF-Guard mit IPv4-mapped-IPv6 | 1 vs. 12 Versuche | WP-1b |
| **Fehlerpfade der Plugins**: kein Stacktrace-Leak, kein Key im Log; `/mcp/sse/` ist **kein** Phantom (vollständiger Handshake live gefahren) | 2 Plugins | WP-2 §7 |
| **Test-Skip-Quote** mit Grund: alle 13 Marker backend-seitig tragen ein `reason=`; 0 `unittest.skip`; 0 `it.skip`/`it.todo` im Frontend | 13 / 10 052 = 0,13 % | WP-5 §6.1 |

**Was daraus folgt:** Die Priorität der Behebung liegt auf den *Rändern* —
Fehlersignalisierung, Fences, Idempotenz, Betrieb — nicht auf einem Umbau der
Domänen- oder Service-Schicht. Der Backlog folgt genau dieser Lesart.

---

## 8. Vergleich mit dem Vor-Audit

**Vor-Audit:** [`docs/se/reports/deep_audit/system-audit-2026-09/`](../../../se/reports/deep_audit/system-audit-2026-09/)
— Prüf-HEAD `e3df119e`, Branch `feat/1031-bluepencil-host-bridge`, 47 kanonische
Tracks `CR-01`…`CR-47` aus 109 Quellbefunden, **System Health Score 1,4/5**,
0 konsolidierte P0, 20 P1 / 26 P2 / 1 P3. **Keine Datei dieses Vor-Audits wurde
überschrieben oder gelöscht.**

### 8.1 Der entscheidende Unterschied: Belegtiefe

| | Vor-Audit | Dieser Audit |
|---|---|---|
| Browser-Nachweis | **keiner** („kein vollständiger Playwright-Lauf") | 28 Screens live, Login + Console- + Netzwerkmatrix je Screen |
| Live-MCP-Nachweis | **keiner** („kein MCP-Client-Lauf", R02) | 82 Rohpaare + 65-Fall-Isolationsmatrix gegen echten 2. Tenant + Redis-Ausfall-Simulation |
| Plugin-E2E | **keiner** | beide Hermes-Plugins end-to-end über eigene Requests; Claude Code + Antigravity über SSE-Handshake |
| Restore-Nachweis | **keiner** | **echter Restore 15/15** in isolierter DB + Defektisolierung im Wegwerf-Container |
| CVE-/Supply-Chain-Nachweis | **keiner** (0 bestätigte verwundbare Pakete im Audit ≠ „0 Schwachstellen") | **ebenfalls keiner** — Trivy/MTTG-Zeitwerte im Messfenster nicht gelaufen (BLOCKED) |
| CI-Baseline | Berichte `R01`–`R04`, `R06` nicht auf `e3df119e` aktualisiert | einheitliche Basis `main` @ `abd61aed` für alle 11 WP |

> **Feststellung:** Der Vor-Audit hatte **keine** Browser-, Live-MCP-, Plugin-E2E-
> oder Restore-Nachweise. Dieser Audit hat sie. Der CVE-Teil bleibt in **beiden**
> Audits unbelegt.

### 8.2 Bestätigt (gleiche Defektklasse am aktuellen Code wiedergefunden)

| Vor-Audit-Track | Status in diesem Audit | Befunde |
|---|---|---|
| `CR-11` Datenintegration | **bestätigt + verschärft** (3 Round-Trip-Bruchstellen) | 070, 071, 072, 074, 076, 077, 079, 080, 082, 086, 087 |
| `CR-12` OpenAPI/Vertragsdrift | **bestätigt** | 070, 058, 075, 078, 081, 085, 090, 091 |
| `CR-42` Source-of-Truth | **bestätigt** | 070, 071, 058, 076, 083, 306, 092, 313, 314, 315 |
| `CR-20` LLM-Budget/Tracking | **bestätigt, Severity relativiert** (self-hosted P1 → P2, policyabhängig P1) | 052, 053, 055, 061, 062, 054, 059, 063, 065 |
| `CR-37` Backup/Restore | **bestätigt + verschärft**, Mechanik-Seite **teilweise entkräftet** | 122, 123, 124, 127, 128 |
| `CR-09` Matrix-Drift | **bestätigt + verschärft** (324 fehlende IDs, 0 von 354 REQ-L3 publiziert) | 330, 331, 155, 202 |
| `CR-40` i18n/Navigation | **bestätigt** | 002, 003, 008 (+ 016, 300, 301, 303, 304) |
| `CR-41` a11y/Semantik | **bestätigt** | 302, 308, 310, 311, 316, 317, 318 |
| `CR-31` E2E/Design-System | **bestätigt** | 309, 310, 311, 014, 312, 318 |
| `CR-45` GitHub-Actions-Injection | **verschärft** (27/28 nur Tag-gepinnt bei `packages: write`) | 225, 230 |
| `CR-35` Performance/Redis | **bestätigt** (aber: die Hot-Path-Hypothesen sind **widerlegt**, s. WP-6b) | 120, 126, 130, 131, 141, 147, 144 |
| `CR-17` Modelle ohne `tenant_id`/RLS | **erweitert von 2 auf 5 Modelle** | 184 |
| `CR-10` Audit-Archivierung | **bestätigt + quantifiziert** (`audit_entry` wächst unbegrenzt) | 270, 179 |
| `CR-30` CI-Testlücke | **Defektklasse bestätigt, Zahl endgültig geklärt**: 463 → **511** → **443 reproduzierbar** (C10), **unabhängig bestätigt** (K-6) | 192, 193, 198, 048 |
| `CR-25` Bluepencil | **voll bestätigt, beides gemessen** | 150, 151 |
| `CR-28` MCP-Session-ID | **live bestätigt** (Session-ID im Query-String jedes Proxy-Logs) | 041 |
| `CR-32`/`CR-38` Supply Chain | **bestätigt** (kein SBOM/Cosign/Provenance, kein Digest-Pinning) | 137, 136 |
| `CR-05`/`CR-06`/`CR-07`/`CR-13`/`CR-14`/`CR-15`/`CR-16`/`CR-21`/`CR-22`/`CR-26`/`CR-33`/`CR-36`/`CR-43`/`CR-47` | **jeweils mit mindestens einem Befund bestätigt oder als Nachbarschaft eingeordnet** | siehe Register § 3, Spalte „CR-Track / Issue" |

**Insgesamt: 34 der 47 Vor-Audit-Tracks haben mindestens einen zugeordneten
Befund; 13 Tracks haben keinen** — `CR-01`…`CR-04`, `CR-18`, `CR-19`, `CR-23`,
`CR-27`, `CR-29`, `CR-34`, `CR-39`, `CR-44`, `CR-46`. Das ist **keine** Entwarnung
für diese 13: sie wurden entweder nicht erneut geprüft oder sind ohne CR-Nennung
subsumiert (z. B. `CR-03`/Workspace-Fence → `AUD-2026-09-222`).

Ein Sonderfall ist `CR-23` (Plugin-Allow-/Blocklisten als Prompt-Governance):
WP-2 ordnet den Track in seiner Reconciliation (§ 6) dem Befund
`AUD-2026-09-113` zu — die **Master-Tabelle des Registers führt diese Zuordnung
aber nicht** (`113` nennt keinen CR-Track). Das ist eine Lücke der
CR-Traceability **innerhalb** des Registers, kein fehlender Befund.

### 8.3 Widerlegt (Vor-Audit-Aussage am aktuellen Code nicht haltbar)

| Vor-Audit | Aussage | Ergebnis | Beleg |
|---|---|---|---|
| **`CR-08`** | Workflow-Transition validiert **vor** dem Lock ⇒ Race | **WIDERLEGT / behoben** — validiert **nach** dem Lock, mit expliziten `CR-08:`-Kommentaren und Lock-Weitergabe an `perform_transition` | `AUD-2026-09-166` (**WIDERLEGT**), `workflow/services.py:302-341` |
| **`CR-24`** | „Hermes-TS und Python-Agent-Plugin sind parallele, **nicht live verifizierte** Verträge" | **WIDERLEGT im Kern** — beide **sind** live verifizierbar und wurden verifiziert. Sie bleiben parallel, sind aber nicht gleich kaputt: TS funktioniert, der Python-Hauptpfad crasht | `AUD-2026-09-152` (**WIDERLEGT**), `AUD-2026-09-115` |
| **`CR-22`** (Teil) | „HTTP/SSE-Timeout-Divergenz, Header sind dekorativ" | **Timeout-Teil widerlegt** (beide Clients 15 000 ms, live exakt bei 15005 ms); der dekorative-Header-Teil **präzisiert**: `X-API-Key` **ist** die Scope-Quelle, live bewiesen (80 Read-Tools bzw. 403) | WP-2 §6 |
| **Embedding-Dimension** | dimensionsfremde Einbettung könne Laufzeitfehler auslösen | **Prämisse widerlegt** — alle 4 Spalten `vector(384)` über **eine** SSOT-Konstante; jeder Write-Site prüft vorher. Rest: stille Degradation, als `DUPLIKAT` zu `#1019` geführt | C8, `AUD-2026-09-143` |
| **`CR-20`** (Severity) | P1 Budget-Lücke | **relativiert**: P1 → P2 (self-hosted), policyabhängig P1 | WP-1b-Reconciliation |
| **`#940`** | offener Blocker Attribut-`kind` | **Issue `#940` ist geschlossen**; der reale Blocker ist `#1112` — **bestätigt und dreifach gesperrt** statt einfach | `AUD-2026-09-176` |
| **`#1115`/`#711`** | i18n-Maskierung offen | beide Issues **geschlossen**, Wirkung besteht fort | `AUD-2026-09-001` |

### 8.4 Neu — Befunde ohne Vor-Audit-Vorgänger

* **179 der 285 Master-Zeilen nennen keinen `CR-Track`**, darunter **7 der 14
  Critical** (`030` Redis-Hänger, `031` Health-Lüge, `121` Beat tot, `220`
  Secret-Leak, `221` Rate-Limit vor AuthN, `345`/`346` Anforderungs-Realität).
* **Vollständig neue Themenbereiche**, die der Vor-Audit als Textsorte nicht
  hatte: der **Restore-Nachweis** (15/15 erfolgreich **und** beide Skripte tot),
  die **Plugin-Live-E2E**, der **Session-ID-als-URL-Credential**-Befund,
  `as_goal` ohne `UNIQUE` (`281`), der **Outbox-Idempotenzbruch** (`283`/`284`),
  die **Audit-Trail-`entity_version`-Lücke** (97,7 % NULL, `285`), die
  **`task_acks_late=False`**-Konsequenz (`126`) und die **Staging-Lücke**
  (`149`, keine `environment:`/`concurrency:` in irgendeiner CI-Datei).

### 8.5 Diskrepanz, die nicht aufgelöst wurde

Der Vor-Audit nennt 463 nicht ausgeführte Testdefinitionen, WP-5 nennt 511, die
reproduzierbare Zahl ist **443 von 8127**. Das Register hat die Methode offengelegt
(C10) und die Frage als **offenen Punkt O-6** an den User gegeben. Diese Synthese
trifft **keine** Entscheidung; sie nennt **443** als die einzige mit offengelegter
Methode belegbare Zahl.

## 9. Was **nicht** geprüft wurde

**BLOCKED ist ausdrücklich kein PASS.** Vollständige Listen:
[`AUDIT_FINDINGS.md` § 7.1 (6 BLOCKED-Findings)](AUDIT_FINDINGS.md) und
[§ 7.2 (12 offene Prüfpunkte)](AUDIT_FINDINGS.md).

### 9.1 Als BLOCKED geführte Findings

| ID | Schwere | Gegenstand | Grund |
|---|---|---|---|
| `AUD-2026-09-178` | Medium | 3/11 Item-Types materialisieren nie; 134/401 Workspaces ohne Attribut-Katalog | Teilbefund belegt, Rest braucht schreibende Daten |
| `AUD-2026-09-205` | Low | Health-Aggregation bei Totalausfall | statisch nicht entscheidbar, Messung am laufenden Stack nötig |
| `AUD-2026-09-023` | Info | Workspace-Löschen-Bestätigungsdialog | kein sicherer Trigger ohne Datenverlust |
| `AUD-2026-09-024` | Info | Diagrammeditoren, Create-Dialoge, Baseline-Compare | Workspace enthielt 0 Datensätze dieser Typen |
| `AUD-2026-09-025` | Info | Tastaturkontrast, `prefers-reduced-motion` | keine Axe-Messung, keine Animation im Testfenster auslösbar |
| `AUD-2026-09-190` | — | Diff-Engine-Korrektheit | ohne Mutation nicht messbar — explizit **kein PASS** |

### 9.2 Themen, die ohne Ausführung blieben (Auswahl, nach Risiko gewichtet)

| Thema | Grund | Findet sich in |
|---|---|---|
| **Stack-Erzeugung / Restore-Abbruch mitten drin** (die eigentliche Nicht-Atomizität) | `pg_restore --clean --if-exists` zielt auf den **Live**-Postgres-Container; ein Abbruch hätte die von Parallel-Audits genutzte DB halb abgeräumt | WP-1c §12 |
| **CVE-Scan / SBOM / MTTG-Zeitwerte** | kein CI-Lauf dieses Branches im Messfenster; Trivy hängt an einem Tag-Trigger — **nicht** als PASS gewertet | WP-1c §12 |
| **LLM-Provider-Keys / echte Provider-Antworten** | keine Keys im Audit-Umfeld; `LLM_PROVIDER`-Umschaltung hätte den geteilten Container verändert. Request-Formate wurden per Capture gegen einen Stub feldweise verifiziert — **echte Antworten nicht** | WP-1b |
| **Auth-Flow mit manipulierten JWTs** (`exp` abgelaufen, `aud`/`iss` fremd) | hätte `AUTH_JWT_SECRET` aus dem Container-Environment gebraucht; getestet wurden nur strukturell manipulierte Tokens (falsche Signatur) | WP-1d §12 |
| **Token eines deaktivierten Users / nach Rollenentzug** (`CR-26`) | hätte dauerhafte Rollen-/Statusmutationen gebraucht; Probe-User wurde nach dem Test gelöscht, Sequenz bewusst nicht gefahren | WP-1d §12 |
| **Celery-Broker-Ausfall gegen Live-Worker / Doppelzustellung auf dem echten Broker** | ein Publish in db0 hätte die Worker der Parallel-Audits beeinflusst; der Fan-out ist stattdessen **vollständig isoliert** über kombu `memory://` bewiesen | WP-1c §12 |
| **`celery-beat`-Root-Cause des Nicht-Dispatchens** | erfordert Neustart bzw. Debugging im laufenden Prozess | WP-1c §12 |
| **Rate-Limit-Auslösung** | bewusst nicht ausgelöst, um parallele Audit-Agenten nicht zu blockieren | WP-1a |
| **Frontend-Bundle-Größe / ungenutzte Libraries / tote Dateien** | kein `vite build`; bräuchte Import-Graph über Modulgrenzen | WP-3b §13 |
| **Last-/Skalierungsverhalten** (Mehr-Worker, `CONN_MAX_AGE` unter Last, 42 Redis-Clients) | Lasttest gegen den von Parallel-Agenten genutzten Stack | WP-1c §12 |
| **Echter Ollama-Server**, Circuit-Breaker-Zyklus live, `TENANT_TOKEN_LIMIT_PER_DAY` im Grenzfall, Kosten gegen echte Rechnungen | kein Ollama im Stack; Grenzfall strukturell nie erreichbar (Variable unset) | WP-1b |
| **Typ-Drift TS ↔ Django-Serializer** | nur Stichprobe, kein Schemasvergleich | WP-3b §13 |
| **`/admin/` tatsächlich erreichbar und Brute-Force-anfällig** | live 500 wegen fehlendem Static-Manifest im **Audit**-Stack; im Produktions-Image ist ein Manifest vorhanden ⇒ die 500 gilt nicht allgemein (C12) | WP-6a |
| **`AGENTS.md:16` „111 E2E-Tests"** | kein Playwright-Lauf | WP-5 |
| **Vollständige PII-/Secret-Prüfung aller Log-Aufrufe** | Stichprobe aus Live-Logs; statische Vollprüfung nicht im Auftrag | WP-1c §12 |

---

## 10. Audit-interne Prozessdefekte

> Dieser Abschnitt ist **kein** Produktbefekt und **nicht** Teil der 279 Findings.
> Er wird offengelegt, weil er die Aussagekraft dieses Audits einschränkt — nach
> demselben Grundsatz, mit dem das Audit Produktdefekte offenlegt. Vollständig in
> [`AUDIT_FINDINGS.md` § 14 (P-1…P-5)](AUDIT_FINDINGS.md).

> ### Das Audit hat selbst ein Secret committet
>
> `AUD-2026-09-220` / **P-1 (Critical)**: Ein **live gültiges `write`-API-Key**
> wurde im Evidenz-JSON committet (Commit `3dcc80d8`). Der Key ist am
> **2026-09-30 widerrufen** (HTTP 204, `revoked_at = 2026-09-30 19:07:05+00`;
> verifiziert über `tools/list` 200 → 401), der Arbeitsbaum ist redigiert
> (`rg 'reqlo_[A-Za-z0-9]{30,}' docs/audit/` ⇒ 0 Treffer).
> **Offen bleibt: die Git-Historie.** `3dcc80d8` wurde nie gepusht, daher ist
> Option A (`filter-repo`, kein Force-Push nötig) technisch möglich — sie wurde
> **empfohlen und nicht ausgeführt** (offener Punkt O-7).
> Prozessursache ist `AUD-2026-09-239` (High): kein Evidenz-Redactor, und der
> Cleanup prüfte die User-Löschung, aber nie den Key-Widerruf.
> Ein **zweiter** live Key `ff77bbd0-…` in `AUDIT_EVIDENCE/stack-seeds.md`
> wurde **eskaliert, auftragsgemäß aber nicht widerrufen** (HTTP 200).

| # | Prozessdefekt | Schwere | Status |
|---|---|---|---|
| **P-1** | Das Audit committete selbst ein live gültiges API-Key | **Critical** | Key widerrufen + Arbeitsbaum redigiert; **Historie offen** (O-7) |
| **P-2** | Zwei Agenten schrieben parallel in dieselbe Datei (`AUDIT_EXTERNAL_INTEGRATIONS.md` trägt WP-1a, WP-1d und WP-1b) | Medium | Inhalt heute vollständig (Zwischenverlust beim Append erkannt und wiederhergestellt), Mechanismus ungeschützt |
| **P-3** | **27 ID-Kollisionen** (K1 `240/241`, K2 `150–153`, K3 `170–190`) durch blockweise Vergabe ohne Reservierung | Medium | behoben (0 Duplikate, § 12.2a) |
| **P-4** | ID-Block `050/051` doppelt vergeben — dieselbe Datei, deshalb kein Dateikonflikt | Low | behoben |
| **P-5** | **Messfehler, die zu Phantom-/Über-Befunden führten — und aktiv korrigiert wurden** | Info | behoben; **zwei der drei Korrekturen haben die Befundmenge erhöht** (i18n 112 → 116; stale Selektoren 0 → 3), eine hat sie reduziert (441 → 0 Hex, als `WIDERLEGT` sichtbar, nicht aus der Zählung entfernt) |

**Was P-5 für die Belastbarkeit bedeutet (ohne Beschönigung):** Für WP-3/WP-3b
stammen die maßgeblichen Zahlen aus einer **zweiten, methodisch korrigierten**
Messung. Für die WPs **ohne** zweite Messung ist die Validität der Zahlen
**nicht** durch eine unabhängige Gegenmessung abgesichert. Das ist eine
**Restunsicherheit dieses Audits** — keine Feststellung zu einem Produktdefekt.

---

---

## 11. Unabhängige Gegenprüfung der Top-10 (2026-09-30)

Eine zweite, vom Haupt-Audit unabhängige Prüfung (Agent `code-reviewer`,
Commit `27a72dde`) hat die **10 kritischsten Findings** dieses Audits gegen
Quelltext, committete Evidenzartefakte und eigene Messungen geprüft.
Vollständige Rohdaten:
[`AUDIT_EVIDENCE/verification-2026-09-30.md`](AUDIT_EVIDENCE/verification-2026-09-30.md).

### 11.1 Einschränkung der Evidenzbasis — vorrangig zu lesen

> ### ⚠ Die Gegenprüfung hatte **keine** Live-Evidenz
>
> Sie fand den Stack **gestoppt**: `docker ps` scheitert an der Docker-Engine,
> `com.docker.service` = `Stopped`, und **alle** Ports (8000, 8001, 5432, 6379,
> 3000, 5173) waren ohne Verbindung. **0 Live-Messungen** waren möglich.
>
> Sie hat stattdessen **statisch und hermetisch** gemessen — lokale Celery-App mit
> **wörtlicher** Produktionskonfiguration, Code-Nachverfolgung, hermetische
> Wiedergabe einzelner Funktionen, Nachrechnen gegen **committete** Artefakte.
>
> **Das ist eine gültige, aber schwächere Evidenzbasis als die Live-Prüfung des
> Haupt-Audits.** Jede Bestätigung aus dieser Gegenprüfung ist deshalb zu lesen
> als: *statisch/hermetisch bestätigt — Live-Nachweis nicht möglich (Stack
> gestoppt)*.
>
> Umgekehrt gilt: eine **Widerlegung** ist auf dieser Basis **belastbarer** als
> eine Bestätigung, weil sie nicht vom Stack abhängt. Genau deshalb trägt die
> Zurücknahme von `-070` auch ohne Live-Nachweis.

### 11.2 Ergebnis

| Urteil | Anzahl |
|---|---:|
| bestätigt | **6** |
| bestätigt, aber Beschreibung ungenau | **3** |
| **WIDERLEGT** | **1** |
| gänzlich unverifizierbar | **0** |
| *davon Teilaussagen nicht verifizierbar* | *13* |

**K-1 — `AUD-2026-09-070` ist widerlegt und wurde zurückgezogen.**
`backend/application/import_service.py:341-344` strippt jede mit `#` beginnende
Zeile vor `csv.DictReader`. Export-Kommentar und Strip stammen aus **demselben**
Commit `3081435a` — der Pfad war nie inkonsistent. Hermetische Gegenmessung des
wörtlichen `_parse_csv` gegen echten Export-Output: **16 Headerfelder, 1
Datenzeile, `title='CLEAN-1'`**. Der A/B-Test des Haupt-Audits variierte zwei
Variablen gleichzeitig und konnte die Behauptung nicht stützen.
**Folge:** Critical **14 → 13**, offene Findings **280 → 279**, Top-10 ohne `-070`.
Das Finding bleibt als `WIDERLEGT` sichtbar — es wird nicht gelöscht.

**Drei Beschreibungen wurden korrigiert, ohne dass ein Schweregrad sank:**

* `-220` — der Commit `3dcc80d8` wurde **nie gepusht** (`merge-base --is-ancestor`
  exit 1); es gab **kein** PR und **keinen** Fork. Die Aussage „jeder PR-Autor und
  jeder Fork hatte ein gültiges Credential" ist widerlegt und gestrichen. Der Kern
  (Key war committet und live gültig) bleibt, Critical bleibt.
* `-071` — `success=True` ist hart kodiert, aber die Antwort **listet alle
  Fehler**. „Stiller Fehlschlag" ist zu streichen; die Ursache ist die
  **unwirksame Savepoint-Rettung**, nicht primär der globale PK-Konflikt.
  Critical bleibt.
* `-031` — bei **DB-Ausfall** liefert `/health/` korrekt 503. Der belegte Fehlfall
  ist der Cache-/Redis-Ausfall. Critical bleibt.

**Ein Befund wurde gestärkt:** `-120` (Celery-4×-Fanout) — die Gegenprüfung hat
Prämisse und Konsequenz unabhängig gemessen und die Gegenhypothese
„ein Consumer liest 4 Queues, konsumiert aber einmal" ausdrücklich widerlegt.

**Eine Teilaussage als nicht verifizierbar markiert:** bei `-121` ist der
Beat-Teil (`0 × Sending due task`) unbelegt — das Log ist nicht im Repo und der
Stack war aus. Er wird **nicht** gestrichen, sondern als `NICHT VERIFIZIERBAR`
mit dem fehlenden Prüfschritt geführt. Die Healthcheck-Aussage und `-270`
gelten.

### 11.3 Drei unabhängig nachgezählte Zahlenpaare

| Zahlenpaar | Ergebnis | Urteil |
|---|---|---|
| MCP-Tools | **219 Tools / 35 Präfixe**; 219 − 139 `is_write` = **exakt 80** | bestätigt — die 80 sind ein Rollenfilter, kein Registrierungsfehler |
| `MISSING_KEY_BASELINE` | **116** | bestätigt (Ratchet-Quelltext ist der belastbare Pfad) |
| Tests ohne CI | **443** (34 von 658 Dateien) | bestätigt — **463 und 511 sind mit dieser Methode nicht reproduzierbar** |

**Offene Frage O-6 ist damit aufgelöst: die kanonische Zahl ist 443.**

### 11.4 Belastbarkeitseinordnung

> **Aussage zur Belastbarkeit dieses Audits — kein Produktbefund.**

1. **Nur eine Zählung hat zwei unabhängige Wege:** die i18n-Lücke
   (`MISSING_KEY_BASELINE` = 116), einmal durch WP-3b gemessen und einmal durch
   die Gegenprüfung aus der Ratchet-Quelle nachgezählt — **übereinstimmend**.
2. **Für alle übrigen Zählungen liegt je eine Messung vor.** Die Gegenprüfung hat
   die 219/35 Tools und die 443 Tests nachgerechnet, aber teils aus **denselben**
   Evidenzartefakten, die das Haupt-Audit erzeugt hat. Das ist kein Fehler, aber
   auch **keine** zweite unabhängige Messung.
3. **Für die 13 offenen Teilaussagen gilt:** die zugrunde liegende Behauptung ist
   **nicht widerlegt, sondern unvollständig belegt.** Der jeweils fehlende
   Prüfschritt steht in `AUDIT_FINDINGS.md` §15.4.
4. **Richtung der Korrekturen:** 1 Widerlegung (Qualitätsgewinn — ein Fehlbefund
   wurde entfernt), 3 Präzisierungen ohne Schweregradwechsel, 1 gestärkter
   Befund, 13 offene Teilaussagen. Das Audit ist dadurch **nicht** insgesamt
   verschärft, aber einzelne Aussagen sind korrigiert worden.

**Vor einer Investitionsentscheidung, die sich allein auf eine der 13 offenen
Teilaussagen stützt, gehört der zugehörige Prüfschritt aus §15.4 nach.**

---

## 12. Wie es weitergeht

| Frage | Antwort |
|---|---|
| Was ist jetzt zu tun? | [`AUDIT_BACKLOG.md`](AUDIT_BACKLOG.md) — 35 priorisierte Einträge, davon 6 × P0 |
| Was braucht eine Architekturentscheidung? | [`AUDIT_ADR_CANDIDATES.md`](AUDIT_ADR_CANDIDATES.md) — 8 Kandidaten mit Optionen und Trade-offs. **Es wurde keine ADR geschrieben.** |
| Wo sind die Rohdaten? | [`AUDIT_FINDINGS.md`](AUDIT_FINDINGS.md) (Register) → WP-Reports → [`AUDIT_EVIDENCE/`](AUDIT_EVIDENCE/) |
| Was ist offen und braucht eine User-Entscheidung? | [`AUDIT_BACKLOG.md` § „Vor Phase 2 zu klären"](AUDIT_BACKLOG.md) (History-Rewrite, geschlossene Issues, `CR-30`-Zahl, Doku-Drift) |
---

*Erstellt von `documenter` am 2026-09-30. Synthese ohne neue Fachanalyse; alle
Zahlen aus [`AUDIT_FINDINGS.md`](AUDIT_FINDINGS.md). Vor-Audit unverändert.*




