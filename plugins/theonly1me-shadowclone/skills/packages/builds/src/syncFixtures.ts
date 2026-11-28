import { cp, mkdtemp, realpath } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { defaultConfig, writeConfig, seedSkillsDirectory } from "@shadowclone/core";
import { type BuildInput, readEnvironment } from "@shadowclone/environment";
import { applyBuild } from "./apply";
import { buildFixture, buildInput } from "./testing";
import { previewBuild } from "./plan";

export const skillRoots = [".agents/skills", ".claude/skills", ".gemini/config/skills"];
export const addedLine = "\nRun the command the user runs and read every output line.\n";

export async function installedBuild(input: Partial<BuildInput> = {}) {
  const context = await buildFixture();

  await writeConfig({
    config: { ...defaultConfig, sources: { ...defaultConfig.sources, "skill-library": true } },
    configPath: context.paths.configFile,
  });
  await applyBuild({
    ...context,
    plan: await previewBuild({
      ...context,
      input: buildInput({ choices: { "verify-and-review": true }, ...input }),
    }),
  });

  const state = await readEnvironment(context.paths);

  if (state === null) {
    throw new Error("The build did not record an environment.");
  }

  return { ...context, state, home: path.dirname(context.paths.shadowcloneDirectory) };
}

export async function newerPackage(): Promise<string> {
  const directory = await realpath(await mkdtemp(path.join(os.tmpdir(), "shadowclone-package-")));
  const skill = path.join(directory, "verify-and-review/SKILL.md");

  await cp(await seedSkillsDirectory(), directory, { recursive: true });
  await Bun.write(skill, (await Bun.file(skill).text()) + addedLine);

  return directory;
}

export function copyPath(options: { readonly home: string; readonly root: string }): string {
  return path.join(options.home, options.root, "verify-and-review/SKILL.md");
}
