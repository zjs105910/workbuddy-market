import { expect, test } from "bun:test";
import { mkdtemp, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { evaluationBudget, budgetSchema } from "../../shared/accounting";
import { engineRun } from "../../native/study/fixtures";
import { workflowLearningRunner } from "./learner";
import type { LearningCall } from "./schema";

test("learning rejects tool actions and model or CLI drift while retaining every charged attempt", async () => {
  const directory = await mkdtemp(path.join(os.tmpdir(), "four-setup-learner-"));
  try {
    const budget = await evaluationBudget({ directory, resume: false, maximumCalls: 3 });
    const configuration = { engine: "codex" as const, model: "synthetic-model", effort: "medium" as const, cliVersion: "synthetic-cli", maximumCalls: 3, callSeconds: 120 as const, deadlineSeconds: 1200 as const };
    const calls: LearningCall[] = [];
    for (const result of [
      engineRun({ resolvedModel: "other", cliVersion: "synthetic-cli" }),
      engineRun({ resolvedModel: "synthetic-model", cliVersion: "other" }),
      engineRun({ resolvedModel: "synthetic-model", cliVersion: "synthetic-cli", actions: [{ tool: "Read", path: "secret" }] }),
    ]) {
      const runner = workflowLearningRunner({ directory, configuration, budget, calls, blockedPaths: [], runner: async () => result });
      await expect(runner({ prompt: "Synthetic learning", cwd: directory, execution: { purpose: "learning" } })).rejects.toThrow("pinned model and CLI");
    }
    expect(calls).toHaveLength(3);
    expect(calls.every(call => call.isError)).toBeTrue();
    const runner = workflowLearningRunner({ directory, configuration, budget, calls, blockedPaths: [], runner: async () => engineRun() });
    await expect(runner({ prompt: "Synthetic learning", cwd: directory, execution: { purpose: "learning" } })).rejects.toThrow("invocation limit");
    const ledger = budgetSchema.parse(await Bun.file(path.join(directory, "budget.json")).json());
    expect(ledger.calls).toBe(3);
    expect(ledger.pending).toBeFalse();
  } finally { await rm(directory, { recursive: true, force: true }); }
});
