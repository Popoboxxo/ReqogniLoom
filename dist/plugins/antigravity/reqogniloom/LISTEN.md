# Listen mode (Antigravity) — stage B

`hooks.json` registers a `PreInvocation` hook that runs `python3 listen.py`.
Antigravity has no submit event, so this fires before **every** model call and
carries `lastUserInput`; the relay deduplicates on `(session_id, sha256(text))`
in `~/.reqogniloom/listen/capture-seen.json` before it queues a message.

* Default **off**. Switch: `python3 listen.py on <workspace_id>` / `off` /
  `status`, or the equivalent commands of the other clients — the state
  directory `~/.reqogniloom/listen` is shared.
* Both switches must be on: the local `listen.json` and the server-side
  workspace preference `capture.enabled`.
* The hook only queues and detaches; delivery happens in `listen.py --drain`
  and uses `POST /api/v1/suggestions/capture/` with
  `REQOGNILOOM_MCP_URL` (or `REQOGNILOOM_BASE_URL`) and `REQOGNILOOM_API_KEY`.
* Fail-open: no stdout, no non-zero exit, diagnostics without message text in
  `capture.log`.

Status of this adapter: **partial**. The hook schema (`PreInvocation`,
`lastUserInput`, script cwd) follows the documented preview shape but was not
executed against a live Antigravity installation; the conformance suite checks
the relay against an HTTP stub. See `docs/clients/listen-mode-contract.md`.
