import path from "node:path";
import { commitLocalChanges } from "@shadowclone/changes";
import {
  readEffectiveConfig,
  runHostCommand,
  acquireLocalLock,
  canonicalPath,
  type ProjectPaths,
} from "@shadowclone/core";
import {
  isOriginBlocked,
  resolveRepository,
  type GitRemoteReader,
} from "@shadowclone/sessions";
import type { ClaudeMemoryDecisions } from "./decisions";
import {
  createClaudeMemoryMigrationPlan,
  type ClaudeMemoryMigrationPlan,
} from "./plan";

export type ClaudeMemoryMigrationResult = {
  readonly plan: ClaudeMemoryMigrationPlan;
  readonly revisionId: string | null;
};

async function gitRoot(cwd: string): Promise<string> {
  const result = await runHostCommand({
    arguments: ["git", "rev-parse", "--show-toplevel"],
    cwd,
  });

  if (result.exitCode !== 0 || result.stdout.trim().length === 0) {
    throw new Error("Claude memory migration requires a Git repository");
  }

  return canonicalPath(result.stdout.trim());
}

export async function migrateClaudeMemory(options: {
  readonly paths: ProjectPaths;
  readonly cwd: string;
  readonly apply: boolean;
  readonly decisions?: ClaudeMemoryDecisions;
  readonly repositoryRoot?: string;
  readonly configPath?: string;
  readonly managedConfigPath?: string | null;
  readonly readRemote?: GitRemoteReader;
  readonly now?: number;
}): Promise<ClaudeMemoryMigrationResult> {
  const { config, policy } = await readEffectiveConfig({
    configPath: options.configPath ?? options.paths.configFile,
    managedConfigPath:
      options.managedConfigPath === undefined
        ? options.paths.managedConfigFile
        : options.managedConfigPath,
  });

  if (!policy.enabled || !config.sources["claude-memory"]) {
    throw new Error("Enable the claude-memory source before migration");
  }

  const repositoryRoot = options.repositoryRoot ?? (await gitRoot(options.cwd));
  const repository = await resolveRepository({
    cwd: repositoryRoot,
    enabled: config.sources["git-metadata"],
    readRemote: options.readRemote,
  });

  if (isOriginBlocked({ repository, patterns: policy.blockedOrigins })) {
    throw new Error("Managed policy blocks this repository");
  }

  const plan = await createClaudeMemoryMigrationPlan({
    paths: options.paths,
    repositoryRoot,
    repository,
    decisions: options.decisions?.feedback,
    excludedReferences: options.decisions?.excludeReferences,
    now: options.now,
  });

  if (!options.apply || plan.alreadyApplied) {
    return { plan, revisionId: null };
  }

  if (plan.reviewRequired.length > 0) {
    throw new Error(
      "Every feedback memory needs a reviewed disposition before apply",
    );
  }

  const lock = await acquireLocalLock(
    path.join(options.paths.shadowcloneDirectory, "profile-write.db"),
  );

  if (!lock) {
    throw new Error("Another profile update is running; retry shortly");
  }

  try {
    const revisionId = await commitLocalChanges({
      paths: options.paths,
      root: options.paths.profileDirectory,
      kind: "profile",
      updates: plan.updates,
    });

    return { plan, revisionId };
  } finally {
    lock.release();
  }
}
