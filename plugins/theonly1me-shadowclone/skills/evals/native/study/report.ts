import type { CoverageEntry } from "./coverage";
import type { MatrixReceipt } from "./matrix";
import type { RunArmName, RunRecord } from "./record";
import { studyArms, type KeyGroup, type PersonalArm, type StudyArm, type StudySuite } from "./schema";
import { taskResults } from "./taskResults";
import { summarizeOutcomes } from "../../shared/outcome";

type Observation = { readonly taskId: string; readonly sessionId: string; readonly keyItem: string; readonly passed: boolean; readonly skillRead: boolean | null };
type Filter = (observation: Observation) => boolean;

export function randomSource(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let value = state;
    value = Math.imul(value ^ (value >>> 15), value | 1);
    value ^= value + Math.imul(value ^ (value >>> 7), value | 61);
    return ((value ^ (value >>> 14)) >>> 0) / 4294967296;
  };
}

function coveringSkill(entry: CoverageEntry | undefined): string | null {
  const match = entry?.file ? /^(home|workspace)\/.*skills\/([^/]+)\/SKILL\.md$/.exec(entry.file) : null;
  return match?.[1] && match[2] ? `${match[1]}:${match[2]}` : null;
}

export function observations(options: {
  suite: StudySuite; runs: readonly RunRecord[]; arm: RunArmName; coverage: Partial<Record<PersonalArm, readonly CoverageEntry[]>>;
}): Observation[] {
  const coverage = options.arm === "bare" || options.arm === "told" ? [] : options.coverage[options.arm] ?? [];
  return options.suite.tasks.flatMap((task) => options.runs.filter((run) => run.arm === options.arm && run.taskId === task.id)
    .flatMap((run) => task.checks.flatMap((check) => {
      const verdict = run.checks.find((entry) => entry.id === check.id)?.verdict ?? "unknown";
      if (verdict !== "pass" && verdict !== "fail") return [];
      const skill = coveringSkill(coverage.find((entry) => entry.keyItem === check.keyItem));
      const read = skill === null ? null : run.turns.some((turn) => turn.skillReads.includes(skill));
      return [{ taskId: task.id, sessionId: `${run.arm}:${run.taskId}:${run.repeat}`, keyItem: check.keyItem, passed: verdict === "pass", skillRead: read }];
    })));
}

export function taskWeightedRate(options: { observations: readonly Observation[]; tasks: readonly string[] }): number | null {
  const rates = options.tasks.flatMap((taskId) => {
    const entries = options.observations.filter((entry) => entry.taskId === taskId);
    return entries.length === 0 ? [] : [entries.filter((entry) => entry.passed).length / entries.length];
  });
  return rates.length === 0 ? null : rates.reduce((total, rate) => total + rate, 0) / rates.length;
}

function percentile(values: readonly number[], fraction: number): number | null {
  const sorted = values.toSorted((left, right) => left - right);
  return sorted.length === 0 ? null : sorted[Math.min(sorted.length - 1, Math.floor(fraction * sorted.length))] ?? null;
}

function pick<Value>(values: readonly Value[], random: () => number): Value[] {
  return values.flatMap(() => {
    const value = values[Math.floor(random() * values.length)];
    return value === undefined ? [] : [value];
  });
}

function sampledRate(options: { entries: readonly Observation[]; tasks: readonly string[]; random: () => number }): number | null {
  const observations = options.tasks.flatMap((taskId, index) => {
    const sessions = Map.groupBy(
      options.entries.filter((entry) => entry.taskId === taskId),
      (entry) => entry.sessionId,
    );

    return pick([...sessions.values()], options.random).flatMap((session) =>
      session.map((entry) => ({ ...entry, taskId: `${taskId}#${index}` })),
    );
  });
  return taskWeightedRate({ observations, tasks: options.tasks.map((taskId, index) => `${taskId}#${index}`) });
}

function interval(rates: readonly number[]) {
  const lower = percentile(rates, 0.025);
  const upper = percentile(rates, 0.975);
  return { lower, upper, halfWidth: lower === null || upper === null ? null : (upper - lower) / 2 };
}

export function bootstrapRate(options: { observations: readonly Observation[]; tasks: readonly string[]; seed: number; samples: number }) {
  const random = randomSource(options.seed);
  const rates: number[] = [];
  for (let sample = 0; sample < options.samples; sample += 1) {
    const rate = sampledRate({ entries: options.observations, tasks: pick(options.tasks, random), random });
    if (rate !== null) rates.push(rate);
  }
  return { point: taskWeightedRate({ observations: options.observations, tasks: options.tasks }), ...interval(rates) };
}

export function bootstrapDifference(options: {
  left: readonly Observation[]; right: readonly Observation[]; tasks: readonly string[]; seed: number; samples: number;
}) {
  const random = randomSource(options.seed);
  const differences: number[] = [];
  for (let sample = 0; sample < options.samples; sample += 1) {
    const tasks = pick(options.tasks, random);
    const left = sampledRate({ entries: options.left, tasks, random });
    const right = sampledRate({ entries: options.right, tasks, random });
    if (left !== null && right !== null) differences.push(left - right);
  }
  const left = taskWeightedRate({ observations: options.left, tasks: options.tasks });
  const right = taskWeightedRate({ observations: options.right, tasks: options.tasks });
  const bounds = interval(differences);
  return { point: left === null || right === null ? null : left - right, ...bounds, supported: bounds.lower !== null && bounds.lower > 0 };
}

export function studyReport(options: {
  suite: StudySuite; receipt: MatrixReceipt; coverage: Partial<Record<PersonalArm, readonly CoverageEntry[]>>;
}) {
  const tasks = options.suite.tasks.map((task) => task.id);
  const runsInView = options.receipt.runs.filter((run) => tasks.includes(run.taskId));
  const group = (keyItem: string) => options.suite.keyItems.find((item) => item.id === keyItem)?.group;
  const byArm = (arm: StudyArm, filter: Filter = () => true) =>
    observations({ suite: options.suite, runs: runsInView, arm, coverage: options.coverage }).filter(filter);
  const withoutResolved: Filter = (entry) => group(entry.keyItem) !== "resolved";
  const covered = (arm: StudyArm): Filter => (entry) => arm !== "bare" &&
    (options.coverage[arm]?.some((item) => item.keyItem === entry.keyItem && item.status === "covered") ?? false);
  const rate = (arm: StudyArm, filter?: Filter) => taskWeightedRate({ observations: byArm(arm, filter), tasks });
  const compare = (left: StudyArm, right: StudyArm, filter?: Filter) => bootstrapDifference({
    left: byArm(left, filter), right: byArm(right, filter), tasks, seed: options.suite.analysis.bootstrapSeed, samples: options.suite.analysis.bootstrapSamples,
  });
  const groups: KeyGroup[] = ["personal", "wizard", "learned", "resolved"];

  return {
    protocol: "preference-study-v1", scorerVersion: "session-bootstrap-2", status: options.receipt.status, failure: options.receipt.failure,
    recordedRuns: runsInView.length,
    productRevisions: Object.fromEntries(studyArms.map((arm) => [arm,
      [...new Set(runsInView.filter((run) => run.arm === arm)
        .map((run) => run.productCommit ?? "unknown"))].sort(),
    ])),
    arms: studyArms.map((arm) => {
      const runs = runsInView.filter((run) => run.arm === arm);
      const all = byArm(arm);
      const read = all.filter((entry) => entry.skillRead === true);
      const unread = all.filter((entry) => entry.skillRead === false);
      return {
        arm, adherence: rate(arm), fidelity: rate(arm, covered(arm)),
        workflowOutcomes: summarizeOutcomes(runs.flatMap((run) => run.outcome ? [run.outcome] : [])),
        interval: bootstrapRate({ observations: all, tasks, seed: options.suite.analysis.bootstrapSeed, samples: options.suite.analysis.bootstrapSamples }),
        groups: Object.fromEntries(groups.map((name) => [name, rate(arm, (entry) => group(entry.keyItem) === name)])),
        adherenceWhenSkillRead: read.length === 0 ? null : read.filter((entry) => entry.passed).length / read.length,
        adherenceWhenSkillUnread: unread.length === 0 ? null : unread.filter((entry) => entry.passed).length / unread.length,
        runs: runs.length, errors: runs.filter((run) => run.status === "error").length,
        correctnessFailures: runs.filter((run) => run.correctness === "fail").length,
        safetyFailures: runs.filter((run) => run.safety === "fail").length,
        notApplicable: runs.flatMap((run) => run.checks).filter((check) => check.verdict === "not-applicable").length,
        unknown: runs.flatMap((run) => run.checks).filter((check) => check.verdict === "unknown").length,
      };
    }),
    hypotheses: {
      deepOverBare: compare("deep", "bare"), deepOverOriginal: compare("deep", "original"), firstTimeOverBare: compare("first-time", "bare"),
      deepOverBareWithoutResolved: compare("deep", "bare", withoutResolved),
      deepOverOriginalWithoutResolved: compare("deep", "original", withoutResolved),
      deepOverFirstTimeWithoutResolved: compare("deep", "first-time", withoutResolved),
    },
    counts: taskResults({ suite: options.suite, runs: runsInView }),
    droppedChecks: options.suite.droppedChecks,
  };
}
