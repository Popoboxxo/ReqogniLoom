---
description: Show or change the ReqogniLoom listen mode (ambient capture)
argument-hint: "on|off|status"
allowed-tools: Bash(node:*)
---

Run the listen-mode command:

!`node "${CLAUDE_PLUGIN_ROOT}/scripts/listen.mjs" $ARGUMENTS`

Report the output above to the user. When the output says listen mode is ON,
repeat the privacy note: user-message text is sent to the ReqogniLoom server and
processed by its model, and the server-side workspace switch `capture.enabled`
must also be on. When it says listen mode is OFF, mention that any message still
queued was deleted — nothing that was not sent is kept on disk.
