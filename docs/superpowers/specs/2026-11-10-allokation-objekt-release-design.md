# Allokation als Objekt und Freigabe-Kaskade — Design (Stufen 2–4)

**Status:** proposed (Freigabe-Gate vor Task 4–6 des Plans)
**Datum:** 2026-11-12
**Bezug:** ADR-028, ADR-027, Issue #1670 (Konzept), Plan `docs/superpowers/plans/2026-11-10-phase-e-requirements-architektur.md`
**Entscheidungen:** D9 (Mehrfachallokation konfigurierbar), D10 (beide Release-Pfade), D12 (Inhaltsfreeze rigor-abhängig)

---

## 1. Zustandsmodell `Allocation`

Eine `Allocation` ist das Objekt hinter genau einer `TraceLink(allocated-to)`-Kante.

| Feld | Typ | Bedeutung |
|---|---|---|
| `id` | UUID | Primärschlüssel |
| `tenant_id`, `workspace_id` | UUID | RLS-/Tenant-Scope wie alle Artefakt-Tabellen |
| `requirement_artifact_id` | UUID FK | alloziiertes Requirement (Artifact-Ebene) |
| `element_artifact_id` | UUID FK | Ziel-Architekturelement |
| `status` | enum | `draft` \| `released` \| `revoked` |
| `is_primary` | bool | führende Kante bei Mehrfachallokation (D9) |
| `released_at`, `released_by` | timestamp, UUID | wer/wann freigegeben |
| `revoked_at`, `revocation_reason` | timestamp, text | wer/wann zurückgezogen, Begründung |
| `created_at`, `updated_at` | timestamp | Audit |

**Übergänge:**

```
draft ──release──► released ──revoke──► revoked
  ▲                   │
  └─────reopen────────┘   (nur solange kein Element-Release existiert)
```

| Übergang | Erlaubt wer | Bedingung |
|---|---|---|
| `draft → released` | Admin/Approver im Workspace | Element nicht freigegeben oder Teil derselben Freigabe |
| `released → revoked` | Admin | Change Request mit Begründung |
| `released → draft` | — | verboten (`reopen` nur aus `revoked`) |
| `revoked → draft` | Admin | neuer Change Request |

**Invariante (Dual-Write):** Für jede **aktive** Allokation (`draft`/`released`)
existiert genau eine `TraceLink(allocated-to)`-Kante und umgekehrt. `revoked`
ist ein Archivzustand ohne Kante. Die Invariante wird (a) in jedem
Schreibpfad hergestellt, (b) von einer Konsistenzprüfung
(`manage.py check_allocations`) über alle Pfade geprüft und (c) in Tests über
`allocate()`, generisches `create_trace_link`, Import und Baseline-Restore
belegt.

## 2. Freigabe-Kaskade

**Element-Release** (`POST /api/v1/architecture-elements/{id}/release/`):

1. Element und seine Nachfahren sperren (Position, Kanten) — vorhandener
   `artifact_freeze`-Mechanismus.
2. Alle aktiven Allokationen auf dieses Element und seine Nachfahren:
   `status = released`.
3. **Nur `extended`:** je alloziertem Requirement eine `ArtifactVersion`
   (Inhaltsstand) anlegen.
4. `tier_key` des Elements im Release-Stand pinnen (Stufe 4).

**Batch-Grenzen:** Verarbeitung in Blöcken von 500; bis 5.000 betroffene
Requirements synchron, darüber asynchron (Celery, Antwort `202` mit Task-ID).
Die Zahl der Datenbankabfragen muss von der Requirement-Zahl unabhängig bleiben
(Stapelverarbeitung, kein N+1).

**Einzel-Release** (`POST /api/v1/requirements/{id}/release/`): setzt
ausschließlich die Allokation(en) dieses Requirements auf `released` und pinnt
dessen `tier_key`. `D10`-Vorrang: Liegt das Requirement unter einem
freigegebenen Element, ist der Einzel-Release ein No-op-Erfolg (bereits
abgedeckt), kein Fehler.

**Sperre:** Nach einem Release liefern Änderungen an Struktur, Kante oder
(bei `extended`) Inhalt **409** mit CR-Verweis (§4). Kein Pfad darf die Sperre
umgehen — insbesondere nicht `allocate(mode="replace")`, generische
TraceLink-Schreibpfade, Import oder Baseline-Restore.

## 3. Rigor-Matrix (D3/D12)

| Rigor | Ordnung (O2/O3) | Container-Deklaration | Konflikt Allokation ↔ Container | Änderung nach Freigabe | Inhaltsfreeze |
|---|---|---|---|---|---|
| `minimal` | frei, nicht freigaberelevant | Vorschlag | `info` | ohne CR, protokolliert | nein |
| `standard` | versioniert, ohne CR änderbar | verbindlich für unallokierte | `warning` | CR empfohlen | nein |
| `extended` | Freigabegegenstand, eingefroren | verbindlich | `blocker` | CR-Pflicht (409) | ja (ArtifactVersion) |

Der Rigor wird ausschließlich vom CCB geändert (D17). Die Wirkung ist eine
Ableitung aus dem Preset, keine zweite Einstellung.

## 4. Fehlerbild nach Freigabe

```json
{
  "error": {
    "code": "ELEMENT_RELEASED",
    "message": "The architecture element is released; changes require a change request.",
    "details": [
      {
        "field": "element_id",
        "element_id": "…",
        "release_id": "…",
        "required_action": "create_change_request",
        "change_request_url": "/api/v1/change-requests/?scope=allocation&element_id=…"
      }
    ]
  }
}
```

- Immer **409**, nie 200 oder 500.
- Der Verweis ist ein ausführbarer Pfad, keine Fließtextbeschreibung.
- Auf `minimal`/`standard` entfällt der 409 für Inhaltsänderungen; Struktur-
  und Kantensperren gelten dort unverändert.

## 5. Impact-Vorschau

`GET /api/v1/architecture-elements/{id}/release-impact`

```json
{
  "element_id": "…",
  "requirements_total": 128,
  "requirements_by_status": {"draft": 120, "released": 8},
  "descendant_elements": 14,
  "baselines_affected": 3,
  "content_freeze": true,
  "conflicts": [
    {"requirement_id": "…", "kind": "multiple_allocations", "severity": "warning"}
  ],
  "async_required": false
}
```

Rein lesend, ohne Seiteneffekt; dieselbe Berechnung speist den Release-Pfad
(keine zweite Zählweise).

## 6. Baseline-Pin (D11, Stufe 4)

- Beim Release wird `tier_key` des Elements und der allozierten Requirements in
  den Release-Stand geschrieben.
- Der Baseline-Snapshot liest den **gepinnten** Wert, nicht den Live-Wert; nach
  einer Reallokation zeigt die Baseline weiterhin den damaligen `tier_key`.
- Der Audit meldet Abweichungen „Live ↔ Baseline" als eigenen Befund.

## 7. Migrationsplan der 890 Kanten

1. **Trockenlauf:** `manage.py backfill_allocations --dry-run` zählt Kanten,
   Dubletten und Fälle ohne Gegenstück; Bericht als Artefakt im PR.
2. **Backfill (idempotent):** je Kante `get_or_create` auf
   (`requirement_artifact_id`, `element_artifact_id`); Status `draft`, außer das
   Requirement ist im Freeze-Zustand → `released`.
3. **Invariante:** zweiter Lauf erzeugt keine neuen Zeilen (Test: gleiche
   Zeilenzahl).
4. **RLS:** eigene Policy-Migration nach dem Muster
   `0136_workspace_tier_rls_policy.py`.
5. **Rückfall:** Objekt-Tabelle löschen, Kanten bleiben unverändert (die Kante
   war vorher die Wahrheit).

## 8. Nicht-Ziele

- Keine automatische Auflösung von Mehrfachallokationen (D9).
- Kein Re-Design der ReqIF-Schnittstelle.
- Keine Änderung der Rigor-Presets selbst.
- Keine neue Entität „Spezifikation" (D4).
