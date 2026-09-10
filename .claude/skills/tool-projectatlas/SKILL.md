# Skill: ProjectAtlas — Token-Optimized Codebase Navigation

**MCP Server:** `projectatlas` (in `.mcp.json`)  
**Config Location:** `.projectatlas/projectatlas.db`, `.projectatlas/config.toml`

## Overview

ProjectAtlas provides symbol-graph lookups, file ranking, and structured code navigation tuned for token efficiency. Unlike raw file reads, atlas returns ranked snippets and relevance signals without parsing entire files.

## Main Tools

| Tool | Purpose | Example |
|------|---------|---------|
| `atlas_search(symbol)` | Find symbol definitions by name (fast, no grep). | `atlas_search("TenantContext")` → live definition with context |
| `atlas_map(path?)` | Rank files by importance; show entry points. | `atlas_map("backend/")` → sorted by fans-in/out, hotspot markers |
| `atlas_overview()` | High-level repo structure + key modules. | `atlas_overview()` → architecture diagram + key components |
| `atlas_symbols(file)` | List all symbols in a file with signatures. | `atlas_symbols("backend/application/services.py")` → [function_name, class_name, ...] |
| `atlas_impact(symbol)` | Show callsites and dependents of a symbol. | `atlas_impact("set_tenant")` → all callers in read-only cached index |

## When to Use

- **Quick lookups:** Find a symbol without opening files → `atlas_search()`.
- **File navigation:** Which files matter most in a directory → `atlas_map()`.
- **Impact analysis:** What breaks if I change this function → `atlas_impact()`.
- **Signature browsing:** See function signatures without full file reads → `atlas_symbols()`.
- **Architecture overview:** High-level entry points and key modules → `atlas_overview()`.

## When NOT to Use

- **Exhaustive grep for all occurrences** → Use Grep tool instead (atlas is read-only cached index).
- **Full file content review** → Use Read tool (atlas returns snippets).
- **Multiline pattern matching** → Use Grep with multiline mode.

## Token Reporting

When a tool result includes `projectatlas_metrics:` line, report the savings to the user (e.g., "ProjectAtlas saved ~150 tokens").

## Limitations

- Index is read-only (updated via `atlas update` CLI, not via MCP).
- Does not track runtime state (calls, values, etc.).
- Best for Go, Python, TypeScript; other languages may have limited symbol extraction.

---

**Configured:** `.projectatlas/projectatlas.db` (live index). If missing or stale, run `projectatlas update .` in repo root, or use raw tools (Read, Grep) as fallback.
