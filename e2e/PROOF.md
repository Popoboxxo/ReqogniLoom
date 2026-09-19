# Proof artefacts — system cross-surface journey

These files are **generated**, not tracked (see `.gitignore`: `e2e/proof/`).
They are the evidence produced by
[`tests/system-proof-journey.spec.ts`](tests/system-proof-journey.spec.ts).

## How to regenerate

```bash
cd e2e
npx playwright test tests/system-proof-journey.spec.ts
```

Every run recreates all files below. Titles carry a run suffix, and cleanup
removes everything the test created, so re-runs are safe.

## What the spec proves

One artifact journey that crosses all three surfaces, in **four directions** —
each direction is asserted separately so a one-way implementation cannot pass:

| Direction | Step | Evidence |
|---|---|---|
| **MCP → REST** | 3 | a requirement written via `requirement.create` is returned by `GET /api/v1/requirements/<id>/` |
| **REST → MCP** | 5 | a trace link created via `POST /api/v1/tracelinks/` is returned by `needs.get_traces` |
| **MCP/REST → UI** | 6, 7, 8 | the created artifacts render in `/requirements`, `/testcases`, `/test-runs` |
| **UI → MCP** | 7b | a title edited and saved in the browser is read back through `requirement.get` (see `version: 3` in the response) |

## Files

### Screenshots (`0N-*.png`)
| File | Shows |
|---|---|
| `01-login.png` | authenticated session established |
| `02-mcp-created.png` | the MCP-created requirement visible in the UI list |
| `03-requirement-detail.png` | its detail editor |
| `04-trace-panel.png` | the REST-created trace link in the inspector |
| `05-title-updated-via-mcp.png` | UI after an MCP-side title update |
| `06-testcase.png` | the MCP-created test case |
| `07-test-run.png` | the test run with reported results |
| `08-ui-edit-saved.png` | form in its **saved** state (button reads "Save", not "Saving…") before MCP reads it back |

### Raw protocol evidence (`*.req.json` / `*.res.json`)
The exact JSON-RPC envelope sent and received, plus the REST bodies for the
trace-link step. These are the non-visual half of the proof: they show the
wire format, the tool names and the returned payloads rather than a
screenshot's interpretation of them.

Pairs are named `<surface>-<operation>.req/res.json`, e.g.
`mcp-requirement-get-after-ui-edit.res.json` is the response proving the
UI→MCP direction.
