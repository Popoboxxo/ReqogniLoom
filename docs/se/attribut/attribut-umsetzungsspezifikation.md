# Attribut-System v3 — Umsetzungsspezifikation

**Status:** Draft (zur Freigabe) · 12.09.2026
**Basis:** `main` `9224440b` (v1.8.0-beta.10+)
**Bezug:** #929 (3-Stufen-Modell), #930 (AWMS), #932 (ID), #871/#408/#583/#393/#912/#920
**Vollständige Attribut-Matrix:** `attribut-matrix-3-stufen.md` (Teil dieser Spec)

---

## 1. Ziel und Geltungsbereich

Das Attribut-System besteht aus drei Schichten:

1. **Definition** (Attribut-Definition v2) — funktioniert (Auflösung `(tenant, item_type, preset)`, `core`/`extended`, Validierung, Admin-Gating).
2. **Transport** (REST + MCP) — **divergent und teils gebrochen** (der eigentliche Defekt).
3. **Identität und Werte-Migration** — `uid` tot, Wertebewegung fehlt (AWMS).

Diese Spec definiert die Vereinheitlichung aller drei Schichten und das dauerhafte Versprechen:

> **Attribute Usability Contract (AUC):** Für jedes `(workspace, item_type ∈ 11, preset ∈ 3)` und jedes sichtbare Attribut der aufgelösten Definition gilt:
> **W** (schreibbar), **R** (lesbar), **V** (identisch validiert) und **Round-Trip** — auf **beiden** Transporten, **immer**.
> Kein Silent-Drop. Discovery der Definition für jeden Item-Typ.

Durchgesetzt wird das nicht durch Zusicherung, sondern durch eine **Contract-Matrix** (Abschnitt 11).

---

## 2. Träger-Modell (Abstraktionsebenen)

| Träger | Speicher | Wofür |
|---|---|---|
| **core** | echte Spalte (Spezialtabelle **oder** generische `Artifact`) | sortier-/filter-/join-relevant, API-/MCP-erstklassig |
| **extended** | `Artifact.custom_fields` (JSONB) | konfigurierbar je Tenant/Preset, ohne Migration |
| **system** | core, aber `editable="system"`, `locked` | ID, Status; nicht schreibbar |
| **link** | `TraceLink` | semantische Ketten (derives-from, allocated-to, verifies) |
| **widget** | core/extended + Widget-Komponente | strukturierte Werte (steps, risk_matrix, ICD-Payload) |
| **entity** | eigene Tabelle | `Measure` (Zeitreihe), `Actor` (Personen) |

**Entscheidungsregel** (aus #929 C3): Modellfeld nur, wenn mindestens eines zutrifft — (a) sortier-/filterbar nötig, (b) im API/MCP-Schema erstklassig nötig, (c) FK-Integrität nötig, (d) auf jedem Artefakt des Typs normativ. Sonst extended.

**Festgelegt:**

| Attribut | Träger |
|---|---|
| `id`, `owner`, `reporter`, `priority` | **core auf `Artifact`** (alle 11 Typen, eine Migration) |
| `status` | system (workflow) — existiert |
| `rationale`, `source` | extended |
| `moscow_priority` | extended **nur StakeholderNeed** (Legacy-Spalte wird per AWMS gefaltet) |
| alle übrigen in `attribut-matrix-3-stufen.md` genannten | teils core, teils extended (dort je Zeile) |

---

## 3. Systemfelder auf `Artifact`

Weil alle Typen an `pl_artifact` hängen, liegen die querschnittlichen Systemfelder dort:

```python
# persistence.Artifact (models.py:784)
owner    = models.ForeignKey("persistence.Actor", null=True, blank=True,
                             on_delete=models.SET_NULL, related_name="+")
reporter = models.ForeignKey("persistence.Actor", null=True, blank=True,
                             on_delete=models.SET_NULL, related_name="+")
# Bewusst OHNE feste model-`choices`: die Skala ist je (item_type, preset)
# über die Attribut-Definition konfigurierbar (type=enum, options).
priority = models.CharField(max_length=64, blank=True, default="", db_index=True)
```

- `id` (UUID-PK) ist die **einzige** Identität. Es gibt **keinen** neuen `REQ-NNN`-Generator.
- `uid` (CharField auf 8 Spezialmodellen) wird als **externer Import-Schlüssel** (ReqIF) beibehalten, `help_text` an die Realität angepasst; keine Auto-Generierung. Optional später per AWMS in `custom_fields.uid` überführen.
- `priority`-Skala: **Default** `low | medium | high | critical`, aber **anpassbar** je Attribut-Definition (Enum-`options`). MoSCoW nur am Need. Validierung gegen die Definitions-`options`, nicht gegen DB-`choices`.
- Der Bootstrap (`bootstrap_attribute_definitions.py`) muss die `Artifact`-Felder je Item-Typ als **core**-Attribute entdecken (Erweiterung von `introspect_core_attributes` um eine `ARTIFACT_LEVEL_CORE_ATTRIBUTES`-Quelle).

**Sichtbarkeit als Attribut:** `id`, `owner`, `reporter`, `priority` sind core-Attribute und können wie jedes andere per Definition `visible`/`audience`/Layout gesteuert werden („aufblendbar").

---

## 4. Personen-/Team-Sonderfunktion: `Actor`

Neue Entität, die interne User **und** Dummies (Menschen außerhalb des Systems) trägt:

```python
class Actor(TenantScopedModel):
    kind         = models.CharField(max_length=16, choices=[("user","User"),("external","External")])
    user         = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                     on_delete=models.SET_NULL, related_name="+")
    display_name = models.CharField(max_length=255)
    email        = models.EmailField(blank=True)
    organization = models.CharField(max_length=255, blank=True)
    notes        = models.TextField(blank=True)
    is_active    = models.BooleanField(default=True)
```

- `kind="user"`: verweist auf `persistence.User` (Login-fähig).
- `kind="external"`: Dummy/Platzhalter, kein Login.
- Unique: `(tenant, user)` bei `user`, `(tenant, lower(display_name))` bei `external`.

**Kombi-Feld (ein Feld, zwei Quellen):** Der Attribut-Typ `actor` rendert eine Combobox. Eingabe sucht interne User; kein Treffer → „als externe Person anlegen". Gespeichert wird die `Actor`-ID.

REST/MCP-Wertform:

```json
"owner":   {"kind": "user",     "id": "<user-or-actor-uuid>"}
"owner":   {"kind": "external", "name": "Frau Müller (TÜV)"}
"deciders":{"multiple": true, "items": [ {"kind":"user","id":...}, {"kind":"external","name":...} ]}
```

**Neuer Attribut-Typ `actor`** (in `ATTRIBUTE_TYPES`), Konfiguration je Attribut:

| Property | Werte | Wirkung |
|---|---|---|
| `multiple` | bool | Einzelperson (false) oder Team (true) |
| `allow_external` | bool | Dürfen Dummies/Externe eingetragen werden? `false` = nur interne User |

- Systemfelder `owner`/`reporter`: `type=actor`, `multiple=false`, `allow_external=false` (Default; je Attribut umstellbar).
- Der bisherige Typ `user` bleibt für Alt-Definitionen lesbar; Neu-Definitionen nutzen `actor`.
- Validierung: `field_validation._check_type` bekommt `actor` (Struktur + `allow_external`/`multiple`); FK-Existenz prüft die Service-Schicht (DB-freier Validator bleibt DB-frei).
- Frontend: `ActorPicker` (ersetzt/erweitert `UserPicker`), Einzel- und Mehrfachvariante.

---

## 5. Generische Display- und Interaktions-Properties

Neue, generische Attribut-Properties (gelten für **jedes** Attribut, nicht nur die ID):

| Property | Werte | Wirkung |
|---|---|---|
| `copyable` | bool | Doppelklick/Button kopiert den Wert |
| `reveal` | `always \| click \| shortcut` | dauerhaft sichtbar / per Klick / per Tastenkürzel einblenden |
| `visible` | bool (vorhanden) | „per Default nicht anzeigen" |
| `mask` | `none \| short` | Label kurz (z.B. UUID 8 Zeichen), kopiert voll (`copyValue`) |
| `display_format` | `text \| mono \| chips` | rein visuell |

- ID-Systemfeld: `visible=false`, `reveal="click"`, `copyable=true`, `mask="short"`.
- Baustein existiert: `frontend/src/components/shared/ArtifactId.tsx` (Kopieren + `copyValue` + `readOnly`). Wird zu einem generischen `<RevealValue>`-Wrapper verallgemeinert, doppelt genutzt von allen Feldkomponenten.

---

## 6. Edit-Policy und Automatisierung

`editable` wird zur Policy erweitert (bestehende Werte bleiben gültig):

```
editable: true | false | "workflow" | "system" | "automation"
source:   "user" | "import" | "computed" | "derived"
computed: { expression? | template?, depends_on: [attr...] }
read_only_reason: <i18n-key>
```

- `system` → ID, Status; nie schreibbar, aber anzeig-/kopierbar.
- `automation` → heute nur vorbereitet (Schema + UI-Lock); Ausführung später über AWMS `derive_value` (#930).
- Durchsetzung serverseitig zentral in `attribute_definitions/field_validation.py` (gilt damit automatisch für REST **und** MCP).

---

## 7. Layout-Engine

Heute: 2-Spalten-Grid, nur Sections `full`/`half` (`ArtifactForm.module.css:14-31`). Neu: **12-Spalten-Grid mit Flow-Tokens** auf Section- und Attribut-Ebene.

```yaml
layout:
  section_flow:
    - {kind: section, name: identification}
    - {kind: spacer, size: md}          # Section-Dummy
    - {kind: section, name: content}
  # je Section:
  attribute_flow:
    - {kind: attribute, name: title, span: half}
    - {kind: attribute, name: uid,   span: quarter}
    - {kind: spacer, size: sm}          # Attribut-Dummy
    - {kind: attribute, name: description, span: full}
```

| Token | Werte |
|---|---|
| `span` | `full`=12, `half`=6, `quarter`=3 Spalten |
| `spacer.size` | `sm`=1, `md`=2, `lg`=4 Spalten (relative Größen) |

- Fehlt ein Flow, wird er aus der Reihenfolge abgeleitet → **keine Migration**, Altverhalten identisch.
- Responsive: unter Breakpoint kollabiert das Grid auf 1–2 Spalten; Spacer entfallen.
- Additive Schema-Erweiterung in `attribute_definitions/schema.py` (`SECTION_LAYOUTS` bleibt für Section-Breite; Flow ist neu).

---

## 8. Zentraler Attribut-Katalog

Neue, item-typ-**unabhängige** Vorlagen-Bibliothek je Tenant:

```python
class AttributeCatalogEntry(TenantScopedModel):
    name        = models.CharField(max_length=64)     # unique je tenant
    definition  = models.JSONField()                  # ein normalisierter extended-Attribut-Block
    category    = models.CharField(max_length=64, blank=True)
    tags        = models.JSONField(default=list, blank=True)
    label       = models.JSONField(default=dict)      # {de,en}
    help_text   = models.JSONField(default=dict)
    origin      = models.CharField(max_length=64, blank=True)
    deprecated  = models.BooleanField(default=False)
```

- Operationen: `list/search`, `create`, `update`, `deprecate`, `add_to_definition(item_type, preset|workspace)`.
- `add_to_definition` kopiert den normalisierten Block und löst Namenskollisionen über die vorhandene `_merge_import`-Logik (`attribute_definition_service.py:855`).
- Katalog ist **Vorlage**, keine harte Bindung; Änderungen wirken nicht rückwirkend, „Re-Apply" ist explizit.
- REST: `/api/v1/attribute-catalog/…`; MCP: Gruppe `attribute_catalog.*`; UI: „Aus Katalog hinzufügen" in `AttributeEditorPage`.
- Export/Import (vorhanden, `export_definition`/`import_definition` mit `on_collision`) wird um Katalog-Dokumente erweitert.

---

## 9. Transport-Parität REST/MCP (die zu schließenden Lücken)

**REST:**
- `custom_fields` fehlt in Serializer **und** View bei `Goal`, `ChangeRequest`, `GlossaryTerm` (teils Silent-Success); `Icd` ohne Attribut-Anbindung; `ChangeRequest`-Create validiert die Definition nicht; Discovery (`attribute-schema`) nur für `Requirement`.

**MCP:**
- `Requirement`/`Needs`/`Test`/`Architecture`: Handler verwerfen `custom_fields`, Schema `additionalProperties:false`.
- `Adr`/`Risk`/`Issue`: schreibbar, aber nicht lesbar (`generic._to_dict` liest Modell-`__dict__` statt `artifact.custom_fields`).
- `GlossaryTerm`/`ChangeRequest`/`Goal`: Service kennt `custom_fields` nicht; `Icd` ohne Tools; `artifact.search`/`get_tree` liefern keine Attribute; `attribute_definition.update` ohne `sections`.

**Fix:** ein gemeinsamer `ArtifactAttributeGateway` (REST-View und MCP-Handler nutzen ihn), damit keine per-Typ-Verdrahtung mehr abweichen kann.

---

## 10. Werte-Migration (AWMS, #930)

Unverändert wie in `attribut-migrationssystematik.md` spezifiziert (deklarativer Plan, `dry_run`-Default, Transform-Registry, Snapshot/Rollback, `attribute_migration_run`, CLI/REST/MCP). Erste Pläne: `uid`→externer Schlüssel, `moscow_priority`→extended, `rationale` aus `description` rekonstruieren, `priority`-Backfill, Legacy-Owner (`Risk.owner`, `created_by_name`)→`Actor`, Goal-Messgrößen→`Measure`.

---

## 11. Contract-Matrix

Automatisierte Prüf-Matrix: für **jede** `(item_type, preset)` × Transport (REST, MCP) × Attribut wird **W/R/V/Round-Trip** durchgeführt. CI-blockierend.

- Start: **rot** (dokumentiert alle heutigen Lücken aus Abschnitt 9), Ziel: grün.
- Jedes neue Attribut und jeder neue Item-Typ muss die Matrix bestehen.
- Verortung: `backend/attribute_definitions/tests/test_transport_contract_matrix.py` (parametrisiert über `ITEM_TYPES` × `PRESETS`).

Das ist das technische „JEDERZEIT alle Attribute via MCP & REST nutzbar".

---

## 12. Vorbedingung #912

`mandatory_fields` liegt in `presets/registry.py` **pro Preset, nicht pro Item-Typ** und nennt Feldnamen, die für 10/11 Typen sinnlos sind. Wird ersetzt durch `required` je Attribut in der **Definition** (pro `(item_type, preset)`). Danach ist der Träger des Stufenmodells korrekt.

---

## 13. Phasenplan

| WS | Inhalt | Hängt an | Aufwand |
|---|---|---|---|
| **WS0** Fundament | Contract-Matrix (rot), gemeinsamer Gateway, ADR, #912 | – | 1–1,5 Wo |
| **WS1** Parität | REST+MCP `custom_fields` für alle 11, Icd, Discovery | WS0 | 2–3 Wo |
| **WS2** Identität & Systemfelder | `Artifact.owner/reporter/priority`, `Actor` + Kombi-Feld, ID-Systemfeld, `uid`→Import-Schlüssel | WS0 | 2,5–3,5 Wo |
| **WS3** Display-Engine | `copyable`/`reveal`/`mask`/`display_format`, `ArtifactId`-Doppelklick | WS0 | 1–1,5 Wo |
| **WS4** Layout-Engine | 12 Spalten, quarter, Section- + Attribut-Dummies sm/md/lg | WS0 | 1,5–2 Wo |
| **WS5** Zentraler Katalog | `AttributeCatalogEntry` + REST/MCP/UI | WS1 | 2–3 Wo |
| **WS6** 3-Stufen-Modell | Matrix ausrollen, `priority` generisch, MoSCoW nur Need | WS1, WS2 | 2–3 Wo |
| **WS7** AWMS | Plan-Engine + Backfills | WS1 | 3–5 Wo |

Reihenfolge: **WS0 → WS1 → (WS2 ∥ WS3 ∥ WS4 ∥ WS5) → WS6 → WS7**.

---

## 14. Entscheidungen (festgezurrt 12.09.2026)

1. `priority`-Skala: Default `low/medium/high/critical`, **je Definition anpassbar** (Enum-`options`).
2. `Actor`-Entität als **ein** Träger (Kombi-Feld) — bestätigt.
3. `allow_external`-Default **`false`** (nur interne User; je Attribut umstellbar).
4. Layout **flach** (Section → Attribut + Dummies); **Section- und Attribut-Dummies**.
5. Attribut-Typ-Name **`actor`** (Team-fähig).
