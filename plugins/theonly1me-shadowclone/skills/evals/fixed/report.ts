import { z } from "zod";
import type { MatrixReceipt } from "../native/study/matrix";
import { deterministicChecks } from "../native/study/checks";
import { bootstrapRate, bootstrapDifference } from "../native/study/report";
import { fingerprint } from "../shared/structured";
import { fixedDefinition, fixedArms, internalArms, armNames } from "./definition";
import type { FixedSuite } from "./freeze";

const verdictSchema = z.enum(["pass", "fail", "unknown"]);
export const fixedReportSchema = z.object({
  protocol: z.literal("preference-respect-v1"), scorerVersion: z.literal("fixed-task-1"), benchmarkFingerprint: z.string(),
  graderFingerprint: z.string(),
  product: z.object({ commit: z.string(), tree: z.string(), branch: z.string() }),
  configuration: z.object({ engine: z.string(), cliVersion: z.string(), model: z.string(), effort: z.string(), repetitions: z.number(), limits: z.unknown(), runtime: z.object({ bun: z.string(), typescript: z.string() }) }),
  status: z.enum(["complete", "incomplete"]),
  cells: z.array(z.object({ arm: z.enum(fixedArms), taskId: z.string(), repeat: z.number(), verdict: verdictSchema,
    adherence: verdictSchema, correctness: verdictSchema, safety: verdictSchema, error: z.string().nullable(),
    checks: z.array(z.object({ id: z.string(), keyItem: z.string(), verdict: z.string(), evidence: z.string() })),
    verificationEvidence: z.string(), safetyEvidence: z.string(),
    costUsd: z.number().nullable(), durationMs: z.number(), skillReads: z.array(z.string()) })),
  arms: z.array(z.object({ arm: z.enum(fixedArms), expected: z.number(), passed: z.number(), failed: z.number(), unknown: z.number(),
    score: z.number().nullable(), adherenceScore: z.number().nullable(), interval: z.unknown() })),
});

export type FixedReport = z.infer<typeof fixedReportSchema>;

function combined(verdicts: readonly string[]): "pass" | "fail" | "unknown" {
  if (verdicts.includes("fail")) return "fail";
  if (verdicts.some((verdict) => verdict !== "pass" && verdict !== "fail")) return "unknown";
  return "pass";
}

export function fixedReport(options: { frozen: FixedSuite; receipt: MatrixReceipt }): FixedReport {
  const { suite } = options.frozen;
  if (options.receipt.suiteFingerprint !== fingerprint(suite)) throw new Error("Receipt does not match the frozen suite");
  const entries = suite.tasks.flatMap((task) => internalArms.flatMap((arm) => Array.from({ length: suite.analysis.repetitions }, (_, repeat) => ({ arm, taskId: task.id, repeat }))));
  const keys = new Set<string>();
  for (const run of options.receipt.runs) {
    const key = `${run.arm}/${run.taskId}/${run.repeat}`;
    if (keys.has(key) || !entries.some((entry) => entry.arm === run.arm && entry.taskId === run.taskId && entry.repeat === run.repeat)) throw new Error("Receipt contains duplicate or unexpected cells");
    if (run.productCommit !== suite.productCommit || run.productTreeFingerprint !== suite.productTreeFingerprint) throw new Error("Receipt contains another product revision");
    keys.add(key);
  }
  const cells = entries.map((entry) => {
    const run = options.receipt.runs.find((record) => record.arm === entry.arm && record.taskId === entry.taskId && record.repeat === entry.repeat);
    const task = suite.tasks.find((candidate) => candidate.id === entry.taskId);
    if (!task) throw new Error("Fixed task is missing");
    const usable = run?.status === "complete" && run.turns.length === task.turns.length && run.turns.every((turn, index) =>
      turn.index === index && !turn.isError && !turn.timedOut && (turn.resolvedModel === null || turn.resolvedModel === suite.model));
    const checks = run ? deterministicChecks({ record: run, task }) : task.checks.map((check) => ({ id: check.id, keyItem: check.keyItem, verdict: "unknown", evidence: "Missing run." }));
    const preferences = checks.filter((check) => !fixedDefinition.functionalChecks.includes(`${task.id}/${check.id}`));
    const correctness = usable ? task.acceptance ? run.correctness : combined(checks.filter((check) => !preferences.includes(check)).map((check) => check.verdict)) : "unknown";
    const adherence = usable ? combined(preferences.map((check) => check.verdict)) : "unknown";
    const safety = usable ? run.safety : "unknown";
    return { ...entry, arm: armNames[entry.arm], verdict: combined([correctness, adherence, safety]), adherence, correctness, safety,
      checks, error: run?.error ?? null, verificationEvidence: run?.verificationEvidence ?? "Missing run.", safetyEvidence: run?.safetyEvidence ?? "Missing run.",
      costUsd: run?.turns.every((turn) => turn.costUsd !== null) ? run.turns.reduce((total, turn) => total + (turn.costUsd ?? 0), 0) : null,
      durationMs: run?.turns.reduce((total, turn) => total + turn.durationMs, 0) ?? 0, skillReads: [...new Set(run?.turns.flatMap((turn) => turn.skillReads) ?? [])] };
  });
  const complete = options.receipt.status === "complete" && cells.every((cell) => cell.verdict !== "unknown");
  const arms = fixedArms.map((arm) => {
    const selected = cells.filter((cell) => cell.arm === arm);
    const observations = selected.map((cell) => ({ taskId: cell.taskId, sessionId: `${arm}/${cell.taskId}/${cell.repeat}`, keyItem: "task", passed: cell.verdict === "pass", skillRead: null }));
    const interval = complete ? bootstrapRate({ observations, tasks: suite.tasks.map((task) => task.id), seed: suite.analysis.bootstrapSeed, samples: suite.analysis.bootstrapSamples }) : null;
    return { arm, expected: selected.length, passed: selected.filter((cell) => cell.verdict === "pass").length,
      failed: selected.filter((cell) => cell.verdict === "fail").length, unknown: selected.filter((cell) => cell.verdict === "unknown").length,
      score: complete ? 100 * selected.filter((cell) => cell.verdict === "pass").length / selected.length : null,
      adherenceScore: complete && selected.every((cell) => cell.adherence !== "unknown") ? 100 * selected.filter((cell) => cell.adherence === "pass").length / selected.length : null, interval };
  });
  return fixedReportSchema.parse({ protocol: "preference-respect-v1", scorerVersion: "fixed-task-1", benchmarkFingerprint: options.frozen.benchmarkFingerprint,
    graderFingerprint: options.frozen.graderFingerprint,
    product: { commit: suite.productCommit, tree: suite.productTreeFingerprint, branch: options.frozen.branch },
    configuration: { engine: suite.engine, cliVersion: suite.cliVersion, model: suite.model, effort: suite.effort, repetitions: suite.analysis.repetitions, limits: suite.limits, runtime: options.frozen.runtime },
    status: complete ? "complete" : "incomplete", cells, arms });
}

export function compareFixedReports(options: { baseline: FixedReport; candidate: FixedReport }) {
  if (options.baseline.status !== "complete" || options.candidate.status !== "complete") throw new Error("Branch comparison requires two complete reports");
  if (options.baseline.graderFingerprint !== options.candidate.graderFingerprint || options.baseline.benchmarkFingerprint !== options.candidate.benchmarkFingerprint ||
    fingerprint(options.baseline.configuration) !== fingerprint(options.candidate.configuration) || options.baseline.scorerVersion !== options.candidate.scorerVersion) {
    throw new Error("Branch comparison requires identical benchmark, host, model, effort, repetitions, and limits");
  }
  const expected = fixedDefinition.tasks.flatMap((task) => fixedArms.flatMap((arm) => Array.from({ length: options.baseline.configuration.repetitions }, (_, repeat) => `${arm}/${task.id}/${repeat}`))).sort();
  for (const report of [options.baseline, options.candidate]) {
    const actual = report.cells.map((cell) => `${cell.arm}/${cell.taskId}/${cell.repeat}`).sort();
    if (fingerprint(actual) !== fingerprint(expected) || report.cells.some((cell) => cell.verdict === "unknown")) throw new Error("Branch comparison requires the complete fixed task matrix");
  }
  const observations = (options_: { report: FixedReport; arm: typeof fixedArms[number] }) => options_.report.cells.filter((cell) => cell.arm === options_.arm)
    .map((cell) => ({ taskId: cell.taskId, sessionId: `${cell.taskId}/${cell.repeat}`, keyItem: "task", passed: cell.verdict === "pass", skillRead: null }));
  return { baseline: options.baseline.product, candidate: options.candidate.product,
    comparisons: fixedArms.map((arm) => ({ arm, ...bootstrapDifference({ left: observations({ report: options.candidate, arm }),
      right: observations({ report: options.baseline, arm }), tasks: fixedDefinition.tasks.map((task) => task.id), seed: 20261001, samples: 10000 }) })) };
}
