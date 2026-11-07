import path from "node:path";
import { z } from "zod";
import {
  readEffectiveConfig,
  sourceIds,
  acquireLocalLock,
  fingerprint,
  readLocalText,
  replaceLocalText,
} from "@shadowclone/core";
import type { AssessedCorrection } from "../distill/feedback";
import {
  type EnvironmentState,
  readEnvironment,
  recordFingerprint,
} from "@shadowclone/environment";
import type { ProjectPaths } from "@shadowclone/core";

const feedbackSchema = z.array(z.strictObject({
  key: z.string(),
  inputFingerprint: z.string(),
  guidanceHash: z.string(),
  evidenceHash: z.string(),
  source: z.enum(sourceIds),
  timestamp: z.number(),
  reviewedAt: z.number().optional(),
}));

function feedbackFile(paths: ProjectPaths): string {
  return path.join(paths.shadowcloneDirectory, "learning-feedback.json");
}

async function readFeedback(paths: ProjectPaths) {
  const text = await readLocalText(feedbackFile(paths));
  return text === null ? [] : feedbackSchema.parse(JSON.parse(text));
}

function guidanceHash(rule: EnvironmentState["records"][number]["rule"]): string {
  return fingerprint(JSON.stringify({ body: rule.body, scope: rule.scope,
    origin: rule.originDirectory, repository: rule.repositoryName, appliesWhen: rule.appliesWhen }));
}

export async function recordLaterCorrections(options: {
  readonly paths: ProjectPaths;
  readonly state: EnvironmentState | null;
  readonly corrections: readonly AssessedCorrection[];
}): Promise<void> {
  if (!options.state || options.corrections.length === 0) return;
  const lock = await acquireLocalLock(path.join(options.paths.shadowcloneDirectory, "learning-feedback.db"));
  if (!lock) throw new Error("Another learning feedback update is running");
  try {
    const { config } = await readEffectiveConfig({
      configPath: options.paths.configFile, managedConfigPath: options.paths.managedConfigFile,
    });
    const entries = await readFeedback(options.paths);
    for (const correction of options.corrections) {
      const source = sourceIds.find((entry) => correction.sessionId.startsWith(`${entry}:`));
      if (!source || !config.sources[source]) continue;
      const record = options.state.records.find(({ rule }) => rule.key === correction.key);
      if (!record || record.retirementRequested || record.rule.status !== "active") continue;
      const inputFingerprint = recordFingerprint(record);
      const published = options.state.dispositions.find((entry) => entry.key === correction.key &&
        entry.inputFingerprint === inputFingerprint &&
        (entry.status === "published" || entry.status === "covered") &&
        entry.publishedAt !== undefined && entry.publishedAt < correction.timestamp);
      if (!published) continue;
      const evidenceHash = fingerprint(correction.evidenceId);
      if (entries.some((entry) => entry.key === correction.key && entry.evidenceHash === evidenceHash)) continue;
      entries.push({ key: correction.key, inputFingerprint, guidanceHash: guidanceHash(record.rule), evidenceHash, source, timestamp: correction.timestamp });
    }
    const filePath = feedbackFile(options.paths);
    await replaceLocalText({ filePath, previous: await readLocalText(filePath), next: `${JSON.stringify(entries, null, 2)}\n` });
  } finally {
    lock.release();
  }
}

export async function correctionReviewSignals(paths: ProjectPaths) {
  const { config } = await readEffectiveConfig({ configPath: paths.configFile, managedConfigPath: paths.managedConfigFile });
  const state = await readEnvironment(paths);
  const entries = (await readFeedback(paths)).filter((entry) => {
    const record = state?.records.find(({ rule }) => rule.key === entry.key);
    return config.sources[entry.source] && entry.reviewedAt === undefined && record !== undefined &&
      !record.retirementRequested && record.rule.status === "active" && entry.guidanceHash === guidanceHash(record.rule);
  });
  return [...Map.groupBy(entries, (entry) => entry.key)].map(([key, corrections]) => ({
    key,
    count: corrections.length,
    lastCorrectionAt: Math.max(...corrections.map((entry) => entry.timestamp)),
    reason: "A later correction matched previously published guidance. Review its scope and delivery or run a behavior probe.",
  }));
}

export async function acknowledgeCorrections(options: { readonly paths: ProjectPaths; readonly key: string }): Promise<void> {
  const lock = await acquireLocalLock(path.join(options.paths.shadowcloneDirectory, "learning-feedback.db"));
  if (!lock) throw new Error("Another learning feedback update is running");
  try {
    const filePath = feedbackFile(options.paths);
    const entries = await readFeedback(options.paths);
    if (!entries.some((entry) => entry.key === options.key)) throw new Error("No later corrections were recorded for this rule");
    const next = entries.map((entry) => entry.key === options.key ? { ...entry, reviewedAt: Date.now() } : entry);
    await replaceLocalText({ filePath, previous: await readLocalText(filePath), next: `${JSON.stringify(next, null, 2)}\n` });
  } finally {
    lock.release();
  }
}
