import path from "node:path";
import type { FileUpdate } from "@shadowclone/changes";
import { readLocalText } from "@shadowclone/core";
import type { ProjectPaths } from "@shadowclone/core";
import { referenceRelativePath, renderReference } from "../../references";
import { parseProfileBlocks } from "../parse";
import { assertNotCoveredRouting } from "../skillRouting";
import { profileRulePath, renderProfileRule } from "../render";
import { readGeneratedProfileState, readProfileRejections } from "../state";
import {
  renderGeneratedProfileState,
  renderProfileRejections,
} from "../stateRender";
import {
  indexProfileCurationRules,
  profileRuleFromDecision,
  readProfileCurationFiles,
  referenceFromDecision,
  rejectionFromDecision,
} from "./curationData";
import type { ProfileCurationDecisions } from "./decisions";

export type ProfileCurationPlan = {
  readonly moves: number;
  readonly rejections: number;
  readonly references: number;
  readonly updates: readonly FileUpdate[];
};

export async function createProfileCurationPlan(options: {
  readonly paths: ProjectPaths;
  readonly decisions: ProfileCurationDecisions;
}): Promise<ProfileCurationPlan> {
  const files = await readProfileCurationFiles(options.paths);
  const rules = indexProfileCurationRules(files);
  const removed = new Set<string>();
  const additions = new Map<string, string[]>();
  const manifest = new Map(
    (await readGeneratedProfileState(options.paths.profileManifestFile)).map(
      (entry) => [entry.key, entry],
    ),
  );
  const rejected = new Map(
    (await readProfileRejections(options.paths.rejectedProfileFile)).map(
      (entry) => [entry.key, entry],
    ),
  );
  const referenceUpdates = new Map<string, FileUpdate>();

  for (const decision of options.decisions.rules) {
    const located = rules.get(decision.key);

    if (located === undefined) {
      throw new Error(`Profile rule was not found: ${decision.key}`);
    }

    if (decision.action !== "move") {
      assertNotCoveredRouting({
        body: located.rule.body,
        reason: decision.reason,
      });
    }

    removed.add(decision.key);

    if (decision.action === "move") {
      const moved = profileRuleFromDecision(located.rule, decision);
      const relativePath = profileRulePath(moved);

      additions.set(relativePath, [
        ...(additions.get(relativePath) ?? []),
        renderProfileRule(moved),
      ]);

      const state = manifest.get(decision.key);

      if (state !== undefined) {
        manifest.set(decision.key, { ...state, relativePath });
      }

      continue;
    }

    manifest.delete(decision.key);

    const nextRejection = rejectionFromDecision({ decision, ...located });
    const previousRejection = rejected.get(decision.key);

    if (
      previousRejection !== undefined &&
      JSON.stringify(previousRejection) !== JSON.stringify(nextRejection)
    ) {
      throw new Error(
        `Profile rejection conflicts with existing state: ${decision.key}`,
      );
    }

    rejected.set(decision.key, nextRejection);

    if (decision.action === "reference") {
      const record = referenceFromDecision({
        decision,
        body: located.rule.body,
      });
      const relativePath = referenceRelativePath(record);
      const filePath = path.join(options.paths.profileDirectory, relativePath);
      const previous = await readLocalText(filePath);
      const next = renderReference(record);

      if (previous !== null && previous !== next) {
        throw new Error(
          `Profile reference conflicts with an existing file: ${relativePath}`,
        );
      }

      referenceUpdates.set(relativePath, { filePath, previous, next });
    }
  }

  for (const relativePath of additions.keys()) {
    if (files.has(relativePath)) {
      continue;
    }

    const previous = await readLocalText(
      path.join(options.paths.profileDirectory, relativePath),
    );

    files.set(relativePath, {
      previous,
      blocks: previous === null ? [] : parseProfileBlocks(previous),
    });
  }

  const updates: FileUpdate[] = [];

  for (const [relativePath, file] of files) {
    const blocks = file.blocks
      .filter((block) => block.key === null || !removed.has(block.key))
      .map((block) => block.content);

    blocks.push(...(additions.get(relativePath) ?? []));

    const next = blocks.length === 0 ? null : `${blocks.join("\n\n")}\n`;

    updates.push({
      filePath: path.join(options.paths.profileDirectory, relativePath),
      previous: file.previous,
      next,
    });
  }

  const previousManifest = await readLocalText(
    options.paths.profileManifestFile,
  );
  const previousRejections = await readLocalText(
    options.paths.rejectedProfileFile,
  );

  updates.push({
    filePath: options.paths.profileManifestFile,
    previous: previousManifest,
    next: renderGeneratedProfileState([...manifest.values()]),
  });
  updates.push({
    filePath: options.paths.rejectedProfileFile,
    previous: previousRejections,
    next: renderProfileRejections([...rejected.values()]),
  });
  updates.push(...referenceUpdates.values());

  return {
    moves: options.decisions.rules.filter(
      (decision) => decision.action === "move",
    ).length,
    rejections: options.decisions.rules.filter(
      (decision) => decision.action === "reject",
    ).length,
    references: options.decisions.rules.filter(
      (decision) => decision.action === "reference",
    ).length,
    updates,
  };
}
