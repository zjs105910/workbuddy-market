import argparse
import random
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from harness.config import CONDITIONS, RUNS_DIR, Setting, load_settings
from harness.run_one import run_directory, run_one

MAX_INFRA_ATTEMPTS = 3
SCHEDULE_SEED = 20261005
print_lock = threading.Lock()


def build_schedule(*, settings: list[Setting], first_repetition: int, repetitions: int) -> list[tuple[Setting, str, int]]:
    cells = [
        (setting, condition, repetition)
        for repetition in range(first_repetition, repetitions + 1)
        for setting in settings
        for condition in CONDITIONS
    ]
    random.Random(SCHEDULE_SEED).shuffle(cells)
    return cells


def run_with_retries(*, setting: Setting, condition: str, repetition: int, runs_dir: Path) -> dict:
    attempts_log = runs_dir / "infra_failures.log"
    for attempt in range(1, MAX_INFRA_ATTEMPTS + 1):
        result = run_one(setting=setting, condition=condition, repetition=repetition, runs_dir=runs_dir)
        if not result["infra_error"]:
            return result
        with attempts_log.open("a") as log:
            log.write(f"{setting.label} {condition} {repetition} attempt {attempt}: {result['infra_error']}\n")
        shutil.rmtree(run_directory(setting=setting, condition=condition, repetition=repetition, runs_dir=runs_dir))
    return result


def report_progress(result: dict) -> None:
    hidden = result.get("hidden_tests") or {}
    with print_lock:
        print(
            f"{result['label']:16} {result['condition']} rep={result['repetition']:02d} "
            f"exit={result['exit_code']} secs={result['duration_seconds']} "
            f"hidden={hidden.get('passed')}/{hidden.get('total')} infra={result['infra_error']}",
            flush=True,
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--first-repetition", type=int, default=1)
    parser.add_argument("--repetitions", type=int, required=True)
    parser.add_argument("--concurrency", type=int, default=3)
    parser.add_argument("--runs-dir", type=Path, default=RUNS_DIR)
    parser.add_argument("--labels", nargs="*")
    arguments = parser.parse_args()

    settings = [item for item in load_settings() if not arguments.labels or item.label in arguments.labels]
    schedule = build_schedule(
        settings=settings, first_repetition=arguments.first_repetition, repetitions=arguments.repetitions
    )
    arguments.runs_dir.mkdir(parents=True, exist_ok=True)

    def work(cell: tuple[Setting, str, int]) -> None:
        setting, condition, repetition = cell
        report_progress(
            run_with_retries(setting=setting, condition=condition, repetition=repetition, runs_dir=arguments.runs_dir)
        )

    with ThreadPoolExecutor(max_workers=arguments.concurrency) as pool:
        list(pool.map(work, schedule))


if __name__ == "__main__":
    main()
