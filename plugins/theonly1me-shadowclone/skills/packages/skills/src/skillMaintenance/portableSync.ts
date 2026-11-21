import { rm } from "node:fs/promises";
import { canonicalPath, type ProjectPaths } from "@shadowclone/core";
import {
  readPortableSkills,
  replaceSkillDirectory,
  skillTreeFingerprint,
  writePortableSkills,
  type PortableSkill,
} from "./portableFiles";
import {
  portableSkillDirectories,
  redundantSkillDirectories,
} from "./portableLocations";

export async function syncPortableSkills(options: {
  readonly paths: ProjectPaths;
}): Promise<{ readonly synced: number; readonly conflicts: number }> {
  const skills = await readPortableSkills(options.paths);
  const updated: PortableSkill[] = [];
  let synced = 0;
  let conflicts = 0;

  for (const skill of skills) {
    const expected = portableSkillDirectories({
      paths: options.paths,
      name: skill.name,
    });
    const [canonical, ...replicas] = expected;

    if (canonical === undefined) {
      throw new Error("Portable skill destination is unavailable");
    }

    const redundant = redundantSkillDirectories({
      paths: options.paths,
      name: skill.name,
    });

    const directories = [
      ...new Set(
        [skill.sourceDirectory, ...skill.replicaDirectories, ...expected].map(
          canonicalPath,
        ),
      ),
    ].filter((directory) => !redundant.includes(directory));

    const states = await Promise.all(
      directories.map(async (directory) => ({
        directory,
        fingerprint: await skillTreeFingerprint(directory),
      })),
    );

    const redundantStates = await Promise.all(
      redundant.map(async (directory) => ({
        directory,
        fingerprint: await skillTreeFingerprint(directory),
      })),
    );

    const changed = states.filter(
      (state) =>
        state.fingerprint !== null &&
        state.fingerprint !== skill.baselineFingerprint,
    );

    if (new Set(changed.map((state) => state.fingerprint)).size > 1) {
      conflicts += 1;
      updated.push(skill);

      continue;
    }

    const authority = changed[0] ?? states.find((state) => state.fingerprint);

    if (!authority?.fingerprint) {
      conflicts += 1;
      updated.push(skill);

      continue;
    }

    if (
      redundantStates.some(
        (state) =>
          state.fingerprint !== null &&
          state.fingerprint !== skill.baselineFingerprint &&
          state.fingerprint !== authority.fingerprint,
      )
    ) {
      conflicts += 1;
      updated.push(skill);

      continue;
    }

    for (const state of states.filter((entry) =>
      expected.includes(entry.directory),
    )) {
      if (state.fingerprint !== authority.fingerprint) {
        await replaceSkillDirectory({
          source: authority.directory,
          destination: state.directory,
        });
        synced += 1;
      }
    }

    for (const state of redundantStates) {
      if (
        state.fingerprint === authority.fingerprint ||
        state.fingerprint === skill.baselineFingerprint
      ) {
        await rm(state.directory, { recursive: true, force: true });
        synced += 1;
      }
    }

    updated.push({
      ...skill,
      sourceDirectory: canonical,
      replicaDirectories: replicas,
      baselineFingerprint: authority.fingerprint,
    });
  }

  await writePortableSkills({ paths: options.paths, skills: updated });

  return { synced, conflicts };
}
