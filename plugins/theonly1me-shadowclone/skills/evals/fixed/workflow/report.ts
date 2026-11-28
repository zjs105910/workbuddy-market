import { z } from "zod";
import { bootstrapDifference } from "../../native/study/report";
import type { MatrixReceipt } from "../../native/study/matrix";
import { fingerprint } from "../../shared/structured";
import { cellSchema, workflowCells } from "./cells";
import { workflowArms, workflowDefinition } from "./definition";
import { workflowScores, workflowComparisons, preferenceObservations } from "./scores";
import { workflowPreparationSchema } from "./schema";
import type { WorkflowSuite } from "./freeze";

const intervalSchema = z.strictObject({ point: z.number().nullable(), lower: z.number().nullable(), upper: z.number().nullable(), halfWidth: z.number().nullable() });
const differenceSchema = z.strictObject({ ...intervalSchema.shape, supported: z.boolean() });
export const workflowReportSchema = z.strictObject({ protocol: z.literal("preference-respect-v2"), scorerVersion: z.literal("preference-share-1"),
  benchmarkFingerprint: z.string(), graderFingerprint: z.string(), product: workflowPreparationSchema.shape.product,
  configuration: z.strictObject({ engine: z.string(), cliVersion: z.string(), model: z.string(), effort: z.string(), repetitions: z.number(),
    limits: z.unknown(), analysis: z.strictObject({ bootstrapSeed: z.number(), bootstrapSamples: z.number() }), runtime: workflowPreparationSchema.shape.runtime,
    learner: workflowPreparationSchema.shape.learner, corpusFingerprint: z.string(), existingSkillsFingerprint: z.string() }),
  learning: z.strictObject({ calls: z.number(), publishedRules: z.number(), processedEpisodes: z.number(), environmentsFingerprint: z.string() }),
  status: z.enum(["complete", "incomplete"]), cells: z.array(cellSchema),
  arms: z.array(z.strictObject({ arm: z.enum(workflowArms), expectedSessions: z.number(), expectedPreferences: z.number(),
    preferencesPassed: z.number(), preferencesFailed: z.number(), preferencesUnknown: z.number(), preferenceScore: z.number().nullable(),
    interval: intervalSchema.nullable(), wholeTasksPassed: z.number(), correctnessPassed: z.number(), safetyPassed: z.number() })),
  comparisons: z.array(z.strictObject({ left: z.enum(workflowArms), right: z.enum(workflowArms), difference: differenceSchema.nullable() })),
});
export type WorkflowReport = z.infer<typeof workflowReportSchema>;

export function workflowReport(options: { frozen: WorkflowSuite; receipt: MatrixReceipt }): WorkflowReport {
  const cells = workflowCells(options);
  const { suite, environments } = options.frozen;
  const complete = options.receipt.status === "complete" && cells.every(cell => cell.verdict !== "unknown");
  const scoring = { cells, complete, seed: suite.analysis.bootstrapSeed, samples: suite.analysis.bootstrapSamples };
  return workflowReportSchema.parse({ protocol: "preference-respect-v2", scorerVersion: "preference-share-1",
    benchmarkFingerprint: environments.preparation.benchmarkFingerprint, graderFingerprint: environments.preparation.graderFingerprint,
    product: environments.preparation.product, configuration: { engine: suite.engine, cliVersion: suite.cliVersion, model: suite.model, effort: suite.effort,
      repetitions: suite.analysis.repetitions, limits: suite.limits, analysis: { bootstrapSeed: suite.analysis.bootstrapSeed, bootstrapSamples: suite.analysis.bootstrapSamples },
      runtime: environments.preparation.runtime, learner: environments.preparation.learner, corpusFingerprint: fingerprint(workflowDefinition.corrections),
      existingSkillsFingerprint: fingerprint(environments.preparation.starting[suite.engine].original) },
    learning: { calls: environments.learning.calls.length, publishedRules: environments.learning.publishedRules, processedEpisodes: environments.learning.processedEpisodes,
      environmentsFingerprint: fingerprint(environments.engines) }, status: complete ? "complete" : "incomplete", cells,
    arms: workflowScores(scoring), comparisons: workflowComparisons(scoring) });
}

export function compareWorkflowReports(options: { baseline: WorkflowReport; candidate: WorkflowReport }) {
  if (options.baseline.status !== "complete" || options.candidate.status !== "complete") throw new Error("Branch comparison requires two complete reports");
  if (options.baseline.benchmarkFingerprint !== options.candidate.benchmarkFingerprint || options.baseline.graderFingerprint !== options.candidate.graderFingerprint ||
    fingerprint(options.baseline.configuration) !== fingerprint(options.candidate.configuration)) throw new Error("Branch comparison requires matching tasks, skills, corrections, hosts, models, and budgets");
  const expected = workflowDefinition.tasks.flatMap(task => workflowArms.flatMap(arm => Array.from({ length: options.baseline.configuration.repetitions }, (_, repeat) => `${arm}/${task.id}/${repeat}`))).sort();
  for (const report of [options.baseline, options.candidate]) {
    if (fingerprint(report.cells.map(cell => `${cell.arm}/${cell.taskId}/${cell.repeat}`).sort()) !== fingerprint(expected) || report.cells.some(cell => cell.verdict === "unknown")) throw new Error("Branch comparison requires the complete four-setup matrix");
  }
  return { baseline: options.baseline.product, candidate: options.candidate.product, comparisons: workflowArms.map(arm => ({ arm,
    ...bootstrapDifference({ left: preferenceObservations({ cells: options.candidate.cells, arm }), right: preferenceObservations({ cells: options.baseline.cells, arm }),
      tasks: workflowDefinition.tasks.map(task => task.id), seed: options.baseline.configuration.analysis.bootstrapSeed, samples: options.baseline.configuration.analysis.bootstrapSamples }) })) };
}
