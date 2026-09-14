---
type: STRATEGY
scope: Release v1.8.0-beta.11
status: done
date: 2026-09-14
author_agent: release
---

# Release-Bericht v1.8.0-beta.11

## 1. Release-Ziel

Vorbereitung des Beta-Release `v1.8.0-beta.11` auf dem Branch
`chore/release-v1.8.0-beta.11`. Dieser Bericht dokumentiert ausschließlich die
**Vorbereitungsphase** (Versionierung, Changelog, Release-Bericht, Neubau der
generierten Manifeste, ein Commit). Tag, Push, `make build` und die
Pre-Release-Gates sind ausdrücklich **nachgelagerte, separate Schritte** und
nicht Bestandteil dieses Durchlaufs.

- **Version:** `1.8.0-beta.11`
- **Tag (geplant):** `v1.8.0-beta.11`
- **Basis-Commit:** `f12949e2` (`Merge pull request #945`), Branch-HEAD
- **Letztes Release:** `v1.8.0-beta.10` = `b4c3a910`, Commit-Zeit
  `2026-09-11 20:44:59 +0200` (= `2026-09-11T18:44:59Z`)
- **Datumsstempel des Berichts:** 2026-09-14

## 2. Release-Cutoff (exakter Zeitstempel)

Gemäß §2 der Projekt-Extension (`.claude/3-project/ReqLo-release-ext.md`) wurde
als Cutoff der **exakte Tag-Zeitstempel** von `v1.8.0-beta.10`
(`2026-09-11T18:44:59Z`) verwendet — **kein Kalender-Tagesfilter**. Die
Änderungsmenge wurde aus `git log v1.8.0-beta.10..HEAD` (71 Commits) sowie
`gh pr list --base main --state merged --search "merged:>2026-09-11T18:44:59Z"`
ermittelt.

## 3. Enthaltene PRs seit dem Cutoff

| PR | Merged (UTC) | Titel |
|----|--------------|-------|
| #945 | 2026-09-14T14:34:02Z | feat(attributes): complete Attribut-System v3 WS1-WS7 (#934) |
| #943 | 2026-09-12T22:14:36Z | docs(attribute): attribute-system v3 specification |
| #933 | 2026-09-12T12:22:01Z | fix: close B1 API-contract & B4 embeddings bugfix bundles |
| #931 | 2026-09-11T23:04:08Z | docs(se): 3-Stufen-Attributmodell + Migrationssystematik + Verifikationsprotokoll |
| #910 | 2026-09-11T19:31:48Z | fix(e2e): stabilize visual-regression snapshots against CI drift |

**Hinweis zur Zuordnung:** Klammer-Nummern in Commit-Messages (z. B. `#935`,
`#936`, `#912`, `#864`) sind **Issue-Referenzen**, keine PR-Nummern. Die sechs
Issue-Titel wurden verifiziert (`gh issue view`) und im CHANGELOG als reine
`#NNN`-Referenzen geführt; die PR-Präfixe wurden ausschließlich gegen die
bestätigte Merge-Liste vergeben.

## 4. Themen-Highlights

- **Attribute System v3 (Hauptthema):** Rollout des Attribut-Systems v3 über
  WS1–WS7 — Transport-Parität REST/MCP und `ArtifactAttributeGateway` (#935),
  Identität & Systemfelder inkl. `Actor` (#936), Display-Engine (#937),
  12-Spalten-Layout-Engine (#938), zentraler Attribut-Katalog (#942),
  AWMS-Werte-Migration (#940) und 3-Stufen-Rollout (#939). Spezifikation,
  ADR-004 und Stufenmodell wurden dokumentiert (#931, #943).
- **Preset-Fix aus beta.10-QA:** `mandatory_fields` werden nun pro
  Item-Typ-Definition aufgelöst, statt als flache Workspace-Liste (#912).
- **B1-API-Contract- & B4-Embedding-Bundle (#933):** u. a. `test_type` im
  TestCase-Create (#864), Trace-Link-Picker-Deduplizierung (#832),
  `relevance_score`-Normalisierung (#827), env-konfigurierbare
  Embedding-Dimension (#826), Lazy-Embedding (#847), Celery-Beat-Heartbeat
  (#822), Honcho-Embedding-Config (#911).
- **E2E-Stabilität:** Stabilisierung der Visual-Regression-Snapshots gegen
  CI-Drift (#910).

## 5. Test- und Gate-Status

| Prüfung | Status |
|---------|--------|
| `pytest docs/agent-templates dist -q` | siehe Abschnitt „Verifikation“ in der Übergabe (lokal ausgeführt) |
| Hermes-Plugin `npm test` | lokal ausgeführt (sofern `node_modules` vorhanden), sonst CI |
| Backend-/Frontend-Volllauf, `make build` | **nachgelagert** (nicht Teil dieses Durchlaufs) |
| `pre-release-check.sh` (Pre-Release-Gates) | **nachgelagert** (bewusst nicht ausgeführt) |
| Docker-Image-/Trivy-Gate (Extension §1b) | **nachgelagert** (CI `docker-publish`) |
| Tag-Push + GitHub-Release (Extension §3 Step 2) | **nachgelagert** |

## 6. Dokumentierte Konvention-Abweichungen

1. **Provider-Abweichung bei der Projekt-Extension:** Der release-Agent
   referenziert `.opencode/3-project/ReqLo-release-ext.md`; diese Datei
   **existiert im Repository nicht**. Angewendet wurde stattdessen die
   Quelldatei `.claude/3-project/ReqLo-release-ext.md` (identischer Inhalt,
   dort selbst referenziert von `.claude/agents/release.md`). Die
   `.opencode`-Ausprägung fehlt und sollte perspektivisch nachgezogen werden,
   damit die Extension provider-agnostisch greift.

2. **Frontend-Versions-Drift trotz `VERSION_DIST_BEHAVIOUR` Punkt 2:**
   `frontend/package.json` (und die entsprechenden Felder in
   `frontend/package-lock.json`) standen seit jeher auf `1.0.0`; auch der
   beta.10-Bump hat sie **nicht** angehoben, obwohl
   `.meta-config/project.yaml` → `variables.VERSION_DIST_BEHAVIOUR` Punkt 2
   fordert, dass beide Dateien exakt übereinstimmen. Für beta.11 wurde der
   **Sync durchgeführt** (`VERSION` + `package.json` + `package-lock.json`
   auf `1.8.0-beta.11`). Dies weicht bewusst von der historischen Praxis ab
   und ist im CHANGELOG unter „Changed“ vermerkt.

3. **Fehlender Report in früheren Beta-Releases:** Frühere Beta-Releases
   (`v1.8.0-beta.1` … `v1.8.0-beta.10`) haben **keinen** Bericht unter
   `docs/se/reports/` angelegt — der Verzeichnisbestand enthielt zuvor nur
   `test_quality_audit_report.md` und `deep_audit/*`. Dieser Bericht
   etabliert das Format erstmalig; eine rückwirkende Ergänzung ist nicht
   vorgesehen.

## 7. Geänderte / erzeugte Dateien

- `VERSION` → `1.8.0-beta.11`
- `frontend/package.json`, `frontend/package-lock.json` → Versionsfelder
- `CHANGELOG.md` → neuer Abschnitt `[1.8.0-beta.11] — 2026-09-14`
- `docs/se/reports/RELEASE_v1.8.0-beta.11.md` (dieser Bericht, neu)
- Regenerierte Manifeste (VERSION-Embedding, Extension §1a):
  `dist/plugins/claude-code/reqogniloom/.claude-plugin/plugin.json`,
  `dist/plugins/antigravity/reqogniloom/plugin.json`,
  `integrations/hermes-plugin/reqogniloom/package.json`,
  `integrations/hermes-plugin/reqogniloom/hermes-plugin.json`

## 8. Offene Folge-Schritte

1. Pre-Release-Gates (`pre-release-check.sh`) — separat.
2. `make build` / Backend- + Frontend-Volllauf — separat.
3. Commit wurde in diesem Durchlauf erstellt; **Push und Tag** verbleiben beim
   `git`-Agenten.
4. GitHub-Release `v1.8.0-beta.11` mit `--prerelease` (Extension §3 Step 2).
