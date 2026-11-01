# Umsetzungsplan: OpenCode V1 + V2 parallel unterstützen

> Stand: 2026-11-01 · Status: Entwurf, nicht freigegeben · Branch-Vorschlag: `feat/opencode-v2-support`
> Quellen: [Migrationsguide](https://opencode.ai/v2/docs/migrate-v1), [MCP-Seite V2](https://opencode.ai/v2/docs/mcp-servers), [Skills-Seite V2](https://opencode.ai/v2/docs/skills)

## 1. Ziel und Nicht-Ziele

**Ziel:** ReqogniLoom verbindet sich mit OpenCode V1 (heute `1.18.x`) **und** OpenCode V2 (Beta). V2 ist die Zukunft, V1 bleibt Übergang. Installer, Snippets, Doku und Tests decken beide ab.

**Nicht-Ziele:**
- Kein Plugin-Code. Unser Paket liefert bewusst nur Config + Skills; V1-Plugins laufen in V2 nicht, also entfällt die Plugin-Migration komplett.
- Keine Änderung am LLM-Provider `opencode_go` (anderes Thema, nicht der Client).
- Kein Entfernen von V1, solange V2 Beta ist.

## 2. Befund (Ist gegen V2-Doku)

| # | Thema | V1 (heute) | V2 laut Doku | Wirkung auf uns |
|---|---|---|---|---|
| F1 | Remote-Transport | `/mcp/sse/` (SSE) | nur **Streamable HTTP** dokumentiert, SSE nicht erwähnt | **Blocker-Risiko.** Server kann `/mcp/` bereits. |
| F2 | OAuth | nicht relevant | **an per Default**, `oauth:false` nötig für Header-Auth | ohne Flag evtl. OAuth-Flow statt API-Key |
| F3 | Config-Form | `mcp.<name>` | `mcp.servers.<name>`; V1-Form „läuft weiter", Mischen pro Eintrag nicht | zwei Snippets oder bewusst V1-Form |
| F4 | Code Mode | n/a | **Default an**, Tools heißen `<server>_<tool>`, Zugriff über Katalog | Skills/Doku nennen evtl. falsche Tool-Namen |
| F5 | `enabled` | `enabled` | `disabled` (invers) | wir setzen keins, kein Aufwand |
| F6 | Skills | `~/.config/opencode/skills`, `.opencode/skills` | gleich, plus `~/.claude/skills`, `~/.agents/skills`; `skills`-Array statt `paths`/`urls` | Layout unverändert, Prüfung reicht |
| F7 | `mcp add/list` | genutzt | `mcp add <name> --url … [--header …]`, `mcp list` dokumentiert, **kein `--oauth`-Flag** | Installer kann `oauth:false` evtl. nicht setzen |
| F8 | Binary-Name | `opencode` | **widersprüchlich**: Migrationsseite „beide `opencode`", Drittquelle „`opencode2` parallel" | Installer/Verify müssen beides können |
| F9 | Stabilität | stabil | Beta, „Daten können gelöscht werden", Server-/Plugin-API ändern sich | V2 als **Beta-Support** labeln |

Code-Stellen, die betroffen sind:
`clients/registry.yaml` (Eintrag `opencode`, Z. 271–340), `scripts/clients/render.py` (`CLIENT_IDS`),
`scripts/clients/install.sh` (`install_opencode`, Z. 209), `scripts/clients/verify.sh` (Z. 52),
`dist/opencode/build_opencode_package.py` (Snippet-Generator), `dist/opencode/opencode.json.snippet`,
`docs/clients/opencode{,.de}.md` (generiert), `scripts/clients/test_render.py`,
`dist/opencode/test_build_opencode_package.py`, `.github/workflows/client-smoke.yml`,
`.github/workflows/release-client-artifacts.yml` (Z. 101, Tarball).

## 3. Entwurf der Lösung

**Leitlinie:** ein Server-Endpunkt, zwei Config-Varianten, Version wird im Installer erkannt.

1. **Transport auf Streamable HTTP `/mcp/` umstellen** für OpenCode, wenn Phase 0 bestätigt, dass auch V1 das nativ spricht. Das ist die kleinste Lösung: ein Endpunkt für beide Versionen, und es folgt der eigenen Registry-Regel „Streamable HTTP bevorzugen, wenn der Client es nativ kann". Fällt Phase 0 negativ aus (V1 spricht kein Streamable HTTP), bleibt V1 auf SSE und V2 geht auf `/mcp/` — dann zwei Transporte pro Client-Eintrag.
2. **Zwei Snippets** statt einem gemischten:
   - `opencode.json.snippet` (V1, unverändert bis auf ggf. URL),
   - `opencode.v2.json.snippet` (`mcp.servers.reqogniloom`, `oauth:false`, `codemode` laut Entscheidung D2).
3. **Installer erkennt die Version** (`opencode --version`, Major-Nummer) und wählt Pfad V1 oder V2. Für V2 schreibt der Installer das Snippet per JSON-Merge in die Config, falls `mcp add` kein `oauth:false` setzen kann (F7).
4. **Eigener Registry-Eintrag `opencode-v2`** neben `opencode` (statt `variants`). Der Renderer iteriert schon über `registry["clients"]`, es entstehen eigene Doku-Seiten und eine eigene Matrix-Zeile ohne Renderer-Umbau. (Entscheidung im Plan `docs/superpowers/plans/2026-11-01-opencode-v2-support.md`, ersetzt die frühere `variants`-Idee.)

## 4. Phasen

### Phase 0 — Spike in Isolation (ohne Repo-Änderung, ~½ Tag)

Ziel: die offenen Fragen F1, F2, F4, F7, F8 mit Beweisen beantworten, bevor Code entsteht.

- V2 in einem Wegwerf-Prefix installieren (`HOME`, `XDG_CONFIG_HOME`, `XDG_DATA_HOME` auf ein Scratch-Verzeichnis), **ohne** die lokale V1-Installation anzufassen (`~/.config/opencode` enthält Backups und `server.env`, nicht berühren).
- Test-Matrix gegen eine laufende ReqogniLoom-Instanz mit gültigem `reqlo_`-Key:

| Test | V1 | V2 |
|---|---|---|
| `mcp add` gegen `/mcp/` | ? | ? |
| `mcp add` gegen `/mcp/sse/` | ✔ (bekannt) | ? |
| `mcp list` zeigt „connected" | ✔ | ? |
| Header-Auth ohne OAuth-Aufforderung | ✔ | ? (`oauth:false`) |
| Echter Tool-Call `requirement_query` | ✔ | ? |
| Tool-Namen mit/ohne Code Mode | n/a | ? (`codemode` an/aus) |
| Binary-Name | `opencode` | `opencode` oder `opencode2`? |

- Ergebnis als kurzer Bericht `docs/test-reports/opencode-v2-spike.md`. **Entscheidungsgate:** erst danach Phase 1 starten und D1/D2 festziehen.

### Phase 1 — Registry und Renderer

- `clients/registry.yaml`: neuer Eintrag `opencode-v2` (`status: beta`, eigener `tested_version`); `render.py` bleibt unverändert bis auf `CLIENT_IDS`.
- Tests: `test_render.py` bleibt grün, `CLIENT_IDS` enthält `opencode-v2`.

### Phase 2 — Snippet-Builder

- `dist/opencode/build_opencode_package.py`: zweites Snippet `opencode.v2.json.snippet` erzeugen; Funktion bleibt deterministisch.
- `dist/opencode/test_build_opencode_package.py`: Test auf beide Dateien plus Gleichheit mit dem eingecheckten Stand.
- `release-client-artifacts.yml` (Z. 101): Tarball um das V2-Snippet erweitern.

### Phase 3 — Installer und Verify

- `install.sh`: `install_opencode` teilt sich in `detect_opencode_major`, `install_opencode_v1`, `install_opencode_v2`. Neue Option `--opencode-major 1|2` als Override für den Fall, dass die Erkennung (F8) scheitert.
- Binary-Suche: zuerst `opencode`, dann `opencode2`; die gewählte Variante wird ausgegeben.
- V2-Pfad: `mcp add` falls Phase 0 zeigt, dass es `oauth:false` erlaubt, sonst atomarer JSON-Merge mit Backup (`backup_file` existiert bereits im Skript) in `~/.config/opencode/opencode.json`. Nie einen Key ins File schreiben, nur `{env:…}`-Platzhalter.
- `--dry-run` muss beide Pfade abdecken.
- `verify.sh`: gleiche Versionserkennung, `mcp list` plus Hinweis auf Beta bei V2.

### Phase 4 — Skills und Tool-Namen (F4, F6)

- Prüfen, ob `dist/opencode/skills/*/SKILL.md` Tool-Namen wörtlich nennen (`requirement_query` usw.). Wenn Code Mode aktiv bleibt, brauchen V2-Nutzer den Namen `reqogniloom_<tool>` bzw. Katalogzugriff.
- Je nach D2: entweder `codemode:false` im V2-Snippet (Tools direkt sichtbar, Skills bleiben gültig) oder Skills um einen kurzen V2-Hinweis ergänzen.
- Skill-Frontmatter gegen V2-Regeln prüfen (`description` Pflicht, sonst nicht beworben). Erwartet: nur Kontrolle, keine Änderung.

### Phase 5 — Doku, Docs-Generierung, CI

- `python scripts/clients/render.py` ausführen, generierte `docs/clients/opencode*.md` und `docs/clients/README*.md` committen (nie von Hand editieren, das schlägt `client-artifacts-check.yml` an).
- `docs/clients/README*.md` Tabelle: OpenCode → „V1: …, V2 (Beta): …".
- `CHANGELOG.md` und `docs/agent-templates/INSTALL.md` (enthält schon einen historischen OpenCode-Widerspruch) abgleichen.
- `client-smoke.yml`: Matrix um `opencode-v2` erweitern, als `continue-on-error` markiert, solange V2 Beta ist.

### Phase 6 — Abnahme

- Alle `scripts/clients`-Tests und `dist/opencode`-Tests grün (`pytest scripts/clients dist/opencode`).
- Manueller End-to-End in Isolation: Installer V1, Installer V2, jeweils `verify.sh` und ein echter `requirement_query` (erwartet laut Registry: 49 Requirements in der Test-Instanz).
- Drift-Gate: `render.py --check` grün.

## 5. Entscheidungen (vom Auftraggeber)

| ID | Frage | Empfehlung |
|---|---|---|
| D1 | Beide Versionen auf `/mcp/` (Streamable HTTP) oder V1 bei SSE lassen? | `/mcp/` für beide, **falls** Phase 0 V1-Support bestätigt (ein Endpunkt, weniger Pflege). |
| D2 | V2 mit `codemode:false` ausliefern oder Code Mode lassen? | `codemode:false`. Unsere 248 Tools sind für Code Mode ein großer Katalog, und die Skills bleiben unverändert gültig. Erst Phase 0 prüfen. |
| D3 | Neue Config-Form `mcp.servers` oder V1-Form auch in V2? | `mcp.servers` in der V2-Variante, damit wir nicht von einer Toleranz-Aussage der Beta abhängen. |
| D4 | Support-Stufe V2 | `beta`, L3-Ziel nach Stabilisierung; kein Gate für Releases, solange V2 Beta ist. |

## 6. Risiken

| Risiko | Wirkung | Gegenmaßnahme |
|---|---|---|
| V2 ändert sich noch (Beta) | Snippet veraltet | `tested_version` je Variante, Smoke-Job `continue-on-error`, Abgleich bei jedem OpenCode-Minor |
| Binary-Name unklar (F8) | Installer findet V2 nicht | Doppelsuche `opencode`/`opencode2`, Override-Flag |
| Installer überschreibt bestehende `opencode.json` | Datenverlust beim Nutzer | Backup vor Merge, Merge nur für den Schlüssel `reqogniloom`, `--dry-run` zeigt Diff |
| `oauth:false` fehlt bei `mcp add` | V2 startet OAuth-Flow, Auth schlägt fehl | JSON-Merge-Pfad (Phase 3) |
| Annahmen aus Doku, nicht aus Lauf | Plan trifft nicht zu | Phase 0 ist Gate; Plan nach Spike aktualisieren |

## 7. Aufwand und Reihenfolge

Phase 0 (½ T) → Gate → Phasen 1+2 (½ T) → Phase 3 (1 T) → Phase 4 (½ T) → Phase 5 (½ T) → Phase 6 (½ T). Gesamt grob **3–3,5 Tage**, davon der größte Unsicherheitsblock in Phase 0 und 3.

## 8. Nicht geprüft

- Die V2-Doku wurde gelesen, nicht ausgeführt. Alle Aussagen zu F1, F2, F4, F7, F8 sind Doku-Stand, nicht Laufzeitbeweis.
- Ob V1 `1.18.x` Streamable HTTP für Remote-Server nativ spricht, ist nicht belegt (Phase 0).
- Die Seite „Plugins migrieren" wurde nicht gelesen, weil wir keinen Plugin-Code ausliefern.
