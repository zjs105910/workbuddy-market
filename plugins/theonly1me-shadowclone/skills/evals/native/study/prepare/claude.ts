import { installIntegration, syncLearningEnvironment } from "@shadowclone/environment";
import { runProcess } from "@shadowclone/core";
import type { ProjectPaths } from "@shadowclone/core";

async function configureRemote(options: { readonly workspace: string; readonly remote: string }): Promise<void> {
  const environment = { PATH: process.env.PATH };
  await runProcess({ arguments: ["git", "init", "-q"], cwd: options.workspace, environment, maximumOutputBytes: 64_000 });
  await runProcess({ arguments: ["git", "config", "remote.origin.url", options.remote], cwd: options.workspace, environment, maximumOutputBytes: 64_000 });
}

export async function installClaudeRouting(options: {
  readonly paths: ProjectPaths;
  readonly workspace: string;
  readonly remote: string | null;
}): Promise<{ readonly synchronized: boolean }> {
  await installIntegration({ paths: options.paths, agent: "claude-code", scope: "global", cwd: options.workspace });
  if (options.remote !== null) await configureRemote({ workspace: options.workspace, remote: options.remote });
  return { synchronized: await syncLearningEnvironment(options.paths) };
}
