import { ownedWrite } from "@shadowclone/core";
import path from "node:path";

export function renderAgent(options: {
  readonly profile: string;
  readonly name?: string;
}): string {
  const name = options.name ?? "shadowclone";

  if (!/^[a-z0-9-]+$/.test(name)) {
    throw new Error(
      "Agent name must use lowercase letters, numbers, and hyphens",
    );
  }

  return [
    "---",
    `name: ${name}`,
    "description: A copy of the user that follows their learned engineering profile",
    "model: inherit",
    "tools: Read, Grep, Glob, Bash, Edit, Write",
    "---",
    "",
    options.profile.trim(),
    "",
  ].join("\n");
}

export async function writeAgent(options: {
  readonly targetDirectory: string;
  readonly profile: string;
  readonly name?: string;
}): Promise<string> {
  const name = options.name ?? "shadowclone";
  const agentsDirectory = path.join(
    options.targetDirectory,
    ".claude",
    "agents",
  );
  const outputPath = path.join(agentsDirectory, `${name}.md`);

  await ownedWrite({ path: outputPath, content: renderAgent(options) });

  return outputPath;
}
