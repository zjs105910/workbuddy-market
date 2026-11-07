import { resolveLearningExecution } from "./execution";
import { selectLearningPreferences } from "./modelPreferences";
import { writeLearningReceipt, type LearningReceipt } from "./receipt";
import path from "node:path";
import {
  readEffectiveConfig,
  acquireLocalLock,
  projectPaths,
  type ProjectPaths,
} from "@shadowclone/core";
import { authorizedLearningEvents, currentEvidenceAuthorization } from "../distill";
import { runLearningService } from "./service";
import type { EngineId, EngineRunner, LearningExecution } from "@shadowclone/agents";
import {
  ingestSources,
  openEventIndex,
  deriveSignals,
  type GitRemoteReader,
} from "@shadowclone/sessions";
import type { SkillUpdateSummary } from "./skillMaintenance/legacyUpdate";
import { maintainSkills } from "./maintenance";
import {
  episodeId,
  learningInterval,
  readLearningState,
  selectLearningEpisodes,
  selectRequestedLearningEpisodes,
  writeLearningState,
} from "./state";

type LearningOptions = {
  readonly paths?: ProjectPaths;
  readonly managedConfigPath?: string | null;
  readonly now?: number;
  readonly runner?: EngineRunner;
  readonly engine?: EngineId;
  readonly model?: string;
  readonly readRemote?: GitRemoteReader;
  readonly reportSkills?: (summary: SkillUpdateSummary) => void;
  readonly execution?: LearningExecution;
  readonly sessionKeys?: readonly string[];
};

type LearningStatus = "disabled" | "busy" | "deferred" | "completed" | "failed";

export function runAutomaticLearning(
  options: LearningOptions = {},
): Promise<LearningStatus> {
  return runLearningMaintenance({ ...options, automatic: true });
}

export async function runLearningMaintenance(
  options: LearningOptions & { readonly automatic: boolean },
): Promise<LearningStatus> {
  const paths = options.paths ?? projectPaths;

  const effective = await readEffectiveConfig({
    configPath: paths.configFile,
    managedConfigPath:
      options.managedConfigPath === undefined
        ? paths.managedConfigFile
        : options.managedConfigPath,
  });

  if (
    !effective.config.distillation.deep ||
    (options.automatic && !effective.config.distillation.automatic) ||
    effective.policy.distillation !== "allowed"
  ) {
    return "disabled";
  }

  const lock = await acquireLocalLock(
    path.join(paths.shadowcloneDirectory, "learning-worker.db"),
  );

  if (!lock) {
    return "busy";
  }

  try {
    const now = options.now ?? Date.now();
    const state = await readLearningState(paths);

    if (
      options.automatic &&
      !options.sessionKeys?.length &&
      state.lastAttemptAt !== null &&
      now - state.lastAttemptAt < learningInterval
    ) {
      return "deferred";
    }

    let attempt = { ...state, lastAttemptAt: now, status: "running" as const };

    await writeLearningState({ paths, state: attempt });

    let stage: "ingestion" | "learning" | "publication" | "complete" = "ingestion";
    let episodeCount = 0;
    let sourceCounts: Record<string, number> = {};
    let proposalCount = 0;
    let pendingCount = 0;
    let outcome: LearningReceipt["outcome"] = "no-eligible-evidence";
    let receiptEngine: string | null = null;
    let receiptModel: string | null = null;
    let ruleKeys: string[] = [];

    try {
      const index = await openEventIndex(paths.indexDatabase);

      try {
        await ingestSources({ index, config: effective.config, paths });

        const authorizedEvents = authorizedLearningEvents({
          events: index.listEvents(),
          config: effective.config,
        });
        sourceCounts = Object.fromEntries(
          [...Map.groupBy(authorizedEvents, (event) => event.source)]
            .map(([source, events]) => [source, events.length]),
        );
        stage = "learning";
        const derived = await deriveSignals({
          events: authorizedEvents,
          corpus: index.getCorpusSummary(),
          gitMetadataEnabled: effective.config.sources["git-metadata"],
          blockedOrigins: effective.policy.blockedOrigins,
          readRemote: options.readRemote,
          bindings: index,
        });

        const requestedSessions = new Set(options.sessionKeys ?? []);

        const signals =
          requestedSessions.size === 0
            ? selectLearningEpisodes({ signals: derived.learning, state, now })
            : selectRequestedLearningEpisodes({
                signals: derived.learning,
                sessionKeys: requestedSessions,
                state,
              });
        episodeCount = signals.length;

        if (signals.length > 0 || effective.config.sources["skill-library"]) {
          const { engine, runner, execution } = await resolveLearningExecution({
            runner: options.runner,
            ...selectLearningPreferences({ triggered: options, saved: effective.config.distillation }),
            execution: options.execution,
            allowedEngines: effective.policy.allowedEngines,
          });
          receiptEngine = engine;
          receiptModel = selectLearningPreferences({ triggered: options, saved: effective.config.distillation }).model ?? null;

          if (signals.length > 0) {
            const learned = await runLearningService({
              paths,
              policy: effective.policy,
              events: derived.events,
              authorizeRef: currentEvidenceAuthorization({
                paths,
                events: derived.events,
                managedConfigPath: options.managedConfigPath,
              }),
              signals,
              engine,
              runner,
              execution,
              dryRun: false,
              apply: true,
              writeLine: ignoreLearningOutput,
              requireSteeringCue: false,
            });
            proposalCount = learned.changesProposed;
            ruleKeys = [...learned.ruleKeys];
            pendingCount = learned.pendingReview;
            outcome = pendingCount > 0 ? "awaiting-review" :
              proposalCount > 0 ? "guidance-recorded" : learned.noChangeReason;
          }

          attempt = {
            ...attempt,
            processed: [
              ...state.processed,
              ...signals.map((signal) => ({
                id: episodeId(signal),
                timestamp: signal.timestamp,
              })),
            ],
          };
          await writeLearningState({ paths, state: attempt });

          if (effective.config.sources["skill-library"]) {
            stage = "publication";
            const summary = await maintainSkills({
              paths,
              execution,
              managedConfigPath: options.managedConfigPath,
              readRemote: options.readRemote,
            });

            options.reportSkills?.(summary);
            pendingCount += summary.pending + summary.deferred + summary.conflicts;
            outcome = pendingCount > 0 ? "needs-scope-or-publication" :
              summary.applied > 0 ? "guidance-published" : outcome;
          }
        }

        stage = "complete";
        await writeLearningReceipt({
          paths,
          receipt: {
            startedAt: now,
            mode: options.automatic ? "automatic" : "maintenance",
            outcome,
            stage,
            episodeCount,
            sourceCounts,
            proposalCount,
            engine: receiptEngine, model: receiptModel, ruleKeys,
            pendingCount,
            nextAction: outcome === "needs-scope-or-publication"
              ? "Run shadowclone skills pending to review scope or publication."
              : outcome === "awaiting-review"
                ? "Run shadowclone learning pending to review learned rules."
                : "Run shadowclone learning status to inspect the latest attempt.",
          },
        });

        await writeLearningState({
          paths,
          state: {
            ...attempt,
            status: "completed",
            lastCompletedAt: now,
          },
        });

        return "completed";
      } finally {
        index.close();
      }
    } catch {
      await writeLearningReceipt({
        paths,
        receipt: {
          startedAt: now,
          mode: options.automatic ? "automatic" : "maintenance",
          outcome: stage === "ingestion" ? "ingestion-failed" :
            stage === "publication" || stage === "complete" ? "publication-failed" : "engine-failed",
          stage,
          episodeCount,
          sourceCounts,
          proposalCount,
          pendingCount,
          nextAction: stage === "publication"
            ? "Run shadowclone skills pending and retry shadowclone skills update."
            : "Check shadowclone doctor and retry learning.",
        },
      });
      await writeLearningState({
        paths,
        state: { ...attempt, status: "failed" },
      });

      return "failed";
    }
  } finally {
    lock.release();
  }
}

function ignoreLearningOutput(): undefined {
  return undefined;
}
