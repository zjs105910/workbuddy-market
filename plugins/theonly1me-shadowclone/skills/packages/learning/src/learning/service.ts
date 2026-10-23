import { captureRoots } from "@shadowclone/sessions";
import { normalizeExplicitCandidates } from "./candidates";
import type { ManagedPolicy, ProjectPaths } from "@shadowclone/core";
import { readConfig } from "@shadowclone/core";
import { selectLearningPreferences } from "./modelPreferences";
import { distillSignals, renderReconciliationChanges } from "../distill";
import {
  defaultLearningExecutionLimits,
  createLearningExecution,
  learningExecutionLimitsForCalls,
  detectEngine,
  type EngineId,
  type EngineRunner,
  type LearningExecution,
  type LearningExecutionLimits,
  type ReasoningEffort,
  getProviderByEngine,
} from "@shadowclone/agents";
import type { IndexedEvent, CorrectionSignal } from "@shadowclone/sessions";
import { readLearningSnapshot, persistLearningRules } from "./storage";
import { learningRuleProvenance } from "./provenance";
import { loadSeedLibrary } from "@shadowclone/skills";
import { readEnvironment, refreshIntegrations } from "@shadowclone/environment";
import { queuePendingLearning, readPendingLearning, updatePendingLearning } from "./pending";
import { recordLaterCorrections } from "./feedback";

export type DeepLearningResult = {
  readonly changesProposed: number;
  readonly networkCallsMade: boolean;
  readonly profileUpdated: boolean;
  readonly pendingReview: number;
  readonly execution: LearningExecution;
  readonly noChangeReason: "already-covered" | "uncertain-evidence" | "no-eligible-evidence";
  readonly engine: EngineId;
  readonly ruleKeys: readonly string[];
};

export async function runLearningService(options: {
  readonly signals: readonly CorrectionSignal[];
  readonly events: readonly IndexedEvent[];
  readonly paths: ProjectPaths;
  readonly policy: ManagedPolicy;
  readonly runner?: EngineRunner;
  readonly engine?: EngineId;
  readonly model?: string;
  readonly reasoningEffort?: ReasoningEffort;
  readonly maximumCalls?: number;
  readonly limits?: LearningExecutionLimits;
  readonly execution?: LearningExecution;
  readonly dryRun: boolean;
  readonly apply: boolean;
  readonly confirm?: (message: string) => Promise<boolean> | boolean;
  readonly writeLine?: (line: string) => void;
  readonly requireSteeringCue?: boolean;
  readonly authorizeRef?: (ref: CorrectionSignal["textRefs"][number]) => Promise<boolean>;
}): Promise<DeepLearningResult> {
  const writeLine = options.writeLine ?? console.log;
  const preferences = selectLearningPreferences({ explicit: options,
    saved: (await readConfig({ configPath: options.paths.configFile })).distillation });

  if (options.policy.distillation !== "allowed") {
    throw new Error("Managed policy does not allow remote distillation");
  }

  if (
    preferences.engine &&
    !options.policy.allowedEngines.includes(preferences.engine)
  ) {
    throw new Error("Managed policy blocks the selected learning engine");
  }

  const detection = options.runner
    ? null
    : await detectEngine({
        purpose: "distill",
        allowedEngines: options.policy.allowedEngines,
        preferredEngine: preferences.engine,
      });
  const detectedRunner = options.runner ?? detection?.runner;
  const engine = preferences.engine ?? detection?.selectedEngine;

  if (!detectedRunner || !engine) {
    throw new Error("No authenticated agent engine is available");
  }

  const runner: EngineRunner = (run) =>
    detectedRunner({
      ...run,
      ...(preferences.model ? { model: preferences.model } : {}),
      ...(options.reasoningEffort
        ? { reasoningEffort: options.reasoningEffort }
        : {}),
    });
  const limits =
    options.limits ??
    (options.maximumCalls === undefined
      ? defaultLearningExecutionLimits
      : learningExecutionLimitsForCalls(options.maximumCalls));
  const execution =
    options.execution ??
    createLearningExecution({
      engine,
      runner,
      limits,
    });
  const supportsCostLimit =
    getProviderByEngine(engine)?.engine?.capabilities.maxBudgetUsd === true;

  writeLine(
    [
      `Learning is limited to ${limits.maximumCalls} total calls and ${limits.timeoutMilliseconds / 1_000} seconds`,
      supportsCostLimit
        ? ` with a $${limits.maximumCostUsd.toFixed(2)} total ceiling.`
        : ".",
    ].join(""),
  );

  const [storedProfile, seedLibrary, pending, previousEnvironment] = await Promise.all([
    readLearningSnapshot(options.paths),
    loadSeedLibrary(),
    readPendingLearning(options.paths),
    readEnvironment(options.paths),
  ]);
  const normalized = normalizeExplicitCandidates(storedProfile);
  const result = await distillSignals({
    signals: options.signals,
    sourceRoots: captureRoots(options.paths),
    runner,
    engine,
    limits,
    execution,
    workingDirectory: options.paths.shadowcloneDirectory,
    checkpointDirectory: options.dryRun ? null : options.paths.distillDirectory,
    events: options.events,
    profile: normalized.profile,
    seedLibrary,
    requireSteeringCue: options.requireSteeringCue,
    authorizeRef: options.authorizeRef,
  });

  writeLine(
    renderReconciliationChanges({
      changes: result.changes,
      rejectedMatches: result.rejectedMatches,
      droppedRules: result.droppedRules,
    }),
  );

  let profileUpdated = false;
  let pendingReview = 0;

  if (!options.dryRun) {
    await recordLaterCorrections({ paths: options.paths, state: previousEnvironment, corrections: result.corrections });
    const proposed = result.rules.filter((rule) => !pending.rejectedKeys.includes(rule.key));
    const approved = proposed.length === 0 || options.apply ||
      (await options.confirm?.("Apply these learned rules?")) === true;
    let authorized = true;
    if (options.authorizeRef) {
      for (const signal of options.signals) {
        for (const ref of signal.textRefs) {
          if (!await options.authorizeRef(ref)) authorized = false;
        }
      }
    }
    const accepted = approved && authorized;
    const updates = [...normalized.promoted, ...(accepted ? proposed : [])];

    if (!accepted) {
      pendingReview = await queuePendingLearning({
        paths: options.paths,
        rules: proposed,
        events: options.events,
        signals: options.signals,
      });
      writeLine(`${pendingReview} learned rule(s) saved for review. Run shadowclone learning pending.`);
      if (!authorized) writeLine("Source consent changed during learning. New rules remain pending.");
    }

    if (updates.length > 0) {
      await updatePendingLearning({ paths: options.paths, update: async (current) => {
        const rules = [
          ...new Map(updates.filter((rule) => !current.rejectedKeys.includes(rule.key))
            .map((rule) => [rule.key, rule])).values(),
        ].sort(
          (left, right) =>
            right.observations - left.observations ||
            left.title.localeCompare(right.title),
        );
        if (rules.length === 0) return current;

        await persistLearningRules({
          paths: options.paths,
          rules,
          provenance: Object.fromEntries(rules.map((rule) => [rule.key, learningRuleProvenance({
            rule, signals: options.signals, events: options.events,
          })])),
        });

        if (normalized.promoted.length > 0) {
          writeLine(
            `Activated ${normalized.promoted.length} explicit profile rule(s).`,
          );
        }

        const refreshed = await refreshIntegrations({
          paths: options.paths,
          configPath: options.paths.configFile,
        });

        if (refreshed.preserved > 0) {
          writeLine(
            `Preserved ${refreshed.preserved} edited or unavailable integration(s).`,
          );
        }

        profileUpdated = true;

        const appliedKeys = new Set(accepted ? rules.map((rule) => rule.key) : []);
        return { ...current, rules: current.rules.filter((rule) => !appliedKeys.has(rule.key)) };
      } });
    }
  }

  const reviewState = options.dryRun ? pending : await readPendingLearning(options.paths);
  const reviewable = result.rules.filter((rule) => !reviewState.rejectedKeys.includes(rule.key));
  return {
    changesProposed: reviewable.length,
    networkCallsMade: result.engineRuns > 0,
    profileUpdated,
    pendingReview,
    execution,
    noChangeReason: result.noChangeReason,
    engine,
    ruleKeys: reviewable.map((rule) => rule.key),
  };
}
