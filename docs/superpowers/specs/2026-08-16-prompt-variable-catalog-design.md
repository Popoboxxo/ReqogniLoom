# Prompt-Variablen-Katalog & Content-getriebene Dekomposition — Design

**Status:** Draft, pending user review
**Scope:** Ein zusammenhängendes Feature in drei Phasen (siehe Abschnitt 7),
aus zwei verzahnten Beobachtungen entstanden:
1. Der Architektur-Dekompositions-Dialog (N1 `architecture.decompose`) lässt
   den User Breite/Tiefe der KI-Dekomposition als feste Zahlen vorgeben —
   fachlich falsch, das sollte die KI inhaltsbasiert entscheiden.
2. Das bestehende `PromptTemplate`-System hat kein Konzept von "Variablen" —
   Platzhalter sind reiner, unstrukturierter Freitext, nirgends dokumentiert,
   nirgends zentral verwaltbar, nicht MCP-überschreibbar.

## 1. Zweck

Zwei Ziele, die sich gegenseitig bedingen:

- **Fachlich richtige KI-Dekomposition:** Statt "erzeuge genau 3 Kind-Elemente
  in 2 Ebenen" bekommt die KI die Kriterien und entscheidet selbst, wie viele
  Kind-Elemente/Ebenen fachlich sinnvoll sind — mit einer Obergrenze als
  Sicherheitsnetz (Blast-Radius-Schutz, siehe `docs/UMSETZUNGSPLAN_SYSENG_2.0.md`
  §3.1). Diese Obergrenze ist selbst keine Magic Number mehr im Code, sondern
  eine zentral verwaltete, workspace-überschreibbare Variable.
- **Ein einheitlicher Prompt-Variablen-Katalog:** Alle ~19 Prompt-Templates
  (plus der bisher komplett außerhalb des Katalogs stehende
  Architektur-Dekompose-Prompt) bekommen eine gemeinsame, zentral verwaltete
  Variablen-Definition. Jede Variable ist über die UI sichtbar, dokumentiert,
  und — wo sinnvoll — ohne Code-Deploy erweiterbar und pro Workspace
  überschreibbar. Alle Prompts bleiben (wie heute) vollständig über die UI
  einsehbar und editierbar; das gilt nach diesem Feature auch für den
  Architektur-Dekompose-Prompt, der aktuell den Katalog umgeht.

**Nicht-Ziel:** Ein generisches "jeder kann beliebige neue KI-Fähigkeiten per
UI erfinden"-System. Variablen, deren Wert aus echten Artefaktdaten berechnet
wird (z. B. `{element_title}`), bleiben zwangsläufig code-gebunden — das
ändert keine Architektur der Welt, weil niemand außer Code diese Daten
beschaffen kann. Das Katalog-Feature macht nur die *Konfigurationsschicht*
(Zahlen-Obergrenzen, Schwellwerte, sonstige einfache Werte) datengetrieben.

## 2. Architektur-Überblick

Vier Bausteine:

1. **`PromptVariable`** — zentrale Variablen-Definition, tenant-scoped, mit
   `workspace_id`-Override-Mechanik (exakt das bestehende `PromptTemplate`-Muster
   wiederverwendet). Unterscheidet zwei `kind`s: `config` (rein datengetrieben,
   ohne Code beliebig erweiterbar) und `data` (code-gebunden, hier nur zur
   Katalog-Sichtbarkeit registriert).
2. **Gemeinsamer Resolver** — ersetzt die heute drei parallelen,
   unabhängig implementierten Fallback-Ketten (`AiDerivationService`,
   `mcp_server/tools/prompt_template.py`, `interview_protocol.py`) durch
   einen einzigen Resolution-Pfad, der zusätzlich `config`-Variablen
   automatisch aus dem Katalog auflöst und in jeden Render-Aufruf einspeist.
3. **Katalog-UI-Erweiterung** (`AiPromptsSection.tsx`) — pro Template eine
   Variablen-Tabelle (Name, Typ, Beschreibung, effektiver Wert, Herkunft-Badge,
   editierbares Override-Feld) plus eine neue, template-übergreifende
   "Variablen-Verwaltung"-Ansicht als zentrale Stelle für alle Variablen.
4. **Promptfoo-Testinfrastruktur** — Testfälle pro Template (Variablen-Werte +
   Assertions), generiert als vollständig gerenderte Prompt-Strings (kein
   Mustache-Templating von promptfoo nötig, siehe Abschnitt 6), in CI
   ausgeführt.

## 3. Datenmodell

### 3.1 `PromptVariable` — neues Modell, Muster von `PromptTemplate` übernommen

```python
class PromptVariable(TenantScopedModel):
    name = models.CharField(max_length=100)        # z.B. "max_breadth"
    kind = models.CharField(
        max_length=10, choices=[("config", "config"), ("data", "data")]
    )
    var_type = models.CharField(max_length=20)      # "int" | "str" | "bool" | "json"
    description = models.TextField()
    default_value = models.TextField()              # JSON-serialisiert
    # Exakt dasselbe Override-Muster wie PromptTemplate (models.py:1908-1958):
    workspace_id = models.UUIDField(null=True, blank=True)
    version = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            # genau eine aktive Zeile pro (tenant, workspace_id, name) —
            # Anwendungsebene-Constraint in save(), wie bei PromptTemplate
        ]
```

`workspace_id=None` → Tenant-weiter Default. `workspace_id=<id>` → Override
für genau diesen Workspace, gewinnt vor dem Tenant-weiten Eintrag. Rows sind
effectively immutable — neue Version = neue Zeile, alte wird deaktiviert
(kein Datenverlust, Audit-Trail bleibt erhalten).

**`kind="data"`-Zeilen sind nicht per UI neu anlegbar** (nur lesbar/dokumentierend)
— sie werden einmalig aus der bestehenden Code-Registry (`ai_derivation_service.py`s
11-Slot-Dict + `PROMPT_TEMPLATE_DEFAULTS`) seed-migriert und bei jedem neuen
`data`-Flow im Code mitgepflegt (ein PR, das eine neue `data`-Variable im Code
einführt, ergänzt auch die Katalog-Zeile — Review-Pflicht, kein Auto-Sync).

**`kind="config"`-Zeilen sind per Admin-UI voll CRUD-fähig**, ohne Code-Deploy.

### 3.2 Template → Variable Zuordnung — bleibt code-seitig, keine Junction-Tabelle

Welche Variablen ein Template *verwendet*, ist eine statische Tatsache des
Codes, der den Render-Aufruf macht (`_render(template, **kwargs)`) — für
`data`-Variablen ändert sich das nur mit einem Code-Change. Deshalb: die
bestehende Registry (`ai_derivation_service.py:80-270`, drei parallele Dicts)
wird zu **einer** kanonischen Registry konsolidiert, jeder Eintrag bekommt ein
neues Feld:

```python
PROMPT_SLOTS: Dict[str, PromptSlotSpec] = {
    "sysreq_decompose_next_level": PromptSlotSpec(
        default_content="...",
        data_variables=["req_title", "req_description"],  # code-gebunden
        # keine config_variables hier — dieser Flow braucht keine Zahl
    ),
    ...
}
```

`config`-Variablen werden **nicht** pro Template deklariert — sie werden bei
jedem Render-Aufruf automatisch für den aktuellen Tenant/Workspace komplett
aufgelöst und verfügbar gemacht (siehe 3.3). Ein Admin kann also eine neue
`config`-Variable anlegen und sie in *jedem* Prompt-Text per `{name}`
referenzieren, ohne dass ein Entwickler das Template vorher "freischalten"
muss — das ist der Kern von "einfach erweiterbar".

### 3.3 Gemeinsamer Resolver

Ersetzt `AiDerivationService._get_template_content` + `_render`, die
Kopie in `mcp_server/tools/prompt_template.py::_handle_get`, und den dritten
Lesepfad in `interview_protocol.py::get_protocol`:

```python
def resolve_and_render(
    slot_name: str,
    ctx: AuthContext,
    workspace_id: Optional[str],
    **data_kwargs: Any,      # code-gelieferte data-Variablen, wie heute
) -> str:
    content = _resolve_template_content(slot_name, ctx, workspace_id)   # unverändert: workspace > tenant > factory
    config_values = _resolve_all_config_variables(ctx, workspace_id)    # NEU: kompletter config-Variablen-Satz
    return _render(content, **{**config_values, **data_kwargs})         # data_kwargs gewinnt bei Namenskollision
```

Auflösungsreihenfolge pro `config`-Variable (spiegelt exakt die bereits
etablierte LLM-Provider-Config-Kette aus `llm_adapter/providers.py`):
**MCP-Call-Parameter (falls das aufrufende Tool ihn explizit überschreibt) >
Workspace-`PromptVariable`-Zeile > Tenant-`PromptVariable`-Zeile > `var_type`-Default.**

`_render` selbst bleibt unverändert (`str.replace`-Loop, bewusst kein
`.format()`/Jinja2 — vermeidet JSON-Brace-Konflikte, siehe bestehender
Kommentar in `ai_derivation_service.py:1521`).

## 4. Migration: Architektur-Dekompose in den Katalog

`architecture_decompose_service.py` bekommt keinen Sonderweg mehr:

- `ARCH_DECOMPOSE_PROMPT_TEMPLATE` wird eine reguläre `PromptTemplate`-Zeile
  (Slot-Name `architecture_decompose_tree`), über `AiPromptsSection.tsx` wie
  jeder andere Prompt einsehbar/editierbar.
- `breadth`/`depth` als feste Zahlen verschwinden aus Request-Serializer,
  MCP-Tool-Schema und Prompt-Text. Neue `config`-Variablen `max_breadth`
  (Default 5) und `max_depth` (Default 3) ersetzen `_MAX_BREADTH`/`_MAX_DEPTH`
  — dieselben Werte, jetzt katalog-verwaltet statt Modul-Konstante.
- Prompt-Text-Änderung (sinngemäß):
  > "Analysiere das Architektur-Element '{element_title}' und die davon
  > abhängigen Requirements. Zerlege es in fachlich sinnvolle Kind-Elemente
  > — bilde reale Kohäsion ab, keine künstliche Aufteilung. Nutze höchstens
  > {max_breadth} Kind-Elemente pro Ebene und höchstens {max_depth} Ebenen
  > insgesamt."
- `_complete_tree()` clamped weiterhin hart nach, falls die KI die Obergrenze
  ignoriert (bestehendes Verhalten bleibt als Sicherheitsnetz, jetzt gegen
  die aufgelösten `config`-Werte statt Modul-Konstanten).
- Frontend `ArchitectureDecomposePanel.tsx`: die beiden Zahlenfelder bleiben
  bestehen, werden aber umbeschriftet ("Max. Kinder je Ebene" /
  "Max. Ebenen") mit Hilfetext, dass die KI die tatsächliche Struktur
  inhaltlich entscheidet — die Zahlen sind Obergrenze, nicht Zielvorgabe.
  Defaults kommen jetzt aus dem Katalog statt hartcodiert `useState(2)`/`useState(1)`.

`derive_requirements_from_need(n=3)` bekommt dieselbe Behandlung: `n` wird
`config`-Variable `max_requirements_per_need` (Default 3), Prompt-Text
entsprechend auf "höchstens {max_requirements_per_need}" umformuliert statt
"genau {n}".

## 5. Katalog-UI

`AiPromptsSection.tsx` (heute: ein Editor pro Slot, Scope-Switch
Workspace/Global) bekommt zwei Erweiterungen:

- **Pro-Slot-Variablen-Panel:** unter jedem Prompt-Text-Editor eine Tabelle
  der in diesem Slot referenzierten Variablen (`data`, read-only, zur
  Dokumentation — UND alle aktuell im Text vorkommenden `config`-Variablen,
  automatisch erkannt durch Parsen der `{...}`-Platzhalter gegen die
  Katalog-Namen). Spalten: Name, Kind-Badge, Typ, Beschreibung, effektiver
  Wert, Herkunft-Badge (wie der bestehende Origin-Badge-Pattern:
  "workspace override" / "tenant default" / "factory").
- **Neue "Variablen-Verwaltung"-Ansicht** (eigener Tab/Abschnitt, nicht pro
  Template verschachtelt): Liste **aller** `PromptVariable`-Einträge über
  alle Templates hinweg, mit Anlegen/Bearbeiten/Deaktivieren für
  `kind="config"`. `kind="data"`-Zeilen erscheinen nur lesend, mit Hinweis
  "code-gebunden, Wert wird vom System berechnet".
- **Validierung beim Speichern eines Prompt-Texts:** unbekannte
  `{...}`-Platzhalter (weder als `data_variables` im Slot deklariert noch als
  `config`-Variable im Katalog vorhanden) werden als Warnung markiert, bevor
  gespeichert wird — verhindert die heute unsichtbare Klasse von Tippfehlern.

## 6. Promptfoo-Testinfrastruktur

**Kernentscheidung:** promptfoo bekommt **keine** rohen `{var}`-Templates zum
selbst-Rendern übergeben — Syntax-Konflikt mit promptfoo's eigenem
`{{mustache}}`-Format, und ReqogniLooms `_render` ist bewusst kein
generischer Templating-Engine (JSON-Brace-Sicherheit). Stattdessen: der
Resolver aus Abschnitt 3.3 rendert den **fertigen** Prompt-String für eine
gegebene Variablen-Kombination, und dieser fertige String wird promptfoo als
literaler `prompt` übergeben — promptfoo sieht nie einen Platzhalter.

**Testfall-Definition** (git-versioniert, nicht in der DB — Testfälle sind
Code/Fixtures, keine Tenant-Daten):
`backend/application/prompt_testing/cases/<slot_name>.yaml`:

```yaml
scenarios:
  - name: "Architektur-Element mit vielen abhängigen Requirements"
    variables:
      element_title: "Zahlungsabwicklung"
      max_breadth: 5
      max_depth: 2
    assertions:
      - type: is-json
      - type: javascript
        value: "output.length <= 5"   # respektiert max_breadth
      - type: llm-rubric
        value: "Jedes Kind-Element hat einen fachlich sinnvollen, nicht-redundanten Titel"
```

**Export-Schritt** (`backend/manage.py export_promptfoo_configs`): liest
`PromptTemplate` + `PromptVariable`-Defaults + die YAML-Szenarien, rendert
pro Szenario den fertigen Prompt via Resolver, schreibt
`promptfoo/generated/<slot_name>.promptfooconfig.yaml` mit Provider-Config
(gegen die bestehende Multi-Provider-Abstraktion — `mock` für schnelle
CI-Läufe, optional `anthropic`/`openai` für tiefere, seltener laufende Checks).
`promptfoo/generated/` ist reines CI-Build-Artefakt (gitignored, bei jedem
Lauf neu erzeugt); `prompt_testing/cases/*.yaml` ist die eingecheckte Quelle
der Wahrheit für Testfälle.

**CI-Integration:** neuer Job (Muster wie "Agent Templates & Distribution"),
läuft bei Änderungen an `PromptTemplate`-Migrationsdaten oder
`prompt_testing/cases/*.yaml`, führt `npx promptfoo eval -c promptfoo/generated/*.yaml --fail-on-error`
aus. Regressions-Schutz: ein Prompt-Textänderung, die eine Assertion bricht,
wird vor dem Merge sichtbar — dieselbe Philosophie wie der bestehende
`ui-ratchet`/`dist`-Drift-Check.

## 7. Rollout-Phasen

Drei unabhängig abnehmbare Phasen (für die anschließende Implementierungsplanung):

1. **Datenmodell + Resolver + Migration bestehender Templates.** `PromptVariable`-Modell,
   konsolidierte Registry, gemeinsamer Resolver ersetzt die drei parallelen
   Fallback-Ketten, Regressions-Snapshot-Test: alle ~19 Bestandstemplates
   rendern nach der Migration identisch wie vorher.
2. **Architektur-Dekompose-Migration + Katalog-UI.** Abschnitt 4 (Breite/Tiefe
   → `max_breadth`/`max_depth`) und Abschnitt 5 (Variablen-Panel +
   Variablen-Verwaltung-Ansicht).
3. **Promptfoo-Testinfrastruktur.** Abschnitt 6, inkl. CI-Job. Kann unabhängig
   von Phase 2 starten, sobald Phase 1 steht (braucht nur den Resolver).

## 8. Testing (querschnittlich)

- Resolver-Auflösungskette: Unit-Tests für alle vier Prioritätsstufen
  (MCP-Param > Workspace > Tenant > Default), inkl. Negativfall (Variable
  existiert nicht → klarer Fehler statt stiller Leerstring).
- Regressions-Snapshot: alle Bestandstemplates rendern nach Migration
  byte-identisch (analog zum `dist/test_full_regeneration.py`-Muster dieser
  Session).
- Auto-Injection: ein Test legt eine neue `config`-Variable rein datengetrieben
  an, referenziert sie in einem Test-Slot, und prüft dass sie ohne
  Code-Änderung im gerenderten Output erscheint.
- Frontend: Variablen-Panel (Anzeige, Origin-Badges), Variablen-Verwaltung
  (CRUD für `config`, Read-only-Darstellung für `data`), Validierungs-Warnung
  bei unbekanntem Platzhalter.
- Promptfoo-Suite läuft gegen `mock`-Provider in CI (schnell, deterministisch);
  echte Provider optional, nicht blockierend.
- KEINE E2E-Pflicht für dieses Feature laut Projekt-Konvention (Testumfang-Regel
  in `CLAUDE.md`) — gezielte Unit-/Integrationstests reichen, E2E deckt es
  später über die reguläre Suite ab.
