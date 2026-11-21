import type { z } from "zod";
import path from "node:path";
import { readBoundedFile } from "@shadowclone/core";
import { budgetSchema } from "../../shared/accounting";
import type { FrozenSuite, Receipt } from "./schema";

export type InvocationLedger = z.infer<typeof budgetSchema>;

export async function readInvocationLedger(directory: string): Promise<InvocationLedger> {
  const text = await readBoundedFile({
    filePath: path.join(directory, "budget.json"),
    roots: [directory],
    maximumBytes: 4096,
  });
  if (text === null) throw new Error("Evaluation call ledger is unavailable.");
  return budgetSchema.parse(JSON.parse(text));
}

export function invocationAccounting(options: {
  suite: FrozenSuite;
  receipt: Receipt;
  ledger?: InvocationLedger;
}) {
  const attributedCalls = options.receipt.cells
    .flatMap((cell) => cell.attempts)
    .reduce((total, attempt) => total + attempt.calls, 0);
  const calls = options.ledger?.calls ?? attributedCalls;
  if (
    calls < attributedCalls ||
    calls > options.suite.limits.maximumCalls ||
    (options.ledger && options.ledger.maximumCalls !== options.suite.limits.maximumCalls)
  ) {
    throw new Error("Invocation ledger conflicts with the receipt or approved ceiling.");
  }
  const unattributedCalls = calls - attributedCalls;
  const pending = options.ledger?.pending ?? false;
  return {
    calls,
    attributedCalls,
    unattributedCalls,
    pending,
    unknownCost: options.ledger?.unknownCost ?? true,
    complete: unattributedCalls === 0 && !pending,
  };
}
