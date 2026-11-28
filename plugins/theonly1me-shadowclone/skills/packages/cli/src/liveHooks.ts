import path from "node:path";
import {
  compileContext,
  readIntegrations,
  sessionStartProjection,
} from "@shadowclone/environment";
import { canonicalPath, projectPaths } from "@shadowclone/core";
import type { ProjectPaths } from "@shadowclone/core";
import type { GitRemoteReader } from "@shadowclone/sessions";
import { parseHookInput, readHookString } from "./hookInput";

type LiveHookOptions = {
  readonly input: string;
  readonly configPath?: string;
  readonly paths?: ProjectPaths;
  readonly readRemote?: GitRemoteReader;
  readonly managedConfigPath?: string | null;
};

export type SessionStartContext = {
  readonly hookSpecificOutput: {
    readonly hookEventName: "SessionStart";
    readonly additionalContext: string;
  };
};

async function nativeClaudeDeliveryCovers(options: {
  readonly paths: ProjectPaths;
  readonly cwd: string;
}): Promise<boolean> {
  const integrations = await readIntegrations(options.paths);

  return integrations.some(
    (integration) =>
      integration.agent === "claude-code" &&
      (integration.scope === "global" ||
        options.cwd === integration.directory ||
        options.cwd.startsWith(`${integration.directory}${path.sep}`)),
  );
}

async function activeProfile(options: LiveHookOptions): Promise<string | null> {
  const paths = options.paths ?? projectPaths;
  const input = parseHookInput(options.input);
  const cwd = readHookString(input, "cwd") ?? process.cwd();

  if (await nativeClaudeDeliveryCovers({ paths, cwd: canonicalPath(cwd) })) {
    return null;
  }

  const profile = await compileContext({
    paths,
    cwd,
    configPath: options.configPath,
    managedConfigPath: options.managedConfigPath,
    readRemote: options.readRemote,
    ...sessionStartProjection,
  });

  return profile === null || profile.length === 0 ? null : profile;
}

export async function getSessionStartContext(
  options: LiveHookOptions,
): Promise<SessionStartContext | null> {
  const profile = await activeProfile(options);

  return profile === null
    ? null
    : {
        hookSpecificOutput: {
          hookEventName: "SessionStart",
          additionalContext: profile,
        },
      };
}

export async function runSessionStartHook(
  options: LiveHookOptions,
): Promise<void> {
  const response = await getSessionStartContext(options);

  if (response !== null) {
    await Bun.stdout.write(`${JSON.stringify(response)}\n`);
  }
}
