---
type: REVIEW
scope: audit-review-summary
status: final
date: 2026-10-01
author_agent: documenter
branch: chore/audit-review-2026-09
source:
  - docs/audit/2026-09/review/AUDIT_REVIEW_FINDINGS.md
  - docs/audit/2026-09/review/AUDIT_REVIEW_METHOD.md
  - docs/audit/2026-09/review/evidence/REVIEW_WP1A.md
  - docs/audit/2026-09/review/evidence/REVIEW_WP1B.md
  - docs/audit/2026-09/review/evidence/REVIEW_WP1C.md
  - docs/audit/2026-09/review/evidence/REVIEW_WP1C_SUPP.md
  - docs/audit/2026-09/review/evidence/REVIEW_WP1D.md
  - docs/audit/2026-09/review/evidence/REVIEW_WP2.md
  - docs/audit/2026-09/review/evidence/REVIEW_WP3.md
  - docs/audit/2026-09/review/evidence/REVIEW_WP4.md
  - docs/audit/2026-09/review/evidence/REVIEW_WP5.md
  - docs/audit/2026-09/review/evidence/REVIEW_WP6A.md
  - docs/audit/2026-09/review/evidence/REVIEW_WP6B.md
  - docs/audit/2026-09/review/evidence/REVIEW_LIVE_CRITICALS.md
---

# AUDIT_REVIEW_SUMMARY — Entscheider-Fassung der Audit-Review

> **Rolle dieses Dokuments.** Entscheider-Fassung. Es aggregiert ausschließlich die
> vorhandene Review-Evidenz der Zweitprüfung (`AUDIT_REVIEW_FINDINGS.md`,
> `AUDIT_REVIEW_METHOD.md` und die `REVIEW_*`-Evidenzdateien). **Keine neue
> Fachanalyse.** Alle Zahlen sind wörtlich aus `AUDIT_REVIEW_FINDINGS.md`
> übernommen und nicht neu berechnet.

---

## 1. Verdikt in einem Absatz

**Ja, das Audit trägt.** Die adversariale Zweitprüfung bestätigt den überwiegenden
Teil der Befunde: von 233 geprüften Findings sind **152 vollständig bestätigt**
und **60 teilweise** (Sachkern haltbar, Details/Zahlen/Zitate zu korrigieren) —
zusammen rund **91 %** im Sachkern belastbar. Nur **4 Findings (≈ 1,7 %) sind
sachlich FALSCH**, 12 weitere (≈ 5,2 %) sind in der Wirkung ÜBERZOGEN. Die
Abdeckung ist mit **233/279 ≈ 83,5 %** hoch, und die risikorelevanten Klassen
wurden **vollständig** geprüft (Critical 14/14, High 76/76 = 100 %). Die
Schwächen liegen systematisch in **Schweregrad-Überschätzung** (27 Korrekturen),
**Zahlen-/Zitat-Ungenauigkeit** und **Register-Hygiene** — nicht im erfundenen
Sachverhalt. Das Audit ist als Grundlage für die Fix-Priorisierung tauglich,
benötigt aber die hier vorgenommene Schweregrad- und Register-Korrektur.

---

## 2. Genauigkeitsquote

| Kennzahl | Wert | Bezug |
|---|---:|---|
| Geprüfte Findings | **233 von 279** | **≈ 83,5 %** Abdeckung |
| davon Critical (geprüft/gesamt) | **14/14** | **100 %** |
| davon High | **76/76** | **100 %** |
| davon Medium/Low/Info | **143/189** | **≈ 75,7 %** |
| Vollständig BESTAETIGT | **152** | **≈ 65,2 %** der geprüften |
| TEILWEISE (Sachkern haltbar) | **60** | zusammen mit BESTAETIGT **≈ 91,0 %** |
| FALSCH | **4** | **≈ 1,7 %** (042, 121, 204, 283) |
| ÜBERZOGEN | **12** | **≈ 5,2 %** |
| NICHT VERIFIKABAR | **3** | 156, 190, 009 |
| KEIN REQOGNILOOM-BEZUG | **2** | 239, 152 |
| UNTERSCHAETZT | **0** (1 Zusatzattribut: AUD-002) | — |
| Schweregrad-Korrekturen | **27** | Ab-/Hochstufungen |

**Lesart.** „Genauigkeitsquote" = **≈ 65 % voll bestätigt**; fasst man die
teilweise bestätigten Befunde als „im Kern richtig, im Detail nachzubessern"
hinzu, sind **≈ 91 %** sachlich haltbar. Dem stehen **4 FALSCH** und **12
ÜBERZOGEN** gegenüber — überwiegend falsche Einzelzahlen, falsche Zitate oder
eine zu hohe Einstufung, selten ein falscher Sachkern. Die Abdeckung erreicht
bei den risikorelevanten Klassen **100 % (Critical/High)** und insgesamt
**83,5 %**.

---

## 3. Fehlerklassen-Verteilung

Nicht disjunkt — ein Finding kann mehrere Klassen tragen. Nennungen wörtlich aus
`AUDIT_REVIEW_FINDINGS.md` §1.3.

| Fehlerklasse | Nennungen | Belegte IDs (Auszug) |
|---|---:|---|
| Severity falsch eingestuft (auf-/abgestuft) | 27 | 034, 052, 056, 060–066, 077, 101, 110, 117, 121, 122, 130, 134, 142, 147, 161, 180, 228, 273, 282, 327, 345, 346 |
| Sachkern falsch (Verdikt FALSCH) | 4 (+6 Teil-FALSCH) | FALSCH: 042, 121, 204, 283 · Teil-FALSCH: 006, 016, 021, 088, 153, 234 |
| Duplikat / Doppelführung / stale Referenz | 10 Beziehungen | 345→123, 346→052, 143=#1019, 241↔148, 121(b)↔125/270, 231↔055/063, 221↔030, 227↔184/185, 002/016/300, 349→070 |
| Fehlzitat (falscher `file:line`-Anker) | 12 | 032, 042, 053, 067, 074, 076, 080, 086, 139, 222, 280, 282 |
| Scope-Verfehlung (kein Produktbezug) | 2 (+2 Orts-/Sync-Hygiene) | 239, 152 · Hygiene: 204 (Register-Sync), 220 (Fundort am HEAD redigiert) |
| Zahlenfehler (nicht reproduzierbar/falsch) | 22 | 001, 002, 039, 085, 130, 132, 142, 147, 156, 160, 180, 188, 192, 193/195, 225, 234, 287, 300, 302, 303, 310, 311, 325 |

**Muster.** Fehler konzentrieren sich auf (a) **Überschätzung des Schweregrads**,
(b) **Unter-/Falschzählungen** (112 statt 116; 511 statt 443; 41 statt 34 Dateien;
453 statt ~406 Requests), (c) **snapshot-/umgebungsgebundene Absolutwerte**
(5914 statt 2425; 160 MB statt 128 MB) und (d) **Zeilenverschiebungen/falsche
Modulpfade** bei ansonsten korrektem Sachkern.

---

## 4. Scope-Urteil: Produkt vs. Framework/Tooling/Audit-Prozess

**Urteil: Das Audit ist überwiegend produktbezogen** — die beiden als
`KEIN REQOGNILOOM-BEZUG` klassifizierten Findings (239 Audit-Prozess, 152
Audit-Track-Prozess) sind **2 von 233 ≈ 0,9 %**. Der Befund-Pool adressiert
ReqogniLoom-Software (Backend, MCP, REST, Datenmodell, Infrastruktur, Security,
Reliability, UI, Plugins).

**Aber:** Es gibt echte Scope-Verfehlungen und Hygiene-Vermischungen:

- **239** (Audit-Prozess / fehlender Evidenz-Redactor) und **152** (Vorab-Track
  CR-24) sind Prozess-, nicht Produktgegenstand.
- **220** (der Audit selbst erzeugte die Secret-Leakage) ist ein Produkt-Security-
  Finding mit **audit-prozessualer Ursache** — beides in einem Befund vermischt.
- **WP-5 (Traceability)**: Die Findings 330–350 betreffen die **SE-Doku-/Matrix-
  Hygiene** (`docs/se/**`, Traceability-Matrix, REQ-Frontmatter) — legitime
  Repo-Artefakte, aber Doku-Hygiene statt Laufzeitcode; der Audit behandelt sie
  teils wie Produktdefekte.
- **Register-Hygiene (204, 220-Fundort, 193-Zahl)**: Sync-/Ortsfehler im Audit-
  Register, nicht im Produkt.

**Fazit:** Keine Verzettelung in Framework/Tooling/Umgebung; die
Audit-Prozess-Anteile sind identifiziert, quantitativ klein und sauber
abgrenzbar. Die Scope-Verfehlungen sind als Lehre relevant (Evidenz-Redactor,
Cleanup-Checkliste), ändern aber den Produktfokus des Audits nicht.

---

## 5. Ampel je Workpackage

| WP | Gegenstand | Ampel | Korrigierte Einschätzung |
|---|---|---|---|
| **WP-1a** | MCP Server | 🟢/🟡 | 13 BESTAETIGT, 2 Critical: 030 TEILWEISE (Mechanik ja, „13 Endpoints" = Proben), 031 BESTAETIGT. 042 FALSCH (Multi-Interview startbar). Kern trägt. |
| **WP-1b** | LLM-Adapter | 🟡 | Kein FALSCH, aber **8 von 15** Schweregraden zu hoch (052 Critical→High; 061/062/066→Medium; 056/060/063/065→Low). 055/057 BESTAETIGT (057 verschärft). |
| **WP-1c** | Infrastruktur | 🟢 | 8 BESTAETIGT; 123 Critical und 120 (live) halten; 122 ÜBERZOGEN (Critical→High, toter Legacy-Pfad); 129 TEILWEISE („degraded→200" falsch, Kern-Gap bleibt). |
| **WP-1c-Supp** | Infra-Ergänzung / Live | 🟢 | 120 live exakt bestätigt; **121 FALSCH** (Headline „Beat dispatcht nie"; Rest Low); 130/134/142/147 heruntergestuft. |
| **WP-1d** | REST API & Data Integration | 🟢 | 071/072/073/074/078 BESTAETIGT (071 Critical hält); 077 ÜBERZOGEN (X-Request-ID-Header existiert). Schwäche = Zitat-Präzision. |
| **WP-2** | Native Plugins | 🟢/🟡 | 115 Critical BESTAETIGT (stärkster Fund); 109/112/113 bestätigt; 101/110/117 ÜBERZOGEN; 152 kein Bezug. |
| **WP-3 / 3b** | UI | 🟡 | High 003/300/301 sauber; Defekte = **Zahlungenauigkeit** (001, 002, 300, 310) und Mechanik-Fehlbeschreibung (016); 006/021 Teil-FALSCH; 009 nicht statisch prüfbar. |
| **WP-4** | Datenmodell | 🟡/🟢 | 24 BESTAETIGT, 4 State-Bypass-Pfade bestätigt; „DB schützt nichts"-Prämisse bei 180/184/186 durch **Messmethodik-Fehler** (FK-/RLS-Auflösung) entkräftet; 325 zählt 3 statt 4. |
| **WP-5** | Traceability / SE-Doku | 🟡 | Kernzahlen **exakt** (835/511/324/443); aber **204 FALSCH** (stale Registerzeile), 345/346 Duplikate, 192/348 Etiketten-Verwechslung. |
| **WP-6a** | Security | 🟢 | 2 Critical (220, 221) bestehen; 221 live belegt, 220 Fakten bestätigt/Widerruf unbelegt; 239 kein Produktbezug; 228 auf Low; **neue Lücken** gefunden. |
| **WP-6b** | Reliability / Concurrency / Observability | 🟢/🟡 | 15 BESTAETIGT (270/281/287 live); **283 FALSCH** (Bus-Namensverwechslung); 273/282 ÜBERZOGEN. |

---

## 6. Korrigierte Critical-Zahl

Das Register führte **14 Critical** (13 offen + die zurückgezogene Kontrolle
`AUD-070`). Nach der Zweitprüfung gilt:

| Original-ID | Verdikt | Korrigierter Schweregrad |
|---|---|---|
| AUD-030 | TEILWEISE | **Critical** (hält) |
| AUD-031 | BESTAETIGT | **Critical** (hält) |
| AUD-071 | BESTAETIGT | **Critical** (hält) |
| AUD-115 | BESTAETIGT | **Critical** (hält) |
| AUD-120 | BESTAETIGT | **Critical** (hält) |
| AUD-123 | BESTAETIGT | **Critical** (hält) |
| AUD-220 | TEILWEISE | **Critical** (hält; Historie offen) |
| AUD-221 | BESTAETIGT | **Critical** (hält, live belegt) |
| AUD-052 | TEILWEISE | **Critical → High** |
| AUD-122 | UEBERZOGEN | **Critical → High** |
| AUD-121 | **FALSCH** (Headline) | **Critical → Low** (Rest: Healthcheck + Duplikat 125/270) |
| AUD-345 | TEILWEISE | **Critical → Medium** (eigenständig; **Duplikat von AUD-123**) |
| AUD-346 | TEILWEISE | **Duplikat von AUD-052** (kein eigener Schweregrad) |
| AUD-070 | Kontrolle (zurückgezogen) | nicht als Critical geführt |

**Ergebnis: 8 der 13 offenen Criticals halten als eigenständige Critical**
(030, 031, 071, 115, 120, 123, 220, 221). **5 werden herabgestuft bzw. als
Duplikat geführt** (052→High, 122→High, 121→Low/FALSCH, 345→Medium/Duplikat 123,
346→Duplikat 052). Die im Audit kommunizierte Critical-Zahl ist damit **um 5
überhöht** — davon 2 echte Duplikate (345/346).

---

## 7. Secret-Leak-Status (Fakt, kompakt)

- **Commit `3dcc80d8`** enthält **2 JSON-Evidenzdateien**
  (`wp1d-auth-pagination-filter-errors-live.json`,
  `wp1d-tenant-leak-matrix.json`) mit einem live gültigen `reqlo_`-Key
  (Owner `admin`, Scope `write`, ohne Expiry).
- **Nie gepusht:** `git merge-base --is-ancestor 3dcc80d8 origin/…` → **exit 1**
  gegen alle Remote-Refs; keine externe Kopie.
- Der Key überlebt **lokal als historischer Blob** im Commit-Baum; der
  Arbeitsbaum am HEAD ist **redigiert** (`git grep … HEAD -- docs/audit` → 0).
- **Widerruf dokumentiert-gemeldet** (HTTP 204, `revoked_at` gesetzt), aber
  **ohne laufende DB nicht live nachbestätigt** → Status „TEILWEISE BEHOBEN".
- **Zweiter live Key** `ff77bbd0…` in `AUDIT_EVIDENCE/stack-seeds.md`
  (**untracked**) wurde **nicht widerrufen** (Auftrag begrenzte DB-Änderung auf
  genau einen Key); plus 8 weitere aktive `admin`-Keys ohne Expiry/Fence.
- **Entscheidung:** History-Rewrite (`git filter-repo`) vor dem ersten Push;
  bis dahin bleibt AUD-220 Critical.

*(Details: `AUDIT_EVIDENCE/secret-incident-2026-09-30.md`; keine Klartext-Keys
in diesem Dokument.)*

---

## 8. Live vs. nicht verifiziert (kurz)

- **Live BESTAETIGT:** 030 (MCP hängt 8 s), 031 (Health 200 bei Redis down),
  073/074 (500/ungepaggt), 120 (4×-Zustellung), 221 (Rate-Limit vor AuthN),
  sowie DB-gestützt 281/285/287/288 und `celery inspect` (270).
- **Live TEILWEISE:** 052 (Shipped-Default `mock`, kein Fehlschlag).
- **Live FALSCH:** 121 (Beat dispatcht doch; „0× Sending due task" = Log-Artefakt).
- **NICHT live verifiziert (Mutation/Scoped-User nötig):** 071 (ReqIF-Import),
  222 (Workspace-Fence) — Mechanik statisch belegt.
- **Nicht ausgeführt (read-only-Grenze):** 196/199 (`vitest run`), 193/195
  (`pytest --collect-only`), 009 (Browser-Messung), 190 (Diff-Engine), 205.
- **Externe Fakten ohne Netz:** 052/053 (Provider-Retirement), 164 (#940).
- **Host-Integration:** Hermes-Desktop bleibt BLOCKED.

Methodik und fehlende Prüfschritte im Detail: `AUDIT_REVIEW_METHOD.md`.

---

## 9. Empfehlung / offene Punkte

1. **Secret:** History-Rewrite vor dem ersten Push dieses Branches; Bundle-Backup
   anlegen, danach SHA-Verweise in den Audit-Dokumenten aktualisieren. Zweiten
   live Key `ff77bbd0…` und die 8 weiteren `admin`-Keys widerrufen/rotieren.
2. **Register-Korrekturen:** 121 auf FALSCH/Low, 204 auf FALSCH/durch 121+270
   ersetzt, 345 als Duplikat 123, 346 als Duplikat 052, 052→High, 122→High,
   129-Kurzformulierung korrigieren; 193-Zahl auf 443, i18n-Zahl vereinheitlichen.
3. **Fix-Priorisierung:** Zuerst die 8 haltenden Criticals (030/221 Redis-Pfad,
   031 Health-Blindheit, 071 ReqIF-`success`, 115 Plugin-`TypeError`, 120
   4×-Zustellung, 123 Restore-Pfad, 220 Secret-Historie, 222-Fence/Key-Scope).
4. **Neu erfasste Lücken** (siehe `AUDIT_REVIEW_CORRECTED_TOP.md`, Markierung
   `NEU-AUDIT-LUECKE`) in das Register übernehmen und priorisieren —
   insbesondere Webhook-Secret im Klartext, REST-seitig nicht durchgesetzte
   API-Key-Workspace-Fence und Outbox-Abonnenten-Idempotenz.
5. **Strukturell:** Secret-Scan-Pflichthook + Evidenz-Redactor (behebt die
   Ursache von 220/239); Messmethodik bei DB-Constraints (FK/RLS über
   `pg_constraint` auflösen); Audit-Snapshot (Migrations-/Datenstand) festhalten.

---

*Entscheider-Fassung, erstellt durch `documenter` am 2026-10-01. Aggregation der
Review-Evidenz; keine neue Fachanalyse, kein Produktcode geändert, kein Push,
keine Secrets (nur maskierte Referenzen).*
