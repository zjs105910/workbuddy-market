#!/usr/bin/env python3
"""Bridge Hermes shell-script hooks to the canonical planning-with-files scripts.

Hermes runs shell hooks declared under ``hooks:`` in config.yaml, feeding one
JSON payload on stdin and reading one JSON object from stdout. The canonical
scripts speak Claude Code's hook dialect instead: ``inject-plan.sh`` prints the
plan context as plain text and ``gate-stop.sh`` prints a Stop decision. This
bridge translates:

* ``pre_llm_call``: runs ``inject-plan.sh`` in the payload's ``cwd`` and wraps
  any output as ``{"context": ...}``.
* ``pre_verify``: runs ``gate-stop.sh`` with ``stop_hook_active`` false and
  forwards a ``{"decision": "block", ...}`` line unchanged; Hermes accepts the
  Claude Code Stop shape on this event.

Everything else prints ``{}``. Every failure prints ``{}`` and exits 0, so a
missing script can never break a Hermes turn. The scripts directory comes from
``PLANNING_WITH_FILES_SKILL_ROOT`` when set, otherwise from the usual install
locations of the canonical skill.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def _candidate_script_dirs() -> list[Path]:
    dirs: list[Path] = []
    explicit = os.environ.get("PLANNING_WITH_FILES_SKILL_ROOT", "").strip()
    if explicit:
        dirs.append(Path(explicit).expanduser() / "scripts")
    home = Path.home()
    hermes_home = os.environ.get("HERMES_HOME", "").strip()
    if hermes_home:
        dirs.append(Path(hermes_home).expanduser() / "skills" / "planning-with-files" / "scripts")
    dirs.extend(
        [
            home / ".claude" / "skills" / "planning-with-files" / "scripts",
            home / ".agents" / "skills" / "planning-with-files" / "scripts",
            home / ".hermes" / "skills" / "planning-with-files" / "scripts",
            Path(__file__).resolve().parent.parent.parent / "skills" / "planning-with-files" / "scripts",
        ]
    )
    return dirs


def _find_script(name: str) -> Path | None:
    for directory in _candidate_script_dirs():
        candidate = directory / name
        if candidate.is_file():
            return candidate
    return None


def _run(
    script: Path,
    cwd: str,
    *,
    args: list[str] | None = None,
    stdin: str = "",
    session_id: str = "",
) -> str:
    shell = shutil.which("sh")
    if shell is None:
        return ""
    env = dict(os.environ)
    if session_id and not env.get("PWF_SESSION_ID"):
        # inject-plan.sh keys session attachment on PWF_SESSION_ID; Hermes
        # carries the same identity in the payload.
        env["PWF_SESSION_ID"] = session_id
    completed = subprocess.run(
        [shell, str(script), *(args or [])],
        input=stdin,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=cwd or None,
        env=env,
        timeout=float(os.environ.get("PWF_HERMES_HOOK_TIMEOUT", "25")),
        check=False,
    )
    return completed.stdout


def handle(payload: dict) -> dict:
    event = str(payload.get("hook_event_name", ""))
    cwd = str(payload.get("cwd") or os.getcwd())
    session_id = str(payload.get("session_id") or "")
    if event == "pre_llm_call":
        script = _find_script("inject-plan.sh")
        if script is None:
            return {}
        output = _run(script, cwd, args=["--context=userprompt"], session_id=session_id)
        return {"context": output} if output.strip() else {}
    if event == "pre_verify":
        script = _find_script("gate-stop.sh")
        if script is None:
            return {}
        output = _run(script, cwd, stdin=json.dumps({"stop_hook_active": False}), session_id=session_id)
        for line in output.splitlines():
            line = line.strip()
            if line.startswith("{") and '"decision"' in line:
                try:
                    decision = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if decision.get("decision") == "block" and decision.get("reason"):
                    return decision
        return {}
    return {}


def main() -> int:
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
        if not isinstance(payload, dict):
            payload = {}
        result = handle(payload)
    except Exception:  # noqa: BLE001 - a hook bridge must never fail the turn
        result = {}
    # ASCII-only JSON: Hermes reads stdout as text, and a Windows pipe would
    # otherwise re-encode the em dash in the plan banner as cp1252.
    sys.stdout.buffer.write(json.dumps(result, ensure_ascii=True).encode("ascii"))
    sys.stdout.buffer.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
