# Release-Bericht v1.8.0-beta.17

> **Status: interner Pre-Release-Cut. Keine Produktions-, Staging- oder
> QA-Freigabe.** Der Schnitt ist bewusst als Beta geführt: W5 ist nicht
> entschieden, und für bereits gebootstrapte Instanzen ist ein
> Upgrade-Pfad-Lücken dokumentiert (Abschnitt 9).

## 1. Release-Ziel

`v1.8.0-beta.17` bündelt den QA-Sweep (PR #1105) und die vier
Entscheidungswellen W1–W4 (PR #1111) inklusive der fünf dazugehörigen
accepted ADRs. Anders als `beta.16` ist der Schnitt **grün**: die
Regression-Suite ist vollständig grün, und W1–W4 sind abgeschlossen.

Der Schnitt trennt zwei Dinge ausdrücklich:

- **Was erfixt ist:** W1–W4 sind implementiert, dokumentiert und getestet.
- **Was er nicht behauptet:** W5 (Baseline-Rollback-Semantik) ist offen, und
  die geänderten Feldkinds aus ADR-006 wandern auf Altinstanzen nicht
  automatisch (Abschnitt 9.1). Beides ist kein Blocker für einen internen
  Beta, aber beides ist eine Aussage, die man nicht unterschreiben sollte,
  ohne sie zu lesen.

## 2. Release-Cutoff (exakter Zeitstempel)

| Feld | Wert |
|---|---|
| Schnitt-Branch | `release/v1.8.0-beta.17` |
| Basis-Commit | `2c4709b079f880edc671790e5ac73d3c788f9217` |
| Merge-PR | #1111 (squash) auf `feat/decision-waves-2026-09` |
| Vorgänger | `origin/release/v1.8.0-beta.16` |
| Commits im Schnitt | 19 |
| Cut-Datum | 2026-09-27 |

Die QA-Sweep-Änderungen sind inhaltlich in beiden Ständen identisch
(`git diff` zwischen `release/v1.8.0-beta.16` und dem Basis-Commit zeigt nur
die Wellen-Dateien), deshalb ist der Basis-Commit des Schnitts ausreichend.

## 3. Enthaltene PRs seit dem Cutoff

| PR | Thema | Commit |
|---|---|---|
| #1111 | Entscheidungswellen W1–W4, ADRs, CI-Fix | `2c4709b0` |
| #1111 | ADR-Record (Basis des Merges) | `1f710c41` |
| #1085 | MCP-Oberflächen-Zählungen in README und Doku | `b30767f2`, `98b1c9a8`, `23ffed8d` |
| #1089 | KI-Ableitungen reviewbar | `5447ec1e` |
| #1087, #1094 | Strg+S speichern, System-ID kopieren | `16af6b55` |
| #1092, #1091, #1093 | KI-Aktionen, Design-System-Dialoge und Paletten | `bca525ee`, `dbf617ff` |
| #1090 | Attributkatalog übersetzen statt Feldnamen | `ce79b513` |
| #1082, #1083 | AWMS: ehrlicher Migrationsumfang, echtes Rollback | `3081b812` |
| #1081 | Einheitliches Error-Envelope über alle Adapter | `1402e84f`, `256e064f` |
| #1080 | `test.run_list` über MCP | `65c732b4` |
| #1077 | Fremder Workspace: 403 JSON statt 500 HTML | `112a9afe` |
| #1076 | API-Key-Header-Präzedenz festgenagelt | `cf7eac9b` |
| #1075 | Subtyp-Entitäten als TraceLink-Endpunkte | `f240c1f8` |
| #1074 | Deployment darf keinen Defekt als Erfolg melden | `ad1cf124` |
| #1076 / Zeitbudget | Source-Scans mit explizitem Zeitbudget | `6f6a4ef8` |

## 4. Themen-Highlights

### 4.1 W1 — `Requirement.level` wird abgeleitet (ADR-005)

Der Level ist keine Eingabe mehr, sondern eine Ableitung aus der Hierarchie.
Bei jeder Hierarchie-Änderung wird er über **alle** betroffenen Pfade neu
berechnet. Eine Wurzel ohne Elternstück bleibt `1`; ein explizites `NULL`
bleibt `NULL` und wird nicht stillschweigend auf einen Default gesetzt.
Abgeleitete Level werden nie als Client-Input persistiert.

**Kontrakt:** `level` ist read-only. Ein Client, der `level` mitsendet, wird
auf diesem Feld ignoriert, nicht abgelehnt.

### 4.2 W2 — Personenfelder und Freitext (ADR-006)

`Artifact.stakeholder` ist eine Mehrfachauswahl mit Katalogoptionen,
`Adr.deciders` und `Issue.assignee` sind `Actor`-Beziehungen (M2M) statt
loser Strings, `origin_link` entfällt. Migration `0102` bringt die
RLS-Policies der berührten Tabellen mit.

### 4.3 W3 — Regel-Vokabular (ADR-007)

Die vier `REQ_MUST_HAVE_*`-Regeln sind auf das Audit-Regel-Vokabular
abgebildet, mit dokumentierter Source-Konvention (ADR- plus REQ-Verweis).
Die SE-Regeln werden am **Baseline-Gate** durchgesetzt.

### 4.4 W4 — Benachrichtigungen wandern in den Assistenten (ADR-009)

Die Sidebar-`NotificationBell` entfällt. Der Feed lebt am
Assistenten-Einstiegspunkt (`InterviewWidget` + `NotificationFeed` +
`useNotificationFeed`) und ist über die Profileinstellungen erreichbar.

### 4.5 QA-Sweep

24 Befunde wurden triagiert und geschlossen, darunter der
Foreign-Workspace-Fall (`#1077`, `500`+HTML → `403`+JSON), das einheitliche
Error-Envelope (`#1081`), die TraceLink-Auflösung für Subtypen (`#1075`) und
der fail-closed Deploy-Schritt (`#1074`).

## 5. Versions-Carrier (Delta dieses Commits)

12 Carrier in 14 Dateien, 23 Ersetzungen, alle von `1.8.0-beta.16` auf
`1.8.0-beta.17`:

| Datei | Treffer |
|---|---|
| `VERSION` | 1 |
| `.env.example` | 2 |
| `deploy/docker-compose.yml` | 6 |
| `deploy/docker-compose.minimal.yml` | 3 |
| `frontend/package.json` | 1 |
| `frontend/package-lock.json` | 2 |
| `integrations/hermes-plugin/reqogniloom/package.json` | 1 |
| `integrations/hermes-plugin/reqogniloom/package-lock.json` | 2 |
| `integrations/hermes-plugin/reqogniloom/hermes-plugin.json` | 1 |
| `dist/plugins/antigravity/reqogniloom/plugin.json` | 1 |
| `dist/plugins/claude-code/reqogniloom/.claude-plugin/plugin.json` | 1 |
| `site/index.html` | 2 |

Bewusst **nicht** angefasst: `deploy/docker-compose.override.yml` und
`deploy/docker-compose.test.yml`. Beide tragen Versionsstrings, sind aber
dev- bzw. testoverlays und gehören nicht zum Release; ein Glob über
`docker-compose*.yml` hätte sie mitgenommen.

### 5.1 Doku-Stände, die mit dem Schnitt mitziehen mussten

Vier Stellen behaupteten nach dem Bump noch den Vorgängerstand und sind
mitgezogen, weil sie den *aktuellen* Release bezeichnen:

| Datei | Stelle |
|---|---|
| `docs/api/MCP-SURFACE.md:28` | `Version`-Zeile, die `VERSION` ausdrücklich als Quelle zitiert |
| `docs/CODEBASE_OVERVIEW.md:20, 657, 1139` | „Stand `v1.8.0-beta.16`" an den drei MCP-Fundstellen |

Die Zahlen selbst (219 Tools / 35 Gruppen) sind unverändert: W1–W4 haben
kein Tool, keine Gruppe und keinen `inputSchema` angefasst. Die Provenienz
wurde deshalb getrennt von der Versionsangabe geführt — die
`Measured at`-Zeile und der History-Eintrag in `MCP-SURFACE.md` nennen
weiter `98b1c9a8` bzw. `9eb2fc58`, weil das die Stellen sind, an denen
tatsächlich gemessen wurde.

### 5.2 Bewusst nicht angefasst: `tool-manifest.json`

`docs/agent-templates/tool-manifest.json` trägt
`"generated_from": "reqogniloom==1.8.0-beta.16"`. Das ist ein
Provenienz-Stempel des generierten Artefakts, kein Versionscarrier. Der
Inhalt ist weiterhin korrekt (der MCP-Ratchet und der Job
*Agent Templates & Distribution* sind beide grün), deshalb wurde die Datei
nicht neu generiert, nur um einen String zu aktualisieren.

## 6. Verifikation

### 6.1 CI (maßgebliche Release-Bedingung)

`14/14` Checks grün auf `0fcb2027`:

| Gate | Ergebnis |
|---|---|
| `lint` | pass (31s) |
| `frontend-test` | pass (2m07s) |
| `backend-test` set-1..set-4 | pass |
| `e2e (1)`..`e2e (4)` | pass (9m45s / 11m51s / 11m48s / ~12m) |
| `Workflow Lint (actionlint)` | pass |
| `Agent Templates & Distribution` | pass |
| `Backend Requirements Drift Check` | pass |
| `Hermes IDE Plugin` | pass |

`ci_green_on_base_commit: true` ist damit erfüllt — anders als bei
`beta.16`, wo der Schnitt bewusst rot war.

### 6.2 Backend (lokal)

`10015 passed, 13 skipped, 1 xfailed` sowie 4 Errors, die ausschließlich in
`test_mcp_api_key_roles.py` liegen und einen Live-Stack brauchen. Dieselben
Dateien laufen in den CI-Backend-Sets grün durch.

### 6.3 Frontend (lokal)

`250/250` Testdateien grün im finalen Full Run. Ein früherer Lauf im selben
Zyklus zeigte 3 intermittierende Fehler, die nicht reproduziert wurden —
sie sind deshalb hier als *nicht reproduzierbar* vermerkt und nicht als
behoben verbucht.

### 6.4 Statische Checks

- `ruff --select=F821,F822` — clean
- `npx tsc -p tsconfig.build.json --noEmit` — clean
- `npm run lint` — mit frischem `npm install` exakt wie CI reproduziert:
  **0 errors, 290 warnings**. Der Lint-Fix ist damit gegen die echte
  CI-Bedingung geprüft, nicht gegen ein veraltetes `node_modules`.

### 6.5 Zielgerichteter E2E

`overlay-dismissal.spec.ts` **6/6 grün** gegen einen laufenden Stack nach
der Umstellung der Pins.

## 7. Was dieser Schnitt **nicht** beweist

- **Kein E2E-Lauf gegen eine verschmutzte Datenbank.** Der lokale
  Dev-Datenbestand enthielt 357 Alt-Workspaces aus
  `e2e-*`-Läufen. Sechs Tests (`review-workflow`, `user-profile`) schlagen
  dort fehl, weil `getWorkspaceId` in `e2e/helpers/auth.ts` `items[0]` aus
  der Workspace-Liste nimmt und damit auf einen Testrest ohne
  `draft → in_review`-Kante stößt. Das ist **kein Produktdefekt**: dieselben
  Tests sind in CI auf frischer Datenbank grün. Die Ursache wurde
  gemessen, nicht geraten.
- **Kein Attributkatalog-Nachweis für Altinstanzen** — siehe 9.1. Der
  Fresh-Instance-Pfad ist durch die grünen E2E-Shards belegt, der
  Upgrade-Pfad nicht.
- **Kein `make test` als Gate** — dieselbe Einschränkung wie in beta.16.

## 8. Offene Punkte / Follow-ups

### 8.1 ADR-006-Feldkinds auf Altinstanzen — gemessen offen

`bootstrap_attribute_definitions` ohne `--reset` ergänzt **nur fehlende**
Attribute: es ändert die `field_kind` eines bestehenden Attributs nie und
entfernt keins. Auf einer vor diesem Schnitt gebootstrappten Instanz wurde
der Zustand nach dem Upgrade gemessen:

| Attribut | erwartet | gemessen |
|---|---|---|
| `stakeholder` | Multi-Select mit Optionen | `text` |
| `deciders` | Actor-Referenz | `text` |
| `assignee` | Actor-Referenz | `text` |
| `origin_link` | entfernt | **noch vorhanden** |

Konsequenz: das UI bietet auf solchen Instanzen weiterhin Freitext für
`stakeholder` und weiterhin `origin_link` an, obwohl die Modellspalte
entfallen ist. Der einzige heutige Weg zu den neuen Feldkinds ist
`--reset`, das die gespeicherte Definition überschreibt und damit
Admin-Customisierungen verwirft. Eine echte Wertmigration ist als
Follow-up erfasst — es ist die AWMS-Wertmigrations-Lücke (#940) an einer
zweiten Stelle.

Für einen **frischen** Stack ist alles korrekt; das belegen die grünen
E2E-Shards, die gegen eine frische Datenbank laufen.

### 8.2 W5 — Baseline-Rollback: additiv oder CCB (#50)

Aus derselben Entscheidungsrunde, nicht entschieden. Die akten Empfehlung
lautet *additiv jetzt, optionales CCB-Gate später*. Es ist kein W5-Code in
diesem Schnitt.

### 8.3 Ein verschobenes Overlay kann seinen Dismiss-Pfad still verlieren

Die `#985`-Pins zeigten einen vollen Zyklus lang auf eine entfernte
Komponente, ohne dass jemand es bemerkte. Genau das ist die Regression-
Klasse, die #985 verhindern soll. Die Pins wurden deshalb beibehalten und
nicht gelöscht. Eine statische Prüfung auf `data-testid`s, die es nicht
mehr gibt, würde die Klasse schließen.

### 8.4 Der E2E-Workspace-Helper ist reihenfolgeabhängig

`getWorkspaceId` in `e2e/helpers/auth.ts` nimmt `items[0]` aus der
Workspace-Liste. Auf einer verschmutzten Entwicklerdatenbank ist das ein
Testrest. Siehe Abschnitt 7.

## 9. Tag & GitHub-Pre-Release

1. Release-PR auf `main` mergen.
2. Tag `v1.8.0-beta.17` auf den Release-Commit setzen.
3. GitHub-Pre-Release als **Pre-Release** markieren, nicht als `latest`.
4. Release-Notizen aus dem `CHANGELOG`-Block dieses Schnitts übernehmen.
