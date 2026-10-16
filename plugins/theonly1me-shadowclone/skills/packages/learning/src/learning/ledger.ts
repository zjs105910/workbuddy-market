import { existsSync } from "node:fs";
import path from "node:path";
import { z } from "zod";
import { readLocalText, replaceLocalText } from "@shadowclone/core";
import type { ProjectPaths } from "@shadowclone/core";

const entriesSchema = z.array(
  z.strictObject({ id: z.string(), timestamp: z.number() }),
);

export type ProcessedEpisode = z.infer<typeof entriesSchema>[number];

async function ledgerFiles(paths: ProjectPaths): Promise<readonly string[]> {
  const directory = path.join(paths.shadowcloneDirectory, "learning-ledger");

  if (!existsSync(directory)) {
    return [];
  }

  return Array.fromAsync(
    new Bun.Glob("*.json").scan({ cwd: directory, onlyFiles: true }),
  );
}

export async function readLearningLedger(
  paths: ProjectPaths,
): Promise<readonly ProcessedEpisode[]> {
  const entries: ProcessedEpisode[] = [];

  for (const filename of await ledgerFiles(paths)) {
    if (!/^\d{4}-\d{2}-\d{2}\.json$/.test(filename)) {
      throw new Error("Invalid learning ledger file");
    }

    const contents = await readLocalText(
      path.join(paths.shadowcloneDirectory, "learning-ledger", filename),
    );

    try {
      entries.push(...entriesSchema.parse(JSON.parse(contents ?? "[]")));
    } catch {
      throw new Error("Invalid learning ledger");
    }
  }

  return entries;
}

export async function writeLearningLedger(options: {
  readonly paths: ProjectPaths;
  readonly entries: readonly ProcessedEpisode[];
}): Promise<void> {
  const days = Map.groupBy(
    options.entries,
    (entry) => `${new Date(entry.timestamp).toISOString().slice(0, 10)}.json`,
  );
  const filenames = new Set([
    ...days.keys(),
    ...(await ledgerFiles(options.paths)),
  ]);

  for (const filename of filenames) {
    if (!/^\d{4}-\d{2}-\d{2}\.json$/.test(filename)) {
      throw new Error("Invalid learning ledger file");
    }

    const filePath = path.join(
      options.paths.shadowcloneDirectory,
      "learning-ledger",
      filename,
    );
    const entries = days.get(filename);

    await replaceLocalText({
      filePath,
      previous: await readLocalText(filePath),
      next: entries ? `${JSON.stringify(entries)}\n` : null,
    });
  }
}
