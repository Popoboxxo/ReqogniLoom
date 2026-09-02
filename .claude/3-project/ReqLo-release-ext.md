---
name: release-ext
version: 1.0.0
description: Extended pre-release checklist for ReqogniLoom beta/production releases. Captures lessons learned from beta release cycles (v1.8.0-beta.1→beta.3) to prevent preventable CI/publish failures.
tools:
- Bash
- Read
- Write
- Edit
- Glob
- Grep
---

# ReqogniLoom Release Extension

> **Anwendung:** Dieser Block wird von `.claude/agents/release.md` automatisch eingelesen (Zeile 19: `If .claude/3-project/ReqLo-release-ext.md exists → read and apply immediately`).

Diese Erweiterung dokumentiert **wiederkehrende Pre-Release-Checks**, die aus drei gescheiterten Beta-Zyklen gelernt wurden und zukünftige Tag-Push-Fehler vermeiden.

---

## 1. Extended Pre-Release Checklist

Die Basis-Checkliste in `.claude/agents/release.md` ist ein Good Start. Zusätzlich prüfe folgende **drei Fehlerklassen**, bevor du `VERSION` commitst oder einen Tag pushst:

### 1a. Generierte Artefakte mit VERSION-Embedding

**Problem:** `dist/plugins/claude-code/build_claude_plugin.py` und `dist/plugins/antigravity/build_antigravity_plugin.py` lesen beide `VERSION` und betten sie in generierte `plugin.json`-Dateien ein. Ein reiner `VERSION`-Edit ohne Neu-Generierung lässt den CI-Job "Agent Templates & Distribution" rot laufen (Test: `dist/test_full_regeneration.py::test_full_pipeline_regenerates_cleanly`).

**Checklisten-Punkt (VOR Commit/Tag):**
```bash
# 1. VERSION-Datei erhöhen (z.B. von 1.8.0 zu 1.8.1)
echo "1.8.1" > VERSION

# 2. Beide Builder-Skripte laufen lassen
python dist/plugins/claude-code/build_claude_plugin.py
python dist/plugins/antigravity/build_antigravity_plugin.py

# 3. Verify: Tests grün
pytest docs/agent-templates dist --verbose

# 4. Commit/Tag nur NACH erfolgreichem Test
```

**Kontext:** Gefunden in v1.8.0-beta.1→beta.2 Zyklus. Der CI-Job "Agent Templates & Distribution" ist die Gate.

---

### 1b. Docker-Base-Image Security Gate (Trivy)

**Problem:** Docker-Base-Images sind "floating" Tags (z.B. `nginx:1.27-alpine`, `python:3.12-slim`) und können zwischen Rebuilds CVEs ansammeln. Der Trivy-Sicherheits-Gate in `.github/workflows/docker-publish.yml` blockiert mit exit-code:1 bei CRITICAL/HIGH mit Fix.

Konkret gefunden: `nginx:1.27-alpine` hatte 35 fixbare CVEs (2 CRITICAL, 33 HIGH: openssl/libcrypto3, c-ares), weil Alpines apk-Repo Patches veröffentlicht hatte.

**Fix (bereits implementiert):** `apk update && apk upgrade --no-cache` in Frontend-Dockerfile und `apt-get upgrade -y` in Backend-Dockerfile sind hinzugefügt.

**Checklisten-Punkt (Optional, aber empfohlen VOR Tag-Push bei Major-/Minor-Releases):**
```bash
# Frontend (Nginx)
docker build --no-cache -f frontend/Dockerfile -t reqogniloom-frontend:test .
trivy image --severity CRITICAL,HIGH --ignore-unfixed reqogniloom-frontend:test

# Backend (Python)
docker build --no-cache -f backend/Dockerfile -t reqogniloom-backend:test .
trivy image --severity CRITICAL,HIGH --ignore-unfixed reqogniloom-backend:test

# Falls CRITICAL/HIGH gefunden:
#   → Dockerfile updaten (apk/apt-get upgrade oder Base-Image zu neuerem Tag wechseln)
#   → Lokal nochmal bauen & trivy laufen
#   → Dann Tag-Push
```

**Warum optional:** Die Dockerfile-Fixes für `apk/apt upgrade` sind bereits committed. Docker-Publish wird lokal dennoch trivy laufen (mit `--exit-code 1`), aber lokales Pre-Check spart einen fehlgeschlagenen Tag-Push.

**Kontext:** Gefunden in v1.8.0-beta.2→beta.3 Zyklus. Der `docker-publish.yml` Job scheiterte mit CRITICAL-Severity, erzwang einen Patch-Tag.

---

### 1c. GitHub Actions Marketplace Sub-Action-Version-Pins

**Problem:** Der GitHub-Actions-Marketplace kann rückwirkig Sub-Action-Versionen löschen, auf die ein gepinntes Composite-Action-Release verweist, was den Job in "Set up job" scheitern lässt (`Unable to resolve action ... unable to find version vX.Y.Z`), bevor irgendein eigener Code läuft.

Konkret: `aquasecurity/trivy-action@v0.28.0` referenzierte intern `aquasecurity/setup-trivy@v0.2.1`, das upstream gelöscht wurde.

**Checklisten-Punkt (Falls docker-publish Fehler):**
1. Prüfe Workflow-Error: Steht "Set up job" mit `Unable to resolve action`?
   → Nicht dein Bug, sondern Action-Pin-Problem.
2. Betroffene Action identifizieren (z.B. `aquasecurity/trivy-action@v0.28.0`).
3. Auf neueste stabile Version bumpen (z.B. zu `@v0.29.0` oder `@latest`-Tag checken).
4. PR/Commit für den Workflow-Fix, dann nächsten Tag-Push versuchen.

**Kontext:** Gefunden in v1.8.0-beta.3 Zyklus. Ein reiner Workflow-Fix, kein Produktions-Bug.

---

## 2. Release-Cutoff: Exakte Timestamps statt Kalender-Filter

**Problem:** Beim Ermitteln "welche PRs sind seit dem letzten Release neu" NIEMALS nach Kalendertag filtern (`merged:>=YYYY-MM-DD`), sondern nach dem exakten Tag-Zeitstempel des letzten Releases. Sonst werden PRs doppelt gezählt, die schon im letzten Release enthalten waren.

Konkret: v1.8.0-beta-Zyklus zeigte zuerst "52 PRs" (nach Datum), dann "69 PRs" (nach Zeitstempel), bis der exakte Cutoff angewendet wurde — massive Verwirrung.

**Checklisten-Punkt:**
```bash
# Exakte Tag-Zeit des letzten Releases lesen
git log --format="%ai" -1 v1.8.0-beta.1  # Beispiel

# PRs/Commits seit diesem exakten Zeitpunkt abfragen (nicht nach Kalendertag)
# z.B. mit gh CLI:
gh pr list --base main --search "merged:>2026-08-29T14:32:05Z" --json number,title,mergedAt

# CHANGELOG.md: Nur PRs nach diesem exakten Stempel dokumentieren
```

**Warum wichtig:** Release-Notes müssen korrekt sein. Doppelzählungen führen zu Verwirrung und fehlerhaften Rels eases, besonders bei schnellen Patch-Zyklen.

---

## 3. Workflow im Release-Agent

**Step 1 — Pre-Release-Checklist (erweitert):**
| Check | Verification |
|-------|--------------|
| Tests green | `pytest (Backend) + npm test (Frontend)` |
| DoD met | Validator check |
| **VERSION-Artefakte neu generiert** | `python dist/plugins/claude-code/build_claude_plugin.py` + `python dist/plugins/antigravity/build_antigravity_plugin.py` + `pytest docs/agent-templates dist` ✓ |
| **Trivy Security Gate (optional)** | `docker build --no-cache` + `trivy image --severity CRITICAL,HIGH --ignore-unfixed` für Frontend + Backend (oder warten bis docker-publish CI it prüft) |
| **GitHub Actions-Pins aktuell** | `.github/workflows/docker-publish.yml`: Keine bekannten kaputten Action-Pins (falls Fehler: upgrade zu neuester stabiler Version) |
| CHANGELOG.md updated | All changes since last tag recorded (mit exaktem Zeitstempel-Cutoff, kein Kalender-Filter) |
| Version bumped | SemVer convention (see `<context>`) |
| Build created | `docker-compose build` |
| README/CODEBASE_OVERVIEW | Current |
| git commit + tag + push | `git` agent |

**Step 2 — GitHub Release erstellen (KRITISCH — NICHT ÜBERSPRINGBAR):**

Nach erfolgreichem Tag-Push IMMER den GitHub-Release-Eintrag erstellen. **`git tag` Push allein ist NICHT ausreichend** — ein Tag wird nicht in `gh release list` angezeigt, bis ein GitHub-Release-Eintrag existiert.

```bash
# Tag auslesen (vom git-Agent kommend, zB v1.8.0-beta.6)
TAG="v1.8.0-beta.6"

# CHANGELOG-Sektion für diesen Tag ermitteln
# (aus CHANGELOG.md, [HEAD]…Tag-Datum auszug)

# GitHub Release erstellen mit CHANGELOG-Ausschnitt als Notes
gh release create "$TAG" \
  --title "Release $TAG" \
  --notes "$(cat CHANGELOG_SECTION.txt)" \
  --prerelease  # Falls Beta/RC; entfernen für Production

# Verifikation: Muss in `gh release list` sichtbar sein
gh release list | head -1
```

**Fallstricke:**
- ❌ Nur `git tag -a` pushen, aber `gh release create` vergessen → Tag sichtbar in `git tag`, aber NICHT in `gh release list`. Das ist der echte v1.8.0-beta.6 Bug.
- ❌ `--prerelease` vergessen bei Beta/RC-Releases → GitHub markiert fälschlicherweise als "Latest Release".
- ✓ CHANGELOG-Ausschnitt als `--notes` übergeben → Release-Notes sind aussagekräftig für Nutzer.

**Step 3 — Wenn docker-publish CI rot wird:**
- Ist es "Set up job" → Workflow-Action-Pin-Issue (siehe 1c)
- Ist es Trivy CRITICAL/HIGH → Dockerfile Base-Image/Packages updaten (siehe 1b)
- Sonst → Standard-Bug-Triage

---

## 4. Lessons Learned Summary

| Fehlerklasse | Zyklus gefunden | Kosten | Prevention |
|---|---|---|---|
| VERSION-Embedding in generierten Dateien nicht neu gebaut | v1.8.0-beta.1 → beta.2 | 1 Patch-Tag | Beide Builder + `dist`-Tests VOR Commit laufen |
| Docker CVE-Trivy-Gate blockiert | v1.8.0-beta.2 → beta.3 | 1 Patch-Tag | Lokales `docker build --no-cache` + `trivy` VOR Tag-Push (optional) |
| GitHub Action Sub-Version gelöscht | v1.8.0-beta.3 | 1 Patch-Tag | Workflow-Pins regelmäßig auditen, Update-Path bereit halten |
| **Summe dieser Zyklen** | **3 Tage Verzögerung, 3 Beta-Patch-Tags** | **Verhindert mit dieser Checkliste** | **Oben dokumentiert** |

---

## 5. Integration mit `release.md` Workflow

Diese Extension lädt sich selbst zur Laufzeit in den `release`-Agent. Der `release`-Agent:
1. Liest diese Datei (Extension-Mechanism, `.claude/agents/release.md` Zeile 19)
2. **Erweitert** die Basis-Checkliste (nicht ersetzt sie) mit den drei Fehlerklassen oben
3. Führt den Workflow aus (Versioning, Build, Tag, Push) unter Beachtung aller erweiterten Checks
4. Returniert `STATUS: done` + Version + Tag + Release-URL

**Kein manuelles Registrieren in `.meta-config/project.yaml` nötig** — sync.py ignoriert `.claude/3-project/` sowieso. Diese Datei ist reine Project-Governance.
