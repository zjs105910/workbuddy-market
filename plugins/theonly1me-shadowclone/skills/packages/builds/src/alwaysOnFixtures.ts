import { rm } from "node:fs/promises";
import path from "node:path";
import { z } from "zod";
import {
  buildScopeSchema,
  customSkillSchema,
  environmentFile,
  type EnvironmentState,
  renderEnvironment,
} from "@shadowclone/environment";
import type { ProjectPaths } from "@shadowclone/core";
import { skillRoots } from "./syncFixtures";

export const skillName = "write-plain-english";

const releasedArtifactSchema = z.strictObject({
  filePath: z.string(),
  fingerprint: z.string(),
  original: z.string().nullable(),
  kind: z.enum(["skill", "instructions", "resource"]),
  encoding: z.enum(["utf8", "base64"]).optional(),
  scope: z.string(),
  name: z.string(),
  description: z.string(),
  appliesWhen: z.string().optional(),
  learningKeys: z.array(z.string()),
  buildId: z.string().optional(),
  buildEntryId: z.string().optional(),
});

const releasedBuildSchema = z.strictObject({
  scope: buildScopeSchema,
  choices: z.record(z.string(), z.boolean()),
  edits: z.record(z.string(), z.string()),
  custom: z.array(customSkillSchema),
  directory: z.string(),
  id: z.string(),
});

const releasedStateSchema = z.object({
  artifacts: z.array(releasedArtifactSchema),
  builds: z.array(releasedBuildSchema),
});

export async function readReleasedShapes(
  paths: ProjectPaths,
): Promise<z.infer<typeof releasedStateSchema>> {
  return releasedStateSchema.parse(JSON.parse(await Bun.file(environmentFile(paths)).text()));
}

export async function writeOlderRelease(options: {
  readonly paths: ProjectPaths;
  readonly state: EnvironmentState;
  readonly directories: readonly string[];
  readonly storedChoice?: false;
}): Promise<EnvironmentState> {
  for (const directory of options.directories) {
    for (const root of skillRoots) {
      await rm(path.join(directory, root, skillName), { recursive: true, force: true });
    }
  }

  const older = {
    ...options.state,
    artifacts: options.state.artifacts.filter((artifact) => artifact.buildEntryId !== skillName),
    builds: options.state.builds.map(({ choices, ...build }) => ({
      ...build,
      choices: {
        ...Object.fromEntries(Object.entries(choices).filter(([id]) => id !== skillName)),
        ...(options.storedChoice === false ? { [skillName]: false } : {}),
      },
    })),
  };

  await Bun.write(environmentFile(options.paths), renderEnvironment(older));

  return older;
}
