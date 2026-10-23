import random
import statistics

BOOTSTRAP_ROUNDS = 10000
STATS_SEED = 20261007


def mean_ci(values: list[float]) -> tuple[float, float, float]:
    if not values:
        return float("nan"), float("nan"), float("nan")
    generator = random.Random(STATS_SEED)
    means = sorted(
        statistics.fmean(generator.choices(values, k=len(values))) for _ in range(BOOTSTRAP_ROUNDS)
    )
    return statistics.fmean(values), means[int(0.025 * BOOTSTRAP_ROUNDS)], means[int(0.975 * BOOTSTRAP_ROUNDS)]


def difference_ci(*, group_a: list[float], group_b: list[float]) -> tuple[float, float, float]:
    if not group_a or not group_b:
        return float("nan"), float("nan"), float("nan")
    generator = random.Random(STATS_SEED)
    differences = sorted(
        statistics.fmean(generator.choices(group_b, k=len(group_b)))
        - statistics.fmean(generator.choices(group_a, k=len(group_a)))
        for _ in range(BOOTSTRAP_ROUNDS)
    )
    observed = statistics.fmean(group_b) - statistics.fmean(group_a)
    return observed, differences[int(0.025 * BOOTSTRAP_ROUNDS)], differences[int(0.975 * BOOTSTRAP_ROUNDS)]


def sign_flip_p_value(values: list[float], *, center: float = 0.5) -> float:
    if not values:
        return float("nan")
    deviations = [value - center for value in values]
    observed = abs(sum(deviations))
    generator = random.Random(STATS_SEED)
    extreme = 0
    for _ in range(BOOTSTRAP_ROUNDS):
        flipped = sum(deviation if generator.random() < 0.5 else -deviation for deviation in deviations)
        extreme += abs(flipped) >= observed - 1e-12
    return (extreme + 1) / (BOOTSTRAP_ROUNDS + 1)
