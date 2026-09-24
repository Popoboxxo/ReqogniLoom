---
type: REVIEW
scope: system-audit-2026-09
status: final
date: 2026-09-24
author_agent: dependency-auditor
revision: e3df119e52c0cbcc18df02f708567207c0374826
branch: feat/1031-bluepencil-host-bridge
---

# Systemaudit 2026-09 — Dependencies, Supply Chain, Lizenzen und Release-Reproduzierbarkeit

**Auditdatum:** 2026-09-24  
**Repository:** `C:\Repositories\ai-native-reqflow-POC`  
**Revisionsstand:** `e3df119e52c0cbcc18df02f708567207c0374826`  
**Änderungsgrenze:** ausschließlich dieser Bericht; keine Anwendungs-, CI- oder Infrastrukturdatei geändert.  
**Prüfmodus:** statische Manifest-, Lockfile-, CI-, Container-, Plugin- und Vendored-Asset-Analyse. Keine Installation, kein Testlauf, kein Containerstart, keine Runtime-Änderung.

## 1. Management-Summary

Der Audit bestätigt **0 P0, 3 P1, 8 P2 und 1 P3**. Die größten Risiken sind nicht einzelne, live bestätigte CVEs, sondern die fehlende Bindung zwischen deklarativem Soll und dem tatsächlich gebauten bzw. ausgelieferten Stand:

1. `backend/requirements.lock` ist stale, dokumentarisch und wird weder im Docker-Build noch in CI installiert; der Docker-/CI-Resolver verwendet dagegen offene Bereiche aus `backend/requirements.txt` (`backend/requirements.txt:4-8`, `backend/Dockerfile:29-51`, `.github/workflows/ci.yml:98-100`).
2. Containerbasis, Betriebssystem-Pakete und Actions sind über Tags statt Digests/SHAs mutierbar; ein Commit ist daher nicht byte-reproduzierbar (`backend/Dockerfile:8,63`, `frontend/Dockerfile:4,44`, `.github/workflows/ci.yml:15-20`).
3. Der Release-Scan läuft auf einem ersten Build, während ein zweiter Build gepusht wird; SBOM-/Provenienz-/Signaturartefakte werden nicht als Release-Nachweis archiviert (`.github/workflows/docker-publish.yml:98-112,142-154,165-191`).
4. Python-Lockdrift, dynamische MCP-Installationen, unvollständige Hermes-Lockdaten und eine absichtlich gemischte Bluepencil-Vendorversion verhindern derzeit eine durchgängige SBOM-/Provenienzkette.
5. Die Lizenzlage ist überwiegend permissiv, aber eine vollständige transitive Lizenz- und Notice-Matrix existiert nicht. MPL-2.0-, OFL-1.1- und CC-BY-4.0-Einträge sind im npm-Lock sichtbar; die Python-Closure enthält überhaupt keine Lizenzfelder.

**CVE-Status:** In diesem Audit wurde **keine externe CVE-Datenbank (NVD, OSV, GitHub Advisory Database) live abgefragt** und kein `pip-audit`, `npm audit` oder Trivy-Lauf ausgeführt. Die in Kommentaren genannten CVE-/PYSEC-IDs sind Projektaussagen, keine hier unabhängig verifizierten Treffer. **Bestätigte verwundbare Pakete: 0 — das bedeutet nicht, dass keine Schwachstellen vorhanden sind.** Ein zentraler Verifikationsplan steht in Abschnitt 9.

## 2. Methodik und Evidenzregeln

- Vorrang haben aktuelle Manifeste, Lockfiles, Dockerfiles, Compose-Dateien, Workflows, Plugin-Metadaten und Vendored-Dateien. Historische Systemaudits wurden nur als Hinweis gelesen.
- Jeder Befund nennt eine konkrete Datei-/Zeilenreferenz, eine mögliche Auswirkung, die Root Cause, Gegenmaßnahme, Aufwand, Alternativen, Confidence und einen Verifikationsplan.
- Externe Seiten wurden nur als Faktenquelle verwendet. Abgerufen am 2026-09-24:
  - npm `headroom-ai`: <https://www.npmjs.com/package/headroom-ai> — 0.38.0, Apache-2.0.
  - npm `@playwright/mcp`: <https://www.npmjs.com/package/@playwright/mcp> — 0.0.82 zum Abrufzeitpunkt.
  - PyPI `honcho-ai`: <https://pypi.org/project/honcho-ai/> — 2.5.0, veröffentlicht 2026-09-17, Apache-2.0.
  - PyPI `django-celery-beat`: <https://pypi.org/project/django-celery-beat/> — 2.9.0, BSD, Django `<6.1`.
  - GitHub-Issue `celery/django-celery-beat#1079`: <https://github.com/celery/django-celery-beat/issues/1079> — offen zum Abrufzeitpunkt.
  - Commit-Raw-Datei `6767df6…/requirements/runtime.txt`: <https://raw.githubusercontent.com/celery/django-celery-beat/6767df6f6f723a96ebd38269a073a11cde124850/requirements/runtime.txt> — `Django>=3.2.25,<6.2`.
- Externe Dateien und Agent-Dokumentation wurden als Daten behandelt; enthaltene Installations- oder Rollen-Anweisungen wurden nicht ausgeführt.
- Ignorierte lokale Provider-/Secret-Konfigurationen wurden nicht in den Bericht übernommen. Es wurden keine Secrets ausgegeben.
- Nicht versionierte lokale `node_modules`-/`Hidden-Lock`-Beobachtungen sind nicht reproduzierbar und werden nicht als kanonische Evidenz oder Zählgrundlage verwendet.

## 3. Manifest- und SBOM-Sicht

Die folgende Tabelle ist eine **manifestbasierte SBOM-Sicht**, kein CycloneDX-/SPDX-Dokument. Im Repository wurde kein formaler SBOM (`*.cdx.json`, `*.spdx.json`, `*sbom*`) gefunden.

| Fläche | Manifest/Lockfile | Umfang und aktueller Befund |
|---|---|---|
| Backend/Python | `backend/requirements.txt`, `backend/requirements.lock` | ca. 25 direkte Deklarationen, 132 Lock-Pins; Lock ohne Hashes, datiert auf 2026-08-30, nicht installiert und nachweislich stale. |
| Frontend/Node | `frontend/package.json`, `frontend/package-lock.json` | 682 Lock-Knoten; 682 `resolved`/`integrity`-Einträge, 681 Lizenzfelder (Root-Metadaten ausgenommen); Production-Docker nutzt `npm ci` (`frontend/Dockerfile:33`). |
| E2E/Node | `e2e/package.json`, `e2e/package-lock.json` | `@playwright/test` 1.61.1 im Lock; CI/Workflow nutzt dennoch `npm install` (`.github/workflows/playwright.yml:187-193`). |
| Hermes-TS-Plugin | `integrations/hermes-plugin/reqogniloom/package.json`, `integrations/hermes-plugin/reqogniloom/package-lock.json` | 139 Lock-Knoten, aber nur 93 `resolved`/`integrity`-Felder; `@hermes/plugin-sdk` ist extern und nicht als Paket/Lock-Eintrag deklarert. |
| Root-/Tooling-Node | `package.json`, `package-lock.json` | nur `headroom-ai` 0.22.4 im versionierten Root-Lock. |
| Agent-Meta | `.agent-meta/package.json`, `.agent-meta/requirements.txt`, `.agent-meta/tests/requirements.txt` | Submodul auf Commit `78d3a322…` (`v1.1.0`) gepinnt; Node-/Python-Bereiche ohne eigene Lockfiles. |
| Container/Compose | `backend/Dockerfile`, `frontend/Dockerfile`, `deploy/docker-compose*.yml` | App-Images nur Versionstag, Fremdimages teils `latest`; kein `FROM`-/Service-Digest. |
| MCP/Agent-Tools | `.mcp.json`, `opencode.json`, `e2e/package.json`, `.agent-meta/config/plugin-catalog.yaml` | `@playwright/mcp@latest` und `npx -y`; ProjectAtlas verlangt lokal `0.4.4`, andere lokale Binaries sind nicht versioniert. |
| Vendored/Generated | `frontend/public/bluepencil/**`, `deploy/bluepencil/**`, `dist/plugins/**` | Bluepencil-Browser alpha.2, Sidecar alpha.1; generierte Plugin-Bundles ohne SBOM/Hash-/Signatur-Nachweis. |

### 3.1 Nachgewiesene Drift zwischen Soll und Ist

- **Python:** Beispiele aus `backend/requirements.txt` gegenüber `backend/requirements.lock`: Django `>=6.1.1` vs. `6.1`; `psycopg2-binary>=2.9.13` vs. `2.9.12`; `reportlab>=5.0.1` vs. `4.5.1`; `anthropic>=1.5.0` vs. `0.125.0`; `openai>=3.6.0` vs. `1.109.1`; `sentence-transformers>=6.0.1` vs. `6.0.0`; `numpy>=2.5.3` vs. `2.5.2` (`backend/requirements.txt:39-171`, `backend/requirements.lock:33,87,103,110,127,135`).
- **Python-Index:** Die Lock-Reproduktion verwendet laut Header `pip-compile requirements.txt` ohne den CPU-PyTorch-Index (`backend/requirements.lock:14-28`), während der Docker-Build `--extra-index-url https://download.pytorch.org/whl/cpu` setzt (`backend/Dockerfile:31-51`). Der Lock enthält dennoch CUDA-/NVIDIA-Pakete (`backend/requirements.lock:88-102,143-146`); die Closure beschreibt damit nicht eindeutig das Produktionsimage.
- **Node:** Die versionierten Locks `frontend/package-lock.json` und `e2e/package-lock.json` sind die Referenzen für die kanonische Frontend-/E2E-Abhängigkeitssicht. Lokale Hidden-Lock-Zählungen und installierte Plattformbäume sind nicht versioniert, nicht reproduzierbar und daher keine kanonische Evidenz.
- **Dokumentation:** `AGENTS.md:7,15,34,59` beschreibt React 18/ESLint 9 und Django 5.2+, während `frontend/package.json:34-35,53-54` React 19/ESLint 10 und `backend/requirements.txt:39` Django 6.1 deklarieren. Das ist Stack-Drift, kein Beweis einer Laufzeitabweichung.

## 4. Lizenzmatrix und Lieferketten-Rechte

| Bereich | Beobachtete Lizenzangaben | Bewertung gegenüber Projekt-MIT |
|---|---|---|
| Projekt | MIT (`LICENSE:1-18`) | Ausgangsbasis. |
| Frontend npm | Überwiegend MIT/Apache-2.0/BSD/ISC; `axe-core` und `lightningcss` MPL-2.0 (`frontend/package-lock.json:2588-2594,6045-6051`), DOMPurify als `(MPL-2.0 OR Apache-2.0)` (`frontend/package-lock.json:3749-3754`), Fontsource OFL-1.1 (`frontend/package-lock.json:813-845`), `caniuse-lite` CC-BY-4.0 (`frontend/package-lock.json:2820-2839`), BlueOak/Unlicense-Ausdrücke. | Kein GPL/AGPL/LGPL im geprüften npm-Lock; MPL/OFL/CC-BY benötigen jedoch Notice-/Attribution- bzw. dateibezogene Review. |
| E2E npm | Apache-2.0 und MIT (`e2e/package-lock.json:15-20,56-60`). | Grundsätzlich kompatibel. |
| Python | `backend/requirements.lock` enthält keine Lizenzfelder; nur Kommentarhinweis für `reqif` (`backend/requirements.txt:126-128`). Registry-Spotchecks: `django-celery-beat` BSD, `honcho-ai` Apache-2.0. | Transitive Python-Lizenzclosure nicht vollständig belegt; keine rechtliche Freigabe ableitbar. |
| Agent-Meta | MIT-Lizenz im Submodul (`.agent-meta/LICENSE:1-21`), aber Tool-Abhängigkeiten ohne Lock-/Notice-Matrix. | Lizenz des Framements okay; Abhängigkeitsrechte nicht inventarisiert. |
| Bluepencil | Header der vendored Browserdateien: MIT; Sidecar-Header: MIT. | Lizenzangabe vorhanden, aber Herkunft/Hash gilt nicht für alle Dateien und Versionen. |
| Container-OS | Debian-/Alpine-Pakete werden per `apt-get upgrade`/`apk upgrade` verändert (`backend/Dockerfile:99-108`, `frontend/Dockerfile:46-53`). | Keine reproduzierbare OS-Lizenz-/Notice-Matrix im Repository. |

**Lizenzurteil:** Kein konkreter GPL/AGPL-Konflikt wurde aus den geprüften npm-Metadaten nachgewiesen. Das ist ausdrücklich **keine rechtliche Freigabe**. Die fehlende Third-Party-Notice-/SBOM-Matrix ist selbst ein Lieferkettenbefund.

## 5. Reifegrad der Release-Kontrollen

| Kontrolle | Aktueller Stand | Bewertung |
|---|---|---|
| Python-Installation | `pip install -r requirements.txt` in Docker und CI (`backend/Dockerfile:49-51`, `.github/workflows/ci.yml:98-100`) | offene Auflösung, nicht reproduzierbar. |
| Python-CVE-Gate | `pip-audit --desc` nach Installation (`.github/workflows/ci.yml:146-153`) | Scanner vorhanden, aber ohne Lock-/Artefaktbindung; Toolversion unpinned. |
| Node-Installation | Production `npm ci`, mehrere CI-/Testpfade `npm install` | uneinheitlich. |
| Image-Scan | Trivy im GHCR-Tag-Workflow (`.github/workflows/docker-publish.yml:142-154`) | vorhanden, aber Scan- und Push-Digest nicht nachweislich identisch. |
| SBOM/Provenance | kein explizites `sbom`-/`provenance`-Artefakt im GHCR-Workflow; Woodpecker setzt `provenance: false`, `sbom: false` (`.woodpecker.yml:123-127`) | Release-Nachweis fehlt. |
| Signierung | kein `cosign`-/`sigstore`-Schritt im Release-Workflow | nicht nachgewiesen. |
| Rollback | Version-/Commit-SHA-Tags in Compose/GitHub-Workflow, aber keine Image-Digest-Matrix | Tag-Rollback möglich, Digest-/SBOM-Rollback nicht abgesichert. |
| Aktualisierung | Dependabot deckt pip backend, npm frontend, Docker und Actions ab (`.github/dependabot.yml:3-33`) | E2E, Root, Hermes, Agent-Meta, MCP und externe Images fehlen. |

## 6. Befunde

### DEP-001 — Python-Lockfile ist stale, nicht autoritativ und indexinkonsistent

**Kategorie / Status:** Outdated/Drift — bestätigt  
**Prio:** P1  
**Evidenz:** `backend/requirements.txt:4-8,39-171`; `backend/requirements.lock:1-28,30-160`; `backend/Dockerfile:29-51`; `.github/workflows/ci.yml:98-100,146-153`; `backend/REGENERATING_LOCK_FILE.md:3-5`.  
**Auswirkung:** Docker, CI, lokale Entwicklung und eine lockbasierte SBOM-/CVE-Analyse können unterschiedliche Python-Closures prüfen. Ein Rollback auf den Lockzustand liefert nicht das aktuelle Produktionsimage; stale Pins können außerdem unterhalb der im Manifest geforderten Floors liegen.  
**Root Cause:** Der Lock ist ausdrücklich nur Dokumentation, wird nicht installiert, enthält keine Hashes und wurde am 2026-08-30 mit einer anderen Index-/Resolver-Konfiguration erzeugt als der Docker-Build.  
**Gegenmaßnahme:** Einen Linux/amd64-, CPython-3.12- und CPU-Torch-kompatiblen, hashgeschützten Lock als einzige Installationsquelle erzeugen; Docker und CI aus diesem Lock installieren; Lock-Drift/Hash-/Floor-Prüfung als Gate ausführen.  
**Aufwand:** M (2–5 Arbeitstage).  
**Alternativen:** Exakte Direktpins in `backend/requirements.txt` sind einfach, verlieren aber die vollständige Closure; `pip-compile`/`uv lock` mit gemeinsamem Index ist robuster.  
**Confidence:** Hoch (0.99).  
**Verifikationsplan:** In einem sauberen Linux-Container zweimal aus demselben Commit bauen; installierte Distributionen, `pip freeze`, Lock-Hashes und Image-SBOM vergleichen; alte Lock-Datei gegen die neuen Constraints prüfen.

### DEP-002 — Container- und Betriebssystem-Eingaben sind nicht digest-gepinnt

**Kategorie / Status:** Supply-Chain-/Release-Reproduzierbarkeit — bestätigt  
**Prio:** P1  
**Evidenz:** `backend/Dockerfile:8,63,99-108`; `frontend/Dockerfile:4,44,46-53`; `deploy/docker-compose.yml:77,140,189,613,655`; `deploy/docker-compose.yml:240,331,378,464,519`; `deploy/docker-compose.minimal.yml:46,78,117,169,203`. Kein `FROM ...@sha256` und kein Service-Digest.  
**Auswirkung:** Ein identischer Commit kann zu unterschiedlichen Images führen; Registry-Tag-Änderungen, Base-Image-Updates und `apt/apk upgrade` verändern Laufzeitinhalt und CVE-/Patchstand. Ein Release-Tag ist damit kein stabiler Rollback-Anker.  
**Root Cause:** Versions-Tags und bewusst zeitabhängige Systemupdates werden als Pinning behandelt; mutierbare `latest`-Images sind im Compose vorgesehen.  
**Gegenmaßnahme:** Alle `FROM`- und Compose-Images per Digest pinnen, `latest` entfernen, `apt/apk upgrade` durch reproduzierbare, versionierte Basis-Images ersetzen und Digest-/SBOM-Updates automatisierbar aber reviewbar machen.  
**Aufwand:** M (2–5 Arbeitstage).  
**Alternativen:** Nur unveränderliche Release-Tags sind schwächer als Digests; wöchentliche Rebuilds ersetzen keine Digest-Pinning.  
**Confidence:** Hoch (0.98).  
**Verifikationsplan:** `docker image inspect`/`RepoDigests` je Image speichern; zwei Builds ohne Netzänderung vergleichen; Compose-Config auf `latest`/unpinned Images prüfen.

### DEP-003 — Vulnerability-Scan, Push, SBOM und Signatur sind nicht digestgebunden

**Kategorie / Status:** Supply-Chain-/Release-Nachweis — bestätigte Kontrolllücke; CVE-Status nicht live verifiziert  
**Prio:** P1  
**Evidenz:** Erster `build-push-action` mit `load: true` in `.github/workflows/docker-publish.yml:98-112`; Trivy-Scan in `.github/workflows/docker-publish.yml:142-154`; separater Push-Build in `.github/workflows/docker-publish.yml:165-191`. `.woodpecker.yml:123-127` deaktiviert Provenance/SBOM ausdrücklich. In keinem Release-Workflow werden Digest, CycloneDX/SPDX-Artefakt, `cosign verify` oder eine signierte Provenance gespeichert.  
**Auswirkung:** Der gescannte Image-Stand ist nicht nachweisbar identisch mit dem gepushten Stand. Ohne SBOM/Attestation/Signatur kann ein Betreiber nicht belegen, welche exakten Komponenten und Quellstände ein Release-Tag enthält.  
**Root Cause:** Scan und Push sind zwei Build-Aufrufe; Tag-Referenzen werden nicht durch Digest-Referenzen ersetzt; Supply-Chain-Artefakte sind nicht Bestandteil des Release-Vertrags.  
**Gegenmaßnahme:** Einmal bauen, Image per Digest laden, genau diesen Digest scannen und pushen; SBOM und Provenance als Release-Asset veröffentlichen; digest-basiertes keyless `cosign sign`/Verify verpflichtend machen; unfixed-Policy explizit dokumentieren.  
**Aufwand:** L (ca. 1 Woche).  
**Alternativen:** Registry-Scan nach Push mit Digest-Abgleich ist einfacher, aber schwächer als Scan-before-push mit gebundenem Digest.  
**Confidence:** Hoch für die Bindungslücke (0.99), keine CVE-Aussage.  
**Verifikationsplan:** Scan-Report und GHCR-Manifest auf denselben `sha256`-Digest vergleichen; SBOM-Komponenten gegen Image-Inventar prüfen; `cosign verify` und Provenance-Prüfung als Release-Gate ausführen.

### DEP-004 — GitHub Actions und ad-hoc-Scanner sind nur über Tags bzw. ohne Version gepinnt

**Kategorie / Status:** Supply-Chain-Hygiene — bestätigt  
**Prio:** P2  
**Evidenz:** Actions in `.github/workflows/ci.yml:15-20,83-100,161-166,242-265,290-301` und `.github/workflows/docker-publish.yml:42-56,100-143,158-183` verwenden `@v…`/`@v0.36.0`, keine 40-stelligen SHAs. `pip install pip-audit` (`.github/workflows/ci.yml:146-152`), `pip install -q flake8 black isort` und `pip install -q safety` (`.woodpecker.yml:17-26,74-81`) sind offen. Der Action-Gate prüft bei Tags nur Existenz (`.agent-meta/.agents/hooks/release-gates/action-pin-validation.sh:50-76`).  
**Auswirkung:** Ein umgeleitetes/verschobenes Action-Tag oder eine neue Scanner-Version kann denselben Workflow-Revision ohne Commit-Änderung verändern; Scanergebnisse sind nicht stabil reproduzierbar.  
**Root Cause:** Komfort-Tags wurden als Pins akzeptiert; Scanner werden als Build-Tool ad hoc installiert.  
**Gegenmaßnahme:** Actions auf vollständige SHAs mit Versionskommentar umstellen; Scanner als versionierte, gehashte Tools/Container beziehen; Dependabot auf SHA-Updates konfigurieren.  
**Aufwand:** M (2–5 Arbeitstage).  
**Alternativen:** Dependabot-SHA-Updates sind langfristig die bessere Lösung; reine Tag-Aktualisierung reduziert nur die Änderungshäufigkeit.  
**Confidence:** Hoch (0.98).  
**Verifikationsplan:** Policy-Grep auf `@v`, `@latest` und offene Scannerinstallationen; Action-Gate mit absichtlich nicht existierendem SHA testen; Scanner-Versionen im SBOM/Run-Metadatum speichern.

### DEP-005 — MCP- und lokale Tooling-Abhängigkeiten umgehen Lockfiles

**Kategorie / Status:** Supply-Chain-/Reproduzierbarkeit — bestätigt  
**Prio:** P2  
**Evidenz:** `@playwright/mcp@latest` in `e2e/package.json:5-12`, `AGENTS.md:571-574`, `.mcp.json:3-10` und `opencode.json:16-25`; `npx -y @playwright/mcp@latest` lädt beim Aufruf. `.agent-meta/config/plugin-catalog.yaml:65-70,333-343` enthält zusätzlich ein unversioniertes, standardmäßig deaktiviertes InfluxDB-MCP. Der versionierte `e2e/package-lock.json:15-86` schreibt die E2E-Playwright-Version auf 1.61.1 fest. Nicht versionierte lokale `node_modules`-Beobachtungen werden nicht als Beleg verwendet. npm-Registry-Abruf am 2026-09-24: `@playwright/mcp` 0.0.82.  
**Auswirkung:** Ein MCP-/Tool-Update kann ohne Commit, Lockfile oder SBOM in Entwickler- und Agentenlaufzeiten gelangen; lokale `npx`-Auflösung kann eine andere Playwright-Version als der E2E-Lock wählen.  
**Root Cause:** Bequeme `npx`-Konfiguration umgeht den Lockfile-Vertrag. Lokale, ignorierte `node_modules`-Abweichungen sind nicht reproduzierbar und werden nicht als kanonische Evidenz behandelt.  
**Gegenmaßnahme:** MCP-/Agent-Tools in ein eigenes, gelocktes Tooling-Paket überführen; exakte Version plus Integrität/Container-Digest verwenden; E2E strikt mit lokalem `npm ci` und `node_modules/.bin` starten; unbenutzte dynamische MCPs deaktivieren.  
**Aufwand:** M (2–5 Arbeitstage).  
**Alternativen:** Auditiertes, digest-gepinntes MCP-Containerimage; bei reinen QS-Tools bleibt dynamisches `npx` vertretbar, muss aber aus dem Release-SBOM ausgeschlossen werden.  
**Confidence:** Hoch für die dynamische Konfiguration (0.97).  
**Verifikationsplan:** In sauberem Checkout mit deaktiviertem Registry-Zugriff alle MCP-/E2E-Kommandos starten; `npm ls --all` und SBOM gegen Manifest-/Lock-Soll vergleichen; unversionierte `npx`-Aufrufe als Gate ablehnen.

### DEP-006 — Hermes-Pluginvertrag ist extern, unpinned und ausdrücklich nicht live verifiziert

**Kategorie / Status:** Plugin-/Release-Reproduzierbarkeit — bestätigt  
**Prio:** P2  
**Evidenz:** `integrations/hermes-plugin/reqogniloom/package.json:13-29` deklariert `@hermes/plugin-sdk` nicht; `integrations/hermes-plugin/reqogniloom/vite.config.ts:18-24` externalisiert es zusammen mit React; `integrations/hermes-plugin/reqogniloom/hermes-plugin.json:40-46` verlangt nur Hermes `>=3.0.0`. `integrations/hermes-plugin/reqogniloom/src/hermes-sdk-types.ts:4-19` dokumentiert den SDK-Vertrag als unbestätigt. Das Python-POC `integrations/hermes-agent-plugin/README.md:7-23` ist nicht live verifiziert; `.github/workflows/ci.yml:284-319` testet nur den TS-Pfad.  
**Auswirkung:** Eine Hermes-/SDK-Version kann den Plugin-Load oder die registrierten APIs brechen, ohne dass das Repo eine kompatible Version oder einen Reproduktionstest besitzt. Die parallelen Plugin-Versionen (`1.8.0-beta.15` vs. `0.1.0`) erschweren Release-/Rollback-Zuordnung.  
**Root Cause:** Hostbereitgestellte Laufzeitabhängigkeiten und ein POC-Plugin werden als verteilbare Release-Artefakte behandelt.  
**Gegenmaßnahme:** Eine Variante als unterstützt auswählen, exakte Hermes-/SDK-Version und Compatibility-Matrix festhalten, beide Build-/Smoke-Tests in CI aufnehmen und dist-Artefakte mit Hash-/SBOM-Nachweis veröffentlichen.  
**Aufwand:** L (1 Woche oder mehr).  
**Alternativen:** POC ausdrücklich als nicht releasefähig markieren und nur Quellcode veröffentlichen; alternativ den Host-SDK als vendored, geprüftes Artefakt mitliefern.  
**Confidence:** Hoch (0.99).  
**Verifikationsplan:** In einer sauberen Hermes-Version den gebauten `dist/plugin.js` laden; Registrierungen/SDK-Version protokollieren; `npm ci` und Host-SDK gegen eine Pin-Matrix testen.

### DEP-007 — Bluepencil liefert Browser alpha.2 und Sidecar alpha.1 ohne einheitliche Integritätskette

**Kategorie / Status:** Vendored-Asset-/Supply-Chain-Integrität — bestätigte Cross-Version-Drift  
**Prio:** P2  
**Evidenz:** `deploy/bluepencil/README.md:178-195` dokumentiert ausdrücklich Browser-Assets alpha.2 und Sidecar alpha.1; `frontend/public/bluepencil/latest/latest.json:2-5` hasht nur das Element; `deploy/bluepencil/server.js:2` ist alpha.1, während `attach.js`/Element alpha.2 sind. `frontend/src/bluepencil/loader.ts:277-298` überspringt den Integritätscheck ohne WebCrypto; die Testfixture verwendet in `frontend/src/test/bluepencil-loader.test.ts:225-240` noch alpha.1.  
**Auswirkung:** Browser- und Serverprotokoll können auseinanderlaufen; ein unsicherer LAN-Origin lädt den Bundle-Satz ohne Hashprüfung. Der Sidecar-Hash ist nur dokumentarisch, nicht Teil eines ausführbaren Release-Gates.  
**Root Cause:** Browser-Assets und Sidecar wurden separat vendored; das Manifest deckt nicht alle ausführbaren Dateien ab.  
**Gegenmaßnahme:** Einen einheitlichen Bluepencil-Release-Stand auswählen, Hashes für `attach.js`, Element und `server.js` in einem signierten Manifest führen, Hash-/Protokollprüfung in CI erzwingen und Insecure-Origin entweder disallowen oder als nicht releasefähig markieren.  
**Aufwand:** S–M (1–3 Arbeitstage).  
**Alternativen:** Bluepencil vollständig aus Produktionsartefakten entfernen und nur als QS-Tool mit lokaler Prüfsumme ausliefern.  
**Confidence:** Hoch (0.99).  
**Verifikationsplan:** SHA-256 aller drei Dateien gegen ein gemeinsames Manifest prüfen; Alpha-1/Alpha-2-Health-/Bundle-Contract-Test ausführen; Build mit absichtlich falschem Hash muss fehlschlagen.

### DEP-008 — Lizenz-/Notice-Matrix ist unvollständig und nicht als Release-Gate gepflegt

**Kategorie / Status:** Lizenzkonflikt-Prüfbedarf — kein konkreter GPL/AGPL-Konflikt nachgewiesen  
**Prio:** P2  
**Evidenz:** Projekt-MIT in `LICENSE:1-18`; npm-Lock Lizenzfelder und Beispiele in `frontend/package-lock.json:813-845,2588-2594,3749-3754,6045-6051,2820-2839`; Python-Lock ohne Lizenzfelder (`backend/requirements.lock:1-164`); keine Root-`NOTICE`/`THIRD_PARTY_NOTICES` gefunden.  
**Auswirkung:** MPL-2.0-, OFL-1.1-, CC-BY-4.0- und Dual-License-Komponenten können Notice-/Attribution-/Source-Pflichten auslösen; transitive Python- und Container-OS-Lizenzen sind nicht release-fähig freigegeben.  
**Root Cause:** npm-Lock-Metadaten werden nicht in eine SBOM-/Notice-Pipeline überführt; Python- und Image-Komponenten werden nicht mit Lizenzfeldern erfasst.  
**Gegenmaßnahme:** CycloneDX/SPDX-SBOM mit SPDX-Lizenzfeldern, `THIRD_PARTY_NOTICES`, Allowlist und CI-Scan für npm wheels, PyPI-Wheels und Container-OS erzeugen; MPL/OFL/CC-BY/Composite-Ausdrücke rechtlich prüfen.  
**Aufwand:** M (2–5 Arbeitstage).  
**Alternativen:** MPL-/CC-BY-/OFL-Abhängigkeiten durch permissive Ersatzpakete ersetzen oder Source-/Notice-Pakete pro Release veröffentlichen.  
**Confidence:** Hoch für die Evidenzlücke (0.98), keine Aussage über endgültige Lizenzkonformität.  
**Verifikationsplan:** SBOM-Lizenzfelder gegen installierte METADATA und Paketlizenzdateien abgleichen; Notice-Dateien in beide Containerstufen kopieren; Lizenz-Allowlist als Release-Gate ausführen.

### DEP-009 — Temporärer Git-Pin für `django-celery-beat` ist kein release-geprüftes PyPI-Artefakt

**Kategorie / Status:** Supply-Chain-/VCS-Abhängigkeit — bestätigt, nicht deprecated behauptet  
**Prio:** P2  
**Evidenz:** `backend/requirements.txt:55-70` und `backend/requirements.lock:54` verwenden `git+https://...@6767df6…`; Docker braucht dafür `git` (`backend/Dockerfile:16-27`). PyPI 2.9.0 verlangt weiterhin `Django<6.1`, Issue #1079 ist offen; der geprüfte Commit-Raw-Stand verlangt `Django>=3.2.25,<6.2`.  
**Auswirkung:** Build und SBOM hängen an Git-Transport und einem nicht veröffentlichten Commit statt an einem versionierten, gehashten PyPI-Artefakt. Upstream-/Netzwerkänderungen oder ein nicht reproduzierbarer Checkout beeinflussen Release und Rollback.  
**Root Cause:** Django-6.1-Kompatibilität ist upstream noch nicht als Release verfügbar.  
**Gegenmaßnahme:** Auf eine signierte/hashgeschützte Wheel-/sdist-Veröffentlichung warten; interimär Commit-Archiv mit fester SHA-256/Signatur und Offline-Mirror pflegen; nach Release auf PyPI-Pin umstellen.  
**Aufwand:** M (2–5 Arbeitstage).  
**Alternativen:** Bis zur Veröffentlichung Django-5.2-LTS verwenden, sofern produktlich akzeptiert; oder einen intern gepflegten, reviewten Fork als Übergang veröffentlichen.  
**Confidence:** Hoch (0.97).  
**Verifikationsplan:** Commit-/Archivhash im Build protokollieren, PyPI-Release-Metadaten beobachten, `pip-audit`/SBOM gegen das tatsächlich installierte Artefakt ausführen.

### DEP-010 — `honcho-ai==2.3.0` ist gegenüber dem aktuellen PyPI-Stand veraltet

**Kategorie / Status:** Outdated/Drift — bestätigt; keine CVE-/Vulnerability-Aussage  
**Prio:** P2  
**Evidenz:** `backend/requirements.txt:159-171` pinnt 2.3.0 und behauptet, dies sei die höchste veröffentlichte Version; offizielles PyPI weist am 2026-09-24 2.5.0 aus (veröffentlicht 2026-09-17, Apache-2.0). Lock ebenfalls `2.3.0` (`backend/requirements.lock:66`).  
**Auswirkung:** Der optionale Memory-Backend-Pfad bleibt auf einem älften SDK; API-/Fix-/Kompatibilitätsdrift zwischen Client und Container wird erst beim Wechsel sichtbar.  
**Root Cause:** Kompatibilitätsfix ist als dauerhafte, nicht überprüfte Versionsentscheidung dokumentiert.  
**Gegenmaßnahme:** 2.5.0 in einer isolierten Umgebung gegen `backend/memory/honcho_backend.py` und die Memory-Tests prüfen; danach aktualisieren oder begründete Ausnahme mit Owner/Ablaufdatum dokumentieren.  
**Aufwand:** S–M (1–3 Arbeitstage).  
**Alternativen:** 2.3.0 behalten, aber gegen 2.5.0 Changelog/API-Diff und einen datierten Security-Review dokumentieren.  
**Confidence:** Hoch für Versionsdrift (0.99), Auswirkungs-Confidence mittel bis hoch.  
**Verifikationsplan:** Kandidaten-Version in Clean-Room installieren, Import-/Memory-Tests und Honcho-Container-Contract ausführen; keine CVE-Aussage ohne separaten Advisory-Lauf.

### DEP-011 — Tooling- und Agent-Meta-Abhängigkeiten besitzen keine eigene Lock-/Provenienzschicht

**Kategorie / Status:** Outdated/Tooling-Drift — bestätigt, begrenzte Reichweite  
**Prio:** P3  
**Evidenz:** `.agent-meta/package.json:1-4` nutzt `@opencode-ai/models:^0.0.19` ohne Lock; `.agent-meta/requirements.txt:1` und `.agent-meta/tests/requirements.txt:4-8` sind offene Bereiche. Root-`package.json:1-4`/`package-lock.json:11-15` pinnen `headroom-ai` 0.22.4; npm weist am 2026-09-24 0.38.0 aus.  
**Auswirkung:** Agent-/Hook- und lokale Kontext-Tools können zwischen Rechnern und Release-Zeitpunkten unterschiedlich laufen; die Abweichung ist außerhalb des Produktions-App-Images, aber ein relevanter Reproduzierbarkeits- und Supportfaktor.  
**Root Cause:** Tooling wurde bewusst außerhalb der App-Lockfiles gehalten, ohne eigene Provenienz-/Update-Pipeline.  
**Gegenmaßnahme:** Eigenes Tooling-Lockfile, Version-Update-PRs und dokumentierte Ausnahmen einführen; nicht benötigte Root-Tools aus dem Release-Artefakt entfernen.  
**Aufwand:** S (bis 1 Arbeitstag).  
**Alternativen:** Tooling außerhalb des Release-SBOM bewusst als Nicht-Produktionsabhängigkeit klassifizieren und nur versionsdocumentiert installieren.  
**Confidence:** Hoch für Pin-/Locklücke (0.98), Auswirkungs-Confidence mittel.  
**Verifikationsplan:** Tooling in frischer virtueller Umgebung installieren, `npm ci`/Python-Resolver-Output und Agent-Meta-Submodul-Commit protokollieren.

### DEP-012 — Dependabot-/SBOM-Abdeckung und lokale Plattformtrees sind unvollständig

**Kategorie / Status:** Supply-Chain-Hygiene/Drift — bestätigt  
**Prio:** P2  
**Evidenz:** `.github/dependabot.yml:3-33` deckt nur `/backend` pip, `/frontend` npm, Docker-Root und GitHub Actions ab; CI-Scans `pip-audit`/`npm audit` nur für Backend/Frontend (`.github/workflows/ci.yml:146-153,277-282`). E2E, Root, Hermes, Agent-Meta und MCP fehlen. Lokale Hidden-Lock-Zählungen und nicht versionierte Root-Playwright-Dateien werden nicht als kanonische Evidenz verwendet.  
**Auswirkung:** Nicht überwachte Abhängigkeiten können veralten oder schwachstellenrelevant werden; lokale SBOMs sind plattformabhängig und nicht direkt mit dem Release vergleichbar.  
**Root Cause:** Keine zentrale Dependency-Inventarliste über alle Manifest- und Tooling-Flächen; plattformabhängige optionale Pakete werden nicht als normalisierter Release-SBOM behandelt.  
**Gegenmaßnahme:** Dependabot/Renovate-Einträge für alle Flächen, zentralen SBOM-Diff und getrennte Linux-/Windows-Metrik ergänzen; ungenutzte Root-Tools und inaktive externe Registry-Einträge explizit quarantänisieren.  
**Aufwand:** S–M (1–3 Arbeitstage).  
**Alternativen:** Zentraler Monorepo-/Workspace-Lock oder wöchentlicher OSV-/Trivy-Gesamtscan.  
**Confidence:** Hoch (0.96).  
**Verifikationsplan:** Manifest-Inventar gegen Dependabot- und CI-Matrix prüfen; SBOM auf Linux-Build gegen normalisierten Soll-Satz vergleichen; jede Abweichung als Plattformfilter oder echte Drift klassifizieren.

## 7. Positive Befunde und vorhandene Paved Roads

- Das Root-Projekt und Agent-Meta besitzen eine MIT-Lizenz; der Agent-Meta-Submodul-Gitlink ist auf `78d3a322…`/`v1.1.0` gepinnt und im Working Tree sauber.
- Frontend-, E2E- und Root-npm-Locks enthalten grundsätzlich `resolved`- und `integrity`-Angaben; der Production-Frontend-Build verwendet `npm ci`.
- `backend/requirements.lock` ist immerhin als Linux/CPython-3.12-Dokumentation mit Provenienzheader vorhanden, auch wenn er derzeit nicht autoritativ ist.
- Der GHCR-Workflow führt Trivy vor dem Push aus; der aktuelle Release-Bericht dokumentiert einen erfolgreichen Tag-Run (`docs/se/reports/RELEASE_v1.8.0-beta.15.md:182-220`). Das ist historische Release-Evidenz, kein Ersatz für einen archivierten Digest/SBOM-Nachweis.
- Bluepencil dokumentiert Hash und Herkunft des Browser-Assets; der Sidecar importiert ausschließlich Node-Built-ins.
- Ein kuratierter `django-celery-beat`-Commit ist immerhin exakt statt eines beweglichen Branches referenziert.

## 8. Priorisierte Maßnahmen

1. **Sofort (P1):** Python-Lock als installierte, hashgeschützte, indexgleiche Quelle herstellen; lockbasierte SBOM/CVE-Prüfung auf das Produktionsimage anwenden.
2. **Vor nächstem Release (P1):** Images und Actions per Digest/SHA pinnen; einmal bauen, Digest scannen, denselben Digest pushen, SBOM/Provenance erzeugen und signieren.
3. **Danach (P2):** MCP-/Plugin-/Bluepencil-Provenienz schließen, Third-Party-Notices erzeugen und die Lizenz-/SBOM-Matrix als Gate verpflichtend machen.
4. **laufend (P2/P3):** E2E-, Root-, Hermes-, Agent-Meta- und MCP-Abhängigkeiten in Update-/Scan-Scope aufnehmen; `honcho-ai` und `headroom-ai` nur nach dokumentiertem Compatibility-Test aktualisieren.

## 9. Verifikations- und Restrisiko-Plan

Da in diesem Audit keine CVE-Datenbank und keine Scanner ausgeführt wurden, ist vor einem Release Folgendes durchzuführen und als Artefakt zu archivieren:

1. Clean-Room-Auflösung von `backend/requirements.lock` und allen npm-Locks auf Linux/amd64; `pip-audit`, `npm audit --package-lock-only`, OSV-Scanner und Trivy/Syft mit fest gepinnten Toolversionen ausführen.
2. SBOM im CycloneDX- oder SPDX-Format erzeugen; Python-Wheel-Metadaten, npm-Lizenzfelder, Container-OS-Pakete, Bluepencil-Dateien, Agent-Meta-Submodul und externe Images zusammenführen.
3. Trivy-/OSV-Ergebnisse ohne Fix und Scanner-Ausnahmen explizit ausweisen; keine CVE- oder Deprecated-Behauptung allein aus Kommentaren ableiten.
4. Release-Image per Registry-Digest identifizieren, SBOM/Provenance/Cosign-Signatur daran binden und Rollback durch Deployments desselben Digests testen.
5. Hermes-/MCP-/Bluepencil-Kompatibilität in einer sauberen Zielumgebung testen; lokale, nicht versionierte `node_modules` nicht als reproduzierbare Release-Evidenz verwenden.

**Restrisiko:** Bis zur Umsetzung sind Python- und Image-Release-Inputs nicht vollständig reproduzierbar; ein bestehendes Trivy-GREEN beweist nicht die Integrität des tatsächlich gepushten Images. Die priorisierte P1-Maßnahme ist die digest- und lockgebundene Release-Kette.

```text
STATUS: done
RESULT: Statischer Deep-Audit abgeschlossen; 0 P0, 3 P1, 8 P2 und 1 P3 belegt. Höchste Risiken sind stale/nicht verwendete Python-Locks, mutierbare Container-/Action-Eingaben sowie nicht digestgebundener Scan/Push ohne archivierte SBOM-/Signatur-Provenienz; CVE-Status ausdrücklich nicht live verifiziert.
ARTIFACTS: docs/se/reports/deep_audit/system-audit-2026-09/10-dependencies-supply-chain-and-release.md
NEXT: [Developer: Python-Lock/Hash-/Index-Gate, Release: Digest-/SBOM-/Cosign-Pipeline, Developer: MCP-/Plugin-/Lizenz-Matrix schließen]
```
