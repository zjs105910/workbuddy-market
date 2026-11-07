import { manifestPath, sameSource } from "./manifestIdentity";
import path from "node:path";
import type { FileUpdate } from "@shadowclone/changes";
import { readLocalText } from "@shadowclone/core";
import type { ProjectPaths } from "@shadowclone/core";
import type { ProfileRejection } from "../../profile";
import { assertNotCoveredRouting } from "../../profile/skillRouting";
import type { RepositoryIdentity } from "@shadowclone/sessions";
import { manifestEntry, referenceFromMemory, ruleFromMemory } from "./convert";
import {
  parseClaudeMemoryManifest,
  renderClaudeMemoryManifest,
} from "./manifest";
import { appendProfileRules, mergeRejections } from "./profileUpdates";
import { claudeMemoryDirectory, scanClaudeMemory } from "./scan";
import type { ClaudeFeedbackDecision, ClaudeMemoryManifest } from "./types";

export type ClaudeMemoryMigrationPlan = {
  readonly manifest: ClaudeMemoryManifest;
  readonly manifestPath: string;
  readonly reviewRequired: readonly string[];
  readonly updates: readonly FileUpdate[];
  readonly alreadyApplied: boolean;
};

export async function createClaudeMemoryMigrationPlan(options: {
  readonly paths: ProjectPaths;
  readonly repositoryRoot: string;
  readonly repository: RepositoryIdentity;
  readonly decisions?: ReadonlyMap<string, ClaudeFeedbackDecision>;
  readonly excludedReferences?: ReadonlySet<string>;
  readonly now?: number;
}): Promise<ClaudeMemoryMigrationPlan> {
  const now = options.now ?? Date.now();
  const files = await scanClaudeMemory(options);
  const target = manifestPath({
    paths: options.paths,
    repositoryId: options.repository.id,
  });
  const previousManifest = await readLocalText(target);

  if (previousManifest !== null) {
    const stored = parseClaudeMemoryManifest(previousManifest);

    if (!sameSource({ stored, repositoryId: options.repository.id, files })) {
      throw new Error("Claude memory changed after migration");
    }

    return {
      manifest: stored,
      manifestPath: target,
      reviewRequired: [],
      updates: [],
      alreadyApplied: true,
    };
  }

  const updates: FileUpdate[] = [];
  const rules: ReturnType<typeof ruleFromMemory>[] = [];
  const rejections: ProfileRejection[] = [];
  const reviewRequired: string[] = [];
  const manifestFiles = [];

  for (const file of files) {
    if (file.kind === "reference" || file.kind === "project") {
      if (
        file.kind === "reference" &&
        options.excludedReferences?.has(file.filename)
      ) {
        manifestFiles.push(
          manifestEntry({ file, disposition: "archive-only" }),
        );

        continue;
      }

      const reference = referenceFromMemory({
        file,
        repository: options.repository,
        now,
      });
      const filePath = path.join(
        options.paths.profileDirectory,
        reference.relativePath,
      );
      const previous = await readLocalText(filePath);

      if (previous !== null && previous !== reference.content) {
        throw new Error(
          "Claude memory reference conflicts with an existing reference",
        );
      }

      updates.push({ filePath, previous, next: reference.content });
      manifestFiles.push(
        manifestEntry({
          file,
          disposition:
            file.kind === "project" ? "recall-reference" : "reference",
          destination: reference.relativePath,
        }),
      );

      continue;
    }

    if (file.kind === "feedback" || file.kind === "user") {
      const decision = options.decisions?.get(file.filename);

      if (decision === undefined) {
        reviewRequired.push(file.filename);
        manifestFiles.push(
          manifestEntry({ file, disposition: "review-required" }),
        );
      } else if (decision.disposition === "rule") {
        const rule = ruleFromMemory({
          file,
          decision,
          repository: options.repository,
        });

        rules.push(rule);
        manifestFiles.push(
          manifestEntry({
            file,
            disposition: "rule",
            destination: rule.relativePath,
          }),
        );
      } else {
        assertNotCoveredRouting({ body: file.body, reason: decision.reason });

        const relativePath = path.join(
          "org",
          options.repository.origin.directoryName,
          "projects",
          `${options.repository.profileFileName ?? "repository"}.md`,
        );

        rejections.push({
          relativePath,
          key: `claude-memory:${file.filename.slice(0, -3)}`,
          title: file.description || file.name,
          body: file.body,
          source: "user",
          importReference: null,
          reason: decision.reason,
        });
        manifestFiles.push(
          manifestEntry({
            file,
            disposition: "covered",
            reason: decision.reason,
          }),
        );
      }

      continue;
    }

    manifestFiles.push(manifestEntry({ file, disposition: "index-rebuilt" }));
  }

  updates.push(...(await appendProfileRules({ paths: options.paths, rules })));

  const rejectionUpdate = await mergeRejections({
    paths: options.paths,
    rejections,
  });

  if (rejectionUpdate !== null) {
    updates.push(rejectionUpdate);
  }

  const manifest: ClaudeMemoryManifest = {
    schema: 1,
    repositoryId: options.repository.id,
    sourceDirectory: claudeMemoryDirectory(options),
    createdAt: new Date(now).toISOString(),
    files: manifestFiles,
  };

  updates.push({
    filePath: target,
    previous: null,
    next: renderClaudeMemoryManifest(manifest),
  });

  return {
    manifest,
    manifestPath: target,
    reviewRequired,
    updates,
    alreadyApplied: false,
  };
}
