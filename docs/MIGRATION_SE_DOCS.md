# Migration: docs/se/ → ReqFlow-Workspace

> Anleitung für `backend/application/management/commands/migrate_se_docs.py`.
> Importiert das SE-Requirements-Register (`docs/se/`) idempotent in einen
> laufenden ReqFlow-Workspace, über `ImportService` (COMP-AS-009) — dieselbe
> Engine wie der CSV-Bulk-Import via REST/MCP.

---

## Voraussetzungen

- Laufender Backend-Container (`docker-compose up`) oder lokale Django-Umgebung
- Ein existierender User (Default: `admin`, siehe `seed_demo.py`)
- Ein existierender Ziel-Workspace (Default: der Demo-Workspace `6d20f0b9-d2cf-46a0-b916-79f8b417210f`)

## Kommando

```bash
# Im Backend-Container:
python manage.py migrate_se_docs [Optionen]

# Via docker-compose:
docker-compose exec backend python manage.py migrate_se_docs [Optionen]
```

### Optionen

| Flag | Default | Bedeutung |
|------|---------|-----------|
| `--docs-root` | `<BASE_DIR>/docs/se` | Pfad zum Requirements-Root (im Container: `/app/docs/se`) |
| `--workspace-id` | Demo-Workspace-UUID | Ziel-Workspace |
| `--username` | `admin` | Actor für den synthetischen `AuthContext` |
| `--dry-run` | aus | Nur parsen + klassifizieren, nichts schreiben |

### Empfohlener Ablauf

```bash
# 1. Trockenlauf — zeigt Zählung, Warnungen, UNMAPPED-Liste, schreibt nichts
python manage.py migrate_se_docs --dry-run --docs-root <pfad> --workspace-id <ziel-uuid>

# 2. Ergebnis prüfen (siehe "Was tun bei Warnungen" unten)

# 3. Echter Import
python manage.py migrate_se_docs --docs-root <pfad> --workspace-id <ziel-uuid>
```

---

## Was wird importiert (Mapping-Regeln)

Das Skript klassifiziert **jede** `.md`-Datei unter `--docs-root` nach festen Regeln:

| Quelle | Ziel-Entität | Erkennungsmerkmal |
|--------|--------------|--------------------|
| `L0/*.md` | `StakeholderNeed` | Datei liegt direkt unter `L0/` — ein Datensatz pro `### REQ-L0-...`-Heading |
| `*_Requirements.md` | `Requirement` | Dateiname-Endung — ein Datensatz pro `### REQ-L1/L2/L3-...`-Heading |
| `*_Architecture.md` | `ArchitectureElement` | Dateiname-Endung — ein Datensatz pro Datei |
| `ADR/ADR-*.md` | `Adr` | Ordner `ADR/` + Dateiname-Präfix `ADR-` |

**Alles andere** (z. B. `*_TestModel.md`, `*_Backlog.md`, Dateien ohne passendes Heading) landet
in der **UNMAPPED-Liste** und wird explizit als Warnung ausgegeben — nie stillschweigend übersprungen.

### Bewusst NICHT importiert

- **TestCase** — die 6 `*_TestModel.md`-Dateien mischen Fließtext, eingebettetes JSON und
  uneinheitliche Pro-Komponente/Pro-Szenario-Abschnitte. Ein regelbasierter Extraktor würde hier
  Datenmüll produzieren. Muss manuell oder mit einem eigenen Parser nachgezogen werden.
- **Risk / Issue** — `docs/se` hat aktuell kein eigenes Risk- oder Issue-Register (keine Quelldateien).

---

## Feld-Mapping pro Entität

### StakeholderNeed
`title`, `description` (Heading-Body), `uid` (die `REQ-L0-...`-ID)

### Requirement
`title`, `description`, `level`, `uid` (die `REQ-L1/L2/L3-...`-ID)

**Level-Mapping** (docs/se-Nummerierung ≠ `persistence.models.RequirementLevel`-Enum):

| docs/se | ReqFlow `RequirementLevel` |
|---------|---------------------------|
| `REQ-L1-*` | `0` (`L0_SYSTEM`) |
| `REQ-L2-*` | `1` (`L1_SUBSYSTEM`) |
| `REQ-L3-*` | `2` (`L2_COMPONENT`) |

`L4` (`L4_MATERIAL`) wird nie belegt — docs/se hat keine L4-Dokumente.

### ArchitectureElement
`title` (erstes H1), `description` (Abschnitt "1. ..."), `element_type`, `uid`

UID-Herleitung (in dieser Priorität):
1. `L1_Gesamtsystem_Architecture.md` → fester Wert `ARCH-L1-000`
2. Ordnername enthält `COMP-<XX>-<NNN>_` → dieser Code, `element_type = component`
3. Text enthält `(ARCH-L1-NNN)` → dieser Code, `element_type = subsystem`
4. Fallback: `ARCH-L2-<SystemName>` aus `**System:** <Name>` — wird als Warnung gemeldet

### ADR
`title` (erstes H1), `description` (**gesamter** Dateiinhalt, nichts geht verloren),
`context` (Abschnitt "Kontext"), `consequences` (Abschnitt "Entscheidung"), `status`, `uid` (`ADR-NNN`)

**Status-Mapping:**

| Quelltext | ReqFlow `Adr.Status` |
|-----------|----------------------|
| `PROPOSED`, `IN REVIEW` | `IN_REVIEW` |
| `DRAFT` | `DRAFT` |
| `ACCEPTED`, `APPROVED` | `APPROVED` |
| `REJECTED` | `REJECTED` |
| `SUPERSEDED` | `SUPERSEDED` |
| unbekannt/fehlend | `DRAFT` (mit Warnung) |

---

## Nachgelagerte Pässe (nach dem CSV-Import)

Nach den vier CSV-Entity-Buckets laufen zwei Zusatz-Pässe **innerhalb desselben Kommandos**.
`ENTITY_FIELD_SPECS` und `ImportService` bleiben dafür unangetastet — beide Features sind reine
Zusatzlogik in `migrate_se_docs.py`.

### Feature 1 — Architektur-Hierarchie (`parent_id`)

`ArchitectureElement.parent_id` (REQ-L1-041) existiert im Datenmodell, ist aber **bewusst kein
Feld** in `ENTITY_FIELD_SPECS` — der CSV-Weg transportiert es nicht. Nach dem Import löst ein
zweiter Pass die Eltern-Beziehung **deterministisch aus der Ordnerstruktur** auf:

| Element | `element_type` | Parent |
|---------|----------------|--------|
| `L1/Gesamtsystem/L1_Gesamtsystem_Architecture.md` → `ARCH-L1-000` | `subsystem` (Wurzel) | — (kein Parent) |
| `.../L2/<System>/L2_<System>_Architecture.md` | `subsystem` | `ARCH-L1-000` (Wurzel) |
| `.../L2/<System>/Components/COMP-<XX>-<NNN>_.../L3_..._Architecture.md` | `component` | uid des L2-Subsystems, dessen Verzeichnis (`.../L2/<System>`) nächster Vorfahre der Komponenten-Datei ist |

**Service-vs-ORM-Entscheidung:** `ArchitectureService.update_architecture_element(...)` existiert,
ist hier aber **nicht** nutzbar: Der Invariant **I2** (Standard/Extended-Rigor) verlangt
`parent.level < child.level`, gemessen an der **aktuellen** Baumtiefe. Direkt nach dem flachen
Import ist jedes Element eine Wurzel (Level 0), das erste Re-Parenting ist also immer
`Level 0 → Level 0` und wird von I2 abgelehnt — der Domain-Service kann eine Hierarchie aus einem
flachen Import prinzipiell nicht aufbauen. Ein Batch-Modus dafür wäre für einen Einmal-Job
unverhältnismäßig. Daher schreibt dieser Pass `parent_id` per **direktem, klar kommentiertem
ORM-Update** (`.update()`, kein Version-Bump, kein Domain-Event) — dokumentierter Migrations-Batch,
**kein** regulärer API-Schreibweg.

Idempotent: bereits korrekt gesetzte `parent_id` werden übersprungen. `--dry-run` schreibt nichts,
meldet aber `would_assign`.

### Feature 2 — Trace-Links aus `traceability-matrix.md`

Die konsolidierte Matrix `docs/se/traceability-matrix.md` wird **als letzter Schritt** gelesen
(Quelle **und** Ziel jedes Links müssen als Artefakt existieren). Sie wird nicht mehr als UNMAPPED
gelistet. Pro Matrix-Abschnitt werden Markdown-Tabellenzeilen geparst; Zellen mit `—` sowie
Platzhalter-Zeilen (`... (N weitere ...)`) und Spaltenköpfe erzeugen keinen Link.

Link-Typ + Orientierung pro Abschnitt (so gewählt, dass sie auch die SE-Endpoint-Semantik
`traceability.types.SE_LINK_SEMANTICS` erfüllen und damit im `se_mode` gültig bleiben):

| Matrix-Abschnitt | Link (Source → Target) | Link-Typ | SE-Semantik |
|------------------|------------------------|----------|-------------|
| §1 REQ-L0 → REQ-L1 | REQ-L1 → REQ-L0 | `derives-from` | Requirement → StakeholderNeed |
| §2 REQ-L1 → REQ-L2 | REQ-L2 → REQ-L1 | `derives-from` | Requirement → Requirement |
| §3 REQ-L2 → Component | Component → REQ-L2 | `implements` | ArchitectureElement → Requirement |

Die **Test-Case-Spalte** in §3 wird **bewusst nicht** verlinkt: TestCases werden von diesem
Kommando nicht importiert (siehe „Bewusst NICHT importiert"), ein Link-Endpunkt würde nie
aufgelöst. Erstellung über `TraceLinkService.create_trace_link(...)` — der reguläre,
event-emittierende Weg (analog zu `ImportService` für die vier Entitäten). Vor jedem Erstellen wird
geprüft, ob das Tripel (Source, Target, Link-Typ) bereits existiert (Idempotenz). Nicht auflösbare
uids (Tippfehler, nicht importierte Ziele) werden als Warnung gemeldet und übersprungen — nie fatal.
`--dry-run` schreibt nichts, meldet aber `resolved` / `already_linked` / `new`.

---

## Idempotenz

Jede importierte Zeile bekommt ein deterministisches `uid`-Feld (aus der `REQ-Lx-...`-ID, dem
`ARCH-...`/`COMP-...`-Code oder dem `ADR-NNN`-Präfix). Vor jedem Import prüft das Skript, welche
`uid`-Werte im Ziel-Workspace bereits existieren, und importiert nur neue.

→ **Beliebig oft wiederholbar.** Zweiter Lauf gegen denselben Workspace zeigt
`already_imported = <alle>`, `new = 0`.

Beide Zusatz-Pässe sind ebenfalls idempotent: bereits gesetzte `parent_id` (Feature 1) und
bereits existierende Trace-Link-Tripel (Feature 2) werden übersprungen — ein zweiter Lauf schreibt
weder neue Parents noch neue Links (`assigned = 0`, `created = 0`).

---

## Was tun bei Warnungen

Der `--dry-run`-Report zeigt drei Kategorien:

1. **Parse-Warnungen** — z. B. Datei ohne passendes Heading (0 Entities), fehlender
   Architecture-Abschnitt "1. ...", unbekannter ADR-Status, fehlender `(ARCH-L1-xxx)`-Code.
   → Quelldokument prüfen, ggf. Heading/Abschnitt nachpflegen, dann erneut versuchen.
2. **Dedup-Warnungen** — doppelt vergebene `uid` innerhalb desselben Laufs (bekannte
   Altlast in docs/se, z. B. `REQ-L1-085` doppelt verwendet). Erste Fundstelle gewinnt,
   jede weitere wird übersprungen und gemeldet — kein automatisches Auto-Fixing der Quelle.
3. **UNMAPPED-Liste** — Datei passt zu keiner der vier Mapping-Regeln. Kein Datenverlust,
   aber auch kein Import — Datei bleibt außen vor bis eine eigene Mapping-Regel ergänzt wird.
4. **Parent-Warnungen** (Feature 1) — Komponente ohne auflösbaren L2-Subsystem-Parent in der
   Ordnerstruktur, oder ein Parent-/Kind-Element fehlt unter den importierten
   `ArchitectureElement`s. `parent_id` bleibt in dem Fall ungesetzt.
5. **Trace-Link-Warnungen** (Feature 2) — nicht auflösbare Source-/Target-uid (Tippfehler in der
   Matrix oder nicht importiertes Ziel wie eine TestCase). Der betroffene Link wird übersprungen.

**Grundsatz:** nichts wird still verschluckt. Jede Datei landet entweder in einem Bucket,
in der UNMAPPED-Liste oder in einer Warnung.

---

## Eigene Requirements migrieren (abweichendes Format)

Das Skript ist **hart auf die docs/se-Konventionen zugeschnitten** (Heading-Syntax, Dateinamen-Suffixe,
Ordnerstruktur `L0/`, `ADR/`). Liegen eigene Requirements in einem anderen Format vor:

- **Gleiche Konventionen, anderer Pfad** → einfach `--docs-root <eigener-pfad>` verwenden.
- **Abweichende Konventionen** (andere Heading-Syntax, andere Dateinamen) → das Skript erkennt
  die Dateien nicht und listet sie unter UNMAPPED. In diesem Fall:
  - Entweder Quelldateien an die docs/se-Konventionen angleichen, oder
  - `_classify_file()` / die `_parse_*_file()`-Funktionen um eine eigene Regel erweitern, oder
  - Direkt den CSV-Bulk-Import (REST/MCP, `ImportService.import_csv`) mit selbst gebauten
    CSV-Dateien nutzen — Spaltenschema siehe `application/export_service.py::ENTITY_FIELD_SPECS`.

---

## Bekannte Einschränkungen

- **CSV-`#`-Stripping-Workaround:** `ImportService._parse_csv` entfernt jede physische Zeile,
  die mit `#` beginnt (Kommentar-Header-Konvention des Exporters), ohne RFC4180-Multiline-Quoting
  zu beachten. Da Requirement-Bodies oft eingebettete Markdown-Headings (`#`) enthalten, fügt das
  Migrationsskript vor jeder eingebetteten `#`-Zeile ein führendes Leerzeichen ein. Das ist eine
  rein CSV-transport-seitige Absicherung, hinterlässt aber ein kosmetisches, einmaliges
  Leerzeichen im gespeicherten Text (nicht rückgängig machbar über `ImportService`).
- **Keine automatische TestCase/Risk/Issue-Migration** (siehe oben).
- **Kein Byte-genauer Round-Trip garantiert** für Dokumente außerhalb der vier Mapping-Regeln.

## Verwandte Dateien

- `backend/application/management/commands/migrate_se_docs.py` — Implementierung
- `backend/application/export_service.py` — `ENTITY_FIELD_SPECS` (CSV-Spaltenschema, von beiden Seiten geteilt)
- `backend/application/import_service.py` — `ImportService` (COMP-AS-009, generische Import-Engine)
