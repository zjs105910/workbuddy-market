import { renderProfileBlocks } from "./writeBlocks";
import { commitLocalChanges, type FileUpdate } from "@shadowclone/changes";
import path from "node:path";
import { acquireLocalLock, readLocalText, ownedDirectory, ownedFile } from "@shadowclone/core";
import type { ProjectPaths } from "@shadowclone/core";
import { prepareProfileWrite } from "./lifecycle";
import { assertProfileRetention } from "./retention";
import type { GeneratedProfileStateEntry } from "./state";
import {
  renderGeneratedProfileState,
  renderProfileRejections,
} from "./stateRender";
import type {
  ProfileRule,
  ProfileRuleReference,
  ProfileWriteResult,
} from "./types";

export type ProfileWriteOptions = {
  readonly paths: ProjectPaths;
  readonly rules: readonly ProfileRule[];
  readonly retired?: readonly ProfileRuleReference[];
};

export async function writeLegacyProfile(
  options: ProfileWriteOptions,
): Promise<ProfileWriteResult> {

  await ownedDirectory(options.paths.profileDirectory);

  const lock = await acquireLocalLock(
    path.join(options.paths.shadowcloneDirectory, "profile-write.db"),
  );

  if (!lock) {
    throw new Error("Another profile update is running; retry shortly");
  }

  try {
    return await writeProfileRevision(options);
  } finally {
    lock.release();
  }
}

async function writeProfileRevision(
  options: ProfileWriteOptions,
): Promise<ProfileWriteResult> {
  const updates: FileUpdate[] = [];
  const previousManifest = await readLocalText(
    options.paths.profileManifestFile,
  );
  const previousRejections = await readLocalText(
    options.paths.rejectedProfileFile,
  );
  const prepared = await prepareProfileWrite({
    paths: options.paths,
    rules: options.rules,
    retiredReferences: options.retired ?? [],
  });
  const nextState = new Map<string, GeneratedProfileStateEntry>();
  const consumed = new Set<string>();
  let writtenFiles = 0;
  let ruleCount = 0;

  for (const file of prepared.files) {
    const nextBlocks = renderProfileBlocks({
      file,
      prepared,
      consumed,
      nextState,
    });

    if (nextBlocks.length > 0) {
      updates.push({
        filePath: file.filePath,
        next: `${nextBlocks.join("\n\n")}\n`,
        previous: file.content,
      });
      writtenFiles += 1;
      ruleCount += nextBlocks.length;
    } else if (file.blocks.length > 0) {
      updates.push({
        filePath: file.filePath,
        next: null,
        previous: file.content,
      });
    }
  }

  assertProfileRetention({
    files: prepared.files,
    written: new Set([...consumed, ...prepared.pinned]),
    retired: new Set(prepared.retired.keys()),
  });

  for (const entry of prepared.previousEntries) {
    if (
      entry.disposition === "present" &&
      !prepared.incoming.has(entry.key) &&
      !prepared.pinned.has(entry.key) &&
      !prepared.retired.has(entry.key)
    ) {
      nextState.set(entry.key, entry);
    }
  }

  for (const entry of prepared.retired.values()) {
    nextState.set(entry.key, entry);
  }

  updates.push({
    filePath: options.paths.profileManifestFile,
    next: renderGeneratedProfileState([...nextState.values()]),
    previous: previousManifest,
  });
  updates.push({
    filePath: options.paths.rejectedProfileFile,
    next: renderProfileRejections([...prepared.rejections.values()]),
    previous: previousRejections,
  });

  for (const update of updates.filter((update) => update.next !== null)) {
    await ownedDirectory(path.dirname(update.filePath));
    await ownedFile(update.filePath);
  }

  await commitLocalChanges({
    paths: options.paths,
    root: options.paths.profileDirectory,
    kind: "profile",
    updates,
  });

  return {
    files: writtenFiles,
    rules: ruleCount,
    rejected: prepared.rejections.size,
    preserved: prepared.incomingRules.filter((rule) =>
      prepared.pinned.has(rule.key),
    ).length,
  };
}
