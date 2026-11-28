import { z } from "zod";
import type { NativeEngineRunner } from "@shadowclone/agents";
import { redactSecrets } from "@shadowclone/redact";
import { ownedWrite } from "@shadowclone/core";
import type { EvaluationBudget } from "../../shared/accounting";
import type { StudyCheckResult } from "./checkSchema";
import { deterministicChecks } from "./checks";
import { agreedVerdict, judgeConversation, runConversation } from "./judge";
import { pendingRun, runRecordSchema, type RunArmName, type RunRecord } from "./record";
import type { StudySuite } from "./schema";
import { runStudySession } from "./session";

export const matrixReceiptSchema = z.strictObject({
  protocol: z.literal("preference-study-v1"),
  phase: z.enum(["validation", "scored"]),
  suiteFingerprint: z.string().length(64),
  deadlineAt: z.number().positive(),
  status: z.enum(["running", "complete", "error"]),
  runs: z.array(runRecordSchema),
  failure: z.string().nullable(),
});

export type MatrixReceipt = z.infer<typeof matrixReceiptSchema>;
export type MatrixEntry = { readonly arm: RunArmName; readonly taskId: string; readonly repeat: number };

const same = (left: MatrixEntry, right: MatrixEntry) => left.arm === right.arm && left.taskId === right.taskId && left.repeat === right.repeat;

async function scoreRun(options: {
  suite: StudySuite; record: RunRecord; runner: NativeEngineRunner; budget: EvaluationBudget; outputDirectory: string;
}): Promise<RunRecord> {
  const task = options.suite.tasks.find((entry) => entry.id === options.record.taskId);
  if (!task) throw new Error("Run task is missing from the suite");
  const checks: StudyCheckResult[] = deterministicChecks({ record: options.record, task });
  const judgments: RunRecord["judgments"] = [];

  for (const check of task.checks) {
    if (check.kind !== "judged" || options.record.status !== "complete") continue;
    const conversation = runConversation({ record: options.record, task, suite: options.suite });
    const votes = [];
    for (let index = 0; index < 2; index += 1) {
      votes.push(await judgeConversation({ check, conversation, files: options.record.files, ...options }));
    }
    judgments.push({ checkId: check.id, votes: votes.map((entry) => entry.vote) });
    const verdict = agreedVerdict(votes.map((entry) => entry.verdict));
    const position = checks.findIndex((entry) => entry.id === check.id);
    checks[position] = { id: check.id, keyItem: check.keyItem, verdict, evidence: `Blinded votes: ${votes.map((entry) => entry.verdict).join(", ")}` };
  }

  return { ...options.record, checks, judgments };
}

export async function runMatrix(options: {
  readonly suite: StudySuite;
  readonly entries: readonly MatrixEntry[];
  readonly receipt: MatrixReceipt;
  readonly receiptFile: string;
  readonly runner: NativeEngineRunner;
  readonly budget: EvaluationBudget;
  readonly outputDirectory: string;
  readonly concurrency: number;
  readonly writeLine?: (line: string) => void;
}): Promise<MatrixReceipt> {
  let receipt: MatrixReceipt = {
    ...options.receipt, status: "running", failure: null,
    runs: options.receipt.runs.map((run) => run.status === "running"
      ? { ...run, status: "error", error: "Interrupted candidate retained without rerunning." } : run),
  };
  let saving = Promise.resolve();
  const save = () => {
    const content = JSON.stringify(receipt, null, 2);
    saving = saving.then(() => ownedWrite({ path: options.receiptFile, content }));
    return saving;
  };
  const upsert = (record: RunRecord) => {
    const exists = receipt.runs.some((run) => same(run, record));
    receipt = { ...receipt, runs: exists ? receipt.runs.map((run) => same(run, record) ? record : run) : [...receipt.runs, record] };
  };
  const queue = options.entries.filter((entry) => !receipt.runs.some((run) => same(run, entry)));
  let stopped: string | null = null;
  await save();

  const worker = async () => {
    while (!stopped) {
      const entry = queue.shift();
      if (!entry) return;
      const task = options.suite.tasks.find((candidate) => candidate.id === entry.taskId);
      if (!task) throw new Error("Matrix task is missing from the suite");
      upsert({
        ...pendingRun(entry),
        productCommit: options.suite.productCommit,
        productTreeFingerprint: options.suite.productTreeFingerprint,
      });
      await save();

      try {
        const record = await runStudySession({ ...options, ...entry, task, deadlineAt: receipt.deadlineAt });
        const mismatch = record.turns.some((turn) => turn.resolvedModel !== null && turn.resolvedModel !== options.suite.model);
        upsert({
          ...await scoreRun({ ...options, record }),
          productCommit: options.suite.productCommit,
          productTreeFingerprint: options.suite.productTreeFingerprint,
        });
        if (mismatch) stopped = "Candidate model identity changed; stopped before another invocation.";
      } catch (error) {
        const message = redactSecrets({ text: error instanceof Error ? error.message : "Candidate failed" });
        const current = receipt.runs.find((run) => same(run, entry));
        if (current) upsert({ ...current, status: "error", error: message });
        if (/limit|deadline|budget|exhausted/i.test(message)) stopped = message;
      }

      await save();
      options.writeLine?.(`${entry.arm} ${entry.taskId} ${entry.repeat + 1}: ${receipt.runs.find((run) => same(run, entry))?.checks.map((check) => check.verdict).join(",") ?? ""}`);
    }
  };

  await Promise.all(Array.from({ length: Math.max(1, options.concurrency) }, worker));
  receipt = { ...receipt, status: stopped ? "error" : "complete", failure: stopped };
  await save();
  return receipt;
}
