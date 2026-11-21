import path from "node:path";
import { canonicalPath, readLocalText } from "@shadowclone/core";
import { readIntegrations } from "../../integrations/state";
import { prepareIntegrationFiles, savedRecords } from "../../integrations/files";
import type { Integration } from "../../integrations/types";
import { sharedIntegrationUpdates } from "../../integrations/sharedUpdates";
import type { BuildContext } from "./definition";

export async function buildIntegrations(
  context: BuildContext,
): Promise<readonly Integration[]> {
  const current = await readIntegrations(context.paths);

  if (current.some((integration) => integration.scope === "global")) {
    return current;
  }

  const homeDirectory = path.dirname(context.paths.shadowcloneDirectory);

  const directories = {
    "claude-code": path.join(homeDirectory, ".claude"),
    codex: canonicalPath(path.dirname(context.paths.codexSessionsDirectory)),
    cursor: path.join(homeDirectory, ".cursor"),
    antigravity: path.join(homeDirectory, ".gemini/config"),
    pi: canonicalPath(context.paths.piAgentDirectory),
  };

  const overrideExists = await Bun.file(
    path.join(directories.codex, "AGENTS.override.md"),
  ).exists();

  return [
    ...current,
    ...(["claude-code", "codex", "cursor", "antigravity", "pi"] as const).map(
      (agent): Integration => ({
        id: crypto.randomUUID(),
        agent,
        scope: "global",
        directory: directories[agent],
        userDirectory: homeDirectory,
        codexInstructions: overrideExists ? "AGENTS.override.md" : "AGENTS.md",
        files: [],
        excludes: [],
        deliveredAt: null,
      }),
    ),
  ];
}

export async function planBuildIntegrations(
  options: BuildContext & { readonly routing: string },
) {
  const integrations = await buildIntegrations(options);
  const updates = [];
  const updated = [];

  for (const integration of integrations) {
    if (integration.scope !== "global") {
      updated.push(integration);

      continue;
    }

    const changes = await prepareIntegrationFiles({
      integration,
      profile: options.routing,
      environment: true,
      peers: integrations,
    });

    updates.push(
      ...changes.map(({ filePath, previous, next }) => ({
        filePath,
        previous,
        next,
      })),
    );
    updated.push({
      ...integration,
      files: savedRecords(changes),
    });
  }

  const filePath = path.join(
    options.paths.shadowcloneDirectory,
    "integrations.json",
  );

  updates.push({
    filePath,
    previous: await readLocalText(filePath),
    next: `${JSON.stringify({ version: 1, integrations: updated }, null, 2)}\n`,
  });

  return { updates: sharedIntegrationUpdates(updates), integrations: updated };
}
