import json
from pathlib import Path


def load_results(runs_dir: Path) -> list[dict]:
    return [json.loads(path.read_text()) for path in sorted(runs_dir.glob("*/*/*/result.json"))]


def load_judgments(runs_dir: Path) -> list[dict]:
    path = runs_dir / "judgments.jsonl"
    if not path.exists():
        return []
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    return [row for row in rows if row["verdict"]]


def b_score(row: dict) -> float:
    preferred = row["verdict"]["preferred"]
    if preferred == "tie":
        return 0.5
    chose_x = preferred == "X"
    return 1.0 if chose_x != row["a_is_x"] else 0.0


def pair_scores(rows: list[dict]) -> dict[tuple, float]:
    grouped: dict[tuple, list[float]] = {}
    for row in rows:
        grouped.setdefault((row["label"], row["a_rep"], row["b_rep"]), []).append(b_score(row))
    return {key: sum(scores) / len(scores) for key, scores in grouped.items()}


def claim_rate(rows: list[dict], *, condition: str) -> float:
    rates = []
    for row in rows:
        is_a_side = (condition == "A") == row["a_is_x"]
        claims = row["verdict"]["x_claims" if is_a_side else "y_claims"]
        rates.append(sum(bool(claim) for claim in claims) / len(claims))
    return sum(rates) / len(rates) if rates else float("nan")
