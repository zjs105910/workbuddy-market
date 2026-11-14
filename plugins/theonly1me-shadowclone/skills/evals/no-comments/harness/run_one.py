import json
import os
import shutil
import signal
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from harness.agents import build_invocation, extract_usage, read_events
from harness.config import RUN_TIMEOUT_SECONDS, RUNS_DIR, WORK_ROOT, Setting, build_prompt, load_settings
from harness.grading import grade_code, remove_grading_files, run_hidden_tests, run_own_tests, run_seed_tests
from harness.workspace import changed_python_files, create_workspace, export_diff

FINAL_SNAPSHOT_IGNORE = shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache", "*.pyc")


def run_directory(*, setting: Setting, condition: str, repetition: int, runs_dir: Path = RUNS_DIR) -> Path:
    return runs_dir / setting.label / condition / f"{repetition:02d}"


def execute_agent(*, setting: Setting, workspace: Path, home: Path, prompt: str, transcript: Path) -> dict:
    invocation = build_invocation(setting=setting, workspace=workspace, home=home)
    started = time.monotonic()
    timed_out = False
    with transcript.open("w") as output, (transcript.with_suffix(".stderr")).open("w") as errors:
        process = subprocess.Popen(
            invocation.command,
            cwd=workspace,
            env=invocation.environment,
            stdin=subprocess.PIPE,
            stdout=output,
            stderr=errors,
            text=True,
            start_new_session=True,
        )
        try:
            process.communicate(prompt, timeout=RUN_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
    return {
        "exit_code": process.returncode,
        "timed_out": timed_out,
        "duration_seconds": round(time.monotonic() - started, 1),
    }


def run_one(*, setting: Setting, condition: str, repetition: int, runs_dir: Path = RUNS_DIR) -> dict:
    destination = run_directory(setting=setting, condition=condition, repetition=repetition, runs_dir=runs_dir)
    result_path = destination / "result.json"
    if result_path.exists():
        return json.loads(result_path.read_text())
    destination.mkdir(parents=True, exist_ok=True)

    sandbox_root = WORK_ROOT / f"run-{uuid.uuid4().hex[:10]}"
    workspace = sandbox_root / "ws"
    home = sandbox_root / "home"
    (home / "tmp").mkdir(parents=True)
    create_workspace(workspace)

    prompt = build_prompt(condition)
    (destination / "prompt.txt").write_text(prompt)
    started_at = datetime.now(timezone.utc).isoformat()
    execution = execute_agent(
        setting=setting, workspace=workspace, home=home, prompt=prompt, transcript=destination / "transcript.jsonl"
    )

    edited = bool(changed_python_files(workspace))
    infra_error = None
    if execution["exit_code"] != 0 and not edited and not execution["timed_out"]:
        infra_error = "agent exited non-zero without editing any file"

    result = {
        "label": setting.label,
        "cli": setting.cli,
        "model": setting.model,
        "effort": setting.effort,
        "condition": condition,
        "repetition": repetition,
        "started_at": started_at,
        **execution,
        "infra_error": infra_error,
        "usage": extract_usage(cli=setting.cli, events=read_events(destination / "transcript.jsonl")),
    }
    if infra_error is None:
        export_diff(workspace, destination / "diff.patch")
        result["code"] = grade_code(workspace)
        result["hidden_tests"] = run_hidden_tests(workspace)
        result["seed_tests"] = run_seed_tests(workspace)
        result["own_tests"] = run_own_tests(workspace)
        remove_grading_files(workspace)
        shutil.copytree(workspace, destination / "final", ignore=FINAL_SNAPSHOT_IGNORE, dirs_exist_ok=True)
        new_comments = result["code"]["new_comments"]
        result["comment_compliant"] = (
            sum(new_comments.values()) == 0 if condition == "B" else None
        )
    result_path.write_text(json.dumps(result, indent=2))
    shutil.rmtree(sandbox_root, ignore_errors=True)
    return result


def main() -> None:
    label, condition, repetition = sys.argv[1], sys.argv[2], int(sys.argv[3])
    setting = next(item for item in load_settings() if item.label == label)
    result = run_one(setting=setting, condition=condition, repetition=repetition)
    print(json.dumps({key: result.get(key) for key in ("label", "condition", "repetition", "exit_code", "infra_error", "hidden_tests")}))


if __name__ == "__main__":
    main()
