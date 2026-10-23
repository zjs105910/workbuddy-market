import { realpathSync } from "node:fs";
import os from "node:os";
import path from "node:path";

export function canonicalPath(target: string): string {
  const absolute = path.resolve(target);

  try {
    return realpathSync(absolute);
  } catch {
    const parent = path.dirname(absolute);

    return parent === absolute
      ? absolute
      : path.join(canonicalPath(parent), path.basename(absolute));
  }
}

export type ProjectPaths = {
  readonly shadowcloneDirectory: string;
  readonly configFile: string;
  readonly indexDatabase: string;
  readonly profileDirectory: string;
  readonly rejectedProfileFile: string;
  readonly profileManifestFile: string;
  readonly installationsFile: string;
  readonly compiledProfileFile: string;
  readonly distillDirectory: string;
  readonly worktreesDirectory: string;
  readonly runsDirectory: string;
  readonly antigravityBrainDirectory: string;
  readonly antigravityWorkspaceHistoryFile: string;
  readonly claudeProjectsDirectory: string;
  readonly claudePromptHistoryFile: string;
  readonly codexSessionsDirectory: string;
  readonly cursorChatsDirectory: string;
  readonly piAgentDirectory: string;
  readonly piSessionsDirectory: string;
  readonly managedConfigFile: string | null;
  readonly runDirectory: (runId: string) => string;
  readonly worktreeDirectory: (runId: string) => string;
};

function getManagedConfigFile(platform: NodeJS.Platform): string | null {
  if (platform === "darwin") {
    return "/Library/Application Support/shadowclone/managed.json";
  }

  if (platform === "linux") {
    return "/etc/shadowclone/managed.json";
  }

  return null;
}

export function createProjectPaths(options: {
  readonly homeDirectory: string;
  readonly platform: NodeJS.Platform;
  readonly codexHomeDirectory?: string;
  readonly piAgentDirectory?: string;
}): ProjectPaths {
  const shadowcloneDirectory = path.join(
    canonicalPath(options.homeDirectory),
    ".shadowclone",
  );
  const profileDirectory = path.join(shadowcloneDirectory, "profile");

  return {
    shadowcloneDirectory,
    configFile: path.join(shadowcloneDirectory, "config.toml"),
    indexDatabase: path.join(shadowcloneDirectory, "index.db"),
    profileDirectory,
    rejectedProfileFile: path.join(profileDirectory, ".rejected"),
    profileManifestFile: path.join(profileDirectory, ".generated"),
    installationsFile: path.join(shadowcloneDirectory, "installations.json"),
    compiledProfileFile: path.join(profileDirectory, ".compiled.md"),
    distillDirectory: path.join(shadowcloneDirectory, "distill"),
    worktreesDirectory: path.join(shadowcloneDirectory, "worktrees"),
    runsDirectory: path.join(shadowcloneDirectory, "runs"),
    antigravityBrainDirectory: path.join(
      options.homeDirectory,
      ".gemini",
      "antigravity-cli",
      "brain",
    ),
    antigravityWorkspaceHistoryFile: path.join(
      options.homeDirectory,
      ".gemini",
      "antigravity-cli",
      "history.jsonl",
    ),
    claudeProjectsDirectory: path.join(
      options.homeDirectory,
      ".claude",
      "projects",
    ),
    claudePromptHistoryFile: path.join(
      options.homeDirectory,
      ".claude",
      "history.jsonl",
    ),
    codexSessionsDirectory: path.join(
      options.codexHomeDirectory ?? path.join(options.homeDirectory, ".codex"),
      "sessions",
    ),
    cursorChatsDirectory: path.join(options.homeDirectory, ".cursor", "chats"),
    piAgentDirectory: options.piAgentDirectory ?? path.join(options.homeDirectory, ".pi", "agent"),
    piSessionsDirectory: path.join(options.piAgentDirectory ?? path.join(options.homeDirectory, ".pi", "agent"), "sessions"),
    managedConfigFile: getManagedConfigFile(options.platform),
    runDirectory: (runId) => path.join(shadowcloneDirectory, "runs", runId),
    worktreeDirectory: (runId) =>
      path.join(shadowcloneDirectory, "worktrees", runId),
  };
}

export const projectPaths = createProjectPaths({
  homeDirectory: os.homedir(),
  platform: process.platform,
  codexHomeDirectory: process.env.CODEX_HOME,
  piAgentDirectory: process.env.PI_CODING_AGENT_DIR,
});
