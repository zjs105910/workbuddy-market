import type { FrozenSuite, Receipt, Setup } from "./schema";
import { setupPerformance } from "./scoring";

function fixedGroupMeans(options: { suite: FrozenSuite; receipt: Receipt; setup: Setup }) {
  return [0, 1, 2].map(
    (repetition) => setupPerformance({ ...options, repetitions: [repetition] }).score,
  );
}

export function fixedSuiteInterval(options: {
  suite: FrozenSuite;
  receipt: Receipt;
  candidate: Setup;
  baseline?: Setup;
}) {
  if (options.suite.repetitions !== 3) return null;
  const candidate = fixedGroupMeans({
    suite: options.suite,
    receipt: options.receipt,
    setup: options.candidate,
  });
  const baseline = options.baseline
    ? fixedGroupMeans({ suite: options.suite, receipt: options.receipt, setup: options.baseline })
    : [0, 0, 0];
  if (candidate.some((value) => value === null) || baseline.some((value) => value === null))
    return null;
  const distribution: number[] = [];
  for (const first of [0, 1, 2])
    for (const second of [0, 1, 2])
      for (const third of [0, 1, 2]) {
        const differences = [first, second, third].map(
          (index) => (candidate[index] ?? 0) - (baseline[index] ?? 0),
        );
        distribution.push(differences.reduce((total, value) => total + value, 0) / 3);
      }
  distribution.sort((left, right) => left - right);
  const quantile = (probability: number) =>
    distribution[Math.floor(probability * (distribution.length - 1))] ?? 0;
  return {
    lower: quantile(0.025),
    upper: quantile(0.975),
    method:
      "exact percentile bootstrap of three matched whole-session/preparation groups, fixed case mix",
    groups: 3,
    limitation:
      "Three preparations give coarse intervals; host cohorts sharing preparations are correlated and must not be pooled as independent samples.",
  };
}
