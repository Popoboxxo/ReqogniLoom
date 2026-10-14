---
title: Bugfix- & Feature-Runde 4 — Umsetzungsplan (beta.20-Nachmeldung, Welle 2)
date: 2026-10-14
branch_base: origin/main @ 3c79adcc (nach Runde-3-Merge: W1/W2/D1/W3/W4/W5/W6)
author_agent: orchestrator
status: proposed
scope: 22 neue beta.20-Issues (#1277–#1302) in 5 Wellen + Entscheidungs-/Housekeeping-Spur
---

# Bugfix- & Feature-Runde 4 — Umsetzungsplan

> **Status:** `proposed` — dieser Plan implementiert nichts. Er beschreibt Paket,
> Reihenfolge, Wellen und Akzeptanzkriterien.
>
> **Faktenbasis:** Die Issue-Analysen der beta.20-QA/UI-Audits sind bereits sehr detailliert
> (mit `file:line`); in dieser Session wurden die folgenschwersten Befunde **im Repo
> gegengeprüft** (`origin/main @ 3c79adcc`). Angaben aus Issues sind als „laut Issue" markiert,
> eigene Verifikation als „**verifiziert**".
>
> **Abgrenzung zur Runde 3** (`docs/audit/2026-10/bugfix-round-3-plan.md`): Runde 3 ist
> **vollständig umgesetzt und gemergt** (W1 #1294, W2 #1297, D1 #1298, W3 #1299, W4 #1303,
> W5 #1304, W6 #1305). Dieser Plan arbeitet den **danach gemeldeten** beta.20-Batch
> (#1277–#1302) plus die offenen Residuen ab.

---

## 0. Ausgangslage

| Aspekt | Wert |
|---|---|
| `origin/main` | `3c79adcc` |
| Gemergt in Runde 3 | 7 PRs, Issues #1239/#1256/#1252/#1255, #1264/#1253/#1259/#1258/#1254, #1270/#1261, #1267/#1268/#1269/#1262, #1247/#1248/#1249/#1250/#1251, #1240/#1241/#1242/#1243/#1244/#1245 |
| Neue Issues (#1277–#1302) | **22** (2026-10-13, beta.20) |
| Themen | Memory/MCP, UI/A11y-Konsistenz, SE-Datenmodell, Repo/Plugin/Doku, BluePencil-Features |
| Offene Residuen | D4 (nicht ausgeführt), #1275 (ADR-ii + 2FA), `interface_coverage`-Metric, `test-results/`-CI-Ablageort, #1153 (vendor), #1258-Vollausbau, REST-`TestRunViewSet`-Write |

**Wichtiger Vorab-Befund (verifiziert):** Mehrere Sachverhalte aus Runde 3 wirken bereits in
den neu gemeldeten Batch hinein:
- **#1281** („`/attributes` verwaist, nicht in der Navigation") ist durch **W2/PR #1297**
  teilweise **behoben** — `SidebarNavigation.tsx:130` trägt jetzt den Eintrag `nav.attributeCatalog`
  auf `/attributes`. Offen bleibt nur der fehlende `<h1>`/die Seitenstruktur.
- **#1279** („`nav` hat `overflow-y: hidden`") — in der aktuellen `SidebarNavigation.module.css:103-104`
  steht **`overflow-x: hidden; overflow-y: auto`** (mit erklärendem Kommentar). Der Befund ist
  damit **zu re-verifizieren**, bevor er als Bug eingeplant wird.

---

## 1. Inventar der neuen Issues

| # | Sev | Track | Kurz | Welle |
|---|---|---|---|---|
| 1290 | MED | MCP | 10 Tools melden `An internal error occurred.` statt `not found` | W7a |
| 1301 | MED | MCP | `memory.promote` fehlt (UI/REST vorhanden) | W7a |
| 1302 | MED | MCP | Memory-MCP deckt 6 REST-Fähigkeiten nicht ab | W7a |
| 1291 | MED | API | Memory hat keinen REST-Schreibpfad (nur MCP) | W7b |
| 1300 | HIGH | MEMORY | Lern-Kreislauf nur auf Interviews beschränkt | W7b |
| 1295 | MED | MEMORY/UI | Scope heißt „Team", Workspace-Name nicht sichtbar | W7c |
| 1296 | MED | MEMORY/UI | Fehler auf `/memory` — Frontend-Repro offen | W7c |
| 1286 | MED | SETTINGS | Honcho-Konfiguration unvollständig | W7c |
| 1277 | MED | UI/i18n | Zwei komplett englische Tabs auf `/settings` (de) | W8a |
| 1280 | MED | UI/A11y | WCAG-Kontrast unterschritten (KPI, `/audit`) | W8a |
| 1278 | MED | UI/A11y | Fokus-Rückgabe nach ESC fehlt auf 3 Routen | W8b |
| 1282 | MED | UI | `/baselines` legt inline an; kein Längenfeedback | W8b |
| 1279 | MED | UI | Sidebar bei 1366×768 abgeschnitten (**re-verifizieren**) | W8b |
| 1281 | MED | UI | `/attributes` ohne `h1` (**Nav-Teil durch W2 erledigt**) | W8b |
| 1289 | HIGH | SE | V-Modell-Ebene ist NULL-Feld ohne Ableitung | W9a |
| 1288 | HIGH | SE/Feature | `acceptance_criteria` braucht strukturierten Feld-Typ | W9b |
| 1290/1292 | LOW/MED | MCP | doppelte MCP-Route + Key im `Authorization`-Header | W10 |
| 1293 | MED | DOCS | Doku-Audit: 12 kaputte Anweisungen, 16 Lücken | W10 |
| 1283/1284/1285 | MED | PLUGIN/REPO | Hermes-Plugin-Drift (Quelle entfernt, Versionsdrift, Doku) | W10 |
| 1257/1260/1263/1265/1266 | — | FEATURE | BluePencil-Features (Anzeige-, Attribut-, Statistik-, Glossar-Konfiguration) | W11 |

---

## 2. Wellen

Jede Welle ist unabhängig shippbar, eigener `fix/*`-Branch off `origin/main`, kein Commit auf
`main`. Bündelung nach **geteilter Komponente** (holistisch).

### W7 — Memory & MCP (größter Block)

| Teil | Inhalt | Ziel |
|---|---|---|
| **W7a — MCP-Exposition/-Fehler** | **#1290** (NotFound einheitlich), **#1301** (`memory.promote`), **#1302** (6 fehlende Memory-Tools + Drift-Test) | Die MCP-Oberfläche an die REST-Fähigkeiten angleichen und Fehler ehrlich machen. |
| **W7b — Schreiben & Lernen** | **#1291** (REST-Schreibpfad *oder* dokumentierte MCP-Only-Entscheidung), **#1300** (`INTERACTION_COMPLETED` + `memory.remember_interaction`) | Das Gedächtnis tatsächlich füttern — **nach** #1248 (Scope ist in #1304 gemergt). |
| **W7c — UI & Kopplung** | **#1295** (Terminologie + Workspace-Name), **#1296** (Fehler sichtbar/zuordbar), **#1286** (Honcho-Settings) | Die Memory-Oberfläche verständlich und diagnostizierbar machen. |

**Risiko:** #1300 ist verhaltens- und kostenrelevant (Konsolidierung = LLM + Embedding).
**Gegenmaßnahme:** neuer Event nur bei **bestätigten** Schritten; Informationsgehalt-Filter;
Counter `memory_consolidations_total` je Quelle. #1291 ist eine **Entscheidung** (REST-Write ja/nein).

### W8 — UI-/A11y-Konsistenz

| Teil | Inhalt | Ziel |
|---|---|---|
| **W8a** | **#1277** (i18n-Restlücken + i18n-Ratchet), **#1280** (Kontrast + Kontrast-Ratchet) | Sprache & Kontrast systemweit über Tokens/Katalog. |
| **W8b** | **#1278** (Fokus-Rückgabe), **#1282** (Dialog-Konvention + `maxlength`-Feedback), **#1279** (Sidebar-Scroll, re-verifizieren), **#1281** (`h1`) | Ein Dialog-/Fokus-Standard und erreichbare Navigation. |

**Risiko:** mittel (viele Routen). Gegenmaßnahme: **ein** gemeinsamer Dialog-Wrapper + Ratchet-Tests
(Dialog-Muster, Kontrast, i18n), damit keine Route mehr aus dem Muster fällt.

### W9 — SE-Datenmodell

| Teil | Inhalt | Ziel |
|---|---|---|
| **W9a** | **#1289** V-Modell-Ebene ableiten (`level_source: derived|manual`, Backfill-Report, Audit-Regel) | Die L0–L4-Achse wird auswertbar (Voraussetzung für #1267-Reports). |
| **W9b** | **#1288** Feld-Typ `criteria-list` + API/MCP-Einzelzugriff + KI-Refine (Vorschlag, kein Autosave) | Verifikationslücke schließen; ein Freitext-Blob wird strukturiert. |

**Reihenfolge:** W9a vor W9b (die Ebene ist die Achse, die Kriterien der Inhalt).

### W10 — Repo / Plugin / Doku / MCP-Hygiene

| Inhalt | Ziel |
|---|---|
| **#1283/#1284/#1285** (Hermes-Plugin-Drift: Quelle entfernt, Versionsdrift, Doku) | Release-Konsistenz: installiertes ≡ ausgeliefertes Plugin; Versions-Ratchet im Release-Check. |
| **#1292** (doppelte MCP-Route + Key im `Authorization`) | Kanonischen Pfad festlegen, Alias deprecaten, Auth-Tabelle dokumentieren (`X-API-Key` bevorzugt). |
| **#1293** (Doku-Audit: 12 kaputt, 16 Lücken) | Doku-Test in CI (Shell-Beispiele, Tool-Zahl aus einer Quelle, `x-opencode-session`-Abschnitt). |

**Bezug:** #1293/#1251 überschneiden sich (Tool-Zahl, Tool-Namen); gemeinsame Quelle anstreben.

### W11 — BluePencil-Features (vom User)

| # | Feature |
|---|---|
| 1257 | Navigationsbaum konfigurierbar (Baumfelder, 3-stufige Vererbung global/Workspace/persönlich) |
| 1260 | Attribute per Drag&Drop innerhalb/zwischen Sektionen (barrierefrei) |
| 1263 | „Neues Element anlegen"-Maske dynamisch konfigurierbar |
| 1265 | Statistiken zentral + an-/abschaltbar + vollständig über REST und MCP |
| 1266 | Glossarbegriffe als gerenderte, versionierte Referenzen |

**Bezug:** #1257/#1260/#1263 hängen am Attribut-Epic **#934/#941** und teilen die 3-Stufen-
Konfigurationsmechanik — als eigenes Epic bündeln statt einzeln. #1266 nutzt den in W3 (#1261)
eingeführten `global_uuid`-Anker.

### Entscheidungs- & Housekeeping-Spur (keine Produktwellen)

| # | Punkt | Schritt |
|---|---|---|
| #1275 | Admin-Gate + 2FA | Achse bereits entschieden durch **ADR-011 (`accepted`, Option C)** — kein neues ADR; Runde-3-D2 war eine Fehlzuordnung. Admin-Gate folgt ADR-011; 2FA = dokumentierte Risiko-Akzeptanz (ADR-021 O5) + eigenes Roadmap-Issue. |
| D4 | `+ 74 APIViews` in `.meta-config/project.yaml` | **noch nicht ausgeführt** — Klausel entfernen (Zeilen 147, 236), Meta-Sync. |
| #1104 | Tool-/Link-Zahlen in Doku/Meta | Teil-Rest; mit W10/#1293 zusammenführen. |
| Metric | `interface_coverage` (#1268) | In Runde 3 bewusst zurückgestellt (se_metrics-Konflikt) — jetzt sauber nachziehen. |
| CI | `frontend/test-results/`-Ablageort je Job | kleiner `devops-engineer`-Task. |
| #1247/#1153 | vendor-externe Dialektik | #1153 ist **wieder geöffnet**; Upstream-Eskalation dokumentiert. Kein In-Repo-Fix. |
| #1258 | volle Token-Migration | Runde 3 lieferte nur den scoped Anteil — Rest nachziehen. |
| #1269 | REST-`TestRunViewSet`-Write für `tested_artifact_version` | Feld ist via Serializer/Service/MCP schreibbar; REST-View-Forwarding fehlt. |

### Housekeeping: bereits erledigt → schließen

Die Runde-3-PRs haben diese Issues implementiert, sie sind aber **noch offen** (Auto-Close hat
nicht gegriffen): **#1262, #1267, #1268, #1269** (W4), **#1281** (Nav-Teil, W2), **#1258**
(Teil, W2). → Kommentar + schließen (bzw. bei #1258/#1281 als Teil-Fix referenzieren).

---

## 3. Prioritärer Vorschlag (wenn „schneller Nutzen zuerst")

1. **W8a** (i18n/Kontrast) und **W7a** (#1290-Fehlermeldungen, #1301/`memory.promote`) — kleine,
   hochsichtbare Fixes mit Ratchet-Wirkung.
2. **W7b** (#1300 Lern-Kreislauf) — größter funktionaler Hebel des Memory-Blocks.
3. **W9a** (#1289 V-Modell-Ebene) — Voraussetzung für aussagekräftige SE-Reports.
4. **W8b/W10** — Konsistenz/Hygiene.
5. **W11** (Features) — eigenes Epic, nach der Bug-Runde.

---

## 4. Reihenfolge & Parallelisierung

- **W7a/W7b** teilen `backend/mcp_server/tools/memory.py` und `backend/memory/**` → **ein** Strang.
- **W7c** ist überwiegend Frontend (`Memory/**`) + `MemorySystemSettingsSection` → parallel zu
  W7a/W7b möglich (disjunkte Dateien), aber #1300/#1291-#Kontext prüfen.
- **W8a** (i18n/Kontrast: Tokens + Locales) und **W8b** (Dialog/Focus/Nav) überlappen in
  `frontend/src/styles/**` und `components/NavigationShell/**` → **sequenziell** oder klare
  Dateiteilung.
- **W9a/W9b** berühren beide `persistence/models.py` → **sequenziell** (W9a zuerst: `level`).
- **W10** ist backend-/repo-/doku-nah, weitgehend disjunkt (Plugin, `docs/**`, `mcp_server`-Auth).
- **W11** eigenes Epic, nachgelagert.

---

## 5. DoD

Wie Runde 3: pro Wellerein eigener `fix/*`-Branch, Conventional Commits, Tests im selben Commit,
`make test-backend`/`make test-frontend` ohne neue Fehler, Ruff `--select=F821,F822`,
`npm run lint`/`npm run build`, Secret-Scan vor jedem Commit. Neue **Ratchet-Tests** wo vorgesehen
(i18n, Kontrast, Dialog-Muster, Memory-REST↔MCP-Parität, Plugin-Version).

---

## 6. Risiken & offene Entscheidungen

| Risiko / Entscheidung | Issue(s) | Handling |
|---|---|---|
| REST-Schreibpfad für Memory: ja oder dokumentiert MCP-only? | #1291 | **Entscheidung** nötig (User/`se-architect`); bei „ja" Rate-Limiter mitnutzen. |
| Lern-Kreislauf-Kosten (LLM+Embedding) | #1300 | Nur bestätigte Schritte einspeisen + Informationsgehalt-Filter + Counter. |
| `criteria-list` als neuer Feld-Typ | #1288 | Berührt Attribut-Contract (`field_validation.py`) + Migration bestehender Freitexte; Rückwärtskompatibilität testen. |
| `level`-Backfill | #1289 | Nur ableiten, wo eine Architektur-Zuordnung existiert; sonst NULL **melden**, nie raten. |
| Plugin-Quellbaum-Entfernung: beabsichtigt? | #1283 | **Entscheidung** nötig (bewusst + dokumentiert vs. wiederherstellen). |
| ADR-ii blockiert Admin-Gate/RLS | #1275 | Zuerst ADR (Option B), dann Umsetzung. |

---

## 7. Self-Review

- **Vollständigkeit:** alle 22 neuen Issues (#1277–#1302) erfasst + 7 offene Residuen.
- **Fakten vs. Annahmen:** Kernbefunde im Repo gegengeprüft (`projector.py:121-122`,
  `memory.py` Tool-Liste, `RequirementLevel`/`level`, `SidebarNavigation` overflow + Nav-Eintrag).
  Zwei Befunde (#1279, #1281) sind **vor Umsetzung zu re-verifizieren**, weil Runde-3-Arbeit sie
  (teilweise) bereits berührt hat.
- **Holistik:** Bündelung nach geteilter Komponente (Memory-Backend/MCP, Dialog/Fokus/Tokens,
  Datenmodell `models.py`).
- **Nicht implementiert:** dieser Plan ändert nichts.

---

*Erstellt am 2026-10-14. Basis `origin/main @ 3c79adcc`; 22 neue beta.20-Issues in 5 Wellen
(W7–W11) + Entscheidungs-/Housekeeping-Spur.*
