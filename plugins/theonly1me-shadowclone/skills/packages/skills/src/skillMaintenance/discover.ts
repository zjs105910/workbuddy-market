import { existsSync } from "node:fs";
import path from "node:path";
import { fingerprint, readLocalText, canonicalPath } from "@shadowclone/core";
import { resolveRedacted } from "@shadowclone/sessions";
import { parseSkillDocument, validateSkillReferences } from "./document";
import { skillTarget } from "./state";
import type { DiscoveredSkill, SkillRoot } from "./types";

export async function discoverSkills(roots: readonly SkillRoot[]): Promise<{
  readonly skills: readonly DiscoveredSkill[];
  readonly invalid: number;
  readonly duplicates: number;
}> {
  return inspectSkills({ roots, includeCompanions: false });
}

export async function discoverDeliverySkills(
  roots: readonly SkillRoot[],
): Promise<{
  readonly skills: readonly DiscoveredSkill[];
  readonly invalid: number;
  readonly duplicates: number;
}> {
  return inspectSkills({ roots, includeCompanions: true });
}

async function inspectSkills(options: {
  readonly roots: readonly SkillRoot[];
  readonly includeCompanions: boolean;
}): Promise<{
  readonly skills: readonly DiscoveredSkill[];
  readonly invalid: number;
  readonly duplicates: number;
}> {
  const skills: DiscoveredSkill[] = [];
  const visited = new Set<string>();
  let invalid = 0;
  let totalBytes = 0;
  let discovered = 0;

  for (const root of options.roots) {
    if (!existsSync(root.directory)) {
      continue;
    }

    for await (const relativePath of new Bun.Glob("**/SKILL.md").scan({
      cwd: root.directory,
      onlyFiles: true,
      followSymlinks: false,
      dot: false,
    })) {
      if (
        relativePath
          .split(path.sep)
          .some(
            (segment) =>
              segment === "shadowclone-context" ||
              (!options.includeCompanions &&
                segment.startsWith("shadowclone-local-")),
          )
      ) {
        continue;
      }

      if (relativePath.split(path.sep).length > 12) {
        throw new Error(
          "Skill library exceeds discovery limits; configure smaller roots",
        );
      }

      const filePath = skillTarget({ directory: root.directory, relativePath });
      const identity = canonicalPath(filePath);

      if (visited.has(identity)) {
        continue;
      }

      visited.add(identity);
      discovered += 1;
      if (discovered > 2_000) {
        throw new Error("Skill library exceeds discovery limits; configure smaller roots");
      }

      const size = Bun.file(filePath).size;

      totalBytes += size;

      if (totalBytes > 8_000_000) {
        throw new Error("Skill library exceeds the total byte limit");
      }

      let materialized: {
        readonly raw: string;
        readonly redacted: string;
      } | null = null;

      try {
        if (size > 48_000 && !options.includeCompanions) {
          throw new Error("Skill exceeds the supported size");
        }

        const raw = await readLocalText(filePath);

        if (raw === null) {
          continue;
        }

        const redacted = await resolveRedacted({
          roots: [root.directory],
          ref: {
            type: "file",
            sourcePath: filePath,
            byteOffset: 0,
            byteLength: size,
          },
        });

        materialized = { raw, redacted };

        if (size > 48_000) {
          throw new Error("Skill exceeds the supported size");
        }

        const document = parseSkillDocument(redacted);

        if (document.metadata.name !== path.basename(path.dirname(filePath))) {
          throw new Error("Skill name does not match its directory");
        }

        await validateSkillReferences({
          filePath,
          text: document.body,
          mentionedFiles: "optional",
        });
        skills.push({
          id: fingerprint(identity),
          root,
          relativePath,
          raw,
          redacted,
          fingerprint: fingerprint(raw),
          name: document.metadata.name,
          description: document.metadata.description,
          body: document.body,
        });
      } catch {
        invalid += 1;

        if (options.includeCompanions && materialized) {
          skills.push({
            id: fingerprint(identity),
            root,
            relativePath,
            ...materialized,
            fingerprint: fingerprint(materialized.raw),
            name: path.basename(path.dirname(filePath)),
            description:
              "Existing skill needs metadata or reference validation before automatic editing.",
            body: materialized.redacted,
            valid: false,
          });
        }
      }
    }
  }

  const groups = [
    ...Map.groupBy(
      skills,
      (skill) => `${skill.root.scope}:${skill.root.cwd}:${skill.name}`,
    ).values(),
  ];

  const duplicates = groups.reduce(
    (count, group) =>
      new Set(group.map((skill) => skill.fingerprint)).size > 1
        ? count + group.length - 1
        : count,
    0,
  );

  const distinct = groups.flatMap((group) => {
    if (new Set(group.map((skill) => skill.fingerprint)).size > 1) {
      return group;
    }

    const canonical = group.find((skill) =>
      skill.root.directory.includes(`${path.sep}.agents${path.sep}skills`),
    );

    return [canonical ?? group[0]].filter(
      (skill): skill is DiscoveredSkill => skill !== undefined,
    );
  });

  return {
    skills: distinct.sort((left, right) => left.id.localeCompare(right.id)),
    invalid,
    duplicates,
  };
}
