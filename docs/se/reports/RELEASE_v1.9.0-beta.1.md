---
type: STRATEGY
scope: release-v1-9-0-beta-1
status: draft
date: 2026-11-15
author_agent: se-migration
---
# Release-Bericht v1.9.0-beta.1

> **Status: interner Pre-Release-Cut. Keine Produktions-, Staging- oder
> QA-Freigabe.** Der Schnitt bündelt die Roadmap-Phasen ab `1.8.0-beta.29`
> (AI-Artifact-Summaries, Inspector M1–M8, bearbeitbare Dokumentansicht R1–R7,
> Verbindungsansicht als zwei Bäume, Allocation als Objekt + Release-Kaskade)
> und die Audit-Abarbeitung vom 2026-11-15. Er ist bewusst als Beta geführt:
> mehrere Residuen sind offen (Abschnitt 6), und die Verifikation stützt sich
> auf die **CI-Läufe der gemergten PRs** — **dieser Cut führt keinen eigenen
> Suite-Lauf durch** (Abschnitt 7).

## 1. Release-Ziel

`v1.9.0-beta.1` ist der erste Minor-Schnitt nach der Bugfix-Reihe
`1.8.0-beta.29`. Inhaltlich schließt er sieben Roadmap-Stränge ab (REST- und
MCP-Oberfläche, Inspector, Dokumentansicht, Verbindungsansicht, Allocation/
Release, Test-Case-Steps, Quality) und arbeitet den Code-Audit vom 2026-11-15
ab.

Der Schnitt trennt drei Dinge ausdrücklich:

- **Was enthalten ist:** alle in Abschnitt 3 gelisteten Feature-Bereiche, die
  Versions- und Doku-Carrier, und die Audit-Abarbeitung inklusive der
  neuen CI-Gates für Abhängigkeiten.
- **Was er nicht behauptet:** es gibt keinen neuen Suite-Lauf dieses Cuts und
  keine visuelle Abnahme der neuen Oberflächen im laufenden Stack
  (DoD-10-Sichtprüfung); beide Punkte stehen in Abschnitt 6.
- **Was sich sichtbar ändert:** die Verbindungsansicht öffnet jetzt im Modus
  `trees` — das ist die einzige bewusste Verhaltensänderung (Abschnitt 3.4).

## 2. Release-Cutoff und Basis

| Feld | Wert |
|---|---|
| Schnitt-Branch | `release/v1.9.0-beta.1` |
| Basis-Commit | `bad3bf93a997d11332895762e25b777240bda972` (`origin/main`, „Merge pull request #1869") |
| Vorgänger | `v1.8.0-beta.29` (Release-Merge #1753, `2026-11-09T08:48:58Z`) |
| Cutoff (exakt) | PRs **strikt nach** `2026-11-09T08:48:58Z` |
| Gemergte PRs seit Cutoff | **115** (122 Treffer ab 2026-11-09 minus die 7 PRs des Vorgänger-Release) |
| Cut-Datum | 2026-11-16 |

Der Kalendertag-Filter (`merged:>=2026-11-09`) liefert 122 PRs; davon gehören
`#1747`–`#1753` noch zum Vorgänger-Cut (Beta.29-Release selbst). Die
Cutoff-Regel aus Issue #726 (exakter Tag-Zeitstempel statt Kalendertag) wurde
angewendet, damit keine Beta.29-PRs doppelt im Changelog landen.

## 3. Enthaltene Feature-Bereiche

### 3.1 AI-Artifact-Summaries (Issues #1792, #1793)

#1833, #1834, #1835, #1836, #1837, #1838, #1839, #1840

- On-Demand-Zusammenfassung eines Artefakts samt sichtbarer Trace-Nachbarn
  (`GET /api/v1/artifacts/{id}/summary/`, MCP `artifact.summary`); jede
  Degradation ist ein geschlossener Enum und antwortet 200, nie Freitext.
- Gespeicherter Typ-Roster-Stand je `(workspace, artifact_type)` in
  `ArtifactSummary` (RLS), flag-gesteuerter Sweep, `stale`-Regel
  (`generated_at < now − 2 × interval`), REST-Lesepfade und die neue
  MCP-Gruppe `summary` (`summary.get`/`summary.refresh`, 47. Präfix).
- Eine Sprachauflösung (`application/ai_language.py`) für **alle** AI-Antworten
  statt per-Feature-Sprachschalter (#1838).
- Pro bezahltem Lauf genau ein Audit-Eintrag ohne Text und ohne Titel;
  Betriebsdoku `docs/AI-SUMMARIES-OPERATIONS.md` (§1793).

### 3.2 Inspector M1–M8 (Issue #1762)

#1822, #1827, #1828, #1829, #1818

- Ein tabbed Shell für alle Artefakttypen, typ-spezifische Tabs für
  Requirements, Architecture Elements und Goals, V6-Level-Filter.
- Die alte Sidebar ist entfernt (`#1829`) — der Inspector ist der einzige
  Detailpfad.
- Kommentar-Panel-Fix: das Panel bekommt die Artifact-UUID statt einer fremden
  Kennung (`#1763`/`#1818`).

### 3.3 Bearbeitbare Dokumentansicht R1–R7 (ADR-026, Nachtrag 2026-11-15)

#1843, #1846, #1854, #1855, #1856, #1857, #1859, #1861

| Schnitt | Inhalt |
|---|---|
| R1 (#1843) | `GET /api/v1/documents/{id}/view/` — Leseobjekt mit Kopf, Feldern und Kapiteln aus den Markdown-Überschriften, `ETag: "<version>"` nach der Konvention von `retrieve` |
| R2 (#1846) | eine Schreib-Urteilsquelle (`document_edit_policy.resolve_field_permissions`, Reihenfolge `PERMISSION` → `REPO_EXTERNAL` → `FIELD_FROZEN`), damit die UI nie einen Schreibvorgang anbietet, den der Dienst ablehnt |
| R3 (#1854) | transaktionales Bulk-Update `PATCH /api/v1/artifacts/bulk-update/` (max. 100 Einträge, alles oder nichts, Fehler per `index` benannt) und dasselbe als MCP-Tool `artifact.bulk_update` → **297 Tools** |
| R4 (#1855) | Lesemodus mit Inhaltsverzeichnis, nummerierten Kapiteln, Ankern aus dem Backend und Sperrhinweisen |
| R5/R6 (#1859) | Sofort-Speichern mit `If-Match` und 412 am Feld; Sammelmodus mit **einem** Request, Entwürfe bleiben bei 409 stehen |
| R7.1 (#1856) | `?format=markdown` — derselbe Lesestand wie die Oberfläche, ohne Bearbeitungsmarken, gleiche `ETag` und gleiche 403/404 |
| R7.2 (#1861, #1858) | Druckansicht ohne Shell-Chrome und Bedienelemente, Feature-Doku |

Anwenderreferenz: `docs/features/document-reading-view.md`. REQs: REQ-197…REQ-203.

### 3.4 Verbindungsansicht als zwei Bäume S0/G1–G3/V.0–V.5

#1844, #1845, #1847, #1848, #1849, #1850, #1851, #1852, #1853, #1854

- **Verhaltensänderung:** ohne `view`-Parameter öffnet `/connections` den Modus
  `trees` (Entscheidung D4/O5 = Option a, #1844/#1853). Der frühere Name
  `?view=tree` bleibt **permanenter Alias** auf `architecture`; gespeicherte
  Sichten und Lesezeichen funktionieren unverändert.
- Zwei Bäume in einem Scroll-Container (Requirements aus `parent_id` +
  `sort_key`, Architektur), gemessenes Kanten-Overlay mit genau einer Linie pro
  spaltenübergreifender Allokation, Zieltext zusätzlich als Text je Zeile,
  Checkbox-Auswahl überlebt Filterwechsel (#1852/#1853).
- `kind=requirement|element` und `sort_key` auf `allocation-view/` — zwei
  gezielte Reads statt eines gemeinsamen 500-Zeilen-Deckels (#1848);
  Element-Lesefehler werden sichtbar gemacht (#1849).
- Anzeigepräferenzen `ui.connection_view.show_edges` (Default `true`) und
  `ui.connection_view.filters_expanded` (Default `false`), geschrieben über den
  Keepalive-`PATCH` mit Last-Click-Wins-Queue (#1851/#1857).
- Gruppenverwaltung als Dialog, Zeilenaktion „Zu Gruppe hinzufügen…" und
  Drag auf Gruppenordner als Mitgliedschafts-Add (#1845/#1847/#1850).

Anwenderreferenz: `docs/features/connection-view-trees.md`. REQs: REQ-204…REQ-208.

### 3.5 Allocation als Objekt, Release-Kaskade, Test-Steps, Quality

#1794, #1795, #1796, #1797, #1798, #1799, #1800, #1801, #1802, #1803,
#1804, #1805, #1806, #1807, #1808, #1809

- Allocation als Objekt neben der Trace-Kante (ADR-028): konfigurierbare
  Kardinalität, Guard gegen den Rückweg `multiple → single` (409 bei
  bestehenden Mehrfachallokationen), `ALLOC-P1`-Auditregel, relative
  Tier-Namen mit Workspace-Overrides (#1794–#1799).
- Expliziter terminaler Zustand `released` mit `freeze_on_enter` in den
  Standard-/Extended-Requirement-Schemata und in `architecture_default`
  (Datenmigration `0026`, idempotent, keine Datenzeile verschoben); `minimal`
  bleibt ohne Release-Pfad (#1800).
- Release-Kaskade über REST mit Content-Freeze, Tier-Pin und
  Allocation-Spiegel, ab 5.000 Elementen asynchron; `REL-P1`-Audit für
  divergierende Live-/Release-Tier-Pins (#1801–#1805, #1819, #1820).
- Typisierte Given/When/Then-Steps über Modell, REST, MCP, Baselines und
  Migration plus Step-Editor (#1564/#1806–#1808).
- Ereignisgetriebenes Quality-Auto-Assessment hinter einem Flag, beratend und
  nicht blockierend (#1578/#1809).
- Document-Projection, Statusvergleich und Adoption über REST/MCP, CLI mit
  CI-Template und Document-Steward-Rolle (#1374/#1811–#1814).

### 3.6 Hermes-Plugin, Search, Clients

#1815, #1816, #1817, #1791, #1776, #1789, #1790

- Requirements-Ansichten im Desktop-Plugin inkl. API-/State-Layer und
  Hub-Eintrag (#1701).
- Optionale AI-Zusammenfassung über `artifact.search`-Ergebnissen (#18).
- stdlib-MCP-Probe für `/mcp/` und verifizierter OpenCode-1/2-Bericht
  (#1703).

### 3.7 Audit-Abarbeitung (Audit 2026-11-15) und Doku

#1860, #1862, #1863, #1864, #1865, #1866, #1867, #1868, #1869, #1832,
#1764–#1773

| PR | Inhalt | Ergebnis |
|---|---|---|
| #1860 | npm advisories | **15 → 0**; `minimatch`-Kette über verschachtelten Override geschlossen (Brücke, Abschnitt 6) |
| #1862 | Ruff `F841` | **59 → 0**, ohne `noqa`/`per-file-ignores`, zwei Assertions verschärft |
| #1863 | hartkodierte Farben | **74 → 43** Literale in **14 → 9** Dateien, 4 neue Layer-1-Alpha-Tokens |
| #1866 | toter ASIL-Code | 18 weitere Literale weg → **25 in 8 Dateien** |
| #1864 | `ChangeRequest.artifact_id` im DTO | geschlossen; `baseline_id` bleibt offen (Abschnitt 6) |
| #1865 | Dependency-Gate | ein CI-Job für `npm audit --audit-level=high` + `pip-audit --strict`, Baseline 145/676 Pakete, 0 Findings |
| #1868 | Woodpecker | `.woodpecker.yml` entfernt, GitHub Actions ist die einzige Pipeline |
| #1867 | Audit-Nachtrag | Abarbeitungsstand je Befund mit Beleg |
| #1869 | Doku-Refresh | README, ARCHITECTURE, CODEBASE_OVERVIEW, MCP-SURFACE, clients |
| #1764–#1773 | Frontend-Refactoring | 14 Hotspot-Komponenten in 10 Iterationen nach Verantwortlichkeit getrennt (#598 S2) |

## 4. Versions-Carrier

Alle Carrier über `scripts/bump_version.py --version 1.9.0-beta.1` gesetzt
(strukturell per JSON-Pointer bzw. Compose-Default-Regex, nicht per
String-Ersetzung). Alter Stand überall `1.8.0-beta.29`.

| Datei | Stellen | alt → neu |
|---|---|---|
| `VERSION` | 1 | `1.8.0-beta.29` → `1.9.0-beta.1` |
| `frontend/package.json` | 1 | dito |
| `frontend/package-lock.json` | 2 (Root + `packages[""]`) | dito |
| `.env.example` | 2 (Kommentarzeile + `REQOGNILOOM_VERSION`) | dito |
| `deploy/docker-compose.yml` | 6 (`${REQOGNILOOM_VERSION:-…}`) | dito |
| `deploy/docker-compose.minimal.yml` | 3 | dito |
| `server.json` | 1 | dito |
| `.claude-plugin/marketplace.json` | 2 | dito |
| `dist/npm/reqogniloom-opencode/package.json` | 1 | dito |
| `dist/plugins/claude-code/reqogniloom/.claude-plugin/plugin.json` | 1 | dito |
| `dist/plugins/antigravity/reqogniloom/plugin.json` | 1 | dito |
| `integrations/hermes-plugin/reqogniloom/package.json` | 1 | dito |
| `integrations/hermes-plugin/reqogniloom/package-lock.json` | 2 | dito |
| `integrations/hermes-plugin/reqogniloom/hermes-plugin.json` | 1 | dito |
| `site/index.html` | 2 (Hero-Badge + Footer) | dito |
| `docs/CODEBASE_OVERVIEW.md` | 1 (Stand-Zeile) | dito |
| `docs/api/MCP-SURFACE.md` | 2 (Version + „Measured at") | dito |
| `docs/clients/hermes.md`, `hermes.de.md` | je 1 (generiert via `render.py`) | dito |

**Gesamt:** 19 Dateien, 32 Ersetzungen, 13 version-gekoppelte JSON-Pointer.

### 4.1 Bewusst NICHT angefasst

| Stelle | Grund |
|---|---|
| `CHANGELOG.md:10` (`## [1.8.0-beta.29]`) | historischer Abschnitt |
| `deploy/README.md:458` („Ab `1.8.0-beta.29` gibt es drei Wege …") | historische Aussage über ein eingeführtes Feature |
| `docs/clients/opencode-endpoint-verification.md:4` | Probe-Bericht, datiert auf einen alten Image-Tag |
| `docs/ARCHITECTURE.md:8` („`VERSION` 1.8.0-beta.29") | Datenquellen-Note des vermessenen Checkouts, kein Carrier |
| `.github/ISSUE_TEMPLATE/reqogniloom-defect.yml:46` | Platzhalter-Beispiel im Issue-Formular |
| `docs/se/reports/*`, `docs/plans/*` | historische Berichte/Pläne |

### 4.2 Geprüfte, aber nicht existente Stellen

`deploy/.env.example`, `deploy/docker-compose.override.yml` und
`deploy/docker-compose.tls.example.yml` führen keinen
`REQOGNILOOM_VERSION`-Fallback (das TLS-Overlay sagt das in Zeile 18
ausdrücklich zu). Die Env-Vorlage liegt als `.env.example` im Repo-Root und ist
in Abschnitt 4 enthalten.

## 5. Changelog

`CHANGELOG.md` erhält einen Block `## [1.9.0-beta.1] — 2026-11-16` direkt unter
`## [Unreleased]`, Keep-a-Changelog, Englisch, mit `### Added` / `### Changed`
/ `### Fixed` / `### Removed` und PR-Nummern je Zeile. Die einzige
**Breaking**-Markierung ist der Default-Modus-Wechsel der Verbindungsansicht;
der Alias `view=tree` bleibt gültig.

## 6. Offene Punkte / was dieser Cut nicht enthält

| Punkt | Status | Herkunft |
|---|---|---|
| **DoD-10-Sichtprüfung** der neuen Oberflächen (1440/1024/768/320 px) | **offen** — braucht einen laufenden Stack; keine visuelle Abnahme von Inspector, Dokumentansicht und Bäumen in diesem Cut | Audit §3 Nr. 1, §8.1 |
| **`ChangeRequestDTO.baseline_id`** fehlt weiterhin im REST-/MCP-Payload | **offen** — in #1864 bewusst nicht mitgelöst (andere Parity-Lücke als `artifact_id`) | Audit §8.1 |
| **`minimatch`-Override** (`@typescript-eslint/typescript-estree → minimatch ^11.0.8`) | **Brücke** — fällt erst, wenn `@typescript-eslint` ≥ 8.72.3 stabil `minimatch@^11` pinnt | #1860, Audit §8.1 |
| **`.woodpecker.yml`** entfernt | **erledigt, aber Settings-Nachlauf:** Pipeline existiert nicht mehr; GitHub Actions ist alleinige Pipeline | #1868 |
| **#1865 als Required Check** in den Repo-Settings | **offen** — ohne Eintrag blockiert der neue Dependency-Job keinen Merge | #1865 |
| Inspector-UX bei 1280 px (Sheet legt das Formular `inert`) | offen, nicht blockierend | Audit §3 Nr. 2 |
| V6-Level-Filter in der UI, einheitliche Fehler-/Leerzustände (V1), Gherkin-Parser im TestRun (V8) | offen, Folge-Slices | Audit §3 Nr. 4–6 |
| `pip-audit` lokal nicht verfügbar | durch den CI-Job #1865 abgedeckt, nicht lokal reproduziert | Audit §1 |

## 7. Verifikation

> **Herkunft der Nachweise.** Dieser Cut führt **keinen eigenen Suite-Lauf**
> durch. Er ändert — außer Versions-Carriern, `CHANGELOG.md`, zwei
> Report-Dateien und den bereits vorher uncommitteten REQ-197…REQ-208 — keinen
> Code. Maßgeblich sind die CI-Läufe der gemergten PRs auf `main`
> (`bad3bf93`); alle in Abschnitt 3 genannten PRs wurden mit grüner CI gemergt.

| Gate | Befehl | Ergebnis |
|---|---|---|
| Carrier-Ratchet | `python3 scripts/check_plugin_packages.py --expect-version 1.9.0-beta.1` | **OK** — 12 Sources, 13 Version-Locations, 2 unabhängige POC-Manifeste konsistent |
| Client-Artefakte | `python3 scripts/clients/render.py --check` | **OK** — 18 Client-/Store-Artefakte aktuell |
| MCP-Manifest-Drift | `docs/agent-templates/test_meta_tool_count_drift.py` (pytest) | **15 passed** (beide Drift-Tests zusammen) |
| Doc-Surface-Konsistenz | `docs/agent-templates/test_doc_surface_consistency.py` (pytest) | **passed** |
| Voller Release-Bump | `python3 scripts/bump_version.py --version 1.9.0-beta.1` | **exit 0** — Carrier gesetzt, Clients neu gerendert, beide Gates grün |

**`scripts/check-version-drift.sh` ist kein Carrier-Gate.** Das Skript
vergleicht den `commit_short` einer **deployten** Umgebung gegen
`origin/main` und verlangt `DEPLOYED_VERSION_URL`; ohne URL endet es mit
`exit 2` („DEPLOYED_VERSION_URL not provided"). Es läuft als geplanter
Monitor (`.github/workflows/version-drift-check.yml`, täglich 09:00 UTC) und
ist kein Merge-Gate. Der Carrier-Drift-Gate dieses Schnitts ist das Paar
`check_plugin_packages.py` + `clients/render.py --check` aus
`.github/workflows/client-artifacts-check.yml` und `ci.yml` — beide grün.

Tool-Oberfläche nach diesem Cut: **297 Tools in 47 Gruppen** (kanonisch:
`docs/agent-templates/tool-manifest.json`, `tool_count: 297`); die neuen
Einträge sind `artifact.summary`, `summary.get`, `summary.refresh` und
`artifact.bulk_update`.

Testumfang des Checkouts (Dateizahlen, keine Läufe):
**1018** Backend-Testdateien, **387** Frontend-Testdateien, **70** E2E-Specs
(4 CI-Shards), **27** Django-Apps.

## 8. Risiken und Residuen

- **Verhaltensänderung ohne Migrationsschritt.** Der Default-Wechsel auf
  `trees` ist der einzige sichtbare Bruch. Er ist durch den permanenten Alias
  `view=tree` abgefedert; Nutzer, die einen Modus explizit gespeichert haben,
  sehen keinen Unterschied. Risiko bleibt die Erwartung „Architektur ist der
  Startbildschirm" bei Doku/Schulungsmaterial außerhalb des Repos.
- **Kein visueller Nachweis.** Drei der vier großen UI-Bereiche (Inspector,
  Dokumentansicht, Bäume) sind durch Unit-/Komponenten-/E2E-Tests gedeckt, aber
  nicht in diesem Cut über vier Breiten visuell abgenommen (Abschnitt 6).
- **Zwei Datenmigrationen mit Verhaltenswirkung.** `0142` entfernt die
  DB-Constraint `uniq_tracelink_allocated_to_source` (die Regel ist jetzt eine
  Workspace-Einstellung, durchgesetzt in der Service-Schicht); `0026` ergänzt
  den Zustand `released` in bestehenden Workflow-Definitionen. Beide sind
  idempotent und verschieben keine Datenzeile — ein Rollback der Migration
  lässt den Zustand/die Constraint aber nicht automatisch zurückkehren.
- **Zwei Brücken mit Ablaufdatum.** Der `minimatch`-Override und der
  `@typescript-eslint`-Pin sind bewusst temporär; ohne Follow-up bleibt eine
  verschachtelte Override-Kette im Frontend-Build.
- **Gate ohne Durchsetzung.** #1865 ist gemergt, aber nicht als Required Check
  eingetragen — der Job kann rot sein, ohne einen Merge zu blockieren.
- **Beta-Charakter.** `0.y.z`-Semantik: innerhalb von `1.9.0-beta.x` kann sich
  alles ändern; dieser Cut ist kein Stabilitätsversprechen.

## 9. Nächste Schritte (nicht Teil dieses Commits)

1. Review dieses Branches, dann Release-PR gegen `main`.
2. Tag `v1.9.0-beta.1` auf den Release-Commit (Aufgabe des `git`-Agenten; kein
   Re-Tag nach dem Push).
3. Image-Build via `scripts/build.sh` (setzt `APP_VERSION`, `GIT_COMMIT_SHA`,
   `BUILD_TIME`), Publish via `docker-publish.yml`.
4. GitHub-**Pre-Release** markieren, nicht `latest`.
5. Release-Notizen aus dem `CHANGELOG`-Block übernehmen.

---

*Erstellt durch den `release`-Agenten am 2026-11-16. Interne Doku (Deutsch),
keine Secrets. Alle Zahlen sind auf die genannten PRs, Gate-Läufe oder
Audit-Abschnitte zurückführbar; es gibt keinen erfundenen Messwert und keinen
Suite-Lauf dieses Cuts. Kein Commit/Push durch den Autor.*
