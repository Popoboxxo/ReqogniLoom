---
description: Turn ReqogniLoom's listen mode on, off or report its status
---

# /reqogniloom-listen

Run the packaged relay CLI in the directory that holds your global npm install
(`npm root -g`). It reads and writes the machine-wide state directory
`~/.reqogniloom/listen`, shared with every other ReqogniLoom client.

```bash
node "$(npm root -g)/@popoboxxo/reqogniloom-opencode/listen.mjs" status
```

For `on`, the workspace must be explicit — capture never guesses a target:

```bash
node "$(npm root -g)/@popoboxxo/reqogniloom-opencode/listen.mjs" on <workspace_id>
node "$(npm root -g)/@popoboxxo/reqogniloom-opencode/listen.mjs" off
```

`off` stops capture and deletes anything still queued. Both switches must be
on: the local one and the server-side workspace preference `capture.enabled`.
