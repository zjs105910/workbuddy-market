import path from "node:path";
import {
  fingerprint,
  canonicalPath,
  type ProjectPaths,
  seedSkillsDirectory,
} from "@shadowclone/core";
import {
  retireStarterSkill,
  readPortableSkills,
  registerPortableSkill,
  syncPortableSkills,
} from "../skillMaintenance/portable";
import {
  readMaintenanceState,
  writeMaintenanceState,
} from "../skillMaintenance/state";
import type { SeedAgentSkill } from "./schema";

export type SeedSkillInstallResult = {
  readonly installed: number;
  readonly removed: number;
  readonly preserved: number;
};

export async function installSeedSkills(options: {
  readonly paths: ProjectPaths;
  readonly skills: readonly SeedAgentSkill[];
  readonly availableSkills: readonly SeedAgentSkill[];
}): Promise<SeedSkillInstallResult> {
  const packagedDirectory = await seedSkillsDirectory();
  const home = path.dirname(options.paths.shadowcloneDirectory);
  const canonicalRoot = canonicalPath(path.join(home, ".agents/skills"));
  const synchronized = await syncPortableSkills({ paths: options.paths });

  if (synchronized.conflicts > 0) {
    throw new Error("Resolve portable skill conflicts before rerunning wizard");
  }

  const selectedNames = new Set(options.skills.map((skill) => skill.id));
  const removedNames: string[] = [];
  let preserved = 0;

  for (const skill of options.availableSkills) {
    if (selectedNames.has(skill.id)) {
      continue;
    }

    const result = await retireStarterSkill({
      paths: options.paths,
      name: skill.id,
    });

    if (result === "removed") {
      removedNames.push(skill.id);
    } else if (result === "preserved") {
      preserved += 1;
    }
  }

  let installed = 0;
  const managed = await readPortableSkills(options.paths);

  for (const skill of options.skills) {
    const existing = managed.find((entry) => entry.name === skill.id);

    if (existing?.managedBy === "starter") {
      continue;
    }

    if (existing) {
      throw new Error(
        "A selected starter skill is already managed as a user skill",
      );
    }

    await registerPortableSkill({
      paths: options.paths,
      name: skill.id,
      sourceDirectory: path.join(packagedDirectory, skill.id),
      managedBy: "starter",
    });
    installed += 1;
  }

  const state = await readMaintenanceState(options.paths);
  const rootId = fingerprint(canonicalRoot);

  const root = {
    id: rootId,
    directory: canonicalRoot,
    cwd: canonicalPath(home),
    scope: "global" as const,
    owner: "user" as const,
    destination: canonicalRoot,
    enabled: true,
  };

  const removedRelativePaths = new Set(
    removedNames.map((name) => `${name}/SKILL.md`),
  );
  let tracked = state.tracked.filter(
    (entry) =>
      entry.rootId !== rootId || !removedRelativePaths.has(entry.relativePath),
  );

  for (const skill of options.skills) {
    const relativePath = `${skill.id}/SKILL.md`;
    const filePath = path.join(canonicalRoot, relativePath);
    const content = await Bun.file(filePath).text();
    const id = fingerprint(canonicalPath(filePath));

    if (tracked.some((entry) => entry.id === id)) {
      continue;
    }

    tracked = [
      ...tracked,
      {
        id,
        rootId,
        relativePath,
        fingerprint: fingerprint(content),
        kind: "amend" as const,
        automatic: false,
      },
    ];
  }

  await writeMaintenanceState({
    paths: options.paths,
    state: {
      ...state,
      roots: [...state.roots.filter((entry) => entry.id !== rootId), root],
      tracked,
    },
  });

  return { installed, removed: removedNames.length, preserved };
}
