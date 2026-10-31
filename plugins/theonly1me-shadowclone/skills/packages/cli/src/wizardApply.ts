import { previewBuild, applyBuild } from "@shadowclone/builds";
import {
  initializeSkillEnvironment,
  readEnvironment,
  refreshIntegrations,
  writeSeedGuidanceSelection,
} from "@shadowclone/environment";
import { installSeedSkills, type SeedGuidance, type SeedLibrary } from "@shadowclone/skills";
import type { ProjectPaths } from "@shadowclone/core";

export async function applyWizardSelection(options: {
  readonly paths: ProjectPaths;
  readonly library: SeedLibrary;
  readonly selected: readonly SeedGuidance[];
}): Promise<void> {
  await initializeSkillEnvironment({ paths: options.paths, automatic: false });

  if ((await readEnvironment(options.paths))?.phase === "active") {
    const selected = new Set(options.selected.map((entry) => entry.id));
    const input = {
      scope: "global",
      choices: Object.fromEntries(
        options.library.guidance.map((entry) => [
          entry.id,
          selected.has(entry.id),
        ]),
      ),
      edits: {},
      custom: [],
    };
    const context = { paths: options.paths, cwd: process.cwd() };

    await applyBuild({
      ...context,
      plan: await previewBuild({ ...context, input }),
    });

    return;
  }

  await installSeedSkills({
    paths: options.paths,
    skills: options.selected.filter((entry) => entry.kind === "skill"),
    availableSkills: options.library.skills,
  });
  await writeSeedGuidanceSelection({
    paths: options.paths,
    library: options.library,
    selectedGuidance: options.selected.filter(
      (entry) => entry.kind === "preference",
    ),
  });
  await refreshIntegrations({
    paths: options.paths,
    configPath: options.paths.configFile,
  });
}
