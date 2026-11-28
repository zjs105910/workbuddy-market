import argparse
import json
import random
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from graders.judge.invoke import JUDGES, judge_once
from harness.config import RUNS_DIR, load_settings

PAIRING_SEED = 20261006
write_lock = threading.Lock()


BATCH_SIZE = 10


def eligible_repetitions(*, runs_dir: Path, label: str, condition: str, batch: int) -> list[int]:
    folders = sorted((runs_dir / label / condition).glob("*/result.json"))
    repetitions = [int(folder.parent.name) for folder in folders]
    return [rep for rep in repetitions if (rep - 1) // BATCH_SIZE + 1 == batch]


def pairing_seed(*, label: str, batch: int) -> str:
    suffix = "" if batch == 1 else f"-batch{batch}"
    return f"{PAIRING_SEED}-{label}{suffix}"


def build_pairs(*, runs_dir: Path, label: str) -> list[tuple[int, int]]:
    pairs = []
    for batch in range(1, 100):
        a_reps = eligible_repetitions(runs_dir=runs_dir, label=label, condition="A", batch=batch)
        b_reps = eligible_repetitions(runs_dir=runs_dir, label=label, condition="B", batch=batch)
        if not a_reps and not b_reps:
            break
        shuffled = random.Random(pairing_seed(label=label, batch=batch)).sample(b_reps, len(b_reps))
        pairs.extend(zip(a_reps, shuffled))
    return pairs


def final_directory(*, runs_dir: Path, label: str, condition: str, repetition: int) -> Path:
    return runs_dir / label / condition / f"{repetition:02d}" / "final"


def judge_task(*, runs_dir: Path, label: str, a_rep: int, b_rep: int, a_is_x: bool, judge_index: int) -> dict:
    final_a = final_directory(runs_dir=runs_dir, label=label, condition="A", repetition=a_rep)
    final_b = final_directory(runs_dir=runs_dir, label=label, condition="B", repetition=b_rep)
    final_x, final_y = (final_a, final_b) if a_is_x else (final_b, final_a)
    verdict = judge_once(judge=JUDGES[judge_index], final_x=final_x, final_y=final_y)
    return {
        "label": label, "a_rep": a_rep, "b_rep": b_rep, "a_is_x": a_is_x,
        "judge": JUDGES[judge_index].label, "verdict": verdict,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs-dir", type=Path, default=RUNS_DIR)
    parser.add_argument("--concurrency", type=int, default=4)
    arguments = parser.parse_args()
    output = arguments.runs_dir / "judgments.jsonl"
    done = {line for line in output.read_text().splitlines()} if output.exists() else set()
    done_keys = {(row["label"], row["a_rep"], row["b_rep"], row["a_is_x"], row["judge"]) for row in map(json.loads, done)}

    tasks = []
    for setting in load_settings():
        for a_rep, b_rep in build_pairs(runs_dir=arguments.runs_dir, label=setting.label):
            for a_is_x in (True, False):
                for judge_index, judge in enumerate(JUDGES):
                    if (setting.label, a_rep, b_rep, a_is_x, judge.label) not in done_keys:
                        tasks.append(dict(runs_dir=arguments.runs_dir, label=setting.label, a_rep=a_rep,
                                          b_rep=b_rep, a_is_x=a_is_x, judge_index=judge_index))

    def work(task: dict) -> None:
        row = judge_task(**task)
        with write_lock, output.open("a") as handle:
            handle.write(json.dumps(row) + "\n")

    with ThreadPoolExecutor(max_workers=arguments.concurrency) as pool:
        list(pool.map(work, tasks))


if __name__ == "__main__":
    main()
