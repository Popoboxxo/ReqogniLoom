# Testplan v1.8.0-beta.17

> **Geltungsbereich: interner Pre-Release.** Dieser Testplan prüft den
> Schnitt, nicht die Produktionsreife. Zwei Punkte aus dem
> Release-Bericht sind hier als **nicht erfüllbar** geführt und nicht als
> bestanden zu werten: W5 (#50) ist nicht entschieden, und die
> ADR-006-Feldkinds wandern auf Altinstanzen nicht mit (siehe 5.4).

## 1. Ziel & Prüfgegenstand

Geprüft wird das Delta `1.8.0-beta.16` → `1.8.0-beta.17`, also der
QA-Sweep (PR #1105) und die Entscheidungswellen W1–W4 (PR #1111).

### 1.1 Im Scope

- W1: `Requirement.level` server-seitig abgeleitet, read-only
- W2: `Artifact.stakeholder` als Mehrfachauswahl, `Adr.deciders` und
  `Issue.assignee` als Actor-Beziehungen, `origin_link` entfernt
- W3: Regel-Vokabular der vier `REQ_MUST_HAVE_*`-Regeln, Durchsetzung am
  Baseline-Gate
- W4: Benachrichtigungen im Assistenten statt Sidebar-Glocke
- QA-Sweep: Foreign-Workspace `403`, einheitliches Error-Envelope,
  TraceLink-Subtypen, fail-closed Deploy, reviewbare KI-Ableitungen

### 1.2 Nicht im Scope

- W5 (Baseline-Rollback additiv/CCB) — nicht entschieden
- Produktions-, Staging- oder QA-Reife
- Migration von Altinstanzen (siehe 5.4)
- MCP-Oberflächen-Vollständigkeit über `test.run_list` hinaus

## 2. Vorbedingungen (exakt)

### 2.1 Source-Checkout, nicht Image

Es existiert kein Image `1.8.0-beta.17`. Der Stack wird aus dem
Source-Checkout dieses Branches gestartet:

```
# Source-Checkout-Pfad - zwingend, da kein Image 1.8.0-beta.17 existiert
make up
```

### 2.2 Health-Check

```
# /health/ ist der kanonische Endpunkt. /api/v1/health/ antwortet 404 -
# das ist kein Fehler, siehe 6.1.
curl http://127.0.0.1:8001/health/
```

Erwartet: HTTP 200.

### 2.3 Seed

```
docker compose -f deploy/docker-compose.yml -f deploy/docker-compose.override.yml \
  exec -T backend python manage.py seed_demo
```

### 2.4 Frische Datenbank ist eine Voraussetzung, kein Komfort

Die E2E-Suite setzt eine frische Datenbank voraus. Auf einer
verschmutzten Entwicklerdatenbank sind sechs Tests rot, **ohne** dass ein
Produktdefekt vorliegt (Release-Bericht 7). Vor einem lokalen E2E-Lauf
also entweder den Datenbestand leeren oder den Lauf als nicht
aussagekräftig werten.

## 3. Schwerpunkttests — Neuerungen seit `beta.16`

### 3.1 W1 — `level` wird abgeleitet (ADR-005)

| # | Schritt | Erwartung |
|---|---|---|
| 1 | Requirement ohne `level` anlegen | Anlegen succeeds, `level` = 1 (Wurzel) |
| 2 | Dessen Ebene auf 2 setzen über die Hierarchie, nicht über `level` | `level` = 2 |
| 3 | Erneut `level: 99` mitsenden | Feld wird **ignoriert**, kein 4xx, `level` bleibt 2 |
| 4 | Kind unter das Requirement hängen | `level` des Kindes = 3, Elternteil unverändert |
| 5 | Zwischenknoten verschieben, der zwei Teilbäume trägt | **beide** Teilbäume neu berechnet, nicht nur einer |
| 6 | `level` explizit auf `NULL` | bleibt `NULL`, wird nicht auf 1 defaultiert |

Punkt 5 ist der eigentliche Test: die Ableitung läuft über alle
betroffenen Pfade, nicht nur über den direkten Elternpfad.

### 3.2 W2 — Personenfelder und Freitext (ADR-006)

| # | Schritt | Erwartung |
|---|---|---|
| 1 | Attributkatalog eines **frischen** Workspace öffnen | `stakeholder` ist Mehrfachauswahl mit Optionen, kein Textfeld |
| 2 | `stakeholder` mehrfach setzen | Auswahl bleibt über einen Reload erhalten |
| 3 | ADR öffnen, `deciders`/`assignee` setzen | Auswahl gegen Actor-Katalog, nicht Freitext |
| 4 | Katalog nach `origin_link` durchsuchen | **nicht** mehr angeboten |
| 5 | REST/MCP-Roundtrip für `stakeholder` | Payload ist eine **Liste** |

**Nur auf frischen Instanzen** gültig. Siehe 5.4.

### 3.3 W3 — Regel-Vokabular und Baseline-Gate (ADR-007)

| # | Schritt | Erwartung |
|---|---|---|
| 1 | Baseline über ein Artefakt erstellen, dessen `REQ_MUST_HAVE_*`-Regeln nicht erfüllt sind | Baseline-Gate blockt, nennt die konkrete Regel |
| 2 | Regel erfüllen, Baseline erneut versuchen | Gate öffnet |
| 3 | Regel-Definition öffnen | Source-Konvention (ADR- plus REQ-Verweis) lesbar |

### 3.4 W4 — Benachrichtigungen im Assistenten (ADR-009)

| # | Schritt | Erwartung |
|---|---|---|
| 1 | Assistenten-Einstiegspunkt öffnen | Benachrichtigungs-Feed sichtbar |
| 2 | Sidebar prüfen | **keine** separate Glocke mehr |
| 3 | Feed öffnen, Overlay schließen | `Escape` schließt |
| 4 | Feed öffnen, außerhalb klicken | schließt |
| 5 | Feed öffnen, `Escape` | **Fokus kehrt an den Trigger zurück** |
| 6 | Profil → Einstellungen | Benachrichtigungsabschnitt vorhanden |

Die Schritte 3–5 sind die Dismiss-Pfade aus #985. Sie sind nach ADR-009
an einen anderen Trigger gewandert; genau deshalb sind die Pins behalten
worden. Ein Verlust dieses Pfades ist die Regression, die dieser Test
fangen soll.

### 3.5 QA-Sweep — die wichtigsten Korrekturen

| # | Schritt | Erwartung |
|---|---|---|
| 1 | Request gegen Workspace eines **anderen** Tenants | **403** mit JSON-Envelope, **kein** 500, **kein** HTML |
| 2 | Fehlerhafte Eingabe über REST | kanonisches Error-Envelope, einheitlich über alle Adapter |
| 3 | TraceLink auf eine Subtyp-Entität | Endpunkt löst auf die Entität auf |
| 4 | KI-Ableitung erzeugen | in der Review-Ansicht reviewbar |
| 5 | UI: `Strg+S` | speichert |
| 6 | UI: System-ID kopieren | legt die ID in die Zwischenablage |
| 7 | Attributkatalog in einer Nicht-Englisch-Sprache | **Katalogbezeichnung** übersetzt, nicht der Feldname |
| 8 | Deploy mit defektem Dienst | meldet **keinen** Erfolg |

## 4. Regression-Kurzcheckliste

- [ ] `make up` startet durch, `/health/` antwortet 200
- [ ] `manage.py migrate` läuft ohne Ownership-Fehler durch
- [ ] Login, Workspace-Wechsel, Artefaktliste, Detailansicht
- [ ] Workflow-Transition in beide Richtungen, inkl. Revisionskonflikt
- [ ] Baseline erstellen, diffen, auflösen
- [ ] Review-Queue: Requirement nach `in_review`, approve und reject
- [ ] Audit-Log und Outbox werden geschrieben
- [ ] MCP `tools/list` und ein repräsentativer Tool-Call
- [ ] i18n DE/EN ohne fehlende Übersetzungen
- [ ] Suche und Dashboard rendern

## 5. Bekannte Grenzen & Hinweise

### 5.1 `bluepencil`

Der Sidecar kann nach einem Stack-Start kurz unavailable sein. Das ist kein
Fehler dieses Schnitts; der Dienst ist optional.

### 5.2 Vier bekannte Backend-Errors

`test_mcp_api_key_roles.py` schlägt ohne laufenden Stack fehl. Die Dateien
laufen in den CI-Backend-Sets grün. Nicht als Regression dieses Schnitts
werten.

### 5.3 Frontend-Flakiness

Ein früherer Full Run zeigte 3 intermittierende Fehler, die im
Folgelauf nicht reproduziert wurden. Ein einzelner grüner Lauf ist hier
kein Freigabesignal; maßgeblich ist der CI-Lauf.

### 5.4 Nicht erfüllbare Punkte — ausdrücklich nicht bestanden

- **W5 (#50):** Baseline-Rollback-Semantik nicht entschieden. Es gibt
  keinen W5-Code, also auch keinen Test dafür.
- **ADR-006 auf Altinstanzen:** der Upgrade-Pfad ist offen. Wer ein
  Upgrade einer Bestandsinstanz prüfen will, braucht `--reset` und
  akzeptiert damit den Verlust von Admin-Customisierungen. Gemessen auf
  einer vor diesem Schnitt gebootstrappten Instanz: `stakeholder`,
  `deciders` und `assignee` stehen weiterhin auf `text`, `origin_link` ist
  weiterhin vorhanden.
