---
adr_id: ADR-018
title: "i18n-Vertrag: Inline-Default nur mit monoton sinkendem Ratchet, dynamische Keys ohne Typschema verboten"
status: proposed
date: "2026-10-03"
deciders: [user, senior-developer]
affected_reqs: [REQ-L0-009, REQ-L1-016, REQ-L1-094, REQ-L2-RF-001, REQ-L2-RF-034, REQ-L2-RF-035, REQ-L2-RF-036, REQ-L2-RF-037, REQ-L2-RA-004]
superseded_by: null
---

# ADR-018: i18n-Vertrag: Inline-Default nur mit monoton sinkendem Ratchet, dynamische Keys ohne Typschema verboten

**Status:** proposed (Empfehlung — Freigabe durch User/Review offen)
**Datum:** 2026-10-03
**Entscheider (vorgeschlagen):** user, senior-developer
**Betroffene REQs:** REQ-L0-009 (SN-09: Zweisprachige Benutzeroberfläche,
`docs/se/L0/SN_Stakeholder_Needs.md:173`), REQ-L1-016 (Zweisprachige Benutzeroberfläche,
`docs/se/L1/Gesamtsystem/L1_Gesamtsystem_Requirements.md:391`), REQ-L1-094 (i18n key naming
convention for ArtifactInspector, ebd. `:2408`; Status in
`docs/se/traceability-matrix.md:185` = `Not Implemented`), REQ-L2-RF-001 (Frontend-i18n mit
react-i18next, `docs/se/L1/Gesamtsystem/L2/ReactFrontendSystem/
L2_ReactFrontendSystem_Requirements.md:31`), REQ-L2-RF-034..037 (ArtifactInspector
Shell/Panels, i18n-Key-Tree `sidebar.*`, ebd. `:831-961`), REQ-L2-RA-004
(Backend-Fehlermeldungen i18n, `docs/se/L1/Gesamtsystem/L2/RestApiAdapterSystem/
L2_RestApiAdapterSystem_Requirements.md:113`)

**Bezug:** Audit-Kandidat **#6** (`docs/audit/2026-09/AUDIT_ADR_CANDIDATES.md:270-317`),
Implementation-Plan-Slot **ADR viii** (`docs/audit/2026-09/review/IMPLEMENTATION_PLAN.md:227`),
Arbeitseinheit `DOC-02` (`docs/audit/2026-09/review/plan/TRACE_DOCS.md:37-47`). Findings
`AUD-2026-09-300`, `-301`, `-002`, `-016`, `-303`, `-304`, `-302`, `-322`, `-348`.

**Bezug zum Code:** `frontend/src/test/i18n-parity.test.ts:186`
(`MISSING_KEY_BASELINE = 116`), `:94-99` (`T_CALL_PATTERN` erfasst nur
String-Literale als erstes `t()`-Argument; dynamische Keys werden **absichtlich** nicht
statisch geprüft), `:202-223` (Ratchet: rot nur bei **Anstieg**);
`frontend/src/i18n/index.ts:22-23` (`lng`-Auswahl + `fallbackLng: "en"`);
`frontend/src/i18n/locales/{de,en}.json`.

**Review-/Lifecycle-Vermerk:** Dieses ADR ist **`proposed`**. Es formuliert eine begründete
**Empfehlung**, keine freigegebene Entscheidung. Die Freigabe erfolgt durch den User nach
Review (`concept-reviewer`); erst dann darf der Status wechseln. Die abhängige Umsetzung
(`DOC-02`) beginnt **nach** der Freigabe.

---

## Kontext

**1. Die Lücke ist Teil des Soll-Zustands.** 116 Keys fehlen in **beiden** Locales
(`i18n-parity.test.ts:186`, `MISSING_KEY_BASELINE = 116`). Der Ratchet wird rot, wenn die
Zahl **steigt** — eine eingefrorene Obergrenze, die die Lücke als Basiszustand
institutionalisiert („Kontrollen, die ihre eigenen Lücken nicht sehen"). Zusätzlich gibt
es 536 tote Locale-Keys und einen Ratchet nur in **eine** Richtung.

**2. Inline-Defaults maskieren Fehler in beide Richtungen.** `t(key, default)` verdeckt
einen fehlenden Locale-Key: In DE erscheint ggf. der englische Default, in EN der
deutsche — genau die Maskierung, die `#619` beschreibt. Die Traceability-Matrix führt
i18n dennoch als `Implemented/Covered` (`-348`), was der Realität widerspricht.

**3. Dynamische Keys sind unsichtbar für die statische Prüfung.** `t(name)` mit einem
Variablen-Argument wird vom Scanner bewusst **nicht** erfasst
(`i18n-parity.test.ts:94-99`); ~76 dynamische Keys sind damit ungeprüft. Ohne Typschema
oder generierte Union gibt es **keine** Instanz, die „dieser Key existiert" garantieren
kann.

**4. Die Anforderung ist bereits strikt formuliert.** REQ-L1-016 verlangt: „fehlende
Translation-Keys als Build-Fehler behandelt werden (Lint-Regel)"; REQ-L2-RF-001 sagt
dasselbe für jeden UI-String in `de.json`/`en.json`; REQ-L1-094 verlangt einen
**einzigen** Key-Naming-Vertrag für den ArtifactInspector. Der Ist-Zustand
(`MISSING_KEY_BASELINE > 0`, Inline-Defaults, ungeprüfte dynamische Keys) erfüllt diese
Zusage **nicht** — das ist Finding `-348`.

**5. Drei Fragen sind je eine Entscheidung:** (a) verbindliche Quelle (Locale-Datei vs.
Code-Stelle), (b) sind dynamische Keys erlaubt, (c) darf `t()` einen Inline-Default
haben. Dieses ADR entscheidet (b) und (c) und ordnet (a) als Zielbild ein.

---

## Alternativen

### Option A: Strikter Vertrag — Inline-Default verboten, dynamische Keys nur mit Typschema

**Beschreibung:** `t()` ohne Inline-Default; der Key muss zur Test-/Compile-Zeit existieren
(fehlender Key ⇒ rot). Dynamische Keys nur über eine generierte Key-Union/Typschema.

**Abwägung:** Der saubere Endzustand: Ratchet kann auf 0 stehen und **bleibt** 0; die
Matrix-Zusage wird wahr. Aber: sofortige Entfernung der Inline-Defaults an ~112 Stellen
ist disruptive und erzeugt in einem Schritt viele rote Stellen — die Migration braucht
ein Fenster, sonst wird sie faktisch abgeschaltet.

**Risiko:** NIEDRIG (Endzustand), HOCH (Übergang ohne Fenster).

### Option B: Vertrag mit erlaubtem Default + monotone Ratchets — GEWÄHLT (Empfehlung)

**Beschreibung:** Inline-Default bleibt **vorerst** erlaubt, aber (1) der bestehende
Missing-Key-Ratchet sinkt **monoton** gegen 0, und (2) ein zweiter Ratchet misst die Zahl
der Stellen, die einen Inline-Default nutzen, und sinkt ebenfalls monoton. Dynamische
Keys ohne Typschema bleiben **verboten** (siehe Entscheidung). Zielbild bleibt Option A
bei Erreichen der 0.

**Abwägung:** Kein Bruch, aber eine **messbare** Richtung: Fortschritt ist als Zahl
sichtbar und CI-erzwingbar. Die Kritik („zwei Indikatoren, die die Pflege erklären muss")
ist berechtigt, aber beide Indikatoren sind mechanisch prüfbar — anders als eine
Absichtserklärung. Genau die Ratchet-Form ist im Repo bereits etabliert
(`i18n-parity.test.ts`, `ui-ratchet.test.ts`, `design-tokens.test.ts`).

**Risiko:** NIEDRIG — schrittweise, CI-gekoppelt; Gefahr nur bei „Ratchet nie senken",
deshalb die Pflicht zur monotonen Senkung.

### Option C: Generierte Keys — VERWORFEN (im POC)

**Beschreibung:** Aus dem Code wird eine Single-Key-Datei generiert; Locales werden
dagegen geprüft und mit dem Code ausgeliefert; Code ist die Quelle.

**Abwägung:** Verhindert Auseinanderlaufen dauerhaft und macht Review-Diffs aussagekräftig,
bringt aber generierten Code ins Repo, eine Build-Abhängigkeit und Extra-Tooling. Für
einen POC mit überschaubarem Key-Bestand ist der Nutzen derzeit nicht belegt; die
Typschema-Forderung aus A lässt sich mit einer generierten Union teilweise auch ohne
volle Code-Generierung erreichen (siehe Entscheidung).

**Risiko:** MITTEL — Tooling-/Build-Komplexität ohne belegten Bedarf.

### Teilfrage: dynamische Keys — erlaubt oder verboten?

- **Verboten ohne Typschema (gewählt):** `t(variable)` ist nur zulässig, wenn die
  mögliche Schlüsselmenge statisch als Union/enum-ähnliche Menge vorliegt und der
  Compiler/Test sie prüfen kann. Ein offener dynamischer Key ist **nicht** erlaubt.
- **Dynamische Keys generell erlaubt:** Widerspricht der statischen Prüfbarkeit; die
  geprüfte Lücke bliebe für diese Stellen blind.

**Empfehlung: verboten ohne Typschema.**

---

## Entscheidung

**Empfehlung: Option B (Default erlaubt + zwei monoton sinkende Ratchets) mit Zielbild A;
dynamische Keys ohne Typschema verboten.**

1. **Inline-Default bleibt vorübergehend erlaubt — mit sinkendem Ratchet.** Ein zweiter
   Ratchet misst die Zahl der `t(key, default)`-Stellen (`i18n-parity.test.ts:94-99`
   erfasst bereits die Literal-Keys); er darf **nur sinken**. Sobald er 0 erreicht, gilt
   die strikte Regel (A): kein Inline-Default mehr.
2. **Missing-Key-Ratchet wird monoton sinkend.** `MISSING_KEY_BASELINE = 116` ist eine
   **Obergrenze auf dem Weg nach 0**, nicht ein eingefrorenes Soll. Jede Senkung ist
   Pflicht, jede Erhöhung ist ein Review-Blocker. Locale-Ceiling = die **kanonische**
   Key-Zahl (DOC-02: 116), nicht eine gewachsene Zahl.
3. **Dynamische Keys ohne Typschema sind verboten.** `t(variable)` ist nur zulässig, wenn
   die Schlüsselmenge statisch (Union/Registry/Typschema) vorliegt und geprüft wird.
   Andernfalls ist der Key statisch zu machen. Ein Runtime-`missingKeyHandler` kann die
   Diagnose verbessern, ersetzt aber die statische Prüfung nicht.
4. **Verbindliche Quelle ist der Code-Key, verifiziert gegen die Locale-Dateien.** Der
   zulässige Weg bleibt: Key im Code referenziert → muss in `de.json` **und** `en.json`
   existieren (beide Richtungen, wie `i18n-parity.test.ts:47-59` prüft). Der Inline-Default
   ist Übergangshilfe, keine Quelle.
5. **Tote Keys werden abgebaut oder begründet** (536 Keys, `-303`); der Matrix-Vermerk
   `REQ-L1-094`/`Implemented` wird auf den **wahren** Stand gezogen (`-348`).
6. **Kaskade:** `DOC-02` implementiert beide Ratchets, senkt `MISSING_KEY_BASELINE` und
   baut die toten Keys ab. Keine Änderung an REQ-Dateien in diesem ADR.

---

## Konsequenzen

**Positiv:**

- Fortschritt wird **messbar**: zwei Zahlen (fehlende Keys, genutzte Inline-Defaults), die
  beide nur sinken dürfen.
- Kein disruptiver Bruch an ~112 Stellen; die Migration läuft schrittweise, CI-gekoppelt.
- Die Ratchet-Form ist im Repo etabliert (kein neues Werkzeug).
- REQ-L1-016/REQ-L2-RF-001 „fehlende Keys = Build-Fehler" wird schrittweise eingelöst
  und die Matrix-Zusage (`-348`) ehrlich.
- Dynamische Keys werden dort, wo sie bleiben, statisch absicherbar.

**Negativ:**

- **Zwei Indikatoren müssen gepflegt werden**; ohne disziplinierte Senkung wird der
  Übergangsvorteil zum Dauerzustand. Das ist die zentrale Restgefahr von B.
- **Inline-Defaults bleiben zunächst erlaubt** — die Maskierung besteht fort, bis der
  zweite Ratchet sie abgebaut hat.
- **~112 Stellen Migrationsaufwand**; einzelne Defaults sind fachlich und können nicht
  maschinell ersetzt werden.
- **Dynamische-Keys-Verbot** kann legitime Fälle (z. B. berechnete Terminologie-Labels)
  aufwändiger machen; diese brauchen dann eine explizite Registry/Union.
- **Entscheidung noch nicht freigegeben:** Status `proposed`; `DOC-02` startet nach der
  User-Freigabe.

---

## Offene Punkte

1. **Freigabe:** `proposed → review → accepted` durch User nach `concept-reviewer`-Review.
2. **Kanonische Key-Zahl** (DOC-02 nennt 116 als Locale-Ceiling) ist zu messen und zu
   fixieren; die genaue Zahl ist Teil von `DOC-02`, nicht dieses ADR.
3. **`open_adrs`** (`AUD-2026-09-333`): maschinelle REQ↔ADR-Verknüpfung fehlt; keine
   REQ-Datei-Änderung in diesem ADR.
4. **Abbau der 536 toten Keys** (`-303`): Auswahl/Begründung je Key ist `DOC-02`.

---

*Erstellt durch `senior-developer` am 2026-10-03. Status `proposed` — begründete
Empfehlung; die Freigabe erfolgt durch User/Review, nicht durch den Autor.
Kein Produktcode, keine Migration, kein Push.*
