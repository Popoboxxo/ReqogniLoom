# Datenmodell-Konsolidierung — Design

**Status:** Draft, pending user review
**Quelle:** `docs/SYSTEMAUDIT_2026-09-02_GROB.md`, Kap. B1 (drei Status-Achsen), B2 (zwei
Persistenzmodelle, Layer-Verstoß), B6 (zwei Versionierungskonzepte), Q2.3 (zu Ende
gedachtes generisches Artefaktmodell). Zweite von mehreren unabhängigen Folge-Specs aus
demselben Audit — siehe [2026-09-03-attribute-definition-design.md](2026-09-03-attribute-definition-design.md)
für die erste.
**Scope:** Nicht Teil dieser Spec: die Attribut-Struktur/-Validierung selbst (eigene
Spec), rollenbasierte Sichten, Traceability-Link-Semantik (eigene Spec). Diese Spec baut
das Fundament, auf dem die Attribut-Definition-Spec aufsetzt — siehe Abschnitt 7 zur
Reihenfolge.

## 1. Problem

Vier unabhängige Konsequenzen desselben Grundproblems — es gibt kein einheitliches
Artefaktmodell, obwohl `persistence.Artifact` (ADR-05) genau dafür gebaut wurde:

- **Drei Status-Achsen** (B1): `Requirement.status` (default `"draft"`),
  `Requirement.lifecycle_status` (Soft-Delete: active/outdated/deleted), und Workflow
  `WorkflowItemState.current_state`. `Goal`/`MainGoal.status` haben zusätzlich einen
  deutschen String-Default `"Entwurf"`, obwohl die Persistence-Schicht durchgängig
  `"draft"` nutzt. Die UI-Prinzip "Farbe gehört dem Zustand" hat keinen eindeutigen
  Zustand, dem sie gehören kann.
- **Layer-Verstoß** (B2): `Adr`, `Risk`, `Goal`, `MainGoal`, `Issue`, `ChangeRequest`
  sind als plain `models.Model` in `application/models.py` (Layer 2) definiert statt als
  `TenantScopedModel` in `persistence/models.py` (Layer 0) — mit manuell dupliziertem
  `tenant_id`/`workspace_id` statt der gemeinsamen RLS-Basisklasse. **Präzisierung
  gegenüber dem Audit-Text:** alle sechs haben bereits eine `artifact`-OneToOne-FK zu
  `persistence.Artifact` (REQ-L2-TE-020-Muster) — der Fehler ist die Platzierung und die
  fehlende RLS-Vererbung, nicht ein fehlendes Artifact-Backing.
- **Diagram/Icd/GlossaryTerm ohne Artifact-Backing:** anders als die sechs oben haben
  `Diagram` und `Icd` (eigene Apps, `TenantScopedModel`, aber bewusst von
  `persistence.Workspace` entkoppelter `workspace_id`-UUID-Feld) **kein**
  Artifact-Backing. **Korrektur (2026-09-03, entdeckt bei der Interview-Engine-Spec):**
  entgegen dem Audit-Text (B2), der `GlossaryTerm` in die "hat schon Artifact +
  Spezialtabelle"-Gruppe einsortiert, hat auch `GlossaryTerm`
  (`persistence/models.py:1833`) **kein** `artifact`-FK — bestätigt durch
  `interview_artifact_adapters.py`s `_glossary_term`-Adapter, der jede
  Interview-Erstellung explizit mit "GlossaryTerm is not Artifact-backed yet" ablehnt.
  GlossaryTerm bekommt daher dieselbe Behandlung wie Diagram/Icd (Abschnitt 4), nicht nur
  diese zwei. Fünf Orte für "Artefakt" statt einem, nicht vier.
- **Zwei Versionierungskonzepte** (B6): Audit-Log-basiert (`versions`+`diff` über
  `backend/audit/`, inkl. `VersionReconstructor`) für Need, Requirement, Architecture,
  TestCase, Adr, Risk, Issue, Glossary — parallel dazu eigene Snapshot-Tabellen
  (`DiagramVersion`, `IcdVersion`, `GlossaryTermVersion`, Glossary nutzt beides). Lücken:
  Goal nur `versions` ohne `diff`, MainGoal nur `versions`, ChangeRequest nur
  `transition`.

## 2. Ziel

Jeder der 10 Artefakttypen: eine `persistence.Artifact`-Zeile + eine spezialisierte
`TenantScopedModel`-Tabelle (wie Requirement/StakeholderNeed/ArchitectureElement/TestCase
heute — `GlossaryTerm` erst nach Abschnitt 4 dieser Spec). Eine sichtbare Status-Achse
(`WorkflowItemState.current_state`), ein orthogonales Soft-Delete-Flag (`lifecycle_status`
auf `Artifact`), eine Versionierungsmaschine (Audit-Log-basiert) für alle 10 Typen.

## 3. Layer-Bereinigung: Adr, Risk, Goal, MainGoal, Issue, ChangeRequest

1. Modellklassen von `application/models.py` nach `persistence/models.py` verschieben.
2. Basisklasse `models.Model` → `TenantScopedModel`. Die bisherigen manuellen
   `tenant_id`/`workspace_id`-UUID-Felder entfallen zugunsten der gemeinsamen
   RLS-Basisklasse (Row-Level-Isolation am Manager statt Join, konsistent mit ADR-03).
3. Die `artifact`-OneToOne-FK bleibt unverändert bestehen (kein struktureller Eingriff
   nötig, nur der Owner der Klasse ändert sich).
4. `application/` behält nur noch die Services (`AdrService`, `RiskService`, ...), die
   auf den jetzt in `persistence` liegenden Modellen operieren — stellt die
   Single-Entry-Point-Fassade (ADR-01) wieder her, die B9 als eingehalten lobt, aber B2
   für diese sechs Typen als verletzt markiert.

## 4. Diagram/Icd/GlossaryTerm: Artifact-Backing nachrüsten

1. Neues nullable `artifact = models.OneToOneField("persistence.Artifact", ...)` auf
   `Diagram`, `Icd` **und `GlossaryTerm`**, exakt das Muster von `Adr.artifact`
   (REQ-L2-TE-020).
2. **Backfill-Migration:** für jede bestehende `Diagram`-/`Icd`-/`GlossaryTerm`-Zeile eine
   `Artifact`-Zeile erzeugen (`artifact_type="Diagram"`/`"Icd"`/`"GlossaryTerm"`,
   `workspace` aus dem bisherigen `workspace`/`workspace_id`-Feld aufgelöst — GlossaryTerm
   hat bereits eine echte `Workspace`-FK, keine entkoppelte UUID wie Diagram/Icd) und die
   neue `artifact`-FK setzen. Ein Referential-Integrity-Check nach der Migration: genau
   eine neue `Artifact`-Zeile pro Alt-Zeile, keine verwaisten oder doppelten
   Verknüpfungen.
3. Neue Zeilen: `DiagramService.create_diagram`/`IcdService.create_icd`/
   `GlossaryService.create_term` legen künftig zuerst die `Artifact`-Zeile an, dann die
   spezialisierte Zeile — wie `AdrService.create_adr` es heute schon tut.
4. Für Diagram/Icd ist das eine bewusste Umkehr der früheren Entkopplungs-Entscheidung
   (der Code-Kommentar in `diagram/models.py` nennt explizit "avoid coupling ... to the
   persistence app's Workspace table"); für GlossaryTerm ist es das Schließen einer
   bisher unbemerkten Lücke, keine Umkehr einer bewussten Entscheidung. Konsequenz und
   Nutzen: `diagram-ref`-TraceLinks (Audit B4), Baseline-Scope "Document" für
   Diagramme/ICDs, **und Multi-Artefakt-Interviews für GlossaryTerm** (siehe
   [2026-09-03-interview-engine-fix-design.md](2026-09-03-interview-engine-fix-design.md))
   funktionieren erst dadurch überhaupt.

## 5. Status-Konsolidierung

- **Einzige sichtbare Status-Achse:** `WorkflowItemState.current_state`. Das Modell selbst
  ist unverändert — es ist bereits generisch über `(tenant, item_id, item_type)`, trackt
  also schon heute beliebige Artefakttypen ohne Änderung.
- **Entfernt (als Spalte, nicht nur deprecated):** `Requirement.status`, `Adr.status`,
  `Risk.status` (`RiskStatus`-Choices), `Issue.status`, `ChangeRequest.status`,
  `Goal.status` (inkl. des deutschen `"Entwurf"`-Defaults — Bug B1 damit als Nebeneffekt
  behoben), `MainGoal.status`.
- **`StateLifecycleManager._sync_status_mirror`** (der bisherige Sync-Mechanismus
  zwischen Workflow-Transition und der jeweiligen Status-Spalte) entfällt vollständig —
  totes Konzept nach der Migration, keine zwei Wahrheiten mehr zu synchronisieren.
- **`lifecycle_status` ist ein anderes Konzept als Status** (Soft-Delete: aktiv/outdated/
  gelöscht, REQ-006) und wandert von `Requirement` (heute der einzige Typ, der es hat)
  auf `Artifact` selbst — alle 10 Typen bekommen dadurch einheitlich Soft-Delete, nicht
  nur Requirement.
- **Migrationsreihenfolge-Zwang:** laut Audit-Priorisierung (Tabelle O) muss dieser
  Schritt **vor** Schritt 2 der Attribut-Definition-Bootstrap (siehe verlinkte Spec,
  Abschnitt 3.2) laufen — sonst nimmt das Bootstrap-Script die dann ohnehin gelöschten
  Alt-Status-Spalten als Kern-Attribute auf und zementiert den Sonderfall ein.

**FE-Konsequenz** (nicht Teil dieser Backend-Spec, aber Abhängigkeit): Badge-Logik liest
künftig zwei klar getrennte, orthogonale Signale — `current_state` (Workflow) und
`lifecycle_status` (Artifact) — statt drei vermischter Achsen.

## 6. Versionierung-Konsolidierung

1. Alle 10 Typen auf die bestehende Audit-Log-basierte Versionierung (`backend/audit/`,
   `AuditEntry` + `VersionReconstructor`) umstellen — das ist bereits der Mechanismus für
   8 von 10 Typen, wird hier nur auf die übrigen zwei/drei erweitert.
2. `DiagramVersion`, `IcdVersion`, `GlossaryTermVersion` werden retired. Vor dem Entfernen
   übersetzt eine Migration jede historische Zeile dieser drei Tabellen in einen
   äquivalenten `AuditEntry`-Eintrag (Payload als Diff-Snapshot im Audit-Log) — harte
   Migration wie entschieden, aber ohne Historienverlust.
3. Damit schließen sich die B6-Lücken automatisch: Goal (heute nur `versions` ohne
   `diff`), MainGoal (heute nur `versions`), ChangeRequest (heute nur `transition`)
   bekommen dieselbe generische `versions`+`diff`-Maschinerie wie Requirement, ohne
   eigenen Code.
4. `ArtifactDiff` im Frontend bedient danach nur noch eine Welt statt zwei parallele
   Formate.

## 7. Migrationsreihenfolge und Abhängigkeit zur Attribut-Definition-Spec

Eine harte Migration (wie bei der Attribut-Definition-Spec entschieden), in vier Phasen
— die Reihenfolge ist durch Abhängigkeiten erzwungen, nicht durch Rollback-Vorsicht:

1. **Status-Konsolidierung** (Abschnitt 5) — zuerst, weil die Attribut-Definition-Spec
   (siehe deren Abschnitt 3.2, Bootstrap-Script) davon abhängt, dass die Status-Spalten
   schon verschwunden sind, bevor sie die Kern-Attribut-Liste generiert.
2. **Layer-Bereinigung** (Abschnitt 3) — Adr/Risk/Goal/MainGoal/Issue/ChangeRequest nach
   `persistence/`.
3. **Diagram/Icd-Artifact-Backfill** (Abschnitt 4).
4. **Versionierung zuletzt** (Abschnitt 6) — jeder Typ braucht ein stabiles Artifact- und
   Status-Fundament, bevor seine Historie in `AuditEntry`-Einträge übersetzt wird.

**Praktische Konsequenz für die Implementierungsreihenfolge über beide Specs hinweg:**
diese Spec (mindestens Phase 1) muss vor der Attribut-Definition-Bootstrap-Migration
(Attribut-Definition-Spec, Abschnitt 3.2/4) umgesetzt sein.

## 8. Risiken

- **Größte Migration im gesamten Audit-Katalog** — der Audit selbst schätzt 3–5 Tage nur
  für die Analyse (Kap. I, Tiefenanalyse #2). Betrifft Produktivdaten in praktisch jeder
  Tabelle, nicht Konfigurationstabellen wie bei der Attribut-Definition-Spec.
- **Jede Lesestelle des bisherigen Status-Mirrors** (Serializer, Badge-Logik in der UI,
  Reports, `se_metrics`) muss vor dem Spalten-Drop auf `WorkflowItemState.current_state`
  umgestellt sein — ein übersehener Leser bricht still (liest eine nicht mehr existierende
  Spalte oder einen veralteten Wert).
- **Diagram/Icd-Backfill** braucht sorgfältige Referential-Integrity-Prüfung, weil hier —
  anders als bei den übrigen acht Typen — rückwirkend neue `Artifact`-Zeilen für
  Bestandsdaten entstehen, nicht nur bestehende FKs umgehängt werden.
- **Audit-Log-Rekonstruktion für große Payloads** (Mermaid-/PlantUML-Strings in
  Diagram-Versionen, ICD-Contract-Specs) muss dieselbe Diff-Qualität liefern wie die
  bisherigen expliziten Snapshot-Zeilen — sonst Funktionsverlust beim Versionsvergleich
  für genau die Typen, die gerade erst Artifact-Backing bekommen haben.
- **Reihenfolge-Kopplung zur Attribut-Definition-Spec** (Abschnitt 7) ist eine echte
  Abhängigkeit zwischen zwei unabhängig geschriebenen Specs — beim Schreiben eines
  Implementierungsplans für eine der beiden muss die jeweils andere Spec als Vorbedingung
  geprüft werden, nicht nur als Kontext gelesen werden.
