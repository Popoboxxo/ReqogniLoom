# S0.1 secret-scan evidence — pinned gitleaks full-history run

**Date:** 2026-11-17 · **Worktree:** `.tmp/wt-s01` · **Branch:** `fix/s0-1-scanner`
**Purpose:** local evidence for review findings S0.1-R1..R6 of the secret-scan
slice (CI secret-scan job in `.github/workflows/ci.yml`).

> **Redaction:** this report contains ONLY counts, rule IDs, file paths, commit
> SHAs and tool metadata. No secret value, token, API key or match string is
> reproduced anywhere in it. Live-shaped values are described by shape
> (`reqlo_<40 alnum>`, `<hex>`) only. This file is referenced from the CI
> comment above the fourth (default-rule) scan step.

## Scanner

| Item | Value |
|---|---|
| Version | gitleaks 8.30.1 (`gitleaks version` → `8.30.1`) |
| Source | `https://github.com/gitleaks/gitleaks/releases/download/v8.30.1/gitleaks_8.30.1_linux_x64.tar.gz` |
| sha256 (linux x64) | `551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb` |
| Checksum check | `gitleaks_8.30.1_linux_x64.tar.gz: OK` |
| Command set | 8.30.1 knows only `git` and `dir`; no `detect`/`protect` |

## Config split under test

| Config | Rules | Allowlists | Used by |
|---|---|---|---|
| `.gitleaks-dedicated.toml` | `reqlo-api-key`, `env-secret-assignment` | **none**, `useDefault = false` | the three dedicated CI gates + canary + local pre-commit hook 1 |
| `.gitleaks.toml` | default ruleset + the same two custom rules | five narrow `[[allowlists]]`, `useDefault = true` | the fourth (default-rule) CI gate + default-rule canary + pre-commit hook 2 |

## Results (exact exit codes and counts)

| # | Command (abridged) | Exit | Result |
|---|---|---:|---|
| 1 | `python3 -c "import tomllib; ..."` on both configs | 0 | both parse |
| 2 | `gitleaks dir . --config .gitleaks.toml --redact --exit-code 1 --no-banner` | 0 | `no leaks found` (24.98 MB) |
| 3 | `gitleaks git . --config .gitleaks.toml --redact --no-banner --report-format json …` | 0 | 3098 commits, 564.57 MB, `no leaks found`, report = 0 findings |
| 4 | `gitleaks dir . --config .gitleaks-dedicated.toml --enable-rule reqlo-api-key …` | 0 | `no leaks found` (76.87 MB) |
| 5 | `gitleaks git . --config .gitleaks-dedicated.toml --enable-rule reqlo-api-key …` | 0 | 3098 commits, `no leaks found`, report = 0 findings |
| 6 | Canary step extracted from `ci.yml` and executed with both rule-id env vars | 0 | four rule IDs reported (see below) |
| 7 | R1 regression (dedicated config, reqlo token under `docs/*.md`) | 1 | finding reported → allowlisted path does **not** hollow the dedicated gate |
| 8 | R1 regression (allowlisted config, same fixture) | 0 | finding suppressed → proves the two configs are genuinely split |
| 9 | SEC-001 expiry guard, today (2026-11-17) | 0 | `expiry OK (removal deadline 2026-12-01)` |
| 10 | SEC-001 expiry guard, simulated date 2026-12-02, marker present | 1 | fails closed with `::error::` message |
| 11 | SEC-001 expiry guard, simulated date 2026-12-02, marker removed | 0 | passes once the allowlist is gone |

### Canary rule IDs (item 6)

All four required IDs were reported in the default-rule canary report:
`reqlo-api-key`, `env-secret-assignment`, `github-pat`, `private-key`.
The step output was:

```
Canary OK: 'reqlo-api-key' resolved and reported its canary
Canary OK: 'env-secret-assignment' resolved and reported its canary
R1 regression OK: reqlo in an allowlisted path is still reported by the dedicated config
Default-rule canary OK: built-in (github-pat, private-key) and custom (reqlo-api-key, env-secret-assignment) detectors reported
```

## Baseline measurements (why the allowlists exist)

Measured on this checkout with the pinned binary; only counts and rule IDs:

| Scan | Without allowlists | With reviewed allowlists |
|---|---:|---:|
| Default rules, full history | 644 findings — `generic-api-key` 444, `env-secret-assignment` 156, `sourcegraph-access-token` 32, `curl-auth-header` 12 | 0 |
| Default rules, working tree | 74 findings | 0 |
| Default rules, full history, **only** TEMP SEC-001 allowlist removed | 3 findings — `env-secret-assignment` × 3, all on `.env` | 0 |

The 3 residual findings come from commits `798650dfad0c11c40285596d2b591d3faee75686`
(1) and `a8cee99e1545e5a4df3b727f6a760a5417ed1daa` (2). When the same lines are
scanned with the commit allowlist narrowed to `targetRules = ["env-secret-assignment"]`
only, 2 `generic-api-key` findings on `.env` lines 11 and 20 of `a8cee99e`
surface (gitleaks dedupes same-line hits, so the previously-active
`env-secret-assignment` finding had hidden them). Listing both rules in
`targetRules` returns the gate to 0 findings while still narrowing the
suppression from "every rule in those commits" to "these two rules on `.env`".

## Scope note — dedicated `env-secret-assignment` on the working tree

Running the dedicated config with `--enable-rule env-secret-assignment` over the
**whole working tree** reports 12 pre-existing hits (informational only — this
rule's only blocking gate is the PR-diff scan, so these historical lines are out
of scope). Paths, for transparency: `backend/Dockerfile` (5),
`backend/llm_adapter/providers.py` (2), `deploy/verify-backup-command.sh` (1),
`deploy/docker-compose.yml` (1),
`docs/superpowers/plans/Archive/2026-08-16-prompt-variable-catalog.md` (1),
`docs/superpowers/plans/2026-09-03-mcp-modernisierung.md` (2).
The rule-level stopwords/path allowlist (`.example`, tests, e2e) is retained in
both configs; no secret value from these files is reproduced here.

## SEC-001 — temporary allowset reconciliation

The TEMP entry in `.gitleaks.toml` is bounded by owner (`devops-engineer`),
issue/evidence link (SEC-001 in `docs/audit/gates/2026-11-16/mvp-gates.md`),
`paths = ['''^\.env$''']`, `targetRules` for the two firing rules, and a hard
removal date of **2026-12-01** enforced by the CI expiry step. The reconciled
commit set:

* `798650df…` — introduced the committed `.env` (1 gitleaks finding).
* `a8cee99e…` — modified it (2 findings on `.env`; full values at lines 11/20).
* `bad447fd…` — untracked/removed `.env` (gate report's `-S` removal commit;
  0 gitleaks findings today, kept so the incident chain is documented).
* Audit-doc commits `cedb62f8` / `08550995` hold only truncated prefixes in
  Markdown and are covered by the `\.md$` path allowlist — no commit entry.

**Next step (owner/user-blocked):** rotate `SECRET_KEY`, `DB_PASSWORD` and all
derived sessions/tokens first; then rewrite history and delete the TEMP
allowlist plus the expiry step together.
