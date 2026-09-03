# Rollenbasierte Sichten — Design

**Status:** Draft, pending user review
**Quelle:** `docs/SYSTEMAUDIT_2026-09-02_GROB.md`, Kap. T (Rollenbasierte Sicht, T1-T3).
Elfte und letzte von mehreren unabhängigen Folge-Specs aus demselben Audit.
**Verhältnis zu GitHub-Issue #848:** T1 (Viewer sieht alle Schreib-Buttons und
Admin-Navigation) ist bereits als P0-Bug gemeldet — der harte Minimalfix dort
(`NAV_ITEMS.requires`, `ArtifactForm.mode`, Buttons nicht rendern statt nur
deaktivieren) ist Teil dieser Spec, nicht separat davon; #848 wird durch die
Implementierung dieser Spec gelöst, keine doppelte Arbeit.
**Cross-Spec-Nachtrag:** die Attribut-Definition-Spec (Abschnitt 8) hat das Feld
`audience: basic | expert` bewusst ausgeklammert und auf diese Spec verwiesen — Abschnitt
4 hier liefert es nach.

## 1. Problem

Rollen (`roles`) liegen schon im Login-Response, aber die UI kennt sie nicht — sie zeigt
jedem alles und lässt den Server nein sagen (live bestätigt: Viewer-Login zeigt "+ Neue
Anforderung", Admin-Navigation, editierbare Felder; erst der Server lehnt ab). Zusätzlich
gibt es keine bewusste Unterscheidung zwischen dem, was ein normaler Bearbeiter braucht
(Titel, Beschreibung, Abnahmekriterien, Status, Links) und dem, was ein Experte zusätzlich
braucht (Typ, Ebene, Komplexität, Verifikationsmethode, Custom Fields,
Änderungsgrund-Historie, Diff, Suspect-Ursache) — jedes Formular zeigt beides gleich
dicht, für jeden.

## 2. Ziel

Drei Sichten statt einer Oberfläche, die alles zeigt und den Server filtern lässt:

| Sicht | Für wen | Rollen-Mapping |
|---|---|---|
| **Leser** | Stakeholder, Auditor, Kunde | `viewer` |
| **Autor** | Requirements Engineer, Entwickler | `editor` |
| **Experte** | Lead Engineer, Prozessverantwortlicher | `admin`, `approver` |

Kein neues Rollensystem — reine UX-Konsequenz der bereits existierenden Rollen
(Auth-Tenancy, keine Änderung an RBAC selbst).

## 3. Navigation und Formular-Modus

### 3.1 Navigations-Sichtbarkeit als Systemobjekt — zur Laufzeit anpassbar

Nicht als hartcodiertes `NAV_ITEMS.requires`-Array im Frontend-Quelltext, sondern als
fünftes Global/Workspace-Systemobjekt nach demselben Muster wie Attribut-Definition,
Workflow-Defaults und Link-Type-Definition dieser Spec-Reihe:

```python
class GlobalNavigationVisibility(TenantScopedModel):
    nav_item_key = models.CharField(max_length=64)   # z.B. "system-settings", "workflows"
    required_role = models.CharField(max_length=32, null=True, blank=True)  # "admin" | "editor" | None
    version = models.IntegerField(default=1)
    # unique(tenant, nav_item_key)

class WorkspaceNavigationVisibility(TenantScopedModel):
    workspace_id = models.UUIDField(db_index=True)
    nav_item_key = models.CharField(max_length=64)
    required_role = models.CharField(max_length=32, null=True, blank=True)
    source_global = models.ForeignKey(GlobalNavigationVisibility, on_delete=models.SET_NULL, null=True)
    is_customized = models.BooleanField(default=False)
    version = models.IntegerField(default=1)
    # unique(tenant, workspace_id, nav_item_key)
```

Materialized-Copy, dieselbe Cache-Invalidierung wie die anderen drei Systemobjekte. Die
26 heutigen Nav-Einträge sind der Bootstrap-Seed (`nav_item_key` fix aus dem
Frontend-Routing — welche **Seiten** existieren, ist Code, nicht Daten; welche **Rolle**
eine Seite sehen darf, ist ab jetzt Daten). Ein Tenant-Admin ändert
`required_role` über einen kleinen Editor (`/system-settings`, gleicher Shell wie die
anderen drei Editoren) **zur Laufzeit**, ohne Deploy — beantwortet den zweiten Teil des
Nutzer-Wunschs ("zur Laufzeit Anpassungen vornehmen können").

**REST:** `GET/PUT navigation-visibility-defaults/{nav_item_key}/` (global),
`GET/PUT workspaces/<id>/navigation-visibility/{nav_item_key}/` (Workspace-Override),
`GET workspaces/<id>/navigation-visibility/` (resolved, das liest das Frontend beim
Rendern der Sidebar).

**Frontend:** `NAV_ITEMS` verliert sein statisches `requires`-Feld, liest stattdessen
die aufgelöste `WorkspaceNavigationVisibility` beim Sidebar-Rendering. Ein Eintrag, den
die Rolle nicht sehen darf, wird **nicht gerendert** — kein CSS-Verstecken, kein
Deaktivieren. Löst T1/#848 auf Navigationsebene, jetzt datengetrieben statt hartcodiert.

### 3.2 Formular-Modus

- **`ArtifactForm`** (Attribut-Definition-Spec, Abschnitt 6) bekommt `mode: "read" |
  "edit"`, abgeleitet aus **Rolle UND Workflow-Zustand** — nicht nur Rolle: ein
  `approved`-Artefakt ist auch für Autor read-only, außer über eine explizite Transition
  (Statusänderung bleibt möglich, Direkt-Edit der Felder nicht). Buttons, die die Rolle
  in diesem Zustand nicht ausführen darf, werden nicht gerendert.
- **Leser-Navigation** beschränkt sich auf: Dashboard, Artefakte (read-only), Verknüpfungen,
  Baselines, Freigaben (nur eigene). Dokument-Lesemodus (Dokument-Sicht-Spec) ist der
  Default-Einstieg für diese Rolle, nicht das Split-View-Formular.
- **Leser-Aktionen:** keine Schreib-Buttons außer Kommentar (Menschen-im-System-Spec),
  Export, Impact-Analyse.

## 4. `audience`-Feld — echte Verbindung zur Attribut-Definition, nicht nur eine Referenz

Die Attribut-Definition-Spec ist um `audience: "basic" | "expert"` (Default `"basic"`)
in `definition_json.attributes[]` amendiert (dortige Abschnitte 3.1 und 6.1) — dieselbe
Datenstruktur, derselbe Editor, kein Parallelsystem. Konkret: der
`AttributeEditorPage`-Editor (Attribut-Definition-Spec, Abschnitt 6.1) bekommt pro
Attribut einen zusätzlichen Toggle "Nur für Experten", der `audience` setzt — genau wie
`required`/`visible`/`section` heute schon dort gesetzt werden. Das beantwortet den
ersten Teil des Nutzer-Wunschs ("sinnvoll verbinden"): `audience` ist kein separates
Feld dieser Spec, das die andere Spec nur zitiert, sondern ein natives Property
**derselben** Systemobjekt-Struktur, mit derselben Laufzeit-Editierbarkeit (kein Deploy,
Tenant-/Workspace-Admin ändert es direkt im Attribut-Editor).

**Wirkung:** Sektionen/Attribute mit `audience="expert"` sind standardmäßig **eingeklappt**
in `ArtifactForm` — nicht versteckt (das ist weiterhin `visible`, eine andere,
unveränderte Eigenschaft), nur kollabiert. Beispiel-Zuordnung passend zum Audit-Text:
"Allgemein" und "Verknüpfungen" bleiben immer offen (`audience="basic"`),
"Klassifikation", "Benutzerdefinierte Felder", "Änderungskontrolle" defaulten auf
eingeklappt (`audience="expert"`).

**Aufklapp-Logik:** eine Sektion mit `audience="expert"` ist aufgeklappt, wenn die Rolle
`admin`/`approver` ist **und** der Nutzer den Expertenmodus (Abschnitt 5) aktiviert hat.
Für die Rolle `viewer` (reine Lesesicht, siehe Abschnitt 3) ist die Kollaps-Frage
zweitrangig — der Dokument-Lesemodus ist ohnehin der Default-Einstieg, nicht das
Formular; öffnet ein Leser trotzdem das Formular, bleibt es wie für Autor eingeklappt,
kein Sonderfall nötig.

`audience` ist **keine Sicherheitsgrenze** — dieselbe Unterscheidung wie `tool_groups`
in der MCP-Modernisierung-Spec (Abschnitt 6.2): reine Darstellungsdichte, keine
Zugriffskontrolle. Ein Autor, der eine eingeklappte Sektion manuell aufklappt, sieht und
bearbeitet sie normal — `visible`/RBAC bleiben die tatsächlichen Zugriffsgrenzen.

## 5. Expertenmodus — User-Präferenz, kein Recht

Ein Umschalter in der Detailansicht, sichtbar nur für `admin`/`approver`-Rollen, der
`audience="expert"`-Sektionen standardmäßig aufklappt. Persistiert als einfaches
Boolean-Feld auf dem bestehenden User-Profil (`expert_mode_enabled`, additiv, default
`false`) — keine neue Tabelle, kein Rechte-Konzept dahinter. Der Schalter ändert nur, was
initial sichtbar ist, nicht was bearbeitbar ist.

## 6. REST/Frontend

`audience` reist mit der bestehenden Attribut-Definition-API mit (Attribut-Definition-
Spec, Abschnitt 5) — kein eigener Endpoint. Neu für Navigation (Abschnitt 3.1):
`navigation-visibility-defaults/*`, `workspaces/<id>/navigation-visibility/*`. Zusätzlich
`PATCH users/me/` (oder äquivalenter bestehender Profil-Endpoint) um
`expert_mode_enabled`.

**Frontend-Arbeiten:**
1. `NAV_ITEMS` liest `WorkspaceNavigationVisibility` statt eines hartcodierten
   `requires`-Felds (löst #848 auf Navigationsebene, jetzt laufzeit-konfigurierbar).
2. `ArtifactForm`/`mode`-Ableitung aus Rolle + Workflow-Zustand (löst #848 auf
   Formularebene — bleibt Code-Logik, keine Konfigurationsdaten, siehe Abschnitt 3.2).
3. `ArtifactForm`-Sektions-Rendering liest `audience` (aus der Attribut-Definition) und
   den Expertenmodus-Zustand für die initiale Aufklapp-Entscheidung.
4. Expertenmodus-Toggle in der Detailansicht (nur `admin`/`approver` sichtbar).
5. `AttributeEditorPage` (Attribut-Definition-Spec) bekommt den "Nur für Experten"-Toggle
   pro Attribut (Abschnitt 4). Neuer `NavigationVisibilityEditorPage`-Editor unter
   `/system-settings`/`/settings`, gleiche Shell wie die anderen drei Editoren dieser
   Spec-Reihe.

## 7. Migration

Additiv:

1. `audience`-Feld im `definition_json`-Schema der Attribut-Definition (Default
   `"basic"` für alle bestehenden Einträge — kein Verhaltensbruch, alles bleibt
   aufgeklappt, bis jemand bewusst `audience="expert"` auf einzelne Attribute setzt).
2. `GlobalNavigationVisibility`/`WorkspaceNavigationVisibility` als neue Tabellen,
   Bootstrap-Seed aus den 26 heutigen `NAV_ITEMS`-Einträgen und ihren heute im
   Frontend-Quelltext hartcodierten Rollenanforderungen (Ist-Zustand als Startwert
   übernommen, danach frei editierbar).
3. `expert_mode_enabled` auf dem User-Profil.
4. Kein Datenumbau bestehender Artefakte — reine Darstellungs-/Konfigurationslogik.

## 8. Risiken

- **`audience`-Zuordnung ist manuelle Kuration**, kein automatischer Vorschlag — ein
  Tenant-Admin muss für jeden Typ bewusst entscheiden, welche Sektionen `expert` sind.
  Ohne diese Pflege bleibt alles `basic` (sicherer Default, aber kein Mehrwert ohne
  Nacharbeit).
- **`GlobalNavigationVisibility`/`WorkspaceNavigationVisibility` sind kein Sicherheits-
  mechanismus** — ein Nav-Item ausblenden verhindert nicht den direkten URL-Aufruf der
  dahinterliegenden Route; das eigentliche Zugriffs-Gate bleibt die bestehende
  RBAC-Prüfung auf der Route/API selbst (wie heute schon). Ein falsch konfiguriertes
  `required_role` (z. B. versehentlich auf `null` gesetzt) macht einen Nav-Eintrag
  sichtbar, den der Server danach trotzdem ablehnt — UX-Fehler, kein Sicherheitsloch.
- **#848-Überschneidung:** wer #848 isoliert als reinen Bugfix implementiert, bevor
  diese Spec geplant wird, baut denselben Code zweimal — bei der Implementierungsplanung
  sollte #848 als bereits durch diese Spec abgedeckt geschlossen werden, nicht separat
  bearbeitet.
- **Expertenmodus als reine UI-Präferenz** kann fälschlich als Berechtigungsstufe
  missverstanden werden (ähnliches Risiko wie bei `tool_groups`, MCP-Modernisierung-Spec)
  — Dokumentation/UI-Copy muss klarstellen: der Schalter zeigt mehr, gibt aber keine
  zusätzlichen Rechte.
