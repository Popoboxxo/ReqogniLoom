---
type: EVIDENCE
scope: wp4-bootstrap-fieldkind-proof
status: success
date: 2026-09-29
author_agent: data-engineer
---

# WP-4 Evidenz 4 — Beweis: `--reset` / `field_kind`-Prämisse (Issue #1112)

## 0. Vorbemerkung zur Bezeichnung

Die Auftragsformulierung und der Issue-Titel sprechen von **`field_kind`**.
Diese Zeichenkette existiert **nirgends** im Repository:

```
$ rg -o "field_kind" backend --glob "*.py"   ->  0 Treffer
$ SELECT column_name FROM information_schema.columns
    WHERE column_name LIKE '%kind%'          ->  pl_actor.kind, as_notification.kind,
                                                pl_prompt_variable.kind, pl_testcase.scenario_kind,
                                                pl_interview_session.session_kind, … (kein field_kind)
```

Das gemeinte Feld ist die **`kind`-Property eines Attribut-Eintrags** im
`definition_json`-Blob (`ad_global_definition.definition_json` /
`ad_workspace_definition.definition_json`). Live-Beleg:

```sql
SELECT elem->>'kind' AS kind, count(*)
  FROM ad_global_definition d,
       jsonb_array_elements((d.definition_json::jsonb)->'attributes') elem
 GROUP BY 1;
-- core      | 1488
-- extended |  660
```

Valide Werte laut Schema: `backend/attribute_definitions/schema.py:15`
`ATTRIBUTE_KINDS = frozenset({"core", "extended"})`, erzwungen in `:492-493`
(„`'kind'` must be one of ['core', 'extended']"). `ADR-006` (PR #1111) ist die
Einführung dieser Property.

Im Folgenden wird „`field_kind`" als die `kind`-Property geführt.

## 1. Die Behauptung

> **„`bootstrap_attribute_definitions` ändert ohne `--reset` das `field_kind` einer
> bestehenden Definition nicht."**

**Antwort: BESTÄTIGT.** Der Codepfad ist vollständig und in drei Schritten belegbar.

## 2. Der Codepfad

### Schritt 1 — die Dispatch-Schleife

`backend/attribute_definitions/management/commands/bootstrap_attribute_definitions.py:1063-1106`

```python
with transaction.atomic():                                            # :1063
    for tenant_id in tenant_ids:
        set_request_tenant(tenant_id)
        try:
            for item_type in BOOTSTRAP_ITEM_TYPES:                    # :1067
                for preset in PRESETS:                                 # :1068
                    attributes = introspect_core_attributes(item_type, preset)   # :1069
                    sections   = materialize_sections(attributes)                # :1074
                    existing   = store.get(tenant_id, item_type, preset)         # :1075
                    if existing is None:
                        store.initialize(...)                        # :1077-1079  NEU
                        created += 1
                    elif options["reset"]:                            # :1081
                        row, _propagated = store.reinitialize(...)    # :1086-1088  RESET
                        reset += 1
                    else:                                            # :1092  <<< OHNE RESET
                        if options["relabel"] and self._relabel(...): # :1097-1099
                            relabelled += 1
                        if options["sync_new_fields"] and \
                           self._append_missing(...):                 # :1101-1102
                            updated += 1
        finally:
            clear_request_tenant()
```

Der `else`-Zweig (`:1092`) ist der **einzige** Pfad ohne `--reset`, und er ruft
**genau zwei** Methoden auf: `_relabel` und `_append_missing`. Beide sind additiv bzw.
whitelist-beschränkt.

### Schritt 2 — `_relabel` ist auf zwei Keys whitelisted

`bootstrap_attribute_definitions.py:309`

```python
#: ``--reset`` (the previous, only remedy) achieves that by DISCARDING every
#: admin customization of the global rows. …
RELABEL_KEYS: tuple[str, ...] = ("label", "help_text")
```

Docstring `_relabel` (`:1138`, `:1150-1152`):

> „**Labels only.** See `RELABEL_KEYS`. Every other attribute property, the attribute
> list itself (admin-added attributes stay) and the `sections` list are carried over
> from the stored row untouched."

`kind` ist **nicht** in `RELABEL_KEYS` → wird von `--relabel` per Konstruktion nicht
angefasst. Das ist eine **positive** Eigenschaft: der Pfad kann die Property nicht
versehentlich überschreiben.

### Schritt 3 — `_append_missing` unterscheidet nicht nach Property

`bootstrap_attribute_definitions.py:1247-1252`

```python
stored    = stored_attributes(row.definition_json)             # :1247
known     = {a["name"] for a in stored}                        # :1248
additions = [copy.deepcopy(a) for a in introspected
             if a["name"] not in known]                        # :1249
if not additions:
    return False                                                # :1250-1251  FRÜHER EXIT
stored.extend(additions)                                       # :1252
```

Der Diff ist **ausschließlich namenbasiert** (`a["name"] not in known`). Ein Attribut,
das in der Introspection existiert und in der DB existiert, wird **nicht** in
`additions` aufgenommen — unabhängig davon, ob sich sein `kind`, sein `type`, seine
`section`, sein `required` oder irgendeine andere Property geändert hat.

**Drei voneinander unabhängige Sperren**, alle drei je für sich ausreichend:

| # | Sperre | Ort |
|---|---|---|
| 1 | `kind` ∉ `RELABEL_KEYS` | `:309` |
| 2 | Diff-Key ist `name`, nicht `kind` | `:1248-1249` |
| 3 | `if not additions: return False` — bei **identischem** Attributsatz wird **gar nichts** geschrieben, kein `save()`, kein `version`-Bump, keine Propagation | `:1250-1251` |

→ **Kein Pfad ohne `--reset` kann eine bestehende `kind`-Property ändern.**

### Schritt 4 — was der einzige schreibende Pfad kostet

`store.reinitialize(...)` (`:1086-1088`) ist der einzige Weg, der `kind` aktualisiert.
`:1082-1085` beschreibt den Preis selbst:

> „Ledger item (f): the recovery path out of a bad initial payload.
> `store.update()` cannot do this — its core/locked rules (correctly) make a bad seed
> permanent, so the escape hatch has to bypass them."

`:1144-1146` nennt ihn explizit: *„`--reset` also fixes the data but **documentedly
DESTROYS every admin customization of the global rows**, so it is the wrong tool for a
label repair."*

→ **AUD-2026-09-176**: BESTÄTIGT #1112. Reconciliation: **BESTAETIGT** — das offene Issue
#1112 deckt den Befund exakt ab. **Kein NEU-Finding**, sondern eine Präzisierung:
`field_kind` heißt im Code `kind`; und die Sperre ist **dreifach**, nicht einfach, was die
Umsetzung billiger macht als im Issue-Body angenommen.

## 3. Gefragte Nebenbedingungen

| Prüfpunkt | Ergebnis | Beleg |
|---|---|---|
| **Idempotenz** | **JA**, für alle drei Modi | `_relabel:1153-1156` („A row whose labels already match … is not written at all — no version bump, no propagation, no cache invalidation"); `_append_missing:1250-1251` (Frühexit); `reinitialize` ist eine Ersetzung per `(item_type, preset)`-Schlüssel (Unique-Constraint live verifiziert) |
| **Transaktionsgrenze** | **JA**, eine äußere für alles | `:1063` `with transaction.atomic():` umschließt die Tenant- × ItemType- × Preset-Doppelschleife. `_append_missing:1282` `store._propagate(row)` (Bulk-`update()`) liegt **innerhalb** — ein Propagationsfehler rollt die globale Zeile mit zurück. |
| **Verhalten bei Teilfehlern** | **Kein Halbschreiben** | Alles oder nichts. Ein Fehler in der letzten Kombination rollt die erste zurück. |
| **Expliziter Rollback-Pfad** | **NEIN** | Es gibt **kein** `--dry-run` und **keinen** Snapshot/Undo-Mechanismus. Der einzige „Rollback" ist der implizite der Transaktion. Für `--reset` heißt das: die vorherige `definition_json` ist nach dem Commit **nicht rekonstruierbar** — weder aus dem Code noch aus einer Tabelle. |
| **Cache-Invalidierung** | **JA**, in allen drei Modi | `:1089-1090` (reset), `:1283-1284` (append), `_relabel` laut `:1161-1163` über `store._propagate()` + Invalidierung. |
| **`--relabel` + `--reset`** | **abgelehnt** | `:1037-1043` — bewusst, „silently picking one would be a trap" |

→ **AUD-2026-09-179** (Medium): fehlender Dry-Run-/Undo-Pfad bei einem destruktiven
Befehl, dessen Zweck es ist, gezielt Admin-Arbeit zu zerstören.

## 4. Zwei Nebenbefunde aus demselben Modul

### 4.1 `ATTRIBUTE_KINDS` (2 Werte) vs. `stage_matrix`-Docstring (5 Carrier)

`attribute_definitions/schema.py:15` — `ATTRIBUTE_KINDS = {"core", "extended"}`,
erzwungen `:492-493`.

`attribute_definitions/stage_matrix.py:48-53` — *„Carrier rule (spec section 2 / ADR-004):
Only attributes whose carrier is `core`/`ext`/`system` are seeded here. `link` rows
(`allocated-to`, `derives-from`, `verifies`, `affects` …) … `entity` rows (`Measure`,
#393) have no table yet."*

Der Docstring beschreibt **fünf** Carrier-Namen (`core`/`ext`/`system`/`link`/`entity`),
von denen das Schema **zwei** kennt, und die anders benannt sind: `ext` vs. `extended`.
Nur `core` ist ein gültiger Wert; `link` und `entity` sind als `kind`-Werte **nicht
zulässig** (Schema-Anspruch), werden aber im Docstring als existierende Kategorien
geführt. Live bestätigt: 0 Attribute mit `kind` ∈ {`link`,`entity`,`system`,`ext`}.

→ **AUD-2026-09-177** (Medium): Schema und Doku beschreiben zwei verschiedene
Klassifikationen. Entweder ist der Docstring aus einer Spec-Fassung vor der
Schema-Verengung, oder das Schema hat eine Kategorie stillschweigend verloren.

### 4.2 Nur 8 von 11 Item-Types materialisieren je in Workspaces; 134/401 Workspaces ganz ohne

```sql
-- global: 11 item_types
SELECT string_agg(DISTINCT item_type, ',' ORDER BY item_type) FROM ad_global_definition;
-- Adr,ArchitectureElement,ChangeRequest,GlossaryTerm,Goal,Icd,Issue,Requirement,
-- Risk,StakeholderNeed,TestCase

-- workspace: nur 8
SELECT string_agg(DISTINCT item_type, ',' ORDER BY item_type) FROM ad_workspace_definition;
-- Adr,ArchitectureElement,GlossaryTerm,Issue,Requirement,Risk,StakeholderNeed,TestCase

SELECT count(*) FROM pl_workspace pw WHERE NOT EXISTS (
  SELECT 1 FROM ad_workspace_definition d WHERE d.workspace_id = pw.id);   -- 134
```

`ChangeRequest`, `Goal` und `Icd` haben eine globale Default-Definition, aber **nie**
eine Workspace-materialisierte. `Diagram` und `Interview` haben **überhaupt keine**
Definition (obwohl `pl_artifact` 111 `Diagram`- und 9 `Interview`-Artefakte führt).
134 der 401 Workspaces (33 %) haben **keinerlei** Attribut-Definition.

Ob das Fehlen bewusst ist (Workspaces ohne Bootstrap) oder ein Provisioning-Gap,
lässt sich read-only nicht entscheiden — die 134 Workspaces sind E2E-Reste (Namensmuster
`e2e-isolated-*`). Als *Datenqualitäts*-Aussage bleibt: das Attribut-System ist für
diese Workspaces **nicht wirksam**.

**Wichtige Abgrenzung:** Der Link-Typ-Katalog ist **nicht** betroffen — dort hat
**jeder** der 401 Workspaces eine Definition:

```sql
SELECT count(*) FROM pl_workspace pw WHERE NOT EXISTS (
  SELECT 1 FROM lt_workspace_definition d WHERE d.workspace_id = pw.id);   -- 0
```

Die 134 Workspaces ohne Attribut-Definition sind also **keine** Workspaces ohne
Provisioning — sie haben den Link-Typ-Katalog, aber keinen Attribut-Katalog. Das ist
ein **spezifischer** Provisioning-Gap im Attribut-Pfad, kein generelles Problem.

→ **AUD-2026-09-178** (Medium), Klassifikation **NEU** mit **BLOCKED**-Anteil
(Ursache nicht read-only entscheidbar).

## 5. Reconciliation

| AUD | Klassifikation | Begründung |
|---|---|---|
| 176 | **BESTAETIGT #1112** | Der Issue-Body benennt `bootstrap_attribute_definitions`, `--relabel`, `--sync-new-fields`/`_append_missing()` — exakt der gefundene Pfad. Präzisierung: Feld heißt `kind`; Sperre ist dreifach. |
| 177 | **NEU** | Kein Issue-Bezug; #1112 betrifft nur den Upgrade-Pfad, nicht die `ATTRIBUTE_KINDS`-/`stage_matrix`-Divergenz. |
| 178 | **NEU (mit BLOCKED-Anteil)** | Kein CR-Track. |
| 179 | **NEU** | Kein CR-Track. `CR-10` betrifft `provision_workflow_definitions` (Workflow, nicht Attribute). |
