# Release-Bericht v1.9.0-beta.2

> **Status: interner Bugfix-Beta-Cut. Keine Produktions-, Staging- oder
> QA-Freigabe.** Der Schnitt schließt zwei Pläne ab (Tabellenansicht S1–S5,
> MCP-Modernisierung Phase A–E) und arbeitet die Bugfix-Rückmeldungen zur
> Beta ein. Die Verifikation stützt sich auf die **CI-Läufe der gemergten PRs**
> — **dieser Cut führt keinen eigenen Suite-Lauf durch** (Abschnitt 7).

## 1. Release-Ziel

`v1.9.0-beta.2` ist ein **Bugfix-Beta** auf `main` (`2c287d50`) direkt nach
`v1.9.0-beta.1` (`f1e9c8f3`). Inhaltlich:

1. **Tabellenansicht komplett** — Bulk-Transition, gespeicherte Sichten,
   per-User-Tabellenzustand, `ArtifactTable` mit Toggle und der serverseitige
   Read-Pfad `GET /api/v1/artifacts/table/` inklusive Filter-DSL und
   E2E-Guardrail.
2. **MCP-Modernisierung abgeschlossen** — Protokollverhandlung, Session-Header,
   SSE auf POST, `resources/*` und `prompts/*`, Tool-Gruppen-Curation auf
   API-Keys, Abschlussdoku.
3. **Vier Bugfix-Cluster aus der Beta-Rückmeldung** — Memory-Purge,
   `projection-status`, Issue-Workflow-Vokabular, Allocation-Coverage-Vertrag.

Der Cut behauptet **nicht**: einen neuen Suite-Lauf, eine visuelle Abnahme der
Tabellenansicht über vier Breiten, oder dass die in Abschnitt 6 genannten
Residuen geschlossen sind.

## 2. Release-Cutoff und Basis

| Feld | Wert |
|---|---|
| Schnitt-Branch | `release/v1.9.0-beta.2` |
| Basis-Commit | `2c287d50` (`origin/main`, „Merge pull request #1886") |
| Vorgänger | `v1.9.0-beta.1` (`f1e9c8f3`) |
| Cutoff (exakt) | PRs **strikt nach** dem Vorgänger-Tag, ermittelt über `git log --merges --oneline v1.9.0-beta.1..origin/main` |
| Gemergte PRs seit Cutoff | **11** |
| Cut-Datum | 2026-11-16 |

## 3. Enthaltene PRs

### 3.1 Tabellenansicht komplett (S2–S5)

#1872, #1874, #1876, #1877

| PR | Inhalt |
|---|---|
| #1872 | Slice 2: `PATCH /api/v1/artifacts/bulk-transition/` — eine Batch durch den Workflow statt durch den Feld-Schreibpfad; gleiche Alles-oder-nichts-Transaktion, gleiche 100er-Grenze, gleiche Fehlerliste mit `index`/`code`/`message`; Guards, Gates und Versionsprüfungen bleiben in den Transition-Services. MCP-Pendant `artifact.bulk_transition`. Katalog 297 → 298 |
| #1874 | Slice 3: gespeicherte Sichten (`saved-views/`, `saved-views/<id>/`, `saved-views/<id>/apply/`) und der eigene Tabellenzustand je Nutzer (`users/me/table-view-state/`), Migrationen `0151`/`0152` inkl. RLS; MCP nur lesend (`saved_view.list`, `saved_view.apply`) |
| #1876 | Slice 4: `ArtifactTable` — virtualisiertes Grid aus einem Spaltenmodell je Typ, Filter-Popover plus Chips, Spaltenauswahl mit persistiertem Zustand, Leiste für gespeicherte Sichten, eine Bulk-Leiste mit **genau einem** Request; Inline-Edit erbt die Konfliktbehandlung des Dokument-Editors (412/409 markiert das Feld, Entwurf bleibt) |
| #1877 | Slice 1 + 5: `GET /api/v1/artifacts/table/` (eingefrorene Zeilenform, eine Filter-DSL mit typisierten Operatoren je Feldart, gebatchte Status-/Freeze-Lookups, Seitengröße ≤ 100, `id`-Tiebreak je Sortierung); gespeicherte Sichten laufen durch denselben Service; Playwright-Spec als Guardrail, die sich mit Begründung selbst überspringt, solange der Endpoint nicht deployt ist |

**Katalog nach diesem Bereich: 301 Tools in 49 Präfixen** (neu:
`saved_view`, `tool`, dazu `artifact.bulk_transition`). Kanonisch:
`docs/agent-templates/tool-manifest.json`, `tool_count: 301`.

### 3.2 MCP-Modernisierung (Phase A–E)

#1871, #1873, #1875, #1878

| PR | Inhalt |
|---|---|
| #1871 | Phase A: Protokollverhandlung (`2025-06-18` als jüngste Revision, `2025-03-26` und `2024-11-05` werden weiter ausgehandelt), `Mcp-Session-Id` nach erfolgreichem `initialize` über den bestehenden Redis-Binding-Store (TTL + Verschlüsselung, kein zweiter Session-Store), `DELETE /mcp/` beendet die Session, SSE-Antwort auf `Accept: text/event-stream` bei POST, ungültiger `MCP-Protocol-Version`-Header → `400 INVALID_REQUEST` vor dem Dispatcher |
| #1873 | Phase B: `resources/list`, `resources/templates/list`, `resources/read` (Artefakte als `reqogniloom://artifact/{id}` Markdown, Mitgliedschaftsprüfung inklusive) und `prompts/list`, `prompts/get` (Workspace-Prompt-Templates) — beide über die bestehende Tool-Registry, damit Auth, Tenant-Isolation, RBAC und Presets ein Pfad bleiben; nichts davon erscheint in `tools/list` |
| #1875 | Phase D: `ApiKey.tool_groups` (Migration `0035`) kuratiert `tools/list`; `scope` bleibt das durchgesetzte Gate. Neues, immer sichtbares Introspektions-Tool `tool.list_groups` (neues Präfix `tool`) |
| #1878 | Phase E: Abschlussdoku — `docs/api/MCP-SURFACE.md` trennt, was `scope` erzwingt und was `tool_groups` nur kuratiert; Plan-Tasks 1–15 abgehakt |

### 3.3 Bugfixes aus der Beta-Rückmeldung

#1884, #1885, #1886

| PR | Inhalt |
|---|---|
| #1884 | Memory-Purge: `entry_id` auf dem Workspace-Delete-Pfad wird nicht mehr still akzeptiert und ignoriert (das löschte den ganzen Scope statt eines Eintrags) — jetzt `400` mit Verweis auf die Einzeleintrag-Route; `change_reason` bleibt der einzige unterstützte Parameter und ist im Schema deklariert. `projection-status` validiert den Body vorab: leerer Body → `400` mit Feldname statt `500` aus einem unbehandelten `ValueError` |
| #1885 | Issue-Workflow einheitlich lowercase (`open`, `in_progress`, `resolved`, `closed`, `wontfix`), Labels bleiben Anzeige; **Datenmigration `workflow/0027`** schreibt bestehende Zeilen und beide Workflow-Definition-Stores idempotent und reversibel um — nur für Issue. Audit-Findings tragen jetzt `standard_ref` und Titel aus dem Regel-Katalog (zur Lesezeit aufgelöst); `ALLOC-P1` hat endlich eine Referenz |
| #1886 | `allocation-coverage` publiziert ein echtes Read-only-Schema (`allocated_count`, `not_allocatable_count`, `coverage_percent`, Liste der nicht allokierten Requirements) statt `ArchitectureElement` als 200-Antwort; `coverage_ratio` (Anteil, `1 von 51` las sich als `1.96`) → `coverage_percent` (`0..100`) |

## 4. Versions-Carrier

Alle Carrier über `python3 scripts/bump_version.py --version 1.9.0-beta.2`
gesetzt (strukturell per JSON-Pointer bzw. Compose-Default-Regex, nicht per
String-Ersetzung), danach `render.py` für die Client-Artefakte.
Alter Stand überall `1.9.0-beta.1`.

| Datei | Stellen |
|---|---|
| `VERSION` | 1 |
| `frontend/package.json` / `frontend/package-lock.json` | 1 / 2 |
| `.env.example` | 2 |
| `deploy/docker-compose.yml` / `deploy/docker-compose.minimal.yml` | 6 / 3 |
| `server.json` | 1 |
| `.claude-plugin/marketplace.json` | 2 |
| `dist/npm/reqogniloom-opencode/package.json` | 1 |
| `dist/plugins/claude-code/…/plugin.json` | 1 |
| `dist/plugins/antigravity/…/plugin.json` | 1 |
| `integrations/hermes-plugin/reqogniloom/package.json` / `package-lock.json` / `hermes-plugin.json` | 1 / 2 / 1 |
| `site/index.html` | 2 |
| `docs/CODEBASE_OVERVIEW.md` | 5 (Stand-Zeilen + Tool-Zahlen) |
| `docs/api/MCP-SURFACE.md` | 2 |
| `systemagents/reqogniloom-operator.md` | 2 |
| `docs/clients/hermes.md`, `hermes.de.md` | je 1 (generiert) |
| `.meta-config/project.yaml` | 2 (manuell: zwei `Stand VERSION`-Zeilen) |

**Gesamt:** 21 Dateien, 40 geänderte Zeilen. Der Carrier-Ratchet
(`check_plugin_packages.py --expect-version 1.9.0-beta.2`) meldet
12 Sources / 13 Version-Locations / 2 unabhängige POC-Manifeste konsistent;
`clients/render.py --check` meldet 18 Artefakte aktuell.

Verbleibender `1.9.0-beta.1`-Treffer im Carrier-Set:
`.meta-config/project.yaml:419` nennt `RELEASE_v1.9.0-beta.1.md` als
Vorgänger-Report — historische Referenz, kein Carrier.

## 5. Changelog

`CHANGELOG.md` erhält einen Block `## [1.9.0-beta.2] — 2026-11-16` direkt unter
`## [Unreleased]` (Englisch, Keep a Changelog) mit `### Added` (7 Zeilen),
`### Changed` (6 Zeilen) und `### Fixed` (6 Zeilen), jede Zeile mit
PR-Nummern. Drei **Breaking**-Markierungen:

| Breaking | vorher → nachher |
|---|---|
| Feldname Allocation-Coverage | `coverage_ratio` (Anteil) → `coverage_percent` (`0..100`) |
| Issue-Workflow-Zustände | `"In Progress"` u. a. → `in_progress` u. a. (lowercase) |
| MCP-Protokoll-Revision | hartkodiert `2024-11-05` → verhandelt, jüngste `2025-06-18` (ältere Revisionen werden weiter ausgehandelt) |

## 6. Upgrade-Hinweise und offene Punkte

### 6.1 Automatisch laufend

Die **Datenmigration `workflow/0027`** (`0027_issue_state_vocabulary_lowercase`)
läuft beim `migrate`-Schritt des Stacks und schreibt Issue-Zeilen sowie beide
Workflow-Definition-Stores von Titel- auf Kleinschreibung um. Sie ist
idempotent, reversibel und fasst **nur** Issue an — andere Item-Typen bleiben
unberührt. Ein Rollback der Migration stellt die Kleinform nicht automatisch
zurück; die Migration ist vorwärts gedacht.

### 6.2 Umbennungen (siehe Breaking)

- `coverage_ratio` → `coverage_percent` (Semantik wechselt von Anteil auf
  Prozent). Clients, die den alten Namen lesen, bekommen ein Feld weniger.
- Issue-Zustände lowercase; Anzeige-Labels bleiben deutsch/englisch lesbar.
  Ein Client, der `"In Progress"` **sendet**, erhält jetzt einen `400`, der den
  gültigen Zustand nennt.
- MCP: jüngste Revision `2025-06-18`. `2025-03-26` und `2024-11-05` werden
  weiter ausgehandelt; nur ein Client mit fest verdrahteter Revision sieht eine
  andere Antwort. Browser-Clients sehen den `Mcp-Session-Id`-Header nur, wenn
  ihn jemand freigibt (offener Punkt 6.3).

### 6.3 Ausdrücklich nicht enthalten

| Punkt | Status |
|---|---|
| **#1247** `memory.ask` gegen Honcho | offen — Upstream-Fähigkeit fehlt; der Pfad bleibt auf pgvector beschränkt |
| **#1230** externe Konten / Identity-Föderation | offen, außerhalb dieses Cuts |
| **CORS exponiert `Mcp-Session-Id` nicht** | offen — `CORS_EXPOSE_HEADERS` ist weiterhin `["ETag"]`; Browser-Clients können den Session-Header nicht lesen, nicht-Browser-Clients (CLI/Server) sind nicht betroffen |
| **`transitions/`-Endpunkt** liefert Kanten ohne Rollen-/Gate-Filter | offen — die Liste zeigt Zustandsübergänge unabhängig davon, ob der Aufrufer sie ausführen darf; die Ausführung selbst bleibt serverseitig geprüft |
| **`ChangeRequestDTO.baseline_id`-Parität** | offen — aus #1864 bewusst nicht mitgelöst |
| DoD-10-Sichtprüfung der Tabellenansicht (1440/1024/768/320 px) | offen — braucht einen laufenden Stack |

## 7. Verifikation

> **Herkunft der Nachweise.** Dieser Cut führt **keinen eigenen Suite-Lauf**
> durch. Er ändert — außer Versions-Carriern, `CHANGELOG.md`, den zwei
> Report-Dateien und zwei `Stand VERSION`-Zeilen in `.meta-config/project.yaml`
> — keinen Code. Maßgeblich sind die CI-Läufe der 11 gemergten PRs auf `main`
> (`2c287d50`); alle wurden mit grüner CI gemergt.

| Gate | Befehl | Ergebnis |
|---|---|---|
| Carrier-Ratchet | `python3 scripts/check_plugin_packages.py --expect-version 1.9.0-beta.2` | **OK** — 12 Sources, 13 Version-Locations, 2 POC-Manifeste |
| Client-Artefakte | `python3 scripts/clients/render.py --check` | **OK** — 18 Artefakte aktuell |
| Doc-Surface + Manifest-Drift | `python3 -m pytest docs/agent-templates/test_doc_surface_consistency.py docs/agent-templates/test_meta_tool_count_drift.py -q` | **15 passed** |
| Voller Bump | `python3 scripts/bump_version.py --version 1.9.0-beta.2` | **exit 0** — Carrier gesetzt, Clients gerendert, beide Gates grün |
| MCP-Manifest | `docs/agent-templates/tool-manifest.json` | `tool_count: 301`, 49 Präfixe (gemessen) |

`scripts/check-version-drift.sh` ist **kein** Carrier-Gate: es vergleicht den
`commit_short` einer deployten Umgebung gegen `origin/main` und verlangt
`DEPLOYED_VERSION_URL` (ohne URL `exit 2`); es läuft als täglicher Monitor.

## 8. Risiken und Residuen

- **Drei Breaking-Änderungen in einem Bugfix-Beta.** `coverage_ratio` und die
  Issue-Zustände sind Feld-/Wert-Umbennungen mit Datenmigration; sie sind
  bewusst klein gehalten, aber nicht rückwärtskompatibel. `0.y.z`-Semantik:
  innerhalb von `1.9.0-beta.x` kann sich alles ändern.
- **Migration `0027` ist einseitig gedacht.** Sie ist idempotent und fasst nur
  Issue an; ein Rollback bringt die Titel-Schreibweise nicht automatisch zurück.
- **Tabellenansicht ohne visuelle Abnahme.** Unit-, Komponenten- und E2E-Tests
  decken die Flows, aber es gibt keine Sichtprüfung über vier Breiten in diesem
  Cut. Der E2E-Guardrail überspringt sich mit Begründung, wenn der Endpoint
  nicht deployt ist — er kann also nicht „hohl" grün werden, aber er beweist
  in einer Umgebung ohne Endpoint auch nichts.
- **`tool_groups` kuratiert, `scope` erzwingt.** Ein per `tool_groups`
  ausgeblendetes Tool bleibt aufrufbar, wenn Rolle und `scope` es erlauben;
  das ist Absicht und in `MCP-SURFACE.md` dokumentiert, überrascht aber
  Erwartungen an „Sichtbarkeit = Durchsetzung".
- **Kein Image-Nachweis.** Ohne `scripts/build.sh` + `docker-publish.yml` gibt
  es für diesen Cut keinen Image-/Digest-Beleg.

## 9. Nächste Schritte (nicht Teil dieses Commits)

1. Review dieses Branches, dann Release-PR gegen `main`.
2. Tag `v1.9.0-beta.2` auf den Release-Commit (Aufgabe des `git`-Agenten;
   kein Re-Tag nach dem Push).
3. Build via `scripts/build.sh`, Publish via `docker-publish.yml`.
4. GitHub-**Pre-Release** markieren, nicht `latest`.
5. Release-Notizen aus dem `CHANGELOG`-Block übernehmen.

---

*Erstellt durch den `release`-Agenten am 2026-11-16. Interne Doku (Deutsch),
keine Secrets. Alle Zahlen sind auf die genannten PRs, Gate-Läufe oder das
Manifest zurückführbar; es gibt keinen erfundenen Messwert und keinen
Suite-Lauf dieses Cuts. Kein Commit/Push/Tag durch den Autor.*
