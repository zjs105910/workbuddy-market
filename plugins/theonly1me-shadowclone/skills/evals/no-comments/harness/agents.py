import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from harness.config import (
    CLAUDE_BINARY,
    CODEX_BINARY,
    CODEX_HOME,
    Setting,
)
from harness.workspace import run_environment

CLAUDE_SANDBOX_SETTINGS = json.dumps({"sandbox": {"enabled": True, "autoAllowBashIfSandboxed": True}})
CLAUDE_ALLOWED_TOOLS = "Bash,Edit,Write,Read,Glob,Grep"
CODEX_CONFIG = 'personality = "none"\n'


@dataclass(frozen=True)
class AgentInvocation:
    command: list[str]
    environment: dict[str, str]


def claude_invocation(*, setting: Setting, workspace: Path, home: Path) -> AgentInvocation:
    environment = run_environment(home)
    environment["HOME"] = str(Path.home())
    environment["USER"] = environment["LOGNAME"] = Path.home().name
    environment["CLAUDE_CODE_DISABLE_AUTO_MEMORY"] = "1"
    environment["DISABLE_AUTOUPDATER"] = "1"
    command = [
        str(CLAUDE_BINARY),
        "-p",
        "--model", setting.model,
        "--effort", setting.effort,
        "--setting-sources", "",
        "--disable-slash-commands",
        "--strict-mcp-config",
        "--no-session-persistence",
        "--output-format", "stream-json",
        "--verbose",
        "--allowedTools", CLAUDE_ALLOWED_TOOLS,
        "--settings", CLAUDE_SANDBOX_SETTINGS,
    ]
    return AgentInvocation(command, environment)


def prepare_codex_home() -> None:
    CODEX_HOME.mkdir(parents=True, exist_ok=True)
    authentication = CODEX_HOME / "auth.json"
    if not authentication.exists():
        shutil.copy2(Path.home() / ".codex" / "auth.json", authentication)
        authentication.chmod(0o600)
    (CODEX_HOME / "config.toml").write_text(CODEX_CONFIG)


def codex_invocation(*, setting: Setting, workspace: Path, home: Path) -> AgentInvocation:
    prepare_codex_home()
    environment = run_environment(home)
    environment["CODEX_HOME"] = str(CODEX_HOME)
    command = [
        str(CODEX_BINARY),
        "exec",
        "-m", setting.model,
        "-c", f'model_reasoning_effort="{setting.effort}"',
        "-s", "workspace-write",
        "--json",
        "--skip-git-repo-check",
        "-C", str(workspace),
        "-",
    ]
    return AgentInvocation(command, environment)


def build_invocation(*, setting: Setting, workspace: Path, home: Path) -> AgentInvocation:
    builder = claude_invocation if setting.cli == "claude" else codex_invocation
    return builder(setting=setting, workspace=workspace, home=home)


def read_events(transcript: Path) -> list[dict]:
    events = []
    for line in transcript.read_text().splitlines():
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events


def extract_usage(*, cli: str, events: list[dict]) -> dict:
    if cli == "claude":
        results = [event for event in events if event.get("type") == "result"]
        final = results[-1] if results else {}
        return {
            "cost_usd": final.get("total_cost_usd"),
            "turns": final.get("num_turns"),
            "usage": final.get("usage"),
            "is_error": final.get("is_error"),
        }
    totals: dict[str, int] = {}
    for event in events:
        if event.get("type") == "turn.completed":
            for key, value in (event.get("usage") or {}).items():
                if isinstance(value, int):
                    totals[key] = totals.get(key, 0) + value
    return {"usage": totals, "turns": sum(1 for event in events if event.get("type") == "turn.completed")}

