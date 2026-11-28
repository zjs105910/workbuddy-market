#!/usr/bin/env python3
"""Codex PermissionRequest adapter for planning-with-files (v2.38.0).

Fires when Codex asks the user to permit a tool call. We surface a short
reminder that an active plan exists so the user reviews task_plan.md before
approving. Read-only; never blocks the request; always exits cleanly.
"""
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

    # Pass a relative plan root so the shell resolver returns a path that is
    # valid in both Git Bash and native Windows Python.
    plan_dir, _ = adapter.run_shell_script("resolve-plan-dir.sh", root, ".planning")
    plan = root / plan_dir / "task_plan.md" if plan_dir else root / "task_plan.md"
    if not plan.exists():
        return

    adapter.emit_json({
        "systemMessage": (
            "[planning-with-files] Active plan detected. Review the current phase "
            "in task_plan.md before approving the tool request."
        )
    })


if __name__ == "__main__":
    raise SystemExit(adapter.main_guard(main))
