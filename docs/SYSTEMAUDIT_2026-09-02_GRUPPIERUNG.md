# Gruppierung: Systemaudit 2026-09-02 (grob) gegen offene GitHub-Issues

**Zweck:** Vorstufe zur Spezifikationsarbeit. Jede Gruppe unten ist ein Kandidat für eine eigene `/superpowers`-Spezifikation → eigener Plan. Diese Datei selbst ist keine Spezifikation und keine Umsetzung.
**Quelle:** `docs/SYSTEMAUDIT_2026-09-02_GROB.md` (Stand main @ 927c169c, v1.8.0-beta.6, Kapitel A-W + O/P) gegen alle 72 offenen GitHub-Issues (Stand 2026-09-03, `state=open`).
**Methodik:** Titel-/Label-Abgleich als erster Filter (bei diesem Repo sehr zuverlässig, da ein großer Teil der offenen Issues erkennbar aus einer vorherigen QA-Runde gegen denselben Instanz-Stand stammt). Punktuelle Inhaltsprüfung nur bei Kandidaten, deren Titel allein nicht eindeutig war. Bei niedriger Sicherheit steht das explizit dabei — nicht geraten.
**Fußnote Datenschutz:** Die Quelldatei (`SYSTEMAUDIT_2026-09-02_GROB.md`) enthält an mehreren Stellen (Methodik-Kopf, Kapitel H2, Kapitel R-Kopf) die reale interne IP `<audit-host>` des Audit-Laufs im Klartext. Nicht in diese Gruppierungsdatei übernommen. Separate Bereinigung der Quelldatei empfohlen (gleiches Muster wie bereits bei anderen Dateien behoben, siehe Commit `84af2f27`).

---

## 1. P0-Soforthärtung (kleine, unabhängige Fixes, quer über Domänen)

Der Audit selbst reiht diese in Abschnitt O ganz oben — alle P0/0/0a. Kein einzelner Fix ist groß, aber jeder blockiert etwas Grundlegendes. Sinnvoll als **ein** kleiner Sprint, weil jeder Punkt für sich unter einem Tag liegt.

| Audit-ID | Issue | Kurzbeschreibung | Neu/Bestehend | Größe |
|---|---|---|---|---|
| R2 | — | CSRF-Cookie `Secure` über HTTP gesetzt → **kein Schreibzugriff aus der UI auf der Live-Instanz möglich** | Neu | klein (1 Zeile + Banner) |
| T1 | teilw. #722 | Viewer-Rolle sieht alle Schreib-Buttons/Admin-Navigation, nur Server lehnt ab | #722 ist RBAC-Backend-Hardening, T1 ist das FE-Pendant (Rendering) — separat behandeln, siehe Gruppe 8 | klein (Rendering-Gate) |
| U2 | teilw. #832 | Suspect-Propagation tot, `suspect`-Feld fehlt im Serializer | #832 ist nur der Trace-Link-Picker-Teilbefund, U2 ist der Kernbefund — neu | klein-mittel |
| H5.1-3 | #799 (teilw.) | `.mcp.json`-Fix, GET `/mcp/` 405 statt 200, OpenCode-Klammern-Fix | #799 deckt nur die inputSchema-Mismatches, nicht die Transport-Bugs — neu | klein (< 2h zusammen) |
| R3 (Teilmenge) | #827, #829, #830 | Unbekannte Felder still verworfen, `page=99` → 500, Batch-JSON-RPC 500, `page_size` still ignoriert | teils bestehend, teils neu | klein, viele Einzel-Fixes |
| R5/R7 (Parser-Teil) | #825 (teilw.) | `LlmResult.score`-Normalisierung (Zehnerskala vs. 0-1), Konsistenz-JSON-Repair, non-retryable-Fehler im 180s-Timeout-Wrapper | Neu (Parser-/Pipeline-Fehler, kein Modellfehler) | klein-mittel |

**Warum eine Gruppe trotz Themenvielfalt:** alles ist "ein Nachmittag bis ein Tag", nichts braucht Konzeptarbeit, und R2 blockiert praktisch jeden Live-Test der anderen Gruppen. Zuerst bearbeiten, bevor irgendeine andere Gruppe sinnvoll live verifiziert werden kann.

---

## 2. API-Vertrag & Client-Generierung

| Audit-ID | Issue | Kurzbeschreibung | Neu/Bestehend | Größe |
|---|---|---|---|---|
| C1 | — | OpenAPI-Schema für 43 von 46 APIViews leer | Neu | groß (2-3 Tage laut Audit) |
| C2 | — | 4 verschiedene Fehlerformate parallel zum Envelope | Neu | klein |
| C3 | — | Route-Dubletten ohne Deprecation (`tracelinks`/`trace-links` etc.) | Neu | klein-mittel |
| C4 | — | Workspace-Adressierung in zwei Stilen (Query-Param vs. nested) | Neu | mittel |
| C7 | — | Frontend-Client an 7 Stellen umgangen (fetch statt `client.ts`) | Neu | klein |
| C8 | — | Filterung handgestrickt, 86 manuelle `query_params.get` | Neu | mittel |
| B4 | teilw. | Trace-Link-Typen driften (Backend 15, FE 14, `diagram-ref` fehlt) | Überschneidet mit Gruppe 10 (Traceability) — hier nur der Schema-Symptom-Teil | klein |
| E2.4 | — | Kein Client-SDK, drei handgeschriebene Clients (FE, Hermes-Py, Hermes-TS) | Neu, hängt an C1 | mittel (folgt aus C1) |

**Reihenfolge intern:** C1 zuerst (macht B4/E2.4 danach trivial lösbar — generierter Client kann nicht mehr driften).

---

## 3. MCP-Modernisierung & Client-Konnektivität (über Gruppe 1 hinaus)

| Audit-ID | Issue | Kurzbeschreibung | Neu/Bestehend | Größe |
|---|---|---|---|---|
| C5 | — | MCP-Protokoll auf altem Stand (2024-11-05 statt 2025-06-18), keine Resources/Prompts | Neu | mittel |
| C6 | teilw. #799 | MCP/REST nicht paritätisch (ICDs, Metrics etc. nur REST; `ai_derivation.*` nur MCP) | #799 ist ein anderer Aspekt (inputSchema-Korrektheit der vorhandenen Tools) — beide gehören in dieselbe Spezifikation | mittel |
| — | **#799** | 12 MCP-Tools mit fehlenden required-Feldern vs. Server-Validierung | Bestehend | klein-mittel |
| H4 | — | Doku-Defekte: `curl -N` als stdio-Bridge unmöglich, falsche Transport-Liste, 4 Ports für ein Backend | Neu | klein (Doku) |
| R4 | — | Live bestätigt: JSON-RPC-Batch → 500, Parse-Error → 401 statt 400 | Neu | klein |

**Bezug:** Gruppe 1 enthält bereits die 3 Sofort-Fixes (H5.1-3) für Claude Code/OpenCode-Konnektivität. Diese Gruppe ist die strukturelle Weiterentwicklung danach (Protokoll-Version, Parität, Doku).

---

## 4. Security der Integrationsflächen

| Audit-ID | Issue | Kurzbeschreibung | Neu/Bestehend | Größe |
|---|---|---|---|---|
| E2.1 | — | API-Keys ohne Scopes/Ablauf, ein Key = volle Nutzerrechte tenantweit | Neu | mittel |
| — | **#722** | RBAC-Kombination härten (structured discriminator + Layer-2-Relocation) | Bestehend | mittel |
| — | **#697** | `str(exc)`-Exception-Leaks (CWE-209), ~40+ Stellen | Bestehend | mittel |
| — | **#696** | Bearer-Token im Login-Response-Body (XSS-Re-Exposure-Risiko) | Bestehend — Audit bewertet R1 "Token im Body plus Cookies" noch als "+", #696 sieht das kritischer; beide zusammen in dieselbe Spezifikation, Widerspruch dort auflösen | mittel |
| — | **#35** | Kein Rate-Limiting auf API-Endpoints — Audit R1 nennt 7 Throttle-Scopes als "+", ggf. schon obsolet, prüfen | Bestehend, evtl. veraltet | klein (Prüfung) |
| — | **#92** | Workspace-spezifische API-Tokens mit UI | Bestehend, hängt an E2.1 | mittel |
| E2.2 | — | Webhooks nicht self-service (nur Django-Admin), keine Test-Delivery, keine Secret-Rotation | Neu | mittel |
| E2.6 | — | Event-Katalog unvollständig (ICD, Diagram, Glossary, TestRun, Review fehlen), kein AsyncAPI | Neu | klein-mittel |

**Reihenfolge intern:** E2.1 zuerst (blockiert laut Audit "jede externe Freigabe"), dann Webhook-Self-Service (E2.2/E2.6), Security-Hardening (#722/#697/#696) parallelisierbar.

---

## 5. Datenmodell-Konsolidierung

| Audit-ID | Issue | Kurzbeschreibung | Neu/Bestehend | Größe |
|---|---|---|---|---|
| B1 | teilw. #831 | Drei Status-Achsen auf einem Artefakt, deutscher Default-String in `application/models.py` | #831 ist ein Symptom davon (Glossary nutzt `lifecycle_status` statt `status`) | groß, Grundlagenarbeit |
| B2 | — | Vier Orte für "Artefakt" (generisch, spezialisiert, application-Layer-Verstoß, Diagram/Icd eigene Apps) | Neu | groß |
| B6 | — | Zwei Versionierungskonzepte parallel (Audit-basiert vs. eigene Version-Tabellen) | Neu | mittel |
| Q2.3 | — | Fachliche Einordnung: generisches Artefaktmodell begonnen, nie beendet — größte Konsolidierung, Voraussetzung für Gruppe 6 | Neu | strategische Einordnung, kein Einzel-Fix |

**Wichtig:** Laut Audit-Priorisierung (O, Rang 3) sollte dies **vor** Schritt 2 der Attribut-Definition (Gruppe 6) geklärt werden, sonst wird der Status-Sonderfall dort einzementiert. Reihenfolge zwischen Gruppe 5 und 6 nicht vertauschen.

---

## 6. Attribut-Definition als Systemobjekt & Formular-Vereinheitlichung

Größtes Einzelvorhaben im ganzen Audit (Autor schätzt 15-20 Tage für N4 komplett). Bündelt sehr viele kleine QA-Issues, die alle Symptome derselben fehlenden Abstraktion sind.

| Audit-ID | Issue | Kurzbeschreibung | Neu/Bestehend | Größe |
|---|---|---|---|---|
| N1-N4 | **#186** (EPIC) | Kein Attribut-Definitions-Systemobjekt, 7 handgeschriebene Formulare, jedes anders. `#186` (UI-Gesamtkonzept-EPIC, 6 Schritte) ist wahrscheinlich die passende Dach-Issue dafür — Body prüfen vor Spec-Start | Teilweise bestehend als Dach-Issue | groß (15-20 Tage) |
| — | **#802** | Zwei Create-Paradigmen (Modal vs. Inline) | Bestehend, deckt sich mit S5 | klein (Symptom von N3) |
| — | **#803** | Requirement-Formular: Attribute ungruppiert | Bestehend | klein (Symptom von N1) |
| — | **#804** | Entity-Listen zeigen SE-Attribute nicht | Bestehend, deckt sich mit S4 | klein |
| — | **#806** | Dashboard/Metrics massive Leerräume | Bestehend, deckt sich mit S2 — eher Gruppe 9 (Design), aber Ursache teils fehlende Attribut-Konsolidierung | klein |
| — | **#807** | Listen: Kurz-Hash statt lesbarer ID | Bestehend, deckt sich mit V ("`uid` ist null") | klein, aber grundlegend (braucht Nummernkreis-Feature) |
| — | **#816** | `TestCase.test_type`: zwei konkurrierende Repräsentationen | Bestehend, exakter Live-Beleg für N1-Tabelle | klein |
| — | **#824** | Custom-Fields: kein REST-Endpoint für CRUD | Bestehend | klein-mittel |
| — | **#829** | TestCase-PATCH lehnt `change_reason` ab | Bestehend | klein |
| — | **#830** | Custom-Field-Erstellung im UI schlägt leise fehl (403) | Bestehend | klein |
| Q1.2 | — | Ohne Attribut-Definition bleibt Configurable Rigor ein Feature-Schalter | Neu, fachliche Begründung | — |
| Q2.2 | — | Rigor endet am Feature-Schalter, müsste Eigenschaft der Definition sein | Neu, fachliche Begründung | — |
| S5, S6, S15 | — | Live-UI-Belege: Create-Dialoge, Detailformulare, Sichtbarkeits-Tab | Neu (Live-Bestätigung von N1) | — |

**Empfehlung:** Erst `describe_schema` für alle Typen (N4 Schritt 1, "ein Tag", macht Lücken sichtbar) als eigene kleine Vorstufe, bevor die große Spezifikation geschrieben wird.

---

## 7. Frontend-Design-System-Schulden

| Audit-ID | Issue | Kurzbeschreibung | Neu/Bestehend | Größe |
|---|---|---|---|---|
| A1 | — | 1015 Inline-Styles in Components | Neu (teils überschneidet Gruppe 6, da Formulare Hauptquelle) | groß, mechanisch |
| A2 | — | 74 Roh-Farben außerhalb Token-System, 4 von 5 Themes fallen bei Canvas/Workflow/Graph/Metrics raus | Neu | mittel |
| A3 | — | Responsive-Modell nur als Token definiert, App faktisch Desktop-only | Neu | mittel-groß |
| A6 | — | Kein einheitliches Feedback-System (Toast kaum genutzt, 105+47 inline alert/status) | Neu | mittel |
| A9 | — | Natives `confirm()` verblieben | Neu | trivial |
| A10 | — | `html lang` folgt nicht dem Sprachwechsel | Neu | trivial |
| S1-S3, S9-S20 (Rest) | — | Diverse Live-UI-Befunde: Login-Theme-Bruch, Dashboard-Leere, Sidebar-Fold, Metriken ohne Verlauf, Responsive bei 768px etc. | Neu, Live-Bestätigung | viele kleine |
| Q2.9 | — | UI-Konzept fehlt Komponentenkatalog + ESLint-Regeln gegen Inline-Styles | Neu, strukturelle Empfehlung | — |
| — | **#665, #666, #668, #675, #677** | Navigationsbaum-Redundanz, Design-System-Uneinheitlichkeit Badges, a11y aria-live | Bestehend (älterer UI/UX-Audit) | mittel je Issue |
| — | **#596** | Workflow-Editor horizontaler Overflow + 480KB DOM auf `/audit` | Bestehend — Widerspruch beachten: S17 lobt Workflow-Editor als "beste Seite", #596 könnte älter/teilweise überholt sein, prüfen | klein-mittel |
| — | **#598** | Frontend-Review v1.6.0 (5 Warnings, 6 Suggestions) | Bestehend, **vermutlich stark veraltet** (v1.6.0 vs. jetzt v1.8.0-beta.6) — gegen aktuellen Stand re-validieren statt blind übernehmen | Prüfung nötig |
| — | **#808** | "Traceability" heißt in Sidebar "Verknüpfungen" | Bestehend, i18n/Terminologie | trivial |
| — | **#809** | SE-Metriken 4+1-KPI-Layout statt responsivem Grid | Bestehend, deckt sich mit S12 | klein |

**Charakter dieser Gruppe:** überwiegend mechanisch abbaubar (Codemod-Kandidat laut Audit selbst, Tiefenanalyse-Vorschlag #9), aber groß im Umfang. Sinnvoll in mehrere Wellen statt einer Riesen-Spezifikation.

---

## 8. Rollen & Sichtbarkeit (UX-Vervollständigung über den P0-Fix hinaus)

| Audit-ID | Issue | Kurzbeschreibung | Neu/Bestehend | Größe |
|---|---|---|---|---|
| T2, T3 | **#810** | Drei Sichten (Leser/Autor/Experte) als vollwertiges Konzept, `audience`-Feld auf Attribut-Definition | #810 ist exakt dieses RFC — direkter Treffer | groß |
| A8 | — | Administrations-IA fragmentiert (5 Einstellungsflächen, 3 Rollenkonzepte client-seitig) | Neu | mittel |
| S3 | — | Sidebar zeigt Admin-Einträge auch dem Viewer | Neu, Live-Beleg (siehe auch T1 in Gruppe 1) | — |
| — | **#449** | Sidebar-Navigation abgeschnitten (10 von 23 Punkten unsichtbar, nicht scrollbar) | Bestehend, exakter Treffer zu S3 | mittel |

**Bezug:** Der reine Rendering-Fix (Buttons nicht rendern statt nur deaktivieren) ist bereits P0 in Gruppe 1 (T1). Diese Gruppe ist der volle Ausbau zum Drei-Sichten-Konzept inkl. `#810`.

---

## 9. Traceability-Modell (Typ-Reduktion, Suspect, Coverage)

| Audit-ID | Issue | Kurzbeschreibung | Neu/Bestehend | Größe |
|---|---|---|---|---|
| U1-U3 | — | Live bewertet: Erlaubt-Matrix lückenhaft, `parent_id` still verworfen, drei Hierarchie-Mechanismen, Pfad nur in Linkrichtung, drei widersprüchliche Coverage-Zahlen. Empfehlung: Reduktion auf 8 Kern-Typen mit fester Semantik | Neu, sehr konkreter Vorschlag inkl. Migrations-Tabelle in U3 | groß (Autor: "ein Tag Modellarbeit und eine Migration") |
| B4 | — | Trace-Link-Typen driften Backend/Frontend | Siehe auch Gruppe 2 (Schema-Symptom) | klein |
| S7, S8 | — | Live-UI: Trace-Link-Dialog erklärt keine erlaubten Typen, Verknüpfungen-Seite mit englischen Gruppennamen | Neu | klein-mittel |
| — | **#832** | Trace-Link-Picker zeigt duplizierte Artefakte | Bestehend | klein |
| — | **#831** | Glossary nutzt `lifecycle_status` statt `status` | Bestehend, Doppel-Einordnung mit Gruppe 5 (Datenmodell) — Umsetzung hier, Ursache dort | klein |

**Nicht in dieser Gruppe, separat kritisch:** `#571` (`GET /tracelinks/` OOM-killt Backend-Worker, CRITICAL) — im Audit-Dokument nicht direkt erwähnt (Performance war laut Kap. P explizit "nicht bewertet"), aber inhaltlich hier zuhause. Da CRITICAL-Label und Produktionsrelevanz: **eigenständig vorziehen**, nicht auf die große Traceability-Spezifikation warten lassen.

---

## 10. SE-Konzept-Lücken & "Menschen im System"

| Audit-ID | Issue | Kurzbeschreibung | Neu/Bestehend | Größe |
|---|---|---|---|---|
| Q1.1 | — | Keine Owner-, Comment-, Notification-Entität — Audit selbst: "größter Nutzwert im ganzen Audit" | Neu | groß (1-2 Wochen laut Audit) |
| D1-D3 | teilw. | NASA-SE-17-Prozesse-Bewertung (39/68 Punkten), 6 Konzeptlücken (Funktionsebene, Meilenstein, Validierung, Entscheidungen, Requirement-Attribute, Stakeholder) | Neu, Rahmenbewertung | strategisch |
| Q1.5 | — | Requirement-Attribute rationale/source/owner/priority + Stakeholder-Entität | Deckt sich mit D2 Lücke 5+6 | mittel |
| Q1.8 | — | Funktionsebene fehlt (`element_type = "function"`) | Neu, Autor beziffert "ein Tag" für Minimalversion | klein-mittel |
| Q1.9 | — | Meilenstein-/Review-Objekt fehlt | Neu | mittel-groß |
| — | **#393** | MOE/MOP/TPM komplett fehlend | Bestehend, deckt D1-Prozess-16-Lücke | groß |
| — | **#399** | Baselines sperren Artefakte nicht, CRs gaten baselined edits nicht | Bestehend, deckt D1-Prozess-14 | mittel |
| — | **#402** | Validation-Layer (Goals) standardmäßig deaktiviert | Bestehend | mittel |
| — | **#408** | Requirement-Creation ohne Pflichtfelder, kein rationale-Feld | Bestehend, exakter Treffer zu Q1.5/D2 Lücke 5 | mittel |
| — | **#410** | MCP-Surface fehlt für Kern-SE-Lifecycle-Tools | Bestehend, überschneidet Gruppe 3 (MCP) | mittel |
| — | **#424** | KI-generierte (Mock-)Testfälle unflagged gespeichert | Bestehend | klein |
| — | **#426** | Audit-Index (Dach-Issue der 2026-08-07-Serie) | Bestehend, Dach-Issue für #393-424 | — |
| — | **#581** | SE-Auditor-Kalibrierung: 100% Blocker, 0 Warnings | Bestehend, deckt sich mit S11 Live-Beleg | mittel |
| — | **#583** | IEEE-29148-Pflichtfelder fehlen (rationale, uid, acceptance_criteria) | Bestehend, exakter Treffer zu V (Attribute live) | mittel |
| — | **#272** | SE-Interview Gesamtnote 3,5 — Vorläufer-Version dieses Audits (D-Kapitel) | Bestehend, wahrscheinlich durch dieses neue Audit überholt/detailliert — bei Spec-Arbeit als historischer Kontext nutzen, nicht als offene Einzelaufgabe | Prüfung: ggf. schließen zugunsten des neuen Audits |
| — | **#50** | Baseline: Benennung, Compare, Rollback | Bestehend, Überschneidung mit D1-Prozess-14/#399 | mittel |

**Größe der Gesamtgruppe:** strategisch, mehrwöchig. Realistisch in mehrere Spezifikationen aufteilen (z. B. "Requirement-Attribute + Stakeholder" zuerst, da klein und hoher Reifegewinn laut Audit-Rang 5).

---

## 11. KI-Vorschlag-Modell, Interview-Engine & Memory/Honcho

| Audit-ID | Issue | Kurzbeschreibung | Neu/Bestehend | Größe |
|---|---|---|---|---|
| Q2.1 | — | "KI-Vorschlag als Zustand" fehlt als Konzept, Agenten ohne eigene Identität | Neu, Audit-Rang 1b (baut auf E2.1 auf) | groß |
| L2.1, R6 | — | `formalize()` kann nur Requirements — 7 von 8 Interview-Typen startbar, nie abschließbar (Live bestätigt, Fehlermeldung ist Entwicklernotiz) | Neu, Audit-Rang 2a ("ein Tag") | klein-mittel |
| L2.2-L2.7 | — | Default-Protokoll zu dünn, Provenienz unsichtbar, Transkript unbegrenzt, zwei UIs, dünnes i18n | Neu | mittel |
| M2.1 | — | Memory nur Interview-Feature, kein Systemfeature (fast nichts füllt/liest es) | Neu, Audit-Rang 3a ("zwei Tage" für Mixin) | mittel |
| M2.2 | teilw. #826 | Honcho-Backend funktional beschnitten (`forget` kaputt, kein Löschrecht = DSGVO-Problem) | #826 ist der Embedding-Dimension-Teilaspekt, M2.2 ist umfassender (Löschrecht!) | mittel |
| — | **#826** | Embedding-Dim-Mismatch: DB vector(384) vs. 768-dim Ollama/Honcho | Bestehend, exakter Treffer | klein-mittel |
| — | **#825** | `suggest_architecture_for_requirement` liefert leere Ergebnisse | Bestehend, Live-Beleg in R7 als funktionierend vermerkt (+) — **möglicher Widerspruch, prüfen ob Regression seit Audit-Zeitpunkt oder Issue veraltet** | Prüfung nötig |
| — | **#828** | AI-Drafts auf Englisch trotz `language=de` | Bestehend, exakter Treffer zu R7 "Sprache"-Querbefund. Referenziert intern Issue #795 (nicht in offener Liste — vermutlich bereits geschlossen oder Tippfehler, bei Spec-Start klären) | klein-mittel |
| M2.3, M2.4 | — | Zwei Konfigurationsorte (Env vs. DB), drei REST-Familien ohne Ordnung | Neu | klein-mittel |
| R7 (Embeddings) | — | Embedding-Pipeline schreibt beim Anlegen nichts trotz "Health: ok" — Ähnliche-Requirements und Interview-Grounding tot | Neu, überschneidet #826 | mittel |

**Reihenfolge intern:** L2.1 (formalize-Dispatch) zuerst — klein, Audit selbst reiht es als Rang 2a direkt nach den P0-Themen. Rest kann als größere Memory/KI-Spezifikation folgen.

---

## 12. Hermes/Plugin-Ökosystem

| Audit-ID | Issue | Kurzbeschreibung | Neu/Bestehend | Größe |
|---|---|---|---|---|
| E1, H3 | — | Zwei Hermes-Plugins, beide nie live verifiziert. TS-Plugin fälschlich als "tot" bezeichnet (README-Fehler) — Manifest ist aber wirklich falsch | Neu | mittel |
| H4 | — | Vier verschiedene Ports in der Doku für dasselbe Backend | Neu, Doku-Fix | klein |
| E2.3 | — | Empfehlung: TS-Plugin-README-Fehler korrigieren, Python-POC live verifizieren, dann erst Scope erweitern | Neu | mittel |
| — | **#649** | Feature: importable Hermes Skill (Connector) neben Desktop-Plugin | Bestehend, erweitert dieses Thema | mittel |

---

## 13. GitHub/Jira-Anbindung (neues Feature)

| Audit-ID | Issue | Kurzbeschreibung | Neu/Bestehend | Größe |
|---|---|---|---|---|
| W1-W3 | — | Drei Ausbaustufen: Link-Only (1 Woche) → Inbound-Sync (2 Wochen) → Outbound+Agent (2 Wochen). Voraussetzungen explizit benannt: E2.1, E2.2, R2, V (uid/owner/external_ref) | Neu, komplett | groß, aber sauber stufenweise geschnitten |

**Abhängigkeiten:** Stufe 1 kann erst sinnvoll starten, wenn Gruppe 1 (R2) und Gruppe 4 (E2.1/E2.2) so weit sind, dass extern Geschriebenes überhaupt ankommt bzw. Dritte angebunden werden können.

---

## 14. Deployment/Docker-Compose — bereits eigener Plan, nur Referenz

`#792` (RFC System-Wide Improvements: Deployment, Security, Operations & DX) ist bereits vollständig eingeordnet und in Bearbeitung: `docs/UMSETZUNGSPLAN_DOCKER-COMPOSE-2026-08-31.md` auf Branch `docs/compose-optimization-plan-792`, Sub-Projekte A-F. **Nicht neu aufrollen.**

Einzige neue Verknüpfung aus diesem Audit:

| Audit-ID | Issue | Kurzbeschreibung | Wohin |
|---|---|---|---|
| — | **#823** | `admin.backup_create` erzeugt unkomprimiertes `.json` | Gehört inhaltlich in Sub-Projekt D (Backup-Härtung) des bestehenden Compose-Plans — dort einsortieren statt neue Gruppe |

---

## 15. Vermutlich veraltete/zu prüfende Alt-Issues (nicht neu gruppiert)

Diese Issues sind entweder deutlich älter als dieser Audit-Stand (v1.8.0-beta.6) oder ihr Titel deckt sich nicht klar mit einem Befund im Dokument. Vor Aufnahme in eine Spezifikation gegen den aktuellen Code-Stand re-validieren, nicht blind übernehmen:

| Issue | Titel | Warum unklar |
|---|---|---|
| #598 | Frontend-Review v1.6.0 | Zwei Major-Betas alt, vermutlich größtenteils durch dieses Audit ersetzt |
| #597 | MCP-Audit-Op-Gap v1.6.0 | Dito |
| #504 | E2E shard 2 baseline failures | Testing-Infrastruktur, außerhalb Audit-Scope (Kapitel P: "Tests ausgeschlossen") |
| #433 | Regression-Test tenant_id CTE | Testing, außerhalb Audit-Scope |
| #378 | Artefakt-Qualitätsbewertung (Feature) | Kein direkter Audit-Befund, thematisch nah an N3/Q1, aber eigenständiges Feature — separat bewerten |
| #319, #318 | AGENT-FEEDBACK Einzelbefunde (Inspector-Diff, Trace-Link-Dialog Selects) | Alt, teils schon durch S7/N3-Befunde umfassender abgedeckt |
| #304 | MCP architecture.create kann keine Kind-Elemente anlegen | Alt, könnte durch aktuellen Stand bereits behoben sein — prüfen |
| #196/#186 | s. Gruppe 6 | bereits eingeordnet |
| #85 | UI-Bewertung v1.0.0 | Sehr alt, mit hoher Wahrscheinlichkeit vollständig durch dieses Audit ersetzt — Kandidat zum Schließen |
| #89, #39 | seed_demo Bootstrap/Idempotenz | DX-Themen, außerhalb UI/Konzept/Schnittstellen-Scope dieses Audits |
| #587 | Promptfoo-Testinfrastruktur | Testing-Infrastruktur, außerhalb Scope |
| #20, #19, #18, #17 | Alte SE-Feature-Requests (derive_and_persist, Rule Enforcer, RAG-Suche, workspace.resolve_references) | Sehr alte Issue-Nummern, möglicherweise durch aktuelle MCP-Tool-Landschaft (172 Tools) bereits erledigt oder Teil einer anderen Gruppe — Body-Prüfung vor Spec-Arbeit nötig |
| #27, #28, #29 | ICDs/Trace-Links/Custom-Fields "leere Seite ohne Anleitung" | Alte QA-Befunde zu leeren Demo-Daten, im aktuellen Audit nicht bestätigt (Instanz hat reale Daten) — vermutlich durch Nutzung überholt |

---

## Empfehlung: Bearbeitungsreihenfolge der Gruppen

Kriterium: Audit-eigene Priorisierung (Kapitel O) plus Issue-Labels (`critical`/`high`/`security`) zuerst, dann Abhängigkeitskette.

1. **Gruppe 1 — P0-Soforthärtung.** Alles andere Live-Testen hängt an R2 (Schreibzugriff).
2. **Gruppe 9 — `#571` (OOM-Kill, CRITICAL) separat vorziehen**, unabhängig vom Rest der Traceability-Arbeit.
3. **Gruppe 5 — Datenmodell-Konsolidierung.** Muss vor Gruppe 6 stehen (Audit-Warnung: sonst Status-Sonderfall einzementiert).
4. **Gruppe 6 — Attribut-Definition.** Größtes Vorhaben, aber löst am meisten kleine Issues gleichzeitig (#802-807, #816, #824, #829, #830).
5. **Gruppe 4 — Security der Integrationsflächen.** E2.1 blockiert Gruppe 13 (GitHub/Jira) und jede externe Freigabe.
6. **Gruppe 8 — Rollen & Sichtbarkeit.** `#810` ist bereits als RFC formuliert, technisch klar umrissen.
7. **Gruppe 2 + 3 — API-Vertrag & MCP-Modernisierung.** Parallelisierbar zueinander, beide unabhängig von 4-6.
8. **Gruppe 10 — SE-Konzept-Lücken.** Strategisch groß, in Teilstücke schneiden (Requirement-Attribute zuerst, da Audit-Rang 5).
9. **Gruppe 11 — KI-Vorschlag/Interview/Memory.** L2.1 (formalize) vorziehbar als Quick-Win, Rest danach.
10. **Gruppe 7 — Frontend-Design-System.** Mechanisch, aber groß — keine Eile, keine Blockade für andere Gruppen.
11. **Gruppe 12 — Hermes.** Klein, unabhängig, jederzeit einschiebbar.
12. **Gruppe 13 — GitHub/Jira.** Erst nach Gruppe 4 (Voraussetzungen explizit im Audit benannt).
13. **Gruppe 14 — Deployment.** Läuft bereits als eigener Plan, nur `#823` nachziehen.
14. **Gruppe 15 — Alt-Issues.** Kein Sprint, sondern laufende Aufräumarbeit: bei Gelegenheit Body prüfen, schließen oder in die passende Gruppe einsortieren.
