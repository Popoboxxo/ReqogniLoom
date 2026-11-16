# Nachweis, Abdeckungsverträge und Revisionen: Entwurfsplan (Draft)

> **Status:** **Entwurf, nicht ausführbar.** Er enthält Arbeitspakete und Gates, **keine** Tasks. Aufgaben entstehen erst nach den Freigaben in Abschnitt 4.
> **Stand:** 2026-11-16. Basis `origin/main` (Analyse `fe34e583`, Branch-Basis zum PR-Zeitpunkt `d097ef06`), ReqogniLoom 1.9.0-beta.2.
> **Spec:** [`../specs/2026-11-16-vergleichswerkzeug-gap-analyse-design.md`](../specs/2026-11-16-vergleichswerkzeug-gap-analyse-design.md) (Befunde, Vorschläge V1–V14, Entscheidungsliste E1–E11, Konzeptbedarf K1).
> **Vorgänger:** [`2026-08-08-vwz-interop-and-inspiration-concept.md`](2026-08-08-vwz-interop-and-inspiration-concept.md), vertagt, wird hier aktualisiert und teilweise aufgenommen.
> **Namensregel:** Das Vergleichswerkzeug heißt im Repository **VWZ** (Wunsch Daniel, 2026-11-16).

## 1. Ziel

ReqogniLoom soll an den Stellen aufholen, an denen das Vergleichswerkzeug fachlich **strenger oder besser prüfbar** ist, ohne unsere Stärken (Mehrmandanten, Workflow, Audit, MCP, KI) aufzugeben. Der wichtigste Punkt: Der **Testnachweis** soll neben dem Trace sichtbar werden. Heute zählt ein Requirement als abgedeckt, sobald ein `verifies`-Link auf einen Test zeigt, auch wenn der Test rot ist oder nie lief.

## 2. Ausgangslage in Kürze

- **Strenger bei VWZ:** Abdeckung braucht Nachweis (`missing-verdict`, `failing-verdict`), Links merken sich den Stand (Pins und `repin`), Abdeckung ist ein Vertrag je Ebene, Schema je Ordner.
- **Einfacher bei VWZ:** ein Prüflauf mit Exit-Code, Testergebnisse im Standardformat (CTRF).
- **Schon bei uns:** Waiver (#569), Baseline-Diff nach Inhalt (#398, besser als VWZ), Workflow, Audit, MCP, KI-Ableitung.
- **Reife von VWZ:** alpha, praktisch ein Autor, keine CI-Tests, GPL-3.0. **Wir übernehmen Konzepte, keinen Code** (E11).
- Details und Belege: Spec Abschnitte 2b und 3.

## 3. Entscheidungsstand

| Thema | Stand | Wer |
|---|---|---|
| **E1** Abdeckungsdefinition ändern? | **zurückgestellt.** Trace bleibt, Ausführungsstatus muss dazu. Konzept K1 fehlt | Daniel, 2026-11-16 |
| **K1.a** Wo hängt der Status? | **entschieden:** gespeichertes Feld am `verifies`-Link, Ausgestaltung offen | Daniel |
| **K1.b** Zustandsmodell | **zurückgestellt**, Richtung: konfigurierbar als Workflow-Erweiterung | Daniel |
| Technischer Weg K1 | **offen:** (A) Workflow-Item-Typ an der Kante oder (B) lose Spalte mit eigener Zustandsliste. Das K1-Konzept vergleicht beide | Daniel, nach Konzept |
| Altbestand Namensneutralität | **erledigt** (PR #1889) | Daniel |
| Alle übrigen | offen, siehe Abschnitt 6 | Daniel |

## 4. Arbeitspakete und Gates

Aufwand sind Schätzungen aus der Spec in Tasks. **Sie überlappen** (z. B. enthält K1-Weg A den Evaluator aus V1) und dürfen nicht addiert werden.

| AP | Inhalt | Spec | Voraussetzung | Grober Aufwand |
|---|---|---|---|---|
| **AP0** | **K1-Konzeptdokument:** Vergleich der Wege A und B, Entscheidung K1.c–K1.h, Q-a bis Q-h. Ergebnis ist ein Konzept, kein Code | K1 | Entscheidungen E1/K1.b weiter | Entwurfsrunde |
| **AP1** | Nachweis: Rollup, `missing`/`failing-verdict`, CTRF-Import, manuelle Verifikation, Disposition | V1, V2, V3, V8 | **Gate G1** (K1 freigegeben), `TestCase.uid`-Eindeutigkeit prüfen | V1 ~6, V2 ~5–7, V3 ~4, V8 ~3, K1-Weg A ~17 |
| **AP2** | Abdeckung als Vertrag je Ebene, Schema je Ebene und Typ | V5, V6 | AP1 teilweise | ~10 |
| **AP3** | Sichten als Scope für Coverage, Export, Baseline-Vergleich | V7 | **Gate G3** (Tabellenansicht Slice 1 und 3), E6 | ~5 |
| **AP4** | Ein Prüflauf mit CI-Exit-Code (REST/JSON, Skript in `dist/`) | V10 | keine, nutzt AP1 später | ~4 |
| **AP5** | Inhaltsrevision (Hash), versionsgepinnte Links, `repin`, `suspect` ableiten | V4 (S0–S3) | **Gate G2** (Abstimmung mit #1669/#1670, E2) | S0 ~4, S1 ~4, S2 ~6, S3 ~3 |
| **AP6** | Ergänzungen: Disjunktheit, Diff-Ergänzungen, HTML/NDJSON-Export, Prozessvorlage, `llms.txt` und `AGENTS.md`-Vorlage | V9, V11, V12, V13, V14 | einzeln | ~22 zusammen |
| zurück | Brücke zum Vergleichswerkzeug, Code-Symbole als Requirements | — | nur auf Wunsch (E8, E9) | — |

**Vorgeschlagene Reihenfolge (Wellen):** AP0 → AP1 → AP2, AP3, AP4 → AP5 (S0 darf früh, S1 ff. erst nach G2) → AP6. Vorschlag: neue **Phase I „Verifikation und Abdeckungsverträge"** in der Roadmap, Absprache mit Phase F (Testqualität, #587), damit das Ergebnismodell nicht doppelt angefasst wird (E10).

**Gates:**

| Gate | Inhalt | Wer gibt frei |
|---|---|---|
| G0 | Entscheidungsliste in Abschnitt 6 abgearbeitet, V-Auswahl getroffen | Daniel |
| G1 | K1-Konzeptdokument reviewed und freigegeben | Daniel |
| G2 | Revisionsmodell mit Allokation-Release und Inhalt einfrieren abgestimmt (#1669/#1670, D10/D12) | Daniel |
| G3 | Tabellenansicht Slice 1 und 3 vorhanden | Stand prüfen |

## 5. Querschnittsregeln

Aus `2026-11-10-backlog-roadmap.md` übernommen:

1. **Frische-Check** vor jeder Ausführung: `python scripts/check_plan_refs.py` gegen aktuellen `origin/main`. Belege in der Spec beruhen teils auf Agentenberichten (Spec Abschnitt 2).
2. **Migrationen** nacheinander mergen und renummerieren (Betrifft AP1, AP5, K1).
3. **Tool-Zähler:** Ziel ist Delta 0 (bestehende Tools erweitern). Der Zähler nennt die Roadmap 290, `CLAUDE.md` auf `origin/main` 301. Vor jeder Zähler-Aussage `docs/agent-templates/tool-manifest.json` prüfen.
4. **Commit- und PR-Texte als Datei** (Trailer `Co-Authored-By: Claude Sonnet 5.5`).
5. **Volle Testläufe nur sequentiell** (Host ca. 5,8 GiB RAM).
6. **Neue Prüfungen mit Randfalltests von Anfang an:** Duplikat, Mehrdeutigkeit, Tippfehler in Unterdrückungen, deterministische Reihenfolge. Das Vergleichswerkzeug hat diese Lücken (Spec Abschnitt 2b).
7. **Keine Übernahme von Fremdcode** (GPL-3.0). Eigene Umsetzung nach eigener Spec.

## 6. Register der offenen Fragen

Alle werden **einzeln** mit Daniel geklärt (AskUserQuestion). „Empfehlung" ist ein Vorschlag, keine Entscheidung.

**K1, Teststand zwischen Requirement und Testfall**

| ID | Frage | Empfehlung |
|---|---|---|
| K1.c | Rollup-Regel: strikt oder konfigurierbar? Zählt `übersprungen` als Nachweis? | strikt als Default, konfigurierbar je Rigor-Tier, `übersprungen` zählt nicht |
| K1.d | Zählen Tests der Kind-Anforderungen mit? | nur direkte Tests als Default, rekursiv als Option |
| K1.e | Gültigkeit eines Ergebnisses: neuestes, Zeitablauf, Ablauf bei Änderung | neuestes, plus „veraltet" bei Inhaltsänderung |
| K1.f | Quellen: CI, manuell, KI-erzeugt | CI und manuell, KI-Tests zählen weiter nicht (#424) |
| K1.g | Darstellung: eine Zahl, zwei Zahlen, Matrix | Matrix, `covered` bleibt sichtbar |
| K1.h | Wirkung auf Freigabe und Baseline | je Rigor-Tier, Blocker nur in Extended |
| K1-Weg | (A) Workflow-Item-Typ an der Kante oder (B) lose Spalte mit eigener Zustandsliste | im K1-Konzept vergleichen |
| Q-a bis Q-h | Datenmenge, Baseline, Suspect, Audit, Backfill, `validates`-Kanten, Löschen von Kanten, Abwärtskompatibilität | im K1-Konzept klären |

**Vorschläge und Entscheidungen**

| ID | Frage | Empfehlung |
|---|---|---|
| V-Auswahl | Welche der Vorschläge V1–V14 werden übernommen? | alle außer V9 (hängt an E7) |
| E2 | Inhaltsrevision: Hash oder Versionstabelle? | Hash zuerst |
| E3 | Testergebnisse: nur CTRF oder auch JUnit-XML? | CTRF zuerst |
| E4 | Schwere kaputter Referenzen und Zyklen im Prüflauf | je Rigor-Tier konfigurierbar |
| E5 | JSON-Schema 2020-12 als Austauschformat? | nein |
| E6 | Freie Ausdruckssprache für Sichten? | nein, Filter-DSL wiederverwenden |
| E7 | Sind Varianten ein echtes Thema (entscheidet V9)? | offen, Fachentscheidung |
| E8 | Brücke zum Vergleichswerkzeug gewollt? | vertagt |
| E9 | Code-Symbole importieren? | nein |
| E10 | Neue Phase I in der Roadmap? | ja |
| E11 | Nur Konzepte, keinen Code (GPL-3.0)? | ja |
| Wellen | Reihenfolge der Wellen in Abschnitt 4 bestätigen | wie vorgeschlagen |

## 7. Nächste Schritte

1. Offene Fragen aus Abschnitt 6 einzeln klären, zuerst K1.c und K1.d, dann die V-Auswahl.
2. AP0 starten: K1-Konzeptdokument (nur nach Freigabe).
3. Nach G0 und G1: Tasks je Arbeitspaket nach `superpowers:writing-plans` schreiben, mit Frische-Check.
4. Roadmap um Phase I ergänzen (nach E10).

## 8. Risiken (Auszug, vollständig in der Spec, Abschnitt 9)

| Risiko | Gegenmaßnahme |
|---|---|
| Ein zweiter Versionsbegriff neben Release und Freeze | G2 vor AP5 |
| `uid`-Duplikate bei Testfällen blockieren den Import | Eindeutigkeit prüfen und bereinigen, vor der Migration |
| Befund-Flut auf Altbestand nach Einführung von Verdict-Befunden | Standard `warning`, Rollout je Rigor-Tier, Waiver nutzbar |
| Zustand an der Kante vergrößert Datenmenge | Q-a im K1-Konzept messen |
| Belege teilweise aus Agentenberichten | Frische-Check, Beleg je Task |

## 9. Grenzen dieses Entwurfs

- Der Code des Vergleichswerkzeugs wurde gelesen, **nicht ausgeführt**. Aussagen zu seinen Tests beruhen auf Funktionsnamen.
- Frontend-Fähigkeiten (Ansichten, Coverage-UI) wurden nur oberflächlich geprüft.
- Datenmenge der `verifies`-Kanten im Bestand ist nicht gemessen.
- Ob die Workflow-Engine Kanten als Gegenstand tragen kann, ist am Code geprüft (heute nein), im Betrieb nicht erprobt.
