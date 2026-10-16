import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEED_REPO = ROOT / "task" / "seed_repo"
HIDDEN_TESTS = ROOT / "graders" / "hidden_tests"
RUNS_DIR = ROOT / "runs"
VENV_BIN = ROOT / ".venv" / "bin"
WORK_ROOT = Path(os.environ.get("EVAL_WORK_ROOT", Path(tempfile.gettempdir()) / "ledger-evals"))
CODEX_HOME = WORK_ROOT / "codex-home"
CLAUDE_BINARY = Path(os.environ.get("EVAL_CLAUDE_BINARY") or shutil.which("claude") or "claude")
CODEX_BINARY = Path(os.environ.get("EVAL_CODEX_BINARY") or shutil.which("codex") or "codex")
RUN_TIMEOUT_SECONDS = 30 * 60
CONDITIONS = ("A", "B")


@dataclass(frozen=True)
class Setting:
    label: str
    cli: str
    model: str
    effort: str


def load_settings() -> list[Setting]:
    entries = json.loads((ROOT / "harness" / "matrix.json").read_text())
    return [Setting(**entry) for entry in entries]


def build_prompt(condition: str) -> str:
    base = (ROOT / "task" / "prompt_base.md").read_text().rstrip("\n")
    if condition == "A":
        return base + "\n"
    ban = (ROOT / "task" / "ban_suffix.md").read_text().strip()
    return f"{base}\n\n{ban}\n"
