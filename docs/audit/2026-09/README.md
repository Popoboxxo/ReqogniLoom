---
type: REVIEW
scope: audit-2026-09-index
status: final
date: 2026-09-30
author_agent: documenter
---

# Systemaudit 2026-09 — Einstiegspunkt

Dieser Ordner enthält den **vollständigen Systemaudit 2026-09**: 11
Workstreams, 9 Fachberichte, ein kanonisches Finding-Register, rund 100
Evidenz-Dateien und die drei Abschluss-Synthesen.

## Was das ist

Eine systematische Prüfung von ReqogniLoom auf **Korrektheit, Betriebssicherheit,
Nachweisbarkeit und Konsistenz** — nicht auf Vollständigkeit von Features.

| Aspekt | Wert |
|---|---|
| **Audit-Basis** | `main` @ `abd61aed` |
| **Branch** | `chore/system-audit-2026-09` |
| **Zeitfenster** | 2026-09-29 bis 2026-09-30 |
| **Befunde** | **280** Findings (14 Critical · 76 High · 115 Medium · 60 Low · 15 Info) + **5** bestätigte Kontrollen |
| **Klassifikation** | 264 `NEU` · 4 `BESTAETIGT` · 5 `WIDERLEGT` · 6 `BLOCKED` · 1 `DUPLIKAT` |
| **Änderungsgrenze** | ausschließlich Dokumentation. **Kein Produkt-Code wurde geändert**, kein Push, kein Branch-Rewrite. |

> **Warum nicht der Release-Cut?** `release/v1.8.0-beta.18` (`38da915f`) liegt
> zwei Commits über der Basis und enthält **keinen Image-Build, keinen Testlauf,
> kein CI-Artefakt**. Geprüft wurde der tatsächliche Produktstand. Begründung in
> [`AUDIT_SUMMARY.md` § 1.1](AUDIT_SUMMARY.md).

## Datei-Index — wer wozu dient

```
docs/audit/2026-09/
├── README.md                        ← DU STARTEST HIER
├── AUDIT_SUMMARY.md                 ← Lesefassung für Entscheider (Ampel, Top-10,
│                                      Fehlermuster, Vergleich mit dem Vor-Audit)
├── AUDIT_BACKLOG.md                 ← der umsetzbare Plan: 35 priorisierte Einträge
│                                      (P0…P3), Quick Wins, offene Entscheidungen
├── AUDIT_ADR_CANDIDATES.md          ← 8 Befunde, die eine ArchitekturENTSCHEIDUNG
│                                      brauchen (nicht nur einen Fix). Keine ADR geschrieben.
├── AUDIT_FINDINGS.md                ← KANONISCHES REGISTER (maßgeblich bei jedem Widerspruch)
├── AUDIT_EXTERNAL_INTEGRATIONS.md   ← WP-1a MCP · WP-1b LLM · WP-1d REST/Datenintegration
├── AUDIT_INFRASTRUCTURE.md          ← WP-1c Infrastruktur/Betrieb
├── AUDIT_NATIVE_PLUGINS.md          ← WP-2 native Plugins & Integrationen
├── AUDIT_UI_BROWSER.md              ← WP-3 echte Browsertests (Playwright/Chromium)
├── AUDIT_FRONTEND_STATIC.md         ← WP-3b statische Frontend-Analyse
├── AUDIT_DATA_MODEL.md              ← WP-4 Artefakt-/Datenmodell
├── AUDIT_TRACEABILITY.md            ← WP-5 Anforderungs-Traceability
├── AUDIT_SECURITY.md                ← WP-6a Security über alle Trust Boundaries
├── AUDIT_RELIABILITY.md             ← WP-6b Error Handling, Concurrency, Observability
└── AUDIT_EVIDENCE/                  ← Rohbelege: Matrizen, JSON-Messungen, Screenshots,
                                       Stack-Dumps, Issue-Inventar, Secret-Incident,
                                       verification-2026-09-30 (Gegenprüfung Top-10)
```

**Lesereihenfolge:** `README.md` → `AUDIT_SUMMARY.md` →
`AUDIT_BACKLOG.md` → bei Bedarf `AUDIT_FINDINGS.md` → dann der jeweilige
WP-Report → dann `AUDIT_EVIDENCE/`.

### Rolle der Dokumente

| Datei | Rolle | Wer schreibt sie |
|---|---|---|
| `AUDIT_FINDINGS.md` | **Formales Konsistenz-Gate.** Vereinheitlicht IDs, Schweregrade, Klassifikationen und Cross-Referenzen, adjudiziert Widersprüche (C1–C12) und macht die Belegbarkeit stichprobenweise prüfbar. **Der Index, nicht der Report.** | `validator` |
| WP-Reports (9 Dateien) | **Fachliche Bewertung.** Hier stehen Reproduktionsschritte, Auswirkung und Empfehlung ausformuliert. Hier bleibt die Original-Einstufung des jeweiligen Audit-Agenten nachvollziehbar. | 11 verschiedene Audit-Agenten |
| `AUDIT_EVIDENCE/` | **Rohbelege.** Jede Zahl ist hier auf eine Datei und eine Zeile zurückführbar. | dieselben Agenten |
| `AUDIT_SUMMARY.md` / `AUDIT_BACKLOG.md` / `AUDIT_ADR_CANDIDATES.md` | **Synthese ohne neue Fachanalyse.** Erfinden, entfernen und bewerten nichts neu. | `documenter` |

## Zählweise — Findings, Kontrollen, reservierte ID-Blöcke

Die Zahlen sind leicht falsch zu lesen. Drei Regeln:

**1. `PASS` ist kein Finding.** Eine als `PASS` klassifizierte Zeile ist eine
**bestätigte Kontrolle** — ein Negativbefund, kein Mangel. Sie steht getrennt in
[`AUDIT_FINDINGS.md` § 6](AUDIT_FINDINGS.md) und ist **nicht** in den 279
enthalten. **Begründung der Regel:** Würden Negativbefunde mitgezählt, stiege die
Gesamtzahl um 5 und die Verteilung würde systematisch zu Gunsten eines
WP-Reports verschoben.

**2. `BLOCKED` ist ausdrücklich kein `PASS`.** „Nicht verifizierbar" heißt
*nicht* „in Ordnung". 6 Findings und 12 offene Prüfpunkte sind so markiert
([§ 7](AUDIT_FINDINGS.md)).

**3. Reservierte ID-Blöcke sind keine Lücken.** Die 285 IDs belegen die
Nummernblöcke `001–025`, `030–067`, `070–093`, `100–206`, `220–241`, `270–288`,
`300–328` und `330–350` — **jede genau einmal** (verifiziert, § 12.2a).
Die als **RESERVIERT** markierten Bereiche (`026–029`, `068–069`, `094–099`,
`207–219`, `242–269`, `289–299`, `329`, alles ab `351`) sind **bewusst frei** für
Folge-Arbeit, damit parallele Agenten nicht erneut kollidieren.

**4. `WIDERLEGT` ist kein offener Mangel — und ein zurückgezogenes Finding zählt nicht.** Eine unabhängige Gegenprüfung der Top-10 (2026-09-30) hat `AUD-2026-09-070` **widerlegt**: `import_service.py:341-344` strippt Kommentarzeilen korrekt, der Round-Trip des eigenen Exporters funktioniert. Critical **14 → 13**, offene Findings **280 → 279**. Die Aussage bleibt als `WIDERLEGT` sichtbar ([§ 15.2](AUDIT_FINDINGS.md)).

**Die Evidenzbasis der Gegenprüfung war eingeschränkt:** Der Stack war **gestoppt**, es waren **0 Live-Messungen** möglich. Sie hat statisch und hermetisch gemessen. Jede ihrer Bestätigungen ist als *statisch/hermetisch bestätigt — Live-Nachweis nicht möglich* zu lesen ([§ 15.0](AUDIT_FINDINGS.md), [§ 11.1](AUDIT_SUMMARY.md)). **13 Teilaussagen** blieben offen — jeweils mit dem fehlenden Prüfschritt ([§ 15.4](AUDIT_FINDINGS.md)).

```
285 Zeilen in der Master-Tabelle
 = 280 Findings        (das, was gezählt und behoben werden muss)
 +   5 bestätigte Kontrollen (Negativbefunde, kein Mangel)
```

**Weiterhin im Register, aber nicht in den 285:** die CVSS-Spalte (nur WP-6a) und
die Originalwerte der P-Skala (WP-3/WP-3b). Beides ist **bewusst** nicht
vereinheitlicht — die Einstufung des jeweiligen Audit-Agenten bleibt
nachvollziehbar.

## Beziehung zum Vor-Audit

Der Vor-Audit liegt **außerhalb** dieses Ordners und wurde **nicht verändert**:

`docs/se/reports/deep_audit/system-audit-2026-09/`
(Prüf-HEAD `e3df119e`, Branch `feat/1031-bluepencil-host-bridge`,
47 kanonische Tracks `CR-01`…`CR-47`, System Health Score **1,4/5**,
0 konsolidierte P0, 20 P1 / 26 P2 / 1 P3).

| | Vor-Audit | Dieser Audit |
|---|---|---|
| Struktur | 13 Dateien, 109 Quellbefunde → 47 Tracks | 11 WP-Reports, 280 Findings |
| Browser-Nachweis | **keiner** | 28 Screens live |
| Live-MCP-Nachweis | **keiner** | 82 Rohpaare + 65-Fall-Isolationsmatrix |
| Plugin-E2E | **keiner** | beide Hermes-Plugins end-to-end |
| Restore-Nachweis | **keiner** | echter Restore 15/15 |
| CVE-Nachweis | **keiner** | **ebenfalls keiner** (BLOCKED) |
| Basis | gemischte Revisionsstände | einheitlich `main` @ `abd61aed` |

**Verhältnis der Zählungen:** ein `CR-NN`-Track ist ein *Vor-Audit-Track*, ein
`AUD-2026-09-NNN` ist ein *Befund*. Viele Tracks sind mehrere Befunde wert
(`CR-20` → 10 Findings). Die CR-Spalte im Register ist daher eine **Zuordnung,
keine Identität**. Die Spalte „CR-Track / Issue" zeigt auf: **34 der 47** Tracks
haben mindestens einen zugeordneten Befund. `CR-08` ist **widerlegt** (Race
behoben), `CR-24` im Kern **widerlegt** (beide Plugin-Verträge **sind** live
verifizierbar).

## Status-Schema

| Feld | Bedeutung |
|---|---|
| `status: final` | Der Bericht ist abgeschlossen und wird nicht mehr geändert. |
| `Status: offen` | Befund ist nicht behoben. **Alle** Findings dieses Audits stehen auf `offen` — **eine einzige** Ausnahme: `AUD-2026-09-220` steht auf `TEILWEISE BEHOBEN` (Key widerrufen, Historie offen). |
| `geschlossen (WIDERLEGT)` | Befund war ein Fehlalarm oder eine überholte Aussage; die Widerlegung ist **im Register sichtbar** und nicht aus der Zählung entfernt. |
| `offen – BLOCKED` | Nicht verifizierbar. **Kein PASS.** |
| `Kontrolle bestätigt` | Negativbefund, kein Mangel (§ 6). |

**Schweregrade:** Critical = Betriebs-/Datenverlust, Sicherheitsvorfall oder
Kernfunktion fällt aus · High = Funktionsverlust oder Vertragsbruch unter
Realbedingungen · Medium = Korrektheits-, Drift- oder Messlücke ohne akuten
Ausfall · Low = Hygiene, Struktur, Dokumentation · Info = Beobachtung,
Präzisierung, Negativbefund.

## Bekannte Einschränkungen

1. **Mojibake in Grep-Ausgaben.** Zeichenketten wie `Ã¶` in manchen
   Konsolenausgaben sind ein **Anzeigeartefakt** des Grep-Toolings. Alle Dateien
   in diesem Ordner sind valides UTF-8 (verifiziert: **0** Replacement-Char,
   **0** Decode-Fehler). **Keine Kodierungsreparatur nötig oder durchgeführt.**
2. **`AUDIT_EVIDENCE/stack-seeds.md` ist bewusst NICHT committet.** Die Datei
   enthält **Demo-Credentials** im Klartext. Sie liegt lokal im Arbeitsbaum,
   steht in keinem Commit und gehört nicht in den Ordner. Wer sie liest, treatet
   den Inhalt als Anmeldedaten des laufenden Audit-Stacks — nicht als
   Veröffentlichungsmaterial.
3. **Zweitmessung-Regel.** Für WP-3/WP-3b stammen die maßgeblichen Zahlen aus
   einer **zweiten, methodisch korrigierten** Messung; wo beide Agenten dasselbe
   Objekt gemessen haben (i18n-Lücke, Hex-Literale, E2E-Selektoren), gilt die
   **WP-3b-Zahl**. Für die WPs **ohne** zweite Messung ist die Validität der
   Zahlen **nicht** durch eine unabhängige Gegenmessung abgesichert — das ist
   eine Restunsicherheit dieses Audits, keine Feststellung zu einem Produktdefekt
   ([§ 14.1](AUDIT_FINDINGS.md)).
4. **Das Audit hat selbst ein Secret committet.** `AUD-2026-09-220` / P-1: ein
   live gültiges `write`-API-Key wurde im Evidenz-JSON committet. **Widerrufen**
   am 2026-09-30, Arbeitsbaum redigiert — **Git-Historie offen**. Der zweite
   gefundene Key `ff77bbd0-…` ist **eskaliert, aber nicht widerrufen**. Das ist
   der teuerste Prozessdefekt des Audits und steht deshalb hier, nicht versteckt
   im Register.
5. **BLOCKED heißt nicht geprüft.** 6 Findings und 12 Prüfpunkte konnten nicht
   verifiziert werden — darunter Stack-Erzeugung, echte LLM-Provider-Antworten,
   CVE-/SBOM-Scan, Restore-Abbruch mitten drin, Auth-Flow mit manipulierten JWTs
   und Frontend-Bundle-Größe. Vollständige Listen: [`AUDIT_FINDINGS.md` § 7](AUDIT_FINDINGS.md).
6. **13 der 47 Vor-Audit-Tracks haben keinen zugeordneten Befund.** Das ist
   **keine** Entwarnung: sie wurden entweder nicht erneut geprüft oder sind ohne
   CR-Nennung subsumiert.
7. **`CR-30`-Zahl offen.** Vor-Audit 463, WP-5 511, reproduzierbar **443 von
   8127**. Die Methoden sind im Register (C10) offengelegt, die Entscheidung ist
   als offener Punkt **O-6** an den User gegeben.

## Nächste Schritte

1. **P0 entscheiden** — [`AUDIT_BACKLOG.md` § 2](AUDIT_BACKLOG.md): 6 Einträge,
   darunter die Historie-Entscheidung zum Secret-Leak.
2. **Offene Fragen beantworten** — [`AUDIT_BACKLOG.md` § 6](AUDIT_BACKLOG.md):
   History-Rewrite, geschlossene Issues mit fortbestehender Wirkung, `CR-30`-Zahl,
   Doku-Drift.
3. **Architekturfragen entscheiden** — [`AUDIT_ADR_CANDIDATES.md`](AUDIT_ADR_CANDIDATES.md):
   8 Kandidaten. **Erst** die Entscheidung, **dann** die Umsetzung.
4. **Nicht vergessen** — [`AUDIT_SUMMARY.md` § 7](AUDIT_SUMMARY.md): Transaktionen
   12/12 atomar, Hot-Paths 0,12–2,95 ms, 0 Tenant-Leaks in 120 Proben, 0 PII in
   Logs, 39/39 Stichproben belegt. **Ein Audit, das nur Defekte zählt, ist
   unvollständig.**

---

*Erstellt von `documenter` am 2026-09-30. Der Vor-Audit unter
`docs/se/reports/deep_audit/system-audit-2026-09/` ist unverändert; die
WP-Reports, `AUDIT_FINDINGS.md` und `AUDIT_EVIDENCE/` wurden nicht überschrieben.*

