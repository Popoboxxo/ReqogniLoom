---
type: REVIEW
scope: audit-adr-candidates
status: final
date: 2026-09-30
author_agent: documenter
---

# AUDIT_ADR_CANDIDATES — Findings, die eine Architekturentscheidung brauchen

> **Was dieses Dokument ist.** Eine Auswahl von Befunden, die **nicht durch einen
> Fix, sondern durch eine Entscheidung** gelöst werden. Für jeden Kandidaten
> stehen das Problem, die betroffenen Finding-IDs, 2–3 mögliche Optionen mit
> Trade-offs, bestehende ADR-Bezüge und die Frage, die der User entscheiden muss.
>
> **Was es nicht ist.** **Es wurde keine ADR geschrieben.** Der Bestand in
> `docs/se/ADR/` ist unverändert. `ADR-001`…`ADR-009` (davon `ADR-004`
> `proposed`, `ADR-005`…`ADR-009` `accepted`; `ADR-001`–`ADR-003` und
> `ADR-DS-02` ohne parsebares Frontmatter-`status`) ist der Bestand, gegen den
> die Kandidaten abgegrenzt werden.
>
> **Auswahlkriterium.** Ein Kandidat braucht **beides**: (a) mindestens einen
> `Critical`- oder `High`-Befund, (b) eine Entscheidung mit **echten
> Trade-offs** — also mindestens zwei vertretbare Optionen, bei denen eine
> andere Entscheidung auch verteidigbar wäre. Ein reiner Bugfix ist **kein**
> ADR-Kandidat und steht im [`AUDIT_BACKLOG.md`](AUDIT_BACKLOG.md).

**8 Kandidaten.** Reihenfolge nach Tragweite der Entscheidung, nicht nach
Schweregrad des Einzelbefunds.

---

## 1. Serverseitiger Workspace-Fence: Tenant- oder Workspace-Autorisierung als Leitmodell

* **Backlog-Rang:** 5 (P0) und 18 (P2)
* **Betroffene Findings:** `AUD-2026-09-222` (High) · `-240` (Medium) · `-081` (Medium) · `-043` (Medium) · `-223` (High, Folgeeffekt: Admin ohne Tenant-Bezug)

### Problem

Zwei Autorisierungsachsen existieren nebeneinander, aber nur eine ist
durchgesetzt. **Tenant** ist vollständig dicht: 0 Leaks in 120 Cross-Tenant-Proben
(REST) und 65 (MCP), RLS greift, die App-Rolle ist non-superuser **ohne**
`BYPASSRLS`. **Workspace** ist **offen**: der Fence wird nur ausgelöst, wenn der
*Client* eine `workspace_id` mitsendet — 269 von 311 mutierenden Routen tun das
nicht. MCP macht es richtig (`tool_registry.py:1378` leitet die Rolle aus dem
**Tool-Argument** ab), REST nicht.

Das ist keine Verdrahtungsfrage, sondern die Frage, **welche Achse das
führende Autorisierungsmodell ist.** Alles andere (RLS-Deckung, Admin, Celery-
Tasks, Plugin-Rechte) folgt daraus.

### Optionen

| Option | Beschreibung | Dafür | Dagegen |
|---|---|---|---|
| **A — Workspace als führende Achse** | Jeder Lese-/Schreibpfad leitet den Ziel-Workspace **aus dem Zielobjekt** ab, nicht aus dem Request. `workspace_id` im Request wird zu einer Optimierung, nicht zur Bedingung. | Schließt die Klasse vollständig; MCP ist der Beweis, dass es funktioniert; passt zum Produktnutzen (Programme/Workspaces eines Mandanten). | Höhere Kosten pro Zugriff (Objekt laden vor der Prüfung); Ausnahmen für dateilose Objekte brauchen eine eigene Regel. |
| **B — Tenant als führende Achse, Workspace als Feature** | Tenant-Durchsetzung bleibt der Kern; Workspace-Sichtbarkeit wird als **konfigurierbare** Policy behandelt (pro Tenant zuschaltbar), mit `x-requires-workspace`-Deklaration pro View. | Weniger Regressionen; passt zu Mandanten, die bewusst einen workspaceübergreifenden Blick brauchen. | Die Policy muss überall gesetzt werden — dieselbe Fehlerklasse wie heute, nur mit Schalter. Löst `-222` nicht, sondern macht es konfigurierbar. |
| **C — Zwei-Ebenen-Modell mit explizitem Scope** | Jede Ressource trägt einen Scope (`tenant` oder `workspace`); der Fence wird aus dem **Ressourcen-Dekorator** abgeleitet, nicht pro Route. | Eine Stelle statt 311; verhindert Rückfall (neue Routen erben automatisch den richtigen Fence). | Einführungsaufwand hoch; ein Fehler im Dekorator wirkt sofort auf alle Routen. |

### Bestehende ADR-Bezüge

* `docs/se/ADR/ADR-002_Event-Bus.md` — betrifft den Event-Pfad, nicht die Autorisierung; **kein** Konflikt.
* `docs/se/ADR/ADR-007_se_regeln_am_baseline_gate.md` (`accepted`) — berührt die Frage, **wo** Regeln durchgesetzt werden, nicht **wer**. Konsistent mit Option C.
* Das Register stellt den Bezug zu Issue **`#103`** her (Reopen-Rest), nicht zu einem ADR ⇒ die Entscheidung ist bisher **nicht** getroffen.

### Frage an den User

> **Ist Workspace- oder Tenant-Scope die führende Autorisierungsachse?**
> Wenn Workspace: Option A (billigster Weg zur Vollständigkeit, MCP als
> Referenz) oder Option C (teurer, aber regressionssicher)? Wenn Tenant:
> Option B mit expliziter Scope-Deklaration — und wird die Option dann als
> **produktives Feature** dokumentiert, damit sie nicht als Lücke missverstanden
> wird?

---

## 2. Rigor-Preset-SSOT: welche Regeln sind Daten, welche sind Code?

* **Backlog-Rang:** 23 (P2)
* **Betroffene Findings:** `AUD-2026-09-160` (High) · `-161` (High) · `-162` (High) · `-187` (Medium) · `-328` (Medium) · `-175` (Low)

### Problem

`presets/registry.py:13` trägt den Docstring **„Single Source of Truth for all
preset rule data"**. Die Behauptung ist **nicht haltbar**: 7 Regeln sind
datengetrieben, 5+ hartkodiert — und die hartkodierte Hälfte steuert die
fachlich gewichtigere Achse (Workflow-Graphen, Attribut-Stufen, Invarianten-Sätze).
`stage_mandatory` wird geseedet und hat **null** Produktionskonsumenten. Der
Downgrade-Blocker in `presets/gate.py:536-549` ist **fail-open**
(`except Exception: pass`) — genau die Stelle, die einen unzulässigen Downgrade
verhindern soll. Drei parallele Entity-Typ-Registries (11 / 10 / 13) und
Link-Typ-Zahlen 6/8/10/11 im Code laufen derselben Richtung.

Der eigentliche Schaden ist nicht die Inkonstenz, sondern die **falsche
Zusage**: jede Folgeentscheidung stützt sich auf „das steht im Registry".

### Optionen

| Option | Beschreibung | Dafür | Dagegen |
|---|---|---|---|
| **A — Volle SSOT** | Alle Preset-Regeln werden Daten; Module lesen ausschließlich. Registry wird generiert oder editiert. | Der Docstring wird wahr; Preset-Wechsel brauchen keinen Deploy; ein Test kann Vollständigkeit erzwingen. | Größter Aufwand; erzwingt ein Datenmodell für Dinge, die heute Code sind (Workflow-Graphen). |
| **B — Ehrliche Teilssot** | Registry ist SSOT für **Attribut- und Invarianten-Regeln**; Workflow-Graphen bleiben Code und werden als solche benannt. Docstring wird korrigiert. | Kleinster Aufwand, beseitigt die falsche Zusage sofort; „7 datengetrieben / 5 Code" wird eine Aussage statt eines Problems. | Rigor-Diff zwischen Presets bleibt teilweise im Code ⇒ Audit-Tooling braucht weiter zwei Quellen. |
| **C — Code-SSOT, Registry als Export** | Umgekehrt: Code ist die Quelle, die Registry ist ein **Export** für UI/Docs. | Keine Doppelbuchhaltung; UI und Doku können nie abweichen. | Ein Preset-Wechsel erfordert Deploy; erschwert Tenant-Overrides. |

### Bestehende ADR-Bezüge

* `docs/se/ADR/ADR-008_moe_mop_tpm_nicht_modelliert.md` (`accepted`) — genau
  dieselbe Entscheidungsklasse: **was nicht modelliert wird, wird benannt.**
  Option B ist die konsequente Fortsetzung; ein neuer ADR sollte darauf Bezug nehmen.
* `docs/se/ADR/ADR-007_se_regeln_am_baseline_gate.md` (`accepted`) — der
  Baseline-Gate ist der Ort, an dem Preset-Regeln wirken; die Frage der *Quelle*
  ist davon getrennt zu entscheiden.
* `open_adrs` existiert repo-weit **nicht** (0/835 REQs, `AUD-2026-09-333`) ⇒
  der Verweis von den betroffenen REQs auf eine künftige ADR ist heute nicht
  möglich. Das ist eine **Voraussetzung**, keine Nebensache.

### Frage an den User

> **Wie groß soll der SSOT-Anspruch sein — voll (A), ehrlich Teil (B) oder
> umgekehrt (C)?** Und: soll die fail-open-Stelle im Downgrade-Gate unabhängig
> davon sofort auf fail-closed gehen, oder erst nach der ADR-Entscheidung?

---

## 3. Health-/Readiness-Vertrag: fail-closed oder degraded-200?

* **Backlog-Rang:** 26 (P2), Teil von 3 (P0) und 33 (P3)
* **Betroffene Findings:** `AUD-2026-09-031` (Critical) · `-129` (High) · `-139` (Medium) · `-275` (Medium) · `-286` (Medium) · `-205` (Low, **BLOCKED**) · `-031` (Health prüft weder Cache noch Worker)

### Problem

`/health/` meldet `200 {"status":"ok"}`, während App, Auth und Schema
**unbenutzbar hängen** — live belegt durch die Redis-Ausfall-Simulation. Es
gibt **keinen** trennbaren Liveness-/Readiness-Punkt: der Docstring in
`health.py:4` verspricht `/health/ready` und `/health/live`, **beide existieren
nicht**. `degraded` liefert HTTP **200**. Der Orchestrator-Check prüft **5 von
10** Abhängigkeiten (Redis/Worker/Beat/Outbox fehlen) — während die
**vollständige** Prüfung admin-authentifiziert in `admin_ops/health_rest.py`
bereits existiert und unbenutzt bleibt. Und: **3 Fail-closed-Sites loggen auf
`DEBUG`**, das in Produktion abgeschaltet ist ⇒ bei DB-Ausfall 403 für alle bei
null Logzeilen.

Die Frage ist nicht „welche Checks fehlen", sondern **was ein Health-Endpoint
verspricht** und **wer** das auswertet.

### Optionen

| Option | Beschreibung | Dafür | Dagegen |
|---|---|---|---|
| **A — Strikt fail-closed** | Jede Abhängigkeit, die die App benötigt, muss gesund sein; sonst 503. Liveness und Readiness getrennt (`/health/live` = Prozess, `/health/ready` = alle Abhängigkeiten). | Klassische, gut verstandene Semantik; Orchestrator und CI können darauf vertrauen. | Ein Redis-Ausfall nimmt die **gesamte** Oberfläche aus dem Load-Balancer, auch die Teile, die gar nicht Redis brauchen. |
| **B — Degraded-200 mit ehrlichem Status** | `/health/` bleibt 200, aber `status` wird zu `degraded` + **Liste** der ausgefallenen Abhängigkeit; Compose- und CI-Gates werten die Liste aus, nicht den Statuscode. | Kein Ausfall verfügbarer Funktionalität; Details sind sichtbar. | Erzeugt genau die Lücke, die das Register belegt: jedes Gate, das nur den Statuscode liest, ist grün. Braucht zwingende Gegenauswertung. |
| **C — Zwei Endpunkte, harte Trennung** | `/health/live` für den Prozess (billig), `/health/ready` für alle Abhängigkeiten (voll, admin-authentifiziert). Orchestrator nutzt `ready`, Menschen nutzen `live`. | Trennt „der Prozess lebt" von „die App ist benutzbar" — genau die Unterscheidung, die jetzt fehlt; die vollständige Prüfung existiert bereits. | Zwei Konventionen ⇒ Dokumentations- und Aufmerksamkeitsaufwand. |

### Bestehende ADR-Bezüge

* **Kein bestehender ADR regelt den Health-Vertrag.** Das ist die Lücke.
* `docs/se/ADR/ADR-007_se_regeln_am_baseline_gate.md` (`accepted`) ist ein
  Präzedenzfall für die Frage „wo wird durchgesetzt?" — aber für ein
  **Laufzeit**-Gate gilt er nicht.
* **Abgrenzung:** ADR-002 (Event-Bus, `ADR-002_Event-Bus.md`) betrifft
  Zustellung, nicht Verfügbarkeit ⇒ **kein** Konflikt.

### Frage an den User

> **Soll `degraded` HTTP 200 oder 503 liefern?** Falls 200: wird die
> ausgefallene Abhängigkeit im Body **verpflichtend** gelistet **und** ein Gate
> eingeführt, das die Liste auswertet — oder akzeptieren wir, dass ein
> Statuscode-gelesenes Gate falsch-grün bleibt? Und: zwei Endpunkte (C) oder
> einer (A/B)?

---

## 4. Celery-Queue-Topologie: vier Queues ohne Wirkung — Wirkung herstellen oder entfernen?

* **Backlog-Rang:** 8 (P1), Teil von 9 (P1) und 11 (P1)
* **Betroffene Findings:** `AUD-2026-09-120` (Critical) · `-121` (Critical) · `-126` (High) · `-270` (High) · `-132` (Medium) · `-133` (Medium) · `-056` (Medium)

### Problem

Der Code dokumentiert eine **Skalierbarkeitsabsicht** — vier Queues, damit
Worker-Klassen unabhängig skaliert werden können. Gebaut ist das Gegenteil:
alle vier sind **identisch gebunden**, jede Task läuft **4×** (live belegt über
den kombu-`memory://`-Nachweis). Parallel dispatcht `celery-beat` **nie**
(`0 × Sending due task`), `audit.archive_lifecycle_manager` ist im
Beat-Schedule eingetragen, aber nie im Worker-Task-Set registriert, und
`task_acks_late=False` macht einen Worker-Kill zu endgültigem Task-Verlust.

Vier Queues ohne Routing-Wirkung sind **eine unentschiedene Architekturfrage**:
entweder wurde die Skalierbarkeit nie umgesetzt, oder sie wurde zurückgebaut und
die Dokumentation blieb stehen. Beides verlangt eine Entscheidung, kein Ticket.

### Optionen

| Option | Beschreibung | Dafür | Dagegen |
|---|---|---|---|
| **A — Wirkung herstellen** | Pro Queue eigener `Exchange` + `routing_key`; Tasks explizit routen; Worker auf Queue-Klassen skalieren. | Die beabsichtigte Skalierbarkeit wird real; Kosten pro Task-Klasse werden steuerbar. | Routing ist eine **stille** Änderung: ein falsch gerouteter Task läuft nie und fällt erst bei Dispatch auf. Braucht einen Routing-Wächter. |
| **B — Auf eine Queue zurückbauen** | Drei Queue-Namen entfernen, Skalierbarkeitsabsicht aus dem Kommentar streichen. | Kleinster Zustand, keine falsche Zusage; `task_acks_late` und Beat sind die einzigen echten Reparaturen. | Skalierbarkeit über Task-Klassen geht verloren — bei Provider-Hot-Paths genau der falsche Ort. |
| **C — Neu modellieren: Prioritätsklassen** | Drei bis vier Queues nach **Dringlichkeit** (`critical` / `default` / `bulk`) statt nach Worker-Klasse, mit expliziter Priorität im Task. | Macht Wartung (Retention, Archivierung) und KI-Kosten kontrollierbar; erklärt, warum Wartung nie laufen darf. | Task-Umbenennung ⇒ alle Aufrufer, Zeitpläne und Monitoring-Regeln wandern. |

### Bestehende ADR-Bezüge

* **Kein bestehender ADR regelt die Task-Topologie.** `ADR-002_Event-Bus.md`
  betrifft den Event-Bus innerhalb der Anwendung, **nicht** Celery-Routing.
* **Wichtige Abgrenzung:** `AUD-2026-09-283`/`-284` (Outbox at-least-once,
  nicht-idempotenter Abonnent) sind ein **eigenes** Thema; ein ADR zur
  Zustellgarantie wäre nötig, ist aber nicht identisch mit der Routing-Frage.
* `AUD-2026-09-350` (Traceability) stuft Asynchronität als `Covered` ein, weil
  jede Task 4× läuft — das ist ein **Argument für A oder C**: eine Wirkung, die
  nicht existiert, wird als Abdeckung verbucht.

### Frage an den User

> **Warum gibt es vier Queues — und welche der drei Antworten ist die
> beabsichtigte?** Falls A oder C: ab wann darf die Prioritäts- oder
> Klassen-Route als verbindlich gelten, ab der ein Routing-Wächter Pflicht ist?
> Und: soll `task_acks_late=True` Voraussetzung oder eigene Entscheidung sein?

---

## 5. Backup-/Restore-Wahrheit: Skript oder Sidecar — welche Quelle ist verbindlich?

* **Backlog-Rang:** 7 (P1)
* **Betroffene Findings:** `AUD-2026-09-122` (Critical) · `-123` (Critical) · `-124` (High) · `-127` (High) · `-128` (High) · `-345` (Critical, Anforderungswahrheit)

### Problem

Es gibt **zwei** Backup-Wege, und beide sind broken — aber auf verschiedene Art:

| Weg | Zustand |
|---|---|
| **Sidecar** (`postgres-backup`) | **funktioniert** — echter Restore reproduzierte **15/15** Tabellenzahlen, 0 Fehler. Aber 42-h-Horizont, kein Off-Host, keine Verschlüsselung, Medien/Uploads nicht enthalten (`-128`). |
| **`scripts/backup.sh`** | **kann nie erfolgreich sein** — `exit 1` (`-122`). |
| **`scripts/restore.sh`** | **kann nie erfolgreich sein** — die Backup-Datei wird nie in den Container kopiert, `psql -f` liest die Datei statt stdin (`-123`); Format-Inkompatibilität (`.sql.gz` im Volume vs. `*.dump`/`*.sql` in `./backups`, `-124`); nicht atomar (`--clean --if-exists` in-place auf der Live-DB, `-127`). |

Parallel ist `REQ-L2-BL-011` in der Traceability-Matrix als **`Implemented`**
geführt (`-345`). Der Audit hat die `CR-37`-Defektklasse damit **bestätigt und
verschärft** und die Mechanik-Seite **teilweise entkräftet**.

Die Entscheidung ist nicht „Skript reparieren", sondern: **welche Quelle ist
verbindlich, und was darf die Matrix versprechen?**

### Optionen

| Option | Beschreibung | Dafür | Dagegen |
|---|---|---|---|
| **A — Sidecar ist die Quelle** | Sidecar als alleiniger Backup-Weg; Skripte entfernen oder als deprecated kennzeichnen; Off-Host-Kopie und Verschlüsselung konfigurierbar. | Die Quelle ist nachweislich funktionsfähig; ein Restore-Smoke kann im Release-Gate laufen. | Der Sidecar kennt keine Fachlogik (was ist „wichtig"?); kein Off-Host im Repo. |
| **B — Skripte sind die Quelle** | Skripte reparieren, atomar in eine Zieldatenbank, Formatvertrag definieren, Smoke-Test als Gate. | Volle Kontrolle über Zeitpunkt, Format und Ziel; Operator-Schnittstelle bleibt. | Der Pfad ist bis zur Reparatur **ungetestet**; ein halb repariertes Skript ist schlimmer als ein entferntes. |
| **C — Beide, mit benannter Wahrheit** | Sidecar für die Automatik, Skripte für den Notfall — **mit** einem Restore-Smoke, der **beide** Wege ausführt und die Tabellenzahlen vergleicht. | Der Smoke wird zur eigentlichen Wahrheit; die Entscheidung kann später kippen, ohne dass der Nachweis verloren geht. | Zwei Pfade, zwei Formate, zwei Fehlerquellen; nur vertretbar mit echtem Vergleich. |

### Bestehende ADR-Bezüge

* **Kein ADR regelt Backup/Restore.** Das ist selbst eine Feststellung: für ein
  zertifizierungsrelevanten Bereich gibt es keine akzeptierte Betriebsentscheidung.
* `docs/se/ADR/ADR-007_se_regeln_am_baseline_gate.md` (`accepted`) ist der
  nächstliegende Präzedenzfall für „eine Quelle der Wahrheit für Regeln" —
  inhaltlich aber nicht dasselbe (Laufzeitbetrieb statt Artefaktzustand).
* **Folge für die Matrix:** `REQ-L2-BL-011` muss auf `Implemented` **oder**
  `Not Implemented` gesetzt werden — WP-5 empfiehlt die ehrliche Nicht-Implementiert-
  Kennzeichnung, solange kein ausführbarer Restore-Skriptpfad existiert.

### Frage an den User

> **Welche Quelle ist verbindlich — Sidecar (A), Skripte (B) oder der
> vergleichende Smoke als Wahrheit (C)?** Und: soll `REQ-L2-BL-011` bis zur
> Entscheidung auf `Not Implemented` zurückgesetzt werden, oder wird die
> Matrix-Zusage gehalten und der Pfad entsprechend priorisiert?

---

## 6. i18n-Key-Vertrag: welche Quelle gilt, und darf `t()` einen Inline-Default haben?

* **Backlog-Rang:** 15 (P1) und 31 (P3)
* **Betroffene Findings:** `AUD-2026-09-300` (High) · `-301` (High) · `-002` (High) · `-016` (Medium) · `-303` (Medium) · `-304` (Medium) · `-322` (Low) · `-302` (Medium) · `-348` (High)

### Problem

**116** Keys fehlen in **beiden** Locales (41 Dateien). Der Paritäts-Ratchet
prüft zwar Code→Locale, vergleicht aber gegen die **eingefrorene Obergrenze**
`MISSING_KEY_BASELINE = 116` — die Lücke ist damit Teil des Soll-Zustands
(„Kontrollen, die ihre eigenen Lücken nicht sehen"). Zusätzlich **536** tote
Locale-Keys (25,3 %), 76 dynamische ungeprüfte Keys, 27 Count-Keys ohne
Pluralform, und die **Inline-Defaults** an 112 Stellen maskieren den Fehler in
beide Richtungen: in DE erscheint englisch, in EN deutsch — während die
Traceability-Matrix i18n als `Implemented/Covered` führt (`-348`).

Die drei Kernfragen sind je **eine** Entscheidung:

1. Welche Quelle ist verbindlich — Locale-Datei oder Code-Stelle?
2. Dürfen dynamische Keys (`t(name)`) überhaupt ohne statische Prüfung durch?
3. Darf `t(key, default)` einen Fallback haben? Genau dieser Fallback ist die
   Ursache der Maskierung.

### Optionen

| Option | Beschreibung | Dafür | Dagegen |
|---|---|---|---|
| **A — Strikter Vertrag** | Der `t()`-Key muss zur Compile-/Test-Zeit existieren; **kein** Inline-Default (ein fehlender Key muss sichtbar rot werden). Dynamische Keys brauchen ein Typschema oder eine generierte Union. | Der Ratchet kann auf 0 stehen und bleibt bei 0; die Matrix-Zusage wird wahr. | Der Inline-Default-Verlust macht fehlende Übersetzungen sofort sichtbar — richtig, aber disruptive für 112 Stellen. |
| **B — Vertrag mit erlaubtem Default** | Inline-Default bleibt erlaubt, aber der Ratchet misst **zusätzlich**, wie viele Stellen einen Default nutzen, und dieser Wert **sinkt** monoton (Ratchet auf 0). | Schrittweise, ohne Bruch; die Zahl macht den Fortschritt messbar. | Zwei Indikatoren (fehlende Keys, genutzte Defaults) — die Pflege muss beide erklären. |
| **C — Generierte Keys** | Aus dem Code wird eine Single-Key-Datei generiert; Locales werden dagegen geprüft und mit dem Code ausgeliefert. Code bleibt die Quelle. | Code und Locale können nicht auseinanderlaufen; Review-Diff wird aussagekräftig. | Generierter Code-Teil im Repo; Build-Abhängigkeit; Extra-Tooling. |

### Bestehende ADR-Bezüge

* **Kein ADR regelt i18n.** Für ein Produkt mit DE/EN als zugesagtem Umfang
  ist das eine offene Lücke.
* `docs/se/ADR/ADR-006_personenfelder_und_freitext.md` (`accepted`) ist ein
  Präzedenzfall für „ein Feldtyp = eine Entscheidung" — der i18n-Fall ist die
  Frontend-Entsprechung.
* `AUD-2026-09-333` (`open_adrs` 0/835) heißt: eine neue ADR ist heute noch
  keinem REQ zugeordnet ⇒ die ADR-Kette selbst muss mitgezogen werden.

### Frage an den User

> **Darf `t()` einen Inline-Default behalten?** Falls ja: Option B mit einem
> **monoton sinkenden** Ratchet auf 0. Falls nein: Option A und ein
> Migrationsfenster für die 112 Stellen. Und: sind dynamische Keys (`-304`)
> erlaubt — mit Typschema (C) oder verboten?

---

## 7. Plugin- und Versions-SSOT: welche Quelle nennt die Version?

* **Backlog-Rang:** 29 (P2), Teil von 30 (P3) und 17 (P1)
* **Betroffene Findings:** `AUD-2026-09-107` (Medium) · `-108` (Low) · `-106` (Medium) · `-100` (High) · `-101` (High) · `-119` (Low) · `-103`/`-104`/`-105` (Low)

### Problem

Es gibt mindestens **vier** Orte, an denen eine Version steht, und keiner ist
verbindlich:

| Ort | gemessener Wert |
|---|---|
| `VERSION` (Projekt) | Referenzgröße |
| MCP `serverInfo.version` | **hart `1.0.0`**, live bestätigt, unabhängig von `VERSION` (`-107`) |
| `GET /api/v1/version/` | live **`{"app_version":"unknown"}`** (`-108`) |
| `integrations/hermes-agent-plugin/plugin.yaml` | **`0.1.0`** statt `VERSION`; von `build_hermes_plugin.py` **nicht erfasst** (`-106`) |
| `manifest.json` / `hermes-plugin.json` | Build-Artefakt, nicht versioniert (`-100`) |

Zusätzlich ist das Manifest ein **VS-Code-Schema**, nicht der
Hermes-`{name, api}`-Vertrag (`-101`), und `engines.hermes`, `permissions`,
`capabilities`, `tools`, `minHostVersion`, `auth` sind dekorativ.

Solange „welche Version gilt" nicht entschieden ist, kann **keine**
Kompatibilitätszusage zwischen Plugin, Server und Doku geprüft werden.

### Optionen

| Option | Beschreibung | Dafür | Dagegen |
|---|---|---|---|
| **A — `VERSION` ist SSOT** | Server liest `VERSION`; `serverInfo.version` wird daraus gespeist; Plugin-Manifeste werden beim Build erzeugt; `/api/v1/version/` liefert `VERSION` plus Commit-SHA. | Eine Zahl, überall identisch; `ABNAHME` und Doku werden prüfbar. | Erfordert, dass `serverInfo` und `/version/` nicht mehr hart kodieren — betrifft laufende Clients. |
| **B — Unabhängige Plugin-Version** | Jedes Plugin trägt seine **eigene** SemVer, unabhängig von der Server-Version; ein Kompatibilitätsfeld (`minServerVersion`) erklärt die Beziehung. | Plugins können unabhängig released werden; das ist die Host-Welt. | Braucht eine Kompatibilitätsmatrix, die jemand pflegen muss. |
| **C — Build-Artefakt als Wahrheit** | Was der Host installiert, ist die Wahrheit; Versionsangaben werden beim Build geschrieben und sind nicht editierbar. | Kein manueller Drift mehr. | Debugging über den installierten Stand hinaus wird unmöglich. |

### Bestehende ADR-Bezüge

* **Kein ADR regelt Plugin-/Server-Versionierung.**
* `docs/se/ADR/ADR-004_traeger_modell_und_auc.md` ist **`proposed`** und
  betrifft das Träger-/AUC-Modell, nicht Versionierung — **kein** direkter
  Konflikt, aber ein Beispiel dafür, dass ein `proposed`-ADR ohne
  `review`-Übergang liegen kann (`-338`: 5× Lifecycle-Sprung
  `proposed → accepted`).
* `AUD-2026-09-336`/`-337` (Dateinamen nicht konform, Statuswerte verlassen das
  lowercase-Enum) betreffen die **ADR-Dateien selbst** — dieselbe Konventionsfrage
  stellt sich bei Versionsfeldern.

### Frage an den User

> **Gibt es eine Projektversion, eine Pluginversion oder beides mit
> Kompatibilitätsfeld?** Falls eine: darf die MCP-`serverInfo`-Angabe eine
> eigene SemVer führen oder muss sie die Projektversion spiegeln? Und: wer
> pflegt die Kompatibilitätsmatrix, wenn sie Option B wird?

---

## 8. Erfolgs-/Fehlersemantik der Datenintegration: was darf ein Import melden?

* **Backlog-Rang:** 6 (P0), Teil von 16 (P1) und 27 (P2)
* **Betroffene Findings:** `AUD-2026-09-070` (Critical) · `-071` (Critical) · `-349` (High) · `-072` (High) · `-079` (Medium) · `-080` (Medium) · `-082` (Medium) · `-083` (Medium) · `-032` (High) · `-036` (High) · `-049` (Info)

### Problem

Ein wiederkehrendes Muster über alle drei Transporte: **die Oberfläche meldet
Erfolg für Zustände, in denen nichts passiert ist.**

| Fall | gemeldet | tatsächlich |
|---|---|---|
| CSV-Import des eigenen Exports | `HTTP 201 success: true` | **0 Zeilen** importiert (`-070`) |
| ReqIF-Import | `success: true` | **915** „internal error" (`-071`, `-349`) |
| CSV-Import, dreifach | dreimal `success: true` | **3 Duplikate** (`-072`) |
| kaputtes Quoting | `201 success` | Restzeile im Titel (`-080`) |
| ungültiger `type`/`level` | `400` mit **`errors: []`** | Ursache unbekannt (`-079`) |
| BOM / falscher Delimiter | `title is missing or empty` | Meldung beschreibt die **Daten**, nicht die Ursache (`-083`) |
| MCP `tools/call` mit ungültigem Input | `-32603` „internal error" | Validierungsfehler (`-036`, `-040`) |
| `/mcp/`-404 vs. `/api/v1/mcp/`-404 | HTML vs. JSON | zwei Formate (`-049`) |

Der Schaden ist nicht der Einzelfehler, sondern ein **öffentlicher Vertrag ohne
vereinbarte Fehlersemantik**: ein Aufrufer kann „Erfolg" nicht von „stillschweigend
gescheitert" unterscheiden — das ist Muster 2 des Summaries.

### Optionen

| Option | Beschreibung | Dafür | Dagegen |
|---|---|---|---|
| **A — Ein Vertrag für alle Import-/Aufrufpfade** | Jeder dieser Endpunkte liefert dasselbe Ergebnismodell: `succeeded` / `skipped` / `failed` mit **Ursache je Zeile**; `success: true` nur bei `failed == 0`. Zusätzlich `Idempotency-Key` für Importe. | Der Aufrufer kann prüfen; Round-Trip wird testbar; ein Muster statt 8 Einzelfixes. | Ein Breaking Change für alle Clients, die auf `success: true` prüfen ⇒ Deprecation-Fenster nötig. |
| **B — Vertrag nur für Importe, MCP bleibt Spec** | Importpfade bekommen das Ergebnismodell; MCP richtet sich **streng** nach JSON-RPC 2.0 (Spec-Fehlercodes statt `internal error`). | Zwei klare Regeln statt einer vermischten; MCP-Spec bleibt unangetastet. | REST-Import und MCP-Tool melden unterschiedlich — die Fehlermatrix wird zweigeteilt, aber jeweils sauber. |
| **C — Bestehende Formate, aber mit ehrlichem Status** | Kein neues Modell; nur die Bedingung verschärfen: bei `failed > 0` HTTP 207/422 statt 201, `errors` wird **niemals** leer geliefert. | Kleinster Eingriff; bestehende Clients brechen nur im Fehlerfall, der vorher **falsch** Erfolg meldete. | Keine programmatische Teil-Erfolgs-Auswertung; `errors` bleibt unstrukturiert. |

### Bestehende ADR-Bezüge

* **Kein ADR regelt die Fehlersemantik der Integrationen.** Das ist die Wurzel
  des Problems: die WP-Reports haben jeweils lokal entschieden, ohne gemeinsame
  Grundlage.
* **Abgrenzung zu ADR-Kandidat #3:** dort geht es um *Verfügbarkeit*
  (`/health/`), hier um *Korrektheit der Antwort*. Beide betreffen
  Fehlersemantik, aber an verschiedenen Stellen.
* `docs/se/ADR/ADR-003_Glossar-Storage.md` ist ein Präzedenzfall dafür, dass ein
  Austauschformat (Glossar) eine eigene Entscheidung bekommt — ReqIF und CSV
  sind formal dasselbe.

### Frage an den User

> **Werden Importpfade ein einheitliches Ergebnismodell bekommen (A), nur
> Imports (B) oder bleibt es bei einer verschärften Bedingung (C)?** Und:
> **muss** ein Import idempotent sein — mit verpflichtendem `Idempotency-Key`
> oder mit fachlicher Duplikaterkennung? Die Frage entscheidet, ob der
> P0-Eintrag 6 als Konfiguration oder als Vertragsänderung umzusetzen ist.

---

## 9. Was **kein** ADR-Kandidat ist

Ausdrücklich nicht aufgenommen, weil es ein Fix und keine Entscheidung ist:

| Befund | Warum kein ADR |
|---|---|
| `AUD-2026-09-030`, `-131` (`CACHES` ohne Timeout) | Konfigurationsvertrag unter bestehender Health-/Resilience-Entscheidung. Die *Vertragsfrage* (fail-closed vs. degraded) ist Kandidat #3, der Timeout selbst nicht. |
| `AUD-2026-09-126` (`task_acks_late=False`) | Klassische Zustellentscheidung mit einer empfohlenen Antwort; die Architekturfrage ist Kandidat #4. |
| `AUD-2026-09-238` (Prompt-Injection) | Der Handlungsbedarf ist unstrittig, die Korrektur lokal. |
| `AUD-2026-09-281`, `-282` (Lost Update) | Korrektheit gegen einen bereits akzeptierten Vertrag (Transaktionsgarantie). |
| `AUD-2026-09-193` (CI-Testlücke) | Nachweisdisziplin, keine Architektur. |
| `AUD-2026-09-037`, `-084` (Doku-Drift) | Dokumentationskorrektur; die nachhaltige Lösung (Ableitung statt Pflege) ist klein und ohne Trade-off. |
| `AUD-2026-09-224`, `-225` (Supply Chain) | Etablierte Praxis mit empfohlener Ausprägung. |

---

*Erstellt von `documenter` am 2026-09-30. **Es wurde keine ADR geschrieben.**
`docs/se/ADR/` ist unverändert. Jeder Kandidat nennt die Finding-IDs, die ihn
ausgelöst haben; die technische Begründung steht in den WP-Reports unter
[`AUDIT_EVIDENCE/`](AUDIT_EVIDENCE/).*



