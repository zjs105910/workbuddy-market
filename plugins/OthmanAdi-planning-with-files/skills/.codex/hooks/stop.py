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

    stop_args = ("--stop-hook-active",) if payload.get("stop_hook_active") is True else ()
    stdout, _ = adapter.run_shell_script("stop.sh", root, *stop_args)
    result = adapter.parse_json(stdout)

    # Codex's native Stop schema supports the same decision shape used by the
    # v3 gate oracle. Defense in depth: even if an older/custom oracle emits a
    # stale block while Codex says the stop hook is already active, never start
    # a recursive continuation.
    if result.get("decision") == "block" and payload.get("stop_hook_active") is not True:
        reason = result.get("reason")
        if isinstance(reason, str) and reason:
            adapter.emit_json({"decision": "block", "reason": reason})
        return

    message = result.get("followup_message")
    if not isinstance(message, str) or not message:
        return

    adapter.emit_json({"systemMessage": message})


if __name__ == "__main__":
    raise SystemExit(adapter.main_guard(main))
