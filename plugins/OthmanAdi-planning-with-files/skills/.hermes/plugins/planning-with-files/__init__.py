from __future__ import annotations

import importlib
import json
import os
import shlex
from pathlib import Path
from typing import Any

from .hooks import (
    WORKTREES_DIR_NAME,
    launch_dir_has_planning_state,
    launch_dir_notice,
    post_tool_call,
    pre_llm_call,
    pre_verify,
)
from .paths import effective_project_root, normalize_cwd, plan_root_is_pinned, plugin_skill_dir
from .tools import (
    planning_with_files_check_complete,
    planning_with_files_init,
    planning_with_files_status,
)

SLASH_COMMANDS = ("pwf", "pwf-status", "plan-status")
BROKEN_PIN_MESSAGE = (
    "planning-with-files: PWF_PLAN_ROOT is set but does not resolve to an absolute, "
    "existing directory; nothing done."
)


def _command_cwd() -> Path | None:
    """Project directory for a slash command.

    The PWF_PLAN_ROOT pin wins, exactly as it does for the hooks, and a broken
    pin returns None instead of a fallback (issue #272: on Hermes 0.21.3 the
    session cwd can name the home directory, and a pinned operator must not
    get a plan created or reported there). Without a pin: the Hermes session
    cwd, else the process cwd. A command handler receives only its arguments,
    no platform or session, so the CLI-only launch-directory rule of the hooks
    cannot be applied here; the pin is the documented answer for commands.
    """
    if plan_root_is_pinned():
        return effective_project_root(normalize_cwd())
    try:
        from agent.runtime_cwd import resolve_agent_cwd

        candidate = resolve_agent_cwd()
        if isinstance(candidate, Path) and candidate.is_dir():
            return normalize_cwd(str(candidate))
    except Exception:  # noqa: BLE001 - any runtime failure falls back to the process cwd
        pass
    return normalize_cwd()


def _format_status(payload: dict[str, Any]) -> str:
    if not payload.get("exists"):
        return payload.get("message", "No planning files found.")
    counts = payload.get("counts") or {}
    lines = [
        f"planning-with-files status ({payload.get('plan_id', 'root')}, {payload.get('mode', 'legacy')} mode"
        f"{', attested' if payload.get('attested') else ''})",
        f"  plan: {payload.get('plan_dir', '')}",
        f"  current phase: {payload.get('current_phase', '')}",
        "  phases: {complete}/{total} complete, {in_progress} in_progress, {pending} pending".format(
            complete=counts.get("complete", 0),
            total=counts.get("total", 0),
            in_progress=counts.get("in_progress", 0),
            pending=counts.get("pending", 0),
        ),
        f"  errors logged: {payload.get('errors_logged', 0)}",
    ]
    return "\n".join(lines)


def pwf_command(raw_args: str = "") -> str:
    """/pwf [--autonomous|--gated] [--template analytics] [plan name]"""
    try:
        tokens = shlex.split(raw_args or "")
    except ValueError:
        tokens = (raw_args or "").split()
    mode = ""
    template = "default"
    name_parts: list[str] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token in {"--autonomous", "-a"}:
            mode = mode or "autonomous"
        elif token in {"--gated", "-g"}:
            mode = "gated"
        elif token in {"--template", "-t"} and index + 1 < len(tokens):
            template = tokens[index + 1]
            index += 1
        elif token.startswith("--template="):
            template = token.split("=", 1)[1]
        elif token in {"--help", "-h"}:
            return (
                "Usage: /pwf [--autonomous|--gated] [--template analytics] [plan name]\n"
                "Creates task_plan.md, findings.md and progress.md (root mode), or an isolated\n"
                ".planning/YYYY-MM-DD-<slug>/ directory when a plan name is given. The v3 flags\n"
                "write the mode marker, a nonce and the plan attestation. Existing files are kept."
            )
        else:
            name_parts.append(token)
        index += 1
    project_dir = _command_cwd()
    if project_dir is None:
        return BROKEN_PIN_MESSAGE
    result = json.loads(
        planning_with_files_init(
            template=template, cwd=str(project_dir), name=" ".join(name_parts), mode=mode
        )
    )
    if not result.get("ok", True):
        return f"planning-with-files: {result.get('error', 'initialization failed')}"
    created = ", ".join(result.get("created") or []) or "none (all present)"
    lines = [
        f"planning-with-files: plan ready ({result.get('plan_id', 'root')}, {result.get('mode', 'legacy')} mode)",
        f"  directory: {result.get('plan_dir', '')}",
        f"  created: {created}",
    ]
    if result.get("attestation"):
        lines.append(f"  attested: sha256 {result['attestation'][:12]}...")
    lines.append("  next: read task_plan.md, findings.md and progress.md, then fill in the goal and phases.")
    if not plan_root_is_pinned():
        # Issue #272: the plan just went where Hermes pointed while the launch
        # directory already holds one; say so instead of leaving two plans apart.
        hint = _launch_dir_hint(project_dir)
        if hint:
            lines.append(hint)
    return "\n".join(lines)


def status_command(raw_args: str = "") -> str:
    """/pwf-status and /plan-status: compact planning state for the current project."""
    project_dir = _command_cwd()
    if project_dir is None:
        return BROKEN_PIN_MESSAGE
    payload = json.loads(planning_with_files_status(cwd=str(project_dir)))
    report = _format_status(payload)
    if not payload.get("exists") and not plan_root_is_pinned():
        hint = _launch_dir_hint(project_dir)
        if hint:
            report = "\n".join((report, hint))
    return report


def _session_cwd_is_pinned() -> bool:
    """True when Hermes pinned this context's cwd per session (``agent.runtime_cwd._SESSION_CWD``).

    A pinned context runs in a multi-session backend whose process cwd is the
    backend's start directory, not a launch directory, so the hint would
    compare the wrong things. Prompt turns on the TUI and Desktop carry the
    pin; their plugin command dispatch does not, so this is a best-effort
    exemption. Read-only inspection; any failure counts as not pinned.
    """
    try:
        value = importlib.import_module("agent.runtime_cwd")._SESSION_CWD.get()
    except Exception:  # noqa: BLE001 - a host without the pin keeps the hint
        return False
    return isinstance(value, str) and bool(value.strip())


def _launch_dir_hint(project_dir: Path) -> str:
    """Issue #272 diagnostic for the slash commands: name the launch directory's plan.

    Read-only and platform-blind (a command handler has no platform), so it is
    a hint under the report, never a refusal. Worktree sessions and sessions
    whose cwd Hermes pinned per session are exempt.
    """
    if WORKTREES_DIR_NAME in project_dir.parts or _session_cwd_is_pinned():
        return ""
    try:
        launch = normalize_cwd(os.getcwd())
        if not launch.is_dir() or launch == project_dir or not launch_dir_has_planning_state(launch):
            return ""
    except (OSError, RuntimeError, ValueError):
        return ""
    return launch_dir_notice(project_dir, launch)


def _register_commands(ctx: Any) -> None:
    register = getattr(ctx, "register_command", None)
    if register is None:
        return
    try:
        register(
            name="pwf",
            handler=pwf_command,
            description="Start planning-with-files: create the plan files (root or .planning/<slug>), optional --autonomous / --gated",
            args_hint="[--gated] [plan name]",
        )
        register(
            name="pwf-status",
            handler=status_command,
            description="Show the active planning-with-files plan: phase counts, mode, attestation",
        )
        register(
            name="plan-status",
            handler=status_command,
            description="Alias of /pwf-status",
        )
    except Exception:  # noqa: BLE001 - a host without slash-command support must not lose the tools
        return


def _register_skill(ctx: Any) -> None:
    register = getattr(ctx, "register_skill", None)
    if register is None:
        return
    try:
        skill_root = plugin_skill_dir()
        if skill_root is None:
            return
        skill_md = skill_root / "SKILL.md"
        if skill_md.is_file():
            register(
                name="planning-with-files",
                path=skill_md,
                description="Persistent file-based planning workflow (task_plan.md, findings.md, progress.md)",
            )
    except Exception:  # noqa: BLE001 - bundled skill registration is best effort
        return


def register(ctx: Any) -> None:
    ctx.register_tool(
        name="planning_with_files_init",
        toolset="terminal",
        schema={
            "name": "planning_with_files_init",
            "description": (
                "Create planning-with-files markdown files (task_plan.md, findings.md, progress.md) "
                "in the current project. Pass a name to create an isolated .planning/<date>-<slug>/ plan; "
                "pass mode autonomous or gated to enable the v3 modes with attestation."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "template": {"type": "string", "description": "Template name, e.g. default or analytics."},
                    "cwd": {"type": "string", "description": "Target project directory. Defaults to current working directory."},
                    "name": {"type": "string", "description": "Optional plan name; creates .planning/YYYY-MM-DD-<slug>/ and sets it active."},
                    "mode": {"type": "string", "description": "Optional v3 mode: autonomous or gated. Empty keeps legacy behavior."},
                },
            },
        },
        handler=lambda args, **kw: planning_with_files_init(
            template=args.get("template", "default"),
            cwd=args.get("cwd", ""),
            name=args.get("name", ""),
            mode=args.get("mode", ""),
        ),
        description="Initialize planning-with-files state files.",
    )
    ctx.register_tool(
        name="planning_with_files_status",
        toolset="terminal",
        schema={
            "name": "planning_with_files_status",
            "description": "Summarize current planning file status for the active project (slug or root plan).",
            "parameters": {
                "type": "object",
                "properties": {
                    "cwd": {"type": "string", "description": "Target project directory. Defaults to current working directory."},
                },
            },
        },
        handler=lambda args, **kw: planning_with_files_status(cwd=args.get("cwd", "")),
        description="Show planning-with-files status summary.",
    )
    ctx.register_tool(
        name="planning_with_files_check_complete",
        toolset="terminal",
        schema={
            "name": "planning_with_files_check_complete",
            "description": "Run the planning-with-files completion check for the active plan.",
            "parameters": {
                "type": "object",
                "properties": {
                    "cwd": {"type": "string", "description": "Target project directory. Defaults to current working directory."},
                },
            },
        },
        handler=lambda args, **kw: planning_with_files_check_complete(cwd=args.get("cwd", "")),
        description="Check whether all planning phases are complete.",
    )
    ctx.register_hook("pre_llm_call", pre_llm_call)
    ctx.register_hook("post_tool_call", post_tool_call)
    ctx.register_hook("pre_verify", pre_verify)
    _register_commands(ctx)
    _register_skill(ctx)
