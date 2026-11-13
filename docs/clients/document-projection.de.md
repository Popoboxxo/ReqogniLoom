# Dokument-Projektion (Phase G / #1374 S3)

ReqogniLoom kann ein `Document` als deterministische Markdown-Datei für ein
Repository rendern — und vergleichen, was auf der Platte liegt und was Loom
hält. **Der Server schreibt nie in ein Repository** und hält keine
Repo-Zugangsdaten. Die Zustellung ist ein Branch plus Pull Request, geöffnet
durch CI oder einen Agenten.

## Die zwei Eigentumsmodi

| `owner_mode` | Bedeutung |
|---|---|
| `loom` (Default) | Das Dokument wird in Loom gepflegt. Eine Projektion ist optional (`projection_mode=generated`). |
| `repo_external` | Die Datei kam aus einem Repository. Ihr Inhalt ist in Loom erst nach der **Adoption** maßgeblich. |

## Der Ablauf

1. `document.project` (MCP) / `GET /api/v1/documents/{id}/projection/` rendert
   den Inhalt. Die Kopfzeile trägt UID, Version, Workflow-Zustand und den Hash
   des Inhalts **ohne** Kopfzeile.
2. Der Client schreibt die Datei auf einem Feature-Branch.
3. Der Client meldet den geschriebenen Hash über `confirm` an
   `document.projection_status` (MCP) bzw. `POST .../confirm-projection/`.
4. Der nächste Lauf vergleicht die client-berechneten Datei-Hashes mit Looms
   Stand.

## Die sechs Zustände

| Zustand | Bedeutung | Was die CLI tut |
|---|---|---|
| `in_sync` | Datei und Loom stimmen überein | nichts |
| `loom_changed` | Loom ist weiter, Datei unverändert | schreibt (bei `--write`) |
| `missing_in_repo` | Loom hat eine Projektion, die Datei fehlt | schreibt (bei `--write`) |
| `file_changed` | Die Datei wurde von Hand geändert | **überschreibt nie**, Exit 1 |
| `conflict` | Beide Seiten geändert | **überschreibt nie**, Exit 1 |
| `untracked_in_loom` | Datei existiert, Loom kennt sie nicht | nur Meldung |

Konflikte sind absichtlich laut. Löse sie in Loom (Datei adoptieren oder
Dokument aktualisieren) und starte den Lauf erneut.

## Adoption

`document.adopt` (MCP) / `POST /api/v1/documents/{id}/adopt/` verlangt, dass
`file_sha256` dem beim Import gespeicherten Hash entspricht. Eine Abweichung
antwortet **409** und ändert nichts. Nach der Adoption ist das Dokument
`loom`-eigen und projiziert; `freeze: true` gibt es zusätzlich frei (friert es
ein).

## CLI

```bash
python scripts/clients/project_documents.py \
  --url https://<host>/mcp/ \
  --key-env REQOGNILOOM_API_KEY \
  --workspace <uuid> --repo . --check     # oder --write
```

Exit-Codes: `0` synchron, `1` Abweichung/Konflikt (nichts überschrieben), `2`
Nutzungs-/Transport-/Branch-Fehler. Auf `main`/`master` verweigert das Skript
die Arbeit.

Eine kopierfertige GitHub-Actions-Vorlage liegt in
`docs/agent-templates/ci/project-documents.yml`; sie läuft täglich und auf
Anforderung und öffnet einen PR statt zu pushen.
