# Document projection (Phase G / #1374 S3)

ReqogniLoom can render a `Document` as a deterministic Markdown file for a
repository — and compare what is on disk with what Loom holds. **The server
never writes to a repository** and holds no repository credentials. Delivery is
a branch + pull request opened by CI or by an agent.

## The two ownership modes

| `owner_mode` | Meaning |
|---|---|
| `loom` (default) | The document is authored in Loom. A projection is optional (`projection_mode=generated`). |
| `repo_external` | The file came from a repository. Its content is not authoritative in Loom until it is **adopted**. |

## The loop

1. `document.project` (MCP) / `GET /api/v1/documents/{id}/projection/` renders
   the content. The header carries UID, version, workflow state and the hash of
   the content **without** the header.
2. The client writes the file on a feature branch.
3. The client reports the written hash with `confirm` on
   `document.projection_status` (MCP) or `POST .../confirm-projection/`.
4. The next run compares client-computed file hashes with Loom's state.

## The six status states

| State | Meaning | What the CLI does |
|---|---|---|
| `in_sync` | File and Loom agree | nothing |
| `loom_changed` | Loom moved on, file unchanged | writes (in `--write`) |
| `missing_in_repo` | Loom has a projection, the file is gone | writes (in `--write`) |
| `file_changed` | The file was edited by hand | **never overwrites**, exit 1 |
| `conflict` | Both sides changed | **never overwrites**, exit 1 |
| `untracked_in_loom` | A file exists that Loom does not track | reports only |

Conflicts are fail-loud on purpose. Resolve them in Loom (adopt the file or
update the document), then re-run.

## Adoption

`document.adopt` (MCP) / `POST /api/v1/documents/{id}/adopt/` requires
`file_sha256` to equal the hash recorded when the file was imported. A
mismatch answers **409** and changes nothing. After adoption the document is
`loom`-owned and projected; `freeze: true` also releases (freezes) it.

## CLI

```bash
python scripts/clients/project_documents.py \
  --url https://<host>/mcp/ \
  --key-env REQOGNILOOM_API_KEY \
  --workspace <uuid> --repo . --check     # or --write
```

Exit codes: `0` in sync, `1` deviation/conflict (nothing overwritten), `2`
usage/transport/branch error. The script refuses to run on `main`/`master`.

A ready-to-copy GitHub Actions template is in
`docs/agent-templates/ci/project-documents.yml`; it runs daily and on demand,
and opens a PR instead of pushing.
