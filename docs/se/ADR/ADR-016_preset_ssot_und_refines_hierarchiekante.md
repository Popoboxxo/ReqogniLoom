---
adr_id: ADR-016
title: "Ehrliche Teil-SSOT für Presets, fail-closed Downgrade-Gate und `refines` bewusst nicht als Hierarchiekante"
status: proposed
date: "2026-10-03"
deciders: [user, senior-developer]
affected_reqs: [REQ-L1-001, REQ-L1-007, REQ-L1-047, REQ-L1-062, REQ-L2-PC-001, REQ-L2-PC-004, REQ-L2-PC-006, REQ-L2-PC-011, REQ-L2-PC-012, REQ-L2-TE-001, REQ-L2-TE-017]
superseded_by: null
---

# ADR-016: Ehrliche Teil-SSOT für Presets, fail-closed Downgrade-Gate und `refines` bewusst nicht als Hierarchiekante

**Status:** proposed (Empfehlung — Freigabe durch User/Review offen)
**Datum:** 2026-10-03
**Entscheider (vorgeschlagen):** user, senior-developer
**Betroffene REQs:** REQ-L1-001 (Artefakt-Hierarchie mit beliebiger Tiefe,
`docs/se/L1/Gesamtsystem/L1_Gesamtsystem_Requirements.md:20`), REQ-L1-007
(Configurable-Rigor-Presets, ebd. `:170`), REQ-L1-047 (Cross-Level-TraceLink-Konzept,
ebd. `:1567`), REQ-L1-062 (Invarianten-Validator I1–I4 rigor-gated, ebd. `:1837`),
REQ-L2-PC-001 (Preset-Verwaltung, `docs/se/L1/Gesamtsystem/L2/PresetConfigEngineSystem/
L2_PresetConfigEngineSystem_Requirements.md:32`), REQ-L2-PC-004 (Pflichtfeld-Regeln pro
Preset, ebd. `:115`), REQ-L2-PC-006 (Workflow-Konfigurierbarkeits-Regeln pro Preset, ebd.
`:166`), REQ-L2-PC-011 (Preset-Downgrade-Validierung, ebd. `:300`), REQ-L2-PC-012
(Default-Preset-Immutabilität, ebd. `:326`), REQ-L2-TE-001 (TraceLink-Verwaltung mit 6
Link-Typen inkl. `refines`, `docs/se/L1/Gesamtsystem/L2/TraceabilityEngineSystem/
L2_TraceabilityEngineSystem_Requirements.md:33`), REQ-L2-TE-017 (Cross-Level-TraceLink-Typ
mit Begründungspflicht, ebd. `:512`)

**Bezug:** Audit-Kandidat **#2** (`docs/audit/2026-09/AUDIT_ADR_CANDIDATES.md:77-121`),
Implementation-Plan-Slot **ADR vi** (`docs/audit/2026-09/review/IMPLEMENTATION_PLAN.md:225`),
Arbeitseinheiten `DATA-10` und `DOC-01`
(`docs/audit/2026-09/review/plan/DATA_RECOVERY.md:142-153`,
`docs/audit/2026-09/review/plan/TRACE_DOCS.md:19-35`). Findings `AUD-2026-09-160`, `-161`,
`-162`, `-175`, `-187`, `-328`.

**Bezug zum Code:** `backend/presets/registry.py:13` (Docstring „Single Source of Truth
for all preset rule data"), `:10-12` („data-driven … never in DB", Default-Presets
immutable); `backend/presets/gate.py:536-549` (`except Exception: pass` im
Downgrade-Check); `backend/traceability/audit/hierarchy.py:34-45` (`refines` bewusst
ausgeschlossen, als offene Entscheidung markiert — genau dieser ADR) und `:179-195`
(`PARENT_TO_CHILD_LINK_TYPES` / `CHILD_TO_PARENT_LINK_TYPES` / `HIERARCHY_LINK_TYPES`);
`backend/reqogniloom/settings.py:508-509`
(`DEFAULT_DECOMPOSITION_LINK_TYPE` Default `decomposes`).

**Review-/Lifecycle-Vermerk:** Dieses ADR ist **`proposed`**. Es formuliert eine
begründete **Empfehlung**, keine freigegebene Entscheidung. Die Freigabe erfolgt durch
den User nach Review (`concept-reviewer`); erst dann darf der Status wechseln. Die
abhängige Umsetzung (`DATA-10`, `DOC-01`) beginnt **nach** der Freigabe.

---

## Kontext

**1. Der SSOT-Anspruch der Preset-Registry ist nicht haltbar.** Der Docstring behauptet
„Single Source of Truth for all preset rule data" (`presets/registry.py:13`). Gemessen
sind 7 Regeln datengetrieben, 5+ dagegen hartkodiert — und die hartkodierte Hälfte steuert
die fachlich gewichtigere Achse (Workflow-Graphen, Attribut-Stufen, Invarianten-Sätze).
`stage_mandatory` wird geseedet und hat **null** Produktionskonsumenten. Der Schaden ist
nicht die Inkonsistenz selbst, sondern die **falsche Zusage**: jede Folgeentscheidung
stützt sich auf „das steht in der Registry". Genau diese „benennen statt verschweigen"-
Frage hat der Präzedenzfall `ADR-008` (`accepted`) bereits für „nicht modellierte"
Sachverhalte entschieden (`docs/se/ADR/ADR-008_moe_mop_tpm_nicht_modelliert.md`).

**2. Das Downgrade-Gate ist fail-open.** REQ-L2-PC-011 fordert: „Bei Inkompatibilitäten
SHALL der Downgrade blockiert werden" (`L2_PresetConfigEngineSystem_Requirements.md:300-301`).
Die Implementierung fängt jedoch **jede** Exception des Persistence-Layers ab und fährt
fort (`presets/gate.py:547-549`). Fällt die Persistenz-Abfrage aus, ist eine
inkompatible Extended→Standard-/Minimal-Migration **erlaubt**, obwohl sie es nach
REQ-L2-PC-011 nicht sein darf. Das ist unabhängig vom SSOT-Grad ein Korrektheitsdefekt
an genau der Stelle, die einen unzulässigen Downgrade verhindern soll.

**3. `refines` ist ein Live-Built-in, dessen Hierarchie-Status offen ist.** `refines`
existiert als Link-Typ (`REQ-L2-TE-001` nennt ihn ausdrücklich; `link_types/builtin.py`),
wird aber vom Hierarchie-Modul **bewusst ausgeschlossen**
(`hierarchy.py:34-45`, `:191-192`). Der Code markiert die Frage selbst als offen und
verweist auf ADR-Kandidat **(vi)** — also genau hierher. `refines` hat dieselbe Richtung
wie `derives-from` (`source = verfeinernd (niedrigere Ebene), target = verfeinert`), aber
eine **schwächere** Aussage. Die Hierarchie-Kanten steuern heute die
`RequirementLevel`-Ableitung und den Umfang des `document`-Baseline-Scopes; würde
`refines` dort aufgenommen, zöge eine Verfeinerung dieselben Ebenen- und Baseline-Folgen
nach sich wie eine Dekomposition. Gleichzeitig ist `DEFAULT_DECOMPOSITION_LINK_TYPE`
konfigurierbar (`settings.py:508-509`, Default `decomposes`) — eine Fehlkonfiguration auf
`refines` würde also eine Dekompositionskante erzeugen, die das Hierarchie-Modul
ignoriert.

**4. `open_adrs` existiert repo-weit nicht.** Die REQ↔ADR-Rückverfolgbarkeit kann
mechanisch noch nicht eingetragen werden (vgl. `ADR-011`/`ADR-012`, `AUD-2026-09-333`).
Die Zuordnung der betroffenen REQs ist eine **belegte Näherung** (Datei + Zeile oben),
keine bereits getrackte Verknüpfung; es wird **keine** REQ-Datei und **keine**
Traceability-Matrix in diesem ADR geändert.

---

## Alternativen

### Option A: Volle SSOT — alle Preset-Regeln werden Daten — VERWORFEN

**Beschreibung:** Sämtliche Preset-Regeln (inkl. Workflow-Graphen, Attribut-Stufen,
Invarianten-Sätze) werden als Daten geführt; Module lesen ausschließlich; die Registry
wird generiert oder datengetrieben editiert.

**Abwägung:** Macht den Docstring wörtlich wahr und erlaubt einen Vollständigkeits-Test,
erzwingt aber ein Datenmodell für Dinge, die heute **aus guten Gründen** Code sind
(Workflow-Graphen). Größter Aufwand, höchstes Regressionsrisiko an der zentralsten
Konfigurationsachse. Für einen POC mit drei fixen Presets ist der Nutzen (Preset-Wechsel
ohne Deploy) derzeit nicht belegt.

**Risiko:** HOCH — Aufwand und Blast-Radius an der Kernkonfiguration.

### Option B: Ehrliche Teil-SSOT — GEWÄHLT (Empfehlung)

**Beschreibung:** Die Registry ist SSOT für die **datenförmigen** Preset-Regeln
(Pflichtfelder, sichtbare Features, Baseline-Scope, Change-Reason-Pflicht). Workflow-Graphen,
Attribut-Stufen und Invarianten-Sätze bleiben **Code** und werden als solche **benannt**.
Der Docstring wird korrigiert; „datengetrieben vs. Code" wird zu einer expliziten Aussage.

**Abwägung:** Kleinster Aufwand, beseitigt die falsche Zusage sofort und setzt `ADR-008`
fort („was nicht modelliert wird, wird benannt"). Die verbleibende Zweiteilung
(Daten-Regeln + Code-Regeln) wird als bewusste Grenze dokumentiert; Audit-Tooling muss
sie kennen, statt sie zu übersehen.

**Risiko:** NIEDRIG — Doku + Benennung, keine Verhaltensänderung der Preset-Regeln.

### Option C: Code-SSOT, Registry als Export — VERWORFEN

**Beschreibung:** Umgekehrt: Code ist die Quelle, die Registry ein Export für UI/Docs.

**Abwägung:** Vermeidet Doppelbuchhaltung, erschwert aber Tenant-Overrides
(`REQ-L2-PC-014` Benutzerdefinierte Presets) und macht jeden Preset-Wechsel deploy-pflichtig.
Die drei Default-Presets sind zwar immutable (`REQ-L2-PC-012`), aber die Registry ist
bereits die Laufzeit-Quelle, gegen die `FeatureGateService` und `PresetPolicyService`
lesen (`registry.py:14-15`). Ein Umkehren des Datenflusses wäre eine echte Regression.

**Risiko:** MITTEL — kollidiert mit dem bestehenden Query-Interface
(`REQ-L2-PC-003`) und dem Custom-Preset-Pfad.

### Teilentscheidung `refines`: Option D1 (ausschließen) vs. D2 (aufnehmen)

- **D1 — `refines` bleibt bewusst keine Hierarchiekante** (aktuelle Code-Haltung):
  Dekomposition bleibt bei `decomposes`/`derives-from`. Verfeinerung ist eine
  **semantische** Relation (Impact/Analyse), keine Ebenen-/Baseline-Kante. Der
  `DEFAULT_DECOMPOSITION_LINK_TYPE` muss auf die Hierarchie-Link-Typen eingeschränkt
  werden, damit eine Konfiguration keinen Hierarchie-fremden Typ setzen kann.
- **D2 — `refines` wird Hierarchiekante:** Dann müsste es in
  `HIERARCHY_LINK_TYPES`/`CHILD_TO_PARENT_LINK_TYPES` aufgenommen werden und dieselben
  Ebenen-/`document`-Baseline-Folgen tragen; eine Verfeinerung wäre einer Zerlegung
  gleichgestellt.

**Empfehlung: D1.** Eine Verfeinerung ist per Definition eine **schwächere** Aussage als
eine Dekomposition; sie als Hierarchiekante zu behandeln, würde Ebenen und
Baseline-Scope aufweichen, ohne dass ein Bedarf belegt ist. D1 ist zudem die minimale,
risikoärmste Fortsetzung des Ist-Verhaltens und macht die Ausnahme explizit statt
implizit.

---

## Entscheidung

**Empfehlung: Option B für den SSOT-Grad, D1 für `refines` — plus ein unabhängiger,
sofortiger fail-closed-Fix am Downgrade-Gate.**

1. **Teil-SSOT, benannt.** `presets/registry.py` ist SSOT für die **datenförmigen**
   Regeln (Pflichtfelder, Features, Baseline-Scope, Change-Reason). Workflow-Graphen,
   Attribut-Stufen und Invarianten-Sätze bleiben Code und werden im Docstring und in
   `DOC-01` als solche benannt. Der irreführende Satz „…for all preset rule data" wird
   korrigiert (z. B. „…for the data-driven preset rules; workflow graphs / attribute
   tiers / invariant sets remain code"). Die Default-Presets bleiben immutable
   (`REQ-L2-PC-012`).
2. **Downgrade-Gate fail-closed — unabhängig vom SSOT-Grad.** `presets/gate.py:547-549`
   darf einen Persistence-Fehler **nicht** mehr verschlucken. Fällt die
   Inkompatibilitätsprüfung aus, gilt der Downgrade als **blockiert** (fail-closed) oder
   eskaliert als Fehler — die genaue Antwort (block vs. error) legt `DATA-10` im Rahmen
   der Downgrade-Policy (`block`/`warn`/`allow`, REQ-L2-PC-011) fest. Legitime
   Testkontexte müssen den Ausfall **explizit** konfigurieren, nicht über einen stillen
   `except: pass` erhalten.
3. **`refines` wird nicht als Hierarchiekante aufgenommen.** Die Struktur in
   `hierarchy.py` (`PARENT_TO_CHILD_LINK_TYPES`, `CHILD_TO_PARENT_LINK_TYPES`,
   `HIERARCHY_LINK_TYPES`) bleibt unverändert; der Ausnahme-Kommentar wird von
   „offene Entscheidung" auf „entschieden (dieses ADR)" umgestellt. `refines` bleibt als
   Link-Typ erhalten (`REQ-L2-TE-001`) und für Impact-/Analyse-Pfade nutzbar.
4. **`DEFAULT_DECOMPOSITION_LINK_TYPE` wird auf Hierarchie-Link-Typen eingeschränkt.**
   Die Dekompositions-Default-Konfiguration darf nur Werte annehmen, die das
   Hierarchie-Modul kennt (`decomposes`, `derives-from`); `refines` ist als
   Dekompositions-Default unzulässig und wird validiert abgewiesen (vgl.
   `link_types/tests/test_default_link_type_env_989.py`). Damit sind Konfiguration und
   Hierarchie-Semantik konsistent.
5. **Kaskade der abhängigen Arbeitseinheiten.** `DATA-10` (fail-closed-Gate, Docstring)
   und `DOC-01` (`refines`-Statusdokumentation, Matrix-Zusage) referenzieren und
   setzen diesen ADR um. Die Preset-Regeln selbst bleiben verhaltensgleich.

### Was diese Entscheidung *nicht* ist

Sie ist **keine** Aussage, dass alle Preset-Regeln irgendwann Daten werden müssen. Sie
ist die Aussage, dass der SSOT-Anspruch der Registry **ehrlich auf ihren tatsächlichen
Umfang begrenzt** wird und dass die eine sicherheitsrelevante Lücke (fail-open-Gate)
unabhängig davon sofort geschlossen wird.

---

## Konsequenzen

**Positiv:**

- Die falsche Zusage verschwindet: „7 datengetrieben / 5 Code" wird eine **benannte**
  Tatsache statt eines Problems, in der Linie von `ADR-008`.
- REQ-L2-PC-011 wird **tatsächlich** durchgesetzt: Ein Persistenz-Ausfall kann einen
  unzulässigen Downgrade nicht mehr still erlauben.
- Die `refines`-Frage ist entschieden und dokumentiert; künftige Leser finden in
  `hierarchy.py` einen Verweis auf dieses ADR statt auf einen offenen Kandidaten.
- Konfiguration und Semantik sind konsistent: `DEFAULT_DECOMPOSITION_LINK_TYPE` kann
  keine Kante mehr setzen, die die Hierarchie ignoriert.
- Kleinster Umfang: keine Migration, keine Änderung der Preset-Regelwerte, keine
  REQ-/Matrix-Änderung.

**Negativ:**

- **Der Rigor-Diff bleibt teilweise im Code.** Audit-Tooling und Doku müssen weiterhin
  zwei Quellen unterscheiden (datenförmige Regeln vs. Code-Regeln). Option B beseitigt
  die Zweiteilung **nicht**, sie macht sie nur sichtbar.
- **fail-closed kann legitime Testkontexte brechen.** Test-/CI-Setups, die heute vom
  stillen `except: pass` profitiert haben, brauchen eine explizite Konfiguration; das ist
  gewollt, aber eine sichtbare Umstellung.
- **`refines` bleibt aus Ebenen-/Baseline-Folgen heraus.** Falls eine fachliche Anforderung
  doch eine Verfeinerungs-Hierarchie verlangt, ist das eine **neue** Entscheidung (dieses
  ADR wäre zu supersedieren), nicht eine stille Erweiterung.
- **Die SSOT-Docstring-Korrektur allein stellt keine Vollständigkeit her.** Sie garantiert
  nicht, dass jede Regel korrekt klassifiziert ist; `DATA-10`/`DOC-01` müssen die
  Klassifikation einmalig durchgehen.
- **Entscheidung noch nicht freigegeben:** Status `proposed`; bis zur User-Freigabe bleibt
  die Lücke offen und der abhängige Fix ungestartet.

---

## Offene Punkte

1. **Freigabe:** `proposed → review → accepted` durch User nach `concept-reviewer`-Review.
2. **`open_adrs`-Feld** (`AUD-2026-09-333`): Die oben genannten REQs können diesen ADR
   erst nach Einführung maschinell referenzieren; bis dahin keine REQ-Datei-Änderung.
3. **Genauer fail-closed-Modus** (block vs. error, Konfigurationsschalter) ist Teil von
   `DATA-10`, nicht dieses ADR.
4. **REQ-Zuordnung ist belegte Näherung** (Datei + Zeile); bei Einführung von `open_adrs`
   formal nachzuziehen.

---

*Erstellt durch `senior-developer` am 2026-10-03. Status `proposed` — begründete
Empfehlung; die Freigabe erfolgt durch User/Review, nicht durch den Autor.
Kein Produktcode, keine Migration, kein Push.*
