import path from "node:path";
import { fingerprint, readLocalText } from "@shadowclone/core";
import type { FileUpdate } from "@shadowclone/changes";
import type { ProjectPaths } from "@shadowclone/core";
import {
  parseSkillDocument,
  validateSkillReferences,
} from "@shadowclone/skills";
import type { DiscoveredSkill } from "@shadowclone/skills";
import { skillDirectories, type LearningScope } from "./scope";
import { recordFingerprint } from "./records";
import type { EnvironmentState, LearningRecord } from "./types";
import { publishSkillResources } from "./resources";

export async function skillPublication(options: {
  readonly paths: ProjectPaths;
  readonly state: EnvironmentState;
  readonly scope: LearningScope;
  readonly skill: DiscoveredSkill | null;
  readonly name: string;
  readonly text: string;
  readonly records: readonly LearningRecord[];
}): Promise<{
  readonly state: EnvironmentState;
  readonly updates: readonly FileUpdate[];
}> {
  const metadata = parseSkillDocument(options.text).metadata;
  const directories = skillDirectories(options.scope);

  const destinations = [
    ...new Set([
      ...directories.map((directory) =>
        path.join(directory, options.name, "SKILL.md"),
      ),
      ...(options.skill?.root.owner === "user"
        ? [path.join(options.skill.root.directory, options.skill.relativePath)]
        : []),
    ]),
  ];

  const updates: FileUpdate[] = [];
  const artifacts = [...options.state.artifacts];

  if (artifacts.some((artifact) =>
    artifact.buildId && destinations.includes(artifact.filePath),
  )) {
    throw new Error("Changes to an equipped build need review in the build editor");
  }

  if (options.skill?.root.owner === "user") {
    const resources = await publishSkillResources({
      source: path.dirname(
        path.join(options.skill.root.directory, options.skill.relativePath),
      ),
      destinations,
      state: options.state,
      scope: options.scope.key,
      name: options.name,
    });

    updates.push(...resources.updates);

    for (const resource of resources.artifacts) {
      const position = artifacts.findIndex(
        (artifact) => artifact.filePath === resource.filePath,
      );

      if (position >= 0) {
        artifacts[position] = resource;
      } else {
        artifacts.push(resource);
      }
    }
  }

  for (const filePath of destinations) {
    const previous = await readLocalText(filePath);
    const tracked = artifacts.find(
      (artifact) => artifact.filePath === filePath,
    );

    if (
      tracked &&
      previous !== null &&
      fingerprint(previous) !== tracked.fingerprint &&
      previous !== options.skill?.raw
    ) {
      throw new Error(
        "A maintained skill changed; preserve it for reconciliation",
      );
    }

    if (
      !tracked &&
      previous !== null &&
      previous !== options.skill?.raw &&
      previous !== options.text
    ) {
      throw new Error(
        "A different skill already occupies a publication destination",
      );
    }

    if (options.skill?.root.owner === "user") {
      await validateSkillReferences({
        filePath: path.join(
          options.skill.root.directory,
          options.skill.relativePath,
        ),
        text: options.text,
        mentionedFiles: "required",
      });
    } else if (
      /\]\((?!https?:|#)|`(?:scripts|references|assets)\//.test(options.text)
    ) {
      throw new Error(
        "New skill references require existing, validated supporting files",
      );
    }

    updates.push({ filePath, previous, next: options.text });

    const original = tracked ? tracked.original : previous;

    const artifact = {
      filePath,
      original,
      fingerprint: fingerprint(options.text),
      kind: "skill" as const,
      scope: options.scope.key,
      name: options.name,
      description: metadata.description,
      learningKeys: [
        ...new Set([
          ...(tracked?.learningKeys ?? []),
          ...options.records.map(({ rule }) => rule.key),
        ]),
      ],
    };

    const position = artifacts.findIndex(
      (entry) => entry.filePath === filePath,
    );

    if (position >= 0) {
      artifacts[position] = artifact;
    } else {
      artifacts.push(artifact);
    }
  }

  const learnedKeys = new Set(options.records.map(({ rule }) => rule.key));

  return {
    updates,
    state: {
      ...options.state,
      artifacts,
      facts: options.state.facts.filter(
        (fact) =>
          fact.scope !== options.scope.key ||
          !fact.learningKeys.some((key) => learnedKeys.has(key)),
      ),
      dispositions: [
        ...options.state.dispositions.filter(
          (entry) =>
            !learnedKeys.has(entry.key) || entry.scope !== options.scope.key,
        ),
        ...options.records.map((record) => ({
          key: record.rule.key,
          scope: options.scope.key,
          inputFingerprint: recordFingerprint(record),
          status: "published" as const,
          publishedAt: Date.now(),
          reason: "Reconciled into the matching skill",
          destinations,
        })),
      ],
    },
  };
}
