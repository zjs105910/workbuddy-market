import { lstat, opendir } from "node:fs/promises";
import path from "node:path";
import type { ProjectPaths } from "@shadowclone/core";

export const onboardingCaptureSourceIds = [
  "antigravity",
  "claude-code",
  "claude-prompts",
  "codex",
  "cursor",
  "pi",
] as const;

export type OnboardingCaptureSourceId =
  (typeof onboardingCaptureSourceIds)[number];

export type OnboardingPresence = {
  readonly hasRepositoryGuidance: boolean;
  readonly presentCaptureSources: ReadonlySet<OnboardingCaptureSourceId>;
};

async function directoryHasEntry(directoryPath: string): Promise<boolean> {
  try {
    const directory = await opendir(directoryPath);

    try {
      return (await directory.read()) !== null;
    } finally {
      await directory.close();
    }
  } catch {
    return false;
  }
}

async function fileHasContent(filePath: string): Promise<boolean> {
  try {
    const file = Bun.file(filePath);

    return (await file.exists()) && file.size > 0;
  } catch {
    return false;
  }
}

async function repositoryFileExists(filePath: string): Promise<boolean> {
  const metadata = await lstat(filePath).catch(() => null);

  return metadata !== null && !metadata.isSymbolicLink();
}

async function repositorySkillRootHasEntry(options: {
  readonly workingDirectory: string;
  readonly rootName: string;
}): Promise<boolean> {
  const parentPath = path.join(options.workingDirectory, options.rootName);
  const parentMetadata = await lstat(parentPath).catch(() => null);

  if (!parentMetadata?.isDirectory()) {
    return false;
  }

  const rootPath = path.join(parentPath, "skills");
  const rootMetadata = await lstat(rootPath).catch(() => null);

  return (
    rootMetadata?.isDirectory() === true && (await directoryHasEntry(rootPath))
  );
}

async function hasRepositoryGuidance(
  workingDirectory: string,
): Promise<boolean> {
  const filenames = ["CLAUDE.md", "AGENTS.md", ".cursorrules"];
  const rootFileExists = (
    await Promise.all(
      filenames.map((filename) =>
        repositoryFileExists(path.join(workingDirectory, filename)),
      ),
    )
  ).some(Boolean);

  if (rootFileExists) {
    return true;
  }

  return (
    await Promise.all([
      repositorySkillRootHasEntry({ workingDirectory, rootName: ".claude" }),
      repositorySkillRootHasEntry({ workingDirectory, rootName: ".agents" }),
    ])
  ).some(Boolean);
}

export async function detectOnboardingPresence(options: {
  readonly paths: ProjectPaths;
  readonly workingDirectory: string;
}): Promise<OnboardingPresence> {
  const results = await Promise.all([
    directoryHasEntry(options.paths.antigravityBrainDirectory),
    directoryHasEntry(options.paths.claudeProjectsDirectory),
    fileHasContent(options.paths.claudePromptHistoryFile),
    directoryHasEntry(options.paths.codexSessionsDirectory),
    directoryHasEntry(options.paths.cursorChatsDirectory),
    directoryHasEntry(options.paths.piSessionsDirectory),
  ]);
  const presentCaptureSources = new Set<OnboardingCaptureSourceId>();

  for (const [sourceIndex, sourceId] of onboardingCaptureSourceIds.entries()) {
    if (results[sourceIndex] === true) {
      presentCaptureSources.add(sourceId);
    }
  }

  return {
    hasRepositoryGuidance: await hasRepositoryGuidance(
      options.workingDirectory,
    ),
    presentCaptureSources,
  };
}
