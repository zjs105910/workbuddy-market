#!/usr/bin/env python3
"""Route Codex plugin events through the established Windows hook launcher.

Codex plugin installs live below a cache path that can contain spaces.  The
Windows hook runner has changed how it quotes command lines across releases, so
the descriptor starts one quote-free PowerShell command and this dispatcher
selects the existing event handler from the JSON payload.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROUTES: dict[str, tuple[str, ...]] = {
    "SessionStart": ("run_sh.py", "session-start.sh"),
    "UserPromptSubmit": ("run_sh.py", "user-prompt-submit.sh"),
    "PreToolUse": ("pre_tool_use.py",),
    "PermissionRequest": ("permission_request.py",),
    "PostToolUse": ("post_tool_use.py",),
    "PreCompact": ("run_sh.py", "pre-compact.sh"),
    "Stop": ("stop.py",),
}


def main() -> int:
    payload = sys.stdin.buffer.read()
    try:
        event = json.loads(payload.decode("utf-8-sig")).get("hook_event_name")
    except (UnicodeDecodeError, json.JSONDecodeError, AttributeError):
        return 0

    route = ROUTES.get(event)
    if route is None:
        return 0

    hooks_dir = Path(__file__).resolve().parent
    result = subprocess.run(
        [sys.executable, str(hooks_dir / route[0]), *route[1:]],
        input=payload,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    sys.stdout.buffer.write(result.stdout)
    sys.stderr.buffer.write(result.stderr)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
