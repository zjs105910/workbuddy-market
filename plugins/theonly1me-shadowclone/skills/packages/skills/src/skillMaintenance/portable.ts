import { rm } from "node:fs/promises";
import { canonicalPath, type ProjectPaths } from "@shadowclone/core";
import {
  portableSkillNameSchema,
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

export async function registerPortableSkill(options: {
  readonly paths: ProjectPaths;
  readonly name: string;
  readonly sourceDirectory: string;
  readonly managedBy: PortableSkill["managedBy"];
}): Promise<PortableSkill> {
  portableSkillNameSchema.parse(options.name);

  const sourceDirectory = canonicalPath(options.sourceDirectory);
  const sourceFingerprint = await skillTreeFingerprint(sourceDirectory);

  if (!sourceFingerprint) {
    throw new Error("Portable skill source is missing");
  }

  const [canonical, ...replicas] = portableSkillDirectories({
    paths: options.paths,
    name: options.name,
  });

  if (!canonical) {
    throw new Error("Portable skill destination is unavailable");
  }

  const redundant = redundantSkillDirectories(options);
  const destinations = [canonical, ...replicas, ...redundant].filter(
    (directory) => directory !== sourceDirectory,
  );

  for (const destination of destinations) {
    const current = await skillTreeFingerprint(destination);

    if (current !== null && current !== sourceFingerprint) {
      throw new Error(
        "A different skill already exists at a portable destination",
      );
    }
  }

  if (sourceDirectory !== canonical) {
    await replaceSkillDirectory({
      source: sourceDirectory,
      destination: canonical,
    });
  }

  for (const destination of replicas) {
    if (
      destination !== sourceDirectory &&
      (await skillTreeFingerprint(destination)) === null
    ) {
      await replaceSkillDirectory({ source: canonical, destination });
    }
  }

  for (const directory of redundant) {
    if ((await skillTreeFingerprint(directory)) === sourceFingerprint) {
      await rm(directory, { recursive: true, force: true });
    }
  }

  const skills = await readPortableSkills(options.paths);

  const entry: PortableSkill = {
    name: options.name,
    sourceDirectory: canonical,
    replicaDirectories: replicas,
    baselineFingerprint: sourceFingerprint,
    installationFingerprint: sourceFingerprint,
    managedBy: options.managedBy,
  };

  await writePortableSkills({
    paths: options.paths,
    skills: [...skills.filter((skill) => skill.name !== options.name), entry],
  });

  return entry;
}

export async function retireStarterSkill(options: {
  readonly paths: ProjectPaths;
  readonly name: string;
}): Promise<"removed" | "preserved" | "unmanaged"> {
  const skills = await readPortableSkills(options.paths);
  const skill = skills.find((entry) => entry.name === options.name);

  if (skill?.managedBy !== "starter") {
    return "unmanaged";
  }

  if (skill.baselineFingerprint !== skill.installationFingerprint) {
    await writePortableSkills({
      paths: options.paths,
      skills: skills.map((entry) =>
        entry.name === skill.name ? { ...entry, managedBy: "adopted" } : entry,
      ),
    });

    return "preserved";
  }

  const expected = new Set(
    portableSkillDirectories({
      paths: options.paths,
      name: options.name,
    }),
  );

  const allowed = new Set([...expected, ...redundantSkillDirectories(options)]);
  const recorded = [skill.sourceDirectory, ...skill.replicaDirectories];
  const resolvedRecorded = recorded.map(canonicalPath);

  if (
    resolvedRecorded.some((directory) => !allowed.has(directory)) ||
    [...expected].some((directory) => !resolvedRecorded.includes(directory))
  ) {
    throw new Error("Portable skill state contains an unsafe destination");
  }

  for (const directory of recorded) {
    await rm(directory, { recursive: true, force: true });
  }

  await writePortableSkills({
    paths: options.paths,
    skills: skills.filter((entry) => entry.name !== skill.name),
  });

  return "removed";
}

export { readPortableSkills, skillTreeFingerprint } from "./portableFiles";

export { syncPortableSkills } from "./portableSync";
