import path from "node:path";
import { readIntegrations } from "@shadowclone/environment";
import { readLocalText, replaceLocalText } from "@shadowclone/core";
import type { ProjectPaths } from "@shadowclone/core";
import { promptConfirmation, type ConfirmPrompt } from "./confirm";
import { detectedIntegrationAgents } from "./initDetection";
import { installNativeCommand } from "./native";

async function installDetectedAgents(paths: ProjectPaths): Promise<void> {
  const agents = await detectedIntegrationAgents(paths);

  if (agents.length > 0) {
    await installNativeCommand({
      agents,
      scope: "global",
      subagent: false,
      autoDelegate: false,
    });
  }
}

export async function offerNativeUpgrade(options: {
  readonly paths: ProjectPaths;
  readonly ask?: ConfirmPrompt;
  readonly setup?: () => Promise<void>;
}): Promise<boolean> {
  if ((await readIntegrations(options.paths)).length > 0) {
    return false;
  }

  const markerPath = path.join(
    options.paths.shadowcloneDirectory,
    "native-upgrade.json",
  );

  if (await Bun.file(markerPath).exists()) {
    return false;
  }

  const accepted = await (options.ask ?? promptConfirmation)(
    "Set up Shadowclone's global main-agent context and session hooks now?",
  );

  if (accepted) {
    await (options.setup ?? (() => installDetectedAgents(options.paths)))();
  }

  await replaceLocalText({
    filePath: markerPath,
    previous: await readLocalText(markerPath),
    next: `${JSON.stringify({ version: 1, prompted: true }, null, 2)}\n`,
  });

  return accepted;
}
