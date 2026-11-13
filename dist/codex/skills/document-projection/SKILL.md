---
name: document-projection
description: Use when projecting Loom documents to Markdown files, reconciling repository content with a ReqogniLoom workspace, or adopting a repo document into Loom — always delivered as a branch and pull request, never as a server push.
---

# Document Projection

Siehe [DOMAIN_MODEL.md](../../DOMAIN_MODEL.md) für die Begriffe Dokument,
Anker, Glossar und Trace-Kante. Die vollständige Betriebsbeschreibung steht in
[`docs/clients/document-projection.md`](../../../clients/document-projection.md).

## Grundsatz

Der Server rendert und prüft nur. Er schreibt **nie** in ein Repository und hält
keine Repo-Zugangsdaten. Das Schreiben, Branchen und Öffnen des Pull Requests
übernimmt der Agent oder der CI-Job `scripts/clients/project_documents.py` —
beide arbeiten mit demselben Protokoll.

## Ablauf

1. `workspace.get_context` — Rigor-Stufe, Workspace-ID und Dokumentumfang
   ermitteln. Dokumente über `document.query` auflisten, einzelne über
   `document.read` prüfen; `document.versions` und `document.diff` zeigen, ob
   sich der Loom-Stand seit der letzten Projektion bewegt hat.
2. Lokal die Repo-Dateien unter den vom Server genannten Pfaden hashen
   (`sha256sum`), dann `document.projection_status` mit der Map
   `Pfad → SHA-256` aufrufen. Der Server sieht nur Hashes, nie Dateiinhalt —
   deshalb hasht der Client.
3. Je Statuszeile handeln (Tabelle unten). Im Zweifel anhalten und berichten.
4. Zustellung: Feature-Branch `docs/loom-projection-<datum>` anlegen, die
   geschriebenen Dateien committen (Commit-Nachricht nennt UID und Version aus
   der Kopfzeile), `gh pr create` öffnen. **Niemals** auf `main`/`master`
   schreiben oder pushen. Scheitert der PR, mit klarer Meldung stoppen und an
   den Menschen übergeben — nicht an einen anderen Agenten.
5. Nach dem Schreiben den tatsächlich geschriebenen Hash über den Parameter
   `confirm` von `document.projection_status` zurückmelden. Erst damit kennt
   Loom den neuen Projektionsstand.
6. Bei Bedarf `document.project` erneut aufrufen und den Inhalt byteweise
   vergleichen: gleicher Stand muss zwei Läufe byteidentisch rendern, sonst ist
   die Projektion nicht diff-fähig.
7. `traceability.query` und `artifact.search` nur zur Kontextklärung, wenn ein
   Dokument auf ein fremdes Artefakt verweist.

## Die sechs Statuszustände

| Zustand | Bedeutung | Aktion |
|---|---|---|
| `in_sync` | Datei und Loom stimmen überein | nichts tun |
| `loom_changed` | Loom ist weiter, Datei unverändert | `document.project`, Datei schreiben, Hash per `confirm` melden |
| `missing_in_repo` | Loom hat eine Projektion, die Datei fehlt | neu schreiben, aber den Verlust im PR-Text erwähnen |
| `file_changed` | Die Datei wurde von Hand geändert | **nie überschreiben**; anhalten und dem Menschen berichten |
| `conflict` | Beide Seiten geändert | **nie überschreiben**; anhalten, Konflikt im PR-Text benennen |
| `untracked_in_loom` | Datei existiert, Loom kennt sie nicht | nur berichten; Adoption vorschlagen |

Konflikte sind absichtlich laut: eine abweichende Projektionsdatei wird gemeldet,
nie still übernommen. Auflösen lässt sich ein Konflikt nur im Loom — entweder
das Dokument dort nachziehen oder die Datei adoptieren —, danach erneut
projizieren.

## Adoption

`document.adopt` verlangt, dass `file_sha256` exakt dem beim Import
festgehaltenen Hash entspricht. Weicht er ab, antwortet der Server mit **409**
und ändert nichts. Die Rolle adoptiert deshalb nur bei Hash-Gleichheit und nur
auf ausdrückliche Anweisung eines Menschen; `freeze: true` friert den Stand
zusätzlich ein. Nach der Adoption ist das Dokument `loom`-owned und wird
projiziert — die Datei wird nicht mehr von Hand bearbeitet. Textänderungen am
adoptierten Dokument laufen über `document.update` und sind freigabepflichtig.

## Grenzen

- Der Server schreibt nie ins Repo: keine Git-Bibliothek, kein Token im Backend,
  kein Push auf `main`. Zustellung ist immer Branch plus Pull Request.
- Projektionen sind deterministisch (stabile Sortierung, festes Zeilenende,
  keine Zeitstempel). Weicht ein Lauf davon ab, ist das ein Fehler und keine
  Stilfrage.
- Eingefrorene Dokumente bleiben eingefroren: `FIELD_FROZEN` gilt auch für
  Projektion und Adoption; `freeze` beim Adopt friert genau den übernommenen
  Stand ein.

## CI-Weg

Dieselben Schritte führt `python3 scripts/clients/project_documents.py` aus
(`--check` prüft, `--write` schreibt und öffnet den PR). Die Vorlage
`docs/agent-templates/ci/project-documents.yml` verdrahtet das in GitHub
Actions. Der Agent ist der manuelle Weg für Fälle, die eine Erklärung im
PR-Text brauchen.
