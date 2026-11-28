import shutil
import subprocess
import xml.etree.ElementTree as ElementTree
from pathlib import Path

from graders.comments import count_new_comments
from graders.static_metrics import measure_files
from harness.config import HIDDEN_TESTS, SEED_REPO, VENV_BIN
from harness.workspace import baseline_source, changed_python_files

PYTEST_TIMEOUT_SECONDS = 180


def run_pytest(*, workspace: Path, target: str) -> dict:
    report = workspace / f"report-{target}.xml"
    command = [
        str(VENV_BIN / "python"), "-m", "pytest", target,
        "-q", "-p", "no:cacheprovider", f"--junitxml={report}",
    ]
    try:
        subprocess.run(command, cwd=workspace, capture_output=True, timeout=PYTEST_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        return {"total": 0, "passed": 0, "pass_rate": 0.0, "all_pass": False, "timed_out": True}
    return summarize_report(report)


def summarize_report(report: Path) -> dict:
    if not report.exists():
        return {"total": 0, "passed": 0, "pass_rate": 0.0, "all_pass": False, "no_report": True}
    suite = ElementTree.parse(report).getroot().find("testsuite")
    total = int(suite.get("tests", 0))
    bad = int(suite.get("failures", 0)) + int(suite.get("errors", 0)) + int(suite.get("skipped", 0))
    passed = total - bad
    return {
        "total": total,
        "passed": passed,
        "pass_rate": passed / total if total else 0.0,
        "all_pass": total > 0 and bad == 0,
    }


def run_hidden_tests(workspace: Path) -> dict:
    shutil.copytree(HIDDEN_TESTS, workspace / "tests_hidden", ignore=shutil.ignore_patterns("__pycache__"))
    return run_pytest(workspace=workspace, target="tests_hidden")


def run_seed_tests(workspace: Path) -> dict:
    shutil.copytree(SEED_REPO / "tests", workspace / "tests_seed", ignore=shutil.ignore_patterns("__pycache__"))
    return run_pytest(workspace=workspace, target="tests_seed")


def run_own_tests(workspace: Path) -> dict:
    if not (workspace / "tests").exists():
        return {"total": 0, "passed": 0, "pass_rate": 0.0, "all_pass": False}
    return run_pytest(workspace=workspace, target="tests")


def is_source_file(relative_path: str) -> bool:
    return relative_path.startswith("ledger/")


def grade_code(workspace: Path) -> dict:
    changed = changed_python_files(workspace)
    new_comments = {"source": 0, "tests": 0}
    for relative_path in changed:
        before = baseline_source(workspace, relative_path)
        after = (workspace / relative_path).read_text()
        bucket = "source" if is_source_file(relative_path) else "tests"
        new_comments[bucket] += count_new_comments(before=before, after=after)
    source_paths = [workspace / name for name in changed if is_source_file(name)]
    test_paths = [workspace / name for name in changed if name.startswith("tests/")]
    return {
        "changed_files": changed,
        "new_comments": new_comments,
        "source_metrics": measure_files(source_paths),
        "test_metrics": measure_files(test_paths),
    }


def remove_grading_files(workspace: Path) -> None:
    for name in ("tests_hidden", "tests_seed"):
        shutil.rmtree(workspace / name, ignore_errors=True)
    for report in workspace.glob("report-*.xml"):
        report.unlink()
