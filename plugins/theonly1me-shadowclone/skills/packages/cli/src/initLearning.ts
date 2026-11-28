import type { ManagedPolicy, ShadowcloneConfig, ProjectPaths } from "@shadowclone/core";
import {
  allowlistedSignals,
  authorizedLearningEvents,
  bindHistoricalRepository,
  currentEvidenceAuthorization,
  distillConcurrency,
  episodeId,
  type LearningPreferences,
  listHistoricalRepositories,
  readLearningState,
  selectLearningPreferences,
  selectNewestLearningEpisodes,
  writeLearningReceipt,
  writeLearningState,
} from "@shadowclone/learning";
import {
  createLearningExecution,
  detectEngine,
  setupLearningLimits,
  type EngineId,
  type EngineRunner,
  type LearningExecution,
} from "@shadowclone/agents";
import {
  ingestSources,
  openEventIndex,
  deriveSignals,
  type GitRemoteReader,
} from "@shadowclone/sessions";
import { runDeepLearning } from "./deepLearn";
import path from "node:path";
import { acquireLocalLock } from "@shadowclone/core";

export type SetupEngine = {
  readonly engine: EngineId;
  readonly runner: EngineRunner;
  readonly execution: LearningExecution;
};

export async function createSetupEngine(options: {
  readonly policy: ManagedPolicy;
  readonly engine?: EngineId;
  readonly runner?: EngineRunner;
  readonly preferences?: LearningPreferences;
}): Promise<SetupEngine | null> {
  const selected = selectLearningPreferences({ explicit: options, saved: options.preferences });
  const detected = options.runner
    ? null
    : await detectEngine({
        purpose: "distill",
        allowedEngines: options.policy.allowedEngines,
        preferredEngine: selected.engine,
        model: selected.model,
      });
  const engine = selected.engine ?? detected?.selectedEngine;
  const runner = options.runner ?? detected?.runner;

  if (!engine || !runner) {
    return null;
  }
  if (!options.policy.allowedEngines.includes(engine)) throw new Error("Managed policy blocks the selected learning engine");

  return {
    engine,
    runner,
    execution: createLearningExecution({
      engine,
      runner,
      limits: setupLearningLimits,
    }),
  };
}

export async function runSetupLearning(options: {
  readonly paths: ProjectPaths;
  readonly configPath?: string;
  readonly config: ShadowcloneConfig;
  readonly policy: ManagedPolicy;
  readonly setupEngine: SetupEngine;
  readonly now: number;
  readonly readRemote?: GitRemoteReader;
  readonly writeLine: (line: string) => void;
  readonly confirmHistoricalRepository?: (question: string) => Promise<boolean> | boolean;
}): Promise<number> {
  const lock = await acquireLocalLock(path.join(options.paths.shadowcloneDirectory, "learning-worker.db"));
  if (!lock) throw new Error("Another learning attempt is running");
  const index = await openEventIndex(options.paths.indexDatabase).catch((error: unknown) => {
    lock.release();
    throw error;
  });
  let stage: "ingestion" | "learning" | "complete" = "ingestion";
  let episodeCount = 0;
  let sourceCounts: Record<string, number> = {};

  try {
    await ingestSources({
      index,
      config: options.config,
      paths: options.paths,
    });

    if (options.config.sources["git-metadata"]) {
      const candidates = await listHistoricalRepositories({
        index,
        events: authorizedLearningEvents({ events: index.listEvents(), config: options.config }),
        blockedOrigins: options.policy.blockedOrigins,
        readRemote: options.readRemote,
      });

      for (const candidate of candidates) {
        if (await options.confirmHistoricalRepository?.(
          `Associate ${candidate.sessionCount} past session(s) in ${candidate.directory} with ${candidate.repository.id}? [y/N]`,
        )) {
          await bindHistoricalRepository({
            index,
            candidate,
            paths: options.paths,
            events: authorizedLearningEvents({ events: index.listEvents(), config: options.config }),
          });
        }
      }

      if (candidates.length > 0 && !options.confirmHistoricalRepository) {
        options.writeLine(`${candidates.length} historical repository association(s) need review. Run shadowclone learning repositories.`);
      }
    }

    const events = authorizedLearningEvents({
      events: index.listEvents(),
      config: options.config,
    });
    sourceCounts = Object.fromEntries([...Map.groupBy(events, (event) => event.source)]
      .map(([source, entries]) => [source, entries.length]));
    stage = "learning";

    const derived = await deriveSignals({
      events,
      corpus: index.getCorpusSummary(),
      gitMetadataEnabled: options.config.sources["git-metadata"],
      readRemote: options.readRemote,
      blockedOrigins: options.policy.blockedOrigins,
      bindings: index,
    });

    const eligibleSignals = allowlistedSignals({
      signals: derived.learning,
      events: derived.events,
    }).filter((signal) => signal.textRefs.length > 0);

    const state = await readLearningState(options.paths);
    const signals = selectNewestLearningEpisodes({
      signals: eligibleSignals,
      state,
      now: options.now,
      limit: distillConcurrency * 20,
    });
    episodeCount = signals.length;

    if (signals.length === 0) {
      await writeLearningReceipt({
        paths: options.paths,
        receipt: {
          startedAt: options.now, mode: "setup", stage: "complete", outcome: "no-eligible-evidence",
          episodeCount, sourceCounts, proposalCount: 0, pendingCount: 0,
          nextAction: "Teach a standing preference, then run shadowclone learn --deep.",
        },
      });
      return 0;
    }

    const result = await runDeepLearning({
      signals,
      events: derived.events,
      authorizeRef: currentEvidenceAuthorization({
        paths: options.paths,
        configPath: options.configPath,
        events: derived.events,
      }),
      paths: options.paths,
      policy: options.policy,
      runner: options.setupEngine.runner,
      engine: options.setupEngine.engine,
      execution: options.setupEngine.execution,
      limits: setupLearningLimits,
      dryRun: false,
      apply: true,
      writeLine: options.writeLine,
    });

    await writeLearningState({
      paths: options.paths,
      state: {
        ...state,
        processed: [
          ...state.processed,
          ...signals.map((signal) => ({
            id: episodeId(signal),
            timestamp: signal.timestamp,
          })),
        ],
      },
    });

    stage = "complete";
    await writeLearningReceipt({
      paths: options.paths,
      receipt: {
        startedAt: options.now, mode: "setup", stage,
        outcome: result.changesProposed > 0 ? "guidance-recorded" : result.noChangeReason,
        engine: result.engine, ruleKeys: [...result.ruleKeys],
        episodeCount, sourceCounts, proposalCount: result.changesProposed, pendingCount: result.pendingReview,
        nextAction: "Run shadowclone learning pending to inspect review and delivery decisions.",
      },
    });

    return result.changesProposed;
  } catch (error) {
    await writeLearningReceipt({
      paths: options.paths,
      receipt: {
        startedAt: options.now, mode: "setup", stage,
        outcome: stage === "ingestion" ? "ingestion-failed" : "engine-failed",
        episodeCount, sourceCounts, proposalCount: 0, pendingCount: 0,
        nextAction: "Run shadowclone doctor, then retry shadowclone learn --deep.",
      },
    });
    throw error;
  } finally {
    index.close();
    lock.release();
  }
}
