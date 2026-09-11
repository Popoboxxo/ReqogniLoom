# Verifikationsprotokoll — Attribut-Analyse (3-Stufen-Modell)

**Stand:** 11.09.2026 · Basis **v1.8.0-beta.10** (`b4c3a910`) · QS `172.20.5.120`
**Zweck:** Jede tragende Aussage des Reports wurde **einzeln** nachgeprüft — live gegen die laufende
Instanz und/oder am Quellcode. Ausführbar über `docs/se/attribut/verify_all.py` (13 Prüfungen).

Ergebnis: **12/13 bestätigt**, 1 zunächst falsch bewertete Aussage wurde durch Nachprüfung **präzisiert**
(uid, s. §2) — der ursprüngliche Verdacht war richtig, mein Prüfmuster zu grob.

---

## 1. Prüftabelle

| # | Aussage | Urteil | Beleg |
|---|---|---|---|
| 1 | Attributliste **und** `required`-Flags sind über `minimal`/`standard`/`extended` **identisch** (alle 11 Typen) | ✅ bestätigt | `GET /attribute-defaults/{type}/{preset}/` je Typ, Signaturen verglichen |
| 2 | `priority` fehlt als Requirement-Attribut | ✅ bestätigt | Attribute: `uid, category, type, level, complexity_fibonacci, verification_method, status, title, description, description_editor, acceptance_criteria` |
| 3 | `rationale` fehlt als Requirement-Attribut | ✅ bestätigt | dito |
| 4 | `source` fehlt als Requirement-Attribut | ✅ bestätigt | dito |
| 5 | `uid` ist vorhanden, aber `editable=False` | ✅ bestätigt | Definition + Bootstrap `READ_ONLY_MODEL_FIELDS = {"uid", "requestor_id"}` |
| 6 | 8 Modelle behaupten `uid "(read-only, auto-generated)"` | ✅ bestätigt | `models.py:973, 1059, 1187, 1558, 1671, 2524, 2657, 2890` |
| 7 | Es gibt **keine** uid-Generierung im Produktivcode | ✅ bestätigt (nach Präzisierung, s. §2) | 8 Grep-Treffer = 1 Validator + Migrations-Helfer |
| 8 | `uid` ist in allen Serializern `read_only` → Client kann es nicht setzen | ✅ bestätigt | 8× `serializers.CharField(read_only=True, allow_null=True)` |
| 9 | Live: **0 von 6** Requirements mit `uid` | ✅ bestätigt | Workspace `5147dcd9-60e6-4663-9fdb-f073e78208e8` |
| 10 | `mandatory_fields` ist **pro Preset**, nicht pro Item-Typ definiert | ✅ bestätigt | `presets/registry.py:170` |
| 11 | Baseline-State erfasst `Artifact.custom_fields` (inkl. „rationale"-Beispiel) | ✅ bestätigt | `baseline/state_capture.py:46` + Docstring (Issue #398) |
| 12 | QS: **0 Artefakte** mit `custom_fields` → Greenfield für Wert-Migration | ✅ bestätigt | requirements/needs/architecture/testcases geprüft |
| 13 | Interview-Adapter mappt `rationale → description` | ✅ bestätigt | `interview_artifact_adapters.py:166` |

---

## 2. Die eine präzisierte Aussage: `uid`

**Erstbefund des Skripts:** „WIDERLEGT — 8 Treffer" für die Aussage „keine uid-Generierung".
**Ursache:** zu grobes Prüfmuster (`grep -iE 'def .*uid'`).

**Nachprüfung der 8 Treffer:**

| Treffer | Art |
|---|---|
| `migrate_se_docs.py:364/375/380/392/635/760` | **Migrations-Command** (Parameter/Helfer) — kein Produktivpfad |
| `requirement_service.py:193` `_assert_uid_unique_in_workspace` | **Validator** (prüft Eindeutigkeit, erzeugt nichts) |
| `persistence/migrations/0055_…:43` `_dedupe_uid_collisions` | **Datenmigration** (räumt Kollisionen auf) |

**Ergebnis: die Aussage ist BESTÄTIGT** — es existiert **kein** Generator.

### Der vollständige uid-Befund

```python
# backend/persistence/models.py:969-974 — identisch in 8 Modellen
uid = models.CharField(
    max_length=64, null=True, blank=True,
    help_text="Unique identifier (read-only, auto-generated)",
)
```

```
# Anlege-Signatur: uid ist ein Durchreiche-Parameter mit Default None
create_requirement(self, workspace_id, title, ctx, description="", acceptance_criteria="",
                   category="", parent_id=None, type="SyReq", complexity_fibonacci=None,
                   verification_method=None, level=None, uid: Optional[str] = None,
                   custom_fields=None) -> Requirement
```

```
# Serializer: read-only → kein Client kann es setzen
uid = serializers.CharField(read_only=True, allow_null=True)      # 8×
```

| Frage | Antwort |
|---|---|
| Wird `uid` automatisch erzeugt? | **Nein** — kein Generator, kein Signal, kein Service |
| Kann ein Nutzer es setzen? | **Nein** — in allen Serializern `read_only` |
| Kann ein Agent (MCP) es setzen? | **Nein** — dieselben Serializer |
| Wer füllt es dann? | nur **Import/Migration**: `reqif_import_service.py:562/698`, `migrate_se_docs` |
| Live-Bestand | **0 von 6** Requirements |

**Folge:** Für jedes normal angelegte Artefakt ist `uid` **dauerhaft NULL**. Der `help_text` beschreibt
einen Zustand, den der Code nicht herstellt — ein gebrochenes, dokumentiertes Versprechen.

**Auswirkung auf den Report:** `uid` wurde von „Stufe-1-Pflichtfeld" auf **system-owned** korrigiert
(Challenge-Punkt **C9**). Ein Feld, das der Nutzer nicht liefern **kann**, darf keine Nutzer-Pflicht sein.

**Vorgeschlagene Lösung:** Autogenerierung implementieren — `{PREFIX}-{NNN}` je `(workspace, item_type)`,
eindeutig (der Constraint aus Migration `0055` existiert bereits), nie wiederverwendet. Andernfalls den
`help_text` auf den tatsächlichen Zustand korrigieren.

---

## 3. Nicht verifizierbar / offen

| Punkt | Warum offen |
|---|---|
| Aussage 1 nur für **globale** Defaults geprüft | Workspace-Ebene materialisiert daraus (`AttributeDefinitionService.resolve`); ein Workspace mit `is_customized=true` kann abweichen — in der QS liegt keiner vor |
| `Measure`-Entität | existiert nicht (bestätigt, #393); die Empfehlung ist ein **Vorschlag**, keine Messung |
| Migrationssystematik (AWMS) | Konzept; es gibt **keine** Implementierung zu prüfen |
| Produktionsdaten | alle Messungen stammen aus der **QS**; PROD wurde nicht angefasst |

---

## 4. Reproduktion

```bash
# auf der QS-Sandbox
cd /home/hermes/repos/ReqogniLoom
python3 verify_all.py        # 13 Prüfungen, Tabelle + Zähler
```

Voraussetzungen: `.env` mit `SYSTEM_ADMIN_PASSWORD`, Backend auf `127.0.0.1:8001`
(override via `RL_BASE`), Repo-Checkout auf `v1.8.0-beta.10`.
