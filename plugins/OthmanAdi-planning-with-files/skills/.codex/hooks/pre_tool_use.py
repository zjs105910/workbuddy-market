#!/usr/bin/env python3
from __future__ import annotations

import codex_hook_adapter as adapter


def main() -> None:
    payload = adapter.load_payload()
    root = adapter.effective_plan_root(adapter.cwd_from_payload(payload))
    if root is None:
        return  # broken PWF_PLAN_ROOT pin fails closed (issue #212); notice is userprompt-only

    if not adapter.is_session_attached(root, adapter.session_id_from_payload(payload)):
        return
    if adapter.session_plan_requires_binding(root):
        return

    stdout, stderr = adapter.run_shell_script(
        "pre-tool-use.sh",
        root,
        session_id=adapter.session_id_from_payload(payload),
    )

    result = adapter.parse_json(stdout)
    decision = result.get("decision")
    if decision and decision != "allow":
        adapter.emit_json(result)
        return

    if stderr:
        adapter.emit_json({
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "additionalContext": stderr,
            }
        })


if __name__ == "__main__":
    raise SystemExit(adapter.main_guard(main))
