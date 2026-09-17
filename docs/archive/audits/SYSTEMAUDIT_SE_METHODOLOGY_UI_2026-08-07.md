# Systemaudit: SE-Methodik von ReqogniLoom — **UI-Beobachtungshälfte**

**Datum:** 2026-08-07
**Auditor:** `e2e-tester` (Browser-Durchlauf gegen die laufende Instanz)
**Prüfgegenstand:** Was ein Systems Engineer im Browser **tatsächlich sieht und tun kann** —
nicht, was der Code behauptet.
**Schwesterdokument:** `docs/SYSTEMAUDIT_SE_METHODOLOGY_2026-08-07.md`
(Backend/API/MCP-Hälfte, `se-consultant`). Beide Berichte ergeben zusammen ein Gesamtbild;
dieser hier steht für sich, deckt aber ausschließlich die **UI-Ebene** ab.

---

## 0. Setup, Methode und Belege

| Punkt | Wert |
|---|---|
| Frontend | `http://localhost:5173` (Vite-Dev-Server im Container) |
| Backend | `http://localhost:8000` — `docker-compose ps`: alle Services `healthy` |
| Login | `admin` / `admin12345` (aus `.env` / `seed_demo.py`) |
| Test-Workspace | **`UIAUDIT-2026-08-07`**, `66c89f36-67db-43d5-bf15-c42eeda70129` |
| Preset | `extended`, Terminologie `SE-Modus`, Sprache DE |
| Viewport | 1920×1080 (funktionale Prüfung), zusätzlich 1600×1000 und 1366×768 (Layout) |

**Der Dogfooding-Workspace und die `SE-AUDIT-2026-08-07-*`-Workspaces des Parallel-Audits
wurden nicht angefasst.** Alle Artefakte wurden ausschließlich über die UI angelegt:

| Artefakt | Editor-ID (Route) | Artifact-ID (Traceability) |
|---|---|---|
| StakeholderNeed | `5eb1a0cc` | `aed9827e` |
| Requirement L1 | `0367c8f5` | `9c706550` |
| Requirement L2 | `5541df0a` | `55fa608c` |
| ArchitectureElement | `426521f0` | `44414834` |
| TestCase | `f78de2b8` | `832b063f` |
| Baseline | `d466c9df` | — |

> **Werkzeug-Hinweis (Transparenz):** Der Playwright-MCP-Server aus
> `.claude/rules/mcp-playwright.md` ist in `.mcp.json` dieser Session **nicht registriert**;
> die MCP-Browser-Tools standen nicht zur Verfügung. Der Durchlauf wurde deshalb mit dem
> repo-eigenen Playwright 1.61.1 (`e2e/node_modules`) gefahren — ausschließlich über die
> Locator-API, `ariaSnapshot()` (Accessibility-Baum) und `screenshot()`.
> **Keine** In-Page-Code-Ausführung (`page.evaluate`), kein File-Upload, kein Dialog-Scripting —
> die gesperrten Fähigkeiten wurden eingehalten. Die bestehende E2E-Suite wurde **nicht**
> ausgeführt.

**Belege:** Screenshots liegen unter `docs/assets/systemaudit-ui-2026-08-07/`.
Accessibility-Snapshots (`*.aria.yaml`) wurden zu jedem Schritt erzeugt; die im Text zitierten
AX-Zeilen stammen daraus.

---

## Kurzfassung

**Es gibt in dieser UI echte, harte SE-Methodik** — und zwar mehr, als man erwartet:
ein constrained State-Machine mit Pflicht-Begründung pro Übergang, eine erzwungene
Change-Control, presetabhängige Freigabe-Gates und vor allem ein **SE-Auditor, der die
Baseline-Erzeugung blockiert**, bis der Trace-Graph konsistent ist. Das ist keine Kosmetik.

**Und genau diese Stärke deckt die schwerste Schwäche auf:** Die vom Tool selbst geführte
„Ableiten"-Strecke erzeugt einen Trace-Graphen, den der eigene Auditor sofort mit vier
Blockern zurückweist. Dazu kommt ein Freigabe-Gate im `extended`-Preset, das ein Feld
verlangt, **das die UI nirgends anbietet** — Requirements sind unter `extended` über die
Oberfläche nicht freigebbar. Der einzige Ausweg ist ein Rigor-Downgrade, das per einzelnem
Radio-Klick ohne jede Warnung möglich ist.

Auf der Sichtbarkeitsebene ist die Bilanz schlechter: Die Traceability-Ansicht zeigt nur
abgeschnittene UUIDs, die Coverage-Kennzahl steht auf 0,0 % obwohl Links existieren, und
eine Baseline sperrt sichtbar **nichts** — Drift dagegen ist gar nicht dargestellt.

---

## 1. StakeholderNeed — als *Bedarf* erkennbar, nicht als Requirement?

**Beleg:** `06b-need-detail.png`, `04a-needs-empty.aria.yaml`

### Was ich sehe — unterstützt die Methodik

- Eigener Navigationspunkt **„Bedarfe"**, eigene Route `/needs`, eigene Liste.
- Der Leerzustand erklärt den Zweck explizit:
  *„Stakeholder-Bedarfe beschreiben, was Stakeholder brauchen und warum."*
- Der Inspector betitelt den Diff artefakttypspezifisch: **„Stakeholder Need Diff"**
  (beim Requirement: „Requirement Diff", bei Architektur: „Architecture Element Diff").
- Die Feldmenge unterscheidet sich **fachlich sinnvoll**:

| | StakeholderNeed | Requirement |
|---|---|---|
| Priorisierung | **MoSCoW** (Must/Should/Could/Won't) | **Komplexität (Fibonacci)** |
| SE-Attribut | — | **Verifikationsmethode** (Inspection/Review/Test/Analysis) |
| Typisierung | — | **Anforderungstyp** (SyReq / UseCase / FeatureReq) |

  MoSCoW auf dem Bedarf und Verifikationsmethode auf der Anforderung ist genau die richtige
  Trennung: der Bedarf wird *priorisiert*, die Anforderung wird *verifiziert*.

**Bewertung: Der Unterschied ist strukturell echt, nicht nur ein anderes Label.**

### Was dagegen spricht

1. **Kein Stakeholder, keine Quelle, keine Rationale.** Ein StakeholderNeed nach NASA-SE-Lesart
   trägt *wer* den Bedarf hat, *woher* er stammt und *warum*. Das Formular kennt nur
   Titel, Beschreibung, Status, Kategorie (Freitext), MoSCoW. Der wichtigste Teil eines
   Bedarfs — die Herkunft — ist nicht modelliert.
2. **Terminologie-Leck, das die Trennung wieder einreißt.** Im Change-Control-Block des
   **Bedarfs** steht als Platzhalter wörtlich:
   *„Warum wird diese **Anforderung** geändert?"* — derselbe Text erscheint auch auf dem
   **ArchitectureElement**. Wer die Need/Requirement-Unterscheidung gerade lernt, bekommt sie
   an dieser Stelle vom Tool wieder weggenommen.
3. **Inline-Anlage ist titelonly.** „Neuer Bedarf" öffnet ein einzelnes Titelfeld
   (Buttons `Cancel` / `Create` — englisch in deutscher UI). Auch unter `extended` gibt es
   an der Anlagestelle keinerlei Pflichtstruktur.

---

## 2. Ableitung über zwei Ebenen — ist der Elternbezug sichtbar und navigierbar?

**Beleg:** `09b-derive-done.png`, `15b-l2-created.png`

### Sichtbar und navigierbar: ja

- Die **„Ableitungskette"** (Breadcrumb über dem Editor) ist ein echter Navigationspfad mit
  Zählern. Auf dem L2-Requirement:
  `Anforderungen ◀ hier [1] · Architektur L0 [1 ↓]` — die Buttons sind anklickbar.
- Im TraceLinks-Block erscheint der Elternbezug als benannte Beziehung, nicht als ID:
  `Derivation → „Als Betreiber benoetige ich lueckenlose Nachweisfuehrung…"` (Button, navigierbar).
- Die Allokation ist ebenso sichtbar: `Architekturelemente → Allocation → „Audit-Trail-Subsystem"`.

**Das ist kein unsichtbares DB-Feld — der Elternbezug ist im UI präsent und klickbar.**

### Ein methodisch starkes Detail

Beim Ableiten **von einer Anforderung** (L1 → L2) ist das Feld
**„Architekturelement (Systemebene) \*" Pflicht** — man kann eine Anforderung nicht
dekomponieren, ohne sie einem Architekturelement zuzuordnen. Das ist echte
Requirements-Allocation-Disziplin und ein klarer Pluspunkt.

**Aber:** Solange kein Architekturelement existiert, enthält das Dropdown nur
„Option auswählen" — **ohne Hinweis, ohne Link, ohne Erklärung**. Der Nutzer steht in einer
Sackgasse und erfährt nicht, dass er erst nach `/architecture` muss.

### Was gegen die Methodik spricht

1. **Requirement-Ebenen (L0–L4) existieren in der UI nicht.**
   L1 und L2 sind **visuell identisch**: beide tragen das Badge `SR`, beide sind
   `System-Anforderung (SyReq)`, beide stehen in einer **flachen, uneingerückten Liste**
   ohne Hierarchie-Indikator (`15b-l2-created.png`, linke Spalte). Ebenen gibt es nur bei
   **ArchitectureElements** (`L0`-Badge, „Übergeordnetes Element", `+ Add child`-Baum).
   Die im Projektkontext beworbene V-Modell-Kaskade L0→L4 ist für Anforderungen
   **nicht sichtbar**.
2. **„Anforderungen (hierarchical view)" zeigt das Artefakt selbst.**
   Auf dem L1-Requirement listet dieser Block *„Das System muss jede Zustandsaenderung…"* —
   also L1 selbst, **nicht** sein Kind L2. Auf L2 listet er L2 selbst, nicht L1.
   Der Block ist mit „hierarchical view" überschrieben, zeigt aber keine Hierarchie.
   Der Dekompositions-Link existiert (der Auditor kennt ihn, s. §5), wird hier aber nicht gerendert.

---

## 3. Coverage — sieht man einer *nicht abgedeckten* Anforderung das an?

Testaufbau bewusst asymmetrisch: **L2** hat Architektur-Allokation *und* Testfall,
**L1** hatte weder Test noch Allokation.

**Beleg:** `19a-traceability.png`, `19c-metrics.png`, `21a-impact-expanded.png`

### Antwort: **Nein — und zwar deutlicher als erwartet.**

Die Traceability-Ansicht (`/traceability`) stellt gar keine Anforderungen dar. Sie zeigt eine
flache, nach Linktyp gruppierte Liste von **abgeschnittenen UUID-Paaren**:

```
Derivation      9c706550…  →  Derivation      →  aed9827e…
Verification    832b063f…  →  Verification    →  55fa608c…
Allocation      55fa608c…  →  Allocation      →  44414834…
Decomposition   9c706550…  →  Decomposition   →  55fa608c…
```

Keine Titel. Keine Artefakttypen. Keine Abdeckungsmarkierung. Keine Matrix.
Kein Lücken-Highlight. Kein Filter „nicht abgedeckt".

**Die Frage „Welche Anforderung hat keinen Test?" ist in dieser Ansicht nicht beantwortbar** —
nicht weil abgedeckt und nicht abgedeckt gleich *aussehen*, sondern weil Anforderungen dort
überhaupt nicht vorkommen. Für ein Traceability-Werkzeug ist das die zentrale Ansicht, und
sie ist für einen Menschen praktisch unlesbar.

### Falsche Kennzahl: Traceability-Coverage 0,0 %

`/metrics` („SE-Prozess-Metriken") meldet **„Traceability-Coverage 0.0 %"** — zu einem
Zeitpunkt, an dem im Workspace vier Trace-Links existierten und **eine von zwei Anforderungen
sowohl allokiert als auch durch einen Testfall verifiziert** war. Erwartbar wären ~50 %.

Das ist keine „false-green"-Anzeige, sondern das Spiegelbild: eine **false-red / schlicht nicht
funktionierende KPI**. Für ein SE-Review ist beides gleich wertlos — die Zahl trägt keine
Information über den tatsächlichen Graphen.

### Zwei getrennte ID-Räume, die die UI nicht überbrückt

Traceability und Impact arbeiten mit **Artifact-IDs**, die Editoren mit **Entity-IDs**
(Tabelle in §0). Nirgends in der UI wird der Zusammenhang hergestellt: Der Ingenieur sieht
auf der Anforderung `0367c8f5`, in der Traceability `9c706550` — und kann nicht erkennen,
dass das dasselbe Objekt ist.

Die Anwendung verwechselt die beiden Räume auch selbst. Während des Durchlaufs wiederholt
beobachtet:

```
404 GET /api/v1/requirements/55fa608c-721f-4134-8143-5a319c2a41d1/
404 GET /api/v1/architecture/44414834-9579-4e47-8152-2b3c92f3b177/
404 GET /api/v1/artifacts/426521f0-9eb8-4b1a-a60f-3e193c49df36/
```

— jeweils die Artifact-ID gegen den Entity-Endpunkt bzw. umgekehrt.

### Auswirkungsanalyse: Titel ja, aber zyklisch und unbegrenzt

`/impact` ist die **einzige** Ansicht, die Trace-Beziehungen mit **Titeln** darstellt, und ist
insofern besser. Zwei ernste Mängel:

1. **Der Wurzelknoten zeigt nur die UUID** (`Requirement 9c706550…`), während alle Kinder
   Titel tragen — ausgerechnet der Ausgangspunkt bleibt unlesbar.
2. **Keine Zyklenerkennung, keine Deduplizierung.** Der Baum läuft in beide Richtungen
   (`→` / `←`) und oszilliert endlos:
   `L1 →DECOMPOSITION→ L2 →←DECOMPOSITION→ L1 →DECOMPOSITION→ L2 …`
   Aus **5 Artefakten und 4 Links** entsteht ein aufgeklappter Baum mit über 25 Knoten,
   in dem dieselben vier Artefakte immer wieder auftauchen (`21a-impact-expanded.png`).
   Bei realistischer Projektgröße ist diese Ansicht kombinatorisch unbrauchbar.

### Positiv an dieser Stelle

Der Dialog **„Trace-Link erstellen"** ist gut gebaut: Zielsuche über **Titel**,
Typfilter (Alle / Anforderung / Architektur / Testfall / ADR / Risiko / Problem) und
**14 Linktypen** (u. a. Derivation, Satisfaction, Verification, Implementation, Allocation,
Decomposition, Refinement, Realization). Das zeigt, dass die lesbare Darstellung im Tool
vorhanden ist — sie fehlt nur ausgerechnet in der Traceability-Übersicht.

---

## 4. Workflow-Übergänge — echtes Gate oder Klick-durch?

**Beleg:** `24b-wf-with-reason.png`, `27a-gate-blocked.png`, `07a-save-without-reason.png`

### Es gibt echte Gates — mehrere, und sie greifen

**a) Beschränkter Zustandsautomat.** Kein freies Status-Dropdown. Aus `draft` wird genau
**ein** Übergang angeboten (`→ in_review`), aus `in_review` genau zwei
(`→ approved`, `→ draft`). Rückwärts-/Sprungübergänge existieren nicht.

**b) Pflicht-Begründung pro Übergang.** Jeder angebotene Übergang trägt ein `*`. Der Klick
öffnet ein Inline-Panel **„Begründung für → in_review"** mit Textarea und einem
**deaktivierten** „Bestätigen"-Button. Geprüft:

```
gate: justification panel shown, Bestätigen disabled=true
gate: Bestätigen disabled after typing=false
[NET] 200 POST /api/v1/requirements/0367c8f5-…/transitions/
-> status now: in_review
```

Ohne Begründung wird der Übergang gar nicht erst abgesetzt. **Das ist ein echtes
Review-Gate**, kein Reibungsfreiklick.

**c) Change Control beim Speichern.** Beschreibung geändert, „Änderungsgrund" leer gelassen,
gespeichert → rote Inline-Meldung **„Änderungsgrund ist erforderlich."**, und nach Reload ist
die Beschreibung **nachweislich leer** — es wurde nichts persistiert. Sauber.

**d) Presetabhängiges Freigabe-Gate mit sichtbarer Begründung.** `in_review → approved` unter
`extended`:

```
HTTP 400
{"error":{"code":"VALIDATION_ERROR","message":
 "Cannot approve this Requirement: the 'extended' preset requires the following
  field(s) to be filled in first: acceptance_criteria, description."}}
```

Die Meldung wird dem Nutzer als `role="alert"` angezeigt — inhaltlich präzise, benennt die
fehlenden Felder. Das ist genau die Art SRR/PDR-äquivalenter Vollständigkeitsprüfung, die man
sich wünscht.

### 🔴 Der blockierende Fund: das Gate ist über die UI nicht erfüllbar

**`acceptance_criteria` existiert im Anforderungsformular nicht.** Die vollständige Feldliste
des Requirement-Editors (aus dem AX-Snapshot, `extended`, alle Abschnitte):

```
General Information:        Titel *, Beschreibung
Classification & Properties: Kategorie, Workflow-Status, Anforderungstyp,
                             Komplexität (Fibonacci), Verifikationsmethode
Benutzerdefinierte Felder:  (leer)
Change Control:             Änderungsgrund *
```

Kein Akzeptanzkriterien-Feld. Nicht ausgeblendet, nicht weiter unten — **es gibt es nicht.**
Der einzige Treffer für „acceptance" im gesamten Snapshot ist die Fehlermeldung selbst.

Gegenprobe, um fair zu sein:

1. **`description` gefüllt** → verschwindet aus der Fehlermeldung. Das Gate arbeitet also
   korrekt feldbezogen: `…requires the following field(s): acceptance_criteria.`
2. **Ad-hoc-Custom-Field** `Schlüssel = acceptance_criteria` gesetzt → Wert nachweislich
   gespeichert (Response-Payload:
   `"custom_fields":{"acceptance_criteria":"GIVEN eine Zustandsaenderung WHEN…"}`) →
   Gate **weiterhin 400**.
3. **Workspace-weites Custom Field** `acceptance_criteria` in den Workspace-Einstellungen
   definiert → erzeugt kein eigenes Formularfeld → Gate **weiterhin 400**.

> **Ergebnis: Unter dem `extended`-Preset kann eine Anforderung über die Oberfläche niemals
> freigegeben werden.** Das Gate liest ein First-Class-Modellfeld, das das Frontend nicht
> rendert. Das höchste Rigor-Level ist in der UI eine Sackgasse.

### Weitere Inkonsistenz

„Änderungsgrund" ist auf **Bedarf** und **Anforderung** mit `*` als Pflicht markiert, auf dem
**ArchitectureElement** dagegen **ohne** `*` (AX: `- text: Änderungsgrund`, kein Sternchen).
Die Change-Control-Strenge ist über die Artefakttypen hinweg nicht einheitlich — für ein
CM-Regime ist das eine Lücke.

---

## 5. Baseline — sperrt sie etwas, und ist Drift sichtbar?

**Beleg:** `39a-audit-before.png`, `41b-baseline-created.png`, `42b-baselines-after-drift.png`

### 🟢 Der stärkste SE-Fund des gesamten Durchlaufs

**Die Baseline-Erzeugung ist durch den SE-Auditor blockiert.** Erster Versuch → HTTP 400,
und der Nutzer bekommt die vollständige Begründung als `role="alert"` zu sehen:

> „Baseline cannot be created: the SE-Auditor reported **4 blocking finding(s)** for this
> workspace. Resolve them first — …"

Die vier Blocker:

| Regel | Befund |
|---|---|
| **TRACE-P5** | L2 wurde von L1 dekomponiert (`decomposes`), trägt aber **keinen passenden `derives-from`-Rücklink** — der Requirement-Baum ist graph-inkonsistent zu seiner Dekomposition. |
| **TRACE-P1b** | L2 hat **keinen ausgehenden `derives-from`-Link** zu einem Upstream-Requirement oder StakeholderNeed (Orphan). |
| **TRACE-P2** | L1 ist **keinem ArchitectureElement allokiert** (`allocated-to`). |
| **TRACE-P3** | ArchitectureElement erfüllt/implementiert **keine Anforderung**. |

Das ist echte Konfigurationsmanagement-Disziplin: **Kein Snapshot über einen inkonsistenten
Trace-Graphen.** Genau das erwartet man vor einem Meilenstein-Baseline.

Die Auditor-Seite `/audit` selbst ist ebenfalls gut: Regel-IDs, Blocker/Warnungs-Zähler,
Anzeige der **„Rigor-Stufe: extended"**, betroffene Artefakte und teilweise **funktionierende
Auto-Remediation** — „Übernehmen" räumte TRACE-P2 und TRACE-P5 tatsächlich ab
(`Findings: 4 → 3 → 1`).

### 🔴 Und genau hier der schärfste Widerspruch des Audits

**Alle vier Blocker wurden von der geführten „Ableiten"-Strecke des Tools selbst erzeugt.**

Ich habe die Kette ausschließlich über die tooleigenen Buttons gebaut:
Bedarf → *Ableiten* → L1 → *Ableiten* (mit Pflicht-Architekturelement) → L2,
Requirement → *Testfall generieren* → TestCase.
Kein manuelles Verlinken, kein API-Zugriff, keine Abkürzung.

**Das Ergebnis dieser vom Tool vorgegebenen Reihenfolge weist der tooleigene Auditor sofort
als methodisch invalide zurück.** Der „Ableiten"-Assistent setzt `decomposes`, aber nicht den
reziproken `derives-from`; er allokiert das *Kind*, aber nicht das *Elternteil*; er erzeugt
kein `satisfies` vom Architekturelement zurück. Wer dem Tool folgt, produziert Blocker.

Dass beides gleichzeitig existiert — ein strenger, korrekter Auditor und ein Assistent, der
gegen dessen Regeln verstößt — ist die aussagekräftigste Einzelbeobachtung dieses Berichts.

### Weitere Baseline-Mängel

1. **TRACE-P1b und TRACE-P3 haben „Anpassen" *deaktiviert*.** Keine Auto-Korrektur, **und kein
   Link zum betroffenen Artefakt**. Der Nutzer sitzt auf der Auditor-Seite fest und muss selbst
   herausfinden, wohin. Ich musste TRACE-P3 manuell über einen `Satisfaction`-Link vom
   Architekturelement auflösen. Erst bei `Findings: 0` ließ sich die Baseline anlegen.
2. **Baselines haben keinen Namen und keine Rationale.** Das Anlageformular bietet nur die
   drei Scopes (Dokument / Projekt / Global) und eine Vorschau
   („5 Elemente werden eingeschlossen." — gut). Kein Namensfeld, kein Zweck-/Meilensteinfeld.
   Ergebnis: `Baseline 2026-08-07T18:45:29.346549+00:00`. Eine SE-Baseline muss
   „SRR-Baseline" / „PDR-Baseline" heißen und einen Grund tragen.
3. **Der Baseline-Inhalt ist nicht einsehbar.** Die Detailansicht zeigt dauerhaft
   „Captured items — Laden…", weil `GET /api/v1/baselines/d466c9df-…/` mit **404** antwortet.
   Man kann nicht nachsehen, was die Baseline eigentlich eingefroren hat.

### 🔴 Drift: vollständig unsichtbar

Nach Anlage der Baseline habe ich das baselinierte L1-Requirement geändert (Titel →
`… [POST-BASELINE-EDIT]`, mit Änderungsgrund gespeichert, Version v3).

Anschließend systematisch nach Drift-Indikatoren gesucht — auf der Artefaktseite und auf
`/baselines`, im AX-Snapshot nach `Baseline`, `Drift`, `abweich`, `veraltet`:

**Kein einziger Treffer** außer meinem eigenen eingetippten Text im Feld „Änderungsgrund".

- Die Artefaktseite zeigt **kein** Badge „seit Baseline geändert".
- Die Baselines-Seite zeigt **keinen** Zähler geänderter Artefakte, keine Statusfarbe.
- Der Inspector-Diff vergleicht **„Creation baseline → Current"**, also die
  *artefakteigene* v0→v1-Historie — **nicht** die Projekt-Baseline.
- „Compare" auf der Baselines-Seite bleibt bei einer Baseline **deaktiviert**; einen
  Vergleich „Baseline ↔ aktueller Stand" gibt es nicht.

> **Die Baseline sperrt sichtbar nichts, und die Abweichung von ihr ist in der UI nicht
> darstellbar.** Damit ist sie als Konfigurations-Referenzpunkt praktisch wertlos — genau das
> „a baseline that doesn't actually lock anything"-Muster.

---

## 6. Rigor-Presets — echter methodischer Schritt oder Kosmetik?

**Beleg:** `33a-settings-extended.png`, `36-preset-*.png`

### Antwort: **funktional echt.** Nachgewiesen, nicht behauptet.

Die Auswahl in den Workspace-Einstellungen ist ungewöhnlich ehrlich beschriftet — jede Option
sagt direkt, was sie ändert:

```
minimal    Baselines: ✗ | change_reason: optional | Basic (Draft/Approved)
standard   Baselines: ✓ | change_reason: optional | Full (Draft/Approved/Deprecated)
extended   Baselines: ✓ | change_reason: required | Full + Approval workflow
```

**Beobachtete UI-Änderung** (identisches Requirement, nur Preset umgestellt):
Unter `minimal` verschwinden aus dem Formular die kompletten Abschnitte
**„Change Control / Änderungsgrund \*"** und **„Benutzerdefinierte Felder"**.

**Beobachtete Verhaltensänderung** — der entscheidende Test, identisches Artefakt,
identischer Klickpfad:

| Preset | Freigabeversuch `in_review → approved` | Ergebnis |
|---|---|---|
| `extended` | `POST …/transitions/` | **HTTP 400** — blockiert (`acceptance_criteria`) |
| `minimal`  | `POST …/transitions/` | **HTTP 200** — Status wird `approved` |

Damit ist bewiesen: Das Preset schaltet ein reales serverseitiges Gate. **Kein Etikett.**

### 🔴 Die Governance-Lücke, die den Nutzen wieder aufhebt

**Der Preset-Wechsel ist ein einzelner Radio-Klick.** `PATCH /api/v1/workspaces/<id>/preset/`
→ 200. Beobachtet:

- **Kein Bestätigungsdialog.**
- **Keine Warnung** — auch nicht beim *Herunterstufen*.
- **Keine Begründungspflicht** — ausgerechnet dort, wo das Tool sonst überall eine
  Begründung verlangt.

Der Downgrade `extended → minimal` deaktiviert Baselines und hebt die
Änderungsgrund-Pflicht auf — reibungslos, in zwei Klicks, ohne Spur in der Oberfläche.

**In Kombination mit §4 ist das gravierend:** Ein Nutzer, der unter `extended` an der
unerfüllbaren `acceptance_criteria`-Hürde scheitert, hat als *einzigen funktionierenden
Ausweg* das Herunterstufen des gesamten Workspace-Rigors. Das Tool erzieht damit aktiv zum
Umgehen seiner eigenen Gates.

### Kleinere Inkonsistenz

Unter `minimal` verspricht das Label „change_reason: **optional**", die
**Übergangs-Begründung** wurde aber weiterhin verlangt (Panel „Begründung für → approved",
Bestätigen bis zur Eingabe deaktiviert). Speicher-Änderungsgrund und Transition-Begründung
folgen unterschiedlichen Regeln, die das Label nicht abbildet.

---

## 7. MOE / MOP / TPM — vorhanden, rudimentär oder abwesend?

**Antwort: vollständig abwesend.** Kein Feld, kein Panel, kein Artefakttyp, keine Kennzahl.

Geprüft:

| Prüfung | Ergebnis |
|---|---|
| Globale Suche „MOE", „Technical Performance", „Effectiveness" | keine Trefferregion |
| `/metrics` („SE-Prozess-Metriken") | nur **Prozess**-KPIs: Traceability-Coverage, Anforderungs-Volatilität, Workflow-Lücken, Offene Risiken, Kritische Risiken |
| `/goals` („Ziele") | Workspace-*Ziele* + KI-generiertes „Haupt-Ziel" — Zielbeschreibungen, **keine Messgrößen** (kein Zielwert, keine Schwelle, kein Istwert) |
| Formulare Need / Requirement / Architecture | kein Messgrößen-Feld |
| Quellcode `frontend/src` + `backend` (`MOE`, `MOP`, `TPM`, `measure_of_effectiveness`, `measure_of_performance`, `technical_performance`) | **0 Treffer** |

Es fehlt damit die gesamte Konzeptfamilie: keine Messgröße mit Zielwert/Schwellwert/Istwert,
kein Margin-Tracking, kein Verlauf gegen ein technisches Ziel, keine Verknüpfung einer
Messgröße an ein Requirement oder Architekturelement.

**Zur Einordnung — was es *stattdessen* gibt:** Das Datenmodell kann technische Attribute
durchaus tragen: **Verifikationsmethode** (Inspection/Review/Test/Analysis) auf Anforderungen,
**ASIL Level (Functional Safety)** (QM/A/B/C/D) und **Make-or-Buy Decision**
(Make/Buy/Reuse) auf Architekturelementen. Das sind ernsthafte SE-Attribute. MOE/MOP/TPM sind
also nicht aus Modellschwäche abwesend, sondern schlicht **nicht vorgesehen**.

---

## 8. Stellen, an denen die UI korrekter SE-Praxis widerspricht

Nach Schwere geordnet.

| # | Widerspruch | Beleg |
|---|---|---|
| **1** | **Der geführte „Ableiten"-Flow erzeugt einen Trace-Graphen, den der eigene SE-Auditor mit 4 Blockern zurückweist** (fehlender `derives-from`-Rücklink, Orphan-Kind, nicht allokiertes Elternteil, `satisfies`-loses Architekturelement). Wer dem Tool folgt, produziert Regelverstöße. | `39a-audit-before.png` |
| **2** | **`extended`-Freigabe-Gate verlangt `acceptance_criteria` — ein Feld, das die UI nirgends anbietet.** Weder ad-hoc- noch workspace-weite Custom Fields erfüllen es. Requirements sind unter `extended` in der UI nicht freigebbar. | `27a-gate-blocked.png` |
| **3** | **Die Baseline sperrt sichtbar nichts.** Kein Drift-Indikator auf Artefakt oder Baselines-Seite; Inspector-Diff vergleicht Artefakt-Versionen statt der Baseline; „Compare" deaktiviert; Baseline-Inhalt lädt nie (404). | `42b-baselines-after-drift.png` |
| **4** | **Traceability-Coverage 0,0 %** bei vorhandenen Derivation-/Decomposition-/Allocation-/Verification-Links und 1 von 2 verifizierten Anforderungen — die KPI bildet den Graphen nicht ab. | `19c-metrics.png` |
| **5** | **Rigor lässt sich per einzelnem Radio-Klick herunterstufen** — ohne Bestätigung, Warnung oder Begründung. Gates sind faktisch optional; bei blockierter Freigabe ist der Downgrade sogar der einzige Ausweg (→ #2). | `36-preset-minimal.png` |
| **6** | **Traceability-Ansicht zeigt nur abgeschnittene UUIDs** — keine Titel, keine Typen, keine Abdeckungsmarkierung. Die zentrale Nachvollziehbarkeitsansicht ist für Menschen unlesbar. | `19a-traceability.png` |
| **7** | **Zwei ID-Räume ohne Brücke** (Editor-ID vs. Artifact-ID); die Anwendung verwechselt sie selbst und erzeugt wiederholt 404 auf eigene Artefakte. | §0/§3 |
| **8** | **Impact-Baum ohne Zyklenerkennung** — 5 Artefakte / 4 Links erzeugen 25+ oszillierende Knoten. Bei Projektgröße unbrauchbar. | `21a-impact-expanded.png` |
| **9** | **„Anforderungen (hierarchical view)" zeigt das Artefakt selbst**, nicht Eltern oder Kinder — trotz existierendem Dekompositions-Link. | `15b-l2-created.png` |
| **10** | **Requirement-Ebenen (L0–L4) sind unsichtbar.** L1 und L2 sind visuell identisch (`SR`-Badge, flache Liste). Ebenen gibt es nur bei Architekturelementen. | `15b-l2-created.png` |
| **11** | **Change-Control-Pflicht uneinheitlich:** `Änderungsgrund *` auf Bedarf und Anforderung, **ohne** Pflichtmarkierung auf dem ArchitectureElement. | §4 |
| **12** | **Terminologie-Leck:** „Warum wird diese **Anforderung** geändert?" erscheint auf **Bedarf** und **ArchitectureElement** — untergräbt genau die Artefakttrennung, die das Tool sonst aufbaut. | `06b-need-detail.png` |

---

## 9. Weitere UI-Qualitätsbefunde (SE-relevant, aber nicht methodisch)

### 🔴 Layout: Anforderungseditor bei 1366×768 praktisch unbenutzbar

**Beleg:** `10-req-layout-1366x768.png` vs. `11a-1366-inspector-collapsed.png`

Im Standardzustand (Inspector **ausgeklappt**, so wird die Seite geladen) überdeckt der
Inspector den Editor:

| Viewport | Zustand des Anforderungseditors |
|---|---|
| 1366×768 | **~100 px sichtbar.** Speichern-Button, alle „Classification & Properties"-Felder, Change Control und TraceLinks sind unerreichbar. |
| 1600×1000 | Inhalte mitten im Wort abgeschnitten („Sp…" statt „Speichern", „W" statt „Workflow-Status", „K" statt „Komplexität"). |
| 1920×1080 | Nutzbar. |

Das Einklappen des Inspectors (`«`) stellt die Ansicht auf 1366 vollständig wieder her — die
Abhilfe existiert also, ist aber nicht der Standard. **1366×768 ist die häufigste
Laptop-Auflösung**; in diesem Zustand kann eine Anforderung nicht bearbeitet werden.

### Weitere Beobachtungen

- **Untersetzte i18n-Schlüssel im Workspace-Anlagedialog** — dem allerersten Schritt eines
  neuen Nutzers. Wörtlich angezeigt: `workspace.create.title`,
  `workspace.create.namePlaceholder`, `workspace.create.preset`, `workspace.create.language`,
  `workspace.create.cancel`. Nur „Erstellen" ist übersetzt. (`02b-ws-create-dialog.png`)
- **Sprachmischung** in deutscher UI: Buttons `Cancel` / `Create` in den Inline-Anlageformularen;
  Abschnittsüberschriften „General Information", „Classification & Properties",
  „Change Control", „Trace Links", „Incoming" / „Outgoing"; Auditor- und Gate-Meldungen
  vollständig englisch.
- **Architekturelement-Widerspruch:** Badge zeigt `L0` und „Rolle System", das Feld
  „Element-Typ" steht gleichzeitig auf `component`.
- **React-Warnung:** „Cannot update a component (`RequirementForm`) while rendering a different
  component (`CustomFieldsEditor`)" — Zustands-Update während des Renderings.
- **Speichern-Button überlappt die Titelüberschrift** des Artefakts in allen geprüften
  Auflösungen (`15b-l2-created.png`).
- **KI-Testfallentwurf ist inhaltsleer** (`LLM_PROVIDER=mock`, insofern erwartbar):
  Schritte lauten „Exercise the behaviour described by '<Titel>'" /
  „The system behaves as specified by the requirement." Kritisch ist nicht der Mock-Inhalt,
  sondern dass der so erzeugte Testfall **ohne jede Kennzeichnung** als regulärer TestCase
  gespeichert wird und in der Verifikations-Verlinkung wie ein echter Testfall zählt —
  ein potenzieller false-green-Pfad in der Coverage.

### Accessibility (Stichprobe über alle besuchten Seiten)

**Gut:** benannte Landmarks (`navigation "Main navigation"`,
`complementary "Inspektor für requirement"`), `tree` / `treeitem` mit `[selected]`,
Fehlermeldungen als `role="alert"`, Workflow-Status als `role="status"`,
`aria-expanded` an Menü-Buttons, `[disabled]` korrekt exponiert, Buttons mit sprechenden
Namen („Bezeichner 0367c8f5 kopieren", „Status ändern (aktuell: draft)").

**Mängel:**

1. **Unbenannte Formularsteuerelemente im Bedarfs-Formular.** Label und Control sind nicht
   verknüpft — der AX-Baum zeigt `- text: Titel` gefolgt von einer namenlosen `textbox`,
   ebenso bei „Kategorie" und „MoSCoW-Priorität". Screenreader-Nutzer erhalten dort
   unbeschriftete Felder. (Im Requirement-Formular ist es korrekt: `textbox "Titel *"`.)
2. **Traceability-Einträge sind reiner Text**, keine Links/Buttons → nicht per Tastatur
   erreichbar, keine ausgezeichnete Beziehung.
3. **Icon-Buttons ohne Textalternative:** `button "·"`, `button "▶"`, `button "≅"`,
   `button "⏱"` — teils ohne beschreibenden Namen.

---

## 10. Fazit der UI-Hälfte

**Was die UI belegt:** ReqogniLoom hat einen **echten methodischen Kern** — beschränkter
Zustandsautomat, Pflicht-Begründung je Übergang, erzwungene Change-Control, presetabhängige
Vollständigkeits-Gates und einen **SE-Auditor, der die Baseline blockiert**, bis der
Trace-Graph konsistent ist, inklusive funktionierender Auto-Remediation. Die Rigor-Presets
sind funktional nachweisbar verschieden. Need, Requirement und ArchitectureElement sind
strukturell unterschiedlich modelliert (MoSCoW vs. Verifikationsmethode vs. ASIL/Make-or-Buy).
Das ist deutlich mehr als eine Traceability-Fassade.

**Was die UI ebenso belegt:** Diese Mechanik ist an drei Stellen **nicht durchgängig
bedienbar**. Der geführte Ableitungspfad verletzt die eigenen Auditor-Regeln; das strengste
Freigabe-Gate ist über die Oberfläche unerfüllbar; und die Baseline — der eigentliche
CM-Anker — sperrt sichtbar nichts und macht Drift unsichtbar. Ergänzt um eine unlesbare
Traceability-Ansicht, eine auf 0,0 % feststehende Coverage-KPI und einen reibungslosen
Rigor-Downgrade ergibt sich das Bild: **Die Gates sind echt, aber die Wege durch sie hindurch
sind es teilweise nicht.**

Für die Bewertung „genuine SE-Methodik" heißt das: **Der Anspruch ist im Kern eingelöst, die
Durchgängigkeit nicht.** Die wertvollsten Korrekturen sind nicht neue Features, sondern das
Schließen der Lücken zwischen bereits vorhandenen Bausteinen — Ableiten-Flow an die
Auditor-Regeln angleichen, `acceptance_criteria` im Formular rendern, Baseline-Drift anzeigen,
Traceability mit Titeln statt UUIDs.

**Nicht adressierbar durch Reparatur:** MOE/MOP/TPM fehlen vollständig und müssten als
Konzept neu eingeführt werden.

---

## Anhang: Belegdateien

Screenshots: `docs/assets/systemaudit-ui-2026-08-07/`

| Datei | Zeigt |
|---|---|
| `02b-ws-create-dialog.png` | Rohe i18n-Schlüssel im Workspace-Anlagedialog |
| `06b-need-detail.png` | Bedarfs-Detailansicht, Change Control, Inspector-Diff |
| `07a-save-without-reason.png` | „Änderungsgrund ist erforderlich." — Gate greift |
| `09b-derive-done.png` | Abgeleitetes L1-Requirement, Ableitungskette, Derivation-Link |
| `10-req-layout-1366x768.png` | Editor durch Inspector verdeckt (1366×768) |
| `11a-1366-inspector-collapsed.png` | Gleiche Auflösung, Inspector eingeklappt — nutzbar |
| `15b-l2-created.png` | L1/L2 visuell identisch; „hierarchical view" zeigt sich selbst |
| `19a-traceability.png` | Traceability-Ansicht als UUID-Liste |
| `19c-metrics.png` | Traceability-Coverage 0,0 % |
| `21a-impact-expanded.png` | Zyklischer, nicht deduplizierter Impact-Baum |
| `24b-wf-with-reason.png` | Pflicht-Begründungspanel mit deaktiviertem „Bestätigen" |
| `27a-gate-blocked.png` | `extended`-Freigabe-Gate: `acceptance_criteria` fehlt im Formular |
| `33a-settings-extended.png` | Preset-Optionen mit expliziter Wirkungsbeschreibung |
| `39a-audit-before.png` | SE-Auditor: 4 Blocker aus dem tooleigenen Ableiten-Flow |
| `41b-baseline-created.png` | Baseline nach `Findings: 0`; „Captured items — Laden…" |
| `42b-baselines-after-drift.png` | Nach Änderung eines baselinierten Artefakts: kein Drift-Hinweis |
