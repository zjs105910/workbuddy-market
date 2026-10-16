import json
import shutil
import uuid
from pathlib import Path

from graders.judge.prepare import render_implementation
from harness.agents import read_events
from harness.config import WORK_ROOT, Setting
from harness.run_one import execute_agent

JUDGES = (
    Setting("judge-opus", "claude", "claude-opus-5-5", "high"),
    Setting("judge-sol", "codex", "gpt-6.1-sol", "high"),
)
RUBRIC = (Path(__file__).parent / "rubric.md").read_text()
CLAIM_COUNT = 10


def build_prompt(*, implementation_x: str, implementation_y: str) -> str:
    return (
        "Two implementations X and Y add the same feature to a Python billing library. "
        "Comments were removed from both. Do not use any tool. Reply with one JSON object only.\n\n"
        f"{RUBRIC}\n"
        "Then decide which implementation is easier to read, understand and change. "
        "Ignore correctness, length by itself, and style trivia such as blank lines.\n\n"
        'JSON shape: {"x_claims": [10 booleans], "y_claims": [10 booleans], "preferred": "X" or "Y" or "tie", "reason": "one sentence"}\n\n'
        f"## Implementation X\n{implementation_x}\n\n## Implementation Y\n{implementation_y}\n"
    )


def extract_reply(*, cli: str, events: list[dict]) -> str:
    if cli == "claude":
        results = [event for event in events if event.get("type") == "result"]
        return results[-1].get("result", "") if results else ""
    messages = [
        event["item"]["text"]
        for event in events
        if event.get("type") == "item.completed" and event["item"].get("type") == "agent_message"
    ]
    return messages[-1] if messages else ""


def parse_verdict(reply: str) -> dict | None:
    start, end = reply.find("{"), reply.rfind("}")
    if start < 0 or end < start:
        return None
    try:
        verdict = json.loads(reply[start : end + 1])
    except json.JSONDecodeError:
        return None
    claims_valid = all(
        isinstance(verdict.get(key), list) and len(verdict[key]) == CLAIM_COUNT
        for key in ("x_claims", "y_claims")
    )
    return verdict if claims_valid and verdict.get("preferred") in {"X", "Y", "tie"} else None


def judge_once(*, judge: Setting, final_x: Path, final_y: Path) -> dict | None:
    sandbox_root = WORK_ROOT / f"judge-{uuid.uuid4().hex[:8]}"
    (sandbox_root / "ws").mkdir(parents=True)
    (sandbox_root / "home" / "tmp").mkdir(parents=True)
    transcript = sandbox_root / "transcript.jsonl"
    prompt = build_prompt(
        implementation_x=render_implementation(final_x), implementation_y=render_implementation(final_y)
    )
    execute_agent(
        setting=judge, workspace=sandbox_root / "ws", home=sandbox_root / "home", prompt=prompt, transcript=transcript
    )
    verdict = parse_verdict(extract_reply(cli=judge.cli, events=read_events(transcript)))
    shutil.rmtree(sandbox_root, ignore_errors=True)
    return verdict
