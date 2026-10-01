---
type: PLAN
scope: audit-review-2026-09-security-track
status: final
date: 2026-10-01
author_agent: planner
epic: SECTRACK — Offener Secret-Vorgang (P0)
branch: chore/audit-review-2026-09
parent: IMPLEMENTATION_PLAN.md
---

# Epic SECTRACK — Offener Secret-Vorgang (eigener P0-Track)

> **Push-Blocker.** Kein Push, bis SECTRACK-02 ausgeführt und verifiziert ist. Keine
> Klartext-Secrets in Doku/Plan; nur maskierte IDs. `stack-seeds.md` bleibt untracked.

## SECTRACK-01 — Key-Rotation: `ff77bbd0…` + 8 `admin`-Keys (P0, W1)

- **Findings:** 220, 240
- **Ort:** `docs/audit/2026-09/AUDIT_EVIDENCE/stack-seeds.md` (`ff77bbd0-e99c-…`,
  untracked); 8 weitere aktive `admin`-Keys (§1.6 der Secret-Evidenz);
  Produktionspfad `DELETE /api/v1/api-keys/<id>/`
- **Zielverhalten:** Zweiten live Key **widerrufen** (nicht User löschen); die 8 weiteren
  Keys widerrufen/rotieren; Policy: Agent-Keys benötigen `expires_at` und `workspace_ids`.
- **Akzeptanz:** `POST /mcp/` mit `ff77bbd0…` ⇒ **401**; `revoked_at` NOT NULL (DB-`SELECT`);
  aktive-Key-Liste enthält die IDs nicht; Policy in Auth-Service/Modell erzwungen.
- **Test:** Live-Widerrufsbeleg (401 + DB) + pytest (Expiry/Fence-Pflicht). ·
  **Aufwand:** S · **Risiko/Rollback:** breite Rotation kann laufende Clients brechen →
  Inventar vorher, Ersatzkeys. · **Deps:** — · **ADR:** ii (Policy)

## SECTRACK-02 — History-Blob Option A (`git filter-repo`, Bundle-Backup) (P0, W1)

- **Findings:** 220
- **Ort:** Commit `3dcc80d8` (nie gepusht, `merge-base --is-ancestor` exit 1);
  `--replace-text` gegen Blob-Ebene; `docs/audit/.../wp1d-*.json`
- **Zielverhalten:** `git filter-repo --replace-text` gegen `3dcc80d8` **und Nachfolger**;
  **Bundle-Backup zwingend vorher**; `refs/original`/`reflog` bereinigt; danach SHA-Verweise
  in `AUDIT_SECURITY.md`, `wp6a-secrets-scan.md`, `secret-incident-*.md` aktualisiert.
- **Akzeptanz:** `git grep -lE "reqlo_[A-Za-z0-9]{40}" <alle Bäume>` → nur README-Doku-Beispiel;
  `rg` in `docs/audit/` → 0; Bundle außerhalb des Repos vorhanden; nur ausgeführt, wenn
  parallele Agents abgeschlossen sind.
- **Test:** Verifikations-`rg`/`git grep` (Baum-Ebene, nicht Diff). ·
  **Aufwand:** S · **Risiko/Rollback:** umschreibt alle 30 lokalen Commit-SHAs → Bundle +
  Branch-Referenz-Vorher; Revert nur aus Bundle. · **Deps:** — · **ADR:** —

## SECTRACK-03 — Secret-Scan-Gate (P0, W1)

- **Findings:** 224, 220
- **Ort:** kein `.pre-commit-config.yaml`; `rg gitleaks|trufflehog|detect-secrets` = 0;
  `.woodpecker.yml:76-80` (nur Dependency-Scan)
- **Zielverhalten:** Pre-Commit `gitleaks protect --staged --redact` + **Custom-Regel
  `reqlo_[A-Za-z0-9]{40}`** (Standardregeln finden den Projekt-Key nicht); CI `gitleaks
  detect` (History + Arbeitsbaum) mit Ausnahmeliste für Doku-Beispiel/Test-Fixtures.
- **Akzeptanz:** Ein Test-Commit mit Dummy-`reqlo_`-Key wird **blockiert**; CI-Step läuft;
  bekannte False Positives sind in der Allowlist dokumentiert.
- **Test:** Negativ-/Positiv-Probe des Hooks. · **Aufwand:** S · **Risiko/Rollback:**
  Fehlalarme blockieren Commits → Allowlist pflegen. · **Deps:** — · **ADR:** —

## SECTRACK-04 — Evidenz-Redactor + Cleanup-Checkliste (P0, W1)

- **Findings:** 239, 220
- **Ort:** Ursache `AUDIT_EVIDENCE/*` (`top_keys` vs. `body_head`);
  `wp1d-cleanup-verification.md` (prüfte User-Löschung statt Key-Widerruf)
- **Zielverhalten:** Wrapper `safe_dump(response)` entfernt `plaintext`/`token`/`password`/
  `key`/`secret` aus **jedem Wert**, schreibt nur `top_keys` + maskierte Values; verbindliche
  Cleanup-Checkliste „je Key widerrufen + `revoked_at` prüfen + `rg` 0 Treffer".
- **Akzeptanz:** Eine synthetische Response mit `plaintext` erzeugt eine Evidenzdatei ohne
  Klartext; Checkliste ist Teil der Audit-Task-Definition.
- **Test:** Unit-Test des Redactors (`rg reqlo_` auf Output = 0). · **Aufwand:** M ·
  **Risiko/Rollback:** Redactor zu aggressiv → strukturierte Feldnamen bleiben erhalten. ·
  **Deps:** — · **ADR:** —

## SECTRACK-05 — Hardcoded Deploy-Credentials (P2, W3)

- **Findings:** 241 (=148, Duplikat), 148
- **Ort:** `deploy/verify-backup-command.sh:90,103` (`POSTGRES_PASSWORD=…`);
  `deploy/docker-compose.yml:73,1053` (`HONCHO_DB_PASSWORD:-honcho`)
- **Zielverhalten:** `${VAR:?}`-Pflichtvariablen statt Klartext/Defaults.
- **Akzeptanz:** Start ohne gesetzte Variablen schlägt mit klarer Meldung fehl; kein
  Klartext-Passwort getrackt. · **Test:** Compose-Konfig-Test. · **Aufwand:** S ·
  **Risiko/Rollback:** Deployment muss Variable setzen → dokumentiert. · **Deps:** — · **ADR:** —
