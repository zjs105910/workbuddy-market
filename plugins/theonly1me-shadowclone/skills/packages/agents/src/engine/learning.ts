import { getProviderByEngine, providerSupportsPurpose } from "../provider";
import { validateEngineExecution } from "./execution";
import type { EngineId, EngineRunner } from "./types";
import {
  beforeDeadline,
  defaultLearningExecutionLimits,
  validateLimits,
  type LearningExecutionLimits,
} from "./learningLimits";

export {
  defaultLearningExecutionLimits,
  setupLearningLimits,
  learningExecutionLimitsForCalls,
  type LearningExecutionLimits,
} from "./learningLimits";

export type LearningExecution = {
  readonly runner: EngineRunner;
  readonly callsUsed: () => number;
  readonly callsRemaining: () => number;
};

export function createLearningExecution(options: {
  readonly engine: EngineId;
  readonly runner: EngineRunner;
  readonly limits?: LearningExecutionLimits;
}): LearningExecution {
  const limits = options.limits ?? defaultLearningExecutionLimits;

  validateLimits(limits);

  const provider = getProviderByEngine(options.engine);

  if (
    provider === null ||
    provider.engine === null ||
    !providerSupportsPurpose({ definition: provider, purpose: "distill" })
  ) {
    throw new Error("Engine cannot enforce the learning contract");
  }

  const supportsCostLimit = provider.engine.capabilities.maxBudgetUsd;
  const startedAt = Date.now();
  let callsUsed = 0;
  let costUsed = 0;

  const dispatch: EngineRunner = async (run) => {
    if (run.execution.purpose !== "learning") {
      throw new Error("Learning execution received a different purpose");
    }

    if (run.maxBudgetUsd !== undefined) {
      throw new Error("Learning execution owns the dollar limit");
    }

    validateEngineExecution(run);

    if (callsUsed >= limits.maximumCalls) {
      throw new Error("Learning call limit reached");
    }

    const remainingTime = limits.timeoutMilliseconds - (Date.now() - startedAt);

    if (remainingTime <= 0) {
      throw new Error("Learning deadline reached");
    }

    const remainingCost = limits.maximumCostUsd - costUsed;

    if (supportsCostLimit && remainingCost <= 0) {
      throw new Error("Learning cost limit reached");
    }

    callsUsed += 1;

    if (supportsCostLimit) {
      costUsed = limits.maximumCostUsd;
    }

    const result = await beforeDeadline({
      timeoutMilliseconds: remainingTime,
      run: (signal) =>
        options.runner({
          ...run,
          allowedTools: [],
          permissionMode: "dontAsk",
          signal,
          ...(supportsCostLimit ? { maxBudgetUsd: remainingCost } : {}),
        }),
    });

    if (result.engine !== options.engine) {
      throw new Error("Learning engine identity did not match its contract");
    }

    if (supportsCostLimit) {
      if (
        result.costUsd === null ||
        !Number.isFinite(result.costUsd) ||
        result.costUsd < 0
      ) {
        if (result.isError) {
          costUsed = limits.maximumCostUsd;

          return result;
        }

        throw new Error("Learning engine did not report a valid cost");
      }

      costUsed = limits.maximumCostUsd - remainingCost + result.costUsd;

      if (costUsed > limits.maximumCostUsd) {
        throw new Error("Learning cost limit reached");
      }
    }

    return result;
  };

  let pending = Promise.resolve();
  const runner: EngineRunner = supportsCostLimit
    ? (run) => {
        const result = pending.then(() => dispatch(run));

        pending = result.then(
          () => undefined,
          () => undefined,
        );

        return result;
      }
    : dispatch;

  return {
    runner,
    callsUsed: () => callsUsed,
    callsRemaining: () => limits.maximumCalls - callsUsed,
  };
}
