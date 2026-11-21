import {
  allowlistedSignals,
  authorizedLearningEvents,
  currentEvidenceAuthorization,
  episodeId,
  maintainSkills,
  readLearningState,
  selectLearningPreferences,
  writeLearningReceipt,
  writeLearningState,
} from "@shadowclone/learning";
import { ingestSources, openEventIndex } from "@shadowclone/sessions";
import { checkMarkerStaleness, deriveSignals } from "@shadowclone/sessions";
import { projectPaths, acquireLocalLock } from "@shadowclone/core";
import { renderMirror } from "@shadowclone/profile";
import type { LearnExecutionOptions } from "./learnOptions";
import { writeSkillMaintenance } from "./learnSummary";
import { registerWorkingRepository } from "@shadowclone/environment";
import { runDeepLearning } from "./deepLearn";
import { selectManualLearningWindow } from "./learningWindow";
import { prepareManualLearning } from "./learnPreparation";
import path from "node:path";
import { validateLimits } from "@shadowclone/agents";

export async function learn(options: LearnExecutionOptions = {}): Promise<void> {
  if (options.limits) {
    validateLimits(options.limits);
    if (!options.deep || options.maximumCalls !== options.limits.maximumCalls)
      throw new Error(
        "Explicit learning limits require deep learning and a matching call ceiling.",
      );
  }
  if (options.apply && !options.deep) {
    throw new Error("learn --apply requires --deep");
  }

  if (options.apply && options.dryRun) {
    throw new Error("learn --apply cannot be combined with --dry-run");
  }

  const paths = options.paths ?? projectPaths;
  const configPath = options.configPath ?? paths.configFile;
  const writeLine = options.writeLine ?? console.log;

  const { config, policy } = await prepareManualLearning({
    paths,
    configPath,
    initializationConfigPath: options.configPath,
    managedConfigPath: options.managedConfigPath,
    writeLine,
  });

  const databasePath = options.databasePath ?? (options.dryRun ? ":memory:" : paths.indexDatabase);
  const lock = options.dryRun
    ? null
    : await acquireLocalLock(path.join(paths.shadowcloneDirectory, "learning-worker.db"));
  if (!options.dryRun && !lock) throw new Error("Another learning attempt is running");
  const index = await openEventIndex(databasePath).catch((error: unknown) => {
    lock?.release();
    throw error;
  });

  try {
    const summary = await ingestSources({ index, config, paths });
    const events = authorizedLearningEvents({
      events: index.listEvents(),
      config,
    });
    const derived = await deriveSignals({
      events,
      corpus: index.getCorpusSummary(),
      gitMetadataEnabled: config.sources["git-metadata"],
      readRemote: options.readRemote,
      blockedOrigins: policy.blockedOrigins,
      bindings: index,
    });

    for (const warning of checkMarkerStaleness(events)) {
      console.warn(`Warning: ${warning}`);
    }

    const eligibleSignals = allowlistedSignals({
      signals: derived.learning,
      events: derived.events,
    }).filter((signal) => signal.textRefs.length > 0);

    const learningState = await readLearningState(paths);
    const learningWindow = selectManualLearningWindow({
      signals: eligibleSignals,
      state: learningState,
      now: Date.now(),
      ...(options.maximumCalls === undefined ? {} : { maximumCalls: options.maximumCalls }),
    });
    const { batches, signals: learningSignals } = learningWindow;

    const deepLearningPreview = {
      eligibleSteeringEpisodes: learningSignals.length,
      extractionBatches: batches.length,
    };

    let networkCallsMade = false;
    let deepChangesProposed = 0;
    let profileUpdated = false;
    let pendingReview = 0;

    if (options.deep) {
      if (!config.distillation.deep) {
        throw new Error("Deep distillation is disabled in config");
      }

      const batchLabel = batches.length === 1 ? "batch" : "batches";

      writeLine(`Deep learning found ${batches.length} reconciliation ${batchLabel}.`);

      const startedAt = Date.now();
      const sourceCounts = Object.fromEntries(
        [...Map.groupBy(derived.events, (event) => event.source)].map(([source, sourceEvents]) => [
          source,
          sourceEvents.length,
        ]),
      );
      let stage: "learning" | "publication" | "complete" = "learning";
      let pendingCount = 0;
      let publishedCount = 0;

      try {
        const result = await runDeepLearning({
          signals: learningSignals,
          events: derived.events,
          paths,
          policy,
          authorizeRef: currentEvidenceAuthorization({
            paths,
            configPath,
            events: derived.events,
            managedConfigPath: options.managedConfigPath,
          }),
          dryRun: options.dryRun ?? false,
          apply: options.apply ?? false,
          ...(options.runner ? { runner: options.runner } : {}),
          ...selectLearningPreferences({ explicit: options, saved: config.distillation }),
          ...(options.reasoningEffort ? { reasoningEffort: options.reasoningEffort } : {}),
          ...(options.maximumCalls === undefined ? {} : { maximumCalls: options.maximumCalls }),
          ...(options.limits ? { limits: options.limits } : {}),
          ...(options.confirm ? { confirm: options.confirm } : {}),
          writeLine,
        });

        networkCallsMade = result.networkCallsMade;
        deepChangesProposed = result.changesProposed;
        profileUpdated = result.profileUpdated;
        pendingCount = result.pendingReview;
        pendingReview = result.pendingReview;

        if (!options.dryRun && learningSignals.length > 0) {
          await writeLearningState({
            paths,
            state: {
              ...learningState,
              processed: [
                ...learningState.processed,
                ...learningSignals.map((signal) => ({
                  id: episodeId(signal),
                  timestamp: signal.timestamp,
                })),
              ],
            },
          });
        }

        if (!options.dryRun && config.sources["skill-library"]) {
          stage = "publication";
          if (options.workingDirectory) {
            await registerWorkingRepository({
              paths,
              workingDirectory: options.workingDirectory,
              gitMetadataEnabled:
                config.sources["git-metadata"] && policy.allowedSources.includes("git-metadata"),
              blockedOrigins: policy.blockedOrigins,
              managedConfigPath: options.managedConfigPath,
              readRemote: options.readRemote,
            });
          }

          const skills = await maintainSkills({
            paths,
            execution: result.execution,
            managedConfigPath: options.managedConfigPath,
            readRemote: options.readRemote,
          });
          pendingCount += skills.pending + skills.deferred + skills.conflicts;
          publishedCount = skills.applied;

          writeSkillMaintenance({ skills, writeLine });
        }

        stage = "complete";

        if (!options.dryRun) {
          const outcome =
            pendingCount > 0
              ? result.pendingReview > 0
                ? "awaiting-review"
                : "needs-scope-or-publication"
              : publishedCount > 0
                ? "guidance-published"
                : profileUpdated
                  ? "guidance-recorded"
                  : result.noChangeReason;

          await writeLearningReceipt({
            paths,
            receipt: {
              startedAt,
              mode: "manual",
              outcome,
              stage,
              episodeCount: learningSignals.length,
              sourceCounts,
              proposalCount: result.changesProposed,
              engine: result.engine,
              model:
                selectLearningPreferences({ explicit: options, saved: config.distillation })
                  .model ?? null,
              ruleKeys: [...result.ruleKeys],
              pendingCount,
              nextAction:
                pendingCount > 0
                  ? result.pendingReview > 0
                    ? "Run shadowclone learning pending to approve or reject the rule."
                    : "Run shadowclone skills pending to resolve scope or publication."
                  : outcome === "uncertain-evidence"
                    ? "No durable rule was resolved. State an explicit standing correction and run shadowclone learn --deep."
                    : outcome === "no-eligible-evidence"
                      ? "Enable a capture source and add a correction before running shadowclone learn --deep."
                      : "Start a new agent session to load active guidance.",
            },
          });
        }
      } catch (error) {
        if (!options.dryRun) {
          await writeLearningReceipt({
            paths,
            receipt: {
              startedAt,
              mode: "manual",
              outcome: stage === "learning" ? "engine-failed" : "publication-failed",
              stage,
              episodeCount: learningSignals.length,
              sourceCounts,
              proposalCount: deepChangesProposed,
              pendingCount,
              nextAction:
                stage === "learning"
                  ? "Check shadowclone doctor and retry shadowclone learn --deep."
                  : "Run shadowclone skills pending and retry shadowclone skills update.",
            },
          });
        }

        throw error;
      }
    }

    writeLine(
      renderMirror({
        report: derived.report,
        deepLearningPreview,
        networkCallsMade,
        ...(options.deep ? { deepChangesProposed } : {}),
        profileUpdated,
        pendingReview,
      }),
    );

    const processedIds = new Set(learningState.processed.map((entry) => entry.id));
    const remaining =
      eligibleSignals.filter((signal) => !processedIds.has(episodeId(signal))).length -
      learningSignals.length;

    if (remaining > 0) {
      writeLine(
        `\n  Deep learning covered ${learningSignals.length} episode(s); ${remaining} remain. Run shadowclone learn --deep again to continue.`,
      );
    }

    if (summary.rescannedFiles > 0) {
      writeLine(`\n  Rescanned ${summary.rescannedFiles} rewritten files.`);
    }

    if (summary.invalidRecords > 0) {
      const label = summary.invalidRecords === 1 ? "record" : "records";

      writeLine(`\n  Skipped ${summary.invalidRecords} invalid transcript ${label}.`);
    }
  } finally {
    index.close();
    lock?.release();
  }
}
