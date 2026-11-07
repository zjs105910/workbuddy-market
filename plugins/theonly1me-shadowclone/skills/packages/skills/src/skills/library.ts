import { readdir } from "node:fs/promises";
import path from "node:path";
import { resolveSeedDirectories } from "@shadowclone/core";
import {
  parseSeedAgentSkillDocument,
  parseSeedPreferenceDocument,
} from "./parse";
import type {
  SeedAgentSkill,
  SeedGuidance,
  SeedGuidanceAxis,
  SeedLibrary,
  SeedPreference,
} from "./schema";

async function loadPreferences(
  directory: string,
): Promise<readonly SeedPreference[]> {
  const filenames = (await readdir(directory))
    .filter((filename) => filename.endsWith(".md"))
    .sort();

  return Promise.all(
    filenames.map(async (filename) =>
      parseSeedPreferenceDocument({
        filename,
        text: await Bun.file(path.join(directory, filename)).text(),
      }),
    ),
  );
}

async function loadAgentSkills(
  directory: string,
): Promise<readonly SeedAgentSkill[]> {
  const entries = await readdir(directory, { withFileTypes: true });
  const directoryNames = entries
    .filter((entry) => entry.isDirectory())
    .map((entry) => entry.name)
    .sort();

  return Promise.all(
    directoryNames.map(async (directoryName) =>
      parseSeedAgentSkillDocument({
        directoryName,
        text: await Bun.file(
          path.join(directory, directoryName, "SKILL.md"),
        ).text(),
      }),
    ),
  );
}

function buildSeedLibrary(options: {
  readonly preferences: readonly SeedPreference[];
  readonly skills: readonly SeedAgentSkill[];
}): SeedLibrary {
  const guidance: readonly SeedGuidance[] = [
    ...options.preferences,
    ...options.skills,
  ];
  const ids = new Set<string>();
  const grouped = new Map<string, SeedGuidance[]>();

  for (const entry of guidance) {
    if (ids.has(entry.id)) {
      throw new Error(`Duplicate seed guidance id: ${entry.id}`);
    }

    ids.add(entry.id);

    if (entry.axis !== null) {
      const axisGuidance = grouped.get(entry.axis) ?? [];

      axisGuidance.push(entry);
      grouped.set(entry.axis, axisGuidance);
    }
  }

  const axes: SeedGuidanceAxis[] = [...grouped.entries()]
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([id, axisGuidance]) => {
      if (axisGuidance.length < 2) {
        throw new Error(`Seed guidance axis needs at least two choices: ${id}`);
      }

      if (new Set(axisGuidance.map((entry) => entry.kind)).size !== 1) {
        throw new Error(
          `Seed guidance axis mixes preferences and skills: ${id}`,
        );
      }

      return { id, guidance: axisGuidance };
    });

  return {
    guidance,
    preferences: options.preferences,
    skills: options.skills,
    axes,
    independentSkills: options.skills.filter((skill) => skill.axis === null),
  };
}

export async function loadSeedLibrary(
  options: {
    readonly preferencesDirectory?: string;
    readonly skillsDirectory?: string;
  } = {},
): Promise<SeedLibrary> {
  const defaults =
    options.preferencesDirectory && options.skillsDirectory
      ? null
      : await resolveSeedDirectories();
  const preferencesDirectory =
    options.preferencesDirectory ?? defaults?.preferences;
  const skillsDirectory = options.skillsDirectory ?? defaults?.skills;

  if (!preferencesDirectory || !skillsDirectory) {
    throw new Error("Both seed guidance directories are required");
  }

  const [preferences, skills] = await Promise.all([
    loadPreferences(preferencesDirectory),
    loadAgentSkills(skillsDirectory),
  ]);

  return buildSeedLibrary({ preferences, skills });
}
