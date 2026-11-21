# Listen-Modus für alle Clients: Entwurfsplan (Draft)

> **Status:** **Entwurf, nicht ausführbar.** Arbeitspakete und Gates, **keine** Tasks. Tasks entstehen erst nach den Freigaben in Abschnitt 4.
> **Stand:** 2026-11-21. Basis `origin/main` `fafa4610`, Server 1.9.0-beta.5, Plugin 1.9.0-beta.4.
> **Spec:** [`../specs/2026-11-21-listen-modus-alle-clients-design.md`](../specs/2026-11-21-listen-modus-alle-clients-design.md) (Ist-Stand, Zielarchitektur, Server-Vertrag, Konformitätsszenarien S1–S12, Entscheidungen D1–D11).
> **Vorgänger:** [`Archive/2026-10-07-umsetzungsplaene-1155-1201-1202-1204.md`](../../plans/Archive/2026-10-07-umsetzungsplaene-1155-1201-1202-1204.md) (Hermes-Zuhörmodus), ADR-019.

## 1. Ziel

Das Plugin erfasst im Gespräch automatisch **Anforderungen**, die **Architektur des Objekts** und **Entscheidungen samt Zusammenhängen** und legt sie als **Vorschläge** zur Bestätigung ab (nie stilles Anlegen). Das gilt **funktional gleich in allen Clients** (Claude Code, Codex, OpenCode V1/V2, Kimi Code, Antigravity, Hermes), gemessen an den Szenarien S1–S12 der Spec.

## 2. Kernaussagen der Analyse

- Der Server hat **keinen** Aufruf „Text rein, Vorschläge raus" und **keine** Art von Vorschlag für Anforderung, Architektur oder Entscheidung aus Freitext. Das Hermes-Plugin umgeht das über den `interview.*`-Weg mit lokaler Warteschlange (und wurde nie live getestet).
- **Gleichheit entsteht durch einen zentralen Aufruf `suggestion.capture`** (Filter, Schwärzung, Duplikatsschutz, Prüfung, Posteingang auf dem Server) und **dünne Anschlüsse** je Client.
- Für alle Clients gibt es nach der Doku einen Hook auf die Nutzernachricht, aber **kein einziger wurde ausgeführt**. Zuverlässigkeit ist offen (Claude Code: ältere Fehlerberichte, OpenCode V1: TUI-Lücke, Kimi: Feldname, Antigravity: kein Submit-Ereignis).
- Ein Client **ohne** Hook kann nur die Modell-Variante und ist **nicht gleichwertig**.

## 3. Entscheidungsstand

| Thema | Stand |
|---|---|
| Anforderung und Rahmen („funktional gleich", Vorschläge statt Anlegen) | **von Daniel gesetzt** |
| D1 bis D11 | **offen**, Empfehlungen in der Spec, werden **einzeln** geklärt |
| Reihenfolge der Clients | Vorschlag D10: Claude Code, Hermes, OpenCode, Codex, Kimi, Antigravity |

## 4. Arbeitspakete und Gates

Aufwände sind **grobe Schätzungen in Tasks**, kein Versprechen. Sie überlappen nicht.

| AP | Inhalt | Voraussetzung | Grober Aufwand |
|---|---|---|---|
| **AP0** | **Probeläufe** (kein Produktcode): P0.1 Claude Code (async `UserPromptSubmit` in einem Wegwerf-Plugin, Nutzdaten, Umgebung, `--debug-file`, `/reload-plugins`, `type: http`), P0.2 Codex, P0.3 Kimi (Feld bei `UserPromptSubmit` gegen `Queued`), P0.4 Antigravity, P0.5 OpenCode V1 und V2 (TUI, `await`), P0.6 Server: Kosten und Latenz eines zustandslosen Aufrufs gegen `interview.chat` | **G0** | je Client 1 bis 2, Server 1 |
| **AP1** | **Server-Kern:** `suggestion.capture` (REST und MCP), Art `artifact_create` aktivieren, Prüfung der Antwort, Duplikatsschutz mit Bestandsabgleich, Schwärzung, Grenzen, Workspace-Schalter, Audit und Token-Zählung, Rechte (D2), Migration, Tests | **G1, G2** | ca. 14 bis 18 |
| **AP2** | **Gemeinsamer Relay** und **Konformitätsfolge** S1–S12 gegen einen Attrappen-Server und gegen den echten Server | AP1 teilweise | ca. 8 bis 10 |
| **AP3** | **Claude-Code-Anschluss:** `hooks/hooks.json`, Skill `/reqogniloom:listen`, `userConfig`-Option, Status, Filter für `/loop`, Doku | AP0 P0.1, AP2 | ca. 6 |
| **AP4** | **Hermes umstellen** auf `suggestion.capture`, lokale Warteschlange und `interview.*`-Pfad entfernen, H1 bis H8 beheben | AP1, AP2 | ca. 6 |
| **AP5** | **OpenCode** (ein Paket, zwei Einstiege), **Codex**, **Kimi**: je Paket, Installer, Schalter, Doku | AP0, AP2 | OpenCode ca. 7, Codex ca. 4, Kimi ca. 5 |
| **AP6** | **Antigravity** (Entdoppelung, Abkoppeln) und **Stufe C** (Skill-Anweisung) als dokumentierte Notlösung | AP0 P0.4 | ca. 5 |
| **AP7** | **Dokumentation und Matrix:** Zeile „Hooks / Mithörmodus" je Client mit belegtem Status (#2001), Datenschutz-Seite (Datenfluss, Aufbewahrung), Hinweis beim Einschalten | alle | ca. 4 |

**Gates:**

| Gate | Inhalt | Wer gibt frei |
|---|---|---|
| G0 | Entscheidungen D1 bis D11 getroffen (mindestens D1 bis D5, D9) | Daniel |
| G1 | Ergebnisse AP0: je Client Stufe A, B oder C **belegt**; Kosten und Latenz bekannt | Daniel |
| G2 | **Neuer ADR** (Ergänzung zu ADR-019: Recht `capture`, Datenschutz des Rohtexts) akzeptiert | Daniel |
| G3 | Datenschutz-Prüfung: Schwärzung, Aufbewahrung, Hinweis beim Einschalten, Datenfluss zum Modellanbieter | Daniel |

## 5. Querschnittsregeln

1. **Frische-Check** vor jeder Ausführung: `python scripts/check_plan_refs.py` gegen aktuellen `origin/main`.
2. **Migrationen** (AP1) nacheinander mergen und renummerieren.
3. **Tool-Zähler:** `suggestion.capture` ist ein neues MCP-Tool (301 → 302), Zähler-Gates und `docs/agent-templates/tool-manifest.json` nachziehen; mit den anderen Plänen abstimmen, die den Zähler ändern.
4. **Keine Aussage ohne Probelauf:** Eine Zelle der Fähigkeiten-Matrix wird erst grün, wenn S1 bis S12 für den Client bestanden sind.
5. **Standardwerte sicher:** Schalter aus, Workspace-Schalter aus, Datenschutzhinweis beim Einschalten.
6. **Commit- und PR-Texte als Datei**, Volltests nur nacheinander.

## 6. Offene Fragen (einzeln mit Daniel)

| ID | Frage | Empfehlung |
|---|---|---|
| D1 | Neuer Aufruf `suggestion.capture` oder `interview.*` weiterverwenden? | neuer Aufruf |
| D2 | Rechte: a) zwei Keys, b) Capture für Nutzer-Keys, c) neues Recht `capture`? | c), mit neuem ADR |
| D3 | Erfassen: nur Nutzernachrichten oder auch Assistententext und Werkzeug-Ausgaben? | nur Nutzernachrichten |
| D4 | Schalter: lokal, serverseitig oder beides? | beides, Standard aus |
| D5 | Rohtext speichern? | nein, nur normalisierter Auszug und Hash |
| D6 | Wo entscheidet der Mensch? | Web-Posteingang plus MCP-Befehle im Chat |
| D7 | Rauschkontrolle | Regelfilter, billiges Vor-Urteil, Obergrenzen |
| D8 | Arten in Version 1 | Requirement, ArchitectureElement, Adr, StakeholderNeed plus Verknüpfungen |
| D9 | Relay-Technik R1, R2, R3 | nach AP0 |
| D10 | Reihenfolge der Clients | Claude Code, Hermes, OpenCode, Codex, Kimi, Antigravity |
| D11 | Architektur aus bestehendem Code mit aufnehmen? | nein, eigene Spec |

## 7. Nächste Schritte

1. D1 bis D5 und D9 mit Daniel klären (G0).
2. AP0 starten, **zuerst P0.1** (Claude Code, lokal ausführbar) und P0.6 (Server).
3. Für die Clients, deren Probelauf Zugangsdaten braucht (Codex, Kimi, OpenCode), klären, wer die Läufe macht.
4. Nach G1 und G2: Tasks je Arbeitspaket nach `superpowers:writing-plans` schreiben, mit Frische-Check.

## 8. Risiken (Auszug, vollständig in der Spec, Abschnitt 9)

| Risiko | Gegenmaßnahme |
|---|---|
| Hook funktioniert in einem Client nicht zuverlässig | AP0 vor jedem Bau, Stufe C nur als ausgewiesene Notlösung |
| Nachrichtentext verlässt den Rechner | Standard aus, Schwärzung, Hinweis, G3 |
| Modellkosten und Latenz je Nachricht unbekannt | P0.6 messen, Obergrenzen, billiges Vor-Urteil |
| Zu viele oder schlechte Vorschläge | Duplikatsschutz mit Bestand, Obergrenze, Rückmeldung der Annahmequote |
| Sechs Anschlüsse pflegen | ein Relay-Vertrag, Konformitätsfolge als Gate |

## 9. Grenzen dieses Entwurfs

- **Kein Hook wurde ausgeführt.** Alle Client-Aussagen stammen aus Doku-Zusammenfassungen oder dem Lesen des Hermes-Codes (belegt mit Datei und Zeile).
- Das Hermes-Plugin wurde nie live getestet, Aussagen zu seinem Verhalten beruhen auf dem Code und seinen Unit-Tests.
- Lastverhalten, mehrere Nutzer je Workspace und Cloud-Sitzungen sind nicht untersucht.
