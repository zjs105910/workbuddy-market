import path from "node:path";
import { z } from "zod";
import { readLocalText, replaceLocalText } from "@shadowclone/core";
import type { ProjectPaths } from "@shadowclone/core";

const receiptSchema = z.strictObject({
  id: z.uuid(),
  startedAt: z.number(),
  completedAt: z.number(),
  mode: z.enum(["manual", "setup", "automatic", "maintenance"]),
  outcome: z.enum([
    "no-eligible-evidence",
    "already-covered",
    "uncertain-evidence",
    "awaiting-review",
    "guidance-recorded",
    "guidance-published",
    "needs-scope-or-publication",
    "ingestion-failed",
    "engine-failed",
    "publication-failed",
  ]),
  stage: z.enum(["ingestion", "learning", "publication", "complete"]),
  episodeCount: z.number().int().nonnegative(),
  sourceCounts: z.record(z.string(), z.number().int().nonnegative()),
  proposalCount: z.number().int().nonnegative(),
  pendingCount: z.number().int().nonnegative(),
  engine: z.string().nullable().default(null),
  model: z.string().nullable().default(null),
  ruleKeys: z.array(z.string()).default([]),
  nextAction: z.string(),
});

export type LearningReceipt = z.infer<typeof receiptSchema>;

function latestFile(paths: ProjectPaths): string {
  return path.join(paths.shadowcloneDirectory, "learning-attempts", "latest.json");
}

export async function readLatestLearningReceipt(paths: ProjectPaths): Promise<LearningReceipt | null> {
  const contents = await readLocalText(latestFile(paths));

  return contents === null ? null : receiptSchema.parse(JSON.parse(contents));
}

export async function writeLearningReceipt(options: {
  readonly paths: ProjectPaths;
  readonly receipt: Omit<z.input<typeof receiptSchema>, "id" | "completedAt">;
}): Promise<LearningReceipt> {
  const receipt = receiptSchema.parse({
    ...options.receipt,
    id: crypto.randomUUID(),
    completedAt: Date.now(),
  });
  const filePath = path.join(options.paths.shadowcloneDirectory, "learning-attempts", `${receipt.id}.json`);
  const next = `${JSON.stringify(receipt, null, 2)}\n`;

  await replaceLocalText({ filePath, previous: null, next });
  const latest = latestFile(options.paths);
  await replaceLocalText({ filePath: latest, previous: await readLocalText(latest), next });

  return receipt;
}
