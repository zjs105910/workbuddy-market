import { maximumProfileBytes } from "@shadowclone/core";
import path from "node:path";
import type { ProjectPaths } from "@shadowclone/core";
import { materializeSnapshot } from "@shadowclone/redact";
import { splitProfileBlocks } from "./blocks";
import { locatedRule } from "./located";
import { parseProfileBlocks } from "./parse";
import type { ProfileRejection } from "./state";
import { readMaterializedProfileRejections } from "./rejectionSnapshot";
import type { ProfileRule } from "./types";
import { profileBlockMetadata, profileVisibleParts } from "./visible";

export type ProfileSnapshotRule = {
  readonly rule: ProfileRule;
  readonly promptTitle: string;
  readonly promptBody: string;
  readonly promptAppliesWhen: readonly string[];
  readonly promptProposal: ProfileRule["proposal"];
};

export type ProfileSnapshotRejection = {
  readonly rejection: ProfileRejection;
  readonly promptTitle: string | null;
  readonly promptBody: string | null;
};

export type ProfileSnapshot = {
  readonly rules: readonly ProfileSnapshotRule[];
  readonly rejections: readonly ProfileSnapshotRejection[];
};

async function profileFiles(
  profileDirectory: string,
): Promise<readonly string[]> {
  try {
    return (
      await Array.fromAsync(
        new Bun.Glob("{global,org}/**/*.md").scan({
          cwd: profileDirectory,
          onlyFiles: true,
        }),
      )
    ).sort();
  } catch {
    return [];
  }
}

async function readRules(options: {
  readonly profileDirectory: string;
  readonly relativePath: string;
}): Promise<readonly ProfileSnapshotRule[]> {
  const filePath = path.join(options.profileDirectory, options.relativePath);

  const snapshot = await materializeSnapshot({
    filePath,
    roots: [options.profileDirectory],
    maximumBytes: maximumProfileBytes,
    parse: parseProfileBlocks,
  });

  if (snapshot === null) {
    return [];
  }

  const rawBlocks = snapshot.parsed;
  const promptBlocks = splitProfileBlocks(snapshot.redacted);

  return rawBlocks.flatMap((block, index) => {
    if (block.key === null) {
      return [];
    }

    const rule = locatedRule({
      existing: block,
      relativePath: options.relativePath,
    });
    const promptBlock = promptBlocks[index];

    if (!rule) {
      throw new Error("Profile rule is outside the reconciliation path shape");
    }

    if (!promptBlock) {
      return [];
    }

    const prompt = profileVisibleParts(promptBlock);
    const metadata = profileBlockMetadata(promptBlock);

    return [
      {
        rule,
        promptTitle: prompt.title,
        promptBody: prompt.body,
        promptAppliesWhen: metadata.appliesWhen,
        promptProposal: metadata.proposal,
      },
    ];
  });
}

async function readRejections(
  paths: ProjectPaths,
): Promise<readonly ProfileSnapshotRejection[]> {
  return readMaterializedProfileRejections({
    filePath: paths.rejectedProfileFile,
    profileDirectory: paths.profileDirectory,
  });
}

export async function readLegacyProfileSnapshot(
  paths: ProjectPaths,
): Promise<ProfileSnapshot> {
  const relativePaths = await profileFiles(paths.profileDirectory);

  const rules = (
    await Promise.all(
      relativePaths.map((relativePath) =>
        readRules({ profileDirectory: paths.profileDirectory, relativePath }),
      ),
    )
  ).flat();

  return { rules, rejections: await readRejections(paths) };
}
