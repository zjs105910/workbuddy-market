import type { EngineRun } from "./types";

export type LearningExecutionLimits = {
  readonly maximumCalls: number;
  readonly timeoutMilliseconds: number;
  readonly maximumCostUsd: number;
};

export const defaultLearningExecutionLimits: LearningExecutionLimits = {
  maximumCalls: 20,
  timeoutMilliseconds: 300_000,
  maximumCostUsd: 2,
};

export const setupLearningLimits: LearningExecutionLimits = {
  maximumCalls: 12,
  timeoutMilliseconds: 90_000,
  maximumCostUsd: 1,
};

export function learningExecutionLimitsForCalls(
  maximumCalls: number,
): LearningExecutionLimits {
  const perCall = {
    timeoutMilliseconds:
      defaultLearningExecutionLimits.timeoutMilliseconds /
      defaultLearningExecutionLimits.maximumCalls,
    costUsd:
      defaultLearningExecutionLimits.maximumCostUsd /
      defaultLearningExecutionLimits.maximumCalls,
  };

  return {
    maximumCalls,
    timeoutMilliseconds: maximumCalls * perCall.timeoutMilliseconds,
    maximumCostUsd: maximumCalls * perCall.costUsd,
  };
}

export function validateLimits(limits: LearningExecutionLimits): void {
  if (!Number.isSafeInteger(limits.maximumCalls) || limits.maximumCalls < 1) {
    throw new Error("Learning maximum calls must be a positive integer");
  }

  if (
    !Number.isFinite(limits.timeoutMilliseconds) ||
    limits.timeoutMilliseconds <= 0
  ) {
    throw new Error("Learning timeout must be a positive number");
  }

  if (!Number.isFinite(limits.maximumCostUsd) || limits.maximumCostUsd <= 0) {
    throw new Error("Learning cost limit must be a positive number");
  }
}

export async function beforeDeadline(options: {
  readonly timeoutMilliseconds: number;
  readonly run: (signal: AbortSignal) => Promise<EngineRun>;
}): Promise<EngineRun> {
  const controller = new AbortController();
  let timeoutId: ReturnType<typeof setTimeout> | null = null;
  const timeout = new Promise<never>((_, reject) => {
    timeoutId = setTimeout(() => {
      reject(new Error("Learning deadline reached"));
      controller.abort();
    }, options.timeoutMilliseconds);
  });

  try {
    return await Promise.race([options.run(controller.signal), timeout]);
  } finally {
    if (timeoutId !== null) {
      clearTimeout(timeoutId);
    }
  }
}
