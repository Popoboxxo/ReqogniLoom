# AI summaries — operations guide

Betriebsdoku für die beiden Zusammenfassungs-Flächen aus #1792 und #1793
(Implementierungsplan: `docs/superpowers/plans/2026-11-15-ai-summaries-implementation.md`,
Spec: `docs/superpowers/specs/2026-11-14-ai-artifact-summaries-design.md`).

Es gibt **drei** verwandte, aber getrennte Dinge:

| | `include_summary` (#18) | Einzel-Summary (#1792) | Typ-Summary (#1793) |
|---|---|---|---|
| Auslöser | Suchanfrage | Nutzer/Agent auf **einem** Artefakt | Celery-Beat (periodisch) + manueller Refresh |
| Persistenz | nur Cache | nur Cache | Tabelle `ArtifactSummary`, **ein** Stand je `(workspace, artifact_type)` |
| Kosten | 1 Call/Request | 1 Call/Aufruf | 1 Call je fälligem `(Workspace, Typ)` |
| Sichtbar | Suchtreffer-Kopf | Inspector → Tab „Summary" | Inspector → Tab „Summary" → Block „Überblick" |

Jeder Provider-Call ist **bezahlt**. Deshalb ist alles, was einen Call auslösen kann,
standardmäßig aus.

---

## 1. Schalter

| Env-Variable | Default | Bedeutung |
|---|---|---|
| `ARTIFACT_SUMMARY_ENABLED` | `false` | Erlaubt **jeden** Summary-Call — den manuellen Refresh im Inspector und den MCP-Pfad `summary.refresh`. Ohne dieses Flag antwortet die API mit `outcome="skipped:flag_off"` und ohne Provider-Call. |
| `ARTIFACT_SUMMARY_SWEEP_ENABLED` | `false` | Erlaubt den **periodischen** Sweep. Bewusst unabhängig vom obigen Flag: „darf das unattended passieren" vs. „darf das überhaupt passieren". Ein alter Beat-Eintrag aus einem früheren Deployment feuert weiter, der Task liest das Flag deshalb bei jedem Lauf neu. |
| `ARTIFACT_SUMMARY_TICK_MINUTES` | `60` | Takt des Beat-Eintrags. Werte unter `ARTIFACT_SUMMARY_MIN_INTERVAL_MINUTES` werden geklemmt, `0` schaltet den Beat-Eintrag ab. |
| `ARTIFACT_SUMMARY_INTERVAL_MINUTES` | `1440` | Default-Nachfrisch-Intervall je Workspace (siehe `summary_sweep_interval_minutes`). |
| `ARTIFACT_SUMMARY_MIN_INTERVAL_MINUTES` | `60` | Untergrenze für jedes Workspace-Intervall und den Beat-Takt. Wird geklemmt, nicht abgelehnt. |
| `ARTIFACT_SUMMARY_SWEEP_BATCH` | `25` | Deckel **pro Tenant-Lauf** (global, nicht je Workspace). Sortierung: „nie zusammengefasst zuerst, dann ältester Stand". |
| `ARTIFACT_SUMMARY_AGENT_KEY_ID` | leer | UUID eines aktiven Agent-API-Keys (`principal_type=agent`). Ohne gültigen Key läuft weder Sweep noch Refresh (`skipped:no_agent_key`) — ein automatischer Lauf schreibt nie unter einer echten Nutzeridentität. |
| `ARTIFACT_SUMMARY_MIN_INTERVAL_SECONDS` | `3600` | Throttle **vor** dem Call: derselbe `(Workspace, Typ)` läuft höchstens einmal pro Fenster. Der Cache-Eintrag wird vor dem Call gesetzt und bei Fehlern gelöscht, damit ein hängender Provider keinen zweiten Lauf parallel startet. |
| `SUMMARY_DAILY_TOKEN_LIMIT` | `200000` | Summary-eigenes Tagesbudget je Tenant (`0`/leer = aus). **Unabhängig** von `TENANT_TOKEN_LIMIT_PER_DAY`; ein Sweep darf das Budget anderer KI-Flows weder auffressen noch von ihm blockiert werden. |
| `ARTIFACT_SUMMARY_RATE` | `60/hour` | DRF-Throttle-Scope `artifact_summary` für die bezahlenden Endpunkte (Einzel-Summary, Typ-Refresh). Leer fällt auf `60/hour` zurück, nie auf „unbegrenzt". |
| `SUMMARY_MAX_NEIGHBOURS` | `20` | Obergrenze der Trace-Nachbarn im Einzel-Summary-Prompt. |
| `SUMMARY_MAX_CHARS_PER_NEIGHBOR` | `300` | Zeichenobergrenze je Nachbar. |
| `SUMMARY_MAX_CHARS_PER_SECTION` | `1500` | Zeichenobergrenze je Prompt-Abschnitt. |
| `SUMMARY_SYNC_TIMEOUT_SECONDS` | `20` | Timeout des synchronen Provider-Calls. |
| `SUMMARY_CACHE_TTL_SECONDS` | `3600` | Cache-TTL der Einzel-Summary (#1792). Die Typ-Summary wird nicht gecacht, sie steht in der Tabelle. |

Die Reihenfolge der Bremsen ist fest: **Flag → eigenes Tagesbudget → Batch-Deckel →
Agent-Key → Throttle**. Jede Bremse greift vor dem Provider-Call.

Templates für `.env` stehen in `.env.example` (Abschnitt „ARTIFACT_SUMMARY_*").

## 2. Workspace-Felder

Drei Spalten auf `Workspace` steuern den Sweep je Workspace. Sie sind **nicht** über
REST/MCP editierbar; gesetzt werden sie im Django-Admin oder per Shell
(`Workspace.objects.filter(...).update(...)`), wie die übrigen Betriebsfelder.

| Feld | Default | Bedeutung |
|---|---|---|
| `summary_sweep_interval_minutes` | `1440` | Nachfrisch-Intervall. `0` = für diesen Workspace aus. Positive Werte unter `ARTIFACT_SUMMARY_MIN_INTERVAL_MINUTES` werden geklemmt. |
| `summary_scopes` | `[]` | JSON-Liste der zu summarisierenden Artefakttypen. Leer = die zwölf Defaults (`Requirement`, `StakeholderNeed`, `ArchitectureElement`, `TestCase`, `Adr`, `Risk`, `Issue`, `ChangeRequest`, `Goal`, `Document`, `WorkItem`, `Icd`). Unbekannte Typnamen werden mit Warnung ignoriert — ein Tippfehler darf keinen Prompt-Müll erzeugen. |
| `summary_trace_depth` | `1` | Trace-Tiefe für Einzel-Summaries, `1` oder `2` (DB-Constraint). |

## 3. Takt und Kosten

Beispielrechnung aus der Spec (§6.4): 10 Workspaces × 12 Typen × 1 Call/Tag = 120 Calls/Tag,
bei je ca. 2 000 Eingabe- und 400 Ausgabe-Token ≈ **290 k Token/Tag**. Ein einzelner Workspace
mit Takt `60` Minuten erzeugt dagegen 12 × 24 = **288 Calls/Tag** (~690 k Token/Tag) — genau
deshalb ist der Takt eine Betriebsentscheidung und der Batch-Deckel global.

Ein Lauf, der nichts Neues findet, kostet **nichts**: der Content-Hash über die sortierte
Roster (`artifact_id`, `content_hash`, `updated_at`) plus Prompt, Provider und Sprache ist
gleich → `skipped:unchanged`, kein Call, und `updated_at` bleibt unverändert (kein falsches
„Stand: jetzt").

## 4. Stale-Verhalten

- Ein `ok`-Stand gilt als **stale**, wenn `generated_at < now − 2 × Workspace-Intervall`.
- Ist der Sweep aus (globales Flag aus **oder** Workspace-Intervall `0`), gilt **jeder**
  gespeicherte Stand als stale. Das ist Absicht: ein abgeschalteter Sweep darf einen alternden
  Text nicht als aktuell präsentieren.
- Die API liefert das als `stale: true` **und** `reason: "stale"`; der Inspector zeigt beides
  (Badge „Veraltet" plus Begründungssatz), nie nur ein Badge ohne Grund.
- Das Degradations-Vokabular ist geschlossen: `budget_exhausted | provider_unavailable | stale |
  disabled`. Kein Freitext in der Antwort (CWE-209); die feinere Ursache (Mock, Timeout, kein
  Provider) bleibt im Log.

## 5. Audit

Jeder **bezahlte** Lauf schreibt genau **einen** Audit-Eintrag
(`op = artifact_summary.generate`, `entity_type = ArtifactSummary`, `entity_id` = Zeile des
Stands). Details: `workspace_id`, `artifact_type`, `item_count`, `provider`, `trigger`
(`periodic`/`manual`), `token_usage` — **kein** generierter Text und keine Artefakt-Titel.

Kein Eintrag entsteht bei Cache-Hit, `skipped:unchanged`, leerem Typ, ausgeschaltetem Flag,
erschöpftem Budget, fehlendem Agent-Key oder Throttle: dort wurde nichts bezahlt.

## 6. UI-Sichtbarkeit

Inspector → Tab „Summary" → Block „Überblick" zeigt den gespeicherten **Typ-Stand** des
Workspace (Text, Anzahl Artefakte, „Stand vom …", ggf. stale/Reason). Der Block ist read-only
und kostenlos (ein GET auf `/api/v1/workspaces/{id}/summaries/<artifact_type>/`).

Der Button „Typ-Zusammenfassung aktualisieren" erscheint nur für Rollen mit Schreibrecht
(`editor`/`admin`) und ruft `POST .../summaries/<artifact_type>/refresh/`. Der Refresh umgeht
den Workspace-Takt (das ist sein Zweck), aber **keine** der übrigen Bremsen; ein abgelehnter
Lauf antwortet weiter mit 200 und `outcome="skipped:<reason>"`.

Typen ohne Roster (`diagram`, `glossary`, `mainGoal`) haben keinen Typ-Stand — der Block
rendert für sie nichts.

## 7. Prune: nur Waisen und veraltete Stände, manuell

Es gibt **kein** `manage.py`-Kommando und keinen Celery-Task zum Aufräumen von
`ArtifactSummary`. Bewusste Entscheidung (S8, Plan-Akzeptanzkriterium 6): die Tabelle ist klein
(ein Stand je `(workspace, artifact_type)`), und ein automatischer Löschlauf auf einem
Kosten-/Audit-Artefakt ist riskanter als der Platzgewinn.

Manuell zu entfernen sind zwei Klassen:

1. **Waisen im Artifact-Scope** (`summary_kind='artifact'`, `artifact` zeigt auf ein gelöschtes
   Artefakt bzw. ist `NULL`). Der partielle Unique-Constraint `uq_artifact_summary_artifact`
   behandelt `NULL` als distinct (PostgreSQL-Semantik), d. h. mehrere `NULL`-Zeilen kollidieren
   nicht — sie müssen aktiv weggeräumt werden.
2. **Typ-Stände außerhalb von `summary_scopes`** (z. B. nach einer Umstellung der Typ-Liste):
   sie werden nie wieder nachgefrischt und laufen in „stale". Achtung: eine **leere** Liste
   bedeutet „die zwölf Defaults", nicht „keine Typen".

Es gibt dafür **kein** fertiges Kommando. Der Weg ist bewusst manuell: erst ansehen, dann
gezielt löschen — im Django-Admin oder per Shell.

```python
# im backend-Container: python manage.py shell
from persistence.models import ArtifactSummary, Workspace

# 1) Waisen im Artifact-Scope ansehen (nichts löschen, nur prüfen)
ArtifactSummary.objects.filter(summary_kind="artifact", artifact__isnull=True).values(
    "id", "workspace_id", "updated_at"
)

# 2) Typ-Stände ansehen, deren Typ im Workspace nicht (mehr) konfiguriert ist.
#    Workspaces mit leerer Liste nutzen die Defaults und sind hier NICHT betroffen.
for row in ArtifactSummary.objects.filter(summary_kind="type_roster"):
    workspace = Workspace.objects.filter(id=row.workspace_id).first()
    scopes = list(getattr(workspace, "summary_scopes", []) or [])
    if scopes and row.artifact_type not in scopes:
        print(row.id, workspace.id, row.artifact_type, row.updated_at)

# 3) Erst nach Sichtprüfung gezielt löschen — mit den IDs aus Schritt 1/2
ArtifactSummary.objects.filter(id__in=[...]).delete()
```

Vor dem Löschen prüfen, ob der Stand nicht gerade als Nachweis gebraucht wird — es gibt keine
Historie: die Tabelle ist ein Upsert-Stand, kein Append-Only-Log (der Audit-Trail bleibt
davon unberührt).

## 8. Betriebs-Checkliste

1. `ARTIFACT_SUMMARY_ENABLED=true` setzen, wenn Nutzer/Agenten Zusammenfassungen auslösen dürfen.
2. Agent-API-Key erzeugen (`principal_type=agent`, Rolle `editor` im Ziel-Workspace) und als
   `ARTIFACT_SUMMARY_AGENT_KEY_ID` eintragen.
3. `ARTIFACT_SUMMARY_SWEEP_ENABLED=true` **nur** mit gesetztem `SUMMARY_DAILY_TOKEN_LIMIT` und
   geprüftem `ARTIFACT_SUMMARY_SWEEP_BATCH`.
4. Beat-Takt (`ARTIFACT_SUMMARY_TICK_MINUTES`) gegen die Workspace-Intervalle rechnen — der
   Deckel pro Tenant-Lauf ist die wirksame Obergrenze.
5. Nach dem ersten Lauf im Audit-Log (`artifact_summary.generate`) die Call-Zahl gegen die
   Erwartung prüfen; `skipped:*`-Gründe stehen im Task-Ergebnis, nicht im Audit.
