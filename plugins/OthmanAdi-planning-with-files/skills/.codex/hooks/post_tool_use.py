#!/usr/bin/env python3
from __future__ import annotations

import codex_hook_adapter as adapter


def main() -> None:
    payload = adapter.load_payload()
    root = adapter.effective_plan_root(adapter.cwd_from_payload(payload))
    if root is None:
        return  # broken PWF_PLAN_ROOT pin fails closed (issue #212); notice is userprompt-only

    session_id = adapter.session_id_from_payload(payload)
    if not adapter.is_session_attached(root, session_id):
        return
    if adapter.session_plan_requires_binding(root):
        return

    stdout, _ = adapter.run_shell_script(
        "post-tool-use.sh",
        root,
        session_id=session_id,
    )
    if stdout:
        # The nudge is addressed to Claude, so it belongs in the model's
        # context, not in a systemMessage (issue #239). systemMessage is a
        # warning shown to the USER, so the instruction never reached the model
        # while the person saw it after every matching tool call.
        # pre_tool_use.py and run_sh.py already emit this shape for their own
        # events; this path had simply never been moved over.
        adapter.emit_json({
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": stdout,
            }
        })


if __name__ == "__main__":
    raise SystemExit(adapter.main_guard(main))
