import path from "node:path";
import { z } from "zod";
import { fingerprint, readLocalText, replaceLocalText } from "@shadowclone/core";
import type { ProjectPaths } from "@shadowclone/core";
import type { CorrectionSignal } from "@shadowclone/sessions";
import {
  readLearningLedger,
  writeLearningLedger,
  type ProcessedEpisode,
} from "./ledger";

export const learningInterval = 60 * 60 * 1_000;
export const learningBatchSize = 60;
const stateSchema = z.strictObject({
  lastAttemptAt: z.number().nullable(),
  lastCompletedAt: z.number().nullable(),
  status: z.enum(["idle", "running", "completed", "failed"]),
});

export type LearningState = z.infer<typeof stateSchema> & {
  readonly processed: readonly ProcessedEpisode[];
};

export function episodeId(signal: CorrectionSignal): string {
  return fingerprint(
    JSON.stringify({
      session: signal.sessionId,
      timestamp: signal.timestamp,
      references: signal.textRefs,
    }),
  );
}

export function selectLearningEpisodes(options: {
  readonly signals: readonly CorrectionSignal[];
  readonly state: LearningState;
  readonly now: number;
  readonly limit?: number;
}): readonly CorrectionSignal[] {
  const processed = new Set(options.state.processed.map((entry) => entry.id));

  return options.signals
    .filter(
      (signal) =>
        signal.timestamp <= options.now && !processed.has(episodeId(signal)),
    )
    .sort((left, right) => right.timestamp - left.timestamp)
    .slice(0, options.limit ?? learningBatchSize);
}

export function selectNewestLearningEpisodes(options: {
  readonly signals: readonly CorrectionSignal[];
  readonly state: LearningState;
  readonly now: number;
  readonly limit: number;
}): readonly CorrectionSignal[] {
  return selectLearningEpisodes(options);
}

export function selectRequestedLearningEpisodes(options: {
  readonly signals: readonly CorrectionSignal[];
  readonly sessionKeys: ReadonlySet<string>;
  readonly state: LearningState;
}): readonly CorrectionSignal[] {
  const processed = new Set(options.state.processed.map((entry) => entry.id));

  return options.signals
    .filter(
      (signal) =>
        options.sessionKeys.has(fingerprint(signal.sessionId)) &&
        !processed.has(episodeId(signal)),
    )
    .sort((left, right) => right.timestamp - left.timestamp)
    .slice(0, learningBatchSize);
}

export async function readLearningState(
  paths: ProjectPaths,
): Promise<LearningState> {
  const contents = await readLocalText(
    path.join(paths.shadowcloneDirectory, "learning.json"),
  );

  if (contents === null) {
    return {
      lastAttemptAt: null,
      lastCompletedAt: null,
      status: "idle",
      processed: [],
    };
  }

  try {
    return {
      ...stateSchema.parse(JSON.parse(contents)),
      processed: await readLearningLedger(paths),
    };
  } catch {
    throw new Error("Invalid automatic learning state");
  }
}

export async function writeLearningState(options: {
  readonly paths: ProjectPaths;
  readonly state: LearningState;
}): Promise<void> {
  const filePath = path.join(
    options.paths.shadowcloneDirectory,
    "learning.json",
  );
  const { processed, ...summary } = options.state;

  await writeLearningLedger({ paths: options.paths, entries: processed });
  await replaceLocalText({
    filePath,
    previous: await readLocalText(filePath),
    next: `${JSON.stringify(summary, null, 2)}\n`,
  });
}
