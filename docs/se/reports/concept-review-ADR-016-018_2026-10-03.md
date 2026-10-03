---
type: REVIEW
scope: adr-016-018
status: final
date: 2026-10-03
author_agent: concept-reviewer
review_id: RVW-2026-10-03-001
target_files:
  - docs/se/ADR/ADR-016_preset_ssot_und_refines_hierarchiekante.md
  - docs/se/ADR/ADR-017_plugin_server_versions_ssot.md
  - docs/se/ADR/ADR-018_t_inline_default_und_dynamische_keys.md
branch: feat/w2-p1
---

# Concept-Review: ADR-016, ADR-017, ADR-018 (MADR-Minimal, Branch `feat/w2-p1`)

## Scope

Drei neue ADRs (`status: proposed`) auf `feat/w2-p1`, die W3-Arbeitseinheiten
entsperren sollen:

| ADR | Entscheidungsgegenstand | Entsperrt |
|-----|-------------------------|-----------|
| ADR-016 | Preset-Teil-SSOT, fail-closed Downgrade-Gate, `refines` nicht als Hierarchiekante | DATA-10, DOC-01 |
| ADR-017 | `VERSION` als Server-SSOT, Plugin-Manifest-Generierung, `minServerVersion` | PLUG-04 |
| ADR-018 | i18n: Inline-Default + zwei Ratchets, dynamische Keys ohne Typschema verboten | DOC-02 |

**Prüfstandard:** AGENTS.md „SE-Kaskade: ADR-Standard" (MADR-Minimal) +
`.agent-meta/schemas/se-adr.schema.json`. **Read-only:** Es wurden keine ADR-/REQ-Inhalte
geändert, keine Commits, kein Push.

**Verifizierte Belege (Stichprobe, alle bestätigt):**

- `presets/registry.py:13` Docstring „Single Source of Truth for all preset rule data";
  `:10-12` data-driven/immutable.
- `presets/gate.py:536-549` – `except Exception: ... pass` (fail-open) bestätigt.
- `traceability/audit/hierarchy.py:34-45` `refines` bewusst ausgeschlossen,
  `:179-195` `PARENT_TO_CHILD`/`CHILD_TO_PARENT`/`HIERARCHY_LINK_TYPES`.
- `mcp_server/protocol_handler.py:503-506` `serverInfo.version` hart `"1.0.0"`;
  `mcp_server/views.py:482` hart `"1.0.0"` – beide bestätigt.
- `reqogniloom/version.py:74-136` Auflösung `APP_VERSION → VERSION → "unknown"` +
  öffentliche `VersionView` – bestätigt. `VERSION` = `1.8.0-beta.17` – bestätigt.
- `frontend/src/test/i18n-parity.test.ts:186` `MISSING_KEY_BASELINE = 116`;
  `:94-99` nur String-Literale; `:202-223` rot nur bei Anstieg – bestätigt.
  `:47-59` prüft de/en in **beide** Richtungen – bestätigt.
- `link_types/defaults.py` validiert gegen `BUILTIN_LINK_TYPES` und **fällt zurück**
  (kein hartes Verwerfen).
- Alle `affected_reqs` existieren; `open_adrs` existiert in `docs/se` tatsächlich nicht
  (AUD-2026-09-333 bestätigt). Keine ADR-ID-Wiederverwendung.

---

## ADR-016 — Preset-Teil-SSOT / fail-closed Gate / `refines`

**Verdict: APPROVED** (keine major-Befunde; Umsetzung von DATA-10/DOC-01 freigebbar).

### Prüfmatrix

| Kriterium | Ergebnis |
|---|---|
| Frontmatter-Pflichtfelder (Schema) | ✅ alle vorhanden, `adr_id` matcht `^ADR-\d{3}$`, `status: proposed`, `date` ISO, `deciders` ≥1 |
| ≥2 Alternativen inkl. rejected | ✅ A (verworfen), B (gewählt), C (verworfen), D1/D2 (Teilentscheidung) |
| Konsequenzen positiv UND negativ | ✅ beide Blöcke substantiell |
| `affected_reqs` belegt / nicht leer | ✅ 11 IDs, alle existent, Datei+Zeile korrekt |
| ADR-ID-Muster / keine Wiederverwendung | ✅ `ADR-016` einmalig |

### Findings

| ID | Severity | Dimension | Category | Beschreibung | Suggested Fix |
|----|----------|-----------|----------|--------------|---------------|
| RVW-2026-10-03-001-01 | minor | Vollständigkeit/Konsistenz | Klassifikation nicht enumeriert | Die zentrale Tatsachenbehauptung „7 datengetrieben / 5 Code" wird nicht enumeriert; die ADR-eigene Daten-Liste (Pflichtfelder, Features, Baseline-Scope, Change-Reason) lässt das im Registry real datenhaltige `workflow_configurability` (`registry.py:77,104-108`) weg und weicht von Kandidat #2 Option B ab (dort waren Attribut-/Invarianten-Regeln Teil der SSOT). | Die 7/5-Regeln explizit auflisten, `workflow_configurability` der Daten-Seite zuordnen und die bewusste Divergenz zu Kandidat #2 benennen. |
| RVW-2026-10-03-001-02 | minor | Feasibility/Logik | Mechanismus unklar | Entscheidung Punkt 4 fordert, `refines` als Dekompositions-Default „validiert abzuweisen"; `link_types/defaults.py:_resolve` **fällt** bei unbekanntem Typ jedoch auf den Default zurück (Warnung, kein Reject). Ein reiner „Hierarchie-Typen"-Filter würde `refines` still ersetzen, nicht abweisen. | Festlegen: hartes Reject (Fehler) vs. stiller Fallback; `refines` explizit nennen und im Akzeptanztest (`test_default_link_type_env_989.py`) pinnen. |
| RVW-2026-10-03-001-03 | info | Konsistenz | Dokumentationsreferenz | Der zu korrigierende Docstring verweist auf `(ADR-04)` – eine andere (Komponenten-)ADR-Nummer; nach Korrektur bliebe der Verweis evtl. falsch. | Beim Docstring-Fix prüfen, ob `ADR-04` eine Komponenten-ADR oder stale ist, und korrekt referenzieren. |
| RVW-2026-10-03-001-04 | minor | Risiko | Threat-Model | Der fail-open-Downgrade-Pfad ist sicherheits-/integritätsrelevant (Baseline-Schutz in Multi-Tenancy), wird aber nur als Korrektheitsdefekt behandelt; die 4 Threat-Model-Fragen sind nicht explizit beantwortet. | Kurze Threat-Model-Notiz (s. unten) in „Kontext"/„Konsequenzen" ergänzen. |

### Threat-Model (4 Fragen, verdichtet)

1. **Was gebaut?** Preset-Registry + Downgrade-Gate; Daten: Presets, Baselines, Artefakte;
   Auth RBAC + Item-Level; Nutzer = authentifizierte Tenant-User.
2. **Was schiefgeht?** fail-open Gate ⇒ unzulässiger Extended→Standard/Minimal-Downgrade
   trotz globaler Baselines ⇒ Integritäts-/Schutzverlust; falsche SSOT-Zusage ⇒
   Fehlentscheidungen auf falscher Grundlage.
3. **Gegenmaßnahme?** fail-closed (block/error) + explizite Testkonfiguration.
4. **Konsequenz?** unzulässige Downgrades/Baseline-Verletzung möglich; kein Rohdatenverlust,
   aber Compliance-/Reputationsrisiko. → als Notiz nachzutragen (001-04).

---

## ADR-017 — `VERSION` als Server-SSOT / Plugin-Manifeste / `minServerVersion`

**Verdict: CHANGES_REQUESTED** (2× major; Server-Teil tragfähig, Plugin-Teil nicht
entscheidungsreif).

### Prüfmatrix

| Kriterium | Ergebnis |
|---|---|
| Frontmatter-Pflichtfelder (Schema) | ✅ vollständig |
| ≥2 Alternativen inkl. rejected | ✅ A (gewählt), B (verworfen), C (verworfen), Teilfrage |
| Konsequenzen positiv UND negativ | ✅ beide Blöcke |
| `affected_reqs` belegt / nicht leer | ✅ 5 IDs existent, aber **nur Server-/MCP-Zusagen** |
| ADR-ID-Muster / keine Wiederverwendung | ✅ `ADR-017` einmalig |

### Findings

| ID | Severity | Dimension | Category | Beschreibung | Suggested Fix |
|----|----------|-----------|----------|--------------|---------------|
| RVW-2026-10-03-002-01 | major | Logik/Vollständigkeit | Entscheidung nicht präzise | Entscheidung Punkt 2 lässt das Python-POC-Plugin explizit offen („entweder auf Build-Generierung umstellen **oder** als unabhängig deklarieren") und delegiert an Offener Punkt 4. Eine „entweder/oder"-Aussage ist keine prüfbare MADR-Entscheidung. | Eine Variante wählen (Empfehlung: POC-Artefakt = unabhängige SemVer mit `minServerVersion`) und die andere als verworfen markieren. |
| RVW-2026-10-03-002-02 | major | Vollständigkeit/Traceability | Fehlende REQ-Anker | Das ADR stellt selbst fest, dass **keine** REQ die Plugin-Versionierung regelt; `affected_reqs` belegen nur Server/MCP. Die Plugin-Hälfte der Entscheidung hängt damit ohne Anforderungsanker in der Kaskade. | Entweder `requirements` beauftragen, eine REQ (Integration/API) anzulegen, oder den ADR-Scope auf Server-/Protokoll-Version begrenzen und Plugin-Versionierung explizit als Nicht-Produkt-Zusage ausweisen. |
| RVW-2026-10-03-002-03 | minor | Konsistenz | Feldvertrag unklar | Entscheidung Punkt 3/4 vermengt `minServerVersion` (neu) mit `engines.hermes` (heute dekorativ). Es bleibt offen, welches Feld verbindlicher Vertrag wird und wie es validiert/erzwungen wird. | Canonical Field benennen (1 Feld), Schema/Validierung skizzieren; `engines.hermes` eindeutig als zu ersetzendes oder zu entfernendes Dekor markieren. |
| RVW-2026-10-03-002-04 | minor | Risiko | Threat-Model | Die sichtbare Versions-Parität (`serverInfo.version`, öffentliche `/api/v1/version/`) und der neue Kompatibilitätsvertrag für Dritt-Plugins sind security-/supply-chain-relevant; die 4 Fragen fehlen. | Kurze Threat-Model-Notiz ergänzen (s. unten). |
| RVW-2026-10-03-002-05 | info | Konsistenz | Begriff | „Option B … VERWORFEN (als alleiniges Modell)" und gleichzeitig „A mit B-Ergänzung" ist korrekt, aber missverständlich formulierbar. | Formulierung schärfen: „B als alleiniges Modell verworfen; B-Bausteine als Ergänzung übernommen". |

### Threat-Model (4 Fragen, verdichtet)

1. **Was gebaut?** Versions-Exposition via MCP `serverInfo` + öffentliche
   `/api/v1/version/`; Build-Generierung von Manifesten; Kompatibilitätsfeld für
   Dritt-Plugins.
2. **Was schiefgeht?** Versions-Disclosure erleichtert CVE-Korrelation (bereits durch
   gekürzten SHA entschärft, `version.py:114-122`); falsche/erzwungene
   Kompatibilitätsangabe eines Dritt-Plugins kann Clients brechen.
3. **Gegenmaßnahme?** Reale Version aus `VERSION`, gekürzter SHA bleibt; Kompatibilitätsfeld
   nur Vertrag, wenn validiert, sonst entfernen (Punkt 4).
4. **Konsequenz?** geringe Recon-Fläche; Fehl-Kompatibilitätszusagen sind Host-Risiko. →
   als Notiz nachzutragen (002-04).

---

## ADR-018 — i18n-Vertrag: Inline-Default + zwei Ratchets / dynamische Keys

**Verdict: CHANGES_REQUESTED** (1× major: zentrale Mechanik nicht erzwingbar).

### Prüfmatrix

| Kriterium | Ergebnis |
|---|---|
| Frontmatter-Pflichtfelder (Schema) | ✅ vollständig |
| ≥2 Alternativen inkl. rejected | ✅ A, B (gewählt), C (verworfen), Teilfrage |
| Konsequenzen positiv UND negativ | ✅ beide Blöcke |
| `affected_reqs` belegt / nicht leer | ✅ 9 IDs existent; `REQ-L1-094`-Matrixstatus `Not Implemented` korrekt zitiert |
| ADR-ID-Muster / keine Wiederverwendung | ✅ `ADR-018` einmalig |

### Findings

| ID | Severity | Dimension | Category | Beschreibung | Suggested Fix |
|----|----------|-----------|----------|--------------|---------------|
| RVW-2026-10-03-003-01 | major | Logik/Feasibility | Enforcement-Lücke | Das Kernversprechen von Option B ist ein **monoton sinkender** Ratchet (fehlende Keys + Inline-Defaults), angeblich „CI-erzwingbar". Das beschriebene Frozen-Ceiling-Ratchet (`toBeLessThanOrEqual`, rot nur bei Anstieg) kann eine **Pflicht zur Senkung** nicht erzwingen. Ohne definierten Mechanismus degeneriert Option B genau zum eingefrorenen Soll, das das ADR kritisiert. | Enforcement explizit definieren: z. B. Senkung pro Release/PR erzwungen (Strict-Lower-Regel, Budget mit Ablaufdatum, oder CI-Job, der eine unveränderte Baseline über N Läufe rot macht). Sonst als Policy (nicht „CI-erzwingbar") kennzeichnen. |
| RVW-2026-10-03-003-02 | minor | Konsistenz | Zahlenbegriff vermischt | Entscheidung Punkt 2 setzt „Locale-Ceiling = die kanonische Key-Zahl (DOC-02: 116)"; `116` ist die **Missing-Key-Baseline** (`MISSING_KEY_BASELINE`), nicht die kanonische Key-Anzahl der Locale-Dateien. | Begriffe trennen: Missing-Key-Ceiling (=116, sinkend) vs. kanonische Gesamt-Key-Zahl; Zahl je Metrik benennen. |
| RVW-2026-10-03-003-03 | minor | Logik | Interner Widerspruch | Kontext Punkt 5 sagt, das ADR entscheide nur (b)/(c) und „ordne (a) als Zielbild ein"; Entscheidung Punkt 4 entscheidet (a) faktisch („Verbindliche Quelle ist der Code-Key"). | Entweder (a) als entschieden deklarieren oder Punkt 4 als Zielbild/non-normativ markieren. |
| RVW-2026-10-03-003-04 | info | Vollständigkeit | Detektor fehlt | Der geforderte zweite Ratchet misst `t(key, default)`-Stellen, aber `T_CALL_PATTERN` (Zeile 99) erfasst das Default-Argument gar nicht; zudem bleiben dynamische Keys mit Default blind. | In DOC-02 einen separaten Detektor für das zweite Argument vorsehen; Coverage-Grenze dokumentieren. |

### Threat-Model (verkürzt, interne UI)

Kein sicherheitsrelevanter Angriffsvektor. Worst case: falschsprachige/rohe Keys im UI
(Reputations-/Usability-Effekt, kein Datenrisiko). Eine Frage genügt.

---

## Querschnitt

| ID | Severity | Beschreibung | Suggested Fix |
|----|----------|--------------|---------------|
| RVW-2026-10-03-000-01 | info | Alle drei ADRs listen `deciders: [user, senior-developer]` und wurden von `senior-developer` erstellt; die SE-Kaskade weist Erstellung/Statuswechsel `se-architect` zu (ADR-015 setzt dieselbe Praxis). Kein formaler Schema-Verstoß, aber Prozessabweichung. | Praxis bestätigen (User-Override) oder Rollenkonformität herstellen; mind. im Lifecycle-Vermerk benennen. |

---

## Gesamtbewertung

**Reif für `proposed → review`?** Ja — alle drei sind strukturell MADR-konform, quellenbelegt
und ehrlich über ihre Grenzen. **Reif für `accepted` durch den User?**

- **ADR-016: ja.** Empfehlung freigebbar; die Findings sind Präzisierungen ohne
  Entscheidungsänderung. **Entsperrt DATA-10/DOC-01.**
- **ADR-017: nein, vor Freigabe nachbessern.** Server-SSOT (der eigentliche PLUG-04-Kern)
  ist entschieden und tragfähig; die **Plugin-Hälfte** ist per „entweder/oder" offen
  (002-01) und ohne REQ-Anker (002-02). Entweder nachschärfen oder Scope auf
  Server-Version begrenzen.
- **ADR-018: nein, vor Freigabe nachbessern.** Die Ratchet-"Zielbild"-Logik ist
  nachvollziehbar, aber die zentrale Zusage „monoton sinkend = CI-erzwingbar" ist mit der
  beschriebenen Mechanik nicht einlösbar (003-01). Nach Definition des Enforcement-Mechanismus
  freigebbar. **DOC-02 startet erst nach dieser Klärung.**

**Was blockiert konkret:** ADR-017 Findings 002-01/002-02 und ADR-018 Finding 003-01.
Es liegen **keine critical-Befunde** vor; ein BLOCKED ist nicht angezeigt. Nach Behebung der
drei major-Befunde steht der User-Freigabe (`accepted`) nichts entgegen; der Statuswechsel
selbst erfolgt durch `se-architect`/User, nicht durch den Autor.

---

# Iteration 2 — Re-Review (RVW-2026-10-03-004)

**Datum:** 2026-10-03 · **Autor:** `concept-reviewer` · **Branch:** `feat/w2-p1`
**Basis:** Nachbesserungs-Commit `245921cb` (`docs(adr): incorporate ADR-016..018 review
findings (iter 1)`, geändert: nur die drei ADR-Dateien + dieser Report, keine Produktcode-
Änderung). **Read-only:** keine ADR-/REQ-/Code-Änderung, kein Commit, kein Push.

**Prüfgegenstand:** ausschließlich die drei Iteration-1-majors `002-01`, `002-02`, `003-01`
sowie die eingearbeiteten minors und `000-01`. Keine neuen Prüfdimensionen (Revisionsregel).

## Verdict je ADR (Iteration 2)

| ADR | Iteration 1 | **Iteration 2** | Begründung |
|-----|-------------|-----------------|------------|
| **ADR-016** | APPROVED | **APPROVED** | Alle minors präzisierend eingearbeitet; Decision-4-Mechanismus jetzt entschieden (Fallback, kein Reject). |
| **ADR-017** | CHANGES_REQUESTED | **APPROVED** | Beide majors aufgelöst: „entweder/oder" in eine Variante überführt, Plugin-Hälfte per Scope-Abgrenzung als Nicht-Produkt ausgewiesen. |
| **ADR-018** | CHANGES_REQUESTED | **APPROVED** | Major `003-01` durch definierten Enforcement (`Non-Increase` + `Deadline-Budget`) eingelöst; alle minors eingearbeitet. |

## Status der Fokus-Majors

| Finding | Status | Nachweis (Iteration 2) | Restrisiko |
|---------|--------|------------------------|-----------|
| **002-01** Plugin-Versionierung „entweder/oder" | **resolved** | Entscheidung Punkt 2 wählt jetzt **eine** Variante: POC-Artefakt `integrations/hermes-agent-plugin` = eigenständig semverisiert (`0.1.0`) mit `minServerVersion`; die Build-Generierungs-Alternative ist explizit **„verworfen"**. Titel + Frontmatter tragen die Entscheidung. | Kein ADR-Restrisiko. Die *Build-Generierung* der produktiven Bundle-Manifeste bleibt eine Behauptung, die `PLUG-04` nachweisen muss (neuer minor `017-R2-01`). |
| **002-02** Fehlender REQ-Anker Plugin | **resolved (mit dokumentiertem Offen-Punkt)** | Kontext 4, Entscheidung Punkt 6 und Offener Punkt 2 begrenzen den ADR-Scope ausdrücklich auf die **Server-/Protokoll-Version** (REQ-verankert) und weisen die Plugin-Versionierung als **Nicht-Produkt-Zusage** aus; **keine** REQ erfunden. `affected_reqs` bleibt konsistent server-lastig. | Der **Traceability-Gap selbst bleibt** bestehen und ist bewusst `requirements` überlassen (REQ anlegen *oder* Nicht-Produkt festschreiben). Organisatorisch, kein ADR-Blocker. |
| **003-01** Nicht erzwingbarer Ratchet | **resolved (mit Restrisiko)** | Entscheidung Punkt 2 definiert Enforcement konkret: **Non-Increase** (`toBeLessThanOrEqual`, verifiziert `i18n-parity.test.ts:219`) **plus Deadline-Budget** („Deadline erreicht und Wert > Ziel ⇒ CI rot"). Das war explizit eine der in Iteration 1 akzeptierten Optionen. | (a) „monoton" ist tatsächlich **deadline-stufenweise**, nicht schrittweise; (b) **Re-Arm** nach Zielerreichung ist nicht geregelt (Re-Freeze möglich). Zahl/Deadline sind korrekt als `DOC-02`-Parameter ausgelagert. Neuer minor `018-R2-01`. |

## Verbleibende Findings (Iteration 2)

Alle Iteration-1-minors (`001-01`–`001-04`, `002-03`–`002-05`, `003-02`–`003-04`) sind
**eingearbeitet und auf resolved gesetzt** (stichprobenartig verifiziert: Enumerierung +
`workflow_configurability` in ADR-016 Kontext 1/Option B; `ADR-04`-Abgrenzung; Threat-Model
in 016/017; kanonisches Feld `minServerVersion`; Formulierung Option B; getrennte Metriken
003-02; „(a) entschieden" 003-03; Default-Argument-Detektor 003-04).

| ID | Severity | Dimension | Findings |
|----|----------|-----------|----------|
| **000-01** | **info** | Prozess/Kaskade | **Offen (unverändert).** Alle drei ADRs listen `deciders: [user, senior-developer]` und wurden von `senior-developer` erstellt; die SE-Kaskade weist Erzeugung/Statuswechsel `se-architect` zu. Kein Schema-Verstoß, aber Prozessabweichung. → Vor dem Statuswechsel `accepted`: als **User-Override** bestätigen oder Rollenkonformität herstellen; Statuswechsel selbst durch `se-architect`/User. |
| **017-R2-01** | **minor** | Feasibility/Konsistenz | Die Zusage „die im Repo produktiv ausgelieferten Bundle-Manifeste (`dist/plugins/**`, TS-Hermes-Plugin) werden beim Build aus `VERSION` erzeugt … kann nicht driften" ist eine **Mechanik-Behauptung**: `integrations/hermes-plugin/reqogniloom/hermes-plugin.json` liegt heute committed mit `1.8.0-beta.17` vor (Hand-Sync vs. generiert ist aus dem ADR nicht belegt). → `PLUG-04` pinnt die Generierung oder benennt das Manifest explizit als hand-gepflegt. Nicht blockierend. |
| **018-R2-01** | **minor** | Logik/Feasibility | `Deadline-Budget` erzwingt Senkung **bis** zur Deadline, nicht „monoton" im Wortsinn; nach Erreichen eines Ziels ist kein Folge-Ziel/-Deadline (Re-Arm) definiert ⇒ theoretischer Re-Freeze. → In `DOC-02` Re-Arm-Regel (nächstes Ziel/Deadline) oder Wortwahl „deadline-stufenweise sinkend" schärfen. Nicht blockierend. |

*(ADR-016: keine verbleibenden Findings außer `000-01`.)*

## Reifegrad für `proposed → accepted` (Q4)

**Ja — alle drei sind inhaltlich reif für die User-Freigabe.** Es liegen **keine** critical-
und **keine** major-Befunde mehr vor; ein BLOCKED ist nicht angezeigt. Die Restpunkte sind
`info`/`minor` und ändern keine Entscheidung.

| ADR | Reif? | Was je ADR noch offen ist |
|-----|-------|---------------------------|
| **ADR-016** | **Ja** | Nur `000-01` (Prozess/deciders). Umsetzung `DATA-10`/`DOC-01` startet nach Freigabe; enthält die Code-Änderungen (Docstring, fail-closed-Gate, `refines`-Kommentar, `HIERARCHY_LINK_TYPES`-Einschränkung + Test). |
| **ADR-017** | **Ja** | `000-01`; offener **Traceability-Gap** Plugin-Versionierung (bewusst `requirements` überlassen); `017-R2-01` (Build-Generierung nachweisen). Freigabe deckt **nur die Server-/MCP-Hälfte** als Produktentscheidung ab; die Plugin-Aussage bleibt Nicht-Produkt-Notiz. |
| **ADR-018** | **Ja** | `000-01`; `DOC-02` muss Ziel/Deadline-Werte setzen, den **Default-Argument-Detektor** bauen und die Re-Arm-/Monotonie-Semantik klären (`018-R2-01`); Zahlen bewusst nicht im ADR. |

**Freigabehinweis:** Der Statuswechsel `proposed → accepted` ist durch `se-architect`/User
vorzunehmen (nicht durch den Autor); `000-01` ist dabei als User-Override zu bestätigen.
`open_adrs` (AUD-2026-09-333) existiert weiterhin nicht — die REQ↔ADR-Verknüpfung bleibt ein
separates, ADR-unabhängiges Thema.

## Verifikationsbelege (Iteration 2, gelesen)

- `git show --stat 245921cb`: nur die 3 ADR-Dateien + dieser Report — **keine** Produktcode-Änderung (Entscheidungen sind noch nicht umgesetzt, korrekt für `proposed`).
- `i18n-parity.test.ts:99` (`T_CALL_PATTERN` nur erstes Literal-Argument), `:186` (`MISSING_KEY_BASELINE = 116`), `:219` (`toBeLessThanOrEqual`) — kein Deadline/Feld vorhanden ⇒ `Deadline-Budget` ist neu in `DOC-02` (stützt `018-R2-01`).
- `mcp_server/protocol_handler.py:505` und `mcp_server/views.py:482` weiterhin hart `"1.0.0"` — ADR-017-Kontext unverändert korrekt.
- `traceability/audit/hierarchy.py:179-195`: `HIERARCHY_LINK_TYPES = {decomposes, derives-from}`, `refines` ausgeschlossen mit „open … ADR candidate (vi)" — ADR-016 Entscheidung 3/4 inhaltlich korrekt.
- `link_types/defaults.py:36-48`: `_resolve` prüft nur `BUILTIN_LINK_TYPES` (Fallback+Warnung) — ADR-016 Entscheidung 4 erweitert genau diesen Punkt korrekt.
- `presets/registry.py:87` `workflow_configurability: str` in `PresetConfig` — ADR-016-Klassifikation als datenförmig belegt.
- `presets/gate.py:547-549` `except Exception: pass` unverändert — ADR-016 Entscheidung 2 (fail-closed) bleibt erforderlich.

---

## Lifecycle-Abschluss (2026-10-03)

Die drei ADRs wurden am 2026-10-03 durch den User von `proposed` auf `accepted` gesetzt
(Grund: Iteration 2 APPROVED, keine critical/major offen). Der Statuswechsel erfolgte durch
den User als `se-architect`-Vertreter.
Prozess-Finding `000-01` (Ersteller `senior-developer` statt `se-architect`) ist damit als
dokumentierte, user-getragene Rollen-Abweichung im Review-Trail festgehalten — kein Blocker.
Offene, nicht-blockierende Folgen: `017-R2-01` (Build-Generierungs-Nachweis → PLUG-04),
`018-R2-01` (Re-Arm/Deadline-Semantik → DOC-02), `open_adrs` (AUD-2026-09-333).
