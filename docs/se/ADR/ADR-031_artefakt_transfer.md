---
adr_id: ADR-031
title: "Artefakt-Transfer: Import, Export und vollstaendige Workspace-Kopie"
status: accepted
date: 2026-11-21
deciders: [user, se-architect, orchestrator]
affected_reqs: [REQ-L1-046, REQ-L3-IMP-001, REQ-L3-IMP-002, REQ-L3-IMP-003, REQ-L3-IMP-004]
superseded_by: null
type: ADR
scope: application/artifact-transfer
author_agent: se-architect
---

# ADR-031: Artefakt-Transfer (Import, Export, Workspace-Kopie)

## Kontext

Import/Export und Backup/Restore deckten vor diesem Entscheid nur einen Teil der
24 REST/MCP-Entitäten ab. ReqIF behandelte TestCase und Icd nicht als
standardkonforme `SPEC-OBJECT`s; ein Voll-Snapshot fehlte; der CSV-Import kannte
weder Konfliktpolitiken noch eine „nie löschen"-Rekonziliation; der
App-Restore war weder checksum-geprüft noch ziel-adressierbar. Details und
Findings stehen im Plan `docs/plans/2026-11-21-artifact-transfer-plan.md`.

Ziel ist **ein** einheitlicher Transfervertrag für alle Entitäten, der in
einen bestehenden Workspace aktualisierend importieren **und** in einen neuen
Workspace als echte Datenkopie schreiben kann — ohne löschende Nebenwirkungen.

## Alternativen

- **Weiterführung der format-spezifischen Inseln** (CSV/ReqIF/Snapshot je
  eigenes Modell) — verworfen: 24 Entitäten × 4 Formate würde unkontrolliert
  driften; Relationen (Comments, TestRuns) blieben unexportiert.
- **Löschen und Neueinfügen (`replace`) als Default** — verworfen (D3/D3b):
  unter RLS und append-only-Audit würde Live-Daten und Audit-Historie
  vernichtet, die der Backup nicht rekonstruieren kann.
- **Cross-Tenant beliebig ohne Dry-Run** — verworfen (D16/D16b): RLS kann für
  einen fremden Tenant bewaffnet werden; ohne Ziel-ADMIN und Audit-Beleg ist
  das ein Datenleck und nicht nachvollziehbar.
- **App-Restore als zweite DR-Wahrheit** — verworfen (D17): der
  `postgres-backup`-Sidecar bleibt die verbindliche DR-Quelle.

## Entscheidung

Die Entscheidungen D1–D16/D18 des Plans werden hiermit verbindlich:

| ID | Entscheidung |
|---|---|
| D1 | Upsert-Schlüssel `uid` + Typ + Workspace, `id` bevorzugt bei Identität. |
| D2 | `version-guard` Default; `update` explizit; `skip`/`error` optional. |
| D3/D3b | Nie löschen: `reconcile_status` setzt typ-spezifischen Status (`Requirement→outdated`, `TestCase→deprecated`, …) und `not_in_source` im Artifact-`custom_fields`. |
| D4 | Ohne `target_workspace_id` → neuer Workspace wie `clone_workspace` (Preset/Workflow-Defaults + Creator-Admin). |
| D5 | Dry-Run optional, Pflicht bei Rekonziliation/Cross-Tenant; voller Diff. |
| D6 | All-or-nothing Default; `partial=true` explizit; ein `ImportResult`-Envelope. |
| D7 | Idempotenz pro `(target_workspace, key)`, Fingerprint inkl. Ziel. |
| D8 | Umfang: alle 24 REST/MCP-Entitäten. |
| D9 | Neue IDs + `source_id`; alle FKs/M2M werden remappt. |
| D10 | Alle Relationen, inklusive Comments und TestRuns. |
| D11 | Custom Fields validieren; Attribute-Definitionen nur beim neuen Workspace mitkopieren. |
| D12/D12b | Exportierte Felder sind autoritativ; `tenant_id`/`workspace_id`/`artifact_id`/FK-Ziele werden **immer** remappt. |
| D13 | Ausschluss: Audit, Secrets, globale Definitionen, externe Stores. |
| D14/D14a–d | ReqIF standardkonform (auch TestCase/Icd als SpecObject); ZIP-Snapshot mit `manifest.json`, JSONL, Relationen, Medien und SHA-256; `EXPORT_DIR` wie `BACKUP_DIR`; async Export; alle Formate für alle Typen. |
| D15 | `editor` = Merge; `admin` = `update`/`reconcile_status` (auch für API-Keys mit ADMIN-Scope). |
| D16/D16b | Cross-Tenant technisch möglich, aber nur mit Quell-LESEN + Ziel-ADMIN + Dry-Run-Pflicht (Audit-Beleg, 24 h) + beidseitigem Audit. |
| D18 | CSV/ReqIF bleiben; neue UI-Seite „Datenübernahme" mit Vorschau. |

D17 (App-Restore als Ziel-Instanz-Restore, Sidecar bleibt DR-Wahrheit) ist in
[ADR-012](ADR-012_backup_wahrheit.md) dokumentiert und wird hier nicht
wiederholt.

Die harte Invariante: **Identität und FK-Ziele werden immer gemappt, niemals
kopiert.** Ein importierter Datensatz trägt `source_id` und neue lokale IDs.

## Konsequenzen

- Positiv: ein Vertrag für alle Entitäten und Formate; verlustfreie
  Workspace-Kopie inklusive Relationen; keine stillen Löschungen;
  Cross-Tenant-Operationen sind auditierbar und brauchen einen expliziten
  Ziel-ADMIN.
- Positiv: der Dry-Run ist bei den gefährlichen Pfaden (Rekonziliation,
  Cross-Tenant) ein harter Gate, kein Komfort-Feature.
- Negativ: mehr Felder pro Import-Envelope (`conflicts[]`, `planned_remaps[]`,
  `not_in_source`) und ein zusätzlicher Audit-Beleg für den Cross-Tenant-Preview.
- Negativ: `reconcile_status` markiert Zeilen dauerhaft als nicht mehr in der
  Quelle vorhanden; ein späterer Export enthält diesen Status. Das ist
  gewollt (Audit-Trail), muss aber in der Doku hervorgehoben werden.
- Negativ: die OpenAPI-/Tool-Manifest-Fixtures und die DOC-008-Zählungen
  müssen bei jedem neuen Transfer-Endpoint mitgezogen werden, sonst rotieren
  die Drift-Gates.
