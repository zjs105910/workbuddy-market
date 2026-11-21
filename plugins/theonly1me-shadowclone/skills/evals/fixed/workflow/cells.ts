import { z } from "zod";
import type { MatrixReceipt } from "../../native/study/matrix";
import { deterministicChecks } from "../../native/study/checks";
import { fingerprint } from "../../shared/structured";
import { workflowArms, workflowInternalArms, workflowArmNames, workflowDefinition } from "./definition";
import type { WorkflowSuite } from "./freeze";

export const verdictSchema = z.enum(["pass", "fail", "unknown"]);
export const cellSchema = z.strictObject({ arm: z.enum(workflowArms), taskId: z.string(), repeat: z.number(),
  verdict: verdictSchema, correctness: verdictSchema, safety: verdictSchema,
  preferences: z.array(z.strictObject({ id: z.string(), keyItem: z.string(), verdict: verdictSchema, evidence: z.string() })),
  error: z.string().nullable(), verificationEvidence: z.string(), safetyEvidence: z.string(),
  costUsd: z.number().nullable(), durationMs: z.number(), skillReads: z.array(z.string()) });
export type WorkflowCell = z.infer<typeof cellSchema>;

export function combined(verdicts: readonly string[]): "pass" | "fail" | "unknown" {
  if (verdicts.includes("unknown")) return "unknown";
  return verdicts.every(verdict => verdict === "pass") ? "pass" : "fail";
}

export function workflowCells(options: { frozen: WorkflowSuite; receipt: MatrixReceipt }): WorkflowCell[] {
  const { suite } = options.frozen;
  if (options.receipt.phase !== "scored" || options.receipt.suiteFingerprint !== fingerprint(suite)) throw new Error("Receipt does not match the frozen scored suite");
  const entries = suite.tasks.flatMap(task => workflowInternalArms.flatMap(arm => Array.from({ length: suite.analysis.repetitions }, (_, repeat) => ({ arm, taskId: task.id, repeat }))));
  const keys = new Set<string>();
  for (const run of options.receipt.runs) {
    const key = `${run.arm}/${run.taskId}/${run.repeat}`;
    if (keys.has(key) || !entries.some(entry => entry.arm === run.arm && entry.taskId === run.taskId && entry.repeat === run.repeat)) throw new Error("Receipt contains duplicate or unexpected cells");
    if (run.productCommit !== suite.productCommit || run.productTreeFingerprint !== suite.productTreeFingerprint) throw new Error("Receipt contains another product revision");
    keys.add(key);
  }
  return entries.map(entry => {
    const run = options.receipt.runs.find(record => record.arm === entry.arm && record.taskId === entry.taskId && record.repeat === entry.repeat);
    const task = suite.tasks.find(candidate => candidate.id === entry.taskId);
    if (!task) throw new Error("Fixed task is missing");
    const usable = run?.status === "complete" && run.turns.length === task.turns.length && run.turns.every((turn, index) =>
      turn.index === index && !turn.isError && !turn.timedOut && turn.resolvedModel === suite.model);
    const checks = usable ? deterministicChecks({ record: run, task }).map(check => ({ ...check,
      verdict: check.verdict === "not-applicable" ? "unknown" : check.verdict,
    })) : task.checks.map(check => ({ id: check.id, keyItem: check.keyItem, verdict: "unknown", evidence: "Missing or unconfirmed run." }));
    const preferences = checks.filter(check => !workflowDefinition.functionalChecks.includes(`${task.id}/${check.id}`));
    const correctness = usable ? task.acceptance ? run.correctness : combined(checks.filter(check => !preferences.includes(check)).map(check => check.verdict)) : "unknown";
    const safety = usable ? run.safety : "unknown";
    return cellSchema.parse({ ...entry, arm: workflowArmNames[entry.arm], verdict: combined([correctness, safety, ...preferences.map(check => check.verdict)]),
      correctness, safety, preferences, error: run?.error ?? null, verificationEvidence: run?.verificationEvidence ?? "Missing run.", safetyEvidence: run?.safetyEvidence ?? "Missing run.",
      costUsd: run && run.turns.length > 0 && run.turns.every(turn => turn.costUsd !== null) ? run.turns.reduce((total, turn) => total + (turn.costUsd ?? 0), 0) : null,
      durationMs: run?.turns.reduce((total, turn) => total + turn.durationMs, 0) ?? 0, skillReads: [...new Set(run?.turns.flatMap(turn => turn.skillReads) ?? [])] });
  });
}
