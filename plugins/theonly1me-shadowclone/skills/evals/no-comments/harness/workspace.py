import shutil
import subprocess
from pathlib import Path

from harness.config import SEED_REPO, VENV_BIN

BASELINE_TAG = "baseline"
GIT_IDENTITY = ["-c", "user.name=eval", "-c", "user.email=eval@example.invalid"]


def run_git(workspace: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", *GIT_IDENTITY, *arguments],
        cwd=workspace,
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout


def create_workspace(workspace: Path) -> None:
    shutil.copytree(SEED_REPO, workspace)
    run_git(workspace, "init", "-q")
    run_git(workspace, "add", "-A")
    run_git(workspace, "commit", "-q", "-m", "baseline")
    run_git(workspace, "tag", BASELINE_TAG)


def changed_python_files(workspace: Path) -> list[str]:
    run_git(workspace, "add", "-A")
    output = run_git(workspace, "diff", "--cached", "--name-only", "--diff-filter=AM", BASELINE_TAG)
    return [name for name in output.splitlines() if name.endswith(".py")]


def baseline_source(workspace: Path, relative_path: str) -> str:
    completed = subprocess.run(
        ["git", "show", f"{BASELINE_TAG}:{relative_path}"],
        cwd=workspace,
        capture_output=True,
        text=True,
    )
    return completed.stdout if completed.returncode == 0 else ""


def export_diff(workspace: Path, destination: Path) -> None:
    run_git(workspace, "add", "-A")
    destination.write_text(run_git(workspace, "diff", "--cached", BASELINE_TAG))


def run_environment(home: Path) -> dict[str, str]:
    return {
        "PATH": f"{VENV_BIN}:/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin:/opt/homebrew/bin",
        "HOME": str(home),
        "TMPDIR": str(home / "tmp"),
        "LANG": "en_US.UTF-8",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
