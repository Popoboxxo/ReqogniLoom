---
name: interview-management
description: Conduct a structured interview to create, improve, or adjust a ReqogniLoom artifact (Requirement, ArchitectureElement, StakeholderNeed, Risk, TestCase, Adr, Issue, or Goal), backed by the interview.* MCP tools.
---

# Interview Management

Use this skill when the user wants to create, refine, or adjust a
ReqogniLoom artifact through a guided conversation, rather than
specifying every field up front.

## Tool names: dotted in docs, underscored in client sessions (#2046)

Canonical tool names — in `tools/list`, the tool manifest and this skill —
are DOTTED (`interview.start`, `interview.formalize`). MCP clients typically
expose the same tools with UNDERSCORED names (e.g. `reqogniloom_interview_start`,
`reqogniloom_interview_formalize`); that client-side form is not guaranteed —
the OpenCode-style prefix is unverified (see
`docs/clients/opencode-endpoint-verification.md`). The `.` → `_` sanitization
happens client-side / at plugin-packager build time
(`scripts/check_plugin_packages.py`: `prefix + tool["name"].replace(".", "_")`),
not in the JSON-RPC layer. The proven Claude Code form in generated agent
`tools:` frontmatter is `mcp__plugin_reqogniloom_reqogniloom__<tool_underscored>`
— e.g. `interview.start` becomes
`mcp__plugin_reqogniloom_reqogniloom__interview_start`.
Rule: write dotted names in documentation, manifest references and source
templates; let the packager generate the underscored/prefixed form. Never
hand-edit a generated `dist/` copy — regenerate it (see
`docs/agent-templates/INSTALL.md`) — and never write the underscored form
into a hand-authored role or skill.

## Tool inventory

All 11 `interview.*` tools, with their one-line purposes:

- `interview.start(...)` — start a typed single-kind or type-less multi-kind
  discovery session; returns the `session_id` and initial state.
- `interview.get_state(session_id)` — current phase, collected/missing fields
  and grounding snapshot; callable from any host to resume a session.
- `interview.answer(session_id, field, value)` — record one protocol field;
  the field name is resolved across ALL phases, not just the current one,
  so an already-collected field can be answered again (#1979).
- `interview.list(workspace_id, status?)` — list sessions in a workspace,
  optionally filtered by status (`in_progress`, `completed`, `abandoned`).
- `interview.get(session_id)` — fetch one session's summary (id, workspace,
  artifact_type, status).
- `interview.grounding_context(session_id)` — structural duplicate check:
  find existing artifacts whose title overlaps the collected title. Only
  `Requirement` is wired up; other types return no candidates.
- `interview.set_target(session_id, artifact_id)` — pin an existing
  `Requirement` as the `formalize()` update target (Requirement only).
- `interview.formalize(session_id, confirmed_proposal?)` — create or update
  the real artifact(s) from collected answers; marks the session completed.
- `interview.propose(session_id)` — read the pending multi-artifact proposal
  emitted by a chat turn (null until one exists).
- `interview.chat(session_id, message?)` — drive one server-generated
  conversational turn (needs a resolvable LLM provider); may emit a proposal.
- `interview.abandon(session_id)` — actively cancel an `in_progress` session
  and mark it `abandoned`.

## How it works

The actual question wording and progress live on the ReqogniLoom server,
not in this file — that's what makes the same interview consistent
across Claude Code, Opencode, and Antigravity. Your job is to run the
conversation naturally, but treat the server as the single source of
truth for state:

1. Call `interview.start(...)` to begin (typed single-kind, or type-less
   multi-kind discovery). It returns a `session_id` and the current state.
2. Call `interview.get_state(session_id)` whenever you need to know
   what's still open — including if you're resuming a session someone
   started on a different host. Never assume your own chat history is
   the source of truth for what's been answered. `interview.list()` and
   `interview.get()` help locate an existing session by workspace/status.
3. As the user answers, call `interview.answer(session_id, field, value)`
   for each field you can confidently extract. Field names are matched
   across ALL protocol phases (#1979), so an earlier field can be
   corrected later. If an answer is ambiguous, ask a clarifying question
   instead of guessing — do not record a value you are not confident about.
   For a conversational flow, `interview.chat()` can drive a
   server-generated turn and may produce a proposal you read via
   `interview.propose()`; it requires a resolvable LLM provider.
4. Optionally call `interview.grounding_context(session_id)` to check
   for existing artifacts that might already cover what the user is
   describing, and mention any close matches to the user before
   proceeding — this may avoid creating a duplicate. If the user confirms
   one of the suggested candidates is the `Requirement` they actually
   mean, call `interview.set_target(session_id, artifact_id)` before
   formalizing — this makes `formalize()` update that existing
   `Requirement` instead of creating a new one. `set_target()` and
   `grounding_context()` are both `Requirement`-only.
5. Once every required field is answered (`get_state` returns an empty
   `missing_fields` for the final phase), call
   `interview.formalize(session_id)` to create or update the real
   artifact(s). Report the resulting artifact id(s) to the user.
   In a multi-kind session, read the proposal via `interview.propose()`
   and pass the caller-confirmed proposal to `formalize()`; all items are
   then created in one transaction.
6. If the user abandons the conversation, call
   `interview.abandon(session_id)` so the session is marked `abandoned`
   instead of lingering as `in_progress` until the inactivity sweep.

### formalize() scope

`formalize()` covers all 8 in-scope types. A single-kind session creates one
artifact of the session's `artifact_type` (Requirement, ArchitectureElement,
StakeholderNeed, Risk, TestCase, Adr, Issue or Goal) through that type's
production create service; a multi-kind session creates every item of a
caller-confirmed proposal atomically (same 8 types; glossary terms are not
proposed by an interview). The grounded UPDATE branch is `Requirement`-only:
only when a target was pinned with `set_target()` does `formalize()` update
an existing `Requirement` instead of creating one. `set_target()` and
`grounding_context()` remain `Requirement`-only — for the other 7 types no
update or duplicate-grounding path exists yet.

## Scope

Available for: Requirement, ArchitectureElement, StakeholderNeed, Risk,
TestCase, Adr, Issue, Goal. NOT available for MainGoal (read-only,
intentionally out of scope).

`interview.start()`, `interview.answer()`, `interview.get_state()`,
`interview.list()`, `interview.get()`, `interview.chat()`,
`interview.propose()` and `interview.formalize()` work for all 8 in-scope
types. `interview.grounding_context()` currently matches candidates only
for `Requirement` — for the other 7 types it returns no candidates.
`interview.set_target()` is `Requirement`-only, since it only feeds
`formalize()`'s update branch, which is likewise `Requirement`-only.
`interview.abandon()` cancels any in-progress session regardless of type.
