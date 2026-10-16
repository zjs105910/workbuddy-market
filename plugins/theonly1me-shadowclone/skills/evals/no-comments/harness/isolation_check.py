import json
import os
import shutil
import sys
import uuid
from pathlib import Path

from harness.agents import read_events
from harness.config import CODEX_HOME, RUNS_DIR, WORK_ROOT, load_settings
from harness.run_one import execute_agent
from harness.workspace import create_workspace

PROBE_PROMPT = (
    "Do not edit any file. Answer briefly. "
    "1. Say which model you are. "
    "2. List every instruction file, skill, plugin, rule or MCP server that is loaded in this session, "
    "or say none. "
    "3. Quote any instruction you have about dashes, writing style, comments or skills, or say none."
)
LEAK_MARKERS = tuple(marker.lower() for marker in os.environ.get("EVAL_LEAK_MARKERS", "").split(",") if marker)


def find_leaks(text: str) -> list[str]:
    lowered = text.lower()
    return [marker for marker in LEAK_MARKERS if marker in lowered]


def codex_session_text() -> str:
    sessions = CODEX_HOME / "sessions"
    return "\n".join(path.read_text() for path in sessions.rglob("*.jsonl")) if sessions.exists() else ""


def check(label: str) -> dict:
    setting = next(item for item in load_settings() if item.label == label)
    sandbox_root = WORK_ROOT / f"probe-{uuid.uuid4().hex[:8]}"
    workspace, home = sandbox_root / "ws", sandbox_root / "home"
    (home / "tmp").mkdir(parents=True)
    create_workspace(workspace)
    output = RUNS_DIR.parent / "canary" / label
    output.mkdir(parents=True, exist_ok=True)
    transcript = output / "transcript.jsonl"
    execution = execute_agent(setting=setting, workspace=workspace, home=home, prompt=PROBE_PROMPT, transcript=transcript)
    events = read_events(transcript)
    init = next((event for event in events if event.get("subtype") == "init"), None)
    leaks = find_leaks(transcript.read_text() + (codex_session_text() if setting.cli == "codex" else ""))
    shutil.rmtree(sandbox_root, ignore_errors=True)
    report = {"label": label, **execution, "init": init, "leak_markers": leaks}
    (output / "canary.json").write_text(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    for requested in sys.argv[1:]:
        summary = check(requested)
        print(json.dumps({key: summary[key] for key in ("label", "exit_code", "duration_seconds", "leak_markers")}))
