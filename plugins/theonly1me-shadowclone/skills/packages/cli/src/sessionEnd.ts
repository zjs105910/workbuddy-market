import { realpath } from "node:fs/promises";
import path from "node:path";
import { readEffectiveConfig, projectPaths } from "@shadowclone/core";
import { ingestClaudeTranscript, openEventIndex } from "@shadowclone/sessions";
import type { ProjectPaths } from "@shadowclone/core";
import type { GitRemoteReader } from "@shadowclone/sessions";
import { parseHookInput, readHookString } from "./hookInput";
import { refreshOfflineProfile } from "./profile";

async function isInsideDirectory(options: {
  readonly filePath: string;
  readonly directory: string;
}): Promise<boolean> {
  let filePath: string;
  let directory: string;

  try {
    [filePath, directory] = await Promise.all([
      realpath(options.filePath),
      realpath(options.directory),
    ]);
  } catch {
    return false;
  }

  const relative = path.relative(directory, filePath);

  return (
    relative.length > 0 &&
    !relative.startsWith(`..${path.sep}`) &&
    relative !== ".." &&
    !path.isAbsolute(relative)
  );
}

export async function runSessionEndHook(options: {
  readonly input: string;
  readonly configPath?: string;
  readonly paths?: ProjectPaths;
  readonly readRemote?: GitRemoteReader;
  readonly managedConfigPath?: string | null;
}): Promise<void> {
  const paths = options.paths ?? projectPaths;
  const { config, policy } = await readEffectiveConfig({
    configPath: options.configPath,
    managedConfigPath:
      options.managedConfigPath === undefined
        ? paths.managedConfigFile
        : options.managedConfigPath,
  });

  if (!policy.enabled || !config.sources["claude-code"]) {
    return;
  }

  const input = parseHookInput(options.input);
  const sourcePath = readHookString(input, "transcript_path");
  const cwd = readHookString(input, "cwd") ?? process.cwd();

  if (
    sourcePath === null ||
    !(await isInsideDirectory({
      filePath: sourcePath,
      directory: paths.claudeProjectsDirectory,
    }))
  ) {
    throw new Error("Session hook received an invalid transcript path");
  }

  const index = await openEventIndex(paths.indexDatabase);

  try {
    await ingestClaudeTranscript({ index, sourcePath });
    await refreshOfflineProfile({
      config,
      paths,
      cwd,
      readRemote: options.readRemote,
      blockedOrigins: policy.blockedOrigins,
    });
  } finally {
    index.close();
  }
}
