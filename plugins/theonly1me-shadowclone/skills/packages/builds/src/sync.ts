import path from "node:path";
import type { FileUpdate } from "@shadowclone/changes";
import {
  type EnvironmentArtifact,
  type EnvironmentState,
  publishSkillResources,
} from "@shadowclone/environment";
import { fingerprint, readLocalFile, seedSkillsDirectory } from "@shadowclone/core";
import { parseSkillDocument, isBundledVersion, loadSeedLibrary } from "@shadowclone/skills";
import { skillClassification } from "./classification";

export type BuildSkillSyncReport = {
  readonly updated: readonly { readonly name: string; readonly copies: number }[];
  readonly kept: readonly { readonly name: string; readonly filePath: string }[];
};

type BuildSkillSync = BuildSkillSyncReport & {
  readonly state: EnvironmentState;
  readonly updates: readonly FileUpdate[];
};

type InstalledFile = {
  readonly artifact: EnvironmentArtifact;
  readonly bundledFile: string | null;
  readonly text: string | null;
};

export async function installedFiles(options: {
  readonly copies: readonly EnvironmentArtifact[];
  readonly resources: readonly EnvironmentArtifact[];
}): Promise<readonly InstalledFile[]> {
  const directories = options.copies.map((copy) => path.dirname(copy.filePath));

  return Promise.all(
    [...options.copies, ...options.resources].map(async (artifact) => {
      const directory = directories.find((candidate) =>
        artifact.filePath.startsWith(`${candidate}${path.sep}`),
      );

      return {
        artifact,
        bundledFile:
          artifact.kind === "skill"
            ? "SKILL.md"
            : directory === undefined
              ? null
              : path.relative(directory, artifact.filePath).split(path.sep).join("/"),
        text: await readLocalFile({
          filePath: artifact.filePath,
          encoding: artifact.kind === "resource" ? "base64" : "utf8",
        }),
      };
    }),
  );
}

export function changedOutsideBundle(options: {
  readonly skill: string;
  readonly file: InstalledFile;
}): boolean {
  const { bundledFile, text } = options.file;

  return (
    text !== null &&
    (bundledFile === null ||
      !isBundledVersion({
        skill: options.skill,
        file: bundledFile,
        fingerprint: fingerprint(text),
      }))
  );
}

export async function syncBuildSkills(options: {
  readonly state: EnvironmentState;
  readonly packagedSkillsDirectory?: string;
}): Promise<BuildSkillSync> {
  const packagedDirectory = options.packagedSkillsDirectory ?? (await seedSkillsDirectory());
  const packagedIds = new Set((await loadSeedLibrary()).skills.map((skill) => skill.id));
  const updates: FileUpdate[] = [];
  const updated: { name: string; copies: number }[] = [];
  const kept: { name: string; filePath: string }[] = [];
  let artifacts = [...options.state.artifacts];

  for (const build of options.state.builds) {
    const groups = Map.groupBy(
      options.state.artifacts.filter(
        (artifact) =>
          artifact.buildId === build.id &&
          artifact.kind === "skill" &&
          packagedIds.has(artifact.buildEntryId ?? "") &&
          build.edits[artifact.buildEntryId ?? ""] === undefined,
      ),
      (artifact) => artifact.buildEntryId ?? "",
    );

    for (const [entryId, copies] of groups) {
      const files = await installedFiles({
        copies,
        resources: options.state.artifacts.filter(
          (artifact) =>
            artifact.buildId === build.id &&
            artifact.kind === "resource" &&
            artifact.buildEntryId === entryId,
        ),
      });
      const changed = files.filter((file) => changedOutsideBundle({ skill: entryId, file }));

      if (changed.length > 0) {
        kept.push(
          ...changed.map(({ artifact }) => ({ name: artifact.name, filePath: artifact.filePath })),
        );

        continue;
      }

      const packagedText = await Bun.file(path.join(packagedDirectory, entryId, "SKILL.md")).text();
      const resources = await publishSkillResources({
        source: path.join(packagedDirectory, entryId),
        destinations: copies.map((artifact) => artifact.filePath),
        state: { ...options.state, artifacts },
        scope: build.id,
        name: entryId,
      });
      const entryUpdates = [
        ...files
          .filter((file) => file.artifact.kind === "skill" && file.text !== packagedText)
          .map((file) => ({
            filePath: file.artifact.filePath,
            previous: file.text,
            next: packagedText,
          })),
        ...resources.updates.filter((update) => update.previous !== update.next),
      ];
      const description = parseSkillDocument(packagedText).metadata.description;
      const appliesWhen = skillClassification(packagedText).appliesWhen ?? undefined;

      artifacts = artifacts.map((artifact) =>
        copies.includes(artifact)
          ? { ...artifact, fingerprint: fingerprint(packagedText), description, appliesWhen }
          : artifact,
      );

      for (const resource of resources.artifacts) {
        const tracked = { ...resource, buildId: build.id, buildEntryId: entryId };
        const index = artifacts.findIndex((artifact) => artifact.filePath === resource.filePath);

        artifacts = index < 0 ? [...artifacts, tracked] : artifacts.with(index, tracked);
      }

      if (entryUpdates.length > 0) {
        updates.push(...entryUpdates);
        updated.push({
          name: entryId,
          copies: copies.filter((copy) =>
            entryUpdates.some(
              (update) =>
                update.filePath === copy.filePath ||
                update.filePath.startsWith(`${path.dirname(copy.filePath)}${path.sep}`),
            ),
          ).length,
        });
      }
    }
  }

  return { state: { ...options.state, artifacts }, updates, updated, kept };
}

export function renderBuildSkillSync(report: BuildSkillSyncReport): readonly string[] {
  return [
    ...report.updated.map(
      (entry) =>
        `Updated ${entry.name} to the bundled version (${entry.copies} cop${entry.copies === 1 ? "y" : "ies"}).`,
    ),
    ...report.kept.map(
      (entry) =>
        `Kept your edited copy of ${entry.name} at ${entry.filePath}. Review it in shadowclone wizard.`,
    ),
  ];
}
