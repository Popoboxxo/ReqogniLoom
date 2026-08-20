# Phase 6 — Agenten-Templates für Downstream-Projekte (Design)

> Spec zu Phase 6 aus `docs/superpowers/specs/Archive/2026-07-23-reqogniloom-status-unification-design.md` §9.

## 1. Ziel und Abgrenzung

**Ziel:** Fünf provider-agnostische, agent-meta-kompatible Agenten-Templates bereitstellen,
die ein **fremdes/Downstream-Projekt** installieren kann, um mit ReqogniLoom über dessen
MCP-Server (`/mcp/sse/`) zu arbeiten.

**Explizit NICHT Teil dieser Spec:**

- ReqogniLooms eigene `se-*`-Rollen (Weiterentwicklung von ReqogniLoom selbst) — keine
  Überschneidung, keine Änderung an diesen Rollen.
- Home-Assistant-spezifische Template-Inhalte (waren nur Beispiel des Vision-Autors).
- `allowed_reviewers`, `require_pair_review`, Batch-Review-Operationen.
- Ein vollständiger Update-/Sync-Mechanismus für Downstream-Templates (analog `sync.py` +
  `context-hashes.json` in agent-meta). Stattdessen: ein einzelnes `compatible_with`-Feld
  im Frontmatter (siehe §5) als minimale Drift-Absicherung.
- Tatsächliche Durchsetzung der Review-Policy über alle Provider hinweg — der in §6
  beschriebene Hook ist eine **optionale Referenzimplementierung für Claude Code**, kein
  garantierter Mechanismus für andere Plattformen.

## 2. Ablageort und Distribution

```
docs/agent-templates/
  README.md                        # Übersicht, Installationsanleitung, Kompatibilitätshinweis
  BOOTSTRAP.md                      # Einstiegs-Snippet für CLAUDE.md/AGENTS.md/GEMINI.md eines Konsumenten-Projekts
  requirements-architect.md
  test-engineer.md
  risk-analyst.md
  change-manager.md
  quality-auditor.md
  hooks/
    review-policy-gate.sh           # optionale Claude-Code-Referenz (PreToolUse-Hook)
    review-policy-gate.md           # Doku zum Hook: Installation, Konfiguration, Grenzen
```

Alle Dateien leben im ReqogniLoom-Repo selbst (nicht im `agent-meta`-Submodul) und werden
von einem Downstream-Projekt manuell kopiert — ReqogniLoom ist Anbieter dieser Templates,
nicht deren Betreiber. Ein Downstream-Projekt, das selbst `agent-meta` nutzt, kann die
5 Rollen-Dateien 1:1 unter `agents/1-generic/` oder `agents/2-platform/` ablegen; das
Frontmatter-Format ist identisch zu bestehenden `agent-meta`-Templates (siehe §5).

## 3. Rollen-Übersicht

| Rolle | Kernaufgabe | Review-Profil |
|---|---|---|
| `requirements-architect` | Stakeholder-Needs erfassen, Requirements ableiten/dekomponieren (V-Modell L0→L3) | `review_changes` |
| `test-engineer` | Testfälle anlegen/verknüpfen, Test-Runs protokollieren | `auto` |
| `risk-analyst` | Risiken identifizieren, mit Requirements/Architektur verknüpfen | `review_high_risk` |
| `change-manager` | ADRs und Issues verwalten, Requirement-/Architektur-Änderungen freigeben | `review_high_risk` |
| `quality-auditor` | Traceability- und Coverage-Prüfungen, rein lesend | `auto` (kein Schreibzugriff) |

Review-Profil-Werte entsprechen den ReqogniLoom-`ReviewPolicy`-Modes (`auto` /
`review_changes` / `review_high_risk`, siehe `persistence.models.REVIEW_POLICY_MODES`).
Sie sind eine **Empfehlung im Prompt-Text**, kein serverseitig erzwungener Wert — das
Downstream-Projekt setzt die tatsächliche Policy über
`PUT /api/v1/review-policy/` bzw. das `ReviewPolicy`-Modell selbst.

## 4. Domänenwissen, das jede Rolle kennen muss

Jedes Template referenziert im System-Prompt (nicht nur oberflächlich erwähnt, sondern
mit konkreten Werten):

- **REQ-ID-Schema:** `REQ-L0-*` (Stakeholder Needs) … `REQ-L3-*` (Components), siehe
  `docs/se/traceability-matrix.md`.
- **8 Trace-Link-Typen:** `TRACE_TO`, `DERIVED_FROM`, `IMPLEMENTS`, `TESTS`, `VERIFIES`,
  `RELATED_TO`, `CONFLICTS_WITH`, `SUPERCEDES`.
- **3 Rigor-Presets:** `minimal` / `standard` / `extended` (gleiches Datenmodell,
  unterschiedliche Pflichtfelder).
- **3 Baseline-Scopes:** Document / Project / Global (eine Entität, ADR-07) — relevant für
  `change-manager` und `quality-auditor`.
- **V-Modell L0–L4:** Stakeholder Needs → System Requirements → Subsystems → Components →
  Presentation.
- **Konfigurierbare Workflow-State-Machines** pro Workspace — relevant für `change-manager`.

Jede Rollendatei MUSS mindestens die für ihre Kernaufgabe relevanten Punkte aus dieser
Liste im Klartext nennen (nicht per Verweis auf eine andere Datei) — das Template soll
ohne Zugriff auf den ReqogniLoom-Sourcecode korrekt funktionieren.

## 5. Frontmatter-Format (alle 5 Rollen identisch strukturiert)

```yaml
---
name: <rolle>
version: 1.0.0
description: <eine Zeile, was die Rolle tut>
compatible_with: "reqogniloom>=1.0.0"
tools:
- <MCP-Tool-Name>
- ...
---
```

- `compatible_with` referenziert die ReqogniLoom-Produktversion aus der Root-`VERSION`-Datei
  (aktuell `1.0.0`). Bei einer Breaking-Change-fähigen MCP-Tool-Änderung (Tool umbenannt/
  entfernt, Pflichtparameter hinzugefügt) MUSS die untere Schranke in allen 5 Dateien
  zusammen mit einem Minor- oder Major-Bump der Root-`VERSION` aktualisiert werden.
- `tools` ist die vollständige, geschlossene Whitelist — kein Freitext-Vorbehalt, keine
  Wildcards. Jeder MCP-Tool-Name wird einzeln aufgeführt (siehe §5.1–5.5 für die exakten
  Listen).

### 5.1 requirements-architect

```yaml
tools:
- needs.read
- needs.create
- needs.update
- needs.get_traces
- needs.derive_requirements
- requirement.get
- requirement.query
- requirement.create
- requirement.update
- requirement.decompose
- requirement.validate
- requirement.derive
- requirement.check_consistency
- ai_derivation.derive_requirements_from_need
- ai_derivation.decompose_requirement_next_level
- traceability.query
- traceability.suggest_links
- artifact.search
- artifact.get_tree
- workspace.get_context
- glossary.read
- prompt_template.get
```

### 5.2 test-engineer

```yaml
tools:
- test.get
- test.query
- test.create
- test.update
- test.link
- test.run_create
- test.run_get
- test.run_report_results
- test.derive_from_requirement
- requirement.get
- requirement.query
- traceability.query
- artifact.search
- workspace.get_context
```

### 5.3 risk-analyst

```yaml
tools:
- risk.read
- risk.create
- risk.update
- risk.delete
- architecture.get
- architecture.query
- requirement.get
- requirement.query
- traceability.query
- artifact.search
- workspace.get_context
```

### 5.4 change-manager

```yaml
tools:
- adr.read
- adr.create
- adr.update
- adr.delete
- issue.read
- issue.create
- issue.update
- issue.delete
- requirement.update
- architecture.update
- traceability.query
- traceability.suggest_links
- artifact.search
- workspace.get_context
```

### 5.5 quality-auditor

```yaml
tools:
- requirement.get
- requirement.query
- architecture.get
- architecture.query
- test.get
- test.query
- traceability.query
- artifact.search
- artifact.get_tree
- workspace.get_context
- glossary.read
- adr.read
- risk.read
- issue.read
```

Ausschließlich lesende Tool-Namen (`get`/`query`/`read`) — kein `create`/`update`/`delete`
in dieser Liste, auch nicht versehentlich über eine gemeinsame Sektion mit anderen Rollen.

## 6. Review-Policy-Hook (optionale Claude-Code-Referenz)

`hooks/review-policy-gate.sh` ist ein `PreToolUse`-Hook für Claude Code. Er:

1. Liest den aufgerufenen Tool-Namen aus dem Hook-Input (stdin, JSON).
2. Vergleicht ihn gegen eine im Skript fest hinterlegte Tabelle
   `Rolle → { review_changes: [...], review_high_risk: [...] }` (die Tool-Listen aus §5,
   minus der rein lesenden Tools).
3. Liest die aktive Rolle aus der Umgebungsvariable `REQFLOW_AGENT_ROLE` (vom Downstream-
   Projekt gesetzt, z. B. in `.claude/settings.json` → `env`).
4. Ist der Tool-Name für diese Rolle als `review_changes` oder `review_high_risk`
   eingestuft → Ausgabe `{"hookSpecificOutput": {"permissionDecision": "ask"}}`, sonst
   `{"hookSpecificOutput": {"permissionDecision": "allow"}}`.

**Grenzen (im Doku-File `review-policy-gate.md` explizit benannt):**

- Kein API-Call gegen ReqogniLooms `ReviewPolicy`-Endpoint — die Einstufung ist statisch
  im Skript hinterlegt, nicht die tatsächlich im Backend konfigurierte Policy. Ändert das
  Downstream-Projekt seine `ReviewPolicy` über die REST-API, muss die Hook-Tabelle manuell
  nachgezogen werden.
- Nur für Claude Code nutzbar. Andere Provider (Gemini, Opencode, Continue) haben keinen
  äquivalenten Hook-Mechanismus in diesem Repo — dort bleibt das Review-Profil eine reine
  Prompt-Anweisung an den Agenten.
- Fehlt `REQFLOW_AGENT_ROLE` in der Umgebung, gibt das Skript `allow` zurück (fail-open) —
  bewusste Entscheidung, damit ein fehlkonfiguriertes Downstream-Projekt nicht spontan
  alle Schreibzugriffe blockiert; das Doku-File weist explizit darauf hin, dass dies kein
  Sicherheitsmechanismus ist, sondern eine Erinnerungshilfe.

## 7. BOOTSTRAP.md — Einstiegs-Snippet

Ein kopierbarer Markdown-Block (keine eigene Datei-Struktur, reiner Text-Snippet) für die
CLAUDE.md/AGENTS.md/GEMINI.md eines Downstream-Projekts, mit:

- MCP-Endpunkt-Form: `{{REQFLOW_MCP_URL}}/mcp/sse/` (SSE), Auth über API-Key-Header
  (Platzhalter, kein echter Key im Snippet).
- Ein-Satz-Beschreibung jeder der 5 Rollen mit Verweis auf die jeweilige Datei unter
  `docs/agent-templates/<rolle>.md` (Pfad wird beim Kopieren auf den tatsächlichen
  Ablageort im Downstream-Projekt angepasst).
- Hinweis auf `compatible_with` im Frontmatter jeder Rollendatei und die Root-`VERSION`
  von ReqogniLoom, gegen die geprüft werden sollte.
- Hinweis, dass `REQFLOW_AGENT_ROLE` gesetzt werden muss, wenn der optionale
  Review-Policy-Hook (§6) verwendet wird.

## 8. Validierung / Testing

Da dies reine Markdown-/Shell-Artefakte ohne Anwendungslogik sind, gibt es keine
Unit-Tests im klassischen Sinn. Definition of Done für diese Phase:

- Jede der 5 Rollendateien enthält ein valides YAML-Frontmatter (`name`, `version`,
  `description`, `compatible_with`, `tools`) — geprüft durch manuelles YAML-Parsen
  (`python -c "import yaml; yaml.safe_load(...)"`) auf jede Datei.
- Jeder in einer `tools`-Liste genannte MCP-Tool-Name existiert tatsächlich in
  `backend/mcp_server/tools/` (Abgleich gegen die Tool-Registry) — kein erfundener
  Tool-Name.
- `hooks/review-policy-gate.sh` läuft fehlerfrei bei drei Testeingaben: (a) Tool aus der
  `review_high_risk`-Liste + passende Rolle gesetzt → `ask`; (b) Tool aus keiner Liste →
  `allow`; (c) `REQFLOW_AGENT_ROLE` nicht gesetzt → `allow`.
- `README.md` und `BOOTSTRAP.md` enthalten keine TODO/Platzhalter-Marker.

## 9. Offene Punkte für die Umsetzungsplanung

Keine — alle Abschnitte oben sind vollständig spezifiziert. Die Implementierungsplanung
(via `writing-plans`) zerlegt dies in Tasks pro Datei/Gruppe.
