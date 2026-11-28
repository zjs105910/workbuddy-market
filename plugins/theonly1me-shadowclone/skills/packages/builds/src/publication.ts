import path from "node:path";
import { fingerprint, readLocalText, seedSkillsDirectory } from "@shadowclone/core";
import {
  type BuildContext,
  type BuildDefinition,
  buildDirectories,
  type EnvironmentState,
  publishSkillResources,
} from "@shadowclone/environment";
import type { FileUpdate } from "@shadowclone/changes";
import {
  parseSkillDocument,
  validateSkillReferences,
} from "@shadowclone/skills";
import { skillClassification } from "./classification";
import { skillDestinationsWithoutLinks } from "./linkedDestinations";
import type { BuildItem } from "./types";

export async function publishBuildSkill(
  options: BuildContext & {
    readonly state: EnvironmentState;
    readonly build: BuildDefinition;
    readonly item: BuildItem;
    readonly text: string;
    readonly edited: boolean;
    readonly packagedSkillsDirectory?: string;
  },
): Promise<{
  readonly state: EnvironmentState;
  readonly updates: readonly FileUpdate[];
  readonly warnings: readonly string[];
}> {
  const { metadata } = parseSkillDocument(options.text);

  if (metadata.name !== options.item.name) {
    throw new Error("Changing a skill name requires creating a new skill");
  }

  const source = options.item.source;
  const destinations = buildDirectories(options).map((root) =>
    path.join(root, metadata.name, "SKILL.md"),
  );

  if (
    source?.root.owner === "user" &&
    options.build.scope === "global" &&
    source.root.scope === "global"
  ) {
    destinations.push(path.join(source.root.directory, source.relativePath));
  }

  const { targets, warnings } = skillDestinationsWithoutLinks({
    destinations,
    source: source ? path.join(source.root.directory, source.relativePath) : null,
    name: metadata.name,
    homeDirectory: path.dirname(options.paths.shadowcloneDirectory),
  });
  let text = options.text;

  const tracked = options.state.artifacts.filter(
    (artifact) =>
      artifact.buildId === options.build.id &&
      artifact.buildEntryId === options.item.id &&
      artifact.kind === "skill",
  );

  const changed = [];

  for (const artifact of tracked) {
    const current = await readLocalText(artifact.filePath);

    if (current !== null && fingerprint(current) !== artifact.fingerprint) {
      changed.push(current);
    }
  }

  if (new Set(changed).size > 1) {
    throw new Error(
      "Skill copies have conflicting edits; resolve them before applying the build",
    );
  }

  if (changed[0] && !options.edited) {
    text = changed[0];
  }

  if (changed.length && options.edited && changed[0] !== source?.raw) {
    throw new Error(
      "A skill changed outside the editor; reload before editing it",
    );
  }

  if (parseSkillDocument(text).metadata.name !== metadata.name) {
    throw new Error(
      "Changing an installed skill name requires creating a new skill",
    );
  }

  if (
    options.build.scope === "shared" &&
    [
      path.dirname(options.paths.shadowcloneDirectory),
      options.paths.shadowcloneDirectory,
    ].some((root) => text.includes(root))
  ) {
    throw new Error(
      "Shared skills cannot contain this machine's personal paths",
    );
  }

  const updates: FileUpdate[] = [];
  const artifacts = [...options.state.artifacts];

  const resourceDirectory =
    source?.root.owner === "user"
      ? path.dirname(path.join(source.root.directory, source.relativePath))
      : options.item.owner === "packaged"
        ? path.join(options.packagedSkillsDirectory ?? (await seedSkillsDirectory()), metadata.name)
        : null;

  if (resourceDirectory !== null) {
    await validateSkillReferences({
      filePath: path.join(resourceDirectory, "SKILL.md"),
      text,
      mentionedFiles: source?.root.owner === "user" ? "optional" : "required",
    });

    const resources = await publishSkillResources({
      source: resourceDirectory,
      destinations: targets,
      state: options.state,
      scope: options.build.id,
      name: metadata.name,
    });

    updates.push(...resources.updates);

    for (const resource of resources.artifacts) {
      const artifact = {
        ...resource,
        buildId: options.build.id,
        buildEntryId: options.item.id,
      };
      const index = artifacts.findIndex(
        (entry) => entry.filePath === artifact.filePath,
      );

      if (index < 0) {
        artifacts.push(artifact);
      } else {
        artifacts[index] = artifact;
      }
    }
  } else if (/\]\((?!https?:|#)|`(?:scripts|references|assets)\//.test(text)) {
    throw new Error(
      "A new skill cannot reference supporting files that have not been installed",
    );
  }

  for (const filePath of targets) {
    const previous = await readLocalText(filePath);
    const existing = artifacts.find(
      (artifact) => artifact.filePath === filePath,
    );

    if (existing && existing.buildId !== options.build.id) {
      throw new Error(
        "This skill belongs to another scope; create a companion instead",
      );
    }

    if (
      !existing &&
      previous !== null &&
      previous !== source?.raw &&
      previous !== text
    ) {
      throw new Error(
        "An existing skill occupies this destination; select that skill to edit it",
      );
    }

    updates.push({ filePath, previous, next: text });

    const artifact = {
      filePath,
      original: existing ? existing.original : previous,
      fingerprint: fingerprint(text),
      kind: "skill" as const,
      scope: options.build.id,
      name: metadata.name,
      description: parseSkillDocument(text).metadata.description,
      appliesWhen: skillClassification(text).appliesWhen ?? undefined,
      learningKeys: existing?.learningKeys ?? [],
      buildId: options.build.id,
      buildEntryId: options.item.id,
    };

    const index = artifacts.findIndex((entry) => entry.filePath === filePath);

    if (index < 0) {
      artifacts.push(artifact);
    } else {
      artifacts[index] = artifact;
    }
  }

  return { state: { ...options.state, artifacts }, updates, warnings };
}

export { retireBuildSkills } from "./retirement";
