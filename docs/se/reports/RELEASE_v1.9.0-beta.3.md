---
type: STRATEGY
scope: release-v1-9-0-beta-3
status: draft
date: 2026-11-19
author_agent: release
---
# Release-Bericht v1.9.0-beta.3

> **Status: interner UI-Beta-Cut. Keine Produktions-, Staging- oder
> QA-Freigabe.** Der Schnitt schließt PR #1943 (Trace-Spine-Footer,
> Baumbreite, Impact-Drawer) ab. Die Verifikation stützt sich auf die
> Nachweise der gemergten PR — **dieser Cut führt keinen eigenen Suite-Lauf
> durch** (Abschnitt 7).

## 1. Release-Ziel

`v1.9.0-beta.3` ist ein **UI-Beta** auf `main` (`0972db01`) direkt nach
`v1.9.0-beta.2`. Inhaltlich vier Schnitte aus dem freigegebenen Plan
`docs/plans/2026-11-19-trace-spine-footer-plan.md` (Revision 2, `status:
approved`, Review-Iteration 4):

1. **Horizontaler Trace-Spine-Footer** über die volle Inhaltsbreite
   (außer Navigation) mit **zwei unabhängigen User-Toggles** für Footer und
   Inspector; aktive Station bleibt beim Einklappen sichtbar.
2. **Baumbreite pro Modul** mit Drag und gespeicherter Breite gemäß
   **ADR-030** (`status: accepted`) — Wiederherstellung von REQ-L1-084 und
   REQ-L3-RF009-001 ohne Reaktivierung des gelöschten Legacy-Vertrags.
3. **On-Demand-Impact-Drawer** auf `/traceability` statt der dauerhaft
   leeren Impact-Spalte und der Full-Page-Navigation.
4. **Mobile Sheet-Koordination** und A11Y-Korrekturen (axe-Sweeps,
   Trefferflächen, Reflow).

Der Cut behauptet **nicht**: einen neuen Suite-Lauf, eine visuelle Abnahme
auf echten Geräten, eine manuelle Screenreader-Abnahme oder dass die in
Abschnitt 8 genannten Residuen geschlossen sind.

## 2. Release-Cutoff und Basis

| Feld | Wert |
|---|---|
| Schnitt-Branch | `release/v1.9.0-beta.3` |
| Basis-Commit | `0972db01` („Merge pull request #1943 from Popoboxxo/docs/trace-spine-footer-plan") |
| Vorgänger | `v1.9.0-beta.2` |
| Cutoff (exakt) | PR #1943, gemergt in `0972db01` |
| Cut-Datum | 2026-11-19 |

## 3. Enthaltene Schnitte (PR #1943)

Die vier Schnitte liefen als 12 dispatchbare Tasks je Gate → Review → CI →
Merge. Kein Eingriff in den Django-Domain-Layer; kein neues Datenmodell,
keine neue Tabelle, kein neues MCP-Tool (der Tool-Katalog bleibt **301 Tools
in 49 Präfixen**, `docs/agent-templates/tool-manifest.json`).

### 3.1 Schnitt 1 — zwei unabhängige Anzeige-Präferenzen

Zwei Q1-Keys (`ui.trace_footer.enabled`, `ui.inspector.enabled`, Default
`true`, `workspace_id=None`, nur User-Scope) mit den HTTP-Feldern
`trace_footer_enabled` / `inspector_enabled`, zwei unabhängige Hooks und
zwei Switches in `UserProfileSettings` (nicht im WorkspaceSettings-
Appearance-Tab). `openapi_contract_snapshot.json` bleibt unverändert (pinnt
keine Felder); `backend/mcp_server` bleibt ohne dediziertes
Display-Preference-Tool — das Manifest-Drift-Gate bleibt unberührt.

### 3.2 Schnitt 2 — horizontaler Footer

`useDerivationChain` zieht in die neue Komponente `TraceSpineFooter`, damit
die Chain-RPC **nur bei gemountetem Footer** feuern. Der Footer ist
Geschwister des `<SplitView>` (nicht im `spine`-Slot), spannt
`Inhaltsbreite − 220 px`, ≤4 Stationen in einer Zeile, ≥5 eingeklappt mit
`[+N weitere]` und immer sichtbarer aktiver Station (`aria-current="step"`).
Der Stations-Panel wird zum Popover (`role="dialog"`, ESC, Fokus-Rückgabe);
`isOpenable=false` (unresolved / in-flight / Fehler) deaktiviert die Chip.
Alle 8 Hosts migriert. Die drei konkurrierenden Breakpoint-Mechanismen
werden auf eine Quelle reduziert; `--bp-lg` bleibt inspector-exklusiv,
`breakpoint-token-gate.test.ts` wird **nicht** gelockert. Bei beiden
Toggles an zeigen Footer und Inspector Links (Status quo seit M8, kein
neues Unterdrückungslogik).

### 3.3 Schnitt 3 — Baumbreite (ADR-030)

Neuer optionaler Prop `moduleType`, `useTreeWidth()` pro Modul, neuer
gerätelokaler Key `reqflow.splitview.treeWidth.v2.<moduleType>` (der gelöschte
`reqflow_splitview_*` wird weder gelesen noch geschrieben). Divider
`role="separator"` mit `aria-valuenow/min/max`, `tabindex="0"`, 24 px
Trefferfläche, Pfeile ±16 px / Shift ±64 px, `Home`/`End`,
`Enter`/Doppelklick = Modul-Default, `prefers-reduced-motion` beachtet; in
`zone === 'mobile'` inert. Nach dem ersten Drag ist `treeWidth` (px)
autoritativ, `ratio` nur Initialwert, `minWidths` Clamp (380 px …
`effMax = min(70 % × contentWidth, contentWidth − minWidths[1] −
dividerWidth)`, zur Laufzeit gemessen, kein neues `@media`). Keine
Cross-Device-Synchronisation (bewusst deferred).

**ADR-030** liegt als `docs/se/ADR/ADR-030_tree_width_drag_reversal.md` im
Status `accepted` (MADR-Minimal vollständig, `affected_reqs`:
REQ-L1-084, REQ-L3-RF009-001, REQ-L2-RF-209; Critic-Gate ohne Finding
„unbegründete Entscheidungsumkehr"). Der UI-001-Hygiene-Entscheid bleibt
erhalten: ein Vertrag, eine Hook-Instanz, kein `spineIsHorizontal` /
`NARROW_RATIO`, Footer als Geschwister.

### 3.4 Schnitt 4 — Drawer, Mobile, Politur

`ImpactDetailPanel` wird in den On-Demand-Drawer auf `/traceability`
überführt; `window.location.assign("/impact")` hat 0 Treffer, Preset
bleibt erhalten, kein `|| true`. Mobil öffnen Footer-Sheet (z 1200) und
Inspector-Sheet (z 1300) einander gegenseitig ausschließlich expandiert;
**eine** Back-Taste schließt das oberste Sheet, Fokus wandert in das
geöffnete Sheet, `aria-modal` nur dort, die kollabierte Footer-Leiste bleibt
Tap-Target. Ratchets und ~14 Visual-Baselines wurden mit benanntem Owner
(`e2e-tester`) aktualisiert — **keine bestehende Baseline angehoben**.

### 3.5 Commits des PR

| Commit | Inhalt |
|---|---|
| `ea4477ca` | `feat(ui): move trace chain into horizontal footer` |
| `1594c709` | `docs: accept ADR-030 for per-module tree width` |
| `7ded6ec7` | `feat(ui): add per-module draggable tree width` |
| `f380608c` | `feat(ui): add on-demand impact drawer and mobile sheets` |
| `35262500` | `fix(ui): repair CI gates after trace footer rollout` |
| `20ab923a` | `fix(e2e): stabilize axe sweeps after footer rollout` |
| `c06fa3c8` | `fix(e2e): keep mobile viewport after reflow check` |

## 4. Versions-Carrier

Alle Carrier über `python3 scripts/bump_version.py --version 1.9.0-beta.3`
gesetzt (strukturell per JSON-Pointer / Compose-Default-Regex, nicht per
String-Ersetzung), danach `render.py` für die Client-Artefakte. Alter Stand
überall `1.9.0-beta.2`.

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
| `docs/CODEBASE_OVERVIEW.md` | 6 |
| `docs/api/MCP-SURFACE.md` | 5 |
| `systemagents/reqogniloom-operator.md` | 2 |
| `docs/clients/hermes.md`, `hermes.de.md` | je 1 (generiert) |

**Gesamt:** 20 Dateien, 38 Insertions / 38 Deletions. Der Carrier-Ratchet
(`check_plugin_packages.py --expect-version 1.9.0-beta.3`) meldet
12 Sources / 13 Version-Locations / 2 unabhängige POC-Manifeste
konsistent; `clients/render.py --check` meldet 18 Artefakte aktuell
(2 neu geschrieben, 16 unverändert).

**Nicht vom Bumper besessen:** `.meta-config/project.yaml` nennt in zwei
Zeilen weiterhin `Stand VERSION 1.9.0-beta.2` und den beta.2-Report als
„jüngsten". Kein Gate prüft diese Zeilen (der Drift-Guard prüft nur Zahlen),
und der Bumper besitzt sie nicht — sie sind bewusst nicht hand-editiert.
Offene Entscheidung für den Review: `"Stand VERSION"` auf `1.9.0-beta.3`
und die Report-Referenz auf `RELEASE_v1.9.0-beta.3.md` anzuheben.

## 5. Changelog

`CHANGELOG.md` erhält einen Block `## [1.9.0-beta.3] — 2026-11-19` direkt
unter `## [Unreleased]` (Englisch, Keep a Changelog) mit `### Added`
(4 Zeilen), `### Changed` (3 Zeilen) und `### Fixed` (3 Zeilen), jede Zeile
mit `#1943`. Keine Breaking-Markierung: die Änderungen sind
backward-kompatible UI-/Anzeige-Verhaltensweisen; die zwei neuen Präferenzen
haben Defaults `true` und die Manifest-Zahlen bleiben stabil.

## 6. Upgrade-Hinweise und offene Punkte

### 6.1 Automatisch laufend

Keine Datenmigration in diesem Cut. Die beiden neuen Q1-Keys werden beim
Start über `auth_tenancy/apps.py` registriert; ohne gespeicherte Row greift
der Default `true`. Die Baumbreite liegt ausschließlich im lokalen
`localStorage` unter dem neuen `v2`-Key — der alte `reqflow_splitview_*`
wird ignoriert, es gibt also keine Stale-Übernahme und keine Migration.

### 6.2 Verhaltensänderungen

- Der Footer liegt jetzt unter dem Formular statt in der schmalen
  Seitenschiene; die Kette wird erst bei gemountetem Footer aufgelöst.
- `ratio` und `minWidths` haben neue Semantik (Initialwert / Clamp statt
  festem Verhältnis); nach dem ersten Drag gewinnt die gespeicherte Breite.
- `/traceability` öffnet den Impact auf Klick im Drawer statt über einen
  Full-Page-Reload nach `/impact`.

### 6.3 Ausdrücklich nicht enthalten

| Punkt | Status |
|---|---|
| CRUD `TraceLinkPanel` / `ReqTraceLinkPanel` | offen — eigenes Finding, unangetastet |
| Version / History / Properties im Inspector | offen — bleiben dort (D7) |
| MCP-Tool für Display Preferences | bewusst nicht ergänzt — rein interne UI-Präferenz, kein Manifest-Drift |
| Cross-Device-Sync der Baumbreite | bewusst deferred — gerätelokal statt Q1 |
| Live-Device-E2E / visuelle PNG-Abnahme | offen — braucht laufenden Stack und echte Geräte (Abschnitt 8) |
| Manuelles NVDA-/JAWS-/VoiceOver-Sign-off | offen — nicht Teil dieses Cuts |

## 7. Verifikation

> **Herkunft der Nachweise.** Dieser Cut führt **keinen eigenen Suite-Lauf**
> durch. Er ändert — außer Versions-Carriern, `CHANGELOG.md` und diesem
> Report — keinen Code. Maßgeblich sind die Nachweise von PR #1943 auf
> `0972db01`: **CI 98 Checks grün** auf PR #1943 und **lokale Suite 4292
> Tests grün** (im Rahmen der PR-Arbeit). Die Zahlen sind nicht in diesem
> Cut neu gemessen.

| Gate | Befehl / Quelle | Ergebnis |
|---|---|---|
| PR-CI | PR #1943 (`0972db01`) | **98 Checks grün** |
| Lokale Suite (PR-Kontext) | PR #1943 | **4292 Tests grün** |
| Carrier-Ratchet | `python3 scripts/check_plugin_packages.py --expect-version 1.9.0-beta.3` | **OK** — 12 Sources, 13 Version-Locations, 2 POC-Manifeste |
| Client-Artefakte | `python3 scripts/clients/render.py --check` | **OK** — 18 Artefakte aktuell |
| Voller Bump | `python3 scripts/bump_version.py --version 1.9.0-beta.3` | **exit 0** — Carrier gesetzt, Clients gerendert, beide Gates grün |
| Doc-Zahlen | `python3 scripts/generate_doc_counts.py` / `test_doc_number_drift.py` | **20 Apps, 30 ViewSet-Klassen / 35 Registrierungen, 93 Services, 1073 Backend-/430 Frontend-Testdateien, 74 E2E-Specs, 301 Tools** — konsistent mit `CODEBASE_OVERVIEW.md`, `project.yaml`, `AGENTS.md` |
| MCP-Manifest | `docs/agent-templates/tool-manifest.json` | `tool_count: 301`, **49 Präfixe** (gemessen), **20** Built-in-Trace-Link-Typen (`backend/link_types/builtin.py`) |
| Doku-Frische | `scripts/tests/test_doc_index_freshness.py` | gedeckt: `docs/plans`, `docs/features`; **keine** Index-Pflicht für `docs/se/reports` — daher kein Index-Eintrag nötig |

`scripts/check-version-drift.sh` ist **kein** Carrier-Gate: es vergleicht den
`commit_short` einer deployten Umgebung gegen `origin/main` und verlangt
`DEPLOYED_VERSION_URL`; es läuft als täglicher Monitor.

## 8. Risiken und Residuen

- **Kein frischer Suite-Lauf im Cut.** 98 CI-Checks und 4292 Tests stammen
  aus PR #1943; dieser Cut führt nur Bump, Changelog, Report und die
  Script-Gates aus.
- **Keine Live-Device-/PNG-Abnahme.** Die ~14 betroffenen Visual-Baselines
  wurden mit Owner aktualisiert, aber nicht auf echten Geräten visuell
  abgenommen; Responsive-/Reflow-Verhalten ist automatisiert geprüft, nicht
  manuell gesichtet.
- **Kein manuelles Screenreader-Sign-off.** NVDA, JAWS und VoiceOver sind
  nicht manuell geprüft; die A11Y-Aussage stützt sich auf axe-Sweeps,
  ARIA-Attribute, Fokus-Rückgabe und Ratchet-Gates.
- **Zwei Breiten-Semantiken.** `ratio` (Initialwert) und `treeWidth`
  (autoritativ nach Drag) müssen dokumentiert und getestet bleiben; ADR-030
  hält die Autoritätsregel fest.
- **Keine Cross-Device-Synchronisation** der Baumbreite (bewusst deferred),
  korrupte `localStorage`-Werte fallen auf den Modul-Default zurück.
- **Kein Image-Nachweis.** Ohne `scripts/build.sh` + `docker-publish.yml`
  gibt es für diesen Cut keinen Image-/Digest-Beleg.
- **project.yaml-Besonderheit** siehe Abschnitt 4 — kein Gate, aber
  reviewpflichtige Inkonsistenz im „Stand VERSION"-Text.

## 9. Nächste Schritte (nicht Teil dieses Commits)

1. Review dieses Branches, dann Release-PR gegen `main`.
2. Tag `v1.9.0-beta.3` auf den Release-Commit (Aufgabe des `git`-Agenten;
   kein Re-Tag nach dem Push).
3. Build via `scripts/build.sh`, Publish via `docker-publish.yml`.
4. GitHub-**Pre-Release** markieren, nicht `latest`.
5. Release-Notizen aus dem `CHANGELOG`-Block übernehmen.

---

*Erstellt durch den `release`-Agenten am 2026-11-19. Interne Doku (Deutsch),
keine Secrets. Alle Zahlen sind auf PR #1943, die genannten Gate-Läufe oder
die Manifest-/Zähl-Gates zurückführbar; es gibt keinen erfundenen Messwert
und keinen Suite-Lauf dieses Cuts. Kein Commit/Push/Tag durch den Autor.*
