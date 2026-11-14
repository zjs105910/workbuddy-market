import path from "node:path";
import { realPathOrNull } from "@shadowclone/core";
import { integrationFilePath, integrationTargets } from "./targets";
import type { Integration } from "./types";

function importedFiles(options: {
  readonly text: string;
  readonly filePath: string;
  readonly homeDirectory: string;
}): ReadonlySet<string> {
  return new Set(
    [...options.text.matchAll(/(?:^|\s)@(~\/\S+|\/\S+|\.{1,2}\/\S+)/g)].flatMap(([, reference]) => {
      if (!reference) return [];

      const absolute = reference.startsWith("~/")
        ? path.join(options.homeDirectory, reference.slice(2))
        : path.resolve(path.dirname(options.filePath), reference);
      const real = realPathOrNull(absolute);

      return real ? [real] : [];
    }),
  );
}

export function importsPeerInstructions(options: {
  readonly integration: Integration;
  readonly filePath: string;
  readonly text: string | null;
  readonly peers: readonly Integration[];
}): boolean {
  if (options.integration.agent !== "claude-code" || options.integration.scope !== "global" || options.text === null) {
    return false;
  }

  const imported = importedFiles({
    text: options.text,
    filePath: options.filePath,
    homeDirectory: options.integration.userDirectory,
  });

  return options.peers.some(
    (peer) =>
      peer.scope === "global" &&
      peer.agent !== "claude-code" &&
      integrationTargets(peer).some(
        (file) =>
          file.kind === "instructions" &&
          imported.has(realPathOrNull(integrationFilePath({ integration: peer, file })) ?? ""),
      ),
  );
}
