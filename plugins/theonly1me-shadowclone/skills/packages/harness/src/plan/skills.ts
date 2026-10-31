import path from "node:path";
import { readLocalText } from "@shadowclone/core";
import { parseSkillDocument } from "@shadowclone/skills";
import type { PersonalSkill } from "../personalSkills";
import type { AuthoredSkill } from "../render/skills";
import type { ReadFirstSkill } from "../render/agents";
import { planOwnedFile, type PlannedFile } from "./files";

export const repositorySkillRoots = [
  ".agents/skills",
  ".claude/skills",
] as const;

export async function planSkillFiles(options: {
  readonly root: string;
  readonly authored: readonly AuthoredSkill[];
  readonly personal: readonly PersonalSkill[];
  readonly artifacts: Readonly<Record<string, string>>;
}): Promise<readonly PlannedFile[]> {
  const planned: PlannedFile[] = [];

  for (const skillRoot of repositorySkillRoots) {
    for (const skill of options.authored) {
      const relativePath = `${skillRoot}/${skill.name}/SKILL.md`;

      planned.push(
        await planOwnedFile({
          root: options.root,
          relativePath,
          next: skill.text,
          recorded: options.artifacts[relativePath],
          reason: "authored workflow skill",
        }),
      );
    }

    for (const skill of options.personal) {
      for (const [file, text] of Object.entries(skill.files)) {
        const relativePath = `${skillRoot}/${skill.name}/${file}`;

        planned.push(
          await planOwnedFile({
            root: options.root,
            relativePath,
            next: text,
            recorded: options.artifacts[relativePath],
            reason: "copy of your personal skill",
          }),
        );
      }
    }
  }

  return planned;
}

async function repositorySkillDescription(options: {
  readonly root: string;
  readonly name: string;
}): Promise<string | null> {
  for (const skillRoot of repositorySkillRoots) {
    const text = await readLocalText(
      path.join(options.root, skillRoot, options.name, "SKILL.md"),
    );

    if (text !== null) {
      return parseSkillDocument(text).metadata.description;
    }
  }

  return null;
}

export async function carriedSkills(options: {
  readonly root: string;
  readonly names: readonly string[];
  readonly artifacts: Readonly<Record<string, string>>;
}): Promise<{
  readonly skills: readonly ReadFirstSkill[];
  readonly artifacts: Readonly<Record<string, string>>;
}> {
  const skills: ReadFirstSkill[] = [];
  const artifacts: Record<string, string> = {};

  for (const name of options.names) {
    const description = await repositorySkillDescription({
      root: options.root,
      name,
    });

    if (description === null) {
      continue;
    }

    skills.push({ name, description });

    for (const [relativePath, recorded] of Object.entries(options.artifacts)) {
      if (
        repositorySkillRoots.some((skillRoot) =>
          relativePath.startsWith(`${skillRoot}/${name}/`),
        )
      ) {
        artifacts[relativePath] = recorded;
      }
    }
  }

  return { skills, artifacts };
}
