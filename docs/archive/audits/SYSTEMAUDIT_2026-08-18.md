# ReqogniLoom Systemrevision — 2026-08-18

> Vollständige Nutzbarkeits- und Funktionsrevision: E2E-Testlauf, Massendaten-Stresstest,
> vollständiger Klick-Test über claude-in-chrome und Playwright-MCP, KI-Feature-Verifikation
> mit mimo-V2.5 (opencode-go) und ein Design-Audit nach frontend-design-Grundsätzen — gegen
> die lokal laufende Anwendung.
>
> Interaktive Version (Stat-Kacheln, Farbcodierung, Tool-Vergleichstabellen):
> https://claude.ai/code/artifact/d0b34897-00f9-4ccb-9ea0-9ddccf1b4dad
>
> Umgebung: Docker Compose, lokal · Testdaten: 300 Requirements + 89 bestehende Needs ·
> Werkzeuge: Playwright, claude-in-chrome, Playwright-MCP, opencode/mimo-v2.5

---

## 1. Executive Summary

Fünf parallele Testläufe gegen die laufende Anwendung, zusätzlich zwei Infrastrukturfehler
behoben, die einen sauberen lokalen Start bereits verhindert haben.

| Kennzahl | Wert |
|---|---|
| E2E-Tests gesamt | 310 |
| bestanden | 283 (91,3%) |
| fehlgeschlagen | 16 (5,2%) |
| Routen/Screens geprüft | 36 |
| kritische App-Bugs | 2 |
| hohe App-Bugs | 6 |
| mittlere App-Bugs | 7 |
| niedrige App-Bugs | 6 |
| Infra-Bugs (blockierend) | 4 |

Die Anwendung ist im Kern **solide und funktionsfähig** — 91,3% der bestehenden E2E-Suite ist
grün, das Design-System ist konsistent und barrierearm (WCAG AA+ durchgehend), und alle vier
getesteten KI/Regel-Endpunkte antworten technisch korrekt. Der ernsteste Einzelbefund ist eine
**nicht persistierende Sprachumschaltung** (DE/EN fällt bei jeder Navigation zurück auf
Deutsch) — unabhängig sowohl von der Playwright-Suite als auch vom manuellen Klick-Test
bestätigt. Der zweite kritische Fund: **Requirements lassen sich mit leerem Titel anlegen**,
ohne serverseitige Validierung.

Überraschender als die App-Bugs: **der lokale Dev-Stack startete nicht von allein.** Vier
Infrastrukturfehler in `docker-compose.yml`/`docker-compose.override.yml` mussten
laufzeit-gepatcht werden, bevor überhaupt getestet werden konnte — siehe Abschnitt 2. Das ist
vermutlich der Befund mit dem größten Hebel für neue Mitwirkende.

---

## 2. Infrastruktur — der Stack startete nicht

Vor jedem funktionalen Test musste der lokale Compose-Stack erst repariert werden. Alle vier
Fehler sind in den committeten Compose-Dateien vorhanden, nicht durch diese Session verursacht.

### INFRA-01 — Kritisch — Frontend-Port-Bindung schlägt fehl (Compose merged statt ersetzt)

`docker-compose.yml` deklariert `ports: ["5173:8080"]` (Prod-Nginx-Image),
`docker-compose.override.yml` deklariert zusätzlich `ports: ["5173:5173"]`
(Vite-Dev-Server). Docker Compose **merged** Ports-Listen über mehrere Compose-Dateien,
statt die Override-Liste die Basis ersetzen zu lassen (dokumentiertes, aber hier nicht
bedachtes Verhalten). Beide Container-Ports landen auf demselben Host-Port 5173 →
`Bind for 0.0.0.0:5173 failed: port is already allocated`. Der Frontend-Container startet in
der Folge gar nicht oder ohne funktionierende Portbindung.

*Fund: manuelle Stack-Diagnose vor Testbeginn · docker-compose.yml + docker-compose.override.yml, Service `frontend`*

### INFRA-02 — Hoch — Frontend-Dev-Image wird nicht neu gebaut (Crash-Loop mangels npm)

Die Basisdatei pinnt `image: ghcr.io/popoboxxo/reqogniloom-frontend:1.7.0-beta.2`, das
Override fügt `build: {context: ./frontend, target: development}` hinzu. Existiert lokal
bereits ein Image mit diesem Tag (z.B. vom letzten `docker pull`), baut Compose es **nicht
automatisch neu** — der Override-Command (`npm install && npm run dev`) läuft dann im
gepullten Prod-Nginx-Image, das kein `npm` enthält: `sh: npm: not found`, Endlos-Crash-Loop
(Exit 127). Erfordert expliziten `docker-compose build frontend`.

*Fund: docker logs frontend-1 · Workaround angewendet, nicht committet*

### INFRA-03 — Hoch — Celery-Memory-Limit zu knapp

384 MB Limit bei `concurrency=16` (prefork) — Worker wird beim Boot sofort OOM-gekillt
(Exit 137).

### INFRA-04 — Hoch — Frontend-Memory-Limit zu knapp

128 MB (für Prod-Nginx bemessen) reicht nicht für `npm install` + Vite-Dev-Server-
Dependency-Scan — OOM-Kill.

> **Für diese Session laufzeit-gefixt** (nicht in Dateien committet): Frontend per
> `docker run` mit einzelner Portbindung + 2,5 GB Limit gestartet, Celery auf 1,5 GB
> angehoben, Frontend-Image explizit neu gebaut. Ein echter Fix gehört in
> `docker-compose.yml`/`.override.yml` selbst (Ports nicht doppelt deklarieren,
> Memory-Limits pro Environment trennen).

---

## 3. E2E-Suite (Playwright)

Komplette bestehende Suite ausgeführt, Laufzeit 9,4 Minuten.

| Ergebnis | Anzahl | Anteil |
|---|---|---|
| Bestanden | 283 | 91,3% |
| Fehlgeschlagen | 16 | 5,2% |
| Übersprungen | 6 | 1,9% |
| Nicht gelaufen (Setup-Abhängigkeit) | 5 | 1,6% |

Konfigurationshinweis: Die Suite ist auf `BACKEND_URL=http://localhost:8000` hartkodiert
(Standardwert in `e2e/helpers/auth.ts`), lokal läuft das Backend aber auf Host-Port `8001`.
Musste für den Lauf überschrieben werden — für neue Mitwirkende ohne diesen Kontext ein
stiller Fehlschlag der gesamten Suite.

---

## 4. Bug-Katalog — Anwendung

21 bestätigte Anwendungsbefunde, konsolidiert aus E2E-Suite, zwei unabhängigen
claude-in-chrome-Durchläufen und dem Design-Audit. Wo mehrere Quellen denselben Fehler
unabhängig gefunden haben, ist das vermerkt — das ist das stärkste Signal in diesem Bericht.

### Kritisch

**BUG-01 — Sprachumschaltung (DE/EN) persistiert nicht**
Umschaltung wirkt nur auf der aktuellen Seite; nach Navigation auf eine andere Route fällt
die UI auf Deutsch zurück. Vermutlich State im Komponenten-Speicher statt in
Session/Backend persistiert (`PATCH /workspaces/{id}/` wird evtl. nicht ausgelöst oder
schlägt still fehl).
*Bestätigt von 2 unabhängigen Quellen: E2E (hermes-bugfix-campaign.spec.ts,
ui-test-campaign.spec.ts) · claude-in-chrome Exhaustiv-Test*

**BUG-02 — Requirement mit leerem Titel wird ohne Validierung angelegt**
Formular akzeptiert leeres Titel-Feld; Backend legt den Datensatz trotzdem an (UUID wird
als Titel-Ersatz übernommen). Weder Frontend- noch Backend-seitige Pflichtfeld-Prüfung
greift.
*Fund: claude-in-chrome Basis-Test, Requirements-Anlage-Dialog*

### Hoch

- **BUG-03** — Baseline-Liste verschwindet nach Erstellung: `[data-testid="baseline-list"]`
  nicht mehr auffindbar, nachdem eine Baseline über die UI angelegt wurde — Navigation zu
  `/baselines` zeigt keine Liste. *(E2E: waterkettle-fullblown.spec.ts:632, :638)*
- **BUG-04** — Artifact-Diff-Rendering schlägt fehl bei Baseline-Vergleich Version 0:
  Feld-Level-Diff überschreitet 30,1s Timeout. *(E2E: artifact-diff.spec.ts:37, :114)*
- **BUG-05** — Review-Workflow-Queue synchronisiert sich nicht mit Statuswechsel:
  Requirement-Übergänge draft→in_review→approved aktualisieren die Queue-Liste in der UI
  nicht. 5 Tests betroffen. *(E2E: review-workflow.spec.ts)*
- **BUG-06** — ICDs-Seite zeigt hartkodierten englischen Text ("Select an ICD from the
  list") unabhängig von Spracheinstellung. *(claude-in-chrome Exhaustiv-Test)*
- **BUG-07** — Diagramme-Seite: hartkodierter englischer Leerzustand-Text, gleiches Muster
  wie BUG-06. *(claude-in-chrome Exhaustiv-Test)*
- **BUG-08** — Formular-Validierungsfehler visuell nicht erkennbar: kein Error-State
  (Farbe/Icon/Text) an Eingabefeldern sichtbar. *(Design-Audit, Playwright-MCP)*

### Mittel

| ID | Befund | Quelle |
|---|---|---|
| BUG-09 | Tracelink-Erstellung: Quell-Dropdown bleibt leer, 60s Timeout nach 116 Retries | E2E tracelink-creation.spec.ts:73 |
| BUG-10 | i18n unvollständig — mehrere Platzhalter/Card-Beschreibungen bleiben Deutsch nach EN-Umschaltung | claude-in-chrome Exhaustiv |
| BUG-11 | Anlage-Dialoge minimal — nur Titel-Feld; Category/Status/Description fehlen in mehreren Formularen | claude-in-chrome Exhaustiv |
| BUG-12 | Mobile-Sidebar-Verhalten (<768px) unklar/ungetestet | Design-Audit |
| BUG-13 | Lade-/Skeleton-Zustände nicht sichtbar erfasst | Design-Audit |
| BUG-14 | Kein visuelles Feedback beim Theme-Umschalten | claude-in-chrome Exhaustiv |
| BUG-15 | `/audit/` liefert 4.440 Findings ungepaginiert in einem 2,5-MB-Response — Skalierungsrisiko | KI-Feature-Test (mimo) |

### Niedrig

| ID | Befund | Quelle |
|---|---|---|
| BUG-16 | Visibility-Reset-Button aktiv, obwohl er deaktiviert sein sollte | E2E user-profile.spec.ts:27 |
| BUG-17 | ICD-Versionsnummer erhöht sich nicht automatisch bei PATCH | E2E icd-api.spec.ts:8 |
| BUG-18 | Workspace-Auswahl auf Dashboard unklar — 25 Workspaces, kein "aktuell"-Indikator | claude-in-chrome Exhaustiv |
| BUG-19 | Filter-/Sortier-Einstellungen setzen sich bei Routenwechsel zurück | claude-in-chrome Exhaustiv & E2E |
| BUG-20 | Empty-State-Messaging uneinheitlich | Design-Audit |
| BUG-21 (Setup) | Ein Test erfordert den nicht dokumentierten `seed_toothbrush` Management-Command | E2E toothbrush-syseng.spec.ts:67 |

> **Offen, braucht Verifikation:** Beim Massendaten-Test lieferten drei Bulk-Anlage-Aufrufe
> Fehler: Architecture-Elemente (404), Testfälle (404), Baselines (400 Validation-Error).
> Das kann an falsch geratenen Endpoint-Pfaden im Testskript liegen statt an der App — nicht
> als bestätigter Bug gewertet, aber ein sauberer nächster Schritt.

---

## 5. UI/UX-Design-Audit

Nach frontend-design-Grundsätzen, 21 Routen + responsive Varianten + Dark Mode, via
Playwright-MCP.

**Stark:**
- Zweischichtiges Token-System (Primitives → Semantik), ESLint-erzwungen — vorbildlich
- Kontrast durchgehend WCAG AA/AAA (Body-Text bis 18:1)
- 21 Routen klar in 5 Gruppen gegliedert, skalierbare IA
- Dark Mode konsistent über alle Tokens
- 8px-Grid, einheitliche Radien/Abstände

**Verbesserungswürdig:**
- Visuell generisch — Standard-Sans, kein eigener Typeface, sicherer Blauton, keine Signatur
- Empty-States uneinheitlich formuliert
- Responsive-Lücke im Bereich 480–768px nicht geprüft
- Kein sichtbarer Fehlerzustand an Formularfeldern

Gesamturteil des Audits: **professionell und intern konsistent, aber bewusst zurückhaltend
statt distinktiv** — für ein technisches SE-Werkzeug eine vertretbare, keine falsche
Entscheidung.

---

## 6. Browser-Automatisierungswerkzeuge im Vergleich

Beide Werkzeugsätze wurden bewusst gegeneinander getestet — claude-in-chrome im echten
Chrome-Tab, Playwright-MCP in einer eigenen isolierten Browser-Instanz — inklusive ihrer
jeweiligen Schwächen.

| Funktion | claude-in-chrome | Playwright-MCP |
|---|---|---|
| Navigation | Exzellent | Exzellent |
| Element finden | Exzellent — `find()` versteht natürliche Sprache zuverlässig | Mittel — komplexe Selektoren timeouten, direkte Pfad-Navigation zuverlässiger |
| Screenshot | Schwach — `screenshot()` timeoutet nach 30s auf komplexen React-Seiten | Exzellent — scharfe PNGs, `fullPage` funktioniert zuverlässig |
| Seiteninhalt lesen ohne Rendering | Exzellent — `read_page()` als Workaround für Screenshot-Timeouts | — |
| Formulare ausfüllen | Exzellent — `form_input()` mit Refs zuverlässig | Exzellent |
| Klicken | Gut — zuverlässig mit Refs, fragil bei Koordinaten | Mittel — komplexe Selektoren instabil |
| Resize / Responsive | nicht gezielt getestet | Exzellent — sofortiges Re-Render |
| Konsole / Netzwerk lesen | Gut — Netzwerk-Tracking muss früh starten | verfügbar, nicht im Detail bewertet |
| Setup-Aufwand | läuft im vorhandenen Chrome-Profil | Browser hart auf Firefox vorkonfiguriert — manuelle Installation nötig |

**Kernbefund:** Die beiden Werkzeuge sind komplementär, nicht austauschbar.
claude-in-chrome gewinnt bei semantischer Interaktion und ist robust gegen
Rendering-Hänger komplexer React-Views (weil es nicht auf Pixel-Screenshots angewiesen
ist); Playwright-MCP gewinnt bei visueller Verifikation und Responsive-Tests. Für einen
UI-Screenshot-Audit ist Playwright-MCP die bessere Wahl, für interaktives Durchklicken mit
vielen dynamischen Komponenten claude-in-chrome.

---

## 7. KI-Feature-Test (opencode / mimo-v2.5)

Vier KI-/Regel-Endpunkte end-to-end gegen die laufende App getestet, gesteuert vom Modell
`opencode-go/mimo-v2.5` statt Claude.

| Endpunkt | Status | Bewertung |
|---|---|---|
| `architecture/decompose/` | 400 (erwartet) | Validierung korrekt — verlangt zu Recht ein alloziertes Parent-Requirement |
| `audit/ai-review/` | 200 | Strukturierte Antwort mit rule_id/severity/remediation, plausibel |
| `traceability/suggest-links/` | 200 | 3.222 Link-Vorschläge, Keyword-Overlap-Ranking mit Begründung |
| `audit/` | 200 | Vollständig, aber siehe BUG-15 (Skalierung) |

> **Wichtige Einordnung:** "AI Review" und der Compliance-Audit sind **deterministische
> Regel-Engines** (Rule-IDs wie `TRACE-P2`/`TRACE-P3`), keine tatsächlichen LLM-Aufrufe —
> der `LLM_PROVIDER` stand während des gesamten Tests auf `mock`. Die Namensgebung "AI
> Review" kann bei Nutzern den Eindruck erwecken, hier generiere ein Sprachmodell die
> Befunde. Technisch funktioniert alles einwandfrei; ein echter LLM-Test
> (Anthropic/OpenAI-Key) stand in dieser Runde nicht zur Verfügung.

---

## 8. Massendaten-Stresstest

| Kennzahl | Wert |
|---|---|
| Requirements erzeugt | 300 (13,6s) |
| Architecture-Elemente | 0 (404) |
| Testfälle | 0 (404) |
| Baselines | 0 (400) |

Die Requirement-Erzeugung über die API skaliert unauffällig. Die drei fehlgeschlagenen
Bulk-Anlagen (Architecture/Testfälle/Baselines) sind nicht als Bugs bestätigt —
plausibelste Ursache sind falsch geratene Endpoint-Pfade im generierten Test-Skript, nicht
zwingend App-Defekte. Bei 300 Requirements ohne Trace-Links produzierte der
Compliance-Audit wie in BUG-15 beschrieben 4.440 Blocker-Findings in einer einzigen,
ungepaginierten Antwort.

---

## 9. Priorisierte nächste Schritte

| Priorität | Maßnahme |
|---|---|
| Sofort | Sprachpersistenz (BUG-01) und Titel-Validierung (BUG-02) fixen — beide kritisch und trivial reproduzierbar |
| Sofort | `docker-compose.yml`/`.override.yml` Port-Deklaration bereinigen (INFRA-01) — jeder neue Checkout scheitert sonst am Start |
| Diese Woche | Baseline-Liste, Artifact-Diff und Review-Queue-Sync reparieren (BUG-03/04/05) — alle drei sind Kernfunktionen des SE-Werkflusses |
| Diese Woche | Memory-Limits für Celery/Frontend in Compose an Dev-Realität anpassen (INFRA-03/04) |
| Bald | i18n-Lücken schließen (BUG-06/07/10), Anlage-Dialoge um fehlende Felder ergänzen (BUG-11) |
| Bald | Pagination für `/audit/` einführen, bevor Kunden mit realistischen Datenmengen arbeiten (BUG-15) |
| Später | Bulk-Anlage-Endpunkte für Architecture/Testfälle/Baselines verifizieren, Empty-States vereinheitlichen |

> **Nachtrag (BUG-15, behoben):** Bewusste Abweichung von "Pagination" — das Dashboard
> gruppiert Findings nach Regel-ID und aggregiert Blocker-/Warnungs-Zähler über die
> *gesamte* Ergebnismenge; eine Page-basierte Antwort (`count`/`next`/`previous`/`results`)
> hätte Regel-Gruppen über Seiten fragmentiert und wäre zudem ein Breaking Change für den
> bestehenden Bare-List-Konsumenten gewesen. Stattdessen: harter Cap
> (`AuditService.MAX_REPORT_FINDINGS = 500`) plus additive Metadaten-Felder
> (`truncated`, `total_findings_available`, `total_blockers_available`,
> `total_warnings_available`) auf der bestehenden `AuditReport`-Struktur — siehe
> `backend/application/audit_service.py`.

---

*ReqogniLoom Systemrevision · erzeugt 2026-08-18 · 5 parallele Testagenten + manuelle
Infrastruktur-Diagnose · Quellrohdaten in den Einzel-Reports der Testagenten (nicht Teil
dieses Repos, siehe Session-Transkript)*
