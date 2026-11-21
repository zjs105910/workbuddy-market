import { readEffectiveConfig } from "@shadowclone/core";
import type { ProjectPaths } from "@shadowclone/core";
import {
  isOriginBlocked,
  resolveRepository,
  type GitRemoteReader,
} from "@shadowclone/sessions";
import { renderReference } from "./format";
import { readScopedReferences } from "./read";
import { searchReferences } from "./search";

export const maximumRecallBytes = 64 * 1024;

export type RecallResult = {
  readonly records: readonly string[];
  readonly matched: number;
  readonly omittedForBudget: number;
  readonly usedBytes: number;
};

export async function recallReferences(options: {
  readonly query: string;
  readonly limit: number;
  readonly cwd: string;
  readonly paths: ProjectPaths;
  readonly configPath?: string;
  readonly managedConfigPath?: string | null;
  readonly readRemote?: GitRemoteReader;
}): Promise<RecallResult> {
  const { config, policy } = await readEffectiveConfig({
    configPath: options.configPath ?? options.paths.configFile,
    managedConfigPath:
      options.managedConfigPath === undefined
        ? options.paths.managedConfigFile
        : options.managedConfigPath,
  });

  if (!policy.enabled) {
    return { records: [], matched: 0, omittedForBudget: 0, usedBytes: 0 };
  }

  const repository = await resolveRepository({
    cwd: options.cwd,
    enabled: config.sources["git-metadata"],
    readRemote: options.readRemote,
  });

  if (isOriginBlocked({ repository, patterns: policy.blockedOrigins })) {
    return { records: [], matched: 0, omittedForBudget: 0, usedBytes: 0 };
  }

  const matches = searchReferences({
    references: await readScopedReferences({
      profileDirectory: options.paths.profileDirectory,
      origin: repository.origin,
      targetRepo: repository.profileFileName,
    }),
    query: options.query,
    limit: options.limit,
  });

  const records: string[] = [];
  let usedBytes = 0;
  let omittedForBudget = 0;

  for (const match of matches) {
    const text = renderReference(match.record);
    const bytes = Buffer.byteLength(text, "utf8");

    if (usedBytes + bytes > maximumRecallBytes) {
      omittedForBudget += 1;

      continue;
    }

    records.push(text);
    usedBytes += bytes;
  }

  return { records, matched: matches.length, omittedForBudget, usedBytes };
}
