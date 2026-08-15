---
name: interview-management
description: Conduct a structured interview to create, improve, or adjust a ReqogniLoom artifact (Requirement, ArchitectureElement, StakeholderNeed, Risk, TestCase, Adr, Issue, or Goal), backed by the interview.* MCP tools.
---

# Interview Management

Use this skill when the user wants to create, refine, or adjust a
ReqogniLoom artifact through a guided conversation, rather than
specifying every field up front.

## How it works

The actual question wording and progress live on the ReqogniLoom server,
not in this file — that's what makes the same interview consistent
across Claude Code, Opencode, and Antigravity. Your job is to run the
conversation naturally, but treat the server as the single source of
truth for state:

1. Call `interview.start(artifact_type, workspace_id)` to begin. It
   returns a `session_id` and the first phase's missing fields.
2. Call `interview.get_state(session_id)` whenever you need to know
   what's still open — including if you're resuming a session someone
   started on a different host. Never assume your own chat history is
   the source of truth for what's been answered.
3. As the user answers, call `interview.answer(session_id, field, value)`
   for each field you can confidently extract. If an answer is
   ambiguous, ask a clarifying question instead of guessing — do not
   record a value you are not confident about.
4. Optionally call `interview.grounding_context(session_id)` to check
   for existing artifacts that might already cover what the user is
   describing, and mention any close matches to the user before
   proceeding — this may avoid creating a duplicate.
5. Once every required field for every phase is answered (`get_state`
   returns an empty `missing_fields` for the final phase), call
   `interview.formalize(session_id)` to create or update the real
   artifact(s). Report the resulting artifact id(s) to the user.
   
   **Note:** `formalize()` currently only supports `Requirement`. For the
   other 7 in-scope types (ArchitectureElement, StakeholderNeed, Risk,
   TestCase, Adr, Issue, Goal), the interview session still collects and
   validates all fields via `interview.answer()` and `interview.get_state()`.
   However, the artifact will not be auto-created/updated; instead, surface
   the collected field values to the user and guide them to create the
   artifact via the ReqogniLoom UI or a dedicated creation flow.

## Scope

Available for: Requirement, ArchitectureElement, StakeholderNeed, Risk,
TestCase, Adr, Issue, Goal. NOT available for MainGoal (read-only,
intentionally out of scope).

`interview.start()`, `interview.answer()`, `interview.get_state()`, and
`interview.grounding_context()` work for all 8 in-scope types.
`interview.formalize()` currently only supports `Requirement` — for the other
7 types, collect and display field values instead.
