# Design: Admin- & Self-Service-UI für das AI-Memory-Feature

**Datum:** 2026-08-26
**Status:** Entwurf — wartet auf Review
**Vorgänger-Feature:** `docs/superpowers/plans/2026-08-24-ai-memory-and-search.md` (gemergt, `feat/ai-memory-and-search`)

## Kontext

Das AI-Memory-Feature (Two-Tier: Workspace-Memory + User-Tenant-Memory) hat aktuell
genau eine UI-Oberfläche: einen Enable/Disable-Toggle pro Workspace
(`frontend/src/components/WorkspaceSettings/MemorySettingsSection.tsx`). Es gibt
keine Möglichkeit,

- den Zustand des Feature systemweit zu prüfen (Verbindungstest Embedding-Provider/
  Memory-Backend),
- Provider-/Backend-Konfiguration zur Laufzeit zu ändern (`SystemMemorySettingsView.put()`
  antwortet aktuell hart mit `501 NOT_IMPLEMENTED` — env-only per Design-Entscheidung des
  Vorgänger-Features),
- zu sehen, in welchen Workspaces Memory aktiv ist und wie viel dort gespeichert ist,
- Memory-Einträge (Workspace- oder User-Tenant-Ebene) gezielt zu löschen,
- den Inhalt des Memory visuell zu inspizieren (Liste, Cluster, Embedding-Landschaft),
- als einzelner Nutzer das eigene User-Tenant-Memory selbst einzusehen oder zu löschen.

Dieses Dokument spezifiziert alle sechs Punkte als ein zusammenhängendes Vorhaben,
mit einer festgelegten Bau-Reihenfolge. Jede Phase bekommt in der Umsetzung einen
eigenen Implementierungsplan (`writing-plans`); dieses Spec-Dokument ist die
gemeinsame Grundlage für alle Phasen.

## Ziele / Erfolgskriterien

- Ein System-Admin kann ohne DB-Zugriff feststellen: läuft Memory technisch (Provider/
  Backend erreichbar), wo ist es aktiv, wie viel liegt dort, und kann gezielt eingreifen
  (Konfiguration ändern, Daten löschen).
- Ein einzelner Nutzer kann sein eigenes User-Tenant-Memory selbst einsehen und löschen,
  ohne einen Admin bitten zu müssen (DSGVO-Auskunfts-/Lösch-Charakter, auch wenn dieses
  Spec keine formale Compliance-Prüfung ist).
- Bestehende Sicherheits-/Tenant-Isolationsmuster werden wiederverwendet, nicht neu
  erfunden (RLS via `_tenant_context()`, Secret-Verschlüsselung via
  `FIELD_ENCRYPTION_KEY`, `HasOperationPermission` + `_is_system_admin()`-Gate).

## Nicht-Ziele (bewusst außerhalb des Scopes)

- Keine Änderung an der Konsolidierungs-Logik (`memory/projector.py`, `memory/tasks.py`).
- Keine automatische Re-Embedding-Pipeline bei Provider-Wechsel — der Admin wird gewarnt,
  eine Re-Indexierung ist manuell (separates, zukünftiges Ticket, siehe "Offene Fragen").
- Kein Undo für gelöschte Memory-Einträge (harte Löschung, wie bei bestehenden
  Löschfunktionen im Projekt üblich, z.B. `issue.delete`).
- UMAP/t-SNE oder andere nicht-lineare Projektionen — v1 nutzt PCA (siehe Abschnitt
  Visualisierung).

## Bau-Reihenfolge (5 Phasen — Punkt "User sieht/löscht" oben als Phase 4 gezählt)

1. **Phase 1 — Workspace-Übersicht + Löschen (Admin)**
2. **Phase 2 — Health-Check-Erweiterung (SystemHealthDialog)**
3. **Phase 3 — System-Settings-Override (Provider/Backend/Verbindungen + Reset)**
4. **Phase 4 — User-Self-Service (eigenes Memory sehen/löschen)**
5. **Phase 5 — Visualisierung (Liste + Cluster + PCA-Scatter, Workspace + global)**

Reihenfolge-Begründung: 1+2 sind lesend/klein und liefern sofort sichtbaren Nutzen.
3 ist die riskanteste Änderung (Secrets, Provider-Wechsel-Warnung) und kommt danach,
wenn das Übersichts-Fundament (Phase 1) schon steht. 4 teilt sich das Datenmodell mit
Phase 1 (gleiche Query-Bausteine, andere Autorisierung). 5 ist die aufwändigste UI und
baut auf den Daten aus Phase 1/4 auf.

---

## Phase 1 — Workspace-Übersicht + Löschen (Admin)

**UI:** Neuer Tab "Memory" in `SystemSettings.tsx` (4. Tab neben administration/
workflow-defaults/permission-defaults). Tabelle mit einer Zeile pro Workspace:

| Spalte | Quelle |
|---|---|
| Workspace-Name | `Workspace.name` |
| Memory aktiv? | `WorkspaceMemorySettings.enabled` |
| Einträge gesamt | `COUNT(WorkspaceMemory)` + `COUNT(UserTenantMemory)` je Tenant der Workspace-Mitglieder |
| Tier-Aufteilung | Workspace-Memory-Anzahl vs. User-Tenant-Memory-Anzahl (letzteres nur für Nutzer, die Mitglied dieses Workspace sind) |
| Letzte Konsolidierung | `MAX(WorkspaceMemory.updated_at)` |
| Embedding-Provider/Dimension | aus dem zuletzt geschriebenen Eintrag (`EmbeddingProvider`-Metadatenfeld, siehe Vorgänger-Feature) |

Pro Zeile: Aktionsbutton "Memory löschen" → Bestätigungsdialog mit Anzahl betroffener
Einträge, löscht **beide Tiers**: alle `WorkspaceMemory`-Zeilen dieses Workspace UND
alle `UserTenantMemory`-Zeilen der Nutzer, die (aktuell) Mitglied dieses Workspace sind.
Der Bestätigungsdialog listet explizit, wie viele Einträge pro Tier betroffen sind,
damit der Admin die User-Tenant-Löschung nicht versehentlich mitreißt ohne es zu sehen.

**API (neu):**
- `GET /api/v1/system/memory/workspaces/` — System-Admin only, paginierte Liste
  obiger Tabelle.
- `DELETE /api/v1/system/memory/workspaces/{workspace_id}/` — löscht beide Tiers wie
  oben beschrieben, gibt die gelöschte Anzahl je Tier zurück.

**Backend:** neuer `MemoryAdminService` (Layer 2, `application/`) — Single-Entry-Point
für beide Endpoints, nutzt `_tenant_context()` aus `memory/backends.py` für die RLS-
korrekte Query pro Tenant (ein Workspace kann nur zu genau einem Tenant gehören,
aber die Nutzerliste muss über `UserRole`/`WorkspaceMembership` aufgelöst werden —
existierendes Muster aus `WorkspaceAdminSection`/`workspace_service.py` wiederverwenden).

---

## Phase 2 — Health-Check-Erweiterung

**Wo:** `backend/admin_ops/health_rest.py`, zwei neue Check-Funktionen nach dem
Muster von `_check_llm_provider()`:

```python
def _check_memory_embedding() -> dict[str, str]:
    # ruft EmbeddingProvider.embed(["ping"]) auf, prüft Antwortdimension
    ...

def _check_memory_backend() -> dict[str, str]:
    # ruft MemoryBackend-Health-Methode auf (pgvector: SELECT 1 gegen die Tabelle;
    # Honcho: einfacher API-Ping)
    ...
```

Beide werden in `get_system_health()`s Liste ergänzt (`_check_database()`,
`_check_redis()`, ... , `_check_memory_embedding()`, `_check_memory_backend()`).
Kein neuer Dialog, kein neuer Button — die zwei Zeilen erscheinen automatisch im
bestehenden `SystemHealthDialog.tsx` (Frontend braucht nur die `STATUS_COLORS`-Map,
die schon generisch über `name`/`status` iteriert — falls die Komponente die Liste
hart codiert statt zu iterieren, muss das an dieser Stelle korrigiert werden, siehe
Prüfpunkt in der Implementierung).

`MemoryBackend` (ABC in `memory/backends.py`) bekommt eine neue abstrakte Methode
`health_check() -> tuple[bool, str]`, implementiert in `PgvectorMemoryBackend` und
`HonchoMemoryBackend`.

---

## Phase 3 — System-Settings-Override

**Datenmodell (neu, `memory/models.py`):**

```python
class SystemMemorySettings(models.Model):
    """Singleton (id=1 erzwungen wie andere System-weite Settings-Modelle)."""
    embedding_provider = models.CharField(max_length=32, null=True, blank=True)
    embedding_model_name = models.CharField(max_length=128, null=True, blank=True)
    ollama_base_url = models.CharField(max_length=255, null=True, blank=True)
    embedding_timeout = models.PositiveIntegerField(null=True, blank=True)
    memory_backend = models.CharField(max_length=32, null=True, blank=True)
    honcho_base_url = models.CharField(max_length=255, null=True, blank=True)
    honcho_api_key = EncryptedTextField(null=True, blank=True)  # FIELD_ENCRYPTION_KEY, wie LlmSettings.api_key
```

`NULL` in einem Feld bedeutet "kein Override — ENV gilt". Ein Reset auf Default
setzt exakt dieses Feld (oder alle Felder) zurück auf `NULL` — kein separates
Lösch-Endpoint für die Row nötig, `PUT` mit `null`-Werten reicht semantisch, wird
aber zusätzlich als eigener `POST .../reset/`-Endpoint angeboten, damit das Frontend
einen einzelnen "Auf Standard zurücksetzen"-Button anbieten kann ohne den ganzen
Formularzustand zu kennen.

**Lese-Reihenfolge (wichtig, betrifft `embedding_service.py`, `memory/backends.py`):**
`SystemMemorySettings`-Override (falls gesetzt) → sonst `os.environ.get(...)` wie
bisher. Diese Stelle ist die einzige, die angefasst werden muss — der Rest des
Embedding-/Backend-Codes bleibt unverändert, da beide Provider-Factories schon eine
einzige Konfigurationsquelle (`get_provider(name, **kwargs)`) haben.

**API:**
- `GET /api/v1/system/memory-settings/` — bestehender Endpoint, erweitert um
  `is_override: bool` je Feld (damit das Frontend zeigen kann, was vom Default
  abweicht).
- `PUT /api/v1/system/memory-settings/` — jetzt echt implementiert statt `501`.
  Bei Änderung von `embedding_provider` oder `memory_backend`: Response enthält
  `"warning": "..."`-Feld (kein Hard-Block), das Frontend zeigt einen
  Bestätigungsdialog ("Bestehende Embeddings werden inkompatibel. Re-Indexierung
  ist manuell nötig.") BEVOR der PUT abgeschickt wird.
- `POST /api/v1/system/memory-settings/reset/` — setzt alle Felder auf `NULL`.

**Sicherheit:** `honcho_api_key` wird in GET-Responses nie im Klartext zurückgegeben
(nur `"is_set": true/false`, gleiches Muster wie `LlmSettingsView` für `api_key`).

---

## Phase 4 — User-Self-Service

**Wo:** `frontend/src/components/UserProfileSettings/`, neue `MemorySection.tsx`
nach dem Muster von `ApiKeysSection.tsx`, eingebunden in `UserProfileSettings.tsx`
neben `ProfileSection`/`ApiKeysSection`.

Zeigt: Anzahl eigener `UserTenantMemory`-Einträge, letzte Aktualisierung, Button
"Mein Memory löschen" mit Bestätigung (löscht ausschließlich die eigenen
`UserTenantMemory`-Zeilen des eingeloggten Nutzers — nie Workspace-Memory, das ist
nicht Eigentum eines einzelnen Nutzers).

**API (neu):**
- `GET /api/v1/memory/me/` — eigene `UserTenantMemory`-Übersicht (kein Admin-Gate,
  nur normale Auth, filtert implizit auf `request.user`).
- `DELETE /api/v1/memory/me/` — löscht alle eigenen `UserTenantMemory`-Einträge.

Kein neuer Service nötig — dünner View, der direkt auf das bestehende
`MemoryBackend`/Model filtert (analog zu bestehenden "eigene Daten"-Endpoints wie
`ApiKeysSection`s Backing-View).

---

## Phase 5 — Visualisierung

**UI:** Neuer Abschnitt im "Memory"-Tab (SystemSettings) mit Scope-Umschalter
("Dieser Workspace" / "Global") und drei Ansichten:

1. **Liste** — Text-Snippet, Timestamp, Tags, Volltext-Filter (paginiert).
2. **Cluster** — Einträge nach Cosine-Similarity gruppiert (Threshold-basiert,
   Server-seitig vorberechnet, kein Live-Clustering im Client).
3. **2D-Scatter** — PCA-Projektion der Embedding-Vektoren auf 2 Dimensionen.
   Technik: reines `numpy` (SVD-basierte PCA, ~10 Zeilen Code), **kein** neuer
   Dependency — `numpy` kommt bereits transitiv über `sentence-transformers`/`torch`
   mit. Kein UMAP/scikit-learn (zusätzlicher schwerer Dependency, unnötig in der
   ressourcenknappen Docker-Umgebung).

**API (neu):**
- `GET /api/v1/system/memory/entries/?scope=workspace&workspace_id=...` bzw.
  `?scope=global` — paginierte Liste für Ansicht 1.
- `GET /api/v1/system/memory/projection/?scope=...` — vorberechnete `[{id, x, y,
  cluster_id}]`-Liste für Ansicht 2+3. Ergebnis wird pro Scope + Datenstand gecacht
  (Redis, kurze TTL) — PCA über alle Einträge neu zu berechnen ist bei jedem
  Seitenaufruf zu teuer.

**Grenze:** Bei sehr großen Workspaces (>5000 Einträge) wird die Projektion auf eine
Stichprobe begrenzt (deterministisch, z.B. jeden n-ten Eintrag) — im UI sichtbar
vermerkt ("Stichprobe von N/Gesamt"), damit "alles abgedeckt" nicht stillschweigend
vorgetäuscht wird.

---

## Offene Fragen (für die Implementierung, nicht blockierend für dieses Spec)

- Automatische Re-Indexierung nach Provider-Wechsel (Phase 3) ist bewusst außerhalb
  des Scopes — als Folge-Ticket vormerken, falls gewünscht.
- Rollen-Frage für Phase 1: reicht `_is_system_admin()` (wie beim bestehenden
  `SystemMemorySettingsView`), oder soll es eine feinere Berechtigung geben
  (z.B. nur lesen vs. löschen dürfen)? Default-Annahme: gleiche Gate wie bestehende
  System-Settings-Endpoints, keine neue Rolle.

## Testing (je Phase)

- Backend: Unit-Tests je neuem Service/View (RLS-Isolation zwischen Tenants ist
  Pflichtfall, analog zu den Tests im Vorgänger-Feature).
- Frontend: Component-Tests je neuer Section/Tab (`*.test.tsx`, bestehendes Muster).
- Phase 3 explizit: Test, dass ein DB-Override tatsächlich Vorrang vor ENV hat, und
  dass Reset zuverlässig auf ENV zurückfällt.
- Phase 5 explizit: Test der PCA-Projektion mit einer kleinen synthetischen
  Embedding-Menge (deterministisches Ergebnis, kein Snapshot-Test auf exakte
  Koordinaten wegen SVD-Vorzeichen-Mehrdeutigkeit — nur Cluster-Zusammengehörigkeit
  prüfen).
