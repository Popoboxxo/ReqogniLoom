---
adr_id: ADR-010
title: "Health-Vertrag: getrennte Liveness- und Readiness-Endpunkte mit fail-closed Readiness"
status: proposed
date: "2026-10-01"
deciders: [api-specialist]
affected_reqs: [REQ-L1-032, REQ-L0-021, REQ-060, REQ-063, REQ-L2-AT-007]
superseded_by: null
---

# ADR-010: Health-Vertrag: getrennte Liveness- und Readiness-Endpunkte mit fail-closed Readiness

**Status:** proposed
**Datum:** 2026-10-01
**Entscheider:** api-specialist (Autor); **Entscheidungsinstanz:** user
(**Freigabe noch ausstehend** — deshalb `status: proposed`, nicht `accepted`)
**Betroffene REQs:** REQ-L1-032 (Resilienz — Fehlertoleranz und Graceful Degradation),
REQ-L0-021/SN-21 (Asynchrone, resiliente Systemkommunikation), REQ-060 (Healthchecks für
Backend und Celery), REQ-063 (Observability-Grundausstattung), REQ-L2-AT-007 (Auth Middleware
Interception — `/health` ohne Token)
**Bezug:** `docs/audit/2026-09/AUDIT_ADR_CANDIDATES.md:125-171` (Kandidat #3, Optionen A/B/C);
`docs/audit/2026-09/review/plan/RESILIENCE_HEALTH.md:58-77` (RES-03);
`docs/audit/2026-09/review/plan/INTERFACE_CONTRACTS.md:216-325` (§3), `:550-576` (§7.1);
Findings `AUD-2026-09-031` (Critical), `-129` (High), `-139`/`-275`/`-286` (Medium)

---

## Kontext

### Ist-Zustand (gegen den Code geprüft)

Es gibt heute **genau einen** Health-Endpunkt. `backend/reqogniloom/urls.py:28` registriert
`path("health/", HealthView.as_view(), name="health")` — und nichts sonst. Der Docstring
des Views verspricht dagegen **zwei** Endpunkte: „Implements both /health/ready (readiness)
and /health/live (liveness) patterns" (`backend/reqogniloom/health.py:1-5`). Beide
existieren **nicht** (Finding `-275`). Es fehlt also genau die Unterscheidung, die ein
Orchestrator braucht: *„der Prozess lebt"* vs. *„die App ist benutzbar"*
(`AUDIT_ADR_CANDIDATES.md:132-141`; `AUDIT_INFRASTRUCTURE.md:314-337`).

`HealthView.get` (`health.py:118-315`) prüft `database`, `memory_backend`,
`embedding_dimensions` (Warning/200), `llm_provider_env` (Warning/200),
`csrf_cookie_secure_matches_auth` (Warning/200) und die Workflow-Definitionen.
**Nicht geprüft** werden Cache/Redis, Celery-Worker und Beat — obwohl diese Abhängigkeiten
den Betrieb tragen (`RESILIENCE_HEALTH.md:65-66`; Finding `-286`, „5 von 10").

Die **vollständige** Probe existiert bereits, ist aber unbenutzt für den Container-Check:
`backend/admin_ops/health_rest.py:96-197` enthält `_check_redis` (`:96-110`),
`_check_celery_worker` (`:113-132`) und `_check_celery_beat` (`:135-198`); die Klasse
`SystemHealthView` (`:517-547`) ist über `Operation.WORKSPACE_CONFIG` **admin-only**
geschützt. Der Compose-Healthcheck des Backends prüft derweil nur
`curl -f http://localhost:8000/health/` (`deploy/docker-compose.yml:642`).

### Korrektur einer Audit-Aussage (wichtig für den Gegenstand)

Die Behauptung, `degraded` liefere HTTP **200** (`AUD-2026-09-129`), ist **widerlegt**: der
Code setzt bei `degraded` bereits **503** (`health.py:134-135` für `database` und
`:160-161` für `memory_backend`). `RESILIENCE_HEALTH.md:61-64` hält das ausdrücklich fest.
Der Entscheidungsgegenstand ist daher **nicht** „ein 503-Bugfix", sondern
(a) die **Endpunkt-Topologie** (ein vs. zwei Endpunkte) und (b) die **Readiness-Semantik**
fail-closed vs. degraded-200 für die heute ungeprüften Pflicht-Abhängigkeiten
(Cache, Worker, Beat). Das ist die Lücke, die offen bleibt.

### Präzedenz, den der Code schon zieht

`health.py:176-181` begründet, warum `embedding_dimensions` bewusst Warning/200 statt 503
ist: ein Container-/k8s-Liveness-Probe darf einen Stack, der noch Traffic bedient, **nicht
in einen Restart-Loop** zwingen. Genau diese Begründung ist das Argument dafür, Liveness und
Readiness zu **trennen** und die Abhängigkeitsprobe nicht auf denselben Endpunkt zu legen,
den ein Liveness-Probe pollt.

### Keine bestehende Anforderung formuliert diesen Vertrag

Es gibt **keine** REQ, die die Health-/Readiness-Semantik (Statuscode bei `degraded`,
Trennung von `live`/`ready`, Pflicht-Abhängigkeitsliste) festschreibt — das ist die Lücke,
die dieser ADR schließt. Die am **nächsten** liegende belegte Anforderung ist
`REQ-L1-032` („Resilienz-Anforderung — Fehlertoleranz und Graceful Degradation",
`docs/se/L1/Gesamtsystem/L1_Gesamtsystem_Requirements.md:1086-1111`;
`docs/se/traceability-matrix.md:130`): sie fordert Verfügbarkeit der Kern-Systeme > 99,5 %
und dass Rand-Ausfälle **nicht kaskadieren**. Weitere belegte Bezüge: `REQ-L0-021`
(Elternal/SN-21, `docs/se/L0/SN_Stakeholder_Needs.md:542-566`;
`traceability-matrix.md:50`), `REQ-060` (Healthchecks, `docs/REQUIREMENTS.md:91`),
`REQ-063` (Observability, `docs/REQUIREMENTS.md:94`; referenziert in `urls.py:27`) und
`REQ-L2-AT-007` (Auth-Ausnahme für `/health`,
`docs/se/L1/Gesamtsystem/L2/AuthAndTenancySystem/L2_AuthAndTenancySystem_Requirements.md:235-249`;
`traceability-matrix.md:300`).

**Zuordnungs-Status (offen):** Die Zuordnung dieses ADR zu den genannten REQs ist eine
**Näherung**, keine bereits getrackte Verknüpfung. `open_adrs` existiert repo-weit nicht
(0/835 REQs, `AUD-2026-09-333`) — die REQ↔ADR-Rückverfolgbarkeit kann heute nicht
maschinell eingetragen werden und bleibt eine Folgeaufgabe (siehe Konsequenzen). Es wird
**keine** REQ neu erfunden und **keine** REQ-Datei geändert.

### Abgrenzung

- Kein bestehender ADR regelt den Health-Vertrag (`AUDIT_ADR_CANDIDATES.md:154-161`).
- `ADR-002_Event-Bus.md` betrifft die Zustellung, **nicht** die Verfügbarkeit — kein
  Konflikt.
- Der Gegenstand ist **Laufzeit-Verfügbarkeit**, nicht die Herkunft von Preset-Regeln
  (`ADR-007`) und nicht das Träger-/AUC-Modell (`ADR-004`, `proposed`).

---

## Alternativen

### Option A: Ein Endpunkt, strikt fail-closed — VERWORFEN

**Beschreibung:** Es bleibt bei **einem** Endpunkt. Er prüft alle benötigten Abhängigkeiten
inkl. Cache, Worker und Beat und liefert bei jeder degradierten Pflicht-Abhängigkeit 503.
Kein getrennter Liveness-Punkt.

**Abwägung:** Die Semantik ist klassisch und gut verstanden, und der Statuscode allein wäre
verlässlich. Der Preis ist jedoch genau der Fehler, den `health.py:176-181` bereits als
Restart-Loop-Risiko benennt: Ohne eigenen Liveness-Punkt muss ein Orchestrator **denselben**
Endpunkt als Liveness-Probe verwenden. Ein Redis-Ausfall (eine Rand-Abhängigkeit) würde
dann nicht nur die Oberfläche aus dem Load-Balancer nehmen, sondern den Container als „tot"
markieren und **neu starten** — obwohl der Prozess lebt und redis-freie Teile weiter bedienen
könnte. Das widerspricht `REQ-L1-032` („Ausfälle in Randbereichen dürfen nicht kaskadieren",
`L1_Gesamtsystem_Requirements.md:1090-1092`) und der verlangten Trennung. Zusätzlich
verschärft es das in `AUDIT_ADR_CANDIDATES.md:150` genannte Risiko (Redis-Ausfall nimmt die
gesamte Oberfläche aus dem LB, auch redis-freie Teile).

**Risiko:** HOCH als Betriebsinvestition — ein Rand-Ausfall kann zum Restart-Loop des
Gesamt-Containers werden.

---

### Option B: Ein Endpunkt, `degraded`=200 + Pflichtliste + auswertendes Gate — VERWORFEN

**Beschreibung:** `/health/` bleibt bei 200, aber `status` wird `degraded` und der Body
listet **verpflichtend** jede ausgefallene Abhängigkeit (Name, Status, statischer Marker).
Compose-/CI-Gates werten **die Liste** aus, nicht den Statuscode.

**Abwägung:** Das nimmt verfügbare Funktionalität nicht unnötig aus dem Load-Balancer und
macht Details sichtbar. Es **verlagert die Lücke aber nur**: Jedes Gate, das nur den
Statuscode liest (und das ist die Regel — heute tut es `docker-compose.yml:642` mit
`curl -f`), bleibt **falsch-grün**. Genau das belegt der Critical-Befund `AUD-2026-09-031`:
`/health/` meldete `200 {"status":"ok"}`, während App, Auth und Schema unbenutzbar hingen.
Die Pflichtliste allein genügt nicht; sie erzwingt eine **Gegenauswertung** in jedem
Konsumenten — teurer und fehleranfälliger als ein verlässlicher 503
(`AUDIT_ADR_CANDIDATES.md:151`; `INTERFACE_CONTRACTS.md:562-566`). Option B verschiebt die
Verantwortung an eine Stelle, an der sie nachweislich schon einmal versagt hat.

**Risiko:** MITTEL-HOCH — sicherheitsrelevante Falsch-Grün-Gates bleiben, bis jeder
Konsument umgestellt ist.

---

### Option C: Zwei Endpunkte, harte Trennung; `/health/ready` fail-closed (A-Semantik) — GEWÄHLT

**Beschreibung:** Zwei Endpunkte mit getrennter Verantwortung:

- `GET /health/live` — **Liveness**: der Prozess kann HTTP bedienen. **Immer 200**, keine
  Abhängigkeitsprobe, billig.
- `GET /health/ready` — **Readiness**: die App ist benutzbar. **Fail-closed**: 200 nur, wenn
  jede Pflicht-Abhängigkeit gesund ist (database, cache/Redis, celery_worker, celery_beat);
  sonst **503** mit verpflichtender Liste der ausgefallenen Abhängigkeiten.
- `GET /health/` wird **Deprecation-Alias auf `/health/ready`**, damit die bestehende
  Compose-Probe (`docker-compose.yml:642`) bei Redis-Stop **rot** wird.

**Vorteile:**

- **Löst die eigentliche Lücke:** trennt „Prozess lebt" (Liveness) von „App benutzbar"
  (Readiness) — die Unterscheidung, die heute fehlt, obwohl der Docstring sie bereits
  verspricht (`health.py:4`).
- **Schließt das falsch-grüne Gate:** Der Statuscode von `/health/ready` ist für sich
  verlässlich; Compose/CI müssen keine Liste nachbauen (Abgrenzung zu B).
- **Reuse statt Neubau:** Die vollständige Probe existiert bereits
  (`admin_ops/health_rest.py:96-197`, inkl. `_check_redis`/`_check_celery_worker`/
  `_check_celery_beat`); C hebt sie ins unauthentifizierte Readiness-View statt sie
  zu duplizieren.
- **Liveness ist restart-sicher:** `/health/live` probt keine Abhängigkeit, ein
  Redis-Ausfall kann den Container also nicht in einen Restart-Loop zwingen.

**Nachteile:**

- **Zwei Konventionen** ⇒ Dokumentations- und Aufmerksamkeitsaufwand: Konsumenten müssen
  wissen, welchen Endpunkt sie pollen.
- **Redis-Ausfall nimmt die gesamte Oberfläche aus dem LB**, auch redis-freie Teile. Das
  ist eine bewusste Abnahme (siehe Konsequenzen) und wird über ein Feature-Flag und eine
  konfigurierbare Abhängigkeitsliste abgefedert.
- Der Alias `/health/` ist ein **Übergangszustand** mit Deprecation-Fenster, kein Endzustand.

**Risiko:** NIEDRIG-MITTEL — beherrschbar über Feature-Flag + konfigurierbare
Pflichtliste; die Alternative (B) trägt ein strukturelles Falsch-Grün-Risiko.

---

## Entscheidung

**Option C wird gewählt: getrennte Liveness-/Readiness-Endpunkte mit fail-closed Readiness
(A-Semantik für `/health/ready`).** Verbindlich und prüfbar:

1. **`GET /health/live`** — Liveness. Liefert **immer 200** mit
   `{"status":"ok","checks":{}}`. Führt **keine** Abhängigkeitsprobe aus (kein DB-, Cache-,
   Worker- oder Beat-Zugriff) und ist damit für Liveness-Proben geeignet, ohne bei
   Rand-Ausfällen einen Restart-Loop auszulösen.

2. **`GET /health/ready`** — Readiness. Liefert **200** (`ok`/`warning`), solange **alle
   Pflicht-Abhängigkeiten** gesund sind; **503** (`degraded`), sobald **mindestens eine**
   Pflicht-Abhängigkeit ausfällt. Pflicht sind: `database`, `memory_backend`, `cache`
   (Redis), `celery_worker`, `celery_beat`. Diese erscheinen **ausschließlich** als
   `checks`-Einträge und sind die **einzige** Quelle für `status`/HTTP-Code; bei Ausfall
   stehen sie zusätzlich in `dependencies`.

   Beratend sind: `outbox`, `llm_provider_env`, `embedding_dimensions`,
   `csrf_cookie_secure_matches_auth` sowie die Workflow-Definitions-Warnungen
   (`health.py:276-310`). Sie erscheinen **ausschließlich** in `warnings`
   (Liste statischer Marker) und **niemals** als `checks`-Eintrag — sonst erzeugte ein
   beratender `mismatch`/`missing` fälschlich `degraded` + `dependencies` bei HTTP 200
   (Semantikkollision). Genau diese Trennung korrigiert den Ist-Code, der
   `embedding_dimensions` (`health.py:194`), `llm_provider_env` (`:239`) und
   `csrf_cookie_secure_matches_auth` (`:261`) heute noch als `checks`-Keys führt.

   `memory_backend` wird damit von „beratend" (so die vorherige Fassung dieses ADR) auf
   **Pflicht** korrigiert. Gegenüber dem **Ist-Code** ist das keine Änderung — er liefert
   bei Ausfall bereits **503** (`:158-161`); die Anpassung beseitigt nur den Widerspruch
   der ADR-Fassung zu ihrem eigenen Code-Beleg und erhält die fail-closed-Semantik.

   **Ist→Soll der `checks`-Keys (gegen `health.py:118-315` geprüft):**

   | Key | Ist (heute) | Soll |
   |---|---|---|
   | `database` | `checks`, 503 bei `error` (`:126`,`:133-135`) | Pflicht-`checks`, 503 |
   | `memory_backend` | `checks`, 503 bei `error` (`:158-161`) | Pflicht-`checks`, 503 (unverändert) |
   | `cache` / `celery_worker` / `celery_beat` | fehlt | Pflicht-`checks`, 503 (neu) |
   | `embedding_dimensions` | `checks` = `mismatch` (`:194`) | nur `warnings` (beratend) |
   | `llm_provider_env` | `checks` = `missing` (`:239`) | nur `warnings` (beratend) |
   | `csrf_cookie_secure_matches_auth` | `checks` = `mismatch` (`:261`) | nur `warnings` (beratend) |

   Für Bestandskonsumenten wird während des Deprecation-Fensters ein additives
   `advisory`-Objekt (gleiche Key-Namen, aus `warnings` abgeleitet) zugelassen, damit die
   bisherigen Keys nicht schlagartig verschwinden; `advisory` ist **nicht** statusrelevant.
   Der Vertragsname der Redis-Abhängigkeit ist `cache`; die bestehende admin-Probe liefert
   die Zeile unter `name: "redis"` (`admin_ops/health_rest.py:107`) und wird für den
   Ready-Endpunkt auf `cache` gemappt.

3. **`GET /health/`** wird **Deprecation-Alias auf `/health/ready`** und erbt dessen
   Semantik. Damit wird der bestehende Compose-Healthcheck (`docker-compose.yml:642`) bei
   einem Cache-/Worker-/Beat-Ausfall **rot** (RES-03-Akzeptanz,
   `RESILIENCE_HEALTH.md:73-74`). Der Alias trägt `Deprecation: true`- und `Sunset`-Header
   und wird nach dem Fenster entfernt.

4. **Body/Status-Vertrag (eindeutig).** `status` ist exakt einer der drei Werte
   `ok | warning | degraded`:

   - `status == "ok"` genau dann, wenn **jeder Pflicht-Check** `ok` ist **und** `warnings`
     leer ist → HTTP **200**.
   - `status == "warning"` genau dann, wenn jeder Pflicht-Check `ok` ist und **mindestens
     ein beratendes Signal** in `warnings` steht → HTTP **200**. Der `warning`-Status wird
     damit **ausdrücklich als Vertragsteil festgeschrieben** (bestehendes Verhalten,
     `health.py:312-313`); sein Entfall wäre ein Breaking Change (Major-Bump), weil
     Konsumenten `warning` heute bereits beobachten können.
   - `status == "degraded"` genau dann, wenn **mindestens ein Pflicht-Check** nicht `ok`
     ist → HTTP **503**.

   Es gilt die Äquivalenz: `dependencies` nicht leer ⇔ `status == "degraded"`. Bei
   `degraded` enthält `dependencies` **jede** nicht-`ok` **Pflicht**-Abhängigkeit als
   `{name, status, detail}`; beratende Signale erscheinen **nie** in `dependencies`,
   sondern ausschließlich in `warnings`/`advisory`. `detail` ist ein **statischer Marker**
   (z. B. `"dependency_down"`), **niemals** DSN/Host/Port/Secret (CWE-209, wie bereits in
   `health.py:127-136` praktiziert); die reale Ursache geht als Logzeile (≥ WARNING) heraus.

5. **Auth:** `/health/live` und `/health/ready` sind — wie der heutige `/health/`
   (`REQ-L2-AT-007`, `L2_AuthAndTenancySystem_Requirements.md:237,249`) — **ohne Token
   erreichbar**, geben aber ausschließlich statische Marker preis. Das präzisiert die
   Formulierung „admin-authentifiziert" aus `AUDIT_ADR_CANDIDATES.md:152` (dort auf die
   heute admin-geschützte Dashboard-Sicht bezogen) für den **Probe**-Endpunkt.

6. **Feature-Flag `HEALTH_STRICT_READINESS`** (Governance):
   - **Default `true` (fail-closed, strikt).** Ein ungesetzter/leerer Wert ist strikt;
     nur ein explizites `false` wechselt den Modus. Fail-closed ist damit
     Default-by-omission.
   - **Rückfallmodus = „degraded-200".** Ist das Flag `false`, liefert `/health/ready`
     auch bei ausgefallener Pflicht-Abhängigkeit **HTTP 200** mit `status:"degraded"` und
     gefüllter `dependencies`-Liste; Konsumenten müssen dann die Liste selbst auswerten.
     Das ist inhaltlich die in §„Alternativen" als **Option B** verworfene Semantik — der
     Modus wird bewusst bereitgestellt, aber **nicht** als Default. Der präzise
     Modusname lautet **„degraded-200"**, nicht „Option B".
   - **Schaltbefugnis:** Nur der Betreiber der jeweiligen Umgebung (Deployment-/
     Infrastruktur-Verantwortung; Agenten `devops-engineer`/`sre-engineer`) darf das Flag
     **pro Umgebung** setzen. Es ist **kein** Laufzeit-Schalter für Anwendungsnutzer und
     wird **nicht** über die App-Oberfläche exponiert. Für Prod gilt `true`, sofern nicht
     ausdrücklich anders entschieden und im Deployment dokumentiert.
   - Eine **konfigurierbare Pflicht-Abhängigkeitsliste pro Umgebung** ergänzt das Flag;
     beide sind Env-/Deployment-Konfiguration und tragen kein Datenrisiko.

7. **Umsetzung nutzt vorhandene Probe:** Die Abhängigkeitsprüfungen werden aus
   `admin_ops/health_rest.py` (`_check_redis`, `_check_celery_worker`, `_check_celery_beat`,
   `:96-197`) wiederverwendet; der admin-geschützte Dashboard-Endpunkt
   `GET /api/v1/admin/health/` (`SystemHealthView`, `:517-547`) bleibt unverändert die
   ausführliche Diagnose-Sicht für Menschen.

**Bewusste Abweichung von `RESILIENCE_HEALTH.md:72` (Outbox).** Der Plan führt `outbox`
als **Pflicht**-Readiness-Abhängigkeit (`RESILIENCE_HEALTH.md:70-72`). Dieser ADR führt
`outbox` stattdessen **beratend** (nur `warnings`, kein 503), aus zwei Gründen:

- Es existiert heute **keine bounded Outbox-Probe**: `admin_ops/health_rest.py:96-198`
  prüft DB, Redis, Celery-Worker, Celery-Beat und MCP — **nicht** `outbox`. Eine
  Pflicht-Aufnahme erzwänge erst eine neue, bounded Probe (`DomainEventOutbox`-Rückstau),
  sonst wäre die Pflicht nicht messbar.
- Ein Outbox-Rückstau hebt die **synchrone Request-Verfügbarkeit nicht auf**:
  `DomainEventOutbox` ist der asynchrone Randpfad der Transaktions-Outbox
  (`application/event_bus.py`, Dispatch über den `OutboxPoller`), nicht der
  Request-Pfad selbst. Ein 503 auf bloßen asynchronen Rückstau nähme die Oberfläche aus
  dem LB — genau die Kaskade, die dieser ADR vermeidet und die `REQ-L1-032` untersagt.
  Der Rückstau ist über Tabelle/DLQ beobachtbar, nicht über die synchrone Verfügbarkeit.

Die Abweichung wird bewusst getragen. Eine spätere Hochstufung von `outbox` zur Pflicht
(nach Nachziehung einer bounded Probe) ist eine **minor** Erweiterung derselben
Pflichtliste, keine Strukturänderung; sie ist als Folgeaufgabe vermerkt.

**Diese Entscheidung blockiert** RES-03, RES-05 (Beat-Heartbeat-Auswertung) und RES-07
(Gates), bis sie `accepted` ist (`RESILIENCE_HEALTH.md:69-77`;
`INTERFACE_CONTRACTS.md:321-325`). Bis dahin bleiben §3.2–3.4 dort **Vertragsvorschlag**,
kein Sofort-Fix.

---

## Konsequenzen

**Positiv:**

- **Die entscheidende Unterscheidung entsteht:** „der Prozess lebt" (`/health/live`) vs.
  „die App ist benutzbar" (`/health/ready`) — die Lücke, die `health.py:4` seit jeher
  verspricht und die bisher fehlt (`-275`).
- **Der Statuscode wird verlässlich:** Compose und CI können `/health/ready` direkt
  auswerten; es braucht **keine** Gate-seitige Listen-Auswertung. Genau das schließt die
  Falsch-Grün-Klasse des Critical-Befunds `AUD-2026-09-031`.
- **Kein Restart-Loop:** Weil `/health/live` keine Abhängigkeit probt, kann ein
  Cache-/Worker-/Beat-Ausfall den Container nicht als „tot" markieren — konsistent mit der
  bereits getroffenen Warnung-200-Entscheidung in `health.py:176-181`.
- **Reuse statt Neubau:** Die vollständige Probe existiert (`admin_ops/health_rest.py`),
  der Aufwand bleibt dadurch beherrschbar (`INTERFACE_CONTRACTS.md:567-568`).
- **Compose wird ehrlich:** Der Backend-Healthcheck (`docker-compose.yml:642`) wird bei
  Rand-Ausfällen rot, statt grün zu bleiben.

**Negativ:**

- **Redis-Ausfall nimmt die gesamte Oberfläche aus dem Load-Balancer** — auch die
  redis-freien Teile. Das ist die bewusste Abnahme dieses ADR und der Kern des Trade-offs
  gegen Option B. Abgefedert wird sie nur durch `HEALTH_STRICT_READINESS` und die
  konfigurierbare Pflichtliste; ein Betreiber, der beides strikt setzt, akzeptiert diese
  Verfügbarkeitsreduktion zugunsten verlässlicher Gates.
- **Zwei Konventionen** erzeugen Dokumentations- und Aufmerksamkeitsaufwand: Konsumenten
  müssen den richtigen Endpunkt wählen. Der Alias `/health/` ist ein Übergangszustand und
  muss später zurückgebaut werden.
- **Semantikwechsel für Bestandskonsumenten von `/health/`:** Der Alias auf `/health/ready`
  bedeutet, dass Cache-/Worker-/Beat-Ausfälle künftig 503 liefern. Dokumentation, TESTPLAN
  und Runbook (`docs/DEPLOY_RUNBOOK.md`, `docs/se/reports/TESTPLAN_*`) referenzieren
  `/health/` und müssen mit einem Deprecation-Fenster nachgezogen werden.
- **Zu strikte Readiness** kann legitime Teil-Verfügbarkeit aussperren; deshalb ist das
  Feature-Flag keine Nebensache, sondern Teil der Entscheidung.
- **Response-Shape-Änderung bei beratenden Signalen:** `embedding_dimensions`,
  `llm_provider_env` und `csrf_cookie_secure_matches_auth` wandern aus `checks` nach
  `warnings` (`status`/HTTP-Code unverändert `warning`/200). Für Konsumenten, die diese
  Keys in `checks` gelesen haben, ist das eine sichtbare Shape-Änderung; das additive
  `advisory`-Objekt überbrückt sie im Deprecation-Fenster. Der Statuscode bleibt stabil —
  keine Breaking Change im Sinne der Status-/Gate-Semantik.
- **Keine REQ trägt den Vertrag:** Die Zuordnung zu `REQ-L1-032`/`REQ-L0-021`/`REQ-060`/
  `REQ-063`/`REQ-L2-AT-007` ist eine **Näherung**, keine getrackte Verknüpfung. Da
  `open_adrs` repo-weit nicht existiert (`AUD-2026-09-333`), bleibt die REQ↔ADR-Kette offen.

---

## Folgeaufgaben (nicht Teil dieser Entscheidung)

1. **`open_adrs`-Feld einführen** (repo-weit, `AUD-2026-09-333`), damit `REQ-L1-032`,
   `REQ-L0-021`, `REQ-060`, `REQ-063` und `REQ-L2-AT-007` diese ADR referenzieren können.
   Bis dahin wird **keine** REQ-Datei geändert.
2. **Review-Übergang `proposed → review`** durch `se-critic` (MADR-Lifecycle), inkl.
   Prüfung gegen `REQ-L1-032` (Nicht-Kaskade) und die Restart-Loop-Abgrenzung.
3. **Contract-Details nachziehen**, sobald `accepted`: exaktes Body-Schema, Statusmatrix je
   Abhängigkeit und Deprecation-Fenster stehen als Vertragsvorschlag in
   `INTERFACE_CONTRACTS.md:233-325` und werden nach der Entscheidung verbindlich.
4. **Auth-Ausnahmeliste erweitern:** `REQ-L2-AT-007` (Auth-Middleware-Interception,
   Ausnahme für `/health`) ist um `/health/live` und `/health/ready` zu ergänzen, sobald
   die Endpunkte implementiert sind — sonst interceptet die Middleware die Probes und die
   Compose-/Orchestrator-Probe erhält kein Ergebnis. Umsetzungsort ist die Auth-Middleware
   der `auth_tenancy`-App; **keine** REQ-Datei wird im Rahmen dieses ADR geändert.
5. **Bounded Outbox-Probe nachziehen** (optional, siehe Abweichung zu
   `RESILIENCE_HEALTH.md:72`): erst dann kann `outbox` von beratend auf Pflicht hochgestuft
   werden. Kein Vertragsbestandteil der aktuellen Entscheidung.

---

*Erstellt durch `api-specialist` am 2026-10-01. Status `proposed` — Review folgt extern;
Freigabe durch `user` steht aus (siehe `deciders`). Belege gegen den Code geprüft; keine
bestehende Datei außer diesem ADR geändert, keine REQ-ID erfunden.
Review-Findings (CHANGES_REQUESTED: 1 major, 4 minor) eingearbeitet — Details siehe
Rückmeldung an den `concept-reviewer`; Re-Review durch `se-critic`/`concept-reviewer` folgt.*
