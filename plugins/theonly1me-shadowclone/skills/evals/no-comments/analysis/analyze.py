import json
import sys
from pathlib import Path

from analysis.load import b_score, claim_rate, load_judgments, load_results, pair_scores
from analysis.stats import difference_ci, mean_ci, sign_flip_p_value
from harness.config import RUNS_DIR, load_settings

METRICS = {
    "hidden_pass_rate": lambda r: r["hidden_tests"]["pass_rate"],
    "hidden_all_pass": lambda r: float(r["hidden_tests"]["all_pass"]),
    "code_lines": lambda r: r["code"]["source_metrics"]["code_lines"],
    "function_count": lambda r: r["code"]["source_metrics"]["function_count"],
    "mean_function_length": lambda r: r["code"]["source_metrics"]["mean_function_length"],
    "max_function_length": lambda r: r["code"]["source_metrics"]["max_function_length"],
    "max_complexity": lambda r: r["code"]["source_metrics"]["max_complexity"],
    "mean_identifier_length": lambda r: r["code"]["source_metrics"]["mean_identifier_length"],
    "max_nesting_depth": lambda r: r["code"]["source_metrics"]["max_nesting_depth"],
    "ruff_warnings": lambda r: r["code"]["source_metrics"]["ruff_warnings"],
    "new_source_comments": lambda r: r["code"]["new_comments"]["source"],
    "duration_seconds": lambda r: r["duration_seconds"],
}


def metric_table(results: list[dict], label: str) -> dict:
    cells = {"A": [r for r in results if r["label"] == label and r["condition"] == "A" and "code" in r],
             "B": [r for r in results if r["label"] == label and r["condition"] == "B" and "code" in r]}
    table = {}
    for name, extract in METRICS.items():
        values = {condition: [extract(r) for r in runs] for condition, runs in cells.items()}
        table[name] = {
            "A": mean_ci(values["A"]),
            "B": mean_ci(values["B"]),
            "B_minus_A": difference_ci(group_a=values["A"], group_b=values["B"]),
        }
    return {"runs": {condition: len(runs) for condition, runs in cells.items()}, "metrics": table}


def judge_summary(rows: list[dict], label: str | None) -> dict:
    selected = [row for row in rows if label is None or row["label"] == label]
    scores = list(pair_scores(selected).values())
    x_votes = [row["verdict"]["preferred"] == "X" for row in selected if row["verdict"]["preferred"] != "tie"]
    return {
        "pairs": len(scores),
        "b_win_rate": mean_ci(scores),
        "p_value": sign_flip_p_value(scores),
        "x_position_rate": sum(x_votes) / len(x_votes) if x_votes else float("nan"),
        "rubric_claims_true": {"A": claim_rate(selected, condition="A"), "B": claim_rate(selected, condition="B")},
        "by_judge": {
            judge: mean_ci([b_score(row) for row in selected if row["judge"] == judge])
            for judge in sorted({row["judge"] for row in selected})
        },
    }


def compliance(results: list[dict], label: str) -> dict:
    banned = [r for r in results if r["label"] == label and r["condition"] == "B" and "comment_compliant" in r]
    return {"b_runs": len(banned), "compliant": sum(1 for r in banned if r["comment_compliant"])}


BATCH_SIZE = 10


def batch_of(repetition: int) -> int:
    return (repetition - 1) // BATCH_SIZE + 1


def build_report(results: list[dict], judgments: list[dict]) -> dict:
    return {
        "pooled_judge": judge_summary(judgments, None),
        "settings": {
            setting.label: {
                **metric_table(results, setting.label),
                "judge": judge_summary(judgments, setting.label),
                "compliance": compliance(results, setting.label),
                "infra_failures": sum(1 for r in results if r["label"] == setting.label and r["infra_error"]),
            }
            for setting in load_settings()
        },
    }


def main() -> None:
    runs_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else RUNS_DIR
    results = load_results(runs_dir)
    judgments = load_judgments(runs_dir)
    report = build_report(results, judgments)
    batches = sorted({batch_of(r["repetition"]) for r in results})
    if len(batches) > 1:
        report["batches"] = {
            str(batch): build_report(
                [r for r in results if batch_of(r["repetition"]) == batch],
                [row for row in judgments if batch_of(row["a_rep"]) == batch],
            )
            for batch in batches
        }
    (runs_dir / "analysis.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report["pooled_judge"], indent=2))


if __name__ == "__main__":
    main()
