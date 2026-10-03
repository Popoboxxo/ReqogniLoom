---
type: EVIDENCE
scope: wp6a-secrets-scan
status: success
date: 2026-09-29
author_agent: security-auditor
---

# WP-6a Evidenz — Secret-Scan

**Methode:** `rg` (ripgrep, read-only) über das Arbeitsverzeichnis, plus `git ls-files` /
`git check-ignore` / `git log -S` für die Tracked-/History-Frage, plus 2 nicht-mutierende
Live-Credential-Validierungen (`POST /mcp/` `tools/list`).
**Grundsatz:** Es werden ausschließlich **Pfade, Zeilen und Mustertypen** dokumentiert, **niemals Werte.**

---

## 1. Gate-Inventar: existiert überhaupt ein Secret-Scanner?

| Ort | Kommando | Ergebnis |
|---|---|---|
| Root `.pre-commit-config.yaml` | `Get-ChildItem -Filter .pre-commit-config.yaml -Recurse -Depth 2` | **existiert nicht** |
| `.agents/hooks.json` | `Get-Content` | genau **1** Hook: `orchestrator-guard` (PreToolUse, Konventions-Guard) |
| `.agents/hooks/*.sh` (7 Dateien) | `rg -e 'gitleaks\|trufflehog\|detect-secrets\|secret.?scan\|sk-\|AKIA' -i` | **0 Treffer** |
| `.claude/hooks/*.sh` (11 Dateien) | dito | **0 Treffer** |
| `.github/workflows/ci.yml` | `rg -e 'gitleaks\|trufflehog\|detect-secrets\|secret' -i` | **0 Treffer** (nur `secrets.FIELD_ENCRYPTION_KEY`, `secrets.GITHUB_TOKEN` als *Verbrauch*) |
| `.github/workflows/docker-publish.yml` | dito | **0 Treffer** (nur Trivy-Image-Scan, `secrets.GITHUB_TOKEN`) |
| `.woodpecker.yml` | dito | **0 Treffer** |
| Host-Tooling | `Get-Command gitleaks,trufflehog,detect-secrets` | **alle drei nicht installiert** (`rg.exe` vorhanden) |

**Befund AUD-2026-09-224 (HIGH):** Es gibt **kein** Secret-Scanning-Gate — weder als pre-commit-Hook noch in CI.
Der in `AGENTS.md` unter *„Security Paved Roads"* geforderte Block `secret-scanning`
(„Vor jedem Commit: Secret-Scan … ausführen") ist **nicht implementiert**.

---

## 2. Pattern-Matrix

Prüfmuster (identisch für Arbeitsbaum und Repo-History):

```
reqlo_[A-Za-z0-9]{20,}                      # projekt-eigene API-Keys
reqlo_[A-Za-z0-9]{40}                       # Realformat-Länge
sk-ant-[A-Za-z0-9_-]{20,}                   # Anthropic
sk-proj-[A-Za-z0-9_-]{20,}                  # OpenAI
AKIA[0-9A-Z]{16}                            # AWS Access-Key-ID
ghp_[A-Za-z0-9]{30,}                        # GitHub PAT
-----BEGIN [A-Z ]*PRIVATE KEY-----          # PEM
eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}    # JWT
(?i)(password|passwd|secret|api[_-]?key|token)\s*[:=]\s*["'][^"']{8,}["']
```

| Muster | Treffer im Arbeitsbaum | Tracked? | Von gitleaks-Standardregeln abgedeckt? |
|---|---|---|---|
| `reqlo_` (≥20 Z.) | 12 | 8 tracked / 4 untracked | **NEIN** — kein bekannter Prefix; Custom-Regel nötig |
| `reqlo_` (exakt 40 Z.) | 5 | 2 tracked / 3 untracked | **NEIN** |
| JWT (`eyJ…`) | 1 | 0 (untracked) | teilweise (nur mit `jwt=`-Kontext) |
| `sk-ant-` | 0 | — | ja |
| `sk-proj-` | 0 | — | ja |
| `AKIA…` | 0 | — | ja |
| `ghp_…` | 0 | — | ja |
| PEM Private Key | 0 | — | ja |
| generischer `password=`/`api_key=` mit Wert ≥8 | 0 in `docs/` | — | ja |

**Wichtig:** Der reale Fund liegt genau in dem Muster, das **kein** Standard-Regelwerk erkennt
(`reqlo_`-Prefix). Ein nachträglich eingeführter gitleaks-Lauf **ohne** Custom-Regel hätte Finding 220
**nicht** gefunden.

---

## 3. Treffer — Pfade und Typen (keine Werte)

### 3.1 ECHT / KRITISCH

| Pfad | Zeile | Typ | Tracked | Commit | Live-Validierung |
|---|---|---|---|---|---|
| `docs/audit/2026-09/AUDIT_EVIDENCE/wp1d-auth-pagination-filter-errors-live.json` | 2246 | `reqlo_` + 40 Z., `principal_type=user`, `scope=write` (`wr…` im abgeschnittenen Body) | **ja** | `3dcc80d8` (2026-09-30) | **HTTP 200** auf `POST /mcp/` `tools/list` |
| `docs/audit/2026-09/AUDIT_EVIDENCE/wp1d-tenant-leak-matrix.json` | 101 | `reqlo_` + 40 Z., `principal_type=agent`, `scope=write` | **ja** | `3dcc80d8` (2026-09-30) | HTTP 401 (widerrufen) |

Kontext des Live-Treffers (`wp1d-auth-pagination-filter-errors-live.json:2237-2247`):

```json
"top_keys": ["agent_label","id","name","plaintext","principal_type","scope","warning"],
"body_head": "{\"id\": \"<uuid>\", \"name\": \"wp1d-probe-dup\", \"plaintext\": \"reqlo_<40 Z.>\", ... \"principal_type\": \"user\", ... \"scope\": \"wr…"
```

**Bemerkenswert:** derselbe Datensatz enthält `top_keys` (das korrekte Redigieren-Verfahren) **und** `body_head`
mit dem vollständigen `plaintext`. Das Redaktions-Prinzip war bekannt und wurde nicht konsequent angewandt.

### 3.2 BEWUSST / UNCOMMITTED (Klartext-Credentials, kein Fund)

| Pfad | Zeilen | Typ | Tracked? |
|---|---|---|---|
| `docs/audit/2026-09/AUDIT_EVIDENCE/stack-seeds.md` | 26, 126, 131 | `reqlo_` + 40 Z. (3× derselbe MCP-Header-Key) | **nein** — `git ls-files` listet die Datei nicht |
| `docs/audit/2026-09/AUDIT_EVIDENCE/stack-seeds.md` | 102 | JWT (3 Segmente, `eyJ…`) | **nein** |
| `.env` (Repo-Root) | 20 Secret-Variablen | SECRET_KEY, DB_PASSWORD, DB_APP_PASSWORD, AUTH_JWT_SECRET, FIELD_ENCRYPTION_KEY, LLM_API_KEY (leer), REDIS_PASSWORD (leer), SYSTEM_ADMIN_PASSWORD | **nein** — `.gitignore:18`; `git check-ignore -v .env` → `.gitignore:18:.env` |

→ **Der Hinweis aus dem Auftrag ist bestätigt:** `stack-seeds.md` enthält bewusst Klartext-Credentials
und ist **nicht committet**. `.env` ist ebenfalls korrekt ignoriert.

### 3.3 FEHLALARME (dokumentiert, kein Fund)

| Pfad | Zeilen | Typ | Bewertung |
|---|---|---|---|
| `README.md` | 1130, 1140, 1164, 1183 | `reqlo_` + 44 Z. (dokumentiertes Beispiel `Ab12Cd34Ef56…`) | **Fehlalarm** — bewusstes API-Doku-Beispiel, aber formal ein Secret-Muster ⇒ braucht Ausnahme |
| `backend/mcp_server/tests/test_interview_tool_group_formalize_parity.py` | 43 | `reqlo_` 27 Z. `…placeholder_testkey1234` | Fehlalarm (Test-Fixture, Name sagt „placeholder") |
| `backend/mcp_server/tests/test_interview_tool_group.py` | 33 | dito | Fehlalarm |
| `backend/mcp_server/tests/test_transition_version_conflict_cr08.py` | 52 | `reqlo_` 34 Z. `…placeholder_testkey_cr08` | Fehlalarm |
| `backend/mcp_server/tests/test_mcp_workspace_id_header_decorative.py` | 53 | `reqlo_test_placeholder_token` | Fehlalarm |
| `backend/mcp_server/tests/test_tenant_context_activation.py` | 59 | `reqlo_tenant_context_test_key` | Fehlalarm |
| `backend/auth_tenancy/tests/test_api_key_pepper.py` | 105 | `reqlo_legacy_key_issued_before_the_pepper` | Fehlalarm |
| `backend/auth_tenancy/tests/test_api_key_header_precedence_1076.py` | 194 | nur Funktionsname im String | Fehlalarm |

**Faustregel:** Test-Fixtures sind laut Auftrag **keine** Findings (FP-Guard). Sie müssen aber in einer
`.gitleaks.toml`-Ausnahmeliste stehen, sonst ist ein eingeführter Scanner dauerhaft rot und wird ignoriert.

### 3.4 Historie

```
git log --all --oneline -S'reqlo_' --pickaxe-regex -- docs/
  75beb750  docs(audit): WP-2 deep audit of native plugins and integrations
  3dcc80d8  docs(audit): WP-1d deep audit of the REST API and data integrations
  cd002d94  docs(audit): WP-1a deep audit of the native MCP server
  38da915f  release: v1.8.0-beta.18
  abd61aed  Fix/plugin interface bugs (#1118)
  … (weitere, Release-/Fix-Commits — README-Beispiel + Fixtures)
```

⇒ Das Problem ist **nicht** auf einen Commit beschränkt; `3dcc80d8` ist der erste Commit mit echtem
Klartext-Credential in `docs/`. Ein `git filter-repo` muss ab dort greifen.

---

## 4. Gegenprobe: `.env.example`

63 Variablen klassifiziert (nur Feldnamen + Kategorie, keine Werte):

| Kategorie | Anzahl | Beispiel-Felder |
|---|---|---|
| `PLACEHOLDER` | 5 | `SECRET_KEY`, `AUTH_JWT_SECRET`, `FIELD_ENCRYPTION_KEY`, `DB_PASSWORD`, `DB_APP_PASSWORD`, `SYSTEM_ADMIN_PASSWORD` |
| `EMPTY` | 8 | `API_KEY_PEPPER`, `LLM_API_KEY`, `LLM_BASE_URL`, `REDIS_PASSWORD`, `HONCHO_API_KEY`, `EMBEDDING_MODEL_NAME`, … |
| `LITERAL` (nicht geheim — Betriebsparameter) | 50 | `DJANGO_ENV=development`, `DEBUG=False`, `ALLOWED_HOSTS=localhost,…`, `API_RATE_LIMIT_USER=600`, `LOGIN_THROTTLE_RATE=10/min`, `DB_NAME=reqflow`, `LLM_PROVIDER=mock`, `OLLAMA_BASE_URL=http://…`, `BACKUP_RETENTION=7`, … |

**Ergebnis: kein echtes Secret in `.env.example`.** Negativbefund N-18.

---

## 5. Empfehlung (Gate-Design)

```
# 1) pre-commit
repos:
  - repo: local
    hooks:
      - id: gitleaks
        entry: gitleaks protect --staged --redact --config .gitleaks.toml
        language: system
        stages: [pre-commit]

# 2) .gitleaks.toml — Custom-Regel für den Projekt-Prefix
[[rules]]
  id = "reqogniloom-api-key"
  description = "ReqogniLoom API key (reqlo_ + 40)"
  regex = '''reqlo_[A-Za-z0-9]{40}'''
  keywords = ["reqlo_"]

# 3) ci.yml — VOR den Tests, zwei Modi
- run: gitleaks detect --no-git --redact --config .gitleaks.toml   # Arbeitsbaum
- run: gitleaks detect --redact --config .gitleaks.toml            # History
- uses: actions/upload-artifact@v7
  if: always()
  with: { name: gitleaks-report, path: gitleaks-report.json }
```

Ohne Schritt 2 findet der Scan Finding 220 **nicht**.