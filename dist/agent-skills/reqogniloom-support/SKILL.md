---
name: reqogniloom-support
description: Use when a ReqogniLoom user reports a defect or problem that must be captured, classified, checked against duplicates and filed as a structured GitHub issue — read-only, with no code or repository changes.
---

# ReqogniLoom Support

Siehe [DOMAIN_MODEL.md](../../DOMAIN_MODEL.md) für die Begriffe Workspace,
Artefakt und Dokument. Das Issue-Formular liegt im ReqogniLoom-Repository unter
`.github/ISSUE_TEMPLATE/reqogniloom-defect.yml`. Diese Rolle arbeitet
ausschließlich lesend und legt am Ende genau ein Issue an.

## 1. Aufnahme-Checkliste

Jede Angabe wird erfragt, nicht geraten. Fehlt eine Pflichtangabe, wird
nachgefragt und der Fall bleibt offen.

| Feld | Pflicht | Quelle / Hinweis |
|---|---|---|
| Zusammenfassung | ja | ein Satz, was kaputt ist |
| Betroffene Oberfläche | ja | REST API, MCP, UI, CLI oder Harness-Plugin |
| ReqogniLoom-Version | ja | `GET /api/v1/version/` (Feld `version`), nicht aus dem Gedächtnis |
| Schritte zur Reproduktion | ja | nummeriert, mit Ausgangszustand und Workspace |
| Erwartetes Verhalten | ja | was passieren sollte |
| Tatsächliches Verhalten | ja | was passiert, inklusive Fehlertext |
| Fehlercode / Request-ID | nein | z. B. `FIELD_FROZEN`, `CONFLICT`, `X-Request-ID` |
| Tool-Name | nein | bei MCP-Fehlern Pflicht in der Praxis, z. B. `document.adopt` |
| Bereich | ja | requirements, architecture, traceability, baseline, mcp, ui, cli, plugin, auth |
| Schweregrad | ja | low, medium, high, critical |
| Redigierte Logs | nein | nur nach Entfernen von Tokens, Passwörtern, API-Keys und PII |

Zusätzlich erfassen, wenn vorhanden: Betriebsart (Docker Compose, Host-Port
8001), Rigor-Preset, `owner_mode` des betroffenen Dokuments, ob ein API-Key mit
welcher Rolle verwendet wurde (Rolle nennen, **nie** den Key selbst).

Redaktionsregel: Logs und Screenshots werden vor dem Einfügen von API-Keys
(Wert des `X-API-Key`- bzw. `Authorization`-Headers), Cookies, E-Mail-Adressen
und Namen befreit. Ein nicht redigierter Log wird nicht eingereicht.

## 2. Klassifikationsbaum

Von oben nach unten prüfen, die erste zutreffende Klasse gewinnt:

1. **Security** — Rechteumgehung, Datenleck, fehlende Tenant-Isolation,
   Secret in einer Antwort oder einem Log. → Vertraulicher Weg (Abschnitt 6),
   **kein** öffentliches Detail-Issue.
2. **Server-Bug** — reproduzierbar mit gültiger Konfiguration und gültigen
   Rechten; ein anderer Aufrufer mit denselben Daten scheitert identisch. Die
   lesenden Tools (`workspace.get_context`, `document.read`) bestätigen den
   Zustand, nicht die Ursache.
3. **Client-Fehler** — der Aufruf ist falsch gebaut: falscher Transport
   (SSE gegen HTTP), fehlender `X-API-Key`-Header, `{env:…}`-Platzhalter nicht
   expandiert, falscher Host-Port.
4. **Konfiguration** — Umgebung oder Workspace falsch eingestellt: fehlende
   Migration, leerer Demo-Seed, `LLM_PROVIDER=mock` ohne Key, Preset oder
   `ReviewPolicy` unerwartet.
5. **Upstream-Anbieter** — Fehler stammt vom LLM-Provider, von pgvector, Redis
   oder einem Netzwerkdienst; ReqogniLoom reicht ihn nur durch.
6. **Fehlende Funktion** — nichts ist kaputt, die Funktion existiert nicht.
   → Feature-Request formulieren, nicht als Bug einreichen.

Bei Mischfällen die Klasse wählen, deren Behebung den Fehler zuerst beseitigt,
und die zweite Klasse im Issue-Text als Zusammenhang nennen.

## 3. Minimal-Reproduktion

1. `workspace.get_context` — Workspace-ID, Rigor-Stufe und Rolle bestätigen.
2. `workspace.list` und `workspace.get_preferences` — liegt der Fehler an einem
   zweiten Workspace ebenfalls vor? Ist die Konfiguration wie erwartet?
3. `artifact.search` und `artifact.get_tree` — betroffenes Artefakt und seine
   Nachbarschaft lokalisieren.
4. `document.read` und `document.query` — bei Dokumentfehlern Version,
   `owner_mode`, `projection_mode` und Workflow-Zustand festhalten.
5. `metrics.get` und `metrics.catalog` — nur wenn der Fall Kennzahlen betrifft;
   sonst überspringen.

Alle Schritte sind lesend. Kein `document.update`, kein `document.adopt`, kein
`*.create` — die Reproduktion darf den Workspace nicht verändern. Reicht das
nicht, wird die Reproduktion als „nicht minimal möglich“ dokumentiert, statt
Testdaten anzulegen.

## 4. Duplikat-Suche

Vor dem Anlegen über die GitHub-Suche prüfen, in dieser Reihenfolge:

1. Exakte Fehlermeldung oder Fehlercode in Anführungszeichen.
2. Request-ID, falls vorhanden.
3. Tool-Name plus „error“ bzw. „fails“ (z. B. `document.adopt 409`).
4. Bereich plus Schweregrad plus Kurzbeschreibung.

Treffer prüfen und im Issue verlinken. Ist der Fall bereits offen, wird ein
Kommentar mit der eigenen Reproduktion ergänzt statt ein zweites Issue
angelegt. Ist er geschlossen, prüfen, ob die Version den Fix enthält
(`compatible_with` bzw. CHANGELOG); sonst neues Issue mit Verweis auf das alte.

## 5. Issue-Aufbau

Das Formular `.github/ISSUE_TEMPLATE/reqogniloom-defect.yml` verlangt:
Zusammenfassung, Oberfläche, Version, Reproduktion, erwartetes und tatsächliches
Verhalten; optional Fehlercode/Request-ID und redigierte Logs. Titel:
`[defect] <Kurzbeschreibung>` — keine Vermutungen über die Ursache im Titel.

Labels:

- automatisch nur **`bug`** (im Formular gesetzt). Weitere Labels nur, wenn sie
  im Repository nachweislich existieren.
- Schweregrad und Bereich bleiben **Antworten im Formular**, keine Labels. So
  erzwingt das Template kein Label, das es nicht gibt.
- Security-Fälle erhalten kein öffentliches Bug-Issue (Abschnitt 6).

Der Issue-Text nennt die Klassifikation aus Abschnitt 2, die minimale
Reproduktion aus Abschnitt 3 und die geprüften Duplikate aus Abschnitt 4. Logs
stehen in einem Codeblock und sind erkennbar redigiert.

## 6. Eskalation

- **Security:** kein öffentliches Issue mit Details. Stattdessen die Maintainer
  über den privaten Sicherheitskanal des Repositories kontaktieren
  (GitHub Security Advisory) und im öffentlichen Text nur „vertraulich gemeldet“
  vermerken. Keine Exploit-Schritte, keine Secrets, keine PII.
- **Datenverlust oder Datenintegrität:** Schweregrad `critical`, sofort an die
  Maintainer, mit Backup-Hinweis (`postgres-backup`, ADR-012).
- **Nicht reproduzierbar:** Issue mit Schweregrad `medium` und dem Status
  „braucht mehr Angaben“ anlegen; nach zwei Runden ohne neue Information
  schließen und im Kommentar festhalten, warum.

## 7. Nachverfolgung

Nach dem Anlegen die Issue-Nummer an den Melder zurückgeben, den Fall im
Workspace nicht duplizieren und keine Statusmeldung erfinden. Ein Issue gilt
erst als erledigt, wenn der Fix im genannten Release enthalten ist; die
Bestätigung erfolgt über Version und CHANGELOG, nicht über Vermutungen.
