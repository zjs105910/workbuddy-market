import path from "node:path";
import { z } from "zod";
import { readBoundedFile, ownedWrite } from "@shadowclone/core";

export const budgetSchema = z.strictObject({
  version: z.literal(1),
  limitUsd: z.number().positive().nullable(),
  spentUsd: z.number().nonnegative(),
  calls: z.number().int().nonnegative(),
  maximumCalls: z.number().int().positive(),
  pending: z.boolean(),
  unknownCost: z.boolean(),
});

export type EvaluationBudget = {
  readonly reserve: () => Promise<number | undefined>;
  readonly settle: (costUsd: number | null) => Promise<void>;
};

export async function evaluationBudget(options: {
  readonly directory: string;
  readonly resume: boolean;
  readonly limitUsd?: number;
  readonly maximumCalls: number;
}): Promise<EvaluationBudget> {
  const filePath = path.join(options.directory, "budget.json");

  let state = budgetSchema.parse({
    version: 1,
    limitUsd: options.limitUsd ?? null,
    spentUsd: 0,
    calls: 0,
    maximumCalls: options.maximumCalls,
    pending: false,
    unknownCost: false,
  });

  if (options.resume) {
    const text = await readBoundedFile({
      filePath,
      roots: [options.directory],
      maximumBytes: 4096,
    });

    if (text === null) {
      throw new Error("Evaluation cannot resume without its budget ledger");
    }

    state = budgetSchema.parse(JSON.parse(text));

    if (state.limitUsd !== (options.limitUsd ?? null)) {
      throw new Error(
        "Resume must retain the original total evaluation budget",
      );
    }

    if (state.pending) {
      state = { ...state, pending: false, unknownCost: true };
    }
  }

  let pendingCalls = 0;
  let persistence = Promise.resolve();

  const persist = () => {
    const content = JSON.stringify(state);

    persistence = persistence.then(() =>
      ownedWrite({ path: filePath, content }),
    );

    return persistence;
  };

  await persist();

  return {
    reserve: async () => {
      if (state.pending && state.limitUsd !== null) {
        throw new Error("Evaluation model calls must be serialized");
      }

      if (state.calls >= state.maximumCalls) {
        throw new Error("Evaluation invocation limit reached");
      }

      const remaining =
        state.limitUsd === null ? undefined : state.limitUsd - state.spentUsd;

      if (
        remaining !== undefined &&
        (state.unknownCost || remaining < 0.000001)
      ) {
        throw new Error("Evaluation total budget exhausted or cost unknown");
      }

      state = { ...state, pending: true, calls: state.calls + 1 };
      pendingCalls += 1;
      await persist();

      return remaining;
    },
    settle: async (costUsd) => {
      const known =
        costUsd !== null && Number.isFinite(costUsd) && costUsd >= 0;

      pendingCalls -= 1;
      state = {
        ...state,
        pending: pendingCalls > 0,
        unknownCost: state.unknownCost || !known,
        spentUsd: state.spentUsd + (known ? costUsd : 0),
      };
      await persist();
    },
  };
}
