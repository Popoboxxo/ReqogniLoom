# OpenCode 2 — known issues in the repo-root config

> Hand-maintained artefact. It documents OpenCode 2 normalization findings for
> the repo-root `opencode.json` and the upstream fix that belongs in the
> `agent-meta` submodule (**not edited here**, see `submodule-protection`).
> Issue: #1706.

## Symptom

OpenCode 2 reports the repo-root config as carrying an unsupported legacy
setting:

```
configuration normalization diagnostic source=REPO/opencode.json
path=$.subagent_depth kind=unsupported action="omitted unsupported legacy setting"
```

Observed on `@opencode/cli` 2.2.5 (issue #1706). On 2.2.6 the key is dropped
**silently** (no diagnostic on stdout/stderr of `opencode debug config`); the
effective config simply no longer contains it.

## Origin — confirmed

The root `opencode.json` is **gitignored** (`.gitignore:46`), so it is a local,
generated file and not part of the repository. It comes from the agent-meta
sync, not from a ReqogniLoom source:

| Evidence | Path |
|---|---|
| Template ships the key | `.agent-meta/templates/configs/OPENCODE.settings-template.json` (`"subagent_depth": 3`, comment "Set to 3 for orchestrator chains") |
| Provider switch that injects it | `.agent-meta/config/ai-providers.yaml` (`Opencode.agent-transform.inject-subagent-depth: true`) |
| Submodule's own generated config | `.agent-meta/opencode.json` (also carries `"subagent_depth": 3`) |

The root file is **not** a byte-for-byte copy of `.agent-meta/opencode.json`:
the submodule config additionally carries `plugin`, `mcp.reqogniloom` and
`mcp.viz-logger`, and uses a coarser `permission` block (`edit`/`bash` →
`"**": "deny"`). Both files nevertheless carry the same
`subagent_depth` + `default_agent` pair, and the template above explains why.
So: origin confirmed as the agent-meta OpenCode settings template/transform,
not as a literal copy of the submodule file.

## Upstream fix already exists in the submodule

agent-meta's v2 surface writes the depth as **`experimental.subagent_depth`**
instead of the top-level key:

* `.agent-meta/scripts/lib/artifact_validate.py:48-51` — "the v2 settings
  document carries the orchestrator depth as `experimental.subagent_depth` …
  a top-level `subagent_depth` key is not emitted on the v2 surface."
* `.agent-meta/scripts/lib/opencode_v2_config.py:504-513` — writes
  `experimental.subagent_depth` from the project option.

So the project only needs the v2 surface enabled (or an equivalent template
change) upstream; ReqogniLoom must not patch the generated root file by hand,
because the next sync would recreate it.

### Ready-to-post upstream issue (agent-meta)

No upstream repository access from this workspace, so the issue text is kept
here for whoever files it:

```markdown
Title: opencode v2 surface: do not emit top-level `subagent_depth`

The OpenCode v2 config surface must not emit the v1-only top-level
`subagent_depth` key. OpenCode 2 omits it with
`kind=unsupported action="omitted unsupported legacy setting"` (2.2.5) or
silently (2.2.6).

Expected: the v2 settings document carries the orchestrator depth as
`experimental.subagent_depth` (as `scripts/lib/opencode_v2_config.py` and
`artifact_validate.py` already state).

Repro:
1. Generate an OpenCode project with a v1 surface.
2. Run `opencode debug config` with `@opencode/cli@2.2.6` in the project root.
3. Observe the top-level `subagent_depth` missing from the effective config.

Affected generated file: project-root `opencode.json`
(template `templates/configs/OPENCODE.settings-template.json`).
```

## Other V1-only keys — checked

Method: a scratch repo-root `opencode.json` with the V1 shapes, read back via
`opencode debug config` (`@opencode/cli` 2.2.6). Raw JSON is echoed by the
command, the `info` block is the normalized config.

| V1 key / shape | V2 (2.2.6) behaviour | Status |
|---|---|---|
| top-level `subagent_depth` | dropped (silently in 2.2.6) | **fix upstream** — use `experimental.subagent_depth` |
| flat `mcp.<name>` server map | normalized to `mcp.servers.<name>` | works, but the installer writes the native shape |
| `enabled: true` on an MCP entry | normalized to `disabled: false` | works; V2-native configs should use `disabled` |
| lowercase `permission` map | normalized to a `permissions` array | works (no drop), no action needed |
| `default_agent` | preserved | works |

Notes:

* The v1-only top-level `subagent_depth` is the only key that is **lost**; the
  other V1 shapes are losslessly normalized.
* The registry entries for `opencode` (V1) and `opencode-v2` are unaffected by
  this warning: they describe the MCP registration, which is valid on both.

## Runtime quirks observed while verifying

* **The background service owns the config and the environment.** `opencode
  debug config` reports the config of a *running* service. An `{env:…}`
  placeholder therefore resolves against that service's environment: a service
  started before the variable existed resolves it to `""` (observed: the MCP
  URL became `/mcp/` with no host). Running the same command with `--standalone`
  (fresh server, same environment) resolved `{env:FOO}` correctly. This is the
  same restart quirk that affects `opencode mcp list` after an install.
* **The project config needs a git root.** V2 only discovers a project config in
  a git-rooted directory; a scratch directory without `.git` shows no project
  document.
