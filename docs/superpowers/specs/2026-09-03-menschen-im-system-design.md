# Menschen im System — Design

**Status:** Draft, pending user review
**Quelle:** `docs/SYSTEMAUDIT_2026-09-02_GROB.md`, Kap. Q1.1 (dringendster Punkt im
gesamten Audit, "größter Nutzwert pro Aufwand"). Sechste von mehreren unabhängigen
Folge-Specs aus demselben Audit — siehe
[2026-09-03-attribute-definition-design.md](2026-09-03-attribute-definition-design.md),
[2026-09-03-traceability-semantik-design.md](2026-09-03-traceability-semantik-design.md),
[2026-09-03-ki-vorschlag-als-zustand-design.md](2026-09-03-ki-vorschlag-als-zustand-design.md).
**Scope:** Nicht Teil dieser Spec — bewusst, laut Audit selbst ein *anderes*, tieferes
Problem (Q2.5 "Der Workflow hat keine Menschen", nicht in der "dringend"-Liste Q1
enthalten): Zuweisung einer *bestimmten Person* pro Transition, Fristen, Eskalation,
Delegation. Diese Spec liefert die Minimalversion aus Q1.1 — Owner, Comments,
Notifications —, nicht die vollständige Personalisierung des Workflow-Systems.

## 1. Problem

Es gibt keine Comment-, Attachment-, Notification- oder Task-Entität. `owner` existiert
nur auf `Risk` — und selbst dort als **Freitext**-CharField, nicht als echte
User-Referenz (ein `owner_user`-FK existiert bereits daneben, REQ-L1-029, ausdrücklich als
"Expand phase of an expand/contract migration" kommentiert — nie zu Ende geführt). Auf
`Issue` gibt es nur `assignee_id` als lose `UUIDField`, **keine echte ForeignKey**. Alle
anderen 8 Typen (Requirement, StakeholderNeed, ArchitectureElement, TestCase, Adr, Goal,
Icd, GlossaryTerm) haben überhaupt keinen Verantwortlichen. Ein Workflow mit
Signature-Gates existiert, aber niemand erfährt, dass er unterschreiben soll. Eine
Review-Queue existiert, aber kein "warum abgelehnt" außer `change_reason`.

Requirements-Management ist laut Audit zu 60 % Kommunikation über das Requirement, nicht
das Requirement selbst — ohne Owner, Kommentare und Benachrichtigungen fehlt der SE-
Zielgruppe genau dieser Teil.

## 2. Ziel

1. **Zwei Rollen statt einer** — `owner` (verantwortlich, stabil) und `assignee` (aktuell
   zugewiesen, wechselt öfter) als echte User-Referenzen auf jedem der 10 Artefakttypen.
   Risk und Issue bekommen ihre bestehenden Baustellen (Freitext-`owner`, loses
   `assignee_id`) endlich zu Ende geführt, nicht als Sonderfälle liegen gelassen.
2. **`Comment`** als generisches, an `persistence.Artifact` hängendes Entity — funktioniert
   dadurch für alle 10 Typen ohne Sonderbehandlung.
3. **`Notification`** mit vier Auslösern: Workflow-Transition mit ausstehender
   Rollen-Aktion, Suspect-Markierung, Zuweisung, Kommentar auf eigenem Artefakt.
4. **Zuweisungs-Änderungen landen in der bestehenden `AuditEntry`-Historie** (Abschnitt
   3.3) — kein neuer Verlaufsmechanismus, Anschluss an ein bereits vorhandenes System.

## 3. Owner und Assignee — zwei Rollen, bestehende Migrationen zu Ende führen

**Warum zwei Felder:** `Risk.owner_user` (FMEA-Terminologie "Risk Owner", REQ-L1-029) ist
ein Verantwortlichkeits-Konzept — wer trägt die Verantwortung, unabhängig davon, wer
gerade daran arbeitet. `Issue.assignee_id` ist ein anderes Konzept — wer ist aktuell damit
beauftragt, es zu bearbeiten. Beide Konzepte existieren im Bestand bereits, nur je für
einen einzigen Typ und uneinheitlich benannt/implementiert. Diese Spec vereinheitlicht sie
als zwei getrennte, universelle Felder statt sie fälschlich zusammenzulegen.

```python
owner = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
assignee = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
```

**Risk:** die Contract-Phase der schon begonnenen Migration (REQ-L1-029) abschließen —
bestehende Freitext-`owner`-Werte, die sich einem echten `User` zuordnen lassen (Name-
Match), nach `owner_user` migrieren; nicht zuordenbare Werte bleiben als Datenqualitäts-
Befund im Migrationsreport (keine automatische Rate-Erfindung). Danach `owner`-CharField
entfernen, `owner_user` auf `owner` umbenennen. Risk bekommt zusätzlich das neue,
zunächst leere `assignee`-Feld.

**Issue:** `assignee_id` (lose `UUIDField`) wird zur echten `assignee`-FK — bestehende
UUIDs, die auf existierende User zeigen, werden übernommen; verwaiste UUIDs werden im
Migrationsreport vermerkt. Issue bekommt zusätzlich das neue, zunächst leere
`owner`-Feld. `due_date` (existiert bereits auf Issue) bleibt unverändert — kein Teil
dieser Spec, siehe Abschnitt 6.

**Die übrigen 8 Typen:** beide Felder neu, additiv, zunächst leer.

**Wo `assignee` keinen Sinn ergibt** (z. B. GlossaryTerm — ein Glossarbegriff hat einen
Verantwortlichen für die Definition, aber niemanden, der "gerade daran arbeitet"): über
die bereits vorhandene `visible`-Eigenschaft der Attribut-Definition ausblenden, kein
neuer Mechanismus — genau der Anwendungsfall, für den `visible` existiert.

**Kein Cross-Spec-Amendment nötig:** die Attribut-Definition-Spec (Abschnitt 3.2) leitet
ihre Kern-Attribut-Liste aus einer Introspektion der Django-Modellfelder ab — sobald
`owner`/`assignee` als echte Felder auf jeder Tabelle existieren, entdeckt deren
Bootstrap-Script sie automatisch als Kern-Attribute vom `type: user` (der Typ existiert
dort bereits als `UserPicker`-Feldkomponente). Reihenfolge: diese Migration muss vor dem
Attribut-Definition-Bootstrap laufen, sonst fehlen beide Felder in der ersten Kern-Liste
und müssen manuell nachgetragen werden.

### 3.3 Zuweisungs-Historie — Anschluss an die bestehende `AuditEntry`

`backend/audit/writer.py` (`AuditLogWriter`) ist Event-Bus-getrieben und append-only:
jeder `AuditableOperationOccurred`-Event erzeugt einen `AuditEntry` mit `actor`,
`actor_type` (user/agent), `op`, `entity_type`, `entity_id`, `timestamp`,
`change_reason` — laut Docstring "for all write operations". Es existiert bereits eine
Operations-Konstante `AuditEntry.OP_ASSIGN = "assign"`, die exakt für diesen Fall gedacht
ist, aber bisher von keinem Schreibpfad genutzt wird (kein Feld namens `owner`/`assignee`
existierte bisher, das sie auslösen könnte).

**Anforderung an diese Spec:** jeder `update_X()`-Servicepfad, der `owner` oder
`assignee` ändert, publiziert `AuditableOperationOccurred(op=AuditEntry.OP_ASSIGN, ...)`
zusätzlich zum normalen `OP_UPDATE`-Eintrag für die restlichen Feldänderungen — damit ist
"wer hat wann wen zugewiesen" ohne neuen Verlaufsmechanismus abgedeckt, rein durch
Anschluss an ein bereits vorhandenes, aber bisher ungenutztes System. Kein neues Modell,
keine neue Tabelle für diesen Teil.

**Für `Comment` selbst** ist die Frage "wer hat was gemacht" bereits im Modell beantwortet
(`author`, `resolved_by`, `resolved_at` aus Abschnitt 4) — Kommentare werden in dieser
Spec nicht editierbar (nur anlegen/auflösen), es gibt also keine "Kommentar-Änderungshistorie"
zu verfolgen.

## 4. `Comment`

```python
class Comment(TenantScopedModel):
    artifact = models.ForeignKey(Artifact, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="+")
    text = models.TextField()
    resolved = models.BooleanField(default=False)
    resolved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
```

Hängt am generischen `persistence.Artifact`, nicht an der spezialisierten Tabelle —
funktioniert dadurch für alle 10 Typen ohne Sonderfall, auch für Diagram/Icd/GlossaryTerm
nach deren Artifact-Backing (Datenmodell-Konsolidierung-Spec).

**REST:** `artifacts/<id>/comments/` (Liste, Anlegen), `comments/<id>/resolve/`,
`comments/<id>/` (Löschen — nur Autor oder Admin).
**MCP:** neue Tool-Gruppe `comment.*` (`create`, `list`, `resolve`).
**UI:** neuer Inspector-Reiter "Kommentare" im `ArtifactForm`-Renderer (Attribut-
Definition-Spec, Abschnitt 6) — neben den bestehenden Reitern Historie/Diff/Impact, ein
Ort statt sieben verschiedene Formulare, die ihn erst noch bräuchten.

## 5. `Notification`

```python
class Notification(TenantScopedModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notifications")
    kind = models.CharField(max_length=32, choices=[
        ("transition_pending", "Transition Pending"),
        ("suspect_flagged", "Suspect Flagged"),
        ("assigned", "Assigned"),
        ("comment_added", "Comment Added"),
    ])
    artifact = models.ForeignKey(Artifact, on_delete=models.CASCADE, null=True, related_name="+")
    message = models.TextField()
    read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
```

**Auslöser (die vier vom Audit benannten — Workflow-Transition und Review-Request fallen
beide unter `transition_pending`, Suspect-Markierung und Zuweisung je eigene Art —, plus
`comment_added` als naheliegende Ergänzung):**

1. **`transition_pending`:** ein Artefakt erreicht einen Zustand, dessen ausgehende
   Transition(en) eine bestimmte Rolle verlangen (`allowed_roles`) — jeder User im
   Workspace mit einer dieser Rollen bekommt eine Notification. Kein
   personenscharfes Routing (das wäre Q2.5, siehe Abschnitt 6) — Rollen-Broadcast reicht
   für die Minimalversion. Deckt auch den Fall aus der KI-Vorschlag-als-Zustand-Spec ab:
   ein Artefakt im Zustand `proposed` löst dieselbe Benachrichtigung aus wie jede andere
   Rollen-gebundene Transition — kein Sonderfall nötig, `proposed → draft`/`proposed →
   rejected` sind normale Transitionen mit `allowed_roles`.
2. **`suspect_flagged`:** wenn die Suspect-Propagation (Traceability-Semantik-Spec,
   Abschnitt 5) `suspect_flagged_at` auf einem `TraceLink` setzt, werden `owner` und
   `assignee` des betroffenen Artefakts benachrichtigt (jeweils sofern gesetzt).
3. **`assigned`:** `owner`- oder `assignee`-Feld (Abschnitt 3) wechselt auf einen neuen
   User → dieser wird benachrichtigt (trägt dieselbe `AuditableOperationOccurred(op=
   OP_ASSIGN)`-Publikation aus Abschnitt 3.3, ein Event, zwei Konsumenten: Audit-Log und
   Notification).
4. **`comment_added`:** ein neuer `Comment` auf einem Artefakt benachrichtigt `owner` und
   `assignee` (außer einer von beiden ist der Kommentar-Autor selbst).

**Kein Echtzeit-Push (WebSocket/SSE) in dieser Spec** — einfacher REST-Abruf beim Laden
der NavigationShell reicht für die Minimalversion, kein neuer Infrastruktur-Baustein.

**REST:** `notifications/` (Liste, eigene), `notifications/<id>/read/`,
`notifications/mark-all-read/`.
**MCP:** keine neue Tool-Gruppe — Notifications sind ein reines Menschen-Feature (Agenten
lesen keinen Benachrichtigungs-Center, sie handeln synchron über Tool-Calls).
**UI:** Glocken-Icon mit Ungelesen-Zähler in der `NavigationShell` (existiert heute nicht,
S3 im Audit listet den Fußblock ohne ein solches Icon) — Dropdown mit den letzten
Benachrichtigungen, Klick navigiert zum Artefakt.

## 6. Warum Zuweisung/Frist/Eskalation/Delegation bewusst ausgeklammert bleiben

Der Audit selbst trennt zwei Probleme: Q1.1 (diese Spec) ist die *fehlende* Minimalbasis
— Owner, Kommentare, Benachrichtigungen, mit "1 bis 2 Wochen" beziffert. Q2.5 ("Der
Workflow hat keine Menschen") ist eine *tiefere* Konzeptkritik — personenscharfe
Zuweisung pro Transition, Fristen, Eskalation, Delegation — die der Audit explizit unter
"Konzepte, die nicht weit genug gedacht sind" führt, nicht unter der dringenden
Q1-Liste. Diese Spec liefert bewusst nur Q1.1: Rollen-Broadcast statt personenscharfem
Routing, kein Fristen-Feld auf Transitionen, keine Eskalationslogik. Eine
Workflow-Personalisierungs-Spec (Q2.5) ist ein eigenständiges, größeres Thema für später.

## 7. Migration

Additiv bis auf die zwei Contract-Abschlüsse:

1. `owner`- und `assignee`-Felder auf den 8 Typen ohne beide (neu, additiv, beide leer).
2. Risk: Freitext-`owner` → `owner_user`-Migration abschließen, umbenennen, Altfeld
   entfernen (Datenqualitätsreport für nicht zuordenbare Werte); `assignee` neu, leer.
3. Issue: `assignee_id` → echte `assignee`-FK-Migration (gleiches Muster wie Risk);
   `owner` neu, leer.
4. Schreibpfade für `owner`/`assignee` publizieren `AuditableOperationOccurred(op=
   AuditEntry.OP_ASSIGN)` (Abschnitt 3.3).
5. `Comment`, `Notification` als neue Tabellen — kein Datenumbau bestehender Zeilen.

## 8. Risiken

- **Owner-/Assignee-Migration für Risk/Issue** betrifft Produktivdaten mit potenziell
  nicht eindeutig zuordenbaren Freitext-/UUID-Werten — der Migrationsreport (Punkt 2/3)
  muss vor dem Feld-Drop von einem Menschen geprüft werden, kein automatischer Blind-Merge.
- **`OP_ASSIGN`-Publikation ist neuer Code in bestehenden Services** (Punkt 4) — ein
  vergessener `update_X()`-Pfad lässt eine Zuweisungsänderung ohne Audit-Eintrag und ohne
  `assigned`-Notification durchrutschen. Ein gemeinsamer Helper (ähnlich dem in der
  KI-Vorschlag-als-Zustand-Spec geforderten `WorkflowInitializationService`) reduziert
  dieses Risiko, ist aber nicht Teil dieser Spec selbst zu bauen — Cross-Spec-Hinweis für
  die Implementierung.
- **`transition_pending`-Rollen-Broadcast** kann in Workspaces mit vielen Nutzern
  derselben Rolle zu Benachrichtigungs-Rauschen führen — akzeptierter Trade-off der
  Minimalversion, personenscharfes Routing ist Q2.5-Scope.
- **Kein Echtzeit-Push:** Notifications erscheinen erst beim nächsten Laden der
  NavigationShell, nicht sofort — für die Zielgruppe (Requirements-Arbeit, keine
  Chat-Anwendung) als ausreichend eingeschätzt, aber ein bewusster Kompromiss, kein
  Nullrisiko.
